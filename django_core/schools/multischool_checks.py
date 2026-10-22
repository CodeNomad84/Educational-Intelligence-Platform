"""Pre-flight counts for the multi-school gate (changes/0010 S2; used by S3). Read-only, counts only.

``readiness_counts`` adds the multi-school BLOCKERS and diagnostics to ``check_access_switch_ready --multi-school``;
``school_admin_parity`` is the SchoolAdmin section of ``compare_access_parity --multi-school``: a STRICT check (owner
decision F6, S3 gate) of what each SchoolAdmin really sees (``visible_students/grades/attendances``) against an
independently computed expectation from the memberships. Neither changes access.
"""
from collections import Counter

from django.contrib.auth import get_user_model

from students import access
from students.access import ADMIN, GRADE_LEAD, PARENT, PLATFORM_ADMIN, TEACHER, school_ids_for_admin
from students.models import Attendance, Enrollment, Grade, Student

from .membership_audit import classify_memberships
from .models import School, SchoolMembership

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
    'students_leaked',            # a SchoolAdmin sees a student outside the schools of their valid memberships
    'grades_leaked',
    'attendances_leaked',
    'students_locked_out',        # a SchoolAdmin does not see a student inside those schools
    'grades_locked_out',
    'attendances_locked_out',
    'school_admins_without_membership',   # an active SchoolAdmin whose valid memberships give no school at all
    'superuser_scope_wrong',      # the temporary superuser branch (until S8): an active one sees all, an inactive one none
    'no_school_admin_while_students_exist',
    'schools_with_students_but_no_school_admin',
    'memberships_invalid',
)
PARITY_INFO_KEYS = (
    'users_compared',
    'superusers_compared',
    'users_with_other_grants_leak_check_skipped',   # the account also holds another role: its extra rows are legitimate
    'info_other_school_students_hidden',            # rows of schools the admin does not administer, correctly hidden
    'info_other_school_grades_hidden',
    'info_other_school_attendances_hidden',
)
PARITY_PROBLEM_TEXT = {
    'students_leaked': 'student row(s) visible to a SchoolAdmin outside the schools of their memberships (LEAK)',
    'grades_leaked': 'grade row(s) visible to a SchoolAdmin outside the schools of their memberships (LEAK)',
    'attendances_leaked': 'attendance row(s) visible to a SchoolAdmin outside the schools of their memberships (LEAK)',
    'students_locked_out': 'student row(s) of a SchoolAdmin\'s own schools that the account cannot see (LOCKOUT)',
    'grades_locked_out': 'grade row(s) of a SchoolAdmin\'s own schools that the account cannot see (LOCKOUT)',
    'attendances_locked_out': 'attendance row(s) of a SchoolAdmin\'s own schools that the account cannot see (LOCKOUT)',
    'school_admins_without_membership': 'active SchoolAdmin account(s) without any valid membership (they see nothing)',
    'superuser_scope_wrong': 'superuser account(s) whose scope differs from the temporary rule (active: all rows, inactive: none)',
    'no_school_admin_while_students_exist': 'students exist but no SchoolAdmin account exists (the comparison would pass vacuously)',
    'schools_with_students_but_no_school_admin': 'school(s) have students, classes or academic years but no valid SchoolAdmin covers them',
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
    """Ids of the Schools that have students, classes or academic years but are covered by NO valid SchoolAdmin
    (S2 review E1; R-b, S3: a school with only classes or academic years needs an administrator too).

    A school is covered when ``school_ids_for_admin`` of at least one active, non-superuser SchoolAdmin account
    contains it, i.e. through an ACTIVE membership of a user who still qualifies (a dual-role, inactive or
    out-of-group user covers nothing). Students without a school are a separate blocker.
    """
    admins = school_admin_users() if admins is None else admins
    covered = set()
    for user in admins:
        covered |= school_ids_for_admin(user)
    from .models import AcademicYear, SchoolClass   # lazy: the module header imports only the School model

    with_content = set(Student.objects.filter(school__isnull=False).values_list('school_id', flat=True).distinct())
    with_content |= set(SchoolClass.objects.values_list('school_id', flat=True).distinct())
    with_content |= set(AcademicYear.objects.values_list('school_id', flat=True).distinct())
    return sorted(with_content - covered)


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


def _expected_school_ids(user):
    """The schools a SchoolAdmin may administer, computed WITHOUT ``school_ids_for_admin``: one join over the membership
    table (active membership, active non-superuser account in group SchoolAdmin and not in PlatformAdmin)."""
    return set(SchoolMembership.objects.filter(
        user=user, is_active=True, user__is_active=True, user__is_superuser=False, user__groups__name=ADMIN,
    ).exclude(user__groups__name=PLATFORM_ADMIN).values_list('school_id', flat=True))


def strict_scope_comparison():
    """F6: for every SchoolAdmin-group account the REAL ``visible_*`` sets against an independent expectation (school of the
    row in the member schools, computed here from the row maps, not by arithmetic on ``visible_*``). Row outside the
    expectation = LEAK, expected row missing = LOCKOUT, rows of other schools that are hidden = INFO. An account that
    also holds another role legitimately sees more, so its leak check is skipped (its lockout check still runs).
    Superusers (temporary branch until S8) are checked separately: active = every row, inactive = none."""
    row_school = {
        'students': dict(Student.objects.values_list('pk', 'school_id')),
        'grades': dict(Grade.objects.values_list('pk', 'student__school_id')),
        'attendances': dict(Attendance.objects.values_list('pk', 'student__school_id')),
    }
    visible = {'students': access.visible_students, 'grades': access.visible_grades,
               'attendances': access.visible_attendances}
    User = get_user_model()
    other_roles = (TEACHER, GRADE_LEAD, PARENT)
    totals = Counter()

    def actual(kind, user):
        return set(visible[kind](user).values_list('pk', flat=True))

    for user in User.objects.filter(groups__name=ADMIN, is_superuser=False).distinct().order_by('pk'):
        school_ids = _expected_school_ids(user)
        skip_leaks = user.groups.filter(name__in=other_roles).exists()
        totals['users_compared'] += 1
        totals['school_admins_without_membership'] += 1 if (user.is_active and not school_ids) else 0
        totals['users_with_other_grants_leak_check_skipped'] += 1 if skip_leaks else 0
        for kind, schools in row_school.items():
            expected = {pk for pk, school_id in schools.items() if school_id in school_ids}
            seen = actual(kind, user)
            totals[f'{kind}_locked_out'] += len(expected - seen)
            if not skip_leaks:
                totals[f'{kind}_leaked'] += len(seen - expected)
            totals[f'info_other_school_{kind}_hidden'] += len(set(schools) - expected - seen)

    for user in User.objects.filter(is_superuser=True).order_by('pk'):
        totals['superusers_compared'] += 1
        wrong = False
        for kind, schools in row_school.items():
            seen = actual(kind, user)
            if user.is_active:
                wrong = wrong or seen != set(schools)
            elif not user.groups.filter(name__in=other_roles).exists():
                wrong = wrong or bool(seen)
        totals['superuser_scope_wrong'] += 1 if wrong else 0
    return totals


def school_admin_parity():
    """Counts only (strict F6 check, see ``strict_scope_comparison``). S2 review K-F1: no pre-filled defaults; every
    declared key is computed by ONE assignment ``result['<key>'] = <expression>`` (read by a test), see
    ``readiness_counts``."""
    result = {}
    admins = school_admin_users()
    totals = strict_scope_comparison()
    result['no_school_admin_while_students_exist'] = 1 if (not admins and Student.objects.exists()) else 0
    result['memberships_invalid'] = sum(1 for m in classify_memberships() if m['is_active'] and m['reason'])
    result['schools_with_students_but_no_school_admin'] = len(schools_without_admin_cover(admins))
    result['users_compared'] = totals['users_compared']
    result['superusers_compared'] = totals['superusers_compared']
    result['users_with_other_grants_leak_check_skipped'] = totals['users_with_other_grants_leak_check_skipped']
    result['students_leaked'] = totals['students_leaked']
    result['grades_leaked'] = totals['grades_leaked']
    result['attendances_leaked'] = totals['attendances_leaked']
    result['students_locked_out'] = totals['students_locked_out']
    result['grades_locked_out'] = totals['grades_locked_out']
    result['attendances_locked_out'] = totals['attendances_locked_out']
    result['school_admins_without_membership'] = totals['school_admins_without_membership']
    result['superuser_scope_wrong'] = totals['superuser_scope_wrong']
    result['info_other_school_students_hidden'] = totals['info_other_school_students_hidden']
    result['info_other_school_grades_hidden'] = totals['info_other_school_grades_hidden']
    result['info_other_school_attendances_hidden'] = totals['info_other_school_attendances_hidden']
    return result
