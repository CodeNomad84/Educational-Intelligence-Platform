"""JSON dashboard summary for the two presentation frontends (Phase 3, Step 1).

GET /api/dashboard/ returns every aggregate figure the TanStack Start dashboards
(frontend-men and frontend-women) need, computed on read from the calling user's own
access scopes via the same visible_* querysets used by the HTML dashboards. A role that
sees nothing gets empty lists and null figures - never an unfiltered count. Alert text is
gated with apply_alert_text_policy before serialization.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from interventions.models import InterventionPlan
from risk.models import Alert
from schools.models import AcademicYear
from schools.vocabulary import SUBJECT_CHOICES
from students.access import (
    apply_alert_text_policy, visible_alerts, visible_attendances, visible_behavior_notes,
    visible_grades, visible_plans, visible_recommendations, visible_students,
)

RECENT_DAYS = 30
TREND_MONTHS = 6
MIN_GROUP = 5
MIN_DAYS = 3
MAX_ROWS = 200
MAX_SUBJECTS = 8
PRESENT = ('present', 'late')

PERSIAN_MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']


def _to_jalali(value):
    gy, gm, gd = value.year, value.month, value.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def _persian_date(value):
    if value is None:
        return None
    if hasattr(value, 'date'):
        value = value.date()
    _jy, jm, jd = _to_jalali(value)
    return {'day': jd, 'month': jm}


def _persian_month(value):
    return PERSIAN_MONTHS[value.month - 1]


def _rate(statuses):
    return round(100 * sum(1 for s in statuses if s in PRESENT) / len(statuses), 1) if statuses else None


def _student_status(gpa, attendance_rate):
    if (gpa is not None and gpa < 12) or (attendance_rate is not None and attendance_rate < 80):
        return 'risk'
    if (gpa is not None and gpa < 15) or (attendance_rate is not None and attendance_rate < 90):
        return 'attention'
    if gpa is not None and gpa >= 17:
        return 'excellent'
    return 'growing'


def _name(user):
    if user is None:
        return '—'
    return (user.get_full_name() or user.get_username()).strip() or '—'


def _subject_label(code):
    labels = dict(SUBJECT_CHOICES)
    return labels.get(code, code)


def build_summary(user):
    today = timezone.localdate()
    student_rows = list(visible_students(user).select_related('school_class')
                        .order_by('grade', 'last_name', 'first_name')[:MAX_ROWS])

    grades = visible_grades(user)
    attendances = visible_attendances(user)
    alerts = visible_alerts(user).select_related('student', 'risk_event')
    plans = visible_plans(user)
    recommendations = visible_recommendations(user).select_related('author')
    behavior_notes = visible_behavior_notes(user).select_related('recorded_by')

    avg_all = grades.aggregate(a=Avg('score'))['a']
    recent_att = list(attendances.filter(date__gt=today - timedelta(days=RECENT_DAYS), date__lte=today)
                      .values_list('student_id', 'status'))
    recent_students = len({sid for sid, _status in recent_att})
    attendance_rate = _rate([s for _sid, s in recent_att]) if recent_students >= MIN_GROUP else None
    average = round(avg_all, 1) if avg_all is not None else None
    new_alerts = alerts.filter(status=Alert.NEW)
    open_plans = plans.filter(status__in=(InterventionPlan.PLANNED, InterventionPlan.ACTIVE))
    observations_count = recommendations.count() + behavior_notes.count()

    windows = [today - timedelta(days=30 * n) for n in range(TREND_MONTHS - 1, -1, -1)]
    attendance_trend = []
    average_trend = []
    for end in windows:
        att_win = attendances.filter(date__gt=end - timedelta(days=30), date__lte=end)
        statuses = list(att_win.values_list('status', flat=True))
        att_n = att_win.values('student_id').distinct().count()
        attendance_trend.append({'label': _persian_month(end),
                                 'value': _rate(statuses) if statuses and att_n >= MIN_GROUP else None})
        grade_win = grades.filter(date__gt=end - timedelta(days=30), date__lte=end).aggregate(
            a=Avg('score'), c=Count('student', distinct=True))
        average_trend.append({'label': _persian_month(end),
                              'value': round(grade_win['a'], 1) if grade_win['a'] is not None and grade_win['c'] >= MIN_GROUP else None})

    subject_rows = list(grades.values('subject').annotate(
        a=Avg('score'), n=Count('student', distinct=True)).order_by('subject'))
    subjects = [{'label': _subject_label(r['subject']), 'average': round(r['a'], 1)}
                for r in subject_rows if r['n'] >= MIN_GROUP][:MAX_SUBJECTS]
    by_grade = defaultdict(list)
    for r in grades.values('student__grade', 'subject').annotate(
            a=Avg('score'), n=Count('student', distinct=True)).order_by('student__grade', 'subject'):
        if r['n'] >= MIN_GROUP:
            by_grade[r['student__grade']].append({'label': _subject_label(r['subject']), 'average': round(r['a'], 1)})
    subjects_by_grade = [{'grade': grade, 'subjects': rows[:MAX_SUBJECTS]}
                         for grade, rows in sorted(by_grade.items())]
    grades_present = sorted({s.grade for s in student_rows if s.grade is not None})

    student_averages = dict(grades.values('student_id').annotate(a=Avg('score')).values_list('student_id', 'a'))
    att_days = defaultdict(int)
    att_present = defaultdict(int)
    for sid, status in recent_att:
        att_days[sid] += 1
        if status in PRESENT:
            att_present[sid] += 1

    observations_by_student = defaultdict(list)
    for r in recommendations:
        observations_by_student[r.student_id].append(
            {'kind': 'suggestion', 'text': r.text, 'mentor': _name(r.author), 'date': _persian_date(r.created_at)})
    for b in behavior_notes:
        observations_by_student[b.student_id].append(
            {'kind': 'kudos' if b.kind == b.POSITIVE else 'alert', 'text': b.note,
             'mentor': _name(b.recorded_by), 'date': _persian_date(b.created_at)})

    roster = []
    for s in student_rows:
        gpa = round(student_averages[s.pk], 1) if s.pk in student_averages else None
        rate = round(100 * att_present[s.pk] / att_days[s.pk], 1) if att_days[s.pk] >= MIN_DAYS else None
        roster.append({
            'id': s.pk, 'name': f'{s.first_name} {s.last_name}', 'grade': s.grade,
            'classroom': s.school_class.title if s.school_class_id else (s.class_name or '—'),
            'gpa': gpa, 'attendance_rate': rate, 'status': _student_status(gpa, rate),
            'observations': sorted(observations_by_student[s.pk], key=lambda o: (o['date'] is None,))[:5],
        })

    open_alerts = apply_alert_text_policy(user, list(new_alerts.select_related('student', 'risk_event')[:MAX_ROWS]))
    alerts_out = [{
        'id': a.pk, 'student_id': a.student_id,
        'student_name': f'{a.student.first_name} {a.student.last_name}', 'grade': a.student.grade,
        'type': a.risk_event.risk_type, 'type_label': a.risk_event.get_risk_type_display(),
        'severity': a.risk_event.severity, 'severity_label': a.risk_event.get_severity_display(),
        'status': a.status, 'created_at': _persian_date(a.created_at),
        'message': a.message, 'text_hidden': getattr(a, 'text_hidden', False),
    } for a in open_alerts]

    school_ids = {s.school_id for s in student_rows}
    current_year = None
    if len(school_ids) == 1:
        year = AcademicYear.objects.filter(school_id=next(iter(school_ids)), is_current=True).first()
        current_year = year.code if year else None

    kpis = [
        {'key': 'students', 'label': 'دانش‌آموزان فعال', 'value': len(student_rows), 'unit': None,
         'tone': 'primary', 'series': None},
        {'key': 'average', 'label': 'میانگین نمرات', 'value': average, 'unit': 'از ۲۰',
         'tone': 'info', 'series': [t['value'] for t in average_trend]},
        {'key': 'attendance', 'label': 'نرخ حضور', 'value': attendance_rate, 'unit': '٪',
         'tone': 'success', 'series': [t['value'] for t in attendance_trend]},
        {'key': 'observations', 'label': 'مشاهدات و بازخوردها', 'value': observations_count, 'unit': None,
         'tone': 'warning', 'series': None},
        {'key': 'alerts_open', 'label': 'هشدارهای باز', 'value': new_alerts.count(), 'unit': None,
         'tone': 'danger', 'series': None},
        {'key': 'plans_open', 'label': 'برنامه‌های مداخله فعال', 'value': open_plans.count(), 'unit': None,
         'tone': 'info', 'series': None},
    ]

    return {
        'meta': {'academic_year': current_year, 'generated_at': timezone.now().isoformat(), 'min_group': MIN_GROUP},
        'kpis': kpis,
        'attendance_trend': attendance_trend,
        'average_trend': average_trend,
        'subjects': subjects,
        'subjects_by_grade': subjects_by_grade,
        'grades_present': grades_present,
        'alerts': alerts_out,
        'students': roster,
    }


class DashboardSummaryView(APIView):
    authentication_classes = (JWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(build_summary(request.user))
