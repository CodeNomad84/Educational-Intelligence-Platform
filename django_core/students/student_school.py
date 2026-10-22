"""Which school does a new or edited student belong to? (ADR-0012 decision 8, changes/0010 stage S2b)

One rule for every creation path (dashboard form, API, Django admin, live import, seed commands), so no path has a
private interpretation and there is NO hidden "the only School" default:

  1. a class is given   -> the school is the class's school; a target school that disagrees is an error;
  2. else a target school -> that school;
  3. else an existing student keeps the school it has (an existing student WITHOUT a school is rejected, S6);
  4. else a non-superuser with exactly ONE active membership -> that school (implied);
  5. else the write is rejected (zero memberships; several memberships without a target; a superuser without a
     target: a superuser may name any school explicitly but is never defaulted).

The result must belong to the user's schools (``school_ids_for_admin``; a superuser: any existing school), and an
existing student's school never changes. Errors are ``StudentSchoolError`` with a stable ``code`` and a message that
does not reveal whether a school the user may not use exists. This module only decides; the callers turn the error
into a form / API error. It changes no visibility rule.
"""
from schools.models import School

from .access import school_ids_for_admin

NO_SCHOOL_ACCESS = 'no_school_access'          # a non-superuser without a valid membership
TARGET_REQUIRED = 'target_school_required'     # several memberships (or a superuser) and nothing names the school
SCHOOL_NOT_ALLOWED = 'school_not_allowed'      # the school is not one of the user's schools (or does not exist)
CLASS_TARGET_MISMATCH = 'class_target_mismatch'
SCHOOL_CHANGE = 'school_change_not_allowed'    # an existing student's school cannot change
STUDENT_WITHOUT_SCHOOL = 'student_without_school'  # S6: an existing school-less student is never adopted here

MESSAGES = {
    NO_SCHOOL_ACCESS: 'Your account is not assigned to a school.',
    TARGET_REQUIRED: 'Choose the school for this student.',
    SCHOOL_NOT_ALLOWED: 'This school is not available to your account.',
    CLASS_TARGET_MISMATCH: 'The chosen class does not belong to the chosen school.',
    SCHOOL_CHANGE: "A student's school cannot be changed.",
    STUDENT_WITHOUT_SCHOOL: 'This student cannot be edited here.',
}


class StudentSchoolError(Exception):
    def __init__(self, code):
        self.code = code
        self.message = MESSAGES[code]
        super().__init__(self.message)


def _as_pk(value):
    """A school id from an int or a numeric string; None for None/''; ``False`` for anything else."""
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return False
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def allowed_school_ids(user):
    """``None`` is never returned: a set of school ids the user may create/edit students in. Superuser: every school
    that exists now; others: ``school_ids_for_admin`` (empty for anonymous, inactive, platform and unassigned)."""
    if user is None or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return set()
    if user.is_superuser:
        return set(School.objects.values_list('pk', flat=True))
    return school_ids_for_admin(user)


def resolve_student_school(user, *, school_class=None, target_school_id=None, existing_school_id=None,
                           is_existing=False):
    """Return the school id for the student or raise ``StudentSchoolError``. See the module docstring.

    ``is_existing``: the write edits a student that already exists. Such a student that has no school (legacy, not yet
    populated by ``backfill_student_school``) is NEVER given one here (S6 requirement 1; before S6 an edit used to
    adopt it for the actor's school): only the backfill command may assign a school to an existing student."""
    allowed = allowed_school_ids(user)
    if not allowed:
        raise StudentSchoolError(NO_SCHOOL_ACCESS)
    if is_existing and existing_school_id is None:
        raise StudentSchoolError(STUDENT_WITHOUT_SCHOOL)
    target = _as_pk(target_school_id)
    if target is False:
        raise StudentSchoolError(SCHOOL_NOT_ALLOWED)

    if school_class is not None:
        chosen = school_class.school_id
        if target is not None and target != chosen:
            raise StudentSchoolError(CLASS_TARGET_MISMATCH)
    elif target is not None:
        chosen = target
    elif existing_school_id is not None:
        chosen = existing_school_id
    elif not user.is_superuser and len(allowed) == 1:
        chosen = next(iter(allowed))
    else:
        raise StudentSchoolError(TARGET_REQUIRED)

    if chosen not in allowed:
        raise StudentSchoolError(SCHOOL_NOT_ALLOWED)
    if existing_school_id is not None and chosen != existing_school_id:
        raise StudentSchoolError(SCHOOL_CHANGE)
    return chosen
