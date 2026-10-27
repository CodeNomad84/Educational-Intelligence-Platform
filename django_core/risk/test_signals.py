"""0025 stage 3: the pure metric functions (windows, minimum-record guards, None below the minimum). No database."""
from datetime import date, timedelta
from types import SimpleNamespace as NS

from django.test import SimpleTestCase

from risk import signals as S

TODAY = date(2026, 3, 1)


def att(days_ago, status):
    return NS(date=TODAY - timedelta(days=days_ago), status=status)


def grade(days_ago, score, subject='math'):
    return NS(date=TODAY - timedelta(days=days_ago), score=score, subject=subject)


class AttendanceMetricTests(SimpleTestCase):
    def test_window_is_open_at_the_start_and_closed_at_today(self):
        rows = [att(0, 'absent'), att(29, 'absent'), att(30, 'absent')] + [att(i, 'present') for i in range(1, 6)]
        sig = S.absence_rate(rows, TODAY, 30, min_records=1)
        self.assertEqual(sig.records, 7)                       # day 0 and day 29 inside, day 30 outside
        self.assertAlmostEqual(sig.value, 100 * 2 / 7)

    def test_below_minimum_records_is_none_not_zero(self):
        rows = [att(i, 'absent') for i in range(4)]
        self.assertIsNone(S.absence_rate(rows, TODAY, 30, min_records=5))
        self.assertIsNone(S.absence_rate([], TODAY, 30, min_records=0))
        self.assertIsNotNone(S.absence_rate(rows, TODAY, 30, min_records=4))

    def test_shift_needs_minimum_in_both_windows(self):
        recent = [att(i, 'absent') for i in range(1, 6)]
        base = [att(30 + i, 'present') for i in range(1, 6)]
        sig = S.absence_shift_pp(recent + base, TODAY, 30, 60)
        self.assertAlmostEqual(sig.value, 100.0)
        self.assertEqual(sig.detail['baseline_records'], 5)
        self.assertIsNone(S.absence_shift_pp(recent + base[:4], TODAY, 30, 60))
        self.assertIsNone(S.absence_shift_pp(recent, TODAY, 30, 60))

    def test_baseline_window_ends_where_recent_starts(self):
        rows = [att(30, 'absent'), att(31, 'absent'), att(89, 'absent'), att(90, 'absent'), att(91, 'absent')]
        sig = S.absence_shift_pp(rows + [att(i, 'present') for i in range(1, 6)], TODAY, 30, 60, min_records=1)
        self.assertEqual(sig.detail['baseline_records'], 3)    # days 30, 31, 89 inside; 90 and 91 outside (lower bound is open)

    def test_late_absent_days_and_consecutive(self):
        rows = [att(1, 'late'), att(2, 'late'), att(3, 'absent'), att(4, 'absent'), att(5, 'present'), att(6, 'absent'), att(7, 'present')]
        self.assertEqual(S.late_count(rows, TODAY, 14).value, 2)
        self.assertEqual(S.absent_days(rows, TODAY, 14).value, 3)
        self.assertEqual(S.max_consecutive_absences(rows, TODAY, 14).value, 2)
        self.assertIsNone(S.absent_days(rows[:3], TODAY, 14))


class GradeMetricTests(SimpleTestCase):
    def test_average_and_guard(self):
        rows = [grade(1, 10), grade(2, 12), grade(3, 14)]
        self.assertEqual(S.avg_score(rows, TODAY, 45).value, 12)
        self.assertIsNone(S.avg_score(rows[:2], TODAY, 45))

    def test_subject_drop_needs_both_windows_and_limits_subjects(self):
        rows = []
        for subject, (old, new) in {'math': (18, 12), 'physics': (16, 12), 'art': (15, 14)}.items():
            rows += [grade(60, old, subject), grade(70, old, subject), grade(5, new, subject), grade(10, new, subject)]
        rows += [grade(5, 5, 'only_recent'), grade(6, 5, 'only_recent')]
        sig = S.subject_drop(rows, TODAY, 45, 75)
        self.assertEqual(sig.value, 6)
        self.assertEqual([s[0] for s in sig.detail['subjects']], ['math', 'physics'])   # at most 2, biggest first
        self.assertIsNone(S.subject_drop([grade(60, 18), grade(5, 10)], TODAY, 45, 75))  # 1 grade per window < 2

    def test_catalog_is_closed(self):
        self.assertEqual(set(S.METRICS), {'absence_rate', 'absence_shift_pp', 'late_count', 'absent_days',
                                          'max_consecutive_absences', 'avg_score', 'grades_count', 'subject_drop'})
        with self.assertRaises(KeyError):
            S.evaluate_metric('eval', [], [], TODAY, window_days=1)
