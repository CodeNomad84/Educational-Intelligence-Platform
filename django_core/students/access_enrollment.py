"""Enrollment-based matching for Grade Lead and Subject Teacher (ADR-0011, stage 2.2a-4b; owner D-4-1..4).

NOT ACTIVE YET: ``students/access.py`` still decides visibility with the mirror fields. This module exists so the
two rules can be compared (``compare_access_parity``) before the switch (4c). It has the same contract as
``access.visible_students``: a ``Student`` queryset annotated with ``full_tier``.

Current enrollment = open (``ended_on`` null), status in ``CURRENT_STATUSES``, in the school's current academic
year, and of the student's own school. Grade Lead: the enrollment's grade equals the assignment's grade and the
assignment's year code (normalised) equals the current year; the enrollment class, when present, must be active.
Subject Teacher: the enrollment's class has an active assignment of the user (valid subject). Account checks
(active, non-staff, group) are the same as before.
"""
from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Q, Value

from schools.academic_years import RESOLVED, normalize_academic_year

from .access import ADMIN, GRADE_LEAD, PARENT, _any, _may_hold_scoped_grants, _teacher_assignments, roles_for
from .enrollment_sync import CURRENT_STATUSES
from .models import Enrollment, Student


def _grade_lead_q(user, roles):
    if GRADE_LEAD not in roles or not _may_hold_scoped_grants(user):
        return None
    from schools.models import GradeLeadAssignment

    parts = []
    for school_id, grade, year in GradeLeadAssignment.objects.filter(user=user, is_active=True).values_list(
            'school_id', 'grade', 'academic_year'):
        status, code = normalize_academic_year(year)
        if status != RESOLVED:
            continue  # unresolved year grants nothing (fail closed)
        parts.append(Q(school_id=school_id) & Q(Exists(Enrollment.objects.filter(
            student_id=OuterRef('pk'), ended_on__isnull=True, status__in=CURRENT_STATUSES,
            academic_year__is_current=True, academic_year__school_id=school_id, academic_year__code=code,
            grade=grade).filter(Q(school_class__isnull=True) | Q(school_class__is_active=True)))))
    return _any(parts)


def _teacher_q(user, roles):
    return _any(
        Q(school_id=school_id) & Q(Exists(Enrollment.objects.filter(
            student_id=OuterRef('pk'), ended_on__isnull=True, status__in=CURRENT_STATUSES,
            academic_year__is_current=True, academic_year__school_id=school_id, school_class_id=class_id)))
        for school_id, class_id, _subject in _teacher_assignments(user, roles)
    )


def visible_students_by_enrollment(user):
    roles = roles_for(user)
    if ADMIN in roles:
        return Student.objects.annotate(full_tier=Value(True, output_field=BooleanField()))
    full = _any([Q(parent_user=user) if PARENT in roles else None, _grade_lead_q(user, roles)])
    teacher = _teacher_q(user, roles)
    scope = _any([full, teacher])
    if scope is None:
        return Student.objects.none().annotate(full_tier=Value(False, output_field=BooleanField()))
    tier = Value(False, output_field=BooleanField()) if full is None else ExpressionWrapper(full, output_field=BooleanField())
    return Student.objects.filter(scope).annotate(full_tier=tier)
