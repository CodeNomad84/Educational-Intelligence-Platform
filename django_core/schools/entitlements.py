"""Per-school module entitlement (Slice A). The ONLY place that answers "may this school use module X today?".

Always-on base (no rows, never asked here): auth/roles, school structure, bulk accounts, grades, attendance, teacher
recommendations, the simple student views, Student 360 and counseling, rule-based risk / ML predict, audit. Optional modules are the keys below; no row (or a row outside its
dates) means OFF. Dependencies are enforced here: a module whose dependency is off counts as off.
Disabled = data retained, reads and writes blocked. Django-side only (the FastAPI token carries no module claim yet).
The Django admin is NOT an ungated surface: since C-A (S9, 2026-11-01) it opens only for platform operators and shows
platform tables only (school data is not registered; `schools/admin.py`, `schools/test_admin_closure.py`).
"""
from django.db.models import Q
from django.utils import timezone

ADVISOR_AI = 'advisor_ai'    # staff-facing School Assistant (LLM/RAG). Rule-based risk and ML /predict are base
TUTOR_AI = 'tutor_ai'        # student-facing study assistant / tutor
EXAMS = 'exams'              # teacher question bank + student practice player (Slice 1)
MISSION = 'mission'          # mission-based selection (observations, weights, reports)
MODULES = (ADVISOR_AI, TUTOR_AI, EXAMS, MISSION)   # the only sellable keys
REQUIRES = {}                # module -> keys it needs; empty today (Student 360 and counseling are base)


BUILT = (ADVISOR_AI, TUTOR_AI, EXAMS, MISSION)   # the others show "coming soon" instead of the unlock text
TRIAL, LICENSED = 'trial', 'licensed'
ACTIVE_TRIAL, ACTIVE_LICENSED, LOCKED = 'active_trial', 'active_licensed', 'locked'
NOTICE_DAYS = 14


def _school_id(school):
    return getattr(school, 'pk', school)


def _active_rows(school_id, key, on):
    from .models import SchoolModule

    return SchoolModule.objects.filter(Q(ends_on__isnull=True) | Q(ends_on__gte=on),
                                       school_id=school_id, module_key=key, starts_on__lte=on)


def module_state(school, key, on=None):
    """``active_licensed`` | ``active_trial`` | ``locked`` (no row, expired, not started, unknown key, missing school or a
    required module that is locked). A licensed row wins over a trial row."""
    school_id = _school_id(school)
    if school_id is None or key not in MODULES:
        return LOCKED
    on = on or timezone.localdate()
    states = []
    for needed in (*REQUIRES.get(key, ()), key):
        kinds = set(_active_rows(school_id, needed, on).values_list('kind', flat=True))
        if not kinds:
            return LOCKED
        states.append(LICENSED if LICENSED in kinds else TRIAL)
    return ACTIVE_TRIAL if TRIAL in states else ACTIVE_LICENSED


def module_enabled(school, key, on=None):
    """True when ``school`` (a School or its id) has ``key`` switched on at date ``on`` (default today), as a trial or
    licensed, and every module ``key`` requires is on too. Unknown keys, a missing school and anything unexpected are OFF."""
    return module_state(school, key, on) != LOCKED


def trial_days_left(school, key, on=None):
    """Days until an ACTIVE trial ends (0 on its last day); None when there is no active trial for the module."""
    school_id = _school_id(school)
    if school_id is None or key not in MODULES:
        return None
    on = on or timezone.localdate()
    if module_state(school_id, key, on) != ACTIVE_TRIAL:
        return None
    end = _active_rows(school_id, key, on).filter(kind=TRIAL).values_list('ends_on', flat=True).first()
    return (end - on).days if end else None


def trial_notices(school_ids, on=None):
    """SchoolAdmin banner data: ``[(module_key, 'expiring', days_left) | (module_key, 'ended', days_ago)]`` for trials with
    <= NOTICE_DAYS left, or that ended <= NOTICE_DAYS ago and have no active row now."""
    from .models import SchoolModule

    on = on or timezone.localdate()
    notices = []
    for row in SchoolModule.objects.filter(school_id__in=school_ids, kind=TRIAL).order_by('module_key'):
        if module_state(row.school_id, row.module_key, on) == LOCKED and row.ends_on and 0 < (on - row.ends_on).days <= NOTICE_DAYS:
            notices.append((row.module_key, 'ended', (on - row.ends_on).days))
        elif row.starts_on <= on <= row.ends_on and (row.ends_on - on).days <= NOTICE_DAYS:
            notices.append((row.module_key, 'expiring', (row.ends_on - on).days))
    return notices


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


def set_module(school, key, starts_on, ends_on=None, *, actor=None, kind=LICENSED):
    """Create/extend an entitlement and write the audit event. Returns the row. Used by the management command (operator
    only; SchoolAdmins have no path to it). A trial is unique per (school, module): calling again extends that row."""
    from . import audit
    from .models import SchoolModule

    if key not in MODULES:
        raise ValueError(f'unknown module {key!r}')
    if kind == TRIAL:
        if ends_on is None:
            raise ValueError('a trial needs an end date')
        row = SchoolModule.objects.filter(school=school, module_key=key, kind=TRIAL).first()
        if row is None:
            row = SchoolModule.objects.create(school=school, module_key=key, kind=TRIAL, starts_on=starts_on, ends_on=ends_on)
        else:
            row.ends_on = ends_on
            row.save(update_fields=['ends_on'])
    else:
        row, created = SchoolModule.objects.update_or_create(
            school=school, module_key=key, starts_on=starts_on, defaults={'ends_on': ends_on, 'kind': kind})
    audit.record(actor, audit.MODULE_CHANGE, row, school=school, detail=module_change_detail(row))
    return row


def module_change_detail(row):
    """Fixed-shape audit detail: ``<key>:<kind>:<end date or open>`` (no content)."""
    return f'{row.module_key}:{row.kind}:{row.ends_on.isoformat() if row.ends_on else "open"}'[:40]
