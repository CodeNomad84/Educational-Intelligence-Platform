"""0025 commit 2: clause validation, evaluation, simulation (aggregate only, nothing written) and the system read path."""
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db.models import Count

from risk import lifecycle, rules
from risk.models import Rule, RuleHit, RuleSettings
from risk.rules_testing import TODAY, RulesBase
from risk.models import Alert, RiskEvent
from students import access
from students.models import Enrollment


class ValidationTests(RulesBase):
    clause = {'metric': 'absent_days', 'op': '>=', 'threshold': 3, 'window_days': 14, 'min_records': 5}

    def bad(self, clauses=None, connective='all', **kw):
        with self.assertRaises(ValidationError):
            rules.validate_clauses(clauses if clauses is not None else [self.clause], connective, school_id=self.a.pk, **kw)

    def test_a_good_clause_is_accepted_and_normalized(self):
        self.assertEqual(rules.validate_clauses([self.clause], 'all', school_id=self.a.pk), [self.clause])

    def test_unknown_metric_operator_keys_and_shape_are_refused(self):
        for patch in ({'metric': 'eval'}, {'op': '=='}, {'threshold': 'x'}, {'threshold': float('inf')}, {'threshold': True},
                      {'window_days': 0}, {'window_days': 366}, {'window_days': '14'}, {'min_records': -1}, {'extra': 1},
                      {'baseline_days': 5}):
            with self.subTest(patch=patch):
                self.bad([{**self.clause, **patch}])
        self.bad([{k: v for k, v in self.clause.items() if k != 'op'}])
        self.bad('absent_days')
        self.bad([])
        self.bad([self.clause] * 5)
        self.bad(connective='xor')
        self.bad([{'metric': 'absence_shift_pp', 'op': '>=', 'threshold': 10, 'window_days': 30}])    # baseline required

    def test_score_rule_needs_the_school_scale_fail_closed(self):
        clause = rules.STARTERS['low_average']['clauses']
        RuleSettings.objects.filter(school=self.a).update(grade_scale_max=None)
        self.bad(clause)
        self.bad(clause, settings=None)
        RuleSettings.objects.filter(school=self.a).delete()
        self.bad(clause)                                                                 # no settings row at all
        RuleSettings.objects.create(school=self.a, grade_scale_max=10)
        self.bad([{**clause[0], 'threshold': 12}])                                       # above the scale
        self.assertTrue(rules.validate_clauses([{**clause[0], 'threshold': 6}], 'all', school_id=self.a.pk))

    def test_risk_types_emotional_and_family_are_refused_in_validation(self):
        for risk_type in ('emotional', 'family', 'social', 'motivation', ''):
            with self.assertRaises(ValidationError):
                rules.validate_rule_fields(kind='low_average', risk_type=risk_type, severity='yellow', cooldown_days=14)
            with self.assertRaises(ValidationError):
                self.starter(code='low_average', risk_type=risk_type)
        for severity in ('red', 'green', ''):
            with self.assertRaises(ValidationError):
                rules.validate_rule_fields(kind='low_average', risk_type='academic', severity=severity, cooldown_days=14)

    def test_starters_all_validate(self):
        for code in rules.STARTERS:
            self.assertTrue(self.starter(code=code))


class EvaluationTests(RulesBase):
    def verdict(self, rule, student):
        students, att, grades = rules.load_school(self.a.pk, TODAY, TODAY)
        return rules.evaluate_rule(rule, students, att, grades, TODAY)[student.pk]

    def test_repeated_absence_fires_with_evidence_and_insufficient_data_never_fires(self):
        rule = self.starter(code='repeated_absence')
        self.absent_streak(self.s7)
        verdict, evidence = self.verdict(rule, self.s7)
        self.assertEqual(verdict, 'fired')
        self.assertEqual({e['metric'] for e in evidence}, {'absent_days', 'max_consecutive_absences'})
        self.assertEqual(self.verdict(rule, self.extra[0]), ('insufficient', None))        # no records at all
        self.absent_streak(self.extra[1], days=range(1, 4))                                 # 3 records < 5: never a guess
        self.assertEqual(self.verdict(rule, self.extra[1]), ('insufficient', None))

    def test_a_student_with_enough_records_and_no_problem_is_no(self):
        rule = self.starter(code='repeated_absence')
        self.absent_streak(self.s7, status='present')
        self.assertEqual(self.verdict(rule, self.s7), ('no', None))

    def test_all_and_any_connectives(self):
        clauses = [{'metric': 'absent_days', 'op': '>=', 'threshold': 3, 'window_days': 14, 'min_records': 5},
                   {'metric': 'late_count', 'op': '>=', 'threshold': 99, 'window_days': 14, 'min_records': 1}]
        self.absent_streak(self.s7)
        any_rule = self.starter(code='repeated_absence', clauses=clauses, connective='any')
        all_rule = self.starter(code='attendance_shift', clauses=clauses, connective='all')
        self.assertEqual(self.verdict(any_rule, self.s7)[0], 'fired')
        self.assertEqual(self.verdict(all_rule, self.s7)[0], 'no')

    def test_low_average_and_grade_drop(self):
        low = self.starter(code='low_average')
        self.grades(self.s7, 8)
        self.assertEqual(self.verdict(low, self.s7)[0], 'fired')
        self.grades(self.s8, 15)
        self.assertEqual(self.verdict(low, self.s8)[0], 'no')
        self.grades(self.extra[0], 18, days=(60, 70, 80))
        self.grades(self.extra[0], 10, days=(3, 8))
        verdict, evidence = self.verdict(self.starter(code='grade_drop'), self.extra[0])
        self.assertEqual(verdict, 'fired')
        self.assertEqual(evidence[0]['detail']['subjects'][0][0], 'math')

    def test_window_boundary_is_exact(self):
        rule = self.starter(code='repeated_absence')
        self.absent_streak(self.s7, days=[13, 14, 15, 16, 17, 20, 21])         # only days 13 and 14 inside (today-14 is inside)
        self.assertEqual(self.verdict(rule, self.s7)[0], 'insufficient')       # 1-2 in-window records: below min 5 -> never a hit


class SimulationTests(RulesBase):
    def test_simulation_counts_withhold_small_groups_and_write_nothing_but_a_run(self):
        for student in [self.s7, *self.extra[:5]]:                              # 6 students fire
            self.absent_streak(student)
        rule = self.starter(code='repeated_absence')
        rule, result = lifecycle.simulate(rule, self.admin, as_of=TODAY)
        self.assertEqual(rule.status, 'simulated')
        self.assertEqual(result[-1]['fired'], 6)
        self.assertEqual(result[-1]['by_grade'], {7: 6})
        self.assertTrue(all(w['fired'] is None for w in result[:-1]))            # earlier weeks: fewer than 5 -> withheld
        self.assertEqual((Alert.objects.count(), RuleHit.objects.count(), RiskEvent.objects.count()), (0, 0, 0))
        run = rule.runs.get()
        self.assertEqual((run.mode, run.evaluated, run.hits), ('simulation', 8, 6))

    def test_groups_under_five_are_withheld_even_per_grade(self):
        for student in [self.s7, *self.extra[:4]]:                              # 5 in grade 7 ...
            self.absent_streak(student)
        self.absent_streak(self.s8)                                             # ... and 1 in grade 8
        _rule, result = lifecycle.simulate(self.starter(code='repeated_absence'), self.admin, as_of=TODAY)
        self.assertEqual(result[-1]['fired'], 6)
        self.assertEqual(result[-1]['by_grade'], {7: 5, 8: None})
        self.assertNotIn(self.s7.last_name + self.s7.first_name, str(result))

    def test_simulation_never_reads_another_school(self):
        for student in (self.sb,):
            self.absent_streak(student)
        _rule, result = lifecycle.simulate(self.starter(code='repeated_absence'), self.admin, as_of=TODAY)
        self.assertEqual(result[-1]['evaluated'], 8)                             # school B's student is not even counted
        self.assertIsNone(result[-1]['fired'])


class SystemScopeTests(RulesBase):
    def test_requires_one_explicit_school_id(self):
        for bad in (None, 0, -1, 'a', True, 1.5, [self.a.pk]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                access.system_scope_students(bad)
        self.assertEqual(set(access.system_scope_students(self.a).values_list('pk', flat=True)),
                         {self.s7.pk, self.s8.pk, *[s.pk for s in self.extra]})
        self.assertEqual(set(access.system_scope_students(self.b.pk).values_list('pk', flat=True)), {self.sb.pk})

    def test_only_students_with_a_current_enrollment(self):
        Enrollment.objects.filter(student=self.s7).update(status='withdrawn')
        self.assertNotIn(self.s7.pk, access.system_scope_students(self.a).values_list('pk', flat=True))
        Enrollment.objects.filter(student=self.s8).update(started_on=TODAY - timedelta(days=30), ended_on=TODAY)
        self.assertNotIn(self.s8.pk, access.system_scope_students(self.a).values_list('pk', flat=True))
        stray = self.student('Stray', self.c7, 7)
        Enrollment.objects.filter(student=stray).delete()
        self.assertNotIn(stray.pk, access.system_scope_students(self.a).values_list('pk', flat=True))

    def test_a_student_moved_to_another_school_is_not_in_the_old_school(self):
        type(self.sb).objects.filter(pk=self.sb.pk).update(school=self.a)         # inconsistent row: school A, enrollment in B
        self.assertNotIn(self.sb.pk, access.system_scope_students(self.a).values_list('pk', flat=True))

    def test_attendance_and_grades_are_the_scope_students_rows_only(self):
        self.absent_streak(self.s7)
        self.absent_streak(self.sb)
        self.grades(self.s7, 10)
        self.grades(self.sb, 10)
        self.assertEqual(set(access.system_scope_attendance(self.a).values_list('student_id', flat=True)), {self.s7.pk})
        self.assertEqual(set(access.system_scope_grades(self.b).values_list('student_id', flat=True)), {self.sb.pk})

    def test_only_the_rules_module_imports_the_system_path(self):
        root = Path(__file__).resolve().parents[1]
        users = []
        for path in root.rglob('*.py'):
            if '.venv' in path.parts or 'migrations' in path.parts or path.name.startswith('test') or path.name == 'rules_testing.py':
                continue
            text = path.read_text(encoding='utf-8')
            if 'system_scope_' in text:
                users.append(str(path.relative_to(root)))
        self.assertEqual(sorted(users), ['risk/rules.py', 'students/access.py'])
