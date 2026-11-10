"""T6 pilot-config: with the pilot switches OFF, the Counselor/referral/assistant routes return 403 and
the feedback footer link is driven by FEEDBACK_URL. Synthetic data only. The switches are flipped with
``override_settings`` so this module runs under the normal (flags-on) test settings."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from schools.models import AcademicYear, School, SchoolClass, SchoolMembership, SchoolStaff
from schools.module_grants import grant
from students.enrollment_sync import ensure_current_enrollment
from students.models import Student

User = get_user_model()
PASSWORD = 'x'


def make_user(name, group=None, school=None, **extra):
    user = User.objects.create_user(name, password=PASSWORD, **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    if school is not None and group != 'SchoolAdmin':
        SchoolStaff.objects.create(user=user, school=school)
    return user


class PilotConfigBase(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        AcademicYear.objects.create(school=self.a, code='1404-1405', start_date=date(2025, 9, 23),
                                    end_date=date(2026, 6, 21), is_current=True)
        self.c7 = SchoolClass.objects.create(school=self.a, title='7-A', academic_year='1404-1405', grade=7)
        self.student = Student.objects.create(first_name='S', last_name='X', national_id='9900000001',
                                              grade=7, phone_number='1', school=self.a, school_class=self.c7)
        ensure_current_enrollment(self.student, source='manual')
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.counselor = make_user('counselor', 'Counselor', self.a)
        self.stu_user = make_user('stu', 'Student')
        Student.objects.filter(pk=self.student.pk).update(student_user=self.stu_user)
        # AI modules on, so the flag is the ONLY blocker under the switch-off tests.
        grant(self.a, 'tutor_ai', 'advisor_ai')


class CounselorGateTests(PilotConfigBase):
    @override_settings(ENABLE_COUNSELOR_ROLE=False)
    def test_counselor_routes_blocked_when_role_off(self):
        self.client.force_login(self.counselor)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_home')).status_code, 403)
        # the flag gate fires before the object lookup, so an arbitrary pk is 403 (not 404)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_case', args=[999])).status_code, 403)

    @override_settings(ENABLE_COUNSELOR_ROLE=False)
    def test_referral_post_blocked_when_role_off(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('dashboard:student_refer', args=[self.student.pk]),
                                {'counselor': self.counselor.pk, 'reason': 'r'})
        self.assertEqual(resp.status_code, 403)

    @override_settings(ENABLE_COUNSELOR_ROLE=True)
    def test_counselor_home_reachable_when_role_on(self):
        self.client.force_login(self.counselor)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_home')).status_code, 200)


class AssistantGateTests(PilotConfigBase):
    @override_settings(ENABLE_AI_FEATURES=False)
    def test_school_assistant_blocked_when_ai_off(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('docqa:home')).status_code, 403)

    @override_settings(ENABLE_AI_FEATURES=False)
    def test_study_assistant_blocked_when_ai_off(self):
        self.client.force_login(self.stu_user)
        self.assertEqual(self.client.get(reverse('dashboard:me_assistant')).status_code, 403)

    @override_settings(ENABLE_AI_FEATURES=True)
    def test_school_assistant_reachable_when_ai_on(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('docqa:home')).status_code, 200)


class FeedbackFooterTests(PilotConfigBase):
    @override_settings(FEEDBACK_URL='https://example.test/feedback')
    def test_footer_link_rendered_verbatim_from_setting(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard:profile'))
        self.assertContains(resp, 'href="https://example.test/feedback"')
        # the setting is rendered verbatim: no student id is interpolated into the URL
        self.assertNotContains(resp, f'href="https://example.test/feedback?student={self.student.pk}"')

    @override_settings(FEEDBACK_URL='')
    def test_footer_link_hidden_when_unset(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard:profile'))
        self.assertNotContains(resp, 'بازخورد و پیشنهاد')
