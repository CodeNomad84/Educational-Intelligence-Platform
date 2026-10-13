# DEMO SCOPE — whole file. Settings for the school-meeting demo.
#
# Use:  DJANGO_SETTINGS_MODULE=config.settings.demo python manage.py <command>
# Uses a SEPARATE SQLite file (demo_db.sqlite3, gitignored via *.sqlite3). db.sqlite3 is never opened here.
# The demo app is added HERE (not in base.py) so normal/production runs are unaffected.
import copy

from .development import *  # noqa: F401,F403

DEMO_MODE = True
DEMO_DB_FILENAME = 'demo_db.sqlite3'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / DEMO_DB_FILENAME,  # noqa: F405
    }
}

INSTALLED_APPS = INSTALLED_APPS + ['demo_intel']  # noqa: F405

TEMPLATES = copy.deepcopy(TEMPLATES)  # noqa: F405
TEMPLATES[0]['OPTIONS']['context_processors'].append('demo_intel.context_processors.demo')
