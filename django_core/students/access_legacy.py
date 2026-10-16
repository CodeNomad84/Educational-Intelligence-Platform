"""The CURRENT (pre-switch) Grade Lead / Subject Teacher matching, kept verbatim (ADR-0011, stage 2.2a-4b).

Copied unchanged from ``students/access.py`` at the commit before the switch (4c). Used ONLY by the parity
tooling (``compare_access_parity`` and its tests); production code never imports this module. It keeps matching
through the mirror fields (``Student.grade``, ``Student.school_class`` and the class's free-text academic year).
Do not edit: it is the reference the new enrollment-based rule is compared with. Remove it only after the
switch has been accepted in production.
"""
from django.db.models import BooleanField, ExpressionWrapper, Q, Value

from schools.vocabulary import SUBJECT_KEYS

from .access import ADMIN, GRADE_LEAD, PARENT, TEACHER, _any, _may_hold_scoped_grants, roles_for
from .models import Student


def _grade_lead_q(user, roles):
    """Students of (school, grade) for each ACTIVE assignment of the user (ADR-0005 §2; owner D-C5a-1).

    Matched through the LINKED class: the class must be active and carry the assignment's academic year.
    Unlinked students are invisible to a Grade Lead (fail closed). The group is re-checked here, so a row
    of a user who left the group grants nothing.
    """
    if GRADE_LEAD not in roles or not _may_hold_scoped_grants(user):
        return None
    from schools.models import GradeLeadAssignment  # lazy: keeps the import graph acyclic

    rows = GradeLeadAssignment.objects.filter(user=user, is_active=True).values_list(
        'school_id', 'grade', 'academic_year')
    return _any(
        Q(school_id=school_id, grade=grade, school_class__isnull=False,
          school_class__is_active=True, school_class__academic_year=year)
        for school_id, grade, year in rows if year
    )


def _teacher_assignments(user, roles):
    """Active assignments of a Subject Teacher: (school_id, class_id, subject). Blank/unknown subject = none."""
    if TEACHER not in roles or not _may_hold_scoped_grants(user):
        return []
    from schools.models import TeacherAssignment

    return list(TeacherAssignment.objects.filter(
        teacher=user, school_class__is_active=True, subject__in=SUBJECT_KEYS,
    ).values_list('school_class__school_id', 'school_class_id', 'subject'))


def _full_tier_q(user, roles):
    """Rows where the user holds a full-detail grant: Parent (own child) or Grade Lead (own grade)."""
    return _any([Q(parent_user=user) if PARENT in roles else None, _grade_lead_q(user, roles)])


def visible_students(user):
    """Students the user may read: the union of the user's grants. Deny by default.

    SchoolAdmin: all. Parent: own children. Grade Lead: students of the assigned school/grade whose linked
    class is active and of the assignment's academic year. Subject Teacher: students of classes with an
    active assignment. Each row is annotated ``full_tier``: True where a full-detail grant covers it
    (SchoolAdmin, Parent, Grade Lead), False where only a Subject Teacher grant does. Field policy, search
    and attendance follow ``full_tier``, never the user's role names (non-widening, ADR-0005 §5).
    """
    roles = roles_for(user)
    if ADMIN in roles:
        return Student.objects.annotate(full_tier=Value(True, output_field=BooleanField()))
    full = _full_tier_q(user, roles)
    teacher = _any(
        Q(school_id=school_id, school_class_id=class_id)
        for school_id, class_id, _subject in _teacher_assignments(user, roles)
    )
    scope = _any([full, teacher])
    if scope is None:
        return Student.objects.none().annotate(full_tier=Value(False, output_field=BooleanField()))
    if full is None:
        tier = Value(False, output_field=BooleanField())
    else:
        tier = ExpressionWrapper(full, output_field=BooleanField())
    return Student.objects.filter(scope).annotate(full_tier=tier)
