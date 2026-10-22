"""An inactive account holds no role and sees nothing (owner decision 2026-10-23, closing the inactive-Parent finding of the
S3 gate review). Negative tests per role (Parent, Grade Lead, Subject Teacher, SchoolAdmin, superuser) for the access layer,
the API and the dashboard. The per-request user object is the unit of trust (H4): the stale-object tests hand the views
an inactive user object directly, as a regression in the authentication layer would; the end-to-end tests go through the
real authentication, which already refuses inactive accounts."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, RequestFactory, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, TeacherAssignment
from students import access, access_legacy
from students.enrollment_sync import ensure_current_enrollment
from students.models import Attendance, Grade, Student
from students.views import StudentViewSet

User = get_user_model()
ROLES = ('Parent', 'GradeLead', 'Teacher', 'SchoolAdmin', 'superuser')


def make_user(username, role, active):
    user = User.objects.create_user(username=username, is_superuser=(role == 'superuser'), is_active=active)
    user.set_unusable_password()
    user.save()
    if role != 'superuser':
        user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class InactiveAccountTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='A', code='a')
        AcademicYear.objects.create(school=self.school, code='1404-1405', start_date=date(2025, 9, 23),
                                    end_date=date(2026, 6, 21), is_current=True)
        self.klass = SchoolClass.objects.create(school=self.school, title='7-A', academic_year='1404-1405', grade=7)
        self.student = Student.objects.create(first_name='S', last_name='One', national_id='9400000001', grade=7,
                                              phone_number='1', school=self.school, school_class=self.klass)
        ensure_current_enrollment(self.student, source='manual')
        Grade.objects.create(student=self.student, subject='math', exam_type='quiz', score=10, date='2026-01-01')
        Attendance.objects.create(student=self.student, date='2026-01-02', status='present')

    def grant(self, user, role):
        """Give ``user`` a real grant of ``role`` over the student (so an ACTIVE twin would see it)."""
        if role == 'Parent':   # one child per account, so the active twin keeps its own
            Student.objects.create(first_name='C', last_name=user.username, national_id=f'95{user.pk:08d}', grade=7,
                                   phone_number='1', school=self.school, parent_user=user)
        elif role == 'GradeLead':
            GradeLeadAssignment.objects.create(user=user, school=self.school, grade=7, academic_year='1404-1405')
        elif role == 'Teacher':
            TeacherAssignment.objects.create(teacher=user, school_class=self.klass, subject='math')
        elif role == 'SchoolAdmin':
            SchoolMembership.objects.create(user=user, school=self.school)

    def pair(self, role):
        """(active, inactive) accounts with the same role and grant; the active one must see the rows."""
        accounts = []
        for active in (True, False):
            user = make_user(f'{role}-{active}', role, active)
            self.grant(user, role)
            accounts.append(user)
        return accounts

    def test_an_inactive_account_holds_no_role_and_sees_no_row_whatever_its_role(self):
        for role in ROLES:
            with self.subTest(role=role):
                active, inactive = self.pair(role)
                self.assertTrue(access.roles_for(active), 'the active twin must hold the role (the test would be vacuous)')
                self.assertTrue(access.visible_students(active).exists())
                self.assertEqual(access.roles_for(inactive), set())
                self.assertFalse(access.has_any_role(inactive, 'Parent', 'GradeLead', 'Teacher', 'SchoolAdmin'))
                for fn in (access.visible_students, access.visible_grades, access.visible_attendances,
                           access_legacy.visible_students):
                    self.assertEqual(list(fn(inactive)), [], f'{fn.__module__}.{fn.__name__}')

    def test_the_parent_branch_itself_refuses_an_inactive_account(self):
        """Defence in depth: even handed the Parent role explicitly, the grant of an inactive account is empty."""
        active, inactive = self.pair('Parent')
        self.assertIsNotNone(access._full_tier_q(active, {'Parent'}))
        self.assertIsNone(access._full_tier_q(inactive, {'Parent'}))
        self.assertIsNone(access_legacy._full_tier_q(inactive, {'Parent'}) if hasattr(access_legacy, '_full_tier_q') else None)

    def test_the_service_token_of_an_inactive_account_carries_no_role(self):
        import jwt
        from django.test import override_settings

        from config.service_auth import AUDIENCE, ISSUER, service_headers
        secret = 'unit-test-service-secret-0123456789abcdef-xyz'
        user = make_user('inactive-parent', 'Parent', False)
        with override_settings(SERVICE_JWT_SECRET=secret):
            token = service_headers(user)['Authorization'].split()[1]
        claims = jwt.decode(token, secret, algorithms=['HS256'], audience=AUDIENCE, issuer=ISSUER)
        self.assertEqual(claims['roles'], [])

    def test_the_api_returns_nothing_to_a_stale_inactive_user_object(self):
        factory = APIRequestFactory()
        view = StudentViewSet.as_view({'get': 'list', })
        for role in ROLES:
            with self.subTest(role=role):
                active, inactive = self.pair(role)
                visible = access.visible_students(active).count()   # children of earlier subtests stay in the table
                self.assertGreater(visible, 0)
                for user, expected in ((active, visible), (inactive, 0)):
                    request = factory.get('/api/students/')
                    force_authenticate(request, user=user)
                    response = view(request)
                    self.assertEqual(response.status_code, 200)
                    rows = response.data['results'] if isinstance(response.data, dict) else response.data
                    self.assertEqual(len(rows), expected, (role, user.is_active))

    def test_the_dashboard_refuses_a_stale_inactive_user_object(self):
        """The role decorator (``has_any_role`` -> ``roles_for``) denies the list, dashboard and detail views (403)."""
        from django.core.exceptions import PermissionDenied

        from dashboard import views
        factory = RequestFactory()
        for role in ROLES:
            with self.subTest(role=role):
                active, inactive = self.pair(role)
                for call in (lambda r: views.student_list_view(r), lambda r: views.dashboard_view(r),
                             lambda r: views.student_detail_view(r, self.student.pk)):
                    request = factory.get('/students/')
                    request.user = inactive
                    with self.assertRaises(PermissionDenied):
                        call(request)

    def test_end_to_end_inactive_accounts_are_refused_by_the_real_authentication(self):
        for role in ROLES:
            with self.subTest(role=role):
                _active, inactive = self.pair(role)
                client = Client()
                client.force_login(inactive)   # ModelBackend.get_user refuses an inactive account: the session is anonymous
                self.assertEqual(client.get('/students/').status_code, 302)
                self.assertIn(client.get('/api/students/').status_code, (401, 403))
