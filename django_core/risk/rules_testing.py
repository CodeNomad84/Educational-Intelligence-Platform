"""Shared fixture for the rule-engine tests (not a test module). Synthetic data only."""
from datetime import date, timedelta

from risk import lifecycle, rules
from risk.loop_testing import LoopBase
from risk.models import Rule, RuleSettings
from students.models import Attendance, Grade

TODAY = date(2026, 3, 1)


class RulesBase(LoopBase):
    def setUp(self):
        super().setUp()
        RuleSettings.objects.create(school=self.a, grade_scale_max=20)
        self.extra = [self.student(f'Kid{n}', self.c7, 7) for n in range(6)]       # 8 students in school A (s7, s8 + 6)

    def absent_streak(self, student, days=range(1, 8), status='absent'):
        for d in days:
            Attendance.objects.create(student=student, date=TODAY - timedelta(days=d), status=status)

    def present_history(self, student, days=range(31, 80)):
        for d in days:
            Attendance.objects.create(student=student, date=TODAY - timedelta(days=d), status='present')

    def grades(self, student, score, days=(2, 5, 9), subject='math'):
        for d in days:
            Grade.objects.create(student=student, subject=subject, exam_type='quiz', score=score, date=TODAY - timedelta(days=d))

    def starter(self, school=None, code='attendance_shift', by=None, **over):
        spec = dict(rules.STARTERS[code])
        spec.update(over)
        return lifecycle.create(by or self.admin, (school or self.a).pk, code=code, kind=code, cooldown_days=14, **spec)

    def live(self, code='repeated_absence', **over):
        rule = self.starter(code=code, **over)
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        return lifecycle.approve(rule, self.admin)
