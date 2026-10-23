"""Phase 1 tests for the server-rendered dashboard (S-01) and Django->FastAPI service tokens.

All data is synthetic. Run with:  python manage.py test students dashboard
"""
import secrets
from unittest import mock

import jwt
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from config.service_auth import AUDIENCE, ISSUER, service_headers
from schools.models import School, SchoolClass, SchoolMembership
from students.access import ADMIN, PARENT, TEACHER
from students.models import Student
from students.tests import make_student, make_user


class DashboardAuthzTests(TestCase):
    def setUp(self):
        self.parent_a = make_user('parent_a', PARENT)
        self.parent_b = make_user('parent_b', PARENT)
        self.teacher = make_user('teacher_a', TEACHER)
        self.admin = make_user('admin_a', ADMIN)
        self.nogroup = make_user('nogroup')
        self.child_a = make_student('0000000001', self.parent_a, first='ChildA')
        self.child_b = make_student('0000000002', self.parent_b, first='ChildB')

    def url(self, name, *args):
        return reverse(f'dashboard:{name}', args=args)

    # -- unauthenticated --------------------------------------------------
    def test_anonymous_redirected_to_login_everywhere(self):
        for name, args in [('dashboard', ()), ('student_list', ()), ('student_detail', (self.child_a.pk,)),
                           ('chat', ()), ('library', ()), ('student_add', ()), ('upload_students', ())]:
            resp = self.client.get(self.url(name, *args))
            self.assertEqual(resp.status_code, 302, name)
            self.assertTrue(resp['Location'].startswith(reverse('dashboard:login')), name)

    def test_anonymous_cannot_mutate(self):
        for name in ('upload_document', 'delete_document'):
            resp = self.client.post(self.url(name), {'parent_id': 'x'})
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp['Location'].startswith(reverse('dashboard:login')))

    # -- parent: own child allowed, other child denied -------------------
    def test_parent_own_child_allowed(self):
        self.client.force_login(self.parent_a)
        self.assertEqual(self.client.get(self.url('student_detail', self.child_a.pk)).status_code, 200)

    def test_parent_other_child_denied(self):
        self.client.force_login(self.parent_a)
        self.assertEqual(self.client.get(self.url('student_detail', self.child_b.pk)).status_code, 404)

    def test_parent_list_shows_only_own_child(self):
        self.client.force_login(self.parent_a)
        resp = self.client.get(self.url('student_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context['students']), [self.child_a])

    def test_parent_search_cannot_reveal_other_children(self):
        self.client.force_login(self.parent_a)
        resp = self.client.get(self.url('student_list'), {'search': '0000000002'})
        self.assertEqual(list(resp.context['students']), [])

    def test_parent_dashboard_redirects_to_own_list(self):
        self.client.force_login(self.parent_a)
        resp = self.client.get(self.url('dashboard'))
        self.assertRedirects(resp, self.url('student_list'))

    def test_parent_denied_staff_and_admin_pages(self):
        self.client.force_login(self.parent_a)
        for name in ('chat', 'library', 'student_add', 'upload_students'):
            self.assertEqual(self.client.get(self.url(name)).status_code, 403, name)
        self.assertEqual(self.client.post(self.url('upload_document')).status_code, 403)
        self.assertEqual(self.client.post(self.url('delete_document'), {'parent_id': 'x'}).status_code, 403)

    # -- unauthorized role (no recognised group) --------------------------
    def test_user_without_role_denied(self):
        self.client.force_login(self.nogroup)
        for name, args in [('dashboard', ()), ('student_list', ()), ('student_detail', (self.child_a.pk,)),
                           ('chat', ()), ('library', ()), ('student_add', ())]:
            self.assertEqual(self.client.get(self.url(name, *args)).status_code, 403, name)

    def test_teacher_predict_flag_on_unrelated_student_is_denied(self):
        self.client.force_login(self.teacher)
        with mock.patch('dashboard.views.requests.post') as post:
            resp = self.client.get(self.url('student_detail', self.child_b.pk), {'predict': 'true'})
        self.assertEqual(resp.status_code, 404)  # the student is not visible to a teacher
        post.assert_not_called()

    def test_unmapped_staff_roles_denied_everywhere(self):
        for group in ('Mentor', 'Manager'):   # Counselor is a recognised role since Slice 4a (dashboard/test_counselor.py)
            self.client.force_login(make_user(f'{group.lower()}_a', group))
            for name, args in [('dashboard', ()), ('chat', ()), ('library', ()), ('student_add', ())]:
                self.assertEqual(self.client.get(self.url(name, *args)).status_code, 403, f'{group} {name}')
            self.assertEqual(self.client.get(self.url('student_detail', self.child_a.pk)).status_code, 403, group)
            self.assertEqual(self.client.post(self.url('upload_document')).status_code, 403, group)

    def test_chat_disabled_for_every_role_and_never_calls_ai(self):
        root = make_user('root', is_superuser=True)
        for user in (self.admin, root, self.teacher, self.parent_a, self.nogroup):
            self.client.force_login(user)
            with mock.patch('dashboard.views.requests.post') as post:
                self.assertEqual(self.client.get(self.url('chat')).status_code, 403, user.username)
                self.assertEqual(self.client.post(self.url('chat'), {'query': 'q'}).status_code, 403, user.username)
            post.assert_not_called()

    # -- staff ------------------------------------------------------------
    def test_teacher_denied_student_data_and_documents(self):
        # A Teacher WITHOUT an assignment sees no student data; documents and writes stay denied.
        # (C5a: aggregates stay SchoolAdmin only, so the landing is a redirect to the teacher's own home, /teacher/.)
        self.client.force_login(self.teacher)
        self.assertRedirects(self.client.get(self.url('dashboard')), self.url('teacher_home'))
        self.assertEqual(self.client.get(self.url('student_detail', self.child_b.pk)).status_code, 404)
        self.assertEqual(list(self.client.get(self.url('student_list')).context['students']), [])
        self.assertEqual(self.client.get(self.url('library')).status_code, 403)
        self.assertEqual(self.client.get(self.url('chat')).status_code, 403)
        self.assertEqual(self.client.get(self.url('student_add')).status_code, 403)
        self.assertEqual(self.client.post(self.url('upload_document')).status_code, 403)
        self.assertEqual(self.client.post(self.url('delete_document'), {'parent_id': 'x'}).status_code, 403)

    def test_admin_can_create_student(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url('student_add')).status_code, 200)

    def test_superuser_is_the_platform_account_and_cannot_add_students(self):
        root = make_user('root', is_superuser=True)
        self.client.force_login(root)
        self.assertEqual(self.client.get(self.url('student_add')).status_code, 403)

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.parent_a)
        resp = self.client.get(self.url('logout'))
        self.assertRedirects(resp, reverse('dashboard:login'))

    # -- predict is staff-only and never called for parents ---------------
    def test_parent_predict_flag_does_not_call_ai_service(self):
        self.client.force_login(self.parent_a)
        with mock.patch('dashboard.views.requests.post') as post:
            resp = self.client.get(self.url('student_detail', self.child_a.pk), {'predict': 'true'})
        self.assertEqual(resp.status_code, 200)
        post.assert_not_called()


class ServiceTokenTests(TestCase):
    def setUp(self):
        self.secret = secrets.token_urlsafe(48)  # generated per run; never stored
        self.teacher = make_user('teacher_a', TEACHER)
        self.admin = make_user('admin_a', ADMIN)

    def decode(self, headers):
        token = headers['Authorization'].split(' ', 1)[1]
        return jwt.decode(token, self.secret, algorithms=['HS256'], audience=AUDIENCE, issuer=ISSUER)

    def test_token_carries_user_roles_and_expiry(self):
        with override_settings(SERVICE_JWT_SECRET=self.secret):
            claims = self.decode(service_headers(self.teacher))
        self.assertEqual(claims['sub'], str(self.teacher.pk))
        self.assertEqual(claims['roles'], [TEACHER])
        self.assertLessEqual(claims['exp'] - claims['iat'], 60)

    def test_token_carries_the_school_ids_of_a_school_admin_only(self):
        from schools.models import School, SchoolMembership
        school = School.objects.create(name='S', code='s-claim')
        SchoolMembership.objects.create(user=self.admin, school=school)
        with override_settings(SERVICE_JWT_SECRET=self.secret):
            self.assertEqual(self.decode(service_headers(self.admin))['schools'], [school.pk])
            self.assertEqual(self.decode(service_headers(self.teacher))['schools'], [])
            self.assertEqual(self.decode(service_headers(make_user('root-claim', is_superuser=True)))['schools'], [])
            type(self.admin).objects.filter(pk=self.admin.pk).update(is_active=False)
            self.assertEqual(self.decode(service_headers(type(self.admin).objects.get(pk=self.admin.pk)))['schools'], [])

    def test_missing_or_short_secret_fails_closed(self):
        for value in ('', 'short'):
            with override_settings(SERVICE_JWT_SECRET=value):
                with self.assertRaises(ImproperlyConfigured):
                    service_headers(self.teacher)

    def test_weak_or_placeholder_secrets_fail_closed(self):
        from django.conf import settings
        weak = ['django-insecure-' + 'x' * 40, 'changeme' * 6, 'a' * 64, 'your-secret-key-' + 'Qz9' * 10,
                settings.SECRET_KEY]
        for value in weak:
            with override_settings(SERVICE_JWT_SECRET=value):
                with self.assertRaises(ImproperlyConfigured, msg=value[:8]):
                    service_headers(self.teacher)

    def test_library_admin_sends_token_and_survives_missing_secret(self):
        self.client.force_login(self.admin)
        fake = mock.Mock(status_code=200)
        fake.json.return_value = {'documents': []}
        with override_settings(SERVICE_JWT_SECRET=self.secret):
            with mock.patch('dashboard.views.requests.get', return_value=fake) as get:
                resp = self.client.get(reverse('dashboard:library'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Authorization', get.call_args.kwargs['headers'])
        with override_settings(SERVICE_JWT_SECRET=''):
            with mock.patch('dashboard.views.requests.get') as get:
                resp = self.client.get(reverse('dashboard:library'))
        self.assertEqual(resp.status_code, 200)
        get.assert_not_called()


class StudentFormClassSelectorTests(TestCase):
    """C2: the add-student form selects an existing ACTIVE class; it never creates one.

    REQ: P2-REQ-18.
    """

    def setUp(self):
        self.admin = make_user('admin_a', ADMIN)
        self.school = School.objects.create(name='School A', code='school-a')
        SchoolMembership.objects.create(user=self.admin, school=self.school)  # S2b: writes need a school
        self.klass = SchoolClass.objects.create(school=self.school, title='10-A')
        self.closed = SchoolClass.objects.create(school=self.school, title='9-Z', is_active=False)
        self.url = reverse('dashboard:student_add')
        self.base = {'first_name': 'N', 'last_name': 'New', 'national_id': '0000000301', 'grade': 10,
                     'phone_number': '0', 'father_job': '', 'mother_job': ''}

    def test_form_offers_active_classes_only_and_no_free_text(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        form = resp.context['form']
        self.assertNotIn('class_name', form.fields)
        self.assertEqual(list(form.fields['school_class'].queryset), [self.klass])
        self.assertFalse(form.fields['school_class'].required)

    def test_create_with_class_derives_school_and_mirror(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url, {**self.base, 'school_class': self.klass.pk})
        self.assertEqual(resp.status_code, 302)
        student = Student.objects.get(national_id='0000000301')
        self.assertEqual((student.school_class, student.school_id, student.class_name),
                         (self.klass, self.school.pk, '10-A'))

    def test_create_without_class_is_allowed_and_creates_no_class(self):
        self.client.force_login(self.admin)
        before = SchoolClass.objects.count()
        resp = self.client.post(self.url, {**self.base, 'class_name': 'typed text'})
        self.assertEqual(resp.status_code, 302)
        student = Student.objects.get(national_id='0000000301')
        self.assertEqual((student.school_class_id, student.school_id, student.class_name),
                         (None, self.school.pk, ''))  # S2b: the admin's only school is implied
        self.assertEqual(SchoolClass.objects.count(), before)

    def test_inactive_or_unknown_class_is_rejected(self):
        self.client.force_login(self.admin)
        for pk in (self.closed.pk, 999999):
            resp = self.client.post(self.url, {**self.base, 'school_class': pk})
            self.assertEqual(resp.status_code, 200, pk)  # form re-rendered with errors
        self.assertFalse(Student.objects.filter(national_id='0000000301').exists())

    def test_non_admin_cannot_create(self):
        for user in (make_user('t', TEACHER), make_user('p', PARENT)):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {**self.base, 'school_class': self.klass.pk}).status_code, 403)
        self.assertFalse(Student.objects.filter(national_id='0000000301').exists())


class RemovedDebugRouteTests(TestCase):
    """/test-fastapi/ was an unauthenticated debug route that echoed exception text; it must stay gone."""

    def test_test_fastapi_route_is_gone_for_everyone(self):
        self.assertEqual(self.client.get('/test-fastapi/').status_code, 404)
        self.client.force_login(make_user('admin_dbg', ADMIN))
        self.assertEqual(self.client.get('/test-fastapi/').status_code, 404)


class AdminRoleContextTests(TestCase):
    """The upload link in base.html is keyed on the ADMIN constant, not on a literal (rename prep)."""

    def render_base(self, group):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        user = get_user_model().objects.create_user(username=f"u_{group}", password="x")
        user.groups.add(Group.objects.get_or_create(name=group)[0])
        request = RequestFactory().get('/')
        request.user = user
        return render_to_string('dashboard/base.html', {'user': user}, request=request)

    def test_only_admin_group_sees_upload_link(self):
        upload = reverse('dashboard:upload_students')
        self.assertIn(upload, self.render_base(ADMIN))
        self.assertNotIn(upload, self.render_base(PARENT))
