"""0025 commit 3: the runner (alerts from active rules), cooldown, circuit breaker, atomicity, school isolation, command, audit."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError

from interventions.models import InterventionPlan
from risk import lifecycle, rules
from risk.models import Alert, RiskEvent, Rule, RuleHit, RuleRun, RuleSettings
from risk.rules_testing import TODAY, RulesBase
from schools.models import AuditEvent
from students.access import visible_alerts
from students.models import Attendance, Enrollment, Grade, Student


class RunnerTests(RulesBase):
    def fire(self, *students):
        for student in students:
            self.absent_streak(student)

    def go(self, as_of=TODAY, **kw):
        return rules.run_school(self.a.pk, as_of=as_of, **kw)

    def test_raises_ordinary_alerts_with_evidence_and_no_names(self):
        self.fire(self.s7)
        self.live()
        (run,) = self.go()
        self.assertEqual((run.status, run.evaluated, run.hits, run.alerts_raised), ('ok', 8, 1, 1))
        alert = Alert.objects.get()
        self.assertEqual((alert.student_id, alert.raised_by_id, alert.status, alert.school_id), (self.s7.pk, None, 'new', self.a.pk))
        event = alert.risk_event
        self.assertEqual((event.detected_by, event.risk_type, event.severity), ('rule_engine', 'attendance', 'yellow'))
        hit = RuleHit.objects.get()
        self.assertEqual((hit.alert_id, hit.evaluated_on, hit.student_id), (alert.pk, TODAY, self.s7.pk))
        self.assertEqual({i['metric'] for i in hit.evidence['items']}, {'absent_days', 'max_consecutive_absences'})
        self.assertNotIn(self.s7.first_name, alert.message + event.explanation)
        self.assertIn('repeated_absence', alert.message)

    def test_alert_follows_normal_visibility(self):
        self.fire(self.s7)
        self.live()
        self.go()
        alert = Alert.objects.get()
        for user in (self.admin, self.lead):
            self.assertIn(alert.pk, visible_alerts(user).values_list('pk', flat=True), user.username)
        for user in (self.admin_b, self.lead_b, self.parent, self.student_user):
            self.assertNotIn(alert.pk, visible_alerts(user).values_list('pk', flat=True), user.username)

    def test_second_run_the_same_day_creates_nothing_more(self):
        self.fire(self.s7)
        self.live()
        self.go()
        (again,) = self.go()
        self.assertEqual((Alert.objects.count(), RuleHit.objects.count(), again.alerts_raised, again.skipped_cooldown), (1, 1, 0, 1))

    def test_only_active_rules_run(self):
        self.fire(self.s7)
        rule = self.live()
        for status in ('paused', 'archived'):
            Rule.objects.filter(pk=rule.pk).update(status=status)
            self.assertEqual(self.go(), [])
        draft = self.starter(code='attendance_shift')
        self.assertEqual(self.go(), [])
        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(draft.status, 'draft')

    def test_insufficient_data_never_raises(self):
        self.absent_streak(self.s7, days=range(1, 4))
        self.live()
        (run,) = self.go()
        self.assertEqual((run.alerts_raised, run.skipped_insufficient, Alert.objects.count()), (0, 8, 0))

    def test_cooldown_new_alert_blocks_even_after_the_cooldown(self):
        self.fire(self.s7)
        self.live()
        self.go()
        later = TODAY + timedelta(days=60)
        Attendance.objects.all().delete()
        self.absent_streak(self.s7, days=range(1, 4))   # nothing in window around `later` ... recreate a fresh streak for it
        for d in range(1, 8):
            Attendance.objects.create(student=self.s7, date=later - timedelta(days=d), status='absent')
        (run,) = self.go(as_of=later)
        self.assertEqual((run.alerts_raised, run.skipped_cooldown), (0, 1))            # the first alert is still `new`

    def _second_wave(self, status, plan_status=None):
        self.fire(self.s7)
        self.live()
        self.go()
        alert = Alert.objects.get()
        if status == 'dismissed':
            Alert.objects.filter(pk=alert.pk).update(status='dismissed', dismiss_reason='not_relevant')
        else:
            from risk.services import review_alert
            review_alert(self.admin, alert, 'accepted')
            alert.refresh_from_db()
        if plan_status:
            self._plan(alert, plan_status)
        return alert

    def _plan(self, alert, status):
        plan = self.plan(student=self.s7, alert=alert, kind='behavioral')
        InterventionPlan.objects.filter(pk=plan.pk).update(status=status, **({'outcome': 'improved'} if status == 'completed' else {}))
        return plan

    def _later(self, days):
        day = TODAY + timedelta(days=days)
        for d in range(1, 8):
            Attendance.objects.update_or_create(student=self.s7, date=day - timedelta(days=d), defaults={'status': 'absent'})
        return self.go(as_of=day)[0]

    def test_dismissed_alert_blocks_only_until_the_cooldown_has_passed(self):
        self._second_wave('dismissed')
        self.assertEqual(self._later(5).alerts_raised, 0)                  # 5 < 14 days
        self.assertEqual(self._later(20).alerts_raised, 1)                 # cooldown passed -> fires again
        self.assertEqual(Alert.objects.count(), 2)

    def test_accepted_alert_with_an_open_plan_blocks_even_after_the_cooldown(self):
        self._second_wave('accepted', 'active')
        self.assertEqual(self._later(40).alerts_raised, 0)
        self.assertEqual(Alert.objects.count(), 1)

    def test_accepted_alert_without_open_plan_follows_the_cooldown(self):
        self._second_wave('accepted')
        self.assertEqual(self._later(3).alerts_raised, 0)
        self.assertEqual(self._later(30).alerts_raised, 1)

    def test_a_completed_plan_does_not_block_after_the_cooldown(self):
        self._second_wave('accepted', 'completed')
        self.assertEqual(self._later(30).alerts_raised, 1)

    def test_cooldown_ignored_mutation_is_visible(self):
        self._second_wave('dismissed')
        with mock.patch.object(rules, '_blocked_by_cooldown', return_value=False):
            self.assertEqual(self._later(5).alerts_raised, 1)               # proves the patch point is what the tests above guard

    # ---- circuit breaker ----
    def test_breaker_trips_above_the_percentage_and_raises_nothing(self):
        self.fire(self.s7, self.s8)                                         # 2 of 8 = 25% > 15%
        self.live()
        (run,) = self.go()
        self.assertEqual((run.status, run.hits, run.alerts_raised, run.evaluated), ('breaker_tripped', 2, 0, 8))
        self.assertEqual((Alert.objects.count(), RuleHit.objects.count(), RiskEvent.objects.count()), (0, 0, 0))
        self.assertTrue(AuditEvent.objects.get(action='rule_run').detail.endswith('B'))

    def test_breaker_boundary_and_setting(self):
        self.fire(self.s7, self.s8)
        self.live()
        RuleSettings.objects.filter(school=self.a).update(breaker_percent=25)       # 25% is not MORE than 25%
        self.assertEqual(self.go()[0].alerts_raised, 2)

    def test_breaker_one_of_eight_is_under_the_default(self):
        self.fire(self.s7)
        self.live()
        self.assertEqual(self.go()[0].status, 'ok')

    def test_breaker_default_applies_without_a_settings_row(self):
        RuleSettings.objects.filter(school=self.a).delete()
        self.fire(self.s7, self.s8)
        rule = self.starter(code='repeated_absence')
        Rule.objects.filter(pk=rule.pk).update(status='active')
        self.assertEqual(self.go()[0].status, 'breaker_tripped')

    def test_score_rule_without_a_scale_does_not_run(self):
        self.grades(self.s7, 5)
        self.live(code='low_average')
        RuleSettings.objects.filter(school=self.a).update(grade_scale_max=None)
        (run,) = self.go()
        self.assertEqual((run.status, run.alerts_raised), ('no_scale', 0))
        self.assertEqual(Alert.objects.count(), 0)

    # ---- atomicity, concurrency of the unique key ----
    def test_a_failed_hit_insert_rolls_the_alert_back(self):
        self.fire(self.s7)
        self.live()
        with mock.patch.object(RuleHit.objects, 'create', side_effect=IntegrityError('boom')):
            (run,) = self.go()
        self.assertEqual((Alert.objects.count(), RiskEvent.objects.count(), RuleHit.objects.count(), run.alerts_raised), (0, 0, 0, 0))

    def test_a_duplicate_day_hit_cannot_create_a_second_alert(self):
        self.fire(self.s7)
        self.live()
        self.go()
        with mock.patch.object(rules, '_blocked_by_cooldown', return_value=False):      # a simultaneous run that missed the cooldown
            (run,) = self.go()
        self.assertEqual((Alert.objects.count(), RuleHit.objects.count(), RiskEvent.objects.count(), run.alerts_raised), (1, 1, 1, 0))

    # ---- isolation and read-only ----
    def test_a_run_for_school_a_never_touches_school_b(self):
        self.fire(self.sb)
        for student in self.extra[:0]:
            pass
        self.live()
        b_rule = self.starter(school=self.b, code='repeated_absence', by=self.admin_b)
        Rule.objects.filter(pk=b_rule.pk).update(status='active')
        RuleSettings.objects.create(school=self.b, breaker_percent=100)
        runs = self.go()
        self.assertEqual({r.school_id for r in runs}, {self.a.pk})
        self.assertEqual(Alert.objects.filter(student=self.sb).count(), 0)
        (b_run,) = rules.run_school(self.b.pk, as_of=TODAY)
        self.assertEqual((b_run.evaluated, b_run.alerts_raised), (1, 1))
        self.assertEqual(Alert.objects.get().school_id, self.b.pk)

    def test_the_runner_writes_only_alerts_events_hits_runs_and_audit(self):
        self.fire(self.s7)
        self.live()
        before = [m.objects.count() for m in (Student, Enrollment, Attendance, Grade)]
        snapshot = list(Student.objects.order_by('pk').values_list('pk', 'school_id', 'grade', 'first_name'))
        self.go()
        self.assertEqual(before, [m.objects.count() for m in (Student, Enrollment, Attendance, Grade)])
        self.assertEqual(snapshot, list(Student.objects.order_by('pk').values_list('pk', 'school_id', 'grade', 'first_name')))

    def test_only_students_with_a_current_enrollment_are_evaluated(self):
        self.fire(self.s7)
        Enrollment.objects.filter(student=self.s7).update(status='withdrawn')
        self.live()
        (run,) = self.go()
        self.assertEqual((run.evaluated, run.alerts_raised), (7, 0))

    def test_run_school_needs_an_explicit_integer_school(self):
        for bad in (None, 'a', True, 1.5, self.a):
            with self.assertRaises(ValueError):
                rules.run_school(bad)

    # ---- audit ----
    def test_audit_system_actor_counts_only(self):
        self.fire(self.s7)
        self.live()
        AuditEvent.objects.all().delete()
        self.go()
        run_event = AuditEvent.objects.get(action='rule_run')
        self.assertEqual((run_event.username, run_event.user_id, run_event.roles, run_event.school_id), ('system', None, 'system', self.a.pk))
        self.assertEqual(run_event.detail, 'e8h1a1c0i7u0s0')
        raised = AuditEvent.objects.get(action='alert_raise')
        self.assertEqual((raised.username, raised.detail), ('system', 'repeated_absence'))
        every = ' '.join(f'{e.detail} {e.object_type} {e.object_id} {e.username}' for e in AuditEvent.objects.all())
        self.assertNotIn(self.s7.last_name + self.s7.first_name, every)

    def test_audit_actor_is_the_user_when_the_button_triggers_the_run(self):
        self.fire(self.s7)
        self.live()
        AuditEvent.objects.all().delete()
        self.go(triggered_by=self.admin)
        self.assertEqual(set(AuditEvent.objects.values_list('username', flat=True)), {'admin'})
        self.assertEqual(RuleRun.objects.get(mode='live').triggered_by_id, self.admin.pk)

    # ---- command ----
    def test_command_needs_school_when_several_exist_and_never_runs_all(self):
        self.fire(self.s7)
        self.live()
        with self.assertRaisesMessage(CommandError, 'more than one school exists'):
            call_command('run_rules', as_of=TODAY.isoformat(), stdout=StringIO())
        self.assertEqual(Alert.objects.count(), 0)
        with self.assertRaises(CommandError):
            call_command('run_rules', school='nope', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('run_rules', school='a', as_of='not-a-date', stdout=StringIO())
        out = StringIO()
        call_command('run_rules', school='a', as_of=TODAY.isoformat(), stdout=out)
        self.assertIn('alerts=1', out.getvalue())
        self.assertEqual(Alert.objects.get().school_id, self.a.pk)
        self.assertEqual(AuditEvent.objects.get(action='rule_run').username, 'system')
