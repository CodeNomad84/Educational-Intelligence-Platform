"""Support levels (MTSS-style tiers, decision pack 0028 P5-2). DERIVED on read from the alerts and plans the CALLER already
scoped (``reviewable_alerts`` / ``visible_plans`` of the viewing user); nothing is stored, typed by hand or attached to the
student, and every display carries ``NOTE``. The rule is deterministic and lives only here:

* level 3 (intensive): two or more open plans, or an open plan together with an unreviewed orange/red alert;
* level 2 (targeted): one open plan, an unreviewed orange/red alert, or two or more unreviewed alerts;
* level 1 (universal): everyone else (no entry is returned).

"Open plan" = planned or active. "Unreviewed" = alert status ``new``.
"""
from collections import defaultdict

from django.db.models import Count

from risk.models import Alert

from .models import InterventionPlan

UNIVERSAL, TARGETED, INTENSIVE = 1, 2, 3
LABELS = {UNIVERSAL: 'سطح ۱ · همگانی', TARGETED: 'سطح ۲ · هدفمند', INTENSIVE: 'سطح ۳ · فشرده'}
NOTE = 'سطح حمایت از هشدارها و برنامه‌های باز محاسبه می‌شود؛ برچسب یا تشخیص نیست.'
OPEN_PLAN = (InterventionPlan.PLANNED, InterventionPlan.ACTIVE)
URGENT = ('orange', 'red')


def level_for(open_plans, new_alerts, urgent_alerts):
    if open_plans >= 2 or (open_plans >= 1 and urgent_alerts >= 1):
        return INTENSIVE
    if open_plans == 1 or urgent_alerts >= 1 or new_alerts >= 2:
        return TARGETED
    return UNIVERSAL


def support_levels(alerts, plans):
    """``{student_id: {'level', 'label', 'open_plans', 'new_alerts', 'urgent_alerts'}}`` for students at level 2 or 3."""
    counts = defaultdict(lambda: {'open_plans': 0, 'new_alerts': 0, 'urgent_alerts': 0})
    for row in plans.filter(status__in=OPEN_PLAN).order_by().values('student_id').annotate(n=Count('pk')):
        counts[row['student_id']]['open_plans'] = row['n']
    for row in alerts.filter(status=Alert.NEW).order_by().values('student_id', 'risk_event__severity').annotate(n=Count('pk')):
        c = counts[row['student_id']]
        c['new_alerts'] += row['n']
        if row['risk_event__severity'] in URGENT:
            c['urgent_alerts'] += row['n']
    out = {}
    for student_id, c in counts.items():
        level = level_for(**c)
        if level > UNIVERSAL:
            out[student_id] = {'level': level, 'label': LABELS[level], **c}
    return out


def levels_for_user(user):
    """Support levels as the user may see them: the review scope only (SchoolAdmin, Grade Lead, Counselor); a Teacher or
    Parent gets ``{}`` because ``reviewable_alerts`` and ``visible_plans`` are empty for them."""
    from students.access import reviewable_alerts, visible_plans

    return support_levels(reviewable_alerts(user), visible_plans(user))


def reviewable_alerts_and_plans_level(user, student):
    """One student's level as the user may see it (None = level 1 or no review scope)."""
    from students.access import reviewable_alerts, visible_plans

    return support_levels(reviewable_alerts(user).filter(student=student), visible_plans(user).filter(student=student)).get(student.pk)
