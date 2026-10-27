"""0025 commit 3: run-now button, run history with the breaker status, quality aggregates (groups under 5 withheld), alert display."""
from django.urls import reverse

from risk.models import Alert, Rule, RuleHit, RuleRun, RuleSettings
from risk.quality import rule_quality
from risk.rules_testing import TODAY, RulesBase
from schools.models import AuditEvent


class RunNowTests(RulesBase):
    def test_button_runs_only_the_admins_own_school_and_ignores_request_parameters(self):
        self.absent_streak(self.s7)
        self.absent_streak(self.sb)
        self.live()
        b_rule = self.starter(school=self.b, code='repeated_absence', by=self.admin_b)
        Rule.objects.filter(pk=b_rule.pk).update(status='active')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('rules:run') + f'?school={self.b.pk}', {'school': self.b.pk, 'school_id': self.b.pk,
                                                                                 'as_of': '2020-01-01'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(RuleRun.objects.filter(mode='live').values_list('school_id', flat=True)), {self.a.pk})
        self.assertEqual(Alert.objects.filter(student=self.sb).count(), 0)
        self.assertEqual(set(AuditEvent.objects.filter(action='rule_run').values_list('username', flat=True)), {'admin'})

    def test_other_roles_cannot_run(self):
        self.live()
        for user in (self.lead, self.teacher, self.counselor, self.parent):
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('rules:run')).status_code, 403, user.username)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('rules:run')).status_code, 302)
        self.assertEqual(RuleRun.objects.filter(mode='live').count(), 0)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('rules:run')).status_code, 405)

    def test_breaker_status_is_shown_to_the_admin(self):
        from datetime import timedelta
        from django.utils import timezone
        today = timezone.localdate()
        from students.models import Attendance
        for student in (self.s7, self.s8):
            for d in range(1, 8):
                Attendance.objects.create(student=student, date=today - timedelta(days=d), status='absent')
        self.live()
        self.client.force_login(self.admin)
        self.client.post(reverse('rules:run'))
        page = self.client.get(reverse('rules:index'))
        self.assertContains(page, 'قطع‌کن فعال شد')
        self.assertContains(page, 'آستانه‌ها را بازبینی کنید')
        self.assertEqual(Alert.objects.count(), 0)


class QualityTests(RulesBase):
    def make(self, n, status='new', reason='', code='repeated_absence'):
        rule = Rule.objects.filter(school=self.a, code=code).first() or self.live(code=code)
        students = [self.student(f'Q{code}{status}{reason}{i}', self.c7, 7) for i in range(n)]
        for student in students:
            alert = self.alert(student=student)
            Alert.objects.filter(pk=alert.pk).update(status=status, dismiss_reason=reason, review_note='n' if reason == 'other' else '')
            RuleHit.objects.create(school=self.a, rule=rule, student=student, alert=alert, evaluated_on=TODAY, evidence={})

    def test_groups_under_five_are_withheld_and_no_students_appear(self):
        self.make(6, 'new')
        self.make(5, 'dismissed', 'not_relevant')
        self.make(3, 'dismissed', 'duplicate')
        self.make(4, 'accepted')
        (row,) = rule_quality(self.a.pk)
        self.assertEqual((row['raised'], row['accepted'], row['withheld']), (18, None, False))      # 4 accepted < 5 -> withheld
        self.assertEqual(row['dismissed'], {'not_relevant': 5, 'duplicate': None})
        self.assertNotIn('student', str(row))

    def test_a_rule_with_fewer_than_five_alerts_shows_nothing(self):
        self.make(4, 'new')
        (row,) = rule_quality(self.a.pk)
        self.assertEqual((row['withheld'], row['raised'], row['accepted'], row['dismissed']), (True, None, None, {}))

    def test_quality_is_per_school(self):
        self.make(6, 'new')
        self.assertEqual(rule_quality(self.b.pk), [])

    def test_page_renders_the_withheld_note(self):
        self.make(4, 'new')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('rules:index')), 'نمایش داده نمی‌شود')


class AlertDisplayTests(RulesBase):
    def test_rule_alert_is_visible_to_reviewers_with_the_rule_label_and_numbers_not_to_a_teacher(self):
        self.absent_streak(self.s7)
        self.live()
        from risk import rules
        rules.run_school(self.a.pk, as_of=TODAY)
        self.refer(self.s7, self.counselor)
        for user in (self.admin, self.lead, self.counselor):
            self.client.force_login(user)
            page = self.client.get(reverse('dashboard:alert_list'))
            self.assertContains(page, 'ثبت‌شده توسط قاعدهٔ repeated_absence', msg_prefix=user.username)
            self.assertContains(page, 'تعداد روزهای غیبت', msg_prefix=user.username)       # the evidence numbers are in the message
        for user in (self.teacher, self.admin_b, self.lead_b):
            self.client.force_login(user)
            self.assertNotContains(self.client.get(reverse('dashboard:alert_list')), 'repeated_absence', msg_prefix=user.username)
