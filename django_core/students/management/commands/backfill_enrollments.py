"""Evidence-only backfill of enrollments and of grade/attendance links (ADR-0011, proposal 0003 §4 step 3).

    manage.py backfill_enrollments                       DRY-RUN (default): counts of what --apply would do
    manage.py backfill_enrollments --apply               write
    manage.py backfill_enrollments --revert-backfill     DRY-RUN of the revert
    manage.py backfill_enrollments --revert-backfill --apply   write the revert

Rules (nothing is guessed; whatever is not evidenced stays untouched and is counted):
  * A student gets ONE enrollment, only when it has a class AND the class year resolves to an existing
    ``AcademicYear`` of the class's school AND that year is the school's CURRENT year (a link to a class of a
    past year is a stale link whose status is not evidenced: skipped) AND the class grade (if set) equals the
    student's grade. Grade = ``Student.grade``, status ``active``, ``source='backfill'``.
  * A ``Grade``/``Attendance`` row is linked only when it has no enrollment, its student has a school, its date
    lies in exactly one year range of that school, and the student has exactly one enrollment in that year.
    The row is marked ``enrollment_link_source='backfill'`` so the revert is exact.
  * Idempotent: existing enrollments and links are never replaced; a second run changes nothing.
  * Revert: unlinks only rows marked 'backfill' and deletes only ``source='backfill'`` enrollments that no row
    uses any more. Student fields and manually/imported links are never touched.
Counts only are printed (no names, no national ids). The command never changes access: nothing reads
enrollments for visibility before stage 2.2a-4.
"""
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools.academic_years import RESOLVED, normalize_academic_year, year_for_date
from schools.command_scope import resolve_scope
from schools.models import AcademicYear, SchoolClass
from students.models import Attendance, Enrollment, Grade, Student

CHUNK = 500


def _chunks(items, size=CHUNK):
    for i in range(0, len(items), size):
        yield items[i:i + size]


class Command(BaseCommand):
    help = "Backfill enrollments and grade/attendance links from existing evidence (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write the changes (default is a dry-run)')
        parser.add_argument('--revert-backfill', action='store_true',
                            help='undo what a previous --apply created or linked')
        parser.add_argument('--json', action='store_true')
        parser.add_argument('--school-code', help='only this school; required with --apply / --revert-backfill when more than one school exists')

    def handle(self, *args, **opts):
        apply = opts['apply']
        scope = resolve_scope(opts.get('school_code'), writes=apply)
        school_id = scope.pk if scope else None
        report = self._revert(apply, school_id) if opts['revert_backfill'] else self._backfill(apply, school_id)
        report['mode'] = ('revert ' if opts['revert_backfill'] else 'backfill ') + ('APPLIED' if apply else 'DRY-RUN')
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return
        for key, value in sorted(report.items()):
            if isinstance(value, dict):
                self.stdout.write(f'{key}:')
                for k2, v2 in sorted(value.items()):
                    self.stdout.write(f'  {k2}: {v2}')
            else:
                self.stdout.write(f'{key}: {value}')

    # -- backfill ---------------------------------------------------------------------------------
    def _backfill(self, apply, only_school=None):
        years = {}
        ranges = defaultdict(list)
        for y in AcademicYear.objects.values('pk', 'school_id', 'code', 'start_date', 'end_date', 'is_current'):
            years[(y['school_id'], y['code'])] = y
            ranges[y['school_id']].append((y['code'], y['start_date'], y['end_date']))
        classes = {
            pk: (school_id, normalize_academic_year(year), grade)
            for pk, school_id, year, grade in SchoolClass.objects.values_list('pk', 'school_id', 'academic_year', 'grade')
        }
        have = set(Enrollment.objects.values_list('student_id', 'academic_year_id'))

        skipped = Counter()
        to_create = []  # (student_id, year_pk, class_id, grade)
        students = Student.objects.filter(school_id=only_school) if only_school else Student.objects.all()
        for pk, school_id, class_id, grade in students.values_list('pk', 'school_id', 'school_class_id', 'grade'):
            if class_id is None:
                skipped['student_without_class'] += 1
                continue
            class_school, (status, code), class_grade = classes[class_id]
            if school_id != class_school:
                skipped['student_school_differs_from_class_school'] += 1
            elif status != RESOLVED:
                skipped['class_year_blank_or_unresolved'] += 1
            elif (class_school, code) not in years:
                skipped['class_year_has_no_academic_year_row'] += 1
            elif not years[(class_school, code)]['is_current']:
                skipped['class_link_points_to_a_past_year_not_evidenced'] += 1
            elif class_grade is not None and class_grade != grade:
                skipped['class_grade_differs_from_student_grade'] += 1
            elif (pk, years[(class_school, code)]['pk']) in have:
                skipped['enrollment_already_exists'] += 1
            else:
                to_create.append((pk, years[(class_school, code)]['pk'], class_id, grade))

        report = {'enrollments_to_create' if not apply else 'enrollments_created': len(to_create),
                  'enrollments_skipped': dict(skipped)}
        with transaction.atomic():
            if apply and to_create:
                for part in _chunks(to_create):
                    Enrollment.objects.bulk_create([
                        Enrollment(student_id=s, academic_year_id=y, school_class_id=c, grade=g,
                                   status='active', source='backfill')
                        for s, y, c, g in part])
            report.update(self._link_rows(apply, ranges, years, [] if apply else to_create, only_school=only_school))
        return report

    def _link_rows(self, apply, ranges, years, planned, only_school=None):
        year_code = {y['pk']: code for (_s, code), y in years.items()}
        school_of = dict(Student.objects.values_list('pk', 'school_id'))
        per_year = defaultdict(list)  # (student_id, code) -> [enrollment pk]
        for pk, student_id, year_id in Enrollment.objects.values_list('pk', 'student_id', 'academic_year_id'):
            per_year[(student_id, year_code.get(year_id))].append(pk)

        for student_id, year_id, _class_id, _grade in planned:  # dry-run: enrollments --apply would create
            per_year[(student_id, year_code[year_id])].append(None)
        out = {}
        for label, model in (('grades', Grade), ('attendance', Attendance)):
            counts = Counter()
            by_enrollment = defaultdict(list)
            rows = model.objects.filter(student__school_id=only_school) if only_school else model.objects.all()
            for pk, student_id, day, enrollment_id in rows.values_list(
                    'pk', 'student_id', 'date', 'enrollment_id').iterator():
                counts['rows'] += 1
                if enrollment_id is not None:
                    counts['already_linked'] += 1
                    continue
                school_id = school_of.get(student_id)
                found = year_for_date(ranges.get(school_id, []), day)
                if len(found) != 1:
                    counts['unlinked_date_in_no_year' if not found else 'unlinked_date_in_overlapping_years'] += 1
                    continue
                options = per_year.get((student_id, found[0]), [])
                if len(options) == 1:
                    counts['to_link' if not apply else 'linked'] += 1
                    by_enrollment[options[0]].append(pk)
                else:
                    counts['unlinked_no_enrollment_in_that_year' if not options
                           else 'unlinked_several_enrollments_in_that_year'] += 1
            if apply:
                for enrollment_pk, ids in by_enrollment.items():
                    for part in _chunks(ids):
                        model.objects.filter(pk__in=part, enrollment__isnull=True).update(
                            enrollment_id=enrollment_pk, enrollment_link_source='backfill')
            out[label] = dict(counts)
        return out

    # -- revert -----------------------------------------------------------------------------------
    def _revert(self, apply, only_school=None):
        report = {}
        with transaction.atomic():
            for label, model in (('grades', Grade), ('attendance', Attendance)):
                qs = model.objects.filter(enrollment_link_source='backfill')
                if only_school:
                    qs = qs.filter(student__school_id=only_school)
                report[f'{label}_unlinked' if apply else f'{label}_to_unlink'] = qs.count()
                if apply:
                    qs.update(enrollment=None, enrollment_link_source='')
            candidates = Enrollment.objects.filter(source='backfill')
            if only_school:
                candidates = candidates.filter(student__school_id=only_school)
            if apply:
                in_use = [e.pk for e in candidates if e.grades.exists() or e.attendances.exists()]
                deletable = candidates.exclude(pk__in=in_use)
                report['enrollments_deleted'] = deletable.count()
                deletable.delete()
                report['enrollments_kept_because_in_use'] = len(in_use)
            else:
                report['enrollments_to_delete_if_unused'] = candidates.count()
        return report
