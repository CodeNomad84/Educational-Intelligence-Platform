"""Year-aware historical import (ADR-0011 stage 2.2a-3). Dry-run by default.

    manage.py import_history --kind roster|grades|attendance --year 1403-1404 --file PATH [--school-code CODE]
                             [--max-score 20] [--apply] [--json]
    manage.py import_history --revert-batch ID [--apply]

The year is chosen here by the admin (any spelling the normaliser resolves) and must already exist as an
``AcademicYear``; the import never creates years, students or classes and never writes a Student field.
``--apply`` creates one ImportBatch per run; ``--revert-batch`` removes exactly the rows of that batch
(enrollments only if nothing else uses them). See students/history_import.py for the row rules.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import AcademicYear, School
from students import history_import
from students.models import Attendance, Enrollment, Grade, ImportBatch


class Command(BaseCommand):
    help = "Import historical roster/grades/attendance for one academic year (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=history_import.KINDS)
        parser.add_argument('--year', help='academic year, e.g. 1403-1404 (variants accepted)')
        parser.add_argument('--file', help='CSV or XLSX file')
        parser.add_argument('--school-code', help='School.code; optional when only one school has that year')
        parser.add_argument('--max-score', type=float, default=None, help="highest valid score (default: the school's grade scale, 20 if unset)")
        parser.add_argument('--apply', action='store_true', help='write (default is a dry-run)')
        parser.add_argument('--revert-batch', type=int, help='ImportBatch id to remove')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        if opts['revert_batch'] is not None:
            report = self._revert(opts['revert_batch'], opts['apply'])
        else:
            report = self._import(opts)
        report['mode'] = ('APPLIED' if opts['apply'] else 'DRY-RUN')
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        else:
            for key, value in sorted(report.items()):
                self.stdout.write(f'{key}: {value}')

    def _year(self, opts):
        status, code = normalize_academic_year(opts['year'])
        if status != RESOLVED:
            raise CommandError(f"سال تحصیلی «{opts['year']}» قابل تشخیص نیست (نمونه: 1403-1404).")
        years = AcademicYear.objects.filter(code=code)
        if opts['school_code']:
            years = years.filter(school__code=opts['school_code'])
        years = list(years.select_related('school'))
        if not years:
            raise CommandError(f'AcademicYear {code} وجود ندارد؛ ابتدا در پنل مدیریت ثبت شود.')
        if len(years) > 1:
            raise CommandError(f'سال {code} در چند مدرسه وجود دارد؛ --school-code را بدهید.')
        return years[0]

    def _import(self, opts):
        if not (opts['kind'] and opts['year'] and opts['file']):
            raise CommandError('--kind, --year and --file are required (or use --revert-batch).')
        year = self._year(opts)
        try:
            rows, sha = history_import.read_rows(opts['file'], opts['kind'])
        except history_import.FileError as exc:
            raise CommandError(str(exc))
        if opts['max_score'] is None:
            from students.scale import school_scale
            opts['max_score'] = float(school_scale(year.school_id))
        with transaction.atomic():
            batch = None
            if opts['apply']:
                batch = ImportBatch.objects.create(
                    kind=opts['kind'], academic_year=year, file_sha256=sha, dry_run=False)
            report = history_import.run(
                opts['kind'], year, rows, apply=opts['apply'], batch=batch, max_score=opts['max_score'])
            if batch is not None:
                batch.counts = {'counts': report['counts'], 'rejected_by_reason': report['rejected_by_reason']}
                batch.save(update_fields=['counts'])
                report['import_batch'] = batch.pk
        report['file_sha256'] = sha
        report['school'] = year.school.code
        return report

    def _revert(self, batch_id, apply):
        try:
            batch = ImportBatch.objects.get(pk=batch_id)
        except ImportBatch.DoesNotExist:
            raise CommandError(f'ImportBatch {batch_id} وجود ندارد.')
        grades = Grade.objects.filter(import_batch=batch)
        attendance = Attendance.objects.filter(import_batch=batch)
        enrollments = Enrollment.objects.filter(import_batch=batch)
        report = {'import_batch': batch.pk, 'kind': batch.kind, 'academic_year': batch.academic_year.code}
        with transaction.atomic():
            report['grades_' + ('deleted' if apply else 'to_delete')] = grades.count()
            report['attendance_' + ('deleted' if apply else 'to_delete')] = attendance.count()
            if apply:
                grades.delete()
                attendance.delete()
                in_use = [e.pk for e in enrollments if e.grades.exists() or e.attendances.exists()]
                deletable = enrollments.exclude(pk__in=in_use)
                report['enrollments_deleted'] = deletable.count()
                report['enrollments_kept_because_in_use'] = len(in_use)
                deletable.delete()
                batch.counts = {**(batch.counts or {}), 'reverted': True}
                batch.save(update_fields=['counts'])
            else:
                report['enrollments_to_delete_if_unused'] = enrollments.count()
        return report
