"""Slice A.2: trial vs licensed rows, locked-but-visible modules, SchoolAdmin banner, platform-admin-only rows, AI call cap."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from schools import ai_guard, audit
from schools.entitlements import (
    ACTIVE_LICENSED, ACTIVE_TRIAL, LOCKED, module_enabled, module_state, trial_days_left, trial_notices)
from schools.models import AICallUsage, AuditEvent, SchoolModule
from schools.module_grants import grant

from .test_modules import ModuleBase

TODAY = timezone.localdate
User = get_user_model()


def trial(school, key, days_from_today_end, started_days_ago=10):
    return SchoolModule.objects.create(school=school, module_key=key, kind='trial',
                                       starts_on=TODAY() - timedelta(days=started_days_ago),
                                       ends_on=TODAY() + timedelta(days=days_from_today_end))


class StateTests(ModuleBase):
    def test_states_and_days_left(self):
        self.assertEqual(module_state(self.a, 'tutor_ai'), LOCKED)
        self.assertIsNone(trial_days_left(self.a, 'tutor_ai'))
        trial(self.a, 'tutor_ai', 5)
        self.assertEqual(module_state(self.a, 'tutor_ai'), ACTIVE_TRIAL)
        self.assertEqual(trial_days_left(self.a, 'tutor_ai'), 5)
        grant(self.a, 'tutor_ai')                                           # a licensed row wins over the trial
        self.assertEqual(module_state(self.a, 'tutor_ai'), ACTIVE_LICENSED)
        self.assertIsNone(trial_days_left(self.a, 'tutor_ai'))
        self.assertEqual(module_state(self.b, 'tutor_ai'), LOCKED)          # cross-school

    def test_expired_and_not_started_are_locked(self):
        trial(self.a, 'exams', -1, started_days_ago=20)
        self.assertEqual(module_state(self.a, 'exams'), LOCKED)
        self.assertFalse(module_enabled(self.a, 'exams'))
        SchoolModule.objects.create(school=self.a, module_key='mission', kind='trial',
                                    starts_on=TODAY() + timedelta(days=2), ends_on=TODAY() + timedelta(days=9))
        self.assertEqual(module_state(self.a, 'mission'), LOCKED)

    def test_one_trial_per_school_module_and_a_trial_needs_an_end(self):
        trial(self.a, 'exams', 5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() + timedelta(days=30),
                                        ends_on=TODAY() + timedelta(days=40))
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolModule.objects.create(school=self.b, module_key='exams', kind='trial', starts_on=TODAY())
        self.assertEqual(SchoolModule.objects.filter(school=self.a, module_key='exams', kind='licensed').count(), 0)

    def test_command_extends_the_single_trial_and_audits_it(self):
        end = TODAY() + timedelta(days=7)
        call_command('set_school_module', 'a', 'exams', '--kind', 'trial', '--ends', end.isoformat())
        call_command('set_school_module', 'a', 'exams', '--kind', 'trial', '--ends', (end + timedelta(days=7)).isoformat())
        self.assertEqual(SchoolModule.objects.filter(school=self.a, module_key='exams', kind='trial').count(), 1)
        self.assertEqual(SchoolModule.objects.get(school=self.a).ends_on, end + timedelta(days=7))
        self.assertEqual(AuditEvent.objects.filter(action=audit.MODULE_CHANGE).count(), 2)
        with self.assertRaises(Exception):
            call_command('set_school_module', 'a', 'mission', '--kind', 'trial')       # no end date


class LockedVisibleTests(ModuleBase):
    def test_locked_modules_stay_in_the_menu_and_the_info_page_is_static(self):
        page = self.get(self.admin, reverse('dashboard:school_home'))
        for key in ('advisor_ai', 'tutor_ai', 'exams', 'mission'):
            self.assertContains(page, reverse('dashboard:module_info', args=[key]))
        info = self.get(self.admin, reverse('dashboard:module_info', args=['tutor_ai']))
        self.assertEqual(info.status_code, 200)
        self.assertContains(info, 'تماس بگیرید')
        self.assertNotContains(info, 'Seven')                  # no school data
        built = self.get(self.admin, reverse('dashboard:module_info', args=['exams']))       # exams is built since Slice 1
        self.assertContains(built, 'تماس بگیرید')
        self.assertEqual(built.content.decode().count('به‌زودی'), 0)   # no sidebar stub is left (F12 removed the chat/library «به‌زودی» items); the page below still says it for a module that is not built
        with mock.patch('dashboard.module_info.BUILT', ('advisor_ai', 'tutor_ai', 'mission')):   # a module not built yet
            soon = self.get(self.admin, reverse('dashboard:module_info', args=['exams']))
        self.assertContains(soon, 'به‌زودی')
        self.assertNotContains(soon, 'تماس بگیرید')
        self.assertEqual(self.get(self.admin, reverse('dashboard:module_info', args=['nope'])).status_code, 404)

    def test_student_sees_a_locked_link_that_leads_to_the_info_page(self):
        page = self.get(self.stu_user, reverse('dashboard:me_home'))
        self.assertContains(page, reverse('dashboard:module_info', args=['tutor_ai']))
        self.assertNotContains(page, reverse('dashboard:me_assistant'))
        grant(self.a, 'tutor_ai')
        self.assertContains(self.get(self.stu_user, reverse('dashboard:me_home')), reverse('dashboard:me_assistant'))

    def test_expired_trial_locks_the_route_and_a_licensed_row_restores_stored_data(self):
        row = trial(self.a, 'tutor_ai', 5)
        url = reverse('dashboard:me_assistant')
        self.client.force_login(self.stu_user)
        self.assertEqual(self.client.post(url, {'question': 'math'}).status_code, 200)
        self.assertEqual(AICallUsage.objects.get(school=self.a, module_key='tutor_ai').count, 1)   # stored during the trial
        SchoolModule.objects.filter(pk=row.pk).update(ends_on=TODAY() - timedelta(days=1))
        self.assertEqual(self.client.get(url).status_code, 403)                                    # locked: reads blocked
        self.assertEqual(self.client.post(url, {'question': 'math'}).status_code, 403)             # and writes
        self.assertEqual(self.client.get(reverse('dashboard:module_info', args=['tutor_ai'])).status_code, 200)
        self.assertEqual(AICallUsage.objects.get(school=self.a, module_key='tutor_ai').count, 1)   # retained
        grant(self.a, 'tutor_ai')
        self.assertEqual(self.client.get(url).status_code, 200)                                    # access is back
        self.assertEqual(AICallUsage.objects.get(school=self.a, module_key='tutor_ai').count, 1)


class BannerTests(ModuleBase):
    def test_admin_banner_for_expiring_and_just_ended_trials_only(self):
        url = reverse('dashboard:school_home')
        trial(self.a, 'exams', 30, started_days_ago=60)
        self.assertNotContains(self.get(self.admin, url), 'دورهٔ آزمایشی')
        SchoolModule.objects.filter(module_key='exams').update(ends_on=TODAY() + timedelta(days=10))
        self.assertContains(self.get(self.admin, url), '10 روز دیگر')
        SchoolModule.objects.filter(module_key='exams').update(ends_on=TODAY() - timedelta(days=3))
        self.assertContains(self.get(self.admin, url), 'پایان یافته')
        SchoolModule.objects.filter(module_key='exams').update(ends_on=TODAY() - timedelta(days=40))
        self.assertNotContains(self.get(self.admin, url), 'دورهٔ آزمایشی')
        self.assertEqual(trial_notices({self.b.pk}), [])                                      # other school: nothing

    def test_other_roles_and_other_schools_see_no_banner(self):
        trial(self.a, 'exams', 3)
        self.assertNotContains(self.get(self.stu_user, reverse('dashboard:me_home')), 'دورهٔ آزمایشی')
        self.assertNotContains(self.get(self.admin_b, reverse('dashboard:school_home')), 'دورهٔ آزمایشی')


class PlatformAdminOnlyTests(ModuleBase):
    def test_a_school_admin_cannot_see_create_or_extend_rows(self):
        self.admin.is_staff = True
        self.admin.save()
        row = trial(self.a, 'exams', 5)
        self.client.force_login(self.admin)
        # C-A: refused by the admin site itself (redirect to the admin login), before any model permission is asked
        self.assertEqual(self.client.get('/admin/schools/schoolmodule/').status_code, 302)
        self.assertEqual(self.client.get('/admin/schools/schoolmodule/add/').status_code, 302)
        self.assertEqual(self.client.post(f'/admin/schools/schoolmodule/{row.pk}/change/',
                                          {'ends_on': (TODAY() + timedelta(days=99)).isoformat()}).status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.ends_on, TODAY() + timedelta(days=5))

    def test_a_platform_admin_can_extend_and_it_is_audited(self):
        root = User.objects.create_superuser('root', password='x')
        row = trial(self.a, 'exams', 5)
        self.client.force_login(root)
        self.assertEqual(self.client.get('/admin/schools/schoolmodule/').status_code, 200)
        new_end = TODAY() + timedelta(days=20)
        resp = self.client.post(f'/admin/schools/schoolmodule/{row.pk}/change/', {'ends_on': new_end.isoformat()})
        self.assertEqual(resp.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.ends_on, new_end)
        event = AuditEvent.objects.get(action=audit.MODULE_CHANGE)
        self.assertEqual((event.school_id, event.object_id), (self.a.pk, str(row.pk)))
        self.assertTrue(event.detail.startswith('exams:trial:'))
        self.assertEqual(self.client.post(f'/admin/schools/schoolmodule/{row.pk}/delete/', {'post': 'yes'}).status_code, 403)

    def test_platform_admin_group_counts_and_only_it_sets_caps(self):
        pa = User.objects.create_user('pa', password='x', is_staff=True)
        pa.groups.add(Group.objects.get_or_create(name='PlatformAdmin')[0])
        self.client.force_login(pa)
        self.assertEqual(self.client.get('/admin/schools/schoolmodule/').status_code, 200)
        from schools.admin import SchoolAdmin
        from django.contrib import admin as dj_admin
        from django.test import RequestFactory
        req = RequestFactory().get('/')
        model_admin = SchoolAdmin(type(self.a), dj_admin.site)
        req.user = pa
        self.assertNotIn('ai_daily_cap', model_admin.get_readonly_fields(req, self.a))
        self.admin.is_staff = True
        req.user = self.admin
        self.assertIn('ai_daily_cap', model_admin.get_readonly_fields(req, self.a))


class AICapTests(ModuleBase):
    def post(self):
        self.client.force_login(self.stu_user)
        return self.client.post(reverse('dashboard:me_assistant'), {'question': 'math'})

    def test_daily_cap_blocks_with_a_message_and_does_not_count_the_blocked_call(self):
        grant(self.a, 'tutor_ai')
        self.a.ai_daily_cap = 2
        self.a.save()
        self.assertEqual((self.post().status_code, self.post().status_code), (200, 200))
        blocked = self.post()
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, 'سقف روزانه', status_code=429)
        self.assertNotContains(blocked, 'DEMO STUB reply', status_code=429)
        self.assertEqual(AICallUsage.objects.get(school=self.a).count, 2)

    def test_monthly_cap_and_a_new_day_and_other_school_are_independent(self):
        grant(self.a, 'tutor_ai')
        grant(self.b, 'tutor_ai')
        self.a.ai_daily_cap, self.a.ai_monthly_cap = 5, 3
        self.a.save()
        today = TODAY()
        first = today.replace(day=1)
        AICallUsage.objects.create(school=self.a, module_key='tutor_ai', day=first, count=3)     # earlier this month (or today)
        if first == today:
            AICallUsage.objects.all().delete()
            AICallUsage.objects.create(school=self.a, module_key='tutor_ai', day=today, count=3)
        with self.assertRaises(ai_guard.AICapReached) as ctx:
            ai_guard.consume(self.a, 'tutor_ai')
        self.assertEqual(ctx.exception.period, 'monthly')
        ai_guard.consume(self.b, 'tutor_ai')                                                        # school B unaffected
        self.assertEqual(AICallUsage.objects.get(school=self.b).count, 1)
        ai_guard.consume(self.a, 'advisor_ai')                                                      # caps are per module
        with self.assertRaises(ai_guard.AICapReached) as ctx:
            ai_guard.consume(self.a, 'tutor_ai', on=today)
        self.assertEqual(ctx.exception.period, 'monthly')

    def test_defaults_come_from_settings_when_the_school_has_no_override(self):
        from django.test import override_settings

        grant(self.a, 'tutor_ai')
        with override_settings(AI_DEFAULT_DAILY_CAP=1):
            ai_guard.consume(self.a, 'tutor_ai')
            with self.assertRaises(ai_guard.AICapReached):
                ai_guard.consume(self.a, 'tutor_ai')
