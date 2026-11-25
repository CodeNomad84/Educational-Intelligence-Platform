"""Platform global-stats JSON endpoint: platform operators get 200 and aggregate counters only, everyone else gets 403.

Synthetic data only; no student data is ever read (the view counts users and schools, never rows of school data).
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from schools.models import School, SchoolModule
from students.access import PLATFORM_ADMIN

from .test_counselor import Base, make_user

User = get_user_model()
URL = '/api/platform/global-stats/'


class PlatformStatsBase(Base):
    def setUp(self):
        super().setUp()
        SchoolModule.objects.all().delete()
        self.root = make_user('root', is_staff=True, is_superuser=True)
        self.platform = make_user('platform', PLATFORM_ADMIN, is_staff=True)
        self.t = make_user('teach', 'Teacher', self.a)
        self.s7.student_user = make_user('stu', 'Student')
        self.s7.save(update_fields=['student_user'])

    def get(self, user):
        self.client.force_login(user)
        return self.client.get(URL)


class AccessTests(PlatformStatsBase):
    def test_allowed(self):
        for user in (self.root, self.platform):
            self.assertEqual(self.get(user).status_code, 200, user.username)

    def test_denied(self):
        no_staff = make_user('platform-nostaff', PLATFORM_ADMIN)   # group without is_staff: not an operator
        inactive = make_user('root2', is_staff=True, is_superuser=True)
        inactive.is_active = False
        inactive.save()
        for user in (self.admin, self.lead, self.counselor, self.t, self.parent, self.s7.student_user, no_staff):
            self.assertEqual(self.get(user).status_code, 403, user.username)
        self.client.force_login(inactive)
        self.assertIn(self.client.get(URL).status_code, (401, 403))   # an inactive account holds no session

    def test_anonymous(self):
        self.assertEqual(self.client.get(URL).status_code, 401)


class ContentTests(PlatformStatsBase):
    def test_counts_schools_and_roles_without_names(self):
        body = self.get(self.root).json()
        self.assertEqual(body['schools_total'], School.objects.count())   # Base schools + the migrations' default school
        self.assertIsInstance(body['users_total'], int)
        self.assertEqual(set(body.keys()),
                         {'generated_at', 'schools_total', 'users_total', 'users_by_role', 'modules'})

        by_role = {row['role']: row['count'] for row in body['users_by_role']}
        self.assertIn(PLATFORM_ADMIN, by_role)
        self.assertEqual(by_role.get('SchoolAdmin'), 2)           # self.admin + self.admin_b
        self.assertEqual(by_role.get('GradeLead'), 1)
        self.assertEqual(by_role.get('Counselor'), 2)             # self.counselor + self.counselor_b

        # Only module keys and labels; no school names, no personal names, no national ids.
        serialized = str(body)
        self.assertNotIn('Seven', serialized)
        self.assertNotIn('"name"', serialized)                     # no school name field anywhere
        for module in body['modules']:
            self.assertIn(module['key'], ('advisor_ai', 'tutor_ai', 'exams', 'mission'))
            self.assertEqual(module['active_schools'], 0)

    def test_active_modules_are_counted(self):
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='licensed',
                                    starts_on=date.today())
        body = self.get(self.platform).json()
        modules = {row['key']: row['active_schools'] for row in body['modules']}
        self.assertEqual(modules['exams'], 1)
        self.assertEqual(modules['advisor_ai'], 0)
