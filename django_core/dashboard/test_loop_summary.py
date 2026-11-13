"""Student 360 tile, re-evaluation list, recurrence tag and the demo seed of the intervention loop (change 0022)."""
from datetime import timedelta

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from interventions.models import InterventionPlan
from interventions.reeval import due_for_reevaluation, recurrence
from interventions.services import cancel_plan, complete_plan, start_plan
from risk.loop_testing import LoopBase
from risk.models import Alert
from students.access import visible_alerts, visible_plans

SECRET = 'EMO-goal-secret'


class TileTests(LoopBase):
    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)
        self.alert()
        self.done = self.plan()
        start_plan(self.admin, self.done)
        complete_plan(self.admin, self.done, 'improved')
        self.emotional = self.plan(by=self.lead, kind='emotional', goal=SECRET)

    def page(self, user, student=None):
        self.client.force_login(user)
        return self.client.get(reverse('dashboard:student_360', args=[(student or self.s7).pk]))

    def test_tile_shows_metadata_for_admin_and_lead_never_the_emotional_text(self):
        for user in (self.admin, self.lead):
            response = self.page(user)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['loop_plans']), 2)
            self.assertEqual(len(response.context['loop_alerts']), 1)
            self.assertNotIn(SECRET, response.content.decode())      # the 360 page never carries plan text, even for the owner
            self.assertIn('ارزیابی مجدد', response.content.decode())

    def test_a_parent_who_administers_another_school_still_gets_no_foreign_rows(self):
        from dashboard.test_counselor import make_user
        from schools.models import SchoolMembership
        both = make_user('both', 'Parent')
        both.groups.add(*self.admin_b.groups.all())
        SchoolMembership.objects.create(user=both, school=self.b)
        self.s7.parent_user = both
        self.s7.save(update_fields=['parent_user'])
        response = self.page(both)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['loop_plans']), [])
        self.assertEqual(list(response.context['loop_alerts']), [])

    def test_parent_gets_no_tile(self):
        response = self.page(self.parent)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('loop_plans', response.context)
        self.assertNotIn('هشدارها و مداخله‌ها', response.content.decode())

    def test_another_school_and_other_grade_see_no_tile_rows(self):
        self.assertEqual(self.page(self.admin_b).status_code, 404)
        self.assertEqual(self.page(self.lead8).status_code, 404)


class ReevaluationTests(LoopBase):
    def closed_plan(self, days_ago=40, reeval_days_ago=10):
        plan = self.plan()
        start_plan(self.admin, plan)
        complete_plan(self.admin, plan, 'no_change')
        InterventionPlan.objects.filter(pk=plan.pk).update(
            closed_at=timezone.now() - timedelta(days=days_ago), reevaluate_on=self.today - timedelta(days=reeval_days_ago))
        plan.refresh_from_db()
        return plan

    def due(self, user):
        return due_for_reevaluation(visible_plans(user), visible_alerts(user), self.today)

    def test_due_when_the_date_passed_and_nothing_followed(self):
        plan = self.closed_plan()
        self.assertEqual([p.pk for p in self.due(self.admin)], [plan.pk])
        self.assertEqual(self.due(self.admin_b), [])
        self.assertEqual(self.due(self.teacher), [])

    def test_not_due_before_the_date_or_after_new_activity(self):
        self.closed_plan(reeval_days_ago=-5)
        self.assertEqual(self.due(self.admin), [])
        other = self.closed_plan()
        self.alert()                                           # a newer alert for the student
        self.assertNotIn(other.pk, [p.pk for p in self.due(self.admin)])

    def test_the_list_is_shown_on_the_plans_page(self):
        plan = self.closed_plan()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:plan_list'))
        self.assertEqual([p.pk for p in response.context['due']], [plan.pk])

    def test_recurrence_same_kind_within_90_days_only(self):
        plan = self.closed_plan(days_ago=30)
        near = self.alert(risk_type='academic')
        other_kind = self.alert(risk_type='attendance')
        # another student: the only plan closed 200 days ago, so a new academic alert is outside the window
        old = self.plan(student=self.s8)
        start_plan(self.admin, old)
        complete_plan(self.admin, old, 'improved')
        InterventionPlan.objects.filter(pk=old.pk).update(closed_at=timezone.now() - timedelta(days=200))
        late = self.alert(self.s8, risk_type='academic')
        found = recurrence(Alert.objects.filter(pk__in=[near.pk, other_kind.pk, late.pk]).select_related('risk_event'),
                           visible_plans(self.admin))
        self.assertEqual({k: v.pk for k, v in found.items()}, {near.pk: plan.pk})

    def test_recurrence_tag_is_shown_to_reviewers_not_to_a_teacher(self):
        plan = self.closed_plan(days_ago=30)
        alert = self.alert(risk_type='academic', by=self.teacher)
        self.client.force_login(self.admin)
        tagged = {a.pk: a.recurred_plan for a in self.client.get(reverse('dashboard:alert_list')).context['alerts']}
        self.assertEqual(tagged[alert.pk], plan.pk)
        self.client.force_login(self.teacher)
        tagged = {a.pk: a.recurred_plan for a in self.client.get(reverse('dashboard:alert_list')).context['alerts']}
        self.assertEqual(tagged[alert.pk], None)

    def test_cancelled_plans_are_never_due(self):
        plan = self.plan()
        cancel_plan(self.admin, plan)
        InterventionPlan.objects.filter(pk=plan.pk).update(reevaluate_on=self.today - timedelta(days=3))
        self.assertEqual(self.due(self.admin), [])

