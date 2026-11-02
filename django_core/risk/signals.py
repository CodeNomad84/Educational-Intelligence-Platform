"""Derived analytics (0025, stage 3): pure metric functions, nothing stored, no database access.

Each function takes rows the caller already fetched (objects with ``date`` and ``status`` / ``score`` / ``subject``) and returns a
``Signal(value, records, detail)`` or ``None`` when there are fewer than ``min_records`` records (never a guess). Windows are in
days relative to ``today``: the recent window is ``(today - window, today]``, the baseline is the window of ``baseline`` days that
ends where the recent one starts. The maths is ported from ``demo_intel/engine.py`` (the specification); parity tests pin it.
Callers decide who may see the rows; this module has no access rules.
"""
from collections import defaultdict, namedtuple
from datetime import timedelta

Signal = namedtuple('Signal', 'value records detail')

OPS = {'>=': lambda a, b: a >= b, '>': lambda a, b: a > b, '<=': lambda a, b: a <= b, '<': lambda a, b: a < b}


def _window(rows, today, start_offset, end_offset=0):
    """Rows with ``today - start_offset < date <= today - end_offset``."""
    lo, hi = today - timedelta(days=start_offset), today - timedelta(days=end_offset)
    return [r for r in rows if lo < r.date <= hi]


def _avg(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _rate(rows):
    return 100.0 * sum(r.status == 'absent' for r in rows) / len(rows)


def absence_rate(attendances, today, window_days, min_records=5):
    """Percent of absent records in the recent window."""
    rows = _window(attendances, today, window_days)
    if not rows or len(rows) < min_records:
        return None
    return Signal(_rate(rows), len(rows), {})


def absence_shift_pp(attendances, today, window_days, baseline_days, min_records=5):
    """Absence rate of the recent window minus that of the baseline window, in percentage points."""
    recent = _window(attendances, today, window_days)
    base = _window(attendances, today, window_days + baseline_days, window_days)
    if not recent or not base or len(recent) < min_records or len(base) < min_records:
        return None
    r, b = _rate(recent), _rate(base)
    return Signal(r - b, len(recent) + len(base), {'recent_rate': r, 'baseline_rate': b,
                                                   'recent_records': len(recent), 'baseline_records': len(base)})


def late_count(attendances, today, window_days, min_records=1):
    rows = _window(attendances, today, window_days)
    if len(rows) < min_records:
        return None
    return Signal(sum(r.status == 'late' for r in rows), len(rows), {})


def absent_days(attendances, today, window_days, min_records=5):
    rows = _window(attendances, today, window_days)
    if len(rows) < min_records:
        return None
    return Signal(sum(r.status == 'absent' for r in rows), len(rows), {})


def max_consecutive_absences(attendances, today, window_days, min_records=5):
    """Longest run of absent records in date order (consecutive attendance records, so weekends do not break a run)."""
    rows = sorted(_window(attendances, today, window_days), key=lambda r: r.date)
    if len(rows) < min_records:
        return None
    best = run = 0
    for r in rows:
        run = run + 1 if r.status == 'absent' else 0
        best = max(best, run)
    return Signal(best, len(rows), {})


def avg_score(grades, today, window_days, min_records=3):
    rows = _window(grades, today, window_days)
    if not rows or len(rows) < min_records:
        return None
    return Signal(_avg(g.score for g in rows), len(rows), {})


def grades_count(grades, today, window_days, min_records=0):
    rows = _window(grades, today, window_days)
    if len(rows) < min_records:
        return None
    return Signal(len(rows), len(rows), {})


def subject_drop(grades, today, window_days, baseline_days, min_records=2, max_subjects=2):
    """Largest drop of a subject's recent average below its earlier average. ``detail['subjects']`` lists the ``max_subjects``
    biggest drops as ``(subject, earlier_avg, recent_avg, drop)``. A subject needs ``min_records`` grades in BOTH windows."""
    recent = defaultdict(list)
    earlier = defaultdict(list)
    for g in _window(grades, today, window_days):
        recent[g.subject].append(g.score)
    for g in _window(grades, today, window_days + baseline_days, window_days):
        earlier[g.subject].append(g.score)
    drops = []
    for subject, scores in recent.items():
        if subject in earlier and len(scores) >= min_records and len(earlier[subject]) >= min_records:
            e, c = _avg(earlier[subject]), _avg(scores)
            drops.append((e - c, subject, e, c))
    if not drops:
        return None
    drops.sort(reverse=True)
    top = drops[:max_subjects]
    return Signal(top[0][0], sum(len(recent[s]) + len(earlier[s]) for _d, s, _e, _c in top),
                  {'subjects': [(s, e, c, d) for d, s, e, c in top]})


# The closed catalog: metric name -> (function, source rows, takes baseline_days). Rules may use nothing else.
def concern_count(concerns, today, window_days, min_records=0):
    """Number of staff 'concern' behavior entries in the recent window (P6, decision 50). Counts only: the entries' text and
    category are never read (the loader selects the date alone). ``concerns``: rows with a ``date``."""
    rows = _window(concerns, today, window_days)
    if len(rows) < min_records:
        return None
    return Signal(len(rows), len(rows), {})


METRICS = {
    'absence_rate': (absence_rate, 'attendance', False),
    'absence_shift_pp': (absence_shift_pp, 'attendance', True),
    'late_count': (late_count, 'attendance', False),
    'absent_days': (absent_days, 'attendance', False),
    'max_consecutive_absences': (max_consecutive_absences, 'attendance', False),
    'avg_score': (avg_score, 'grade', False),
    'grades_count': (grades_count, 'grade', False),
    'subject_drop': (subject_drop, 'grade', True),
    'concern_count': (concern_count, 'behavior', False),
}


def evaluate_metric(name, attendances, grades, today, *, window_days, baseline_days=None, min_records=None, concerns=()):
    """Run one catalog metric. ``None`` = not enough records."""
    func, source, takes_baseline = METRICS[name]
    kwargs = {'window_days': window_days}
    if takes_baseline:
        kwargs['baseline_days'] = baseline_days
    if min_records is not None:
        kwargs['min_records'] = min_records
    rows = {'attendance': attendances, 'grade': grades, 'behavior': concerns}[source]
    return func(rows, today, **kwargs)
