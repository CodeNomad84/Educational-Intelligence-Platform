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
            keys = sorted(k for k in loader.disk_migrations if k[0] == app)
            self.assertEqual(keys[0], (app, '0001_initial'))
            if app == 'risk':
                self.assertEqual(keys, [('risk', '0001_initial'), ('risk', '0002_rules'), ('risk', '0003_rule_last_edited_by'), ('risk', '0004_rule_kind_repeated_concerns'), ('risk', '0005_notification'), ('risk', '0006_notification_unique'), ('risk', '0007_catalog_templates')])   # 0025: rule tables only (0003: one column on them; 0004: choices of Rule.kind, no SQL; 0005: Notification table; 0006: its unique constraints; 0007: catalog provenance columns and run counters)
            else:
                self.assertEqual(keys, [('interventions', '0001_initial'), ('interventions', '0002_strategy')])   # P6-1: one table + one nullable column
            for key in keys:
                for op in loader.disk_migrations[key].operations:
                    self.assertIsInstance(op, (migrations.CreateModel, migrations.AddIndex, migrations.AddConstraint, migrations.AddField, migrations.AlterField))   # new tables only (AlterField: choices of Rule.kind, state only)

    def test_models_are_not_in_the_django_admin(self):
        registered = {m._meta.label for m in admin.site._registry}
        for label in ('risk.Alert', 'risk.RiskEvent', 'interventions.InterventionPlan', 'interventions.InterventionFollowUp'):
            apps.get_model(label)
            self.assertNotIn(label, registered)
