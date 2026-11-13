"""Migration-order guard (docs/changes/0018): a database migrated from ZERO must give module rows only to the schools that should
have them, i.e. none. ``students.0009`` always creates 'Default School' and ``schools.0010`` backfills ``tutor_ai`` for every school
that exists when it runs; if a new migration's dependencies flip their order, a fresh install silently licenses a module for
the default school. An explicit dependency cannot fix this without breaking databases that are behind on migrations (see the
change note), so this test is the guard. It migrates a throw-away in-memory SQLite database in a fresh interpreter and does not
touch any real file."""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent
PROBE = r"""
import json, os
from django.conf import settings
settings.DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
call_command('migrate', verbosity=0, interactive=False)
from schools.models import School, SchoolModule
plan = [(m.app_label, m.name) for m, _backwards in MigrationExecutor(connection).migration_plan(
    [n for n in MigrationExecutor(connection).loader.graph.leaf_nodes()], clean_start=True)]
print(json.dumps({
    'schools': sorted(School.objects.values_list('code', flat=True)),
    'modules': sorted(SchoolModule.objects.values_list('school__code', 'module_key')),
    'order': {'schools_0010': plan.index(('schools', '0010_backfill_school_modules')),
              'students_0009': plan.index(('students', '0009_link_students_to_classes'))}}))
"""


WHY = ('Migration order regressed: schools.0010 (module backfill) must run BEFORE students.0009 (creates Default School), otherwise a fresh '
       'database licenses tutor_ai for the default school. Do NOT add a dependency edge between them: it breaks databases that are behind '
       'on migrations. Look at the dependencies of the newest migration instead (see docs/RUNBOOK.md, open risk "Migration-order '
       'fragility", and docs/changes/0018-migration-order-guard.md).')


class FreshMigrateTests(SimpleTestCase):
    def probe(self):
        env = {'PATH': os.environ.get('PATH', ''), 'DJANGO_SETTINGS_MODULE': 'config.settings.test_sqlite',
               'PYTHONDONTWRITEBYTECODE': '1', 'SECRET_KEY': 'k3y-' + 'abcdefghijklmnopqrstuvwxyz0123456789' * 2}
        result = subprocess.run([sys.executable, '-c', PROBE], cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_fresh_database_has_no_module_rows_and_the_backfill_runs_before_the_default_school_exists(self):
        found = self.probe()
        self.assertEqual(found['schools'], ['default'])                  # students.0009 creates the default school ...
        self.assertEqual(found['modules'], [], WHY)                      # ... and it must NOT be licensed anything
        order = found['order']
        self.assertLess(order['schools_0010'], order['students_0009'], WHY + f' Plan positions: {order}')
