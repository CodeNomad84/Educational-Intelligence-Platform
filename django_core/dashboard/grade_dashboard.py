"""Grade Lead dashboard (owner correction A1): counts, a class table, an attention list and two charts, computed ONLY from
what the Grade Lead may read (``visible_students(...).filter(full_tier=True)`` and the matching ``visible_grades`` /
``visible_attendances``: the own grade(s) of the own school). Simple deterministic rules, no model, no prediction."""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg
from django.shortcuts import render
from django.utils import timezone

from students.access import GRADE_LEAD, visible_attendances, visible_grades, visible_students

from .decorators import role_required

LOW_AVERAGE = 12.0          # attention: average below this (out of 20)
HIGH_ABSENCE = 0.2          # attention: share of absent days among the last 30 days at or above this
MIN_DAYS = 3                # ... with at least this many recorded days
BUCKETS = ((0, 5), (5, 10), (10, 15), (15, 20.01))


def grade_overview(user, today=None):
    today = today or timezone.localdate()
    students = list(visible_students(user).filter(full_tier=True).order_by('class_name', 'last_name', 'first_name'))
    ids = [s.pk for s in students]
    grades = visible_grades(user).filter(student_id__in=ids)
    attendances = visible_attendances(user).filter(student_id__in=ids)

    averages = {row['student_id']: row['avg'] for row in grades.values('student_id').annotate(avg=Avg('score'))}
    recent_from = today - timedelta(days=30)
    days, absent = defaultdict(int), defaultdict(int)
    for student_id, status in attendances.filter(date__gt=recent_from).values_list('student_id', 'status'):
        days[student_id] += 1
        absent[student_id] += 1 if status == 'absent' else 0

    classes = defaultdict(lambda: {'count': 0, 'scores': [], 'days': 0, 'absent': 0, 'attention': 0})
    attention = []
    for student in students:
        avg = averages.get(student.pk)
        rate = absent[student.pk] / days[student.pk] if days[student.pk] >= MIN_DAYS else None
        reasons = []
        if avg is not None and avg < LOW_AVERAGE:
            reasons.append(f'میانگین نمرات پایین ({round(avg, 1)})')
        if rate is not None and rate >= HIGH_ABSENCE:
            reasons.append(f'غیبت زیاد در ۳۰ روز اخیر ({round(rate * 100)}٪)')
        row = classes[student.class_name or '—']
        row['count'] += 1
        row['days'] += days[student.pk]
        row['absent'] += absent[student.pk]
        if avg is not None:
            row['scores'].append(avg)
        if reasons:
            row['attention'] += 1
            attention.append({'student': student, 'reasons': reasons, 'avg': avg, 'rate': rate})
    class_rows = [{'name': name, 'count': r['count'], 'attention': r['attention'],
                   'average': round(sum(r['scores']) / len(r['scores']), 2) if r['scores'] else None,
                   'absence': round(100 * r['absent'] / r['days']) if r['days'] else None}
                  for name, r in sorted(classes.items())]
    scores = list(grades.values_list('score', flat=True))
    weekly = []
    for weeks_ago in range(7, -1, -1):
        start, end = today - timedelta(days=7 * (weeks_ago + 1)), today - timedelta(days=7 * weeks_ago)
        week = list(attendances.filter(date__gt=start, date__lte=end).values_list('status', flat=True))
        weekly.append({'label': end.isoformat(), 'value': round(100 * week.count('absent') / len(week)) if week else None})
    score_labels = ['۰–۵', '۵–۱۰', '۱۰–۱۵', '۱۵–۲۰']
    score_values = [sum(1 for x in scores if lo <= x < hi) for lo, hi in BUCKETS]
    trend_labels = [w['label'] for w in weekly]
    trend_values = [w['value'] for w in weekly]
    return {
        'total': len(students),
        'average': round(sum(scores) / len(scores), 2) if scores else None,
        'absence': round(100 * sum(absent.values()) / sum(days.values())) if sum(days.values()) else None,
        'attention_count': len(attention),
        'classes': class_rows,
        'attention': sorted(attention, key=lambda a: (-len(a['reasons']), a['avg'] if a['avg'] is not None else 99))[:10],
        'score_buckets': {'labels': score_labels, 'values': score_values,
                          'rows': list(zip(score_labels, score_values))},
        'absence_trend': {'labels': trend_labels, 'values': trend_values,
                          'rows': list(zip(trend_labels, trend_values))},
    }


@role_required(GRADE_LEAD)
def grade_dashboard(request):
    return render(request, 'dashboard/grade_dashboard.html', {'o': grade_overview(request.user)})
