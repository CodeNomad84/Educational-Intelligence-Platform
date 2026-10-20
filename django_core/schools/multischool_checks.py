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

MULTI_SCHOOL_BLOCKERS = (
    'school_admins_without_membership',
    'students_without_school',
    'school_inconsistent_rows',
    'active_memberships_of_platform_admin_users',
    'memberships_invalid',                       # S2 review D3: a dormant grant is exactly what the gate must catch
    'no_school_admin_while_students_exist',      # S2 review D1: the gate must not pass vacuously
    'schools_with_students_but_no_school_admin',  # S2 review E1: per school, not only "no admin at all"
)


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


def unaccounted_parity_keys(result):
    """Counters of a ``school_admin_parity()`` result that are in neither PARITY_PROBLEM_KEYS nor PARITY_INFO_KEYS."""
    return sorted(set(result) - set(PARITY_PROBLEM_KEYS) - set(PARITY_INFO_KEYS))


def parity_problems(report, unaccounted):
    """Human-readable problems of a parity report; a counter nobody classified is a problem (fail closed)."""
    problems = [f'{report[key]} {PARITY_PROBLEM_TEXT[key]}' for key in PARITY_PROBLEM_KEYS if report.get(key)]
    if unaccounted:
        problems.append('unclassified parity counter(s) ' + ', '.join(unaccounted)
                        + ': add them to PARITY_PROBLEM_KEYS or PARITY_INFO_KEYS')
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


def readiness_counts():
    r = Counter()
    users = school_admin_users()
    if not users and Student.objects.exists():
        r['no_school_admin_while_students_exist'] = 1
    r['schools_with_students_but_no_school_admin'] = len(schools_without_admin_cover(users))
    per_school = Counter()
    for user in users:
        ids = school_ids_for_admin(user)
        if not ids:
            r['school_admins_without_membership'] += 1
        for school_id in ids:
            per_school[school_id] += 1
    r['students_without_school'] = Student.objects.filter(school__isnull=True).count()

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
    r['school_inconsistent_rows'] = inconsistent

    rows = classify_memberships()
    active = [m for m in rows if m['is_active']]
    r['active_memberships_of_platform_admin_users'] = sum(1 for m in active if m['user_in_platform_admin'])
    r['memberships_invalid'] = sum(1 for m in active if m['reason'])  # BLOCKER since the S2 review (D3)
    r['info_schools_count'] = School.objects.count()
    r['info_superusers_mapped_to_school_admin_until_s8'] = get_user_model().objects.filter(
        is_superuser=True, is_active=True).count()
    report = {k: 0 for k in MULTI_SCHOOL_BLOCKERS}
    report.update(r)
    report['info_school_admins_per_school'] = {str(k): v for k, v in sorted(per_school.items())}
    return report


def school_admin_parity():
    """Counts only. A SchoolAdmin sees every student, grade and attendance row today; with S3 only the rows of the
    schools of the valid memberships."""
    total_students = Student.objects.count()
    total_grades = Grade.objects.count()
    total_attendances = Attendance.objects.count()
    out = Counter()
    admins = school_admin_users()
    if not admins and total_students:
        out['no_school_admin_while_students_exist'] = 1  # S2 review D1: no vacuous pass
    out['memberships_invalid'] = sum(1 for m in classify_memberships() if m['is_active'] and m['reason'])  # D3
    out['schools_with_students_but_no_school_admin'] = len(schools_without_admin_cover(admins))  # E1
    for user in admins:
        ids = school_ids_for_admin(user)
        out['users_compared'] += 1
        kept_students = Student.objects.filter(school_id__in=ids).count() if ids else 0
        lost = total_students - kept_students
        if lost:
            out['users_with_differences'] += 1
        out['students_lost'] += lost
        if ids:
            out['grades_lost'] += total_grades - Grade.objects.filter(student__school_id__in=ids).count()
            out['attendances_lost'] += total_attendances - Attendance.objects.filter(
                student__school_id__in=ids).count()
            out['explained_by_student_without_school'] += Student.objects.filter(school__isnull=True).count()
            out['explained_by_student_in_school_without_membership'] += Student.objects.filter(
                school__isnull=False).exclude(school_id__in=ids).count()
        else:
            out['grades_lost'] += total_grades
            out['attendances_lost'] += total_attendances
            out['explained_by_no_valid_membership'] += lost
    return dict(out)
