import secrets

from .base import *

DEBUG = True

# Development only: when SECRET_KEY is not set, use a random per-process key (never a
# hard-coded value). Sessions do not survive a restart; set SECRET_KEY in .env to keep them.
if not SECRET_KEY:
    SECRET_KEY = 'django-insecure-dev-' + secrets.token_urlsafe(50)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'fa-ir'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_TZ = True

# Local dev / demo / tests keep the pre-pilot behaviour: AI assistants and the Counselor role stay
# reachable (still gated by roles and entitlements). The pilot/production defaults (base.py) leave
# both OFF until an operator opts in.
ENABLE_AI_FEATURES = True
ENABLE_COUNSELOR_ROLE = True