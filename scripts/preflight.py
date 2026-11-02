#!/usr/bin/env python3
"""Deployment preflight (P9): checks a profile's environment file BEFORE anything is started. Reads KEY=VALUE lines as data (the file is
never executed or sourced) and prints only key names and fixed messages, never a value. Exit 0 = ready, 1 = problems, 2 = usage.

    scripts/preflight.py <env file> [--profile shared|dedicated]

Checks: required keys present and not placeholders (CHANGE_ME, example, changeme...), secret lengths and distinctness (SECRET_KEY,
SERVICE_JWT_SECRET, the three database passwords), DEBUG off, HTTPS settings on, ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS without wildcards
or http://, a backup key set, and (dedicated) a single-school server name. It does NOT touch a server, a database or the network."""
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r'(change[_-]?me|changeme|example|placeholder|your[_-]|replace|secret|password|django-insecure|xxx)', re.I)
REQUIRED = ['SECRET_KEY', 'SERVICE_JWT_SECRET', 'DB_ADMIN_PASSWORD', 'DB_OWNER_PASSWORD', 'DB_APP_PASSWORD', 'ALLOWED_HOSTS',
            'CSRF_TRUSTED_ORIGINS', 'EIP_BACKUP_PUBKEY']
SECRETS = {'SECRET_KEY': 50, 'SERVICE_JWT_SECRET': 32, 'DB_ADMIN_PASSWORD': 16, 'DB_OWNER_PASSWORD': 16, 'DB_APP_PASSWORD': 16}


def parse(path):
    env = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        env[key.strip()] = value.strip().strip('"\'')
    return env


def check(env, profile='shared'):
    problems = []
    for key in REQUIRED:
        if not env.get(key):
            problems.append(f'{key}: missing')
        elif PLACEHOLDER.search(env[key]) and key in SECRETS:
            problems.append(f'{key}: looks like a placeholder')
    for key, minimum in SECRETS.items():
        if env.get(key) and len(env[key]) < minimum:
            problems.append(f'{key}: shorter than {minimum} characters')
    values = [env.get(k) for k in ('SECRET_KEY', 'SERVICE_JWT_SECRET', 'DB_ADMIN_PASSWORD', 'DB_OWNER_PASSWORD', 'DB_APP_PASSWORD') if env.get(k)]
    if len(values) != len(set(values)):
        problems.append('secrets: two of SECRET_KEY, SERVICE_JWT_SECRET and the database passwords are equal')
    if env.get('DEBUG', '').lower() in ('1', 'true', 'yes', 'on') or env.get('DJANGO_DEBUG', '').lower() in ('1', 'true', 'yes', 'on'):
        problems.append('DEBUG: must be off')
    for key in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE'):
        if env.get(key, '1').lower() in ('0', 'false', 'no', 'off'):
            problems.append(f'{key}: must stay on')
    hosts = [h.strip() for h in env.get('ALLOWED_HOSTS', '').split(',') if h.strip()]
    if not hosts or any(h in ('*', 'localhost', '127.0.0.1') or h.startswith('.') and h.count('.') < 2 for h in hosts):
        problems.append('ALLOWED_HOSTS: must list the real host names (no *, no localhost)')
    origins = [o.strip() for o in env.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
    if not origins or any(not o.startswith('https://') or '*' in o for o in origins):
        problems.append('CSRF_TRUSTED_ORIGINS: https:// origins only, no wildcard')
    if profile == 'dedicated' and len(hosts) > 2:
        problems.append('ALLOWED_HOSTS: a dedicated (single school) server should name one host (plus www at most)')
    if env.get('DB_USER') in ('school_user', 'school_admin', 'postgres'):
        problems.append('DB_USER: must not be a superuser role (R-04)')
    return problems


def main(argv):
    if len(argv) < 2 or argv[1].startswith('-'):
        print(__doc__)
        return 2
    profile = argv[argv.index('--profile') + 1] if '--profile' in argv else 'shared'
    problems = check(parse(argv[1]), profile)
    for p in problems:
        print('PROBLEM', p)
    print('preflight:', 'READY (no server was contacted)' if not problems else f'{len(problems)} problem(s)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
