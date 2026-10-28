"""Which school does a new or edited student belong to? (ADR-0012 decision 8, changes/0010 stage S2b)

One rule for every creation path (dashboard form, API, Django admin, live import, seed commands), so no path has a
private interpretation and there is NO hidden "the only School" default:

  1. a class is given   -> the school is the class's school; a target school that disagrees is an error;
  2. else a target school -> that school;
  3. else an existing student keeps the school it has;
  4. else a non-superuser with exactly ONE active membership -> that school (implied);
  5. else the write is rejected (zero memberships; several memberships without a target; a superuser without a
     target: a superuser is the platform account and has no school: rejected).

The result must belong to the user's schools (``school_ids_for_admin``), and an
existing student's school never changes. Errors are ``StudentSchoolError`` with a stable ``code`` and a message that
does not reveal whether a school the user may not use exists. This module only decides; the callers turn the error
into a form / API error. It changes no visibility rule.
"""
from schools.models import School

from .access import school_ids_for_admin

# The ONE message for a national id that cannot be registered. It is identical whether the id belongs to a student of the same
# school or of another school, and says nothing about either (independent review 0027 finding 3). National_id is globally unique
# until S7, so the refusal itself cannot be hidden; the wording must not distinguish the cases.
NATIONAL_ID_REFUSED = 'این کد ملی قابل ثبت نیست.'

NO_SCHOOL_ACCESS = 'no_school_access'          # a non-superuser without a valid membership
TARGET_REQUIRED = 'target_school_required'     # several memberships (or a superuser) and nothing names the school
SCHOOL_NOT_ALLOWED = 'school_not_allowed'      # the school is not one of the user's schools (or does not exist)
CLASS_TARGET_MISMATCH = 'class_target_mismatch'
SCHOOL_CHANGE = 'school_change_not_allowed'    # an existing student's school cannot change

MESSAGES = {
    NO_SCHOOL_ACCESS: 'Your account is not assigned to a school.',
    TARGET_REQUIRED: 'Choose the school for this student.',
    SCHOOL_NOT_ALLOWED: 'This school is not available to your account.',
    CLASS_TARGET_MISMATCH: 'The chosen class does not belong to the chosen school.',
    SCHOOL_CHANGE: "A student's school cannot be changed.",
}


class StudentSchoolError(Exception):
    def __init__(self, code):
        self.code = code
        self.message = MESSAGES[code]
        super().__init__(self.message)


def school_column_is_nullable():
    """The REAL nullability of students_student.school_id, read from the database (not from the model: after
    ``migrate students 0015 --fake`` the model says NOT NULL while the column may still be nullable)."""
    from django.db import connection
    from .models import Student
    with connection.cursor() as cursor:
        columns = {c.name: c.null_ok for c in connection.introspection.get_table_description(
            cursor, Student._meta.db_table)}
    return bool(columns[Student._meta.get_field('school').column])


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
    """``None`` is never returned: a set of school ids the user may create/edit students in: ``school_ids_for_admin``
    (empty for anonymous, inactive, superuser/platform and unassigned accounts)."""
    if user is None or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return set()
    return school_ids_for_admin(user)


def resolve_student_school(user, *, school_class=None, target_school_id=None, existing_school_id=None):
    """Return the school id for the student or raise ``StudentSchoolError``. See the module docstring."""
    allowed = allowed_school_ids(user)
    if not allowed:
        raise StudentSchoolError(NO_SCHOOL_ACCESS)
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


def class_choices(user, *, keep_pk=None):
    """Classes the user may pick for a student: active classes of the user's own schools (plus ``keep_pk``, the class the
    student already has, when it is in one of those schools). Other schools' classes do not exist for the user."""
    from django.db.models import Q

    from schools.models import SchoolClass

    schools = allowed_school_ids(user)
    return SchoolClass.objects.filter(Q(is_active=True) | Q(pk=keep_pk), school_id__in=schools)


def parent_choices(user, *, keep_pk=None):
    """Stopgap (changes/0010 D-MS-6): parent accounts already linked to a student of the user's schools (plus the
    student's current parent). A first-time link of a new parent is a platform duty until the link flow exists."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from .models import Student

    schools = allowed_school_ids(user)
    linked = Student.objects.filter(school_id__in=schools, parent_user__isnull=False).values('parent_user_id')
    return get_user_model().objects.filter(Q(pk__in=linked) | Q(pk=keep_pk), is_active=True).order_by('username') \
        if schools else get_user_model().objects.none()


def national_id_taken(national_id, exclude_pk=None):
    """True when ANY student (any school) already has this national id. Used only to refuse a duplicate with the one fixed message
    ``NATIONAL_ID_REFUSED``; nothing about the other student is returned (review 0027 F3)."""
    from .models import Student

    rows = Student.objects.filter(national_id=national_id)
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    return rows.exists()
