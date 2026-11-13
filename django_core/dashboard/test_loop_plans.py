"""Plan pages (change 0022): roles, scope, the emotional-text gate in the rendered HTML, the full loop over HTTP, audit."""
from django.urls import reverse

from interventions.models import InterventionFollowUp, InterventionPlan
from interventions.services import add_followup, start_plan
from risk.loop_testing import LoopBase
from risk.models import Alert
from schools.models import AuditEvent, SchoolModule

SECRET_GOAL, SECRET_ACTION = 'GOAL-secret-xyz', 'ACTION-secret-xyz'


def form(**extra):
    return {'intervention_type': 'academic', 'goal': 'Raise marks', 'action_plan': 'Weekly review',
            'start_date': '2026-10-26', 'due_date': '2026-11-20', **extra}


class PlanPageTests(LoopBase):
    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)

    def get(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args))

    def post(self, user, name, data=None, *args):
        self.client.force_login(user)
        return self.client.post(reverse(name, args=args), data or {})

    def test_no_module_rows_needed_and_roles(self):
        self.assertEqual(SchoolModule.objects.filter(school=self.a).count(), 0)
        for user in (self.admin, self.lead, self.counselor):
            self.assertEqual(self.get(user, 'dashboard:plan_list').status_code, 200, user.username)
        for user in (self.teacher, self.parent, self.student_user):
            self.assertEqual(self.get(user, 'dashboard:plan_list').status_code, 403, user.username)
            self.assertEqual(self.post(user, 'dashboard:plan_new', form(), self.s7.pk).status_code, 403)
        self.assertEqual(InterventionPlan.objects.count(), 0)

    def test_the_whole_loop_over_http(self):
        alert = self.alert()
        self.post(self.lead, 'dashboard:alert_review', {'decision': 'accept'}, alert.pk)
        response = self.post(self.lead, 'dashboard:plan_new', {**form(), 'alert': alert.pk}, self.s7.pk)
        plan = InterventionPlan.objects.get()
        self.assertRedirects(response, reverse('dashboard:plan_detail', args=[plan.pk]))
        self.assertEqual((plan.alert_id, plan.owner_id, plan.status), (alert.pk, self.lead.pk, 'planned'))
        self.post(self.lead, 'dashboard:plan_start', {}, plan.pk)
        self.post(self.lead, 'dashboard:plan_followup',
                  {'followup_date': '2026-10-26', 'assessment': 'on_track', 'progress_note': 'Met the student'}, plan.pk)
        self.post(self.lead, 'dashboard:plan_complete', {'outcome': 'improved', 'note': 'better'}, plan.pk)
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.outcome), ('completed', 'improved'))
        self.assertEqual(plan.followups.count(), 1)
        page = self.get(self.lead, 'dashboard:plan_detail', plan.pk).content.decode()
        self.assertIn('Met the student', page)
        listing = self.get(self.lead, 'dashboard:plan_list', ).content.decode()
        self.assertNotIn(reverse('dashboard:plan_detail', args=[plan.pk]), listing)          # closed: not in the default "open" list
        self.client.get(reverse('dashboard:plan_list') + '?status=completed')
        self.assertIn(reverse('dashboard:plan_detail', args=[plan.pk]),
                      self.client.get(reverse('dashboard:plan_list') + '?status=completed').content.decode())

    def test_a_dismissed_or_new_alert_cannot_start_a_plan(self):
        alert = self.alert()
        self.post(self.lead, 'dashboard:plan_new', {**form(), 'alert': alert.pk}, self.s7.pk)
        self.assertEqual(InterventionPlan.objects.count(), 0)
        self.assertEqual(Alert.objects.get(pk=alert.pk).status, 'new')

    def test_scope_is_404_for_create_view_and_every_action(self):
        plan = self.plan()
        start_plan(self.admin, plan)
        for user in (self.admin_b, self.lead_b, self.counselor_b, self.lead8):
            self.assertEqual(self.post(user, 'dashboard:plan_new', form(), self.s7.pk).status_code, 404, user.username)
            self.assertEqual(self.get(user, 'dashboard:plan_detail', plan.pk).status_code, 404, user.username)
            for name, data in (('plan_start', {}), ('plan_cancel', {}), ('plan_complete', {'outcome': 'improved'}),
                               ('plan_followup', {'followup_date': '2026-10-26', 'assessment': 'on_track', 'progress_note': 'x'}),
                               ('plan_reassign', {'owner': self.lead.pk})):
                self.assertEqual(self.post(user, f'dashboard:{name}', data, plan.pk).status_code, 404, (user.username, name))
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.owner_id), ('active', self.admin.pk))
        self.assertEqual(InterventionFollowUp.objects.count(), 0)

    def test_a_reviewer_who_does_not_own_the_plan_cannot_act(self):
        plan = self.plan(by=self.lead)
        for name in ('plan_start', 'plan_complete'):
            self.assertEqual(self.post(self.counselor, f'dashboard:{name}', {'outcome': 'improved'}, plan.pk).status_code, 403)
        self.assertEqual(InterventionPlan.objects.get(pk=plan.pk).status, 'planned')

    def test_emotional_text_never_reaches_the_admin_or_a_non_owner_lead(self):
        plan = self.plan(by=self.lead, kind='emotional', goal=SECRET_GOAL, action_plan=SECRET_ACTION)
        start_plan(self.lead, plan)
        add_followup(self.lead, plan, self.today, 'FOLLOW-secret-xyz', 'on_track')
        for user, sees in ((self.lead, True), (self.counselor, True), (self.admin, False)):
            page = self.get(user, 'dashboard:plan_detail', plan.pk)
            html = page.content.decode()
            self.assertEqual(page.status_code, 200)
            for secret in (SECRET_GOAL, SECRET_ACTION, 'FOLLOW-secret-xyz'):
                self.assertEqual(secret in html, sees, (user.username, secret))
        # the admin still sees the metadata and the follow-up count
        html = self.get(self.admin, 'dashboard:plan_detail', plan.pk).content.decode()
        self.assertIn('1 پیگیری', html)
        # a second Grade Lead of the same grade sees no row and no text
        from dashboard.test_counselor import make_user
        from schools.models import GradeLeadAssignment
        twin = make_user('twin', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=twin, school=self.a, grade=7, academic_year='1404-1405')
        html = self.get(twin, 'dashboard:plan_detail', plan.pk).content.decode()
        self.assertNotIn(SECRET_GOAL, html)
        self.assertNotIn(SECRET_GOAL, self.get(self.admin, 'dashboard:plan_list').content.decode())

    def test_every_plan_view_is_audited_with_text_or_meta(self):
        plan = self.plan(by=self.lead, kind='emotional', goal=SECRET_GOAL)
        self.get(self.lead, 'dashboard:plan_detail', plan.pk)
        self.get(self.admin, 'dashboard:plan_detail', plan.pk)
        self.get(self.counselor, 'dashboard:plan_detail', plan.pk)
        rows = list(AuditEvent.objects.filter(action='intervention_view').order_by('pk').values_list('username', 'detail'))
        self.assertEqual(rows, [('lead', 'text'), ('admin', 'meta'), ('counselor', 'text')])
        every = ' '.join(f'{a} {b} {c} {d}' for a, b, c, d in AuditEvent.objects.values_list(
            'action', 'detail', 'object_type', 'object_id'))
        self.assertNotIn('secret', every.lower())

    def test_admin_creates_a_plan_for_another_owner_but_not_an_emotional_one(self):
        self.post(self.admin, 'dashboard:plan_new', form(owner=self.lead.pk), self.s7.pk)
        self.assertEqual(InterventionPlan.objects.get().owner_id, self.lead.pk)
        self.post(self.admin, 'dashboard:plan_new', form(intervention_type='emotional', owner=self.counselor.pk), self.s7.pk)
        self.post(self.admin, 'dashboard:plan_new', form(intervention_type='emotional'), self.s7.pk)
        self.assertEqual(InterventionPlan.objects.filter(intervention_type='emotional').count(), 0)
        self.post(self.lead, 'dashboard:plan_new', form(owner=self.counselor.pk), self.s7.pk)     # not an admin: owner ignored
        self.assertEqual(InterventionPlan.objects.filter(owner=self.counselor).count(), 0)

    def test_admin_reassigns_an_emotional_plan_to_a_counselor_with_a_referral(self):
        plan = self.plan(by=self.lead, kind='emotional', goal=SECRET_GOAL)
        self.post(self.admin, 'dashboard:plan_reassign', {'owner': self.lead8.pk}, plan.pk)      # does not see the student
        self.assertEqual(InterventionPlan.objects.get(pk=plan.pk).owner_id, self.lead.pk)
        self.post(self.admin, 'dashboard:plan_reassign', {'owner': self.counselor.pk}, plan.pk)
        self.assertEqual(InterventionPlan.objects.get(pk=plan.pk).owner_id, self.counselor.pk)
        self.assertEqual(AuditEvent.objects.filter(action='intervention_owner').count(), 1)
        self.assertNotIn(SECRET_GOAL, self.get(self.lead, 'dashboard:plan_detail', plan.pk).content.decode())

    def test_post_endpoints_refuse_get_and_there_is_no_export(self):
        plan = self.plan()
        for name in ('plan_start', 'plan_cancel', 'plan_complete', 'plan_reassign', 'plan_followup'):
            self.assertEqual(self.get(self.admin, f'dashboard:{name}', plan.pk).status_code, 405, name)
        page = self.get(self.admin, 'dashboard:plan_list').content.decode().lower()
        self.assertNotIn('csv', page)
        self.assertNotIn('export', page)

    def test_menu_has_one_plans_entry_for_staff_and_none_for_others(self):
        url = reverse('dashboard:plan_list')
        for user in (self.admin, self.lead, self.counselor):
            self.client.force_login(user)
            self.assertEqual(self.client.get('/account/').content.decode().count(f'href="{url}"'), 1, user.username)
        for user in (self.teacher, self.parent, self.student_user):
            self.client.force_login(user)
            self.assertNotIn(f'href="{url}"', self.client.get('/account/').content.decode())

    def test_counselor_loses_the_pages_when_the_referral_closes(self):
        plan = self.plan(by=self.counselor, kind='emotional', goal=SECRET_GOAL)
        from students.models import Referral
        Referral.objects.update(status='closed')
        self.assertEqual(self.get(self.counselor, 'dashboard:plan_detail', plan.pk).status_code, 404)
