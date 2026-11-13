import os
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

# --- Local dev only (ADR-0014, docs/changes/0040 §4.1): the two Vite frontends ---
# The SPA reverse proxy (D2, recommended) makes the browser talk to ONE origin, so nothing here is needed for it. These
# entries exist for a developer who calls Django cross-origin by hand; production (production.py) never inherits them,
# where the env-only list in base.py applies and eip.E007 keeps it https-only.
CORS_ALLOWED_ORIGINS = sorted(set(CORS_ALLOWED_ORIGINS) | {
    'http://localhost:5173', 'http://localhost:5174',
    'http://127.0.0.1:5173', 'http://127.0.0.1:5174',
})
CORS_ALLOW_CREDENTIALS = True
# Direct cross-origin POSTs by hand ALSO need the origin trusted by Django's own CSRF check; the proxy (D2) does not,
# because then the browser's Origin equals the host. Env-only, so no http origin leaks into the deploy check.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
