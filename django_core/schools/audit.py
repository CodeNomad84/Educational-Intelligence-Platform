"""Audit log writer (2.4). ``record`` stores who/what/when only - never content (no names, notes, phone numbers, texts)."""
from .models import AuditEvent

# Action names (fixed vocabulary).
VIEW_360 = 'view_student_360'
VIEW_DETAIL = 'view_student_detail'
VIEW_CASE = 'view_counselor_case'
SHOW_PARENT_PHONES = 'show_parent_phones'
NOTE_ADD = 'counselor_note_add'
REFERRAL_CREATE = 'referral_create'
REFERRAL_CLOSE = 'referral_close'
GRADE_ADD = 'grade_add'
GRADE_DELETE = 'grade_delete'
RECOMMENDATION_ADD = 'recommendation_add'
STAFF_ACCOUNT_CREATE = 'staff_account_create'
STUDENT_ACCOUNT_CREATE = 'student_account_create'


def record(user, action, obj=None, *, school=None, detail=''):
    """Append one event. ``school`` defaults to ``obj.school_id`` (a Student) or the student's school."""
    from students.access import roles_for

    school_id = getattr(school, 'pk', school)
    if school_id is None and obj is not None:
        school_id = getattr(obj, 'school_id', None) or getattr(getattr(obj, 'student', None), 'school_id', None) \
            or getattr(getattr(obj, 'referral', None), 'school_id', None)
    if school_id is None:
        raise ValueError('audit event without a school')
    return AuditEvent.objects.create(
        user=user if getattr(user, 'pk', None) else None, username=getattr(user, 'username', '')[:150],
        roles=','.join(sorted(roles_for(user)))[:120], school_id=school_id, action=action,
        object_type=type(obj).__name__ if obj is not None else '', object_id=str(getattr(obj, 'pk', '') or ''),
        detail=detail[:40])
