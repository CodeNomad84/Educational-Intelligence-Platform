"""Read-only report: what a backfill of enrollments and of grade/attendance links would do (ADR-0011, 2.2a-1).

    python manage.py check_enrollment_backfill [--json]

It only SELECTs and prints counts (no names, no national ids). Nothing is guessed: a student without a class
gets no candidate enrollment, a class whose year does not resolve or has no ``AcademicYear`` row is counted
apart, and a row whose date lies in no year, in several years, or in a year where the student has no (or more
than one) candidate enrollment is listed by count and left unlinked.
"""
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from schools.academic_years import RESOLVED, normalize_academic_year, year_for_date
from schools.models import AcademicYear, SchoolClass
from students.models import Attendance, Enrollment, Grade, Student


class Command(BaseCommand):
    help = "Report the effect of an enrollment backfill (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Print the report as JSON.')

    def handle(self, *args, **opts):
        years = {}  # (school_id, code) -> (start, end)
        ranges = defaultdict(list)  # school_id -> [(code, start, end)]
        for y in AcademicYear.objects.values('school_id', 'code', 'start_date', 'end_date'):
            years[(y['school_id'], y['code'])] = True
            ranges[y['school_id']].append((y['code'], y['start_date'], y['end_date']))

        classes = {
            pk: (school_id, normalize_academic_year(year), grade)
            for pk, school_id, year, grade in SchoolClass.objects.values_list('pk', 'school_id', 'academic_year', 'grade')
        }

        students = list(Student.objects.values_list('pk', 'school_id', 'school_class_id', 'grade'))
        candidates = {}   # student_id -> set(codes) of candidate enrollments
        out = Counter()
        for pk, school_id, class_id, grade in students:
            if class_id is None:
                out['students_without_class_no_enrollment_would_be_created'] += 1
                continue
            class_school, (status, code), class_grade = classes[class_id]
            if status != RESOLVED:
                out['students_class_year_blank_or_unresolved'] += 1
            elif (class_school, code) not in years:
                out['students_class_year_resolved_but_no_academic_year_row'] += 1
            else:
                out['students_with_candidate_enrollment'] += 1
                candidates.setdefault(pk, set()).add(code)
                if class_grade is not None and class_grade != grade:
                    out['candidates_where_class_grade_differs_from_student_grade'] += 1
        existing = Counter(Enrollment.objects.values_list('student_id', flat=True))
        school_of = {pk: school_id for pk, school_id, _c, _g in students}
        existing_codes = defaultdict(set)
        for sid, code in Enrollment.objects.values_list('student_id', 'academic_year__code'):
            existing_codes[sid].add(code)

        def classify(rows, label):
            c = Counter()
            for student_id, day, enrollment_id in rows:
                c['rows'] += 1
                if enrollment_id is not None:
                    c['already_linked'] += 1
                    continue
                school_id = school_of.get(student_id)
                found = year_for_date(ranges.get(school_id, []), day)
                if not found:
                    c['date_in_no_year_unlinked'] += 1
                elif len(found) > 1:
                    c['date_in_overlapping_years_unlinked'] += 1
                else:
                    code = found[0]
                    options = candidates.get(student_id, set()) | existing_codes.get(student_id, set())
                    if code in options:
                        c['would_link'] += 1
                    else:
                        c['year_found_but_student_has_no_enrollment_in_it_unlinked'] += 1
            return {label: dict(c)}

        report = {
            'students': len(students),
            'students_already_with_enrollment': len(existing),
            **dict(out),
            **classify(Grade.objects.values_list('student_id', 'date', 'enrollment_id').iterator(), 'grades'),
            **classify(Attendance.objects.values_list('student_id', 'date', 'enrollment_id').iterator(), 'attendance'),
            'academic_year_rows': len(years),
            'writes': 'none',
        }
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return
        self.stdout.write('Enrollment backfill (read-only)')
        for key, value in sorted(report.items()):
            if isinstance(value, dict):
                self.stdout.write(f'  {key}:')
                for k2, v2 in sorted(value.items()):
                    self.stdout.write(f'    {k2}: {v2}')
            else:
                self.stdout.write(f'  {key}: {value}')
