"""Tests for ``students.0010_rename_admin_group_to_schooladmin`` and the no-literal rule (ADR-0010).

The forward/backward functions are run against the disposable test database (never a real one).
Traceability: ADR-0010 decision 2 (rename), ADR-0003 (deny by default: an unknown group grants no role).
"""
import importlib
import re
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import SimpleTestCase, TestCase

from students.access import ADMIN, roles_for

migration = importlib.import_module('students.migrations.0010_rename_admin_group_to_schooladmin')
ROOT = Path(__file__).resolve().parents[1]


class RenameMigrationTests(TestCase):
    def test_constant_is_the_new_name(self):
        self.assertEqual(ADMIN, 'SchoolAdmin')

    def test_forward_preserves_id_members_and_permissions(self):
        group = Group.objects.create(name='Admin')
        perm = Permission.objects.first()
        group.permissions.add(perm)
        user = get_user_model().objects.create_user(username='a')
        user.groups.add(group)
        migration.forwards(apps, None)
        group.refresh_from_db()
        self.assertEqual(group.name, 'SchoolAdmin')
        self.assertEqual(list(group.user_set.all()), [user])
        self.assertEqual(list(group.permissions.all()), [perm])
        self.assertIn(ADMIN, roles_for(user))

    def test_backward_restores_old_name(self):
        group = Group.objects.create(name='SchoolAdmin')
        migration.backwards(apps, None)
        group.refresh_from_db()
        self.assertEqual(group.name, 'Admin')

    def test_collision_aborts_and_changes_nothing(self):
        Group.objects.create(name='Admin')
        Group.objects.create(name='SchoolAdmin')
        with self.assertRaises(RuntimeError):
            migration.forwards(apps, None)
        self.assertEqual(sorted(Group.objects.values_list('name', flat=True)), ['Admin', 'SchoolAdmin'])

    def test_fresh_database_is_a_no_op(self):
        migration.forwards(apps, None)
        migration.backwards(apps, None)
        self.assertFalse(Group.objects.exists())

    def test_old_name_alone_grants_no_role(self):
        """Fail closed: a user still in a group named 'Admin' (migration not applied) has no role."""
        user = get_user_model().objects.create_user(username='old')
        user.groups.add(Group.objects.create(name='Admin'))
        self.assertEqual(roles_for(user), set())


class NoAdminLiteralTests(SimpleTestCase):
    def test_no_admin_group_literal_in_code_or_templates(self):
        pattern = re.compile(r"""['"]Admin['"]""")
        offenders = []
        # django_core code and templates plus the repo launch scripts (seed_demo and start_demo.sh are demo paths)
        paths = list(ROOT.rglob('*.py')) + list(ROOT.rglob('*.html')) + list(ROOT.parent.glob('scripts/**/*.sh'))
        for path in paths:
            rel = path.relative_to(ROOT.parent)
            parts = rel.parts
            if '.venv' in parts or 'staticfiles' in parts or 'migrations' in parts:
                continue
            if rel.name == 'test_migration_0010.py':
                continue
            if pattern.search(path.read_text(encoding='utf-8')):
                offenders.append(str(rel))
        self.assertEqual(offenders, [])
