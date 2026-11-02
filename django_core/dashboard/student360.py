"""Student 360 (Slice 3): one read-only page per student for SchoolAdmin, Grade Lead and Parent. Identity, enrollment path
per year, grades per year/subject with simple averages, attendance summary and the teachers' recommendations. No
predictions, no AI, no counseling content, no export. Deny by default: the student is looked up in the users's own
full-detail scope (``visible_students(...).filter(full_tier=True)``), so another school's / family's student is a 404."""
from collections import OrderedDict

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from students.access import (
    ADMIN, COUNSELOR, GRADE_LEAD, PARENT, roles_for, visible_alerts, visible_plans, visible_attendances, visible_counselor_notes, counselor_note_metadata, visible_grades,
    visible_recommendations, visible_referrals, visible_students)
from schools.vocabulary import SUBJECT_CHOICES
from students.models import Enrollment

from schools import audit

from .decorators import role_required

UNKNOWN_YEAR = 'سال نامشخص'


def grades_by_year(grades):
    """``[(year_code, [(subject_label, count, average)], year_average)]``, newest year first."""
    years = OrderedDict()
    rows = grades.select_related('enrollment__academic_year').order_by('-date')
    for grade in rows:
        year = (grade.enrollment.academic_year.label or grade.enrollment.academic_year.code) if grade.enrollment_id else UNKNOWN_YEAR
        years.setdefault(year, {}).setdefault(grade.get_subject_display(), []).append(grade.score)
    result = []
    for year in sorted(years, reverse=True):
        subjects = [(name, len(scores), round(sum(scores) / len(scores), 2)) for name, scores in sorted(years[year].items())]
        every = [s for scores in years[year].values() for s in scores]
        result.append((year, subjects, round(sum(every) / len(every), 2)))
    return result


def attendance_summary(attendances):
    counts = {row['status']: row['n'] for row in attendances.values('status').annotate(n=Count('pk'))}
    total = sum(counts.values())
    labels = dict(attendances.model.STATUS_CHOICES) if hasattr(attendances.model, 'STATUS_CHOICES') else {}
    css = {'present': 'bg-success', 'absent': 'bg-danger', 'late': 'bg-warning', 'sick': 'bg-info'}
    bars = [(labels.get(k, k), v, round(100 * v / total), css.get(k, 'bg-secondary')) for k, v in sorted(counts.items())] if total else []
    return {'total': total, 'bars': bars, 'rows': [(labels.get(k, k), v) for k, v in sorted(counts.items())],
            'present_rate': round(100 * counts.get('present', 0) / total) if total else None}


def key_signals(grade_years, attendance, trend_subjects=None):
    """Top-of-page facts for the 360: latest year average, attendance rate and the biggest drop between the two most
    recent grade periods (staff only: ``trend_subjects`` is None for a Parent). Derived on the fly, nothing stored."""
    labels = dict(SUBJECT_CHOICES)
    drop = None
    for code, avgs in (trend_subjects or {}).items():
        last, prev = avgs[-1], next((a for a in reversed(avgs[:-1]) if a is not None), None)
        if last is not None and prev is not None and prev - last > 0 and (drop is None or prev - last > drop[1]):
            drop = (labels.get(code, code), round(prev - last, 1))
    return {'average': grade_years[0][2] if grade_years else None, 'year': grade_years[0][0] if grade_years else '',
            'present_rate': attendance['present_rate'], 'drop': drop}


def summary_context(request, student):
    """The read-only summary shared by the Student 360 page and the counselor's case page (all through the access layer)."""
    enrollments = (Enrollment.objects.filter(student=student).select_related('academic_year', 'school_class')
                   .order_by('-academic_year__start_date'))
    grade_years = grades_by_year(visible_grades(request.user).filter(student=student))
    attendance = attendance_summary(visible_attendances(request.user).filter(student=student))
    return {
        'signals': key_signals(grade_years, attendance),
        'student': student,
        'enrollments': enrollments,
        'grade_years': grade_years,
        'attendance': attendance,
        'recommendations': visible_recommendations(request.user).filter(student=student).select_related('author'),
    }


@role_required(ADMIN, GRADE_LEAD, PARENT)
def student_360(request, pk):
    student = get_object_or_404(visible_students(request.user).filter(full_tier=True), pk=pk)
    audit.record(request.user, audit.VIEW_360, student)
    context = summary_context(request, student)
    context['referrals'] = visible_referrals(request.user).filter(student=student).select_related('counselor')
    notes = list(visible_counselor_notes(request.user).filter(referral__student=student).select_related('author'))
    context['counselor_notes'] = notes
    # SchoolAdmin, closed referral: existence and date only (the text is not read from the database here)
    context['closed_note_dates'] = list(counselor_note_metadata(request.user).filter(referral__student=student)
                                        .order_by('created_at').values_list('created_at', flat=True))
    if notes:       # note text is rendered below: record that, counts only (view_student_360 stays the page-level event)
        audit.record(request.user, audit.COUNSELOR_NOTE_VIEW, student, detail=f'n{len(notes)}')
    roles = roles_for(request.user)
    if roles & {ADMIN, GRADE_LEAD}:
        # Trend tile (0025): derived only from the rows this user's own visible_* helpers return; a Parent never gets it.
        from django.utils import timezone
        from risk import trends
        today = timezone.localdate()
        context['trend_weeks'] = trends.weekly_absence(visible_attendances(request.user).filter(student=student), today)
        context['trend_subjects'] = trends.subject_period_averages(visible_grades(request.user).filter(student=student), today)
        labels = dict(SUBJECT_CHOICES)
        context['trend_rows'] = [(labels.get(c, c), a) for c, a in context['trend_subjects'].items()]
        context['signals'] = key_signals(context['grade_years'], context['attendance'], context['trend_subjects'])
        # Intervention loop tile: metadata only (counts, type, status, dates, owner, outcome code). The scoped querysets give a
        # Parent nothing, and the tile is not rendered for them at all.
        context['loop_alerts'] = visible_alerts(request.user).filter(student=student).select_related('risk_event')[:10]
        context['loop_plans'] = visible_plans(request.user).filter(student=student).select_related('owner')[:10]
        # P5-2 support level: derived from the same review-scope alerts/plans, never stored (interventions/support.py)
        from interventions.support import NOTE, reviewable_alerts_and_plans_level
        context['support'] = reviewable_alerts_and_plans_level(request.user, student)
        context['support_note'] = NOTE
        from .counselor_views import ReferralForm
        context['referral_form'] = ReferralForm(student=student)
    if ADMIN in roles:
        from .student_views import StudentAccountForm
        context['account_form'] = None if student.student_user_id else StudentAccountForm(student=student)
        context['student_account'] = student.student_user
    # P5-3 behavior log: the read scope decides (a Parent sees positive entries only); the form only for writers
    from students.access import behavior_writable_students, visible_behavior_notes
    from .behavior_views import BehaviorNoteForm
    context['behavior_notes'] = visible_behavior_notes(request.user).filter(student=student)[:30]
    context['behavior_form'] = BehaviorNoteForm() if behavior_writable_students(request.user).filter(pk=student.pk).exists() else None
    return render(request, 'dashboard/student_360.html', context)


@role_required(ADMIN, GRADE_LEAD, PARENT, COUNSELOR)
@require_POST
def reveal_national_id(request, pk):
    """Full national id on an explicit click; same scope as the pages that show the masked value; audit-logged."""
    student = get_object_or_404(visible_students(request.user).filter(full_tier=True), pk=pk)
    audit.record(request.user, audit.NATIONAL_ID_REVEAL, student)
    return JsonResponse({'national_id': student.national_id})
