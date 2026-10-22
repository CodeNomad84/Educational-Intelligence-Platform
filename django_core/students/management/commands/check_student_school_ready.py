"""Read-only pre-flight for S6 (``Student.school`` NOT NULL; changes/0010). Counts only, no personal data.

    manage.py check_student_school_ready [--json]

It only SELECTs: it never writes, migrates or assigns a school. Run it on a COPY of the synthetic data (SQLite file or a
restored PostgreSQL dump) before the S6 migration. Verdict READY only when no student has ``school IS NULL``; otherwise
NOT READY and the exit code is 1. The NOT NULL migration itself refuses to run in that case (S6-2); this report shows
what is left to do and what ``backfill_student_school`` would resolve (same rule, same function, so the two never
disagree). Exit codes: 0 READY, 1 NOT READY.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from schools.models import School
from students.management.commands.backfill_student_school import plan_assignments
from students.models import Student


def readiness_report():
    school_ids = list(School.objects.order_by('pk').values_list('pk', flat=True))
    null_rows = list(Student.objects.filter(school__isnull=True).values_list('pk', 'school_class__school_id'))
    assignments, unresolved = plan_assignments(null_rows, school_ids)
    inconsistent = sum(
        1 for sid, csid in Student.objects.filter(school__isnull=False, school_class__isnull=False)
        .values_list('school_id', 'school_class__school_id') if sid != csid)
    report = {
        'students': Student.objects.count(),
        'schools': len(school_ids),
        'students_without_school': len(null_rows),
        'students_without_school_but_with_class': sum(1 for _pk, csid in null_rows if csid is not None),
        'backfill_would_assign': len(assignments),
        'backfill_would_leave_unresolved': unresolved,
        'students_whose_school_differs_from_their_class_school': inconsistent,
        'school_column_is_nullable': bool(Student._meta.get_field('school').null),
    }
    report['ready'] = report['students_without_school'] == 0 and inconsistent == 0
    return report


class Command(BaseCommand):
    help = 'Report whether Student.school can be made NOT NULL (read-only; exit 1 when it cannot).'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        report = readiness_report()
        if opts['json']:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            for key in sorted(report):
                self.stdout.write(f'{key}: {report[key]}')
            self.stdout.write('READY' if report['ready'] else 'NOT READY')
        if not report['ready']:
            raise CommandError('NOT READY: ' + ('some students have no school' if report['students_without_school']
                                                else 'some students disagree with their class school'))
