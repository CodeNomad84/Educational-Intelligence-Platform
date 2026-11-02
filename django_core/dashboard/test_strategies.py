"""P6-1 strategy library: SchoolAdmin only, own school only, plan creation accepts only an active same-school entry."""
from django.core.management import call_command
from django.urls import reverse

from interventions.models import InterventionPlan, Strategy
from risk.loop_testing import LoopBase
from schools.models import School


class StrategyTests(LoopBase):
    def test_seed_is_idempotent_and_roles(self):
        call_command('seed_strategies', stdout=open('/dev/null', 'w'))
        n = Strategy.objects.filter(school=self.a).count()
        self.assertGreaterEqual(n, 48)
        call_command('seed_strategies', stdout=open('/dev/null', 'w'))
        self.assertEqual(Strategy.objects.filter(school=self.a).count(), n)
        url = reverse('dashboard:school_strategies')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        for user in (self.lead, self.teacher, self.parent, self.counselor):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403, user.username)

    def test_other_school_row_is_404_and_plan_ignores_foreign_strategy(self):
        other = School.objects.create(name='Other school')
        foreign = Strategy.objects.create(school=other, title='x', intervention_type='academic', description='d')
        own = Strategy.objects.create(school=self.a, title='y', intervention_type='academic', description='d')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:school_strategy_edit', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('dashboard:school_strategy_toggle', args=[foreign.pk])).status_code, 404)
        data = {'intervention_type': 'academic', 'goal': 'g', 'action_plan': 'a', 'start_date': '2026-10-26', 'due_date': '2026-11-20'}
        self.client.force_login(self.lead)
        self.client.post(reverse('dashboard:plan_new', args=[self.s7.pk]), {**data, 'strategy': foreign.pk})
        self.assertIsNone(InterventionPlan.objects.get().strategy)
        InterventionPlan.objects.all().delete()
        self.client.post(reverse('dashboard:plan_new', args=[self.s7.pk]), {**data, 'strategy': own.pk})
        self.assertEqual(InterventionPlan.objects.get().strategy, own)

    def test_changes_are_audited_and_duplicates_are_a_form_error(self):
        from schools.models import AuditEvent
        self.client.force_login(self.admin)
        data = {'title': 'T1', 'intervention_type': 'academic', 'tier': 1, 'typical_days': 20, 'description': 'd'}
        url = reverse('dashboard:school_strategies')
        self.client.post(url, data)
        self.assertEqual(self.client.post(url, data).status_code, 200)       # duplicate title: form error, not a 500
        self.assertEqual(Strategy.objects.filter(school=self.a, title='T1').count(), 1)
        self.assertEqual(self.client.post(url, {**data, 'title': 'T2', 'typical_days': 0}).status_code, 200)
        obj = Strategy.objects.get(title='T1')
        self.client.post(reverse('dashboard:school_strategy_toggle', args=[obj.pk]))
        self.assertEqual(set(AuditEvent.objects.filter(action='strategy_save').values_list('detail', flat=True)), {'created', 'off'})

    def test_effectiveness_is_withheld_below_five_completed_plans(self):
        """P6-3: outcomes per strategy appear only from MIN_GROUP completed plans."""
        from datetime import date

        from interventions.models import InterventionPlan
        s = Strategy.objects.create(school=self.a, title='eff', intervention_type='academic', description='d')
        def plan(outcome):
            return InterventionPlan.objects.create(
                school=self.a, student=self.s7, owner=self.lead, created_by=self.lead, intervention_type='academic', goal='g',
                action_plan='a', start_date=date(2026, 10, 1), due_date=date(2026, 11, 1), status='completed', outcome=outcome, strategy=s)
        self.client.force_login(self.admin)
        for _ in range(4):
            plan('improved')
        page = self.client.get(reverse('dashboard:school_strategies')).content.decode()
        self.assertIn('کمتر از ۵ برنامهٔ پایان‌یافته', page)
        self.assertNotIn('بهبود 4', page)
        plan('worse')
        page = self.client.get(reverse('dashboard:school_strategies')).content.decode()
        self.assertIn('بهبود 4 · بدون تغییر 0 · بدتر 1', page)
