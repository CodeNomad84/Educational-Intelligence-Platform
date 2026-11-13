from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# No default: an empty key makes Django raise ImproperlyConfigured (fail closed).
# development.py supplies a per-process key; production.py validates this one.
SECRET_KEY = os.environ.get('SECRET_KEY', '')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Platform branding (T10): ONE source for every template, exposed as PLATFORM_NAME / PLATFORM_NAME_EN by
# dashboard.context_processors.role_names. Never a literal in a template and never a school-specific value
# (CLAUDE.md §7): the school's own name comes from the School row (SCHOOL_NAME), this is the product name.
PLATFORM_NAME = os.environ.get('EIP_PLATFORM_NAME', 'سکوی آموزشی-تربیتی آرمان نو')
PLATFORM_NAME_EN = os.environ.get('EIP_PLATFORM_NAME_EN', 'Arman-e-No Educational & Upbringing Platform')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'students',
    'dashboard',
    'schools',
    'vocabulary',
    'missions',
    'exams',
    'risk',
    'interventions',
    'docqa',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'dashboard.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dashboard.context_processors.role_names',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Dashboard login page (namespaced URL). Without this, login_required redirects
# to Django's default /accounts/login/, which does not exist.
LOGIN_URL = 'dashboard:login'
# Login throttle client address (dashboard/throttle.py). OFF by default: the address is REMOTE_ADDR and X-Forwarded-For is NEVER read.
# Behind a reverse proxy set THROTTLE_TRUSTED_PROXIES to the proxy address(es)/networks (comma separated, e.g. "10.0.0.5,172.18.0.0/16");
# only then, and only for a request that really comes from one of them, the real client is taken from X-Forwarded-For.
THROTTLE_TRUSTED_PROXIES = [x.strip() for x in os.environ.get('THROTTLE_TRUSTED_PROXIES', '').split(',') if x.strip()]

# Django -> FastAPI service trust (ADR-0002, interim). Read from the environment only;
# there is deliberately NO default. Empty/short value => service calls fail closed.
SERVICE_JWT_SECRET = os.environ.get('SERVICE_JWT_SECRET', '')

# Display name of the single default School row created by the class-link data migration (ADR-0004).
# Deliberately neutral: a deployment must set the real school name here (or edit the School in the admin).
DEFAULT_SCHOOL_NAME = os.environ.get('DEFAULT_SCHOOL_NAME', 'Default School')

# JWT: a token carries a hash of the account's password and is rejected once the password changed (reset by an admin or a Grade Lead,
# forced change, user change). Without this a refresh token issued before a reset kept working for its whole lifetime
# (independent review 0027 finding 2). No new table, no migration.
SIMPLE_JWT = {'CHECK_REVOKE_TOKEN': True}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}
# AI trial guard defaults (schools/ai_guard.py); a School can override both. Not billing.
AI_DEFAULT_DAILY_CAP = 100
AI_DEFAULT_MONTHLY_CAP = 1000


# --- Pilot configuration (T6, docs/pilot/PILOT_CONFIG.md) ---
def _env_bool(name, default=False):
    """Parse an environment flag; the default is fail-closed (False)."""
    return os.environ.get(name, '1' if default else '0').strip().lower() in ('1', 'true', 'yes', 'on')


# Operator switches for the pilot deployment. The defaults are the SAFE (fail-closed) state: AI
# assistants and the Counselor role are OFF until an operator explicitly enables them.
# development.py turns them back ON for local dev/demo/tests; production (this file's defaults)
# stays off. PILOT_MODE is a marker only — the real gates are ENABLE_AI_FEATURES and
# ENABLE_COUNSELOR_ROLE.
PILOT_MODE = _env_bool('PILOT_MODE', False)
ENABLE_AI_FEATURES = _env_bool('ENABLE_AI_FEATURES', False)
ENABLE_COUNSELOR_ROLE = _env_bool('ENABLE_COUNSELOR_ROLE', False)
# Global feedback link shown in the footer of every authenticated page. Empty = hidden. Rendered
# verbatim: it MUST be a fixed, student-data-free URL (a form/survey link), never a URL carrying ids.
FEEDBACK_URL = os.environ.get('FEEDBACK_URL', '').strip()
