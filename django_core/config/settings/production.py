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