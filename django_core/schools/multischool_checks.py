"""Pre-flight counts for the multi-school gate (changes/0010 S2; used by S3). Read-only, counts only.

``readiness_counts`` adds the multi-school BLOCKERS and diagnostics to ``check_access_switch_ready --multi-school``;
``school_admin_parity`` is the SchoolAdmin section of ``compare_access_parity --multi-school``: what each SchoolAdmin
sees TODAY (everything) versus what the membership scope of S3 would show. Neither changes access.
"""
from collections import Counter

from django.contrib.auth import get_user_model

from students.access import ADMIN, school_ids_for_admin
from students.models import Attendance, Enrollment, Grade, Student

from .membership_audit import classify_memberships
from .models import School

# DECLARED SCHEMA of ``readiness_counts()`` (S2 review K1): every key it returns is either a PROBLEM (a blocker of
# ``check_access_switch_ready --multi-school``) or INFORMATIONAL, and it always returns ALL of them (zero-initialised).
# The command treats a key outside the schema (unclassified) and a declared key that is absent (missing) as blockers,
# i.e. it fails closed; tests read the source of ``readiness_counts`` and compare its behaviour with the schema.
READINESS_PROBLEM_KEYS = (
    'school_admins_without_membership',
    'students_without_school',
    'school_inconsistent_rows',
    'active_memberships_of_platform_admin_users',
    'memberships_invalid',                       # S2 review D3: a dormant grant is exactly what the gate must catch
    'no_school_admin_while_students_exist',      # S2 review D1: the gate must not pass vacuously
    'schools_with_students_but_no_school_admin',  # S2 review E1: per school, not only "no admin at all"
)
MULTI_SCHOOL_BLOCKERS = READINESS_PROBLEM_KEYS   # name used by the commands and older tests
READINESS_INFO_KEYS = (
    'info_schools_count',
    'info_superusers_mapped_to_school_admin_until_s8',
    'info_school_admins_per_school',
)


def readiness_defaults():
    """Shared zero defaults of the readiness schema (a fresh copy each time)."""
    return {**{key: 0 for key in READINESS_PROBLEM_KEYS},
            'info_schools_count': 0, 'info_superusers_mapped_to_school_admin_until_s8': 0,
            'info_school_admins_per_school': {}}


def unclassified_keys(result, problem_keys, info_keys):
    """Keys of ``result`` that are in neither tuple of the declared schema."""
    return sorted(set(result) - set(problem_keys) - set(info_keys))


def missing_keys(result, problem_keys, info_keys):
    """Declared keys that ``result`` does not contain (a producer that stopped reporting a counter)."""
    return sorted((set(problem_keys) | set(info_keys)) - set(result))


def invalid_counter_values(result, problem_keys, info_keys, dict_info_keys=('info_school_admins_per_school',)):
    """Names of declared counters (present in ``result``) whose value is not valid (S2 review K-F2): a counter must be a
    real ``int`` >= 0 (so not None, bool, float, str, list, dict or a negative number); an info counter named in
    ``dict_info_keys`` must be a dict of str -> int >= 0. An invalid value is a blocker, whatever it is."""
    def good_int(value):
        return type(value) is int and value >= 0

    bad = []
    for key in problem_keys:
        if key in result and not good_int(result[key]):
            bad.append(key)
    for key in info_keys:
        if key not in result:
            continue
        value = result[key]
        if key in dict_info_keys:
            ok = type(value) is dict and all(type(k) is str and good_int(v) for k, v in value.items())
        else:
            ok = good_int(value)
        if not ok:
            bad.append(key)
    return sorted(bad)


def invalid_readiness_values(result):
    return invalid_counter_values(result, READINESS_PROBLEM_KEYS, READINESS_INFO_KEYS)


def invalid_parity_values(result):
    return invalid_counter_values(result, PARITY_PROBLEM_KEYS, PARITY_INFO_KEYS, dict_info_keys=())


def unclassified_readiness_keys(result):
    return unclassified_keys(result, READINESS_PROBLEM_KEYS, READINESS_INFO_KEYS)


def missing_readiness_keys(result):
    return missing_keys(result, READINESS_PROBLEM_KEYS, READINESS_INFO_KEYS)



# Every counter ``school_admin_parity()`` can return is either a PROBLEM (the gate fails while it is non-zero) or
# INFORMATIONAL. ``compare_access_parity --multi-school`` derives ``multi_school_passed``, ``verdict`` and the exit code
# from PARITY_PROBLEM_KEYS and treats a counter that is in neither tuple as a problem (fail closed); a test reads the
# source of ``school_admin_parity`` and fails when a counter is added without being classified here (S2 review J1).
PARITY_PROBLEM_KEYS = (
    'students_lost',
    'grades_lost',
    'attendances_lost',
    'no_school_admin_while_students_exist',
    'schools_with_students_but_no_school_admin',
    'memberships_invalid',
)
PARITY_INFO_KEYS = (
    'users_compared',
    'users_with_differences',
    'explained_by_student_without_school',
    'explained_by_student_in_school_without_membership',
    'explained_by_no_valid_membership',
)
PARITY_PROBLEM_TEXT = {
    'students_lost': 'student rows would be hidden from a SchoolAdmin by the membership scope',
    'grades_lost': 'grade rows would be hidden from a SchoolAdmin by the membership scope',
    'attendances_lost': 'attendance rows would be hidden from a SchoolAdmin by the membership scope',
    'no_school_admin_while_students_exist': 'students exist but no SchoolAdmin account exists (the comparison would pass vacuously)',
    'schools_with_students_but_no_school_admin': 'school(s) have students but no valid SchoolAdmin covers them',
    'memberships_invalid': 'active membership(s) of users who no longer qualify',
}


def parity_defaults():
    """Shared zero defaults of the parity schema (a fresh copy each time)."""
    return {key: 0 for key in PARITY_PROBLEM_KEYS + PARITY_INFO_KEYS}


def unaccounted_parity_keys(result):
    """Counters of a ``school_admin_parity()`` result that are in neither PARITY_PROBLEM_KEYS nor PARITY_INFO_KEYS."""
    return unclassified_keys(result, PARITY_PROBLEM_KEYS, PARITY_INFO_KEYS)


def missing_parity_keys(result):
    return missing_keys(result, PARITY_PROBLEM_KEYS, PARITY_INFO_KEYS)


def parity_problems(report, unaccounted, missing=(), invalid=()):
    """Human-readable problems of a parity report; a counter nobody classified, and a declared counter that is no
    longer reported, are problems (fail closed)."""
    problems = [f'{report[key]} {PARITY_PROBLEM_TEXT[key]}' for key in PARITY_PROBLEM_KEYS
                if type(report.get(key)) is int and report[key] > 0]
    if unaccounted:
        problems.append('unclassified parity counter(s) ' + ', '.join(unaccounted)
                        + ': add them to PARITY_PROBLEM_KEYS or PARITY_INFO_KEYS')
    if missing:
        problems.append('declared parity counter(s) not reported: ' + ', '.join(missing))
    if invalid:
        problems.append('parity counter(s) with an invalid value (must be an integer >= 0): ' + ', '.join(invalid))
    return problems


def school_admin_users():
    """Active, non-superuser accounts of group ``SchoolAdmin`` (the accounts S3 scopes by membership)."""
    return list(get_user_model().objects.filter(
        groups__name=ADMIN, is_active=True, is_superuser=False).distinct().order_by('pk'))


def schools_without_admin_cover(admins=None):
    """Ids of the Schools that have students but are covered by NO valid SchoolAdmin (S2 review E1).

    A school is covered when ``school_ids_for_admin`` of at least one active, non-superuser SchoolAdmin account
    contains it, i.e. through an ACTIVE membership of a user who still qualifies (a dual-role, inactive or
    out-of-group user covers nothing). Students without a school are a separate blocker.
    """
    admins = school_admin_users() if admins is None else admins
    covered = set()
    for user in admins:
        covered |= school_ids_for_admin(user)
    with_students = set(Student.objects.filter(school__isnull=False).values_list('school_id', flat=True).distinct())
    return sorted(with_students - covered)


def _inconsistent_school_rows():
    """Rows whose school links disagree (blocker ``school_inconsistent_rows``)."""
    inconsistent = 0
    # a student whose school differs from its class's school
    inconsistent += sum(1 for sid, csid in Student.objects.filter(school_class__isnull=False, school__isnull=False)
                        .values_list('school_id', 'school_class__school_id') if sid != csid)
    # an enrollment whose year's school differs from the student's school, or from its class's school
    for student_school, year_school, class_school in Enrollment.objects.values_list(
            'student__school_id', 'academic_year__school_id', 'school_class__school_id'):
        if (student_school is not None and student_school != year_school) or (
                class_school is not None and class_school != year_school):
            inconsistent += 1
    # a grade or attendance row linked to an enrollment of another student
    for model in (Grade, Attendance):
        inconsistent += sum(1 for sid, esid in model.objects.filter(enrollment__isnull=False)
                            .values_list('student_id', 'enrollment__student_id') if sid != esid)
    return inconsistent


def readiness_counts():
    """The multi-school readiness counters. S2 review K-F1: NO pre-filled defaults. Every declared key is computed by
    ONE assignment ``report['<key>'] = <expression>`` below, so deleting a counter's computation makes the key missing
    (the command then fails closed); a test reads this source and requires the written keys to equal the declared
    schema exactly. Zero defaults are applied by the command only for the OUTPUT, after the checks."""
    report = {}
    users = school_admin_users()
    scopes = [school_ids_for_admin(user) for user in users]
    rows = classify_memberships()
    active = [m for m in rows if m['is_active']]
    per_school = Counter(school_id for ids in scopes for school_id in ids)
    report['no_school_admin_while_students_exist'] = 1 if (not users and Student.objects.exists()) else 0
    report['schools_with_students_but_no_school_admin'] = len(schools_without_admin_cover(users))
    report['school_admins_without_membership'] = sum(1 for ids in scopes if not ids)
    report['students_without_school'] = Student.objects.filter(school__isnull=True).count()
    report['school_inconsistent_rows'] = _inconsistent_school_rows()
    report['active_memberships_of_platform_admin_users'] = sum(1 for m in active if m['user_in_platform_admin'])
    report['memberships_invalid'] = sum(1 for m in active if m['reason'])
    report['info_schools_count'] = School.objects.count()
    report['info_superusers_mapped_to_school_admin_until_s8'] = get_user_model().objects.filter(
        is_superuser=True, is_active=True).count()
    report['info_school_admins_per_school'] = {str(k): v for k, v in sorted(per_school.items())}
    return report


def school_admin_parity():
    """Counts only. A SchoolAdmin sees every student, grade and attendance row today; with S3 only the rows of the
    schools of the valid memberships. S2 review K-F1: no pre-filled defaults; every declared key is computed by ONE
    assignment ``result['<key>'] = <expression>`` (read by a test), see ``readiness_counts``."""
    result = {}
    total_students = Student.objects.count()
    total_grades = Grade.objects.count()
    total_attendances = Attendance.objects.count()
    students_without_school = Student.objects.filter(school__isnull=True).count()
    admins = school_admin_users()
    scopes = [school_ids_for_admin(user) for user in admins]
    kept_students = [Student.objects.filter(school_id__in=ids).count() if ids else 0 for ids in scopes]
    result['no_school_admin_while_students_exist'] = 1 if (not admins and total_students) else 0
    result['memberships_invalid'] = sum(1 for m in classify_memberships() if m['is_active'] and m['reason'])
    result['schools_with_students_but_no_school_admin'] = len(schools_without_admin_cover(admins))
    result['users_compared'] = len(admins)
    result['users_with_differences'] = sum(1 for kept in kept_students if total_students - kept)
    result['students_lost'] = sum(total_students - kept for kept in kept_students)
    result['grades_lost'] = sum(
        total_grades - Grade.objects.filter(student__school_id__in=ids).count() if ids else total_grades
        for ids in scopes)
    result['attendances_lost'] = sum(
        total_attendances - Attendance.objects.filter(student__school_id__in=ids).count() if ids
        else total_attendances for ids in scopes)
    result['explained_by_student_without_school'] = students_without_school * sum(1 for ids in scopes if ids)
    result['explained_by_student_in_school_without_membership'] = sum(
        Student.objects.filter(school__isnull=False).exclude(school_id__in=ids).count() for ids in scopes if ids)
    result['explained_by_no_valid_membership'] = sum(
        total_students - kept for ids, kept in zip(scopes, kept_students) if not ids)
    return result
