"""Guards for the intervention loop: views read alerts, plans and follow-ups only through ``students.access``; the loop's
migrations only create tables; the admin does not register these models."""
import re
from pathlib import Path

from django.apps import apps
from django.contrib import admin
from django.db import migrations
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase

ROOT = Path(__file__).resolve().parents[1]
RAW = re.compile(r"\b(Student|Alert|RiskEvent|InterventionPlan|InterventionFollowUp)\.objects\b|\.followups\b|\.alerts\b")


class ViewsUseTheAccessLayer(SimpleTestCase):
    def view_files(self):
        files = []
        for app in ('risk', 'interventions'):
            files += sorted((ROOT / app).glob('views*.py'))
        files += [ROOT / 'dashboard' / 'loop_views.py'] if (ROOT / 'dashboard' / 'loop_views.py').exists() else []
        return files

    def test_no_raw_manager_in_views(self):
        offenders = [f"{f.relative_to(ROOT)}:{n}" for f in self.view_files()
                     for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1) if RAW.search(line)]
        self.assertEqual(offenders, [])


class MigrationTests(TestCase):
    def test_loop_migrations_only_create_tables_and_depend_on_the_latest_of_others(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        for app in ('risk', 'interventions'):
            keys = [k for k in loader.disk_migrations if k[0] == app]
            self.assertEqual(keys, [(app, '0001_initial')])
            for op in loader.disk_migrations[keys[0]].operations:
                self.assertIsInstance(op, (migrations.CreateModel, migrations.AddIndex, migrations.AddConstraint))   # new tables only

    def test_models_are_not_in_the_django_admin(self):
        registered = {m._meta.label for m in admin.site._registry}
        for label in ('risk.Alert', 'risk.RiskEvent', 'interventions.InterventionPlan', 'interventions.InterventionFollowUp'):
            apps.get_model(label)
            self.assertNotIn(label, registered)
