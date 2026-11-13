"""Principal dashboard (decision pack 0028 P5-1): one school page for the SchoolAdmin. Everything is computed on read from the
viewing user's own scopes (``visible_students`` / ``visible_attendances`` / ``visible_grades`` / ``reviewable_alerts`` /
``visible_plans``), restricted to the school chosen among the user's memberships. No alert or plan TEXT is read here: counts,
types, statuses and dates only. Rates and averages over fewer than ``MIN_GROUP`` students are withheld (``None``)."""
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Avg, Count
from django.shortcuts import render
from django.utils import timezone

from interventions.models import InterventionFollowUp, InterventionPlan
from interventions.reeval import due_for_reevaluation
from interventions.support import INTENSIVE, NOTE, OPEN_PLAN, TARGETED, support_levels
from risk.models import Alert, RiskEvent, RuleHit
from risk.rules import MIN_GROUP
from schools import audit
from schools.models import AcademicYear, School
from schools.vocabulary import SUBJECT_CHOICES
from students.access import reviewable_alerts, visible_attendances, visible_grades, visible_plans, visible_students

RECENT_DAYS = 30            # attendance window (and the one before it for the change)
GRADE_DAYS = 45             # grade window (and the one before it for the change)
WEEKS = 12                  # attendance trend
STALE_DAYS = 14             # an active plan without a follow-up for this long "needs a follow-up"
ATTENTION_ROWS = 12
PRESENT = ('present', 'late')


def _rate(statuses):
    """Share of recorded days the student was in school (present or late); None without records."""
    return round(100 * sum(1 for s in statuses if s in PRESENT) / len(statuses), 1) if statuses else None


def _withheld(value, n):
    return value if n >= MIN_GROUP else None


def principal_overview(user, school, today):
    students = visible_students(user).filter(school=school, full_tier=True)
    rows = list(students.select_related('school_class').order_by('grade', 'class_name', 'last_name', 'first_name'))
    by_id = {s.pk: s for s in rows}
    total = len(rows)
    attendances = visible_attendances(user).filter(student__in=students)
    grades = visible_grades(user).filter(student__in=students)
    alerts = reviewable_alerts(user).filter(school=school)
    plans = visible_plans(user).filter(school=school)

    # attendance: last 30 days vs the 30 before; weekly trend
    att = list(attendances.filter(date__gt=today - timedelta(days=WEEKS * 7), date__lte=today)
               .values_list('student_id', 'date', 'status'))
    recent = [r for r in att if r[1] > today - timedelta(days=RECENT_DAYS)]
    before = [r[2] for r in att if today - timedelta(days=2 * RECENT_DAYS) < r[1] <= today - timedelta(days=RECENT_DAYS)]
    per_student = defaultdict(list)
    for sid, _day, status in recent:
        per_student[sid].append(status)
    weekly = []
    for n in range(WEEKS - 1, -1, -1):
        end = today - timedelta(days=7 * n)
        week = [r for r in att if end - timedelta(days=7) < r[1] <= end]
        weekly.append((end.isoformat(), _rate([r[2] for r in week]) if len({r[0] for r in week}) >= MIN_GROUP else None))

    # grades: last 45 days vs the 45 before; per subject; monthly trend
    g_recent = grades.filter(date__gt=today - timedelta(days=GRADE_DAYS), date__lte=today)
    g_before = grades.filter(date__gt=today - timedelta(days=2 * GRADE_DAYS), date__lte=today - timedelta(days=GRADE_DAYS))
    avg_recent, avg_before = g_recent.aggregate(a=Avg('score'))['a'], g_before.aggregate(a=Avg('score'))['a']
    student_avg = {r['student_id']: r['a'] for r in g_recent.values('student_id').annotate(a=Avg('score'))}
    labels = dict(SUBJECT_CHOICES)
    subjects = [{'label': labels.get(r['subject'], r['subject']), 'average': round(r['a'], 1)}
                for r in g_recent.values('subject').annotate(a=Avg('score'), n=Count('student', distinct=True)).order_by('subject')
                if r['n'] >= MIN_GROUP]
    monthly = []
    for n in range(5, -1, -1):
        end = today - timedelta(days=30 * n)
        m = grades.filter(date__gt=end - timedelta(days=30), date__lte=end).aggregate(a=Avg('score'), c=Count('student', distinct=True))
        monthly.append((end.isoformat(), round(m['a'], 2) if m['a'] is not None and m['c'] >= MIN_GROUP else None))

    # support levels, alerts, plans
    levels = {sid: v for sid, v in support_levels(alerts, plans).items() if sid in by_id}
    level_counts = Counter(v['level'] for v in levels.values())
    new_alerts = alerts.filter(status=Alert.NEW)
    type_labels = dict(RiskEvent.RiskType.choices)
    reviewed = alerts.filter(reviewed_at__date__gt=today - timedelta(days=RECENT_DAYS))
    open_plans = plans.filter(status__in=OPEN_PLAN)
    followed = set(InterventionFollowUp.objects.filter(plan__in=open_plans, followup_date__gt=today - timedelta(days=STALE_DAYS))
                   .values_list('plan_id', flat=True))
    stale = (open_plans.filter(status=InterventionPlan.ACTIVE, start_date__lte=today - timedelta(days=STALE_DAYS))
             .exclude(pk__in=followed).count())
    outcomes = Counter(plans.filter(status=InterventionPlan.COMPLETED).values_list('outcome', flat=True))
    completed = sum(outcomes.values())
    outcome_labels = dict(InterventionPlan.OUTCOME_CHOICES)

    attention = []
    for sid, info in sorted(levels.items(), key=lambda kv: (-kv[1]['level'], -kv[1]['urgent_alerts'], -kv[1]['open_plans'])):
        mine = per_student.get(sid, [])
        attention.append({'student': by_id[sid], **info, 'attendance': _rate(mine) if len(mine) >= 5 else None,
                          'average': round(student_avg[sid], 1) if sid in student_avg else None})

    classes = defaultdict(list)
    for s in rows:
        classes[(s.grade or 0, s.school_class.title if s.school_class_id else (s.class_name or '—'))].append(s.pk)
    class_rows = []
    for (grade, title), ids in sorted(classes.items()):
        avgs = [student_avg[i] for i in ids if i in student_avg]
        class_rows.append({
            'grade': grade, 'title': title, 'students': len(ids),
            'attendance': _withheld(_rate([st for i in ids for st in per_student.get(i, [])]), len(ids)),
            'average': _withheld(round(sum(avgs) / len(avgs), 1) if avgs else None, len(ids)),
            'targeted': sum(1 for i in ids if levels.get(i, {}).get('level') == TARGETED),
            'intensive': sum(1 for i in ids if levels.get(i, {}).get('level') == INTENSIVE)})

    return {
        'total': total,
        'attendance': _withheld(_rate([r[2] for r in recent]), total),
        'attendance_before': _withheld(_rate(before), total),
        'average': _withheld(round(avg_recent, 2) if avg_recent is not None else None, total),
        'average_before': _withheld(round(avg_before, 2) if avg_before is not None else None, total),
        'levels': {'targeted': level_counts.get(TARGETED, 0), 'intensive': level_counts.get(INTENSIVE, 0),
                   'universal': total - len(levels)},
        'alerts': {'new': new_alerts.count(), 'urgent': new_alerts.filter(risk_event__severity__in=('orange', 'red')).count(),
                   'by_type': [{'label': type_labels.get(k, k), 'n': n}
                               for k, n in Counter(new_alerts.values_list('risk_event__risk_type', flat=True)).most_common()],
                   'accepted_30': reviewed.filter(status=Alert.ACCEPTED).count(),
                   'dismissed_30': reviewed.filter(status=Alert.DISMISSED).count()},
        'plans': {'open': open_plans.count(), 'overdue': open_plans.filter(due_date__lt=today).count(),
                  'due_soon': open_plans.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7)).count(),
                  'stale': stale, 'reevaluate': len(due_for_reevaluation(plans, alerts, today)), 'completed': completed,
                  'outcomes': [{'code': k, 'label': outcome_labels.get(k, k), 'n': _withheld(n, n)}
                               for k, n in outcomes.most_common() if k] if completed >= MIN_GROUP else []},
        'rule_hits_30': RuleHit.objects.filter(school=school, evaluated_on__gt=today - timedelta(days=RECENT_DAYS)).count(),
        'attention': attention[:ATTENTION_ROWS], 'attention_total': len(attention),
        'classes': class_rows, 'subjects': subjects,
        'weekly_attendance': {'labels': [w[0] for w in weekly], 'values': [w[1] for w in weekly]},
        'monthly_average': {'labels': [m[0] for m in monthly], 'values': [m[1] for m in monthly]},
        'min_group': MIN_GROUP,
    }


def principal_dashboard(request):
    """SchoolAdmin only: ``dashboard_view`` checked the role. The attention list names students, so it is audit-logged as a
    list (``attention``), like the other student lists."""
    from students.student_school import allowed_school_ids

    from .school_views import _current_school
    if not allowed_school_ids(request.user):        # a SchoolAdmin without an active membership sees an empty page, no data
        return render(request, 'dashboard/principal.html', {'overview': None, 'no_school': True})
    school = _current_school(request)
    today = timezone.localdate()
    overview = principal_overview(request.user, school, today)
    audit.record_list(request.user, 'attention', [row['student'] for row in overview['attention']])
    return render(request, 'dashboard/principal.html', {
        'overview': overview, 'school': school, 'today': today, 'support_note': NOTE,
        'year': AcademicYear.objects.filter(school=school, is_current=True).first(),
        'my_schools': School.objects.filter(pk__in=allowed_school_ids(request.user)).order_by('name')})
