"""0025 commit 1: the rule tables and what the DATABASE itself refuses (sensitive risk types, two live versions, double hits)."""
from datetime import date

from django.db import IntegrityError, transaction

from risk.loop_testing import LoopBase
from risk.models import Rule, RuleHit, RuleRun, RuleSettings


class RuleModelTests(LoopBase):
    def rule(self, **extra):
        args = dict(school=self.a, code='low_average', version=1, kind='low_average', title='t', risk_type='academic',
                    severity='yellow', clauses=[{'metric': 'avg_score'}])
        args.update(extra)
        return Rule.objects.create(**args)

    def refused(self, **extra):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.rule(**extra)

    def test_sensitive_risk_types_are_refused_by_the_database(self):
        for risk_type in ('emotional', 'family', 'social', 'motivation'):
            with self.subTest(risk_type=risk_type):
                self.refused(risk_type=risk_type)
        for risk_type in ('academic', 'attendance', 'behavioral'):
            self.rule(code=f'ok-{risk_type}', risk_type=risk_type)

    def test_one_live_version_per_code_but_many_archived(self):
        self.rule(status='active')
        self.refused(version=2, status='active')
        self.refused(version=2, status='paused')
        self.rule(version=2, status='draft')
        self.rule(version=3, status='archived')
        self.rule(school=self.b, status='active')                # another school may use the same code
        self.refused(version=1)                                  # (school, code, version) is unique

    def test_a_hit_is_unique_per_rule_student_and_day(self):
        rule = self.rule(status='active')
        alert = self.alert()
        RuleHit.objects.create(school=self.a, rule=rule, student=self.s7, alert=alert, evaluated_on=date(2026, 3, 1))
        RuleHit.objects.create(school=self.a, rule=rule, student=self.s7, alert=alert, evaluated_on=date(2026, 3, 2))
        with self.assertRaises(IntegrityError), transaction.atomic():
            RuleHit.objects.create(school=self.a, rule=rule, student=self.s7, alert=alert, evaluated_on=date(2026, 3, 1))

    def test_settings_defaults_and_breaker_range(self):
        s = RuleSettings.objects.create(school=self.a)
        self.assertEqual((s.grade_scale_max, s.breaker_percent, s.require_second_approver), (None, 15, False))
        for bad in (0, 101):
            with self.assertRaises(IntegrityError), transaction.atomic():
                RuleSettings.objects.create(school=self.b, breaker_percent=bad)

    def test_run_row_holds_counts_only(self):
        run = RuleRun.objects.create(school=self.a, rule=self.rule(), mode='live', as_of=date(2026, 3, 1), evaluated=10)
        self.assertEqual((run.status, run.hits, run.alerts_raised), ('ok', 0, 0))
        names = {f.name for f in RuleRun._meta.get_fields()}
        self.assertFalse(names & {'student', 'students', 'student_ids', 'names'})
