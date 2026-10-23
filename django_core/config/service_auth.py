"""Short-lived service token for Django -> FastAPI calls (interim, ADR-0002 PROPOSED).

The token carries the end user's id and recognised roles so FastAPI can authorise the
request. It is signed (HS256) with ``settings.SERVICE_JWT_SECRET``, which has no default.
"""
import time

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

ISSUER = 'school-django'
AUDIENCE = 'school-fastapi'
TTL_SECONDS = 60
MIN_SECRET_LENGTH = 32
MIN_DISTINCT_CHARS = 10
_PLACEHOLDER_PREFIXES = ('django-insecure', 'changeme', 'change-me', 'change_me', 'your-', 'your_',
                         'placeholder', 'example', 'secret', 'password', 'replace')


def _is_weak(secret):
    """Too short, a known placeholder, low-entropy, or the same value as Django's SECRET_KEY."""
    return (
        len(secret) < MIN_SECRET_LENGTH
        or secret.lower().startswith(_PLACEHOLDER_PREFIXES)
        or len(set(secret)) < MIN_DISTINCT_CHARS
        or secret == getattr(settings, 'SECRET_KEY', None)
    )


def service_headers(user):
    """Authorization headers for a FastAPI call made on behalf of ``user``.

    Raises ImproperlyConfigured when the secret is missing/too short (fail closed).
    """
    from students.access import roles_for, school_ids_for_admin  # local import: avoid app-loading cycles

    secret = getattr(settings, 'SERVICE_JWT_SECRET', '') or ''
    if _is_weak(secret):
        raise ImproperlyConfigured(
            'SERVICE_JWT_SECRET is not configured (min %d characters, not a placeholder, not SECRET_KEY).'
            % MIN_SECRET_LENGTH
        )
    now = int(time.time())
    payload = {
        'iss': ISSUER,
        'aud': AUDIENCE,
        'sub': str(user.pk),
        'roles': sorted(roles_for(user)),
        # SchoolAdmin scope (FastAPI filters documents by it, ACL before retrieval); empty for every other role
        'schools': sorted(school_ids_for_admin(user)),
        'iat': now,
        'exp': now + TTL_SECONDS,
    }
    token = jwt.encode(payload, secret, algorithm='HS256')
    if isinstance(token, bytes):  # PyJWT < 2 returned bytes
        token = token.decode('ascii')
    return {'Authorization': f'Bearer {token}'}
