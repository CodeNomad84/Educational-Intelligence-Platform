"""Per-school module entitlement (Slice A). The ONLY place that answers "may this school use module X today?".

Always-on base (no rows, never asked here): auth/roles, school structure, bulk accounts, grades, attendance, teacher
recommendations, the simple student views, Student 360 and counseling, rule-based risk / ML predict, audit. Optional modules are the keys below; no row (or a row outside its
dates) means OFF. Dependencies are enforced here: a module whose dependency is off counts as off.
Disabled = data retained, reads and writes blocked. Django-side only (the FastAPI token carries no module claim yet);
the Django admin is a known UNGATED surface.
"""
from django.db.models import Q
from django.utils import timezone

ADVISOR_AI = 'advisor_ai'    # staff-facing School Assistant (LLM/RAG). Rule-based risk and ML /predict are base
TUTOR_AI = 'tutor_ai'        # student-facing study assistant / tutor
EXAMS = 'exams'              # not built yet
MISSION = 'mission'          # not built yet
MODULES = (ADVISOR_AI, TUTOR_AI, EXAMS, MISSION)   # the only sellable keys
REQUIRES = {}                # module -> keys it needs; empty today (Student 360 and counseling are base)


def _school_id(school):
    return getattr(school, 'pk', school)


def module_enabled(school, key, on=None):
    """True when ``school`` (a School or its id) has ``key`` switched on at date ``on`` (default today) and every
    module ``key`` requires is on too. Unknown keys, a missing school and anything unexpected are OFF."""
    from .models import SchoolModule

    school_id = _school_id(school)
    if school_id is None or key not in MODULES:
        return False
    on = on or timezone.localdate()
    live = Q(ends_on__isnull=True) | Q(ends_on__gte=on)
    return all(SchoolModule.objects.filter(live, school_id=school_id, module_key=needed, starts_on__lte=on).exists()
               for needed in (*REQUIRES.get(key, ()), key))


def user_school_ids(user):
    """Schools the user belongs to: SchoolAdmin memberships, staff school, own student record, and the schools of the
    students they may see (parents). Empty for anonymous/inactive accounts."""
    if user is None or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return set()
    from students.access import school_ids_for_admin, visible_students
    from students.models import Student

    from .models import SchoolStaff

    ids = set(school_ids_for_admin(user))
    ids |= set(SchoolStaff.objects.filter(user=user).values_list('school_id', flat=True))
    ids |= set(Student.objects.filter(student_user=user).values_list('school_id', flat=True))
    ids |= set(visible_students(user).order_by().values_list('school_id', flat=True).distinct())
    return ids


def module_enabled_for_user(user, key, on=None):
    """Request-level gate: on for at least one of the user's schools. Object-level views must also check the object's
    school with ``module_enabled``. A user with no school (e.g. a superuser) is refused."""
    return any(module_enabled(sid, key, on) for sid in user_school_ids(user))


def enabled_modules_for_user(user):
    """Keys on for at least one of the user's schools (menu hiding only; never a security control)."""
    ids = user_school_ids(user)
    return {key for key in MODULES if any(module_enabled(sid, key) for sid in ids)}


def set_module(school, key, starts_on, ends_on=None, *, actor=None):
    """Create/extend an entitlement and write the audit event. Returns the row. Used by the management command."""
    from . import audit
    from .models import SchoolModule

    if key not in MODULES:
        raise ValueError(f'unknown module {key!r}')
    row, created = SchoolModule.objects.update_or_create(
        school=school, module_key=key, starts_on=starts_on, defaults={'ends_on': ends_on})
    audit.record(actor, audit.MODULE_CHANGE, row, school=school,
                 detail=f'{key}:{ends_on.isoformat() if ends_on else "on"}')
    return row
