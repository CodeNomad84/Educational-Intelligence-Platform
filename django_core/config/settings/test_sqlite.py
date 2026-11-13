"""Settings for running the test suite on SQLite (``scripts/run_tests.sh sqlite``, step "manage.py test students dashboard ...").

Identical to development except for ONE thing: a fast password hasher. Almost every test creates users, and the production
hasher (PBKDF2, about 1 million iterations) costs roughly 0.3 s per password, which made up most of the run time. MD5 is
used here ONLY: never in development, demo or production (``schools/test_settings_hashers.py`` proves the other settings
still use a strong hasher). Tests do not depend on the hash algorithm, only on ``check_password``.
"""
from .development import *  # noqa: F401,F403

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
