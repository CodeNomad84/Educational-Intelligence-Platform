"""Settings of ``scripts/backup_restore_check.sh``: the demo application (same apps as ``config.settings.demo``) on a
database chosen by the environment, so a RESTORED copy can be checked with the normal management commands.

    RC_SQLITE_PATH   path of a SQLite file (default engine). The real and demo files are refused by name.
    RC_PG_HOST       set it to use PostgreSQL instead; then RC_PG_PASSWORD is required
    RC_PG_NAME       must start with ``eip_restore`` (default eip_restore_dst)
    RC_PG_USER       default eip_restore;  RC_PG_PORT default 5432

There are no defaults for the path, host or password and nothing is read from ``.env``: these settings can not be pointed at
``db.sqlite3``, ``demo_db.sqlite3`` or a real PostgreSQL database by accident.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .demo import *  # noqa: F401,F403


def _required(name):
    value = os.environ.get(name, '')
    if not value:
        raise ImproperlyConfigured(f'{name} is required for config.settings.restore_check (see scripts/backup_restore_check.sh).')
    return value


if os.environ.get('RC_PG_HOST'):
    _name = os.environ.get('RC_PG_NAME', 'eip_restore_dst')
    if not _name.startswith('eip_restore'):
        raise ImproperlyConfigured('RC_PG_NAME must start with "eip_restore": disposable databases only.')
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': _name, 'USER': os.environ.get('RC_PG_USER', 'eip_restore'),
        'PASSWORD': _required('RC_PG_PASSWORD'), 'HOST': os.environ['RC_PG_HOST'], 'PORT': os.environ.get('RC_PG_PORT', '5432')}}
else:
    _path = Path(_required('RC_SQLITE_PATH')).resolve()
    if _path.name in ('db.sqlite3', 'demo_db.sqlite3'):
        raise ImproperlyConfigured('RC_SQLITE_PATH must be a COPY, never the real or the demo database file.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': _path}}
