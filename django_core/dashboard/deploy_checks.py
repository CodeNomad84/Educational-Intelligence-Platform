"""Project checks for `manage.py check --deploy` (P3 C-H), on top of Django's own deploy checks (DEBUG, SECRET_KEY, secure
cookies, HSTS, SSL redirect). Run against the production settings before every release:

    DJANGO_SETTINGS_MODULE=config.settings.production python manage.py check --deploy --fail-level WARNING
"""
import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Info, Tags, Warning, register

LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1', '[::1]'}
# A page must not load a script, stylesheet, font or image from another site: on the national network during an
# international outage it would break, and it leaks visits to a third party (decision pack 0028 P3-4).
EXTERNAL_ASSET = re.compile(r'<(?:script|link|img|iframe)\b[^>]*\b(?:src|href)\s*=\s*["\']?(?:https?:)?//', re.I)
EXTERNAL_CSS = re.compile(r'(?:@import\s+(?:url\()?|url\()\s*["\']?(?:https?:)?//', re.I)


LOCAL_ORIGIN_PREFIXES = ('http://localhost:', 'http://127.0.0.1:', 'http://[::1]:')


def cors_origin_errors():
    """``CORS_ALLOWED_ORIGINS`` may only name https origins (ADR-0014, D2). A wildcard is always an error: with
    ``CORS_ALLOW_CREDENTIALS`` the browser would let any site read the session's answers. A loopback http origin
    (``http://localhost:5173``, the dev list in ``development.py``) is tolerated: it can only be the developer's own
    machine, and it grants nothing to a remote site."""
    origins = [str(o).strip() for o in (getattr(settings, 'CORS_ALLOWED_ORIGINS', None) or [])]
    if getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False) or '*' in origins:
        return [Error('CORS_ALLOW_ALL_ORIGINS / "*" is never allowed: name each origin explicitly, or none.', id='eip.E007')]
    errors = []
    for origin in origins:
        if origin.startswith('https://') or origin.startswith(LOCAL_ORIGIN_PREFIXES):
            continue
        errors.append(Error(f'CORS_ALLOWED_ORIGINS entry {origin!r} must be an https:// origin (eip.E007).',
                            id='eip.E007'))
    return errors


@register(Tags.security, deploy=True)
def check_hosts_and_origins(app_configs, **kwargs):
    errors = []
    hosts = [h.strip() for h in settings.ALLOWED_HOSTS if h.strip()]
    if not hosts or '*' in hosts or set(hosts) <= LOCAL_HOSTS:
        errors.append(Error('ALLOWED_HOSTS must list the public host name(s), without "*".', id='eip.E001'))
    bad = [o for o in getattr(settings, 'CSRF_TRUSTED_ORIGINS', []) if not o.startswith('https://')]
    if bad:
        errors.append(Error('CSRF_TRUSTED_ORIGINS entries must start with https://.', id='eip.E002'))
    errors += cors_origin_errors()
    if getattr(settings, 'SECURE_SSL_REDIRECT', False) and not getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        errors.append(Warning('SECURE_SSL_REDIRECT without SECURE_PROXY_SSL_HEADER loops behind a TLS proxy; '
                              'set EIP_BEHIND_TLS_PROXY=1 unless Django terminates TLS itself.', id='eip.W003'))
    if 0 < getattr(settings, 'SECURE_HSTS_SECONDS', 0) < 31536000:
        errors.append(Info(f'HSTS is still staged ({settings.SECURE_HSTS_SECONDS} s); raise SECURE_HSTS_SECONDS step by step to '
                           '31536000 once HTTPS is stable.', id='eip.I006'))
    return errors


@register(Tags.security, deploy=True)
def check_database_password(app_configs, **kwargs):
    return database_password_errors(settings.DATABASES.get('default', {}))


def database_password_errors(db):
    if 'postgresql' in db.get('ENGINE', '') and not db.get('PASSWORD'):
        return [Error('The PostgreSQL password is empty (DB_PASSWORD).', id='eip.E005')]
    return []


def external_asset_references():
    """(path, line number) of every first-party template that loads an asset from another site."""
    found = []
    base = Path(settings.BASE_DIR).resolve()
    for config in apps.get_app_configs():
        folder = Path(config.path).resolve() / 'templates'
        if base not in folder.parents or '.venv' in folder.parts or not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*.html')):
            for number, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
                if EXTERNAL_ASSET.search(line) or EXTERNAL_CSS.search(line):
                    found.append((str(path.relative_to(base)), number))
    return found


@register(Tags.security, deploy=True)
def check_no_external_assets(app_configs, **kwargs):
    return [Error(f'{path}:{line} loads an asset from another site; serve it from static files.', id='eip.E004')
            for path, line in external_asset_references()]
