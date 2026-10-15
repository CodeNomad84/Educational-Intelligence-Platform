"""Single place that maps a Django user to roles and to the students they may see.

Roles are the existing Django groups: ``SchoolAdmin`` (was ``Admin``), ``Teacher``, ``Parent``. A superuser is
treated as ``SchoolAdmin``. Anything else (no group, anonymous, unknown group) gets NO role and
therefore no access. This is an interim containment policy for Phase 1 (docs/SECURITY.md,
ADR-0003 is still DECISION REQUIRED); it is not the final authorization model.
"""
from functools import reduce
from operator import or_

from django.db.models import BooleanField, ExpressionWrapper, Q, Value

from schools.vocabulary import SUBJECT_KEYS

from .models import Attendance, Grade, Student

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


def _grade_lead_q(user, roles):
    """Students of (school, grade) for each ACTIVE assignment of the user (ADR-0005 §2; owner D-C5a-1).

    Matched through the LINKED class: the class must be active and carry the assignment's academic year.
    Unlinked students are invisible to a Grade Lead (fail closed). The group is re-checked here, so a row
    of a user who left the group grants nothing.
    """
    if GRADE_LEAD not in roles:
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
    if TEACHER not in roles:
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


def visible_grades(user):
    """Grade rows the user may read: through a full-detail grant (all subjects) or through a Subject Teacher
    assignment (own subject, assigned class only)."""
    roles = roles_for(user)
    if ADMIN in roles:
        return Grade.objects.all()
    full = _full_tier_q(user, roles)
    parts = [Q(student__in=Student.objects.filter(full)) if full is not None else None]
    parts += [
        Q(student__school_id=school_id, student__school_class_id=class_id, subject=subject)
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
