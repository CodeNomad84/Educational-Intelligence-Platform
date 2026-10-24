"""Per-school module entitlement. Sellable keys: advisor_ai, tutor_ai, exams, mission. Student 360 and counseling are
base (always on). Simple negative tests per gated route: 403 when off, allowed when on, 403 once ends_on has passed or
before starts_on, and a school without the module is refused even if another school has it."""
from datetime import timedelta
from unittest import mock

import requests
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from schools import audit
from schools.entitlements import MODULES, enabled_modules_for_user, module_enabled
from schools.models import AuditEvent, SchoolMembership, SchoolModule
from schools.testing import grant

from .test_counselor import Base, make_user

TODAY = timezone.localdate


class ModuleBase(Base):
    def setUp(self):
        super().setUp()
        SchoolModule.objects.all().delete()     # start from "nothing granted"
        self.stu_user = make_user('stu', 'Student', self.a)
        self.s7.student_user = self.stu_user
        self.s7.save(update_fields=['student_user'])

    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)


class SellableKeyTests(ModuleBase):
    def test_exactly_four_sellable_keys_and_student360_is_gone(self):
        self.assertEqual(set(MODULES), {'advisor_ai', 'tutor_ai', 'exams', 'mission'})
        grant(self.a, 'tutor_ai')
        self.assertFalse(module_enabled(self.a, 'student360'))

    def test_counseling_and_student_360_are_base_and_work_without_any_row(self):
        ref = self.refer(self.s7, self.counselor)
        self.assertEqual(self.get(self.counselor, reverse('dashboard:counselor_home')).status_code, 200)
        self.assertEqual(self.get(self.counselor, reverse('dashboard:counselor_case', args=[ref.pk])).status_code, 200)
        page = self.get(self.admin, reverse('dashboard:student_360', args=[self.s7.pk]))
        self.assertContains(page, 'ارجاع به مشاور')
        self.assertContains(page, 'Frequent absences')
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('dashboard:student_refer', args=[self.s8.pk]),
                                {'counselor': self.counselor.pk, 'reason': 'x'})
        self.assertEqual(resp.status_code, 302)


class TutorRouteTests(ModuleBase):
    def url(self):
        return reverse('dashboard:me_assistant')

    def test_off_on_ended_not_yet_started_and_other_school(self):
        self.assertEqual(self.get(self.stu_user, self.url()).status_code, 403)                  # no row
        grant(self.a, 'tutor_ai')
        self.assertEqual(self.get(self.stu_user, self.url()).status_code, 200)                  # on
        SchoolModule.objects.all().update(ends_on=TODAY() - timedelta(days=1))
        self.assertEqual(self.get(self.stu_user, self.url()).status_code, 403)                  # ended
        SchoolModule.objects.all().update(starts_on=TODAY() + timedelta(days=2), ends_on=None)
        self.assertEqual(self.get(self.stu_user, self.url()).status_code, 403)                  # not started
        SchoolModule.objects.all().delete()
        grant(self.b, 'tutor_ai')
        self.assertEqual(self.get(self.stu_user, self.url()).status_code, 403)                  # other school only

    def test_menu_follows_the_module(self):
        grant(self.a, 'tutor_ai')
        self.assertEqual(enabled_modules_for_user(self.stu_user), {'tutor_ai'})
        SchoolModule.objects.all().delete()
        self.assertEqual(enabled_modules_for_user(self.stu_user), set())


class PredictGateTests(ModuleBase):
    """ML risk prediction through FastAPI is an AI call: advisor_ai is checked before the request is made."""

    def url(self):
        return f'/api/students/{self.s7.pk}/predict/'

    def test_off_ended_not_started_and_other_school_never_reach_fastapi(self):
        self.client.force_login(self.admin)
        with mock.patch('requests.post', side_effect=AssertionError('FastAPI called')) as post:
            self.assertEqual(self.client.get(self.url()).status_code, 403)                      # no row
            grant(self.a, 'advisor_ai')
            SchoolModule.objects.all().update(ends_on=TODAY() - timedelta(days=1))
            self.assertEqual(self.client.get(self.url()).status_code, 403)                      # ended
            SchoolModule.objects.all().update(starts_on=TODAY() + timedelta(days=2), ends_on=None)
            self.assertEqual(self.client.get(self.url()).status_code, 403)                      # not started
            SchoolModule.objects.all().delete()
            grant(self.b, 'advisor_ai')
            self.assertEqual(self.client.get(self.url()).status_code, 403)                      # other school only
            self.assertEqual(post.call_count, 0)
        SchoolModule.objects.all().delete()
        grant(self.a, 'advisor_ai')
        with mock.patch('requests.post', side_effect=requests.exceptions.ConnectionError):
            self.assertEqual(self.client.get(self.url()).status_code, 503)                      # allowed; service unreachable

    def test_admin_of_two_schools_is_blocked_per_object(self):
        SchoolMembership.objects.create(user=self.admin, school=self.b)
        grant(self.a, 'advisor_ai')                                                             # school B has no module
        self.client.force_login(self.admin)
        with mock.patch('requests.post', side_effect=requests.exceptions.ConnectionError):
            self.assertEqual(self.client.get(self.url()).status_code, 503)
            self.assertEqual(self.client.get(f'/api/students/{self.sb.pk}/predict/').status_code, 403)


class EntitlementHelperTests(ModuleBase):
    def test_unknown_keys_and_dates(self):
        self.assertFalse(module_enabled(self.a, 'exams'))
        grant(self.a, 'exams')
        self.assertTrue(module_enabled(self.a, 'exams'))
        self.assertFalse(module_enabled(self.a, 'not_a_module'))
        self.assertFalse(module_enabled(None, 'exams'))
        self.assertFalse(module_enabled(self.a, 'exams', on=TODAY().replace(year=2019)))        # before it started
        SchoolModule.objects.filter(module_key='exams').update(ends_on=TODAY())
        self.assertTrue(module_enabled(self.a, 'exams'))                                        # ends_on is inclusive
        self.assertFalse(module_enabled(self.a, 'exams', on=TODAY() + timedelta(days=1)))

    def test_constraints(self):
        grant(self.a, 'exams')
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolModule.objects.create(school=self.a, module_key='exams', starts_on=TODAY().replace(year=2020, month=1, day=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolModule.objects.create(school=self.a, module_key='mission', starts_on=TODAY(), ends_on=TODAY() - timedelta(days=1))

    def test_command_writes_a_row_and_an_audit_event_without_content(self):
        call_command('set_school_module', 'a', 'tutor_ai', '--ends', (TODAY() + timedelta(days=30)).isoformat())
        row = SchoolModule.objects.get(school=self.a, module_key='tutor_ai')
        event = AuditEvent.objects.get(action=audit.MODULE_CHANGE)
        self.assertEqual((event.school_id, event.object_id, event.username), (self.a.pk, str(row.pk), ''))
        self.assertTrue(event.detail.startswith('tutor_ai:'))
        with self.assertRaises(Exception):
            call_command('set_school_module', 'nope', 'tutor_ai')
        with self.assertRaises(Exception):
            call_command('set_school_module', 'a', 'student360')
