"""One-time population of ``Student.school`` for existing rows (changes/0010 S2). Run while ONE School exists.

    manage.py backfill_student_school [--json]                                       dry-run (default): counts only
    manage.py backfill_student_school --apply --batch-file PATH                      write (batch-logged)
    manage.py backfill_student_school --revert-batch PATH                            undo exactly that batch

Only students whose ``school`` is NULL are considered; a student that already has a school is NEVER changed
(a student whose school differs from its class's school is only counted). Evidence-only:
  1. the student has a class  -> the class's school;
  2. no class and EXACTLY ONE School exists -> that School (the one-time population of stage S2, like
     students/0009; not a runtime default: creation paths are S2b);
  3. otherwise unresolved and reported (several Schools: nothing is guessed).
Writes use queryset updates restricted to ``school IS NULL`` rows and never touch enrollments. Because staff access
(Grade Lead / Teacher) requires the student's school to match the enrollment's school, giving a school to a student
who already has a CURRENT enrollment would WIDEN staff visibility; ``--apply`` is refused in that case unless
``--accept-visibility-change`` is given. A revert sets ``school`` back to NULL only where it still holds the value
the batch wrote and the student has no class (a class requires a school).
"""
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools import batch_log
from schools.models import School
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, Student
from students.student_school import school_column_is_nullable

COMMAND = 'backfill_student_school'
CHUNK = 500


def plan_assignments(rows, school_ids):
    """``rows``: iterable of ``(student_pk, class_school_id)`` for students with school NULL (``class_school_id`` None
    when the student has no class). Returns ``(assignments, unresolved)``: ``assignments`` maps student_pk to the
    school id, ``unresolved`` counts the students that stay NULL. Pure function (unit-tested)."""
    only = school_ids[0] if len(school_ids) == 1 else None
    assignments, unresolved = {}, 0
    for pk, class_school_id in rows:
        if class_school_id is not None:
            assignments[pk] = class_school_id
        elif only is not None:
            assignments[pk] = only
        else:
            unresolved += 1
    return assignments, unresolved


def _chunks(items):
    items = list(items)
    for start in range(0, len(items), CHUNK):
        yield items[start:start + CHUNK]


class Command(BaseCommand):
    help = 'Fill Student.school where it is NULL, from evidence only (dry-run by default, batch-logged, revertible).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write (needs --batch-file)')
        parser.add_argument('--batch-file', help='new file that records the affected students')
        parser.add_argument('--accept-visibility-change', action='store_true',
                            help='allow --apply although some students already have a current enrollment')
        parser.add_argument('--revert-batch', help='batch file to revert')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        batch_log.reject_flag_combinations(
            opts, revert='revert_batch', needs_apply=('batch_file', 'accept_visibility_change'))
        if opts['revert_batch'] is not None:
            return self._revert(opts)
        school_ids = list(School.objects.order_by('pk').values_list('pk', flat=True))
        null_rows = list(Student.objects.filter(school__isnull=True).values_list('pk', 'school_class__school_id'))
        assignments, unresolved = plan_assignments(null_rows, school_ids)
        by_rule = Counter('from_class' if cls is not None else 'only_school' for _pk, cls in null_rows
                          if _pk in assignments)
        inconsistent = sum(
            1 for sid, csid in Student.objects.filter(school__isnull=False, school_class__isnull=False)
            .values_list('school_id', 'school_class__school_id') if sid != csid)
        widened = self._would_become_visible(assignments)
        report = {
            'schools': len(school_ids),
            'students_without_school': len(null_rows),
            'would_set_from_class': by_rule['from_class'],
            'would_set_to_the_only_school': by_rule['only_school'],
            'unresolved_stay_null': unresolved,
            'info_students_with_school_differing_from_class_school_not_changed': inconsistent,
            'students_with_current_enrollment_that_staff_would_newly_see': widened,
            'writes': 'none',
        }
        if opts['apply']:
            if opts['batch_file'] is None:
                raise CommandError('--apply needs --batch-file (a new file that records the affected students).')
            if widened and not opts['accept_visibility_change']:
                raise CommandError(
                    f'Refused: {widened} student(s) already have a current enrollment and would become visible to '
                    'staff of their school. Review them, then re-run with --accept-visibility-change.')
            batch_log.ensure_new(opts['batch_file'])
            items = []
            with transaction.atomic():
                grouped = defaultdict(list)
                for pk, sid in assignments.items():
                    grouped[sid].append(pk)
                for sid, pks in sorted(grouped.items()):
                    for chunk in _chunks(sorted(pks)):
                        # lock the rows that are STILL NULL: the batch records the rows actually written
                        ids = list(Student.objects.select_for_update(of=('self',)).filter(
                            pk__in=chunk, school__isnull=True).order_by('pk').values_list('pk', flat=True))
                        if Student.objects.filter(pk__in=ids, school__isnull=True).update(school_id=sid) != len(ids):
                            raise CommandError('The rows changed while writing; nothing was written. Re-run.')
                        items.extend({'student_id': pk, 'school_id': sid} for pk in ids)
                batch_log.write_batch(opts['batch_file'], COMMAND, {'assignments': items})
            report['planned'] = len(assignments)
            report['writes'] = f'set {len(items)}; batch file written'
        else:
            report['mode'] = 'dry-run (nothing written)'
        self._print(report, opts)

    @staticmethod
    def _would_become_visible(assignments):
        """Students about to get a school who already hold a CURRENT enrollment in that school's current year."""
        count = 0
        by_school = defaultdict(list)
        for pk, sid in assignments.items():
            by_school[sid].append(pk)
        for sid, pks in by_school.items():
            for chunk in _chunks(pks):
                count += Enrollment.objects.filter(
                    student_id__in=chunk, ended_on__isnull=True, status__in=CURRENT_STATUSES,
                    academic_year__is_current=True, academic_year__school_id=sid,
                ).values('student_id').distinct().count()
        return count

    def _revert(self, opts):
        data = batch_log.read_batch(opts['revert_batch'], COMMAND)
        items = batch_log.id_rows(data, 'assignments', ('student_id', 'school_id'))
        if items and not school_column_is_nullable():
            raise CommandError('Cannot revert: students.school is NOT NULL since students.0015 (S6). Nothing was changed. '
                               'Reverse the migration first ("manage.py migrate students 0014") if this revert is really wanted.')
        grouped = defaultdict(list)
        for i in items:
            grouped[i['school_id']].append(i['student_id'])
        reverted = 0
        with transaction.atomic():
            for sid, pks in grouped.items():
                for chunk in _chunks(pks):
                    reverted += Student.objects.filter(
                        pk__in=chunk, school_id=sid, school_class__isnull=True).update(school=None)
        self._print({'batch_rows': len(items), 'reverted_to_null': reverted,
                     'left_alone_changed_since_or_has_class': len(items) - reverted, 'writes': 'reverted'}, opts)

    def _print(self, report, opts):
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                self.stdout.write(f'{key}: {value}')
