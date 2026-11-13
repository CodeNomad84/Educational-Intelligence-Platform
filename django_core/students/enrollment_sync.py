"""Keep the CURRENT-year enrollment in step with the student's class and grade (ADR-0011, stage 2.2a-4a).

``ensure_current_enrollment(student)`` is called explicitly from the write paths (admin, dashboard form, API,
live import) after a student is saved; no signals (owner D-4-3). It changes NO access: nothing reads
enrollments for visibility before stage 2.2a-4c.

Evidence-only, like the backfill: it never guesses. Returns one outcome string; a skip is reported to the
caller, never raised, so saving a student is never blocked by it.

    created / updated / class_changed   a current-year enrollment was written
    unchanged                           already in step
    no_class, no_current_year, class_year_mismatch, class_grade_conflict   skipped (why)
"""
from django.utils import timezone

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import AcademicYear
from students.models import Enrollment

SKIPPED = frozenset({'no_class', 'no_current_year', 'class_year_mismatch', 'class_grade_conflict'})
CURRENT_STATUSES = ('active', 'transferred_in')  # owner D-4-1


def ensure_current_enrollment(student, *, source='manual', today=None):
    if student.school_class_id is None:
        return 'no_class'
    year = AcademicYear.objects.filter(school_id=student.school_id, is_current=True).first()
    if year is None:
        return 'no_current_year'
    klass = student.school_class
    status, code = normalize_academic_year(klass.academic_year)
    if status != RESOLVED or code != year.code:
        return 'class_year_mismatch'  # a link to a class of another year is a stale mirror, not evidence
    if klass.grade is not None and klass.grade != student.grade:
        return 'class_grade_conflict'

    open_rows = list(Enrollment.objects.filter(student=student, academic_year=year, ended_on__isnull=True))
    if not open_rows:
        Enrollment.objects.create(
            student=student, academic_year=year, school_class=klass, grade=student.grade,
            status='active', source=source, started_on=today or timezone.localdate())
        return 'created'
    current = open_rows[0]
    if current.school_class_id == klass.pk and current.grade == student.grade:
        return 'unchanged'
    if current.school_class_id != klass.pk and current.school_class_id is not None:
        # a mid-year class change closes one row and opens another (proposal 0003 §3.2)
        when = today or timezone.localdate()
        Enrollment.objects.filter(pk=current.pk).update(ended_on=when)
        Enrollment.objects.create(
            student=student, academic_year=year, school_class=klass, grade=student.grade,
            status='active', source=source, started_on=when)
        return 'class_changed'
    Enrollment.objects.filter(pk=current.pk).update(school_class=klass, grade=student.grade)
    return 'updated'
