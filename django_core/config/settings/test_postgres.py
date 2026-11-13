"""Settings for running the test suite against PostgreSQL in a DISPOSABLE container (``scripts/run_tests.sh pg``).

Everything comes from the environment; there is no default for the host or the password, and nothing is read from
``.env``. The database name must start with ``eip_test``, so these settings can never be pointed at the real database
by accident (Django's test runner creates its own ``test_<name>`` database and never touches the real data anyway).

    TEST_PG_HOST      (required)  container host name on the private test network
    TEST_PG_PASSWORD  (required)  random per run, passed by the script through the environment
    TEST_PG_NAME      default eip_test
    TEST_PG_USER      default eip_test
    TEST_PG_PORT      default 5432
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .development import *  # noqa: F401,F403


def _required(name):
    value = os.environ.get(name, '')
    if not value:
        raise ImproperlyConfigured(f'{name} is required for config.settings.test_postgres (see scripts/run_tests.sh pg).')
    return value


# Fast hasher for disposable test databases only (see config/settings/test_sqlite.py): these settings cannot reach real data.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

_name = os.environ.get('TEST_PG_NAME', 'eip_test')
if not _name.startswith('eip_test'):
    raise ImproperlyConfigured('TEST_PG_NAME must start with "eip_test": these settings are for disposable test databases only.')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _name,
        'USER': os.environ.get('TEST_PG_USER', 'eip_test'),
        'PASSWORD': _required('TEST_PG_PASSWORD'),
        'HOST': _required('TEST_PG_HOST'),
        'PORT': os.environ.get('TEST_PG_PORT', '5432'),
    }
}
