from .base import *
import os

from django.core.exceptions import ImproperlyConfigured

# DEBUG is fixed to False here on purpose: there is no environment override.
DEBUG = False

# Fail closed on a missing or placeholder SECRET_KEY (same policy as config/service_auth.py;
# duplicated because that module needs configured settings at import time).
_MIN_SECRET_LENGTH = 32
_PLACEHOLDER_PREFIXES = ('django-insecure', 'changeme', 'change-me', 'change_me', 'your-', 'your_',
                         'placeholder', 'example', 'secret', 'password', 'replace')
if (
    len(SECRET_KEY) < _MIN_SECRET_LENGTH
    or SECRET_KEY.lower().startswith(_PLACEHOLDER_PREFIXES)
    or len(set(SECRET_KEY)) < 10
):
    raise ImproperlyConfigured(
        'SECRET_KEY is missing, too short (min %d characters) or a placeholder; production refuses to start.'
        % _MIN_SECRET_LENGTH
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'school_db'),
        'USER': os.environ.get('DB_USER', 'school_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'postgres'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': CELERY_BROKER_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

LANGUAGE_CODE = 'fa-ir'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_TZ = True

# ---------- HTTPS and browser hardening (P3 C-H; docs/DEPLOYMENT.md "HTTPS for a .ir domain") ----------
# TLS ends at a reverse proxy (any: nginx, Caddy, HAProxy). The proxy MUST overwrite X-Forwarded-Proto; gunicorn must listen on
# loopback or a private network only, otherwise a client could forge the header. EIP_BEHIND_TLS_PROXY=0 for direct TLS.
def _env_flag(name, default):
    return os.environ.get(name, '1' if default else '0').strip().lower() in ('1', 'true', 'yes', 'on')


if _env_flag('EIP_BEHIND_TLS_PROXY', True):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = _env_flag('SECURE_SSL_REDIRECT', True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
# HSTS is staged (decision pack 0028 P3-3): 1 hour by default; raise to 604800, then 31536000 once HTTPS is stable.
# Preload stays off: it cannot be undone quickly.
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '3600'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_flag('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = False
# Deliberate (0028 P3-3), so `check --deploy --fail-level WARNING` can gate a release: no preload; includeSubDomains is opt-in.
SILENCED_SYSTEM_CHECKS = ['security.W021'] + ([] if SECURE_HSTS_INCLUDE_SUBDOMAINS else ['security.W005'])
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Console only, WARNING and above. No e-mail handler (Django's mail_admins would send request details), no request bodies.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False}},
}
