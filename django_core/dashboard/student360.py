"""Student 360 (Slice 3): one read-only page per student for SchoolAdmin, Grade Lead and Parent. Identity, enrollment path
per year, grades per year/subject with simple averages, attendance summary and the teachers' recommendations. No
predictions, no AI, no counseling content, no export. Deny by default: the student is looked up in the users's own
full-detail scope (``visible_students(...).filter(full_tier=True)``), so another school's / family's student is a 404."""
from collections import OrderedDict

from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from students.access import (
    ADMIN, GRADE_LEAD, PARENT, visible_attendances, visible_grades, visible_recommendations, visible_students)
from students.models import Enrollment

from .decorators import role_required

UNKNOWN_YEAR = 'بدون سال'


def grades_by_year(grades):
    """``[(year_code, [(subject_label, count, average)], year_average)]``, newest year first."""
    years = OrderedDict()
    rows = grades.select_related('enrollment__academic_year').order_by('-date')
    for grade in rows:
        year = grade.enrollment.academic_year.code if grade.enrollment_id else UNKNOWN_YEAR
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
    return {'total': total, 'rows': [(labels.get(k, k), v) for k, v in sorted(counts.items())],
            'present_rate': round(100 * counts.get('present', 0) / total) if total else None}


@role_required(ADMIN, GRADE_LEAD, PARENT)
def student_360(request, pk):
    student = get_object_or_404(visible_students(request.user).filter(full_tier=True), pk=pk)
    enrollments = (Enrollment.objects.filter(student=student).select_related('academic_year', 'school_class')
                   .order_by('-academic_year__start_date'))
    return render(request, 'dashboard/student_360.html', {
        'student': student,
        'enrollments': enrollments,
        'grade_years': grades_by_year(visible_grades(request.user).filter(student=student)),
        'attendance': attendance_summary(visible_attendances(request.user).filter(student=student)),
        'recommendations': visible_recommendations(request.user).filter(student=student).select_related('author'),
    })
