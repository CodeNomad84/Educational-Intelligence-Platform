"""Mission slice 2b: the weights lifecycle (draft > simulated > pending approval > active > retired) for the SchoolAdmin, the
aggregate simulation, immutability of active/retired sets, params_version, and the gate. Synthetic data only."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from dashboard.test_counselor import make_user
from schools.models import AuditEvent, SchoolModule
from schools.module_grants import grant
from students.access import PLATFORM_ADMIN

from . import lifecycle
from .models import Branch, Indicator, Observation, PathSuggestion, Weight, WeightSet
from .test_reports import ReportBase
from .tests import TODAY


class WeightBase(ReportBase):
    def setUp(self):
        super().setUp()
        self.active = WeightSet.objects.get(school=self.a, status='active')

    def url(self, name, ws):
        return reverse(f'missions:weight_{name}', args=[ws.pk])

    def do(self, user, ws, what, **extra):
        return self.post(user, self.url('action', ws), {'action': what, **extra})

    def new_draft(self):
        self.do(self.admin, self.active, 'clone')
        return WeightSet.objects.get(school=self.a, status='draft')

    def form(self, ws, **over):
        """The editor POST for ``ws`` with its current values, plus overrides (cell keys like 'w_1_nurturing')."""
        data = {'min_observations': ws.min_observations, 'min_activities': ws.min_activities, 'diff_threshold': ws.diff_threshold,
                'strong_at': ws.strong_at, 'growth_at': ws.growth_at, 'note': ws.note}
        if ws.show_x20:
            data['show_x20'] = 'on'
        cells = {(i, b): p for i, b, p in ws.weights.values_list('indicator__code', 'branch__code', 'percent')}
        data.update({f'w_{i}_{b}': p for (i, b), p in cells.items()})
        data.update(over)
        return data

    def move_ten(self, ws, branch='knowledge_production'):
        """Shift 10 points from indicator 1 to indicator 2 in one column (the column still sums to 100)."""
        return self.form(ws, **{f'w_1_{branch}': 15, f'w_2_{branch}': 35})

    def more_students(self, count):
        """Give ``count`` more students observations on all indicators (indicator 1 high, 2 low) in both activities."""
        for n in range(count):
            student = self.student(f'Extra{n}', self.c7, 7)
            for act in (self.a1, self.a2):
                for code in self.by_code:
                    for who in (self.t1, self.t1b):
                        self.add(act, who, code, 5 if code == 1 else 1 if code == 2 else 3, student=student)


class GatingTests(WeightBase):
    def setUp(self):
        super().setUp()
        self.draft = self.new_draft()

    def pages(self):
        return [self.url('detail', self.active), self.url('simulation', self.draft)]

    def test_allowed_denied_roles(self):
        for url in self.pages():
            self.assertEqual(self.get(self.admin, url).status_code, 200, url)
        operator = make_user('op', PLATFORM_ADMIN, is_staff=True)
        for user in (self.lead, self.t1, self.counselor, self.parent, operator):
            for url in self.pages():
                self.assertEqual(self.get(user, url).status_code, 403, (user.username, url))
            self.assertEqual(self.do(user, self.active, 'clone').status_code, 403, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(self.pages()[0]).status_code, 302)

    def test_expired_not_started_trial_and_cross_school(self):
        for state in ('none', 'expired', 'future'):
            SchoolModule.objects.filter(school=self.a).delete()
            if state == 'expired':
                grant(self.a, 'mission', starts_on=TODAY() - timedelta(days=9), ends_on=TODAY() - timedelta(days=1))
            if state == 'future':
                grant(self.a, 'mission', starts_on=TODAY() + timedelta(days=2))
            for url in self.pages():
                self.assertEqual(self.get(self.admin, url).status_code, 403, (state, url))
            self.assertEqual(self.do(self.admin, self.active, 'clone').status_code, 403)
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='mission', kind='trial', starts_on=TODAY() - timedelta(days=1),
                                    ends_on=TODAY() + timedelta(days=5))
        self.assertEqual(self.get(self.admin, self.pages()[0]).status_code, 200)
        grant(self.a, 'mission')
        for url in self.pages():
            self.assertEqual(self.get(self.admin_b, url).status_code, 404, url)                    # another school's admin
        self.assertEqual(self.do(self.admin_b, self.active, 'clone').status_code, 404)

    def test_trial_data_is_readable_again_after_a_licensed_row_is_added(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='mission', kind='trial', starts_on=TODAY() - timedelta(days=3),
                                    ends_on=TODAY() + timedelta(days=3))
        draft = self.draft
        self.assertEqual(self.post(self.admin, self.url('detail', draft), self.move_ten(draft)).status_code, 302)
        SchoolModule.objects.filter(school=self.a).update(ends_on=TODAY() - timedelta(days=1))
        self.assertEqual(self.get(self.admin, self.url('detail', draft)).status_code, 403)
        self.assertEqual(self.post(self.admin, self.url('detail', draft), self.form(draft)).status_code, 403)       # no write
        self.assertEqual(Weight.objects.get(weight_set=draft, indicator__code=2, branch__code='knowledge_production').percent, 35)
        grant(self.a, 'mission', starts_on=TODAY())
        page = self.get(self.admin, self.url('detail', draft))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'value="35"')


class EditingTests(WeightBase):
    def test_clone_creates_the_next_draft_with_the_same_numbers(self):
        draft = self.new_draft()
        self.assertEqual((draft.version, draft.status, draft.created_by_id), (2, 'draft', self.admin.pk))
        self.assertEqual(sorted(draft.weights.values_list('indicator_id', 'branch_id', 'percent')),
                         sorted(self.active.weights.values_list('indicator_id', 'branch_id', 'percent')))
        self.assertEqual(self.do(self.admin, self.active, 'clone').status_code, 302)           # refused: one unfinished set already
        self.assertEqual(WeightSet.objects.filter(school=self.a).count(), 2)

    def test_save_draft_updates_cells_and_thresholds_and_shows_column_sums(self):
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.move_ten(draft) | {'min_observations': 4, 'strong_at': '4.5', 'show_x20': 'on', 'note': 'trial'})
        draft.refresh_from_db()
        self.assertEqual((draft.min_observations, str(draft.strong_at), draft.show_x20, draft.note), (4, '4.5', True, 'trial'))
        page = self.get(self.admin, self.url('detail', draft))
        self.assertEqual(page.context['sums'], [100] * 8)
        broken = self.form(draft, w_1_nurturing=0)                                               # nurturing column now sums to 95
        self.post(self.admin, self.url('detail', draft), broken)
        self.assertEqual(self.get(self.admin, self.url('detail', draft)).context['sums'][5], 95)   # saved, flagged, not blocked

    def test_invalid_input_saves_nothing(self):
        draft = self.new_draft()
        before = sorted(draft.weights.values_list('indicator_id', 'branch_id', 'percent'))
        for bad in ({'w_1_nurturing': 101}, {'w_1_nurturing': 'x'}, {'w_1_nurturing': '-5'}, {'min_observations': 0}, {'min_activities': 11},
                    {'diff_threshold': '9'}, {'strong_at': '2.0', 'growth_at': '2.5'}, {'growth_at': '4.9'}, {'note': 'x' * 201}):
            response = self.post(self.admin, self.url('detail', draft), self.form(draft, **bad))
            self.assertEqual(response.status_code, 200, bad)
            self.assertTrue(response.context['errors'], bad)
        draft.refresh_from_db()
        self.assertEqual(sorted(draft.weights.values_list('indicator_id', 'branch_id', 'percent')), before)

    def test_only_a_draft_is_editable_and_active_or_retired_never_change(self):
        self.assertEqual(self.post(self.admin, self.url('detail', self.active), self.move_ten(self.active)).status_code, 404)
        self.assertEqual(Weight.objects.get(weight_set=self.active, indicator__code=1, branch__code='knowledge_production').percent, 25)
        with self.assertRaises(ValidationError):
            w = Weight.objects.filter(weight_set=self.active).first()
            w.percent = 1
            w.save()
        with self.assertRaises(ValidationError):
            self.active.min_observations = 9
            self.active.save()
        with self.assertRaises(ValidationError):
            self.active.delete()
        page = self.get(self.admin, self.url('detail', self.active))
        self.assertNotContains(page, 'ذخیرهٔ پیش‌نویس')
        self.assertFalse(page.context['editable'])


class LifecycleTests(WeightBase):
    def go(self, ws, what):
        self.do(self.admin, ws, what)
        ws.refresh_from_db()
        return ws.status

    def test_the_full_path_and_the_old_set_is_retired(self):
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.move_ten(draft))
        self.assertEqual(self.go(draft, 'submit'), 'draft')                    # a draft cannot jump to pending
        self.assertEqual(self.go(draft, 'approve'), 'draft')                   # nor to active
        self.assertEqual(self.go(draft, 'simulate'), 'simulated')
        self.assertEqual(self.go(draft, 'approve'), 'simulated')               # still needs submission
        self.assertEqual(self.go(draft, 'submit'), 'pending_approval')
        self.assertEqual(self.go(draft, 'approve'), 'active')
        self.active.refresh_from_db()
        self.assertEqual(self.active.status, 'retired')
        self.assertEqual(WeightSet.objects.filter(school=self.a, status='active').count(), 1)
        draft.refresh_from_db()
        self.assertEqual((draft.approved_by_id, draft.approved_at is not None), (self.admin.pk, True))
        self.assertEqual(self.go(draft, 'reopen'), 'active')                   # an active set cannot be reopened
        self.assertEqual(self.go(self.active, 'reopen'), 'retired')

    def test_simulate_needs_columns_summing_to_100(self):
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.form(draft, w_1_nurturing=0))
        self.assertEqual(self.go(draft, 'simulate'), 'draft')
        self.post(self.admin, self.url('detail', draft), self.form(draft, w_1_nurturing=5))
        self.assertEqual(self.go(draft, 'simulate'), 'simulated')

    def test_reopen_returns_to_draft_and_editing_resets_the_path(self):
        draft = self.new_draft()
        self.go(draft, 'simulate')
        self.assertEqual(self.go(draft, 'reopen'), 'draft')
        self.go(draft, 'simulate')
        self.go(draft, 'submit')
        self.assertEqual(self.go(draft, 'reopen'), 'draft')
        self.assertEqual(self.post(self.admin, self.url('detail', draft), self.move_ten(draft)).status_code, 302)
        self.assertEqual(self.go(draft, 'submit'), 'draft')

    def test_params_version_old_snapshots_keep_their_set_and_new_reports_use_the_new_one(self):
        self.post(self.lead, reverse('missions:plan', args=[self.s7.pk]), self.plan_data([('nurturing', self.future()), ('culture_promotion', self.future())]))
        old_plan = PathSuggestion.objects.first()
        self.assertEqual(old_plan.params_version, self.active.pk)
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.move_ten(draft))
        for what in ('simulate', 'submit', 'approve'):
            self.go(draft, what)
        page = self.get(self.lead, self.report_url)
        self.assertEqual(page.context['params_version'], draft.pk)
        old_plan.refresh_from_db()
        self.assertEqual(old_plan.params_version, self.active.pk)              # the stored snapshot is untouched
        self.post(self.lead, reverse('missions:plan', args=[self.s7.pk]), self.plan_data([('nurturing', self.future()), ('culture_promotion', self.future())]))
        self.assertEqual(set(PathSuggestion.objects.values_list('params_version', flat=True)), {draft.pk})

    def test_new_thresholds_apply_only_after_activation(self):
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.form(draft, strong_at='5.0', growth_at='1.0'))
        before = self.get(self.lead, self.report_url).context['strong']
        for what in ('simulate', 'submit', 'approve'):
            self.go(draft, what)
        after = self.get(self.lead, self.report_url).context['strong']
        self.assertEqual([i['name'] for i in before], ['کاوشگری و فهم عمیق'])        # score 5 >= 4.0 under the old set
        self.assertEqual([i['name'] for i in after], ['کاوشگری و فهم عمیق'])         # and >= 5.0 under the new one
        self.assertEqual(draft.pk, self.get(self.lead, self.report_url).context['params_version'])

    def test_audit_has_versions_and_codes_without_numbers(self):
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.move_ten(draft) | {'note': 'secret-note'})
        for what in ('simulate', 'submit', 'approve'):
            self.go(draft, what)
        events = AuditEvent.objects.filter(action__startswith='mission_weights_')
        self.assertTrue({'mission_weights_save', 'mission_weights_simulate', 'mission_weights_status'} <= set(events.values_list('action', flat=True)))
        details = set(events.filter(action='mission_weights_status').values_list('detail', flat=True))
        self.assertTrue({'clone:v2', 'submit:v2', 'approve:v2'} <= details)
        self.assertFalse(any('secret' in str(v) or '35' in str(v) for e in events for v in (e.detail, e.object_type, e.object_id)))


class SimulationTests(WeightBase):
    def test_withheld_below_five_students(self):
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.move_ten(draft))
        page = self.get(self.admin, self.url('simulation', draft))
        self.assertTrue(page.context['result']['withheld'])
        self.assertEqual(page.context['result']['n'], 1)
        self.assertNotContains(page, 'Seven')

    def test_identical_copy_changes_nothing(self):
        self.more_students(5)
        draft = self.new_draft()
        result = self.get(self.admin, self.url('simulation', draft)).context['result']
        self.assertFalse(result['withheld'])
        self.assertEqual(result['top3_changed'], 0)
        self.assertTrue(all(r['changed'] in (0, None) and r['status_changed'] == 0 for r in result['rows']))

    def test_moved_weights_change_scores_in_aggregate_only(self):
        self.more_students(5)
        draft = self.new_draft()
        self.post(self.admin, self.url('detail', draft), self.move_ten(draft))               # indicator 1 (score 5) -10, indicator 2 (score 1) +10
        page = self.get(self.admin, self.url('simulation', draft))
        result = page.context['result']
        self.assertEqual(result['n'], 6)
        row = next(r for r in result['rows'] if r['branch'] == 'تولید دانش')
        self.assertEqual(row['changed'], 5)                                                    # the five extras have indicators 1 and 2 scored
        self.assertLess(row['mean_after'], row['mean_before'])
        self.assertAlmostEqual(float(row['mean_before'] - row['mean_after']), 0.4, places=2)    # 0.10 * (5 - 1)
        html = page.content.decode()
        for secret in ('Seven', 'Extra0', 'found-two-causes', 'Obsone', 't1b-evidence-text'):
            self.assertNotIn(secret, html)

    def test_simulation_is_only_for_unfinished_sets_and_the_period_is_the_schools(self):
        self.assertEqual(self.get(self.admin, self.url('simulation', self.active)).status_code, 404)
        draft = self.new_draft()
        self.assertEqual(self.get(self.admin, self.url('simulation', draft) + '?period=999999').status_code, 200)   # unknown period: the latest
        self.assertEqual(self.get(self.admin_b, self.url('simulation', draft)).status_code, 404)

    def test_running_the_simulation_action_marks_it_and_audits_the_count(self):
        draft = self.new_draft()
        response = self.do(self.admin, draft, 'simulate')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/simulation/', response['Location'])
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'simulated')
        self.assertEqual(AuditEvent.objects.get(action='mission_weights_simulate').detail, 'n1')


class ApprovalTrailTests(WeightBase):
    """Single-approver decision (2026-10-25): the approval is attributable and timed, in the audit log and on the page."""

    def test_page_and_audit_show_who_created_who_approved_and_when(self):
        draft = self.new_draft()
        for what in ('simulate', 'submit', 'approve'):
            self.do(self.admin, draft, what)
        draft.refresh_from_db()
        self.assertEqual((draft.created_by_id, draft.approved_by_id), (self.admin.pk, self.admin.pk))
        self.assertIsNotNone(draft.approved_at)
        page = self.get(self.admin, self.url('detail', draft))
        self.assertContains(page, 'ساخته‌شده توسط')
        self.assertContains(page, 'admin')
        from dashboard.templatetags.eip_ui import jdate
        self.assertContains(page, jdate(draft.approved_at))   # Jalali display (decision 46)
        event = AuditEvent.objects.get(action='mission_weights_status', detail='approve:v2')
        self.assertEqual((event.username, event.school_id, event.object_id), ('admin', self.a.pk, str(draft.pk)))
        self.assertIsNotNone(event.created_at)

    def test_a_second_administrator_can_be_the_approver_and_is_recorded(self):
        from schools.models import SchoolMembership
        other = make_user('admin2', 'SchoolAdmin')
        SchoolMembership.objects.create(user=other, school=self.a)
        draft = self.new_draft()
        for what in ('simulate', 'submit'):
            self.do(self.admin, draft, what)
        self.do(other, draft, 'approve')
        draft.refresh_from_db()
        self.assertEqual((draft.created_by.username, draft.approved_by.username), ('admin', 'admin2'))
        self.assertEqual(AuditEvent.objects.get(action='mission_weights_status', detail='approve:v2').username, 'admin2')
