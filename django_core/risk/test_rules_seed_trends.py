"""0025 commit 4: starter drafts seeded per school, and the Student 360 trend tile (scoped like attendance and grades)."""
from datetime import date, timedelta
from io import StringIO
from types import SimpleNamespace as NS

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from risk import trends
from risk.models import Rule
from risk.rules_testing import RulesBase
from students.models import Attendance, Grade


class SeedTests(RulesBase):
    def test_seeds_four_drafts_idempotently_and_labelled(self):
        call_command('seed_rules', school='a', stdout=StringIO())
        call_command('seed_rules', school='a', stdout=StringIO())
        rules = Rule.objects.filter(school=self.a)
        self.assertEqual(sorted(rules.values_list('code', flat=True)), ['attendance_shift', 'grade_drop', 'low_average', 'repeated_absence'])
        self.assertEqual(set(rules.values_list('status', flat=True)), {'draft'})
        self.assertTrue(all('اعتبارسنجی‌نشده' in r.title for r in rules))
        self.assertFalse(Rule.objects.filter(school=self.b).exists())

    def test_needs_school_when_several_exist(self):
        with self.assertRaisesMessage(CommandError, 'more than one school exists'):
            call_command('seed_rules', stdout=StringIO())
        self.assertEqual(Rule.objects.count(), 0)

    def test_seeded_drafts_are_never_active_and_low_average_needs_the_scale_to_activate(self):
        from risk import lifecycle
        from risk.models import RuleSettings
        call_command('seed_rules', school='a', stdout=StringIO())
        self.assertFalse(Rule.objects.filter(status='active').exists())
        low = Rule.objects.get(school=self.a, code='low_average')
        RuleSettings.objects.filter(school=self.a).update(grade_scale_max=None)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            lifecycle.simulate(low, self.admin)


class TrendFunctionTests(SimpleTestCase):
    today = date(2026, 3, 1)

    def test_weekly_absence_shows_none_below_three_records(self):
        rows = [NS(date=self.today - timedelta(days=d), status='absent' if d < 2 else 'present') for d in range(0, 3)]
        weeks = trends.weekly_absence(rows, self.today)
        self.assertEqual(len(weeks), 12)
        self.assertAlmostEqual(weeks[-1][1], 100 * 2 / 3)
        self.assertTrue(all(w[1] is None for w in weeks[:-1]))

    def test_subject_periods(self):
        rows = [NS(date=self.today - timedelta(days=d), score=s, subject='math') for d, s in ((1, 10), (3, 14), (50, 16), (200, 1))]
        self.assertEqual(trends.subject_period_averages(rows, self.today), {'math': [None, 16, 12]})


class TrendTileTests(RulesBase):
    def test_admin_and_lead_see_the_tile_parent_does_not_and_a_hidden_student_is_404(self):
        today = timezone.localdate()
        for d in range(1, 6):
            Attendance.objects.create(student=self.s7, date=today - timedelta(days=d), status='absent')
        Grade.objects.create(student=self.s7, subject='math', exam_type='quiz', score=9, date=today - timedelta(days=2))
        url = reverse('dashboard:student_360', args=[self.s7.pk])
        for user in (self.admin, self.lead):
            self.client.force_login(user)
            page = self.client.get(url)
            self.assertContains(page, 'روند (محاسبهٔ خودکار')
            self.assertEqual(len(page.context['trend_weeks']), 12)
        self.client.force_login(self.parent)
        page = self.client.get(url)
        self.assertNotContains(page, 'روند (محاسبهٔ خودکار')
        self.assertNotIn('trend_weeks', page.context)
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.lead8)
        self.assertEqual(self.client.get(url).status_code, 404)
