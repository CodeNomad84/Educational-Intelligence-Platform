"""Read-only report: how stored ``TeacherAssignment.subject`` values relate to the fixed vocabulary (C4b).

    python manage.py check_assignment_subjects [--json]

It only SELECTs. It never normalises, migrates or writes anything and prints counts and subject strings only
(no teacher or student data). It is the rehearsal for the optional ``schools/0003`` data migration: only exact,
unambiguous matches are ever converted (ADR-0004 amendment, owner decision 2).
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand

from schools.models import TeacherAssignment
from schools.vocabulary import BLANK, EXACT_LABEL, UNMATCHED, VALID, classify_subject


class Command(BaseCommand):
    help = "Report TeacherAssignment.subject values against the subject vocabulary (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Print the report as JSON.')

    def handle(self, *args, **opts):
        values = list(TeacherAssignment.objects.values_list('subject', flat=True))
        counts = Counter()
        exact = Counter()
        unmatched = Counter()
        for value in values:
            status, key = classify_subject(value)
            counts[status] += 1
            if status == EXACT_LABEL:
                exact[f'{value} -> {key}'] += 1
            elif status == UNMATCHED:
                unmatched[value] += 1

        report = {
            'assignments': len(values),
            'valid_key': counts[VALID],
            'blank': counts[BLANK],
            'exact_label_convertible': counts[EXACT_LABEL],
            'unmatched': counts[UNMATCHED],
            'exact_label_values': dict(exact),
            'unmatched_values': dict(unmatched),
            'writes': 'none',
        }
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        self.stdout.write('TeacherAssignment.subject vs vocabulary (read-only)')
        for key in ('assignments', 'valid_key', 'blank', 'exact_label_convertible', 'unmatched'):
            self.stdout.write(f'  {key}: {report[key]}')
        for label, group in (('exact label -> key', exact), ('unmatched', unmatched)):
            for value, n in sorted(group.items()):
                self.stdout.write(f'  {label}: {value!r} x{n}')
        self.stdout.write('writes: none')
