"""setup_staff_roles (proposal 0002 C4, ADR-0005 §9): groups with zero permissions, explicit Admin grant."""
from io import StringIO

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from students.access import ADMIN, COUNSELOR, GRADE_LEAD, TEACHER
from students.tests import make_user

STAFF = (TEACHER, GRADE_LEAD, COUNSELOR)


def run(*args):
    out = StringIO()
    call_command('setup_staff_roles', *args, stdout=out)
    return out.getvalue()


class StaffRoleGroupTests(TestCase):
    def test_creates_three_groups_with_zero_permissions(self):
        text = run()
        for name in STAFF:
            group = Group.objects.get(name=name)
            self.assertEqual(group.permissions.count(), 0, name)
            self.assertIn(f'group {name}: created', text)

    def test_is_idempotent(self):
        run()
        text = run()
        self.assertEqual(Group.objects.filter(name__in=STAFF).count(), 3)
        self.assertIn('exists', text)
        self.assertNotIn('created', text)

    def test_permission_found_is_reported_not_removed_by_default(self):
        run()
        perm = Permission.objects.get(content_type__app_label='schools', codename='view_school')
        Group.objects.get(name=GRADE_LEAD).permissions.add(perm)
        with self.assertRaises(CommandError):
            run()
        self.assertEqual(Group.objects.get(name=GRADE_LEAD).permissions.count(), 1)

    def test_fix_removes_permissions_and_lists_them(self):
        run()
        perm = Permission.objects.get(content_type__app_label='schools', codename='view_school')
        Group.objects.get(name=COUNSELOR).permissions.add(perm)
        text = run('--fix')
        self.assertIn('schools.view_school', text)
        self.assertEqual(Group.objects.get(name=COUNSELOR).permissions.count(), 0)

    def test_does_not_touch_users_or_staff_flags(self):
        user = make_user('lead_user', GRADE_LEAD)
        run()
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_group_member_cannot_open_the_admin_site(self):
        run()
        for name in STAFF:
            self.client.force_login(make_user(f'u_{name}', name))
            resp = self.client.get('/admin/')
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn('/admin/login/', resp['Location'], name)


class AdminGrantTests(TestCase):
    def test_grant_requires_existing_admin_group(self):
        with self.assertRaises(CommandError):
            run('--grant-admin-assignments')
        self.assertFalse(Group.objects.filter(name=ADMIN).exists())

    def test_grant_gives_only_school_structure_permissions(self):
        admin_group = Group.objects.create(name=ADMIN)
        text = run('--grant-admin-assignments')
        got = set(admin_group.permissions.values_list('content_type__app_label', 'codename'))
        self.assertEqual(got, {
            ('schools', 'view_school'),
            ('schools', 'view_schoolclass'), ('schools', 'add_schoolclass'), ('schools', 'change_schoolclass'),
            ('schools', 'view_teacherassignment'), ('schools', 'add_teacherassignment'),
            ('schools', 'change_teacherassignment'), ('schools', 'delete_teacherassignment'),
            ('schools', 'view_gradeleadassignment'), ('schools', 'add_gradeleadassignment'),
            ('schools', 'change_gradeleadassignment'), ('schools', 'delete_gradeleadassignment'),
            ('schools', 'view_academicyear'), ('schools', 'add_academicyear'), ('schools', 'change_academicyear'),
        })
        self.assertFalse(any(app in ('auth', 'students') for app, _ in got))
        self.assertIn('is_staff', text)

    def test_grant_is_idempotent_and_leaves_staff_groups_empty(self):
        admin_group = Group.objects.create(name=ADMIN)
        run('--grant-admin-assignments')
        run('--grant-admin-assignments')
        self.assertEqual(admin_group.permissions.count(), 15)
        for name in STAFF:
            self.assertEqual(Group.objects.get(name=name).permissions.count(), 0)

    def test_grant_does_not_make_anyone_staff(self):
        Group.objects.create(name=ADMIN)
        user = make_user('office', ADMIN)
        run('--grant-admin-assignments')
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
