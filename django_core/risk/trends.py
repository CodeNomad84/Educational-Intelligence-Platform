"""Student 360 trend tile (0025 stage 3): derived from rows the CALLER already filtered through the user's ``visible_*`` helpers.
Nothing is stored. Weeks or periods with too few records show ``None`` (never a guess)."""
from collections import defaultdict
from datetime import timedelta

MIN_WEEK_RECORDS = 3
PERIOD_DAYS = 45
PERIODS = 3


def weekly_absence(attendances, today, weeks=12):
    """Oldest first: ``[(week_end_date, absence_rate_percent_or_None, records)]`` for the last ``weeks`` weeks (7 days each)."""
    rows = list(attendances)
    out = []
    for n in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * n)
        week = [r for r in rows if end - timedelta(days=7) < r.date <= end]
        rate = 100.0 * sum(r.status == 'absent' for r in week) / len(week) if len(week) >= MIN_WEEK_RECORDS else None
        out.append((end, rate, len(week)))
    return out


def subject_period_averages(grades, today):
    """``{subject: [avg_or_None per period, oldest first]}`` over ``PERIODS`` periods of ``PERIOD_DAYS`` days; one grade is enough
    for a period to show an average (the count is not shown), a subject with no grade at all is absent."""
    buckets = defaultdict(lambda: [[] for _ in range(PERIODS)])
    for g in grades:
        age = (today - g.date).days
        if 0 <= age < PERIOD_DAYS * PERIODS:
            buckets[g.subject][PERIODS - 1 - age // PERIOD_DAYS].append(g.score)
    return {subject: [sum(v) / len(v) if v else None for v in parts] for subject, parts in sorted(buckets.items())}
