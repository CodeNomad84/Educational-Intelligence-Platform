"""Read-only pre-flight for the access switch (ADR-0011, stage 2.2a-4a). Counts only, no personal data.

    manage.py check_access_switch_ready [--json]

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

BLOCKERS = (
    'schools_with_students_but_no_current_year',
    'students_missing_current_enrollment',
    'enrollment_mirror_disagreements',
    'grade_lead_assignments_with_unresolved_year',
    'grade_lead_assignments_year_has_no_academic_year_row',
    'grade_lead_assignments_year_not_current',
    'teacher_assignments_class_without_current_enrollments',
)


class Command(BaseCommand):
    help = "Report whether the enrollment-based access switch would change what staff see (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
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

        r = Counter()
        schools_with_students = set()
        class_mirror = Counter(Student.objects.filter(school_class__isnull=False).values_list('school_class_id', flat=True))
        for pk, school_id, class_id, grade in Student.objects.values_list('pk', 'school_id', 'school_class_id', 'grade'):
            r['students'] += 1
            if school_id is None:
                r['info_students_without_school'] += 1
                continue
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
                r['info_students_class_grade_conflict_not_expected_to_enroll'] += 1
                continue
            rows = enrollments.get(pk, [])
            if not rows:
                r['students_missing_current_enrollment'] += 1
            elif not any(e['school_class_id'] == class_id and e['grade'] == grade for e in rows):
                r['enrollment_mirror_disagreements'] += 1
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

        report = {k: r.get(k, 0) for k in sorted(set(r) | set(BLOCKERS))}
        blockers = {k: report[k] for k in BLOCKERS if report[k]}
        report['verdict'] = 'READY' if not blockers else 'NOT READY'
        report['blockers_nonzero'] = blockers
        report['writes'] = 'none'
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                self.stdout.write(f'{key}: {value}')
        if blockers:
            raise CommandError(f'NOT READY: {sum(blockers.values())} blocker row(s).')
