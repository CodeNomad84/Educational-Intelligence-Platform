"""Single place that maps a Django user to roles and to the students they may see.

Roles are the existing Django groups: ``Admin``, ``Teacher``, ``Parent``. A superuser is
treated as ``Admin``. Anything else (no group, anonymous, unknown group) gets NO role and
therefore no access. This is an interim containment policy for Phase 1 (docs/SECURITY.md,
ADR-0003 is still DECISION REQUIRED); it is not the final authorization model.
"""
from .models import Student

ADMIN = 'Admin'
TEACHER = 'Teacher'
PARENT = 'Parent'
ALL_ROLES = (ADMIN, TEACHER, PARENT)


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


def visible_students(user):
    """Students the user may read. Deny by default.

    Admin: all students.
    Parent: only students whose ``parent_user`` is this user.
    Teacher: NONE. There is no verified teacher-to-student/class assignment model yet (S-04), so
    teacher access to student data stays disabled until one exists (DECISION REQUIRED).
    """
    roles = roles_for(user)
    if ADMIN in roles:
        return Student.objects.all()
    if PARENT in roles:
        return Student.objects.filter(parent_user=user)
    return Student.objects.none()
