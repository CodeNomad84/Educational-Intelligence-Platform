"""Read-only pre-flight for the access switch (ADR-0011, stage 2.2a-4a). Counts only, no personal data.

    manage.py check_access_switch_ready [--json]

The multi-school gate (changes/0010, S3) is a SEPARATE opt-in run: `--multi-school`. Without it the output ends with
"multi-school checks: NOT RUN" and READY says nothing about the multi-school scope. The S3 gate requires BOTH this
command and `compare_access_parity` to be run WITH `--multi-school` and to pass. Machine check: with `--json` BOTH outputs
must contain `"multi_school_checks_run": true` AND `"multi_school_passed": true`, and both commands must exit 0 (a bare
READY or an exit code of 0 is not enough; `multi_school_passed` is false in every failing or not-run output).
Verdict READY only when every BLOCKER is zero; otherwise NOT READY and the exit code is 1 (owner D-4-6 policy).
After the switch (4c) a Grade Lead or Subject Teacher sees only students with a CURRENT enrollment, so each
blocker is a place where staff would see fewer students than today.
"""
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, TeacherAssignment
from schools.vocabulary import SUBJECT_KEYS
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, Student

# DECLARED SCHEMA of ``access_switch_counts()`` (R-h / K-F6, the same discipline as the multi-school counters): every key it
# returns is a PROBLEM (a blocker) or INFORMATIONAL; an unclassified, a missing or an invalid (not int >= 0) counter is a
# blocker itself. A source test (``AccessSwitchCountsSchemaTests``) reads the function and fails when a key is written
# that is not declared, or declared but never written.
BLOCKERS = (
    'schools_with_students_but_no_current_year',
    'students_missing_current_enrollment',
    'students_class_grade_conflict_would_vanish',
    'enrollment_mirror_disagreements',
    'grade_lead_assignments_with_unresolved_year',
    'grade_lead_assignments_year_has_no_academic_year_row',
    'grade_lead_assignments_year_not_current',
    'teacher_assignments_class_without_current_enrollments',
)
PROBLEM_KEYS = BLOCKERS
INFO_KEYS = (
    'students',
    'info_students_without_class_invisible_to_staff',
    'info_students_with_stale_or_unresolved_class_year',
    'info_continuing_students_without_current_enrollment',
    'grade_lead_assignments_active',
    'info_teacher_assignments_with_blank_or_invalid_subject_grant_nothing',
    'teacher_assignments_active',
)


def access_switch_counts():
    """Raw 4c counters (R-h / K-F6). Every key is declared in PROBLEM_KEYS or INFO_KEYS; the command treats an
    unclassified, missing or invalid counter as a blocker (fail closed); a source test reads this function."""
    current = {y['school_id']: y for y in AcademicYear.objects.filter(is_current=True).values(
        'pk', 'school_id', 'code')}
    years = {(y['school_id'], y['code']): y for y in AcademicYear.objects.values('pk', 'school_id', 'code', 'is_current')}
    classes = {
        pk: (school_id, normalize_academic_year(year), grade, active)
        for pk, school_id, year, grade, active in SchoolClass.objects.values_list(
            'pk', 'school_id', 'academic_year', 'grade', 'is_active')
    }
    enrollments = defaultdict(list)  # student_id -> current open enrollments
    class_enrolled = Counter()
    for e in Enrollment.objects.filter(
            ended_on__isnull=True, status__in=CURRENT_STATUSES, academic_year__is_current=True,
    ).values('student_id', 'school_class_id', 'grade'):
        enrollments[e['student_id']].append(e)
        if e['school_class_id']:
            class_enrolled[e['school_class_id']] += 1

    r = Counter()   # accumulator only; the REPORT below has no pre-filled defaults (S3-1 F1, like readiness_counts)
    schools_with_students = set()
    class_mirror = Counter(Student.objects.filter(school_class__isnull=False).values_list('school_class_id', flat=True))
    for pk, school_id, class_id, grade in Student.objects.values_list('pk', 'school_id', 'school_class_id', 'grade'):
        r['students'] += 1
        schools_with_students.add(school_id)
        if class_id is None:
            r['info_students_without_class_invisible_to_staff'] += 1
            continue
        class_school, (status, code), class_grade, active = classes[class_id]
        year = current.get(school_id)
        if year is None:
            continue  # counted per school below
        if status != RESOLVED or code != year['code']:
            r['info_students_with_stale_or_unresolved_class_year'] += 1
            continue
        if class_grade is not None and class_grade != grade:
            r['students_class_grade_conflict_would_vanish'] += 1  # sync refuses to enroll: staff would lose them
            continue
        rows = enrollments.get(pk, [])
        if not rows:
            r['students_missing_current_enrollment'] += 1
        elif not any(e['school_class_id'] == class_id and e['grade'] == grade for e in rows):
            r['enrollment_mirror_disagreements'] += 1
    # Diagnostic (not a blocker: both rules already hide these): students whose latest earlier enrollment says
    # they continue (promoted/retained) but who have no current enrollment. Typical causes: a mirror class of a
    # past year, an unresolved class year, no class, a class-grade conflict.
    last_status = {}
    for student_id, status, _start in Enrollment.objects.filter(academic_year__is_current=False).order_by(
            'academic_year__start_date').values_list('student_id', 'status', 'academic_year__start_date'):
        last_status[student_id] = status
    for student_id, status in last_status.items():
        if status in ('promoted', 'retained') and student_id not in enrollments:
            r['info_continuing_students_without_current_enrollment'] += 1
    r['schools_with_students_but_no_current_year'] = sum(1 for s in schools_with_students if s not in current)

    for a in GradeLeadAssignment.objects.filter(is_active=True).values('school_id', 'academic_year'):
        r['grade_lead_assignments_active'] += 1
        status, code = normalize_academic_year(a['academic_year'])
        if status != RESOLVED:
            r['grade_lead_assignments_with_unresolved_year'] += 1
        elif (a['school_id'], code) not in years:
            r['grade_lead_assignments_year_has_no_academic_year_row'] += 1
        elif not years[(a['school_id'], code)]['is_current']:
            r['grade_lead_assignments_year_not_current'] += 1

    for class_id, subject in TeacherAssignment.objects.filter(school_class__is_active=True).values_list(
            'school_class_id', 'subject'):
        if subject not in SUBJECT_KEYS:
            r['info_teacher_assignments_with_blank_or_invalid_subject_grant_nothing'] += 1
            continue
        r['teacher_assignments_active'] += 1
        if class_mirror[class_id] > 0 and class_enrolled[class_id] == 0:  # students linked, none enrolled
            r['teacher_assignments_class_without_current_enrollments'] += 1
    report = {}
    report['schools_with_students_but_no_current_year'] = r['schools_with_students_but_no_current_year']
    report['students_missing_current_enrollment'] = r['students_missing_current_enrollment']
    report['students_class_grade_conflict_would_vanish'] = r['students_class_grade_conflict_would_vanish']
    report['enrollment_mirror_disagreements'] = r['enrollment_mirror_disagreements']
    report['grade_lead_assignments_with_unresolved_year'] = r['grade_lead_assignments_with_unresolved_year']
    report['grade_lead_assignments_year_has_no_academic_year_row'] = r['grade_lead_assignments_year_has_no_academic_year_row']
    report['grade_lead_assignments_year_not_current'] = r['grade_lead_assignments_year_not_current']
    report['teacher_assignments_class_without_current_enrollments'] = r['teacher_assignments_class_without_current_enrollments']
    report['students'] = r['students']
    report['info_students_without_class_invisible_to_staff'] = r['info_students_without_class_invisible_to_staff']
    report['info_students_with_stale_or_unresolved_class_year'] = r['info_students_with_stale_or_unresolved_class_year']
    report['info_continuing_students_without_current_enrollment'] = r['info_continuing_students_without_current_enrollment']
    report['grade_lead_assignments_active'] = r['grade_lead_assignments_active']
    report['info_teacher_assignments_with_blank_or_invalid_subject_grant_nothing'] = r['info_teacher_assignments_with_blank_or_invalid_subject_grant_nothing']
    report['teacher_assignments_active'] = r['teacher_assignments_active']
    return report


class Command(BaseCommand):
    help = "Report whether the enrollment-based access switch would change what staff see (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')
        parser.add_argument(
            '--multi-school', action='store_true',
            help='also check the multi-school gate (changes/0010 S2): SchoolAdmins without a membership, students '
                 'without a school, inconsistent school links, active memberships of PlatformAdmin users. Default '
                 'output and verdict are unchanged without this flag.')

    def handle(self, *args, **opts):
        raw = access_switch_counts()
        r = Counter(raw)
        from schools.multischool_checks import invalid_counter_values, missing_keys, unclassified_keys
        blocker_keys = BLOCKERS
        extra = {}
        # R-h: the 4c counters are checked against their declared schema on the RAW result, like the multi-school ones
        unclassified = unclassified_keys(raw, PROBLEM_KEYS, INFO_KEYS)
        missing = missing_keys(raw, PROBLEM_KEYS, INFO_KEYS)
        invalid = invalid_counter_values(raw, PROBLEM_KEYS, INFO_KEYS, dict_info_keys=())
        if opts['multi_school']:
            from schools.multischool_checks import (
                READINESS_PROBLEM_KEYS, invalid_readiness_values, missing_readiness_keys, readiness_counts,
                readiness_defaults, unclassified_readiness_keys)
            extra = readiness_counts()
            # all checks run on the RAW result; the zero defaults only complete the OUTPUT afterwards (S2 review K-F1)
            unclassified = sorted(set(unclassified) | set(unclassified_readiness_keys(extra)))
            missing = sorted(set(missing) | set(missing_readiness_keys(extra)))
            invalid = sorted(set(invalid) | set(invalid_readiness_values(extra)))
            # K-F4: a 4c key produced by the readiness counters is unclassified THERE (the schemas are disjoint), so
            # ``report.update(extra)`` can never silently overwrite a 4c counter
            extra = {**readiness_defaults(), **extra}
            blocker_keys = BLOCKERS + READINESS_PROBLEM_KEYS
        report = {k: r.get(k, 0) for k in sorted(set(r) | set(BLOCKERS))}
        report.update(extra)
        # only a valid (int >= 0) value can be a blocker count; an invalid value is a blocker of its own (K-F2)
        blockers = {k: report[k] for k in blocker_keys
                    if type(report.get(k)) is int and report[k] > 0}
        if invalid:
            report['invalid_counters'] = invalid
            blockers['invalid_counter_values'] = len(invalid)
        # S2 review K1: a counter outside the declared schema, and a declared counter that is no longer reported,
        # are blockers themselves (fail closed), whatever their value
        if unclassified:
            report['unclassified_counters'] = unclassified
            blockers['unclassified_counters'] = len(unclassified)
        if missing:
            report['missing_counters'] = missing
            blockers['missing_counters'] = len(missing)
        report['verdict'] = 'READY' if not blockers else 'NOT READY'
        report['blockers_nonzero'] = blockers
        report['writes'] = 'none'
        status = 'RUN' if opts['multi_school'] else 'NOT RUN'
        report['multi_school_checks'] = status
        report['multi_school_checks_run'] = bool(opts['multi_school'])
        # S3 gate (H1): true only when the multi-school checks RAN and every blocker is zero; never true without the flag
        report['multi_school_passed'] = bool(opts['multi_school']) and not blockers
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                if key not in ('multi_school_checks', 'multi_school_checks_run', 'multi_school_passed'):
                    self.stdout.write(f'{key}: {value}')
            self.stdout.write(f'multi-school checks: {status}')
            self.stdout.write(f"multi-school passed: {'true' if report['multi_school_passed'] else 'false'}")
        if blockers:
            raise CommandError(f'NOT READY: {sum(blockers.values())} blocker row(s).')
