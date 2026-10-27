"""0025 commit 2: the SchoolAdmin rules pages. Role matrix, school isolation, base module (works with zero SchoolModule rows)."""
from django.urls import reverse

from dashboard.test_counselor import make_user
from risk import lifecycle, rules
from risk.models import Rule, RuleSettings
from risk.rules_testing import TODAY, RulesBase
from schools.models import AuditEvent, SchoolMembership, SchoolModule


class RulesViewsTests(RulesBase):
    def login(self, user):
        self.client.force_login(user)

    def post_rule(self, **over):
        data = {'code': 'my_rule', 'kind': 'repeated_absence', 'title': 'قاعدهٔ من', 'risk_type': 'attendance', 'severity': 'yellow',
                'connective': 'all', 'cooldown_days': '14', 'c0_metric': 'absent_days', 'c0_op': '>=', 'c0_threshold': '3',
                'c0_window': '14', 'c0_min': '5'}
        data.update(over)
        return self.client.post(reverse('rules:create'), data)

    def test_works_with_zero_module_rows(self):
        self.assertEqual(SchoolModule.objects.count(), 0)
        self.login(self.admin)
        self.assertContains(self.client.get(reverse('rules:index')), 'اعتبارسنجی‌نشده')
        self.assertEqual(self.post_rule().status_code, 302)
        self.assertEqual(Rule.objects.get(code='my_rule').status, 'draft')

    def test_role_matrix_pages_and_actions(self):
        rule = self.starter(code='repeated_absence')
        urls = [('get', reverse('rules:index')), ('get', reverse('rules:create')), ('get', reverse('rules:detail', args=[rule.pk])),
                ('post', reverse('rules:settings')), ('post', reverse('rules:action', args=[rule.pk])),
                ('post', reverse('rules:detail', args=[rule.pk])), ('post', reverse('rules:create'))]
        self.client.logout()
        for method, url in urls:
            self.assertEqual(getattr(self.client, method)(url).status_code, 302, url)       # anonymous -> login
        platform = make_user('platform', 'PlatformAdmin')
        su = make_user('root', None, is_superuser=True, is_staff=True)
        for user in (self.lead, self.teacher, self.counselor, self.parent, self.student_user, platform, su):
            self.login(user)
            for method, url in urls:
                self.assertEqual(getattr(self.client, method)(url, {'do': 'approve'}).status_code, 403, f'{user.username} {url}')
        self.assertEqual(Rule.objects.get(pk=rule.pk).status, 'draft')

    def test_another_schools_admin_gets_404_for_a_rule_and_cannot_change_it(self):
        rule = self.starter(code='repeated_absence')
        self.login(self.admin_b)
        self.assertEqual(self.client.get(reverse('rules:detail', args=[rule.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('rules:action', args=[rule.pk]), {'do': 'archive'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('rules:index') + f'?school={self.a.pk}').context['school'].pk, self.b.pk)
        self.assertEqual(Rule.objects.get(pk=rule.pk).status, 'draft')

    def test_full_flow_through_the_pages(self):
        self.login(self.admin)
        self.post_rule()
        rule = Rule.objects.get(code='my_rule')
        act = lambda do: self.client.post(reverse('rules:action', args=[rule.pk]), {'do': do})   # noqa: E731
        page = act('simulate')
        self.assertContains(page, 'هیچ هشداری ثبت نشد')
        self.assertEqual(act('submit').status_code, 302)
        self.assertEqual(act('approve').status_code, 302)
        self.assertEqual(Rule.objects.get(pk=rule.pk).status, 'active')
        self.assertEqual(act('pause').status_code, 302)
        self.assertEqual(Rule.objects.get(pk=rule.pk).status, 'paused')
        edit = self.client.post(reverse('rules:detail', args=[rule.pk]), {'title': 'x', 'risk_type': 'attendance', 'severity': 'yellow',
                                'connective': 'all', 'cooldown_days': '1', 'c0_metric': 'late_count', 'c0_op': '>=', 'c0_threshold': '1', 'c0_window': '5'})
        self.assertEqual(edit.status_code, 200)                           # refused: shown again with an error, rule unchanged
        self.assertEqual(Rule.objects.get(pk=rule.pk).clauses[0]['metric'], 'absent_days')

    def test_bad_input_is_shown_as_errors_not_saved(self):
        self.login(self.admin)
        for over in ({'risk_type': 'emotional'}, {'c0_metric': 'os.system'}, {'c0_threshold': 'abc'}, {'c0_window': '9999'},
                     {'code': ''}, {'severity': 'red'}, {'cooldown_days': '0'}):
            with self.subTest(over=over):
                self.assertEqual(self.post_rule(**over).status_code, 200)
        self.assertEqual(Rule.objects.count(), 0)

    def test_settings_page_saves_and_audits_keys_only(self):
        self.login(self.admin)
        AuditEvent.objects.all().delete()
        self.client.post(reverse('rules:settings'), {'grade_scale_max': '100', 'breaker_percent': '10', 'second': 'on'})
        s = RuleSettings.objects.get(school=self.a)
        self.assertEqual((s.grade_scale_max, s.breaker_percent, s.require_second_approver), (100, 10, True))
        self.assertEqual(AuditEvent.objects.get(action='rule_settings').detail, 'scale,breaker,second')
        self.client.post(reverse('rules:settings'), {'grade_scale_max': '', 'breaker_percent': '0'})
        self.assertEqual(RuleSettings.objects.get(school=self.a).breaker_percent, 10)       # invalid: unchanged
        self.assertFalse(RuleSettings.objects.filter(school=self.b).exists())

    def test_score_rule_cannot_be_created_without_a_scale_through_the_page(self):
        RuleSettings.objects.filter(school=self.a).update(grade_scale_max=None)
        self.login(self.admin)
        response = self.post_rule(c0_metric='avg_score', c0_op='<', c0_threshold='12', risk_type='academic')
        self.assertContains(response, 'سقف مقیاس نمره')
        self.assertEqual(Rule.objects.count(), 0)

    def test_post_requires_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('rules:settings'), {'breaker_percent': '15'}).status_code, 403)

    def test_text_in_the_pages_is_escaped(self):
        self.login(self.admin)
        self.post_rule(title='<script>alert(1)</script>')
        self.assertNotContains(self.client.get(reverse('rules:index')), '<script>alert(1)</script>')
