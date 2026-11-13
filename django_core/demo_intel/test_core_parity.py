"""0025: parity between the demo engine's maths (the specification) and ``risk/signals.py`` on the same synthetic rows.
Runs under demo settings, where both exist. A drift in either copy fails here."""
import random
from datetime import date, timedelta
from types import SimpleNamespace as NS

from django.test import SimpleTestCase

from demo_intel import engine
from risk import signals as S

TODAY = date(2026, 3, 1)


def rows(seed):
    rnd = random.Random(seed)
    atts = [NS(date=TODAY - timedelta(days=d), status=rnd.choice(['present'] * 5 + ['absent', 'late', 'sick']))
            for d in range(0, 100) if rnd.random() < 0.7]
    grades = [NS(date=TODAY - timedelta(days=d), score=round(rnd.uniform(5, 20), 1), subject=rnd.choice(['math', 'physics', 'art']))
              for d in range(0, 130) if rnd.random() < 0.3]
    return atts, grades


class ParityTests(SimpleTestCase):
    def test_numbers_match_the_demo_engine_on_many_synthetic_students(self):
        compared = 0
        for seed in range(150):
            atts, grades = rows(seed)
            res = engine._analyze(NS(id=seed), atts, grades, [], [], TODAY)
            m = res['metrics']
            shift = S.absence_shift_pp(atts, TODAY, 30, 60)
            if m['absence_recent'] is not None and m['absence_baseline'] is not None \
                    and m['attendance_records_recent'] >= 5 and shift is not None:
                self.assertAlmostEqual(shift.value, m['absence_recent'] - m['absence_baseline'], msg=seed)
                compared += 1
            self.assertEqual(S.late_count(atts, TODAY, 30).value, m['lates_recent'], seed)
            avg = S.avg_score(grades, TODAY, 45, min_records=1)
            self.assertEqual(avg.value if avg else None, m['avg_recent'], seed)
            low = S.avg_score(grades, TODAY, 45)                       # min 3 grades, as in the demo
            self.assertEqual(any(r['rule'] == 'low_average' for r in res['reasons']), bool(low and low.value < 12), seed)
            drop = S.subject_drop(grades, TODAY, 45, 75, min_records=1)
            demo_drops = [r for r in res['reasons'] if r['rule'] == 'subject_drop']
            expected = [x for x in (drop.detail['subjects'] if drop else []) if x[3] >= 3.0]    # the demo filters, then takes 2
            self.assertEqual(len(demo_drops), len(expected), seed)
            shift_fired = shift is not None and shift.value >= 10
            self.assertEqual(any(r['rule'] == 'attendance_shift' for r in res['reasons']), shift_fired, seed)
        self.assertGreater(compared, 50)
