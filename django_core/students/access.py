"""Single place that maps a Django user to roles and to the students they may see.

Since stage 2.2a-4c (ADR-0011) Grade Lead and Subject Teacher scopes are decided by the student's CURRENT
ENROLLMENT, not by the mirror fields on ``Student``; the pre-switch rule is kept verbatim in ``access_legacy`` for
the parity tooling and for revert.

Roles are the existing Django groups: ``SchoolAdmin`` (was ``Admin``), ``Teacher``, ``Parent``. A superuser is
treated as ``SchoolAdmin``. Anything else (no group, anonymous, unknown group) gets NO role and
therefore no access. This is an interim containment policy for Phase 1 (docs/SECURITY.md,
ADR-0003 is still DECISION REQUIRED); it is not the final authorization model.
"""
from functools import reduce
from operator import or_

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Q, Value

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.vocabulary import SUBJECT_KEYS

from .enrollment_sync import CURRENT_STATUSES
from .models import Attendance, Enrollment, Grade, Student

ADMIN = 'SchoolAdmin'  # ADR-0010 (renamed by students/0010); FastAPI auth.ADMIN must match
TEACHER = 'Teacher'  # Subject Teacher (ADR-0005)
GRADE_LEAD = 'GradeLead'  # ADR-0005; group created by setup_staff_roles; read since C5a
COUNSELOR = 'Counselor'  # ADR-0005; same, access arrives with referrals (2.6)
PARENT = 'Parent'
ALL_ROLES = (ADMIN, TEACHER, GRADE_LEAD, PARENT)


def roles_for(user):
    """Return the set of recognised roles held by ``user`` (empty for anonymous/unknown)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()
    names = set(user.groups.filter(name__in=ALL_ROLES).values_list('name', flat=True))
    if user.is_superuser:
        names.add(ADMIN)
    return names


def has_any_role(user, *roles):
    return bool(roles_for(user) & set(roles))


def _any(parts):
    """OR the non-empty parts; None when there is no part (callers treat None as 'grants nothing')."""
    parts = [p for p in parts if p is not None]
    return reduce(or_, parts) if parts else None


def _may_hold_scoped_grants(user):
    """Grade Lead / Subject Teacher grants apply only to an active, non-staff, non-superuser account, checked at
    query time (owner decision 2026-10-16); the assignment forms enforce the same rule only at creation."""
    return bool(user.is_active and not user.is_staff and not user.is_superuser)


def _current_enrollment(school_id, *extra, **conditions):
    """Q on ``Student``: the student has a CURRENT enrollment (open, status in ``CURRENT_STATUSES``) in the current
    academic year of ``school_id``, and ``school_id`` is also the student's own school (owner D-4-1, D-4-4).
    ``extra`` / ``conditions`` further filter the enrollment. An ``Exists`` subquery: no join duplicates, index-backed."""
    return Q(school_id=school_id) & Q(Exists(Enrollment.objects.filter(
        *extra, student_id=OuterRef('pk'), ended_on__isnull=True, status__in=CURRENT_STATUSES,
        academic_year__is_current=True, academic_year__school_id=school_id, **conditions)))


def _grade_lead_q(user, roles):
    """Students of (school, grade) for each ACTIVE assignment of the user (ADR-0005 §2; owner D-C5a-1).

    Matched through the CURRENT ENROLLMENT (ADR-0011, owner D-4-2): the enrollment's grade equals the assignment's
    grade and the current year's code equals the assignment's NORMALISED academic year; an enrollment class, when
    present, must be active. An unresolved or blank assignment year grants nothing (fail closed), and so does a
    student without a current enrollment. The group is re-checked here, so a row of a user who left the group
    grants nothing.
    """
    if GRADE_LEAD not in roles or not _may_hold_scoped_grants(user):
        return None
    from schools.models import GradeLeadAssignment  # lazy: keeps the import graph acyclic

    parts = []
    for school_id, grade, year in GradeLeadAssignment.objects.filter(user=user, is_active=True).values_list(
            'school_id', 'grade', 'academic_year'):
        status, code = normalize_academic_year(year)
        if status != RESOLVED:
            continue
        parts.append(_current_enrollment(
            school_id, Q(school_class__isnull=True) | Q(school_class__is_active=True),
            academic_year__code=code, grade=grade))
    return _any(parts)


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

    SchoolAdmin: all. Parent: own children. Grade Lead: students of the assigned school whose current enrollment
    has the assigned grade, in the current year the assignment names. Subject Teacher: students whose current
    enrollment is in a class with an active assignment. Each row is annotated ``full_tier``: True where a full-detail grant covers it
    (SchoolAdmin, Parent, Grade Lead), False where only a Subject Teacher grant does. Field policy, search
    and attendance follow ``full_tier``, never the user's role names (non-widening, ADR-0005 §5).
    """
    roles = roles_for(user)
    if ADMIN in roles:
        return Student.objects.annotate(full_tier=Value(True, output_field=BooleanField()))
    full = _full_tier_q(user, roles)
    teacher = _any(
        _current_enrollment(school_id, school_class_id=class_id)
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


def visible_grades(user):
    """Grade rows the user may read: through a full-detail grant (all subjects) or through a Subject Teacher
    assignment (own subject, assigned class only)."""
    roles = roles_for(user)
    if ADMIN in roles:
        return Grade.objects.all()
    full = _full_tier_q(user, roles)
    parts = [Q(student__in=Student.objects.filter(full)) if full is not None else None]
    parts += [
        Q(student__in=Student.objects.filter(_current_enrollment(school_id, school_class_id=class_id)), subject=subject)
        for school_id, class_id, subject in _teacher_assignments(user, roles)
    ]
    scope = _any(parts)
    return Grade.objects.none() if scope is None else Grade.objects.filter(scope)


def visible_attendances(user):
    """Attendance rows: SchoolAdmin all; Parent and Grade Lead for their full-detail students; a Subject
    Teacher sees none (owner D7)."""
    roles = roles_for(user)
    if ADMIN in roles:
        return Attendance.objects.all()
    full = _full_tier_q(user, roles)
    if full is None:
        return Attendance.objects.none()
    return Attendance.objects.filter(student__in=Student.objects.filter(full))


def search_students(queryset, term):
    """Name search for every role; ``national_id`` is matched ONLY on full-tier rows, so a limited row can
    never be probed by identity (TEACHER_ACCESS_REVIEW R6). ``queryset`` comes from ``visible_students``."""
    for word in (term or '').split():
        queryset = queryset.filter(
            Q(first_name__icontains=word) | Q(last_name__icontains=word)
            | (Q(full_tier=True) & Q(national_id__icontains=word))
        )
    return queryset
