"""Phase 1 tests: boot sanity, migrations, API authentication and object-level authorization.

All data is synthetic. Run with:  python manage.py test students dashboard
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from schools.models import School, SchoolClass, SchoolMembership

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


def make_student(national_id, parent=None, first='Student', school=None):
    return Student.objects.create(
        first_name=first, last_name=national_id, national_id=national_id,
        grade=8, phone_number='0', parent_user=parent, school=school or School.objects.order_by('pk').first(),
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
        self.assertEqual(roles_for(make_user('root', is_superuser=True)), set())   # Slice 0: platform account

    def test_visible_students_deny_by_default(self):
        self.assertEqual(list(visible_students(self.parent_a)), [self.child_a])
        self.assertEqual(visible_students(make_user('nogroup')).count(), 0)
        # Teacher student access is disabled until a verified assignment model exists (S-04).
        self.assertEqual(visible_students(make_user('t', TEACHER)).count(), 0)
        self.assertEqual(visible_students(make_user('a', ADMIN)).count(), 0)   # S3: a SchoolAdmin needs a membership
        member = make_user('member', ADMIN)
        SchoolMembership.objects.create(user=member, school=School.objects.order_by('pk').first())
        self.assertEqual(visible_students(member).count(), 2)


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
                          'roles': [ADMIN], 'iat': now, 'exp': now + 60},
                         secrets.token_urlsafe(48), algorithm='HS256')
        resp = self.client.get('/api/students/', HTTP_AUTHORIZATION=f'Bearer {svc}')
        self.assertEqual(resp.status_code, 401)

    def test_admin_can_manage(self):
        SchoolMembership.objects.create(user=self.admin, school=self.child_b.school)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.detail(self.child_b)).status_code, 200)

    def test_admin_without_membership_gets_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.detail(self.child_b)).status_code, 404)


class StudentClassLinkTests(TestCase):
    """C2 (proposal 0002): school_class is the source of truth; school and class_name are derived.

    REQ: P2-REQ-18 (mirror, no auto-create), P2-REQ-05 (school key).
    """

    def setUp(self):
        self.school = School.objects.create(name='School A', code='school-a')
        self.other_school = School.objects.create(name='School B', code='school-b')
        self.klass = SchoolClass.objects.create(school=self.school, title='10-A', academic_year='1404')
        self.klass2 = SchoolClass.objects.create(school=self.school, title='10-B', academic_year='1404')
        self.foreign = SchoolClass.objects.create(school=self.other_school, title='X-1')
        self.student = make_student('0000000101', school=self.school)

    def test_unlinked_student_keeps_legacy_free_text(self):
        self.student.class_name = 'legacy text'
        self.student.save()
        self.student.refresh_from_db()
        self.assertEqual((self.student.class_name, self.student.school_id, self.student.school_class_id),
                         ('legacy text', self.school.pk, None))

    def test_linking_derives_school_and_mirrors_title(self):
        self.student.school_class = self.klass
        self.student.save()
        self.student.refresh_from_db()
        self.assertEqual(self.student.school_id, self.school.pk)
        self.assertEqual(self.student.class_name, '10-A')

    def test_class_name_text_is_overwritten_when_class_is_set(self):
        self.student.class_name = 'typed by hand'
        self.student.school_class = self.klass
        self.student.save()
        self.student.refresh_from_db()
        self.assertEqual(self.student.class_name, '10-A')

    def test_school_cannot_disagree_with_the_class(self):
        from django.core.exceptions import ValidationError
        self.student.school = self.other_school
        self.student.school_class = self.klass
        with self.assertRaises(ValidationError):
            self.student.save()
        self.student.refresh_from_db()
        self.assertEqual(self.student.school_id, self.school.pk)

    def test_changing_class_inside_the_school_updates_both_derived_fields(self):
        self.student.school_class = self.klass
        self.student.save()
        self.student.school_class = self.klass2
        self.student.save()
        self.student.refresh_from_db()
        self.assertEqual((self.student.school_id, self.student.class_name), (self.school.pk, '10-B'))

    def test_an_existing_student_cannot_move_to_a_class_of_another_school(self):
        from django.core.exceptions import ValidationError
        self.student.school_class = self.klass
        self.student.save()
        self.student.school_class = self.foreign
        with self.assertRaises(ValidationError) as ctx:
            self.student.save()
        self.assertNotIn(self.other_school.name, str(ctx.exception))
        self.student.refresh_from_db()
        self.assertEqual((self.student.school_id, self.student.school_class_id), (self.school.pk, self.klass.pk))

    def test_clearing_class_keeps_school_and_last_mirror(self):
        self.student.school_class = self.klass
        self.student.save()
        self.student.school_class = None
        self.student.save()
        self.student.refresh_from_db()
        self.assertEqual((self.student.school_class_id, self.student.school_id, self.student.class_name),
                         (None, self.school.pk, '10-A'))

    def test_update_fields_with_school_class_persists_derived_fields(self):
        self.student.school_class = self.klass
        self.student.save(update_fields=['school_class'])
        self.student.refresh_from_db()
        self.assertEqual((self.student.school_id, self.student.class_name), (self.school.pk, '10-A'))

    def test_update_fields_without_school_class_leaves_class_data_alone(self):
        self.student.school_class = self.klass
        self.student.save()
        Student.objects.filter(pk=self.student.pk).update(class_name='drifted')
        self.student.refresh_from_db()
        self.student.grade = 9
        self.student.save(update_fields=['grade'])
        self.student.refresh_from_db()
        self.assertEqual(self.student.class_name, 'drifted')  # only the requested column was written

    def test_check_constraint_rejects_class_without_school(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.bulk_create([Student(
                first_name='B', last_name='Bulk', national_id='0000000102', grade=8, phone_number='0',
                school_class=self.klass)])  # bulk_create bypasses save(): the database must refuse it

    def test_class_and_school_with_students_cannot_be_deleted(self):
        self.student.school_class = self.klass
        self.student.save()
        with self.assertRaises(ProtectedError):
            self.klass.delete()
        with self.assertRaises(ProtectedError):
            self.school.delete()


class StudentApiClassTests(TestCase):
    """REQ: P2-REQ-18. API: class membership is set through school_class only."""

    FIELDS = {'id', 'first_name', 'last_name', 'national_id', 'grade', 'phone_number', 'class_name',
              'father_job', 'mother_job', 'parent_user', 'school', 'school_class', 'created_at', 'updated_at'}

    def setUp(self):
        self.admin = make_user('admin_a', ADMIN)
        self.parent = make_user('parent_a', PARENT)
        self.school = School.objects.create(name='School A', code='school-a')
        SchoolMembership.objects.create(user=self.admin, school=self.school)  # S2b: writes need a school
        self.klass = SchoolClass.objects.create(school=self.school, title='10-A')
        self.closed = SchoolClass.objects.create(school=self.school, title='9-Z', is_active=False)
        self.student = make_student('0000000201', self.parent, school=self.school)

    def url(self):
        return f'/api/students/{self.student.pk}/'

    def patch(self, payload):
        return self.client.patch(self.url(), payload, content_type='application/json')

    def test_admin_sets_class_and_school_is_derived(self):
        self.client.force_login(self.admin)
        resp = self.patch({'school_class': self.klass.pk})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual((resp.json()['school'], resp.json()['class_name']), (self.school.pk, '10-A'))

    def test_class_name_and_school_are_read_only(self):
        self.client.force_login(self.admin)
        other = School.objects.create(name='School B', code='school-b')
        resp = self.patch({'class_name': 'hand typed', 'school': other.pk})
        self.assertEqual(resp.status_code, 200)
        self.student.refresh_from_db()
        # the client's ``school`` is ignored; the student keeps its school
        self.assertEqual((self.student.class_name, self.student.school_id), ('', self.school.pk))

    def test_inactive_or_unknown_class_is_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.patch({'school_class': self.closed.pk}).status_code, 400)
        self.assertEqual(self.patch({'school_class': 999999}).status_code, 400)

    def test_admin_can_clear_class(self):
        self.client.force_login(self.admin)
        self.patch({'school_class': self.klass.pk})
        self.assertEqual(self.patch({'school_class': None}).status_code, 200)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.school_class_id)

    def test_create_through_api_can_link_class(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/api/students/', {
            'first_name': 'N', 'last_name': 'New', 'national_id': '0000000202', 'grade': 10,
            'phone_number': '0', 'school_class': self.klass.pk}, content_type='application/json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Student.objects.get(national_id='0000000202').school_class_id, self.klass.pk)

    def test_field_set_is_explicit_and_unchanged_plus_new_links(self):
        self.client.force_login(self.admin)
        self.assertEqual(set(self.client.get(self.url()).json()), self.FIELDS)
        self.client.force_login(self.parent)
        self.assertEqual(set(self.client.get(self.url()).json()), self.FIELDS)

    def test_parent_cannot_change_class(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.patch({'school_class': self.klass.pk}).status_code, 403)
