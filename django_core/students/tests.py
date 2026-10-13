"""Phase 1 tests: boot sanity, migrations, API authentication and object-level authorization.

All data is synthetic. Run with:  python manage.py test students dashboard
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .access import ADMIN, PARENT, TEACHER, roles_for, visible_students
from .models import Student

User = get_user_model()


def make_user(username, group=None, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


def make_student(national_id, parent=None, first='Student'):
    return Student.objects.create(
        first_name=first, last_name=national_id, national_id=national_id,
        grade=8, phone_number='0', parent_user=parent,
    )


class BootAndMigrationTests(TestCase):
    def test_system_check_clean(self):
        call_command('check')

    def test_dashboard_models_have_migration(self):
        # B-02/D-02: the dashboard models must be covered by a migration (no pending changes).
        call_command('makemigrations', 'dashboard', '--check', '--dry-run')

    def test_predict_route_registered(self):
        # B-03: the single predict action must be routable.
        self.assertEqual(reverse('student-predict-status', args=[1]), '/api/students/1/predict/')

    def test_urls_resolve(self):
        for name in ('dashboard:login', 'dashboard:dashboard', 'dashboard:student_list'):
            reverse(name)


class AccessPolicyTests(TestCase):
    def setUp(self):
        self.parent_a = make_user('parent_a', PARENT)
        self.parent_b = make_user('parent_b', PARENT)
        self.child_a = make_student('0000000001', self.parent_a)
        self.child_b = make_student('0000000002', self.parent_b)

    def test_roles(self):
        self.assertEqual(roles_for(self.parent_a), {PARENT})
        self.assertEqual(roles_for(make_user('nogroup')), set())
        self.assertEqual(roles_for(make_user('root', is_superuser=True)), {ADMIN})

    def test_visible_students_deny_by_default(self):
        self.assertEqual(list(visible_students(self.parent_a)), [self.child_a])
        self.assertEqual(visible_students(make_user('nogroup')).count(), 0)
        # Teacher student access is disabled until a verified assignment model exists (S-04).
        self.assertEqual(visible_students(make_user('t', TEACHER)).count(), 0)
        self.assertEqual(visible_students(make_user('a', ADMIN)).count(), 2)


class StudentApiAuthzTests(TestCase):
    def setUp(self):
        self.parent_a = make_user('parent_a', PARENT)
        self.parent_b = make_user('parent_b', PARENT)
        self.teacher = make_user('teacher_a', TEACHER)
        self.admin = make_user('admin_a', ADMIN)
        self.nogroup = make_user('nogroup')
        self.child_a = make_student('0000000001', self.parent_a)
        self.child_b = make_student('0000000002', self.parent_b)

    def detail(self, student):
        return f'/api/students/{student.pk}/'

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get('/api/students/').status_code, (401, 403))
        self.assertIn(self.client.get(self.detail(self.child_a)).status_code, (401, 403))

    def test_parent_own_child_allowed(self):
        self.client.force_login(self.parent_a)
        self.assertEqual(self.client.get(self.detail(self.child_a)).status_code, 200)

    def test_parent_other_child_denied(self):
        self.client.force_login(self.parent_a)
        self.assertEqual(self.client.get(self.detail(self.child_b)).status_code, 404)

    def test_parent_list_contains_only_own_child(self):
        self.client.force_login(self.parent_a)
        ids = [r['id'] for r in self.client.get('/api/students/').json()['results']]
        self.assertEqual(ids, [self.child_a.pk])

    def test_unauthorized_role_sees_nothing(self):
        self.client.force_login(self.nogroup)
        self.assertEqual(self.client.get('/api/students/').json()['results'], [])
        self.assertEqual(self.client.get(self.detail(self.child_a)).status_code, 404)

    def test_parent_cannot_mutate_or_predict(self):
        self.client.force_login(self.parent_a)
        self.assertEqual(self.client.delete(self.detail(self.child_a)).status_code, 403)
        self.assertEqual(self.client.get(self.detail(self.child_a) + 'predict/').status_code, 403)
        self.assertEqual(self.client.get(self.detail(self.child_a) + 'features/').status_code, 403)

    def test_teacher_sees_no_students_and_cannot_delete(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get('/api/students/').json()['results'], [])
        self.assertEqual(self.client.get(self.detail(self.child_a)).status_code, 404)
        self.assertEqual(self.client.delete(self.detail(self.child_a)).status_code, 403)

    def test_teacher_cannot_predict_or_read_features_for_an_unrelated_student(self):
        with mock.patch('students.views.requests.post') as post:
            self.client.force_login(self.teacher)
            for suffix in ('predict/', 'features/'):
                self.assertEqual(self.client.get(self.detail(self.child_b) + suffix).status_code, 403, suffix)
        post.assert_not_called()  # the AI service is never contacted on a teacher's behalf

    def test_unmapped_staff_roles_see_nothing(self):
        # Mentor / Counselor / Manager are not recognised roles: they get no access at all.
        for group in ('Mentor', 'Counselor', 'Manager'):
            user = make_user(f'{group.lower()}_a', group)
            self.assertEqual(roles_for(user), set(), group)
            self.client.force_login(user)
            self.assertEqual(self.client.get('/api/students/').json()['results'], [], group)
            self.assertEqual(self.client.get(self.detail(self.child_a)).status_code, 404, group)
            self.assertEqual(self.client.delete(self.detail(self.child_a)).status_code, 403, group)

    def test_service_token_is_not_accepted_as_a_user_token(self):
        # Cross-token (FastAPI service token presented to Django): different key and token type.
        import time, secrets, jwt
        now = int(time.time())
        svc = jwt.encode({'iss': 'school-django', 'aud': 'school-fastapi', 'sub': str(self.admin.pk),
                          'roles': ['Admin'], 'iat': now, 'exp': now + 60},
                         secrets.token_urlsafe(48), algorithm='HS256')
        resp = self.client.get('/api/students/', HTTP_AUTHORIZATION=f'Bearer {svc}')
        self.assertEqual(resp.status_code, 401)

    def test_admin_can_manage(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.detail(self.child_b)).status_code, 200)
