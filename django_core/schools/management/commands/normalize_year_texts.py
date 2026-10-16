"""Rewrite free-text academic years to the canonical code (ADR-0011): SchoolClass and GradeLeadAssignment.

    manage.py normalize_year_texts                              DRY-RUN (default): counts of what --apply would do
    manage.py normalize_year_texts --apply --log FILE           write; every old value is logged to FILE (JSON)
    manage.py normalize_year_texts --revert-from FILE [--apply] restore the logged values (dry-run unless --apply)

Only UNAMBIGUOUS conversions are made: a value that resolves to exactly one year (``1404``, ``۱۴۰۴/۱۴۰۵``,
``1404-05`` ...) becomes ``1404-1405``. Blank and unresolved values are reported and left alone (never guessed);
so are conversions that would collide with another row under the table's unique constraint. Nothing else is
written. The command changes data, not any access rule; with canonical texts the legacy string-equality matching
and the enrollment-based matching agree (it removes the spelling-variant differences of ``compare_access_parity``).
The log is the undo: ``--revert-from`` restores a value only if the row still holds the value this command wrote.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools.academic_years import BLANK, RESOLVED, normalize_academic_year
from schools.models import GradeLeadAssignment, SchoolClass

MODELS = {'SchoolClass': SchoolClass, 'GradeLeadAssignment': GradeLeadAssignment}


def _key(model_name, row):
    """The unique key a row would have after conversion, per table."""
    if model_name == 'SchoolClass':
        return (row.school_id, row.title)
    return (row.user_id, row.school_id, row.grade)


class Command(BaseCommand):
    help = "Normalise free-text academic years to the canonical code (dry-run by default; revertible via a log)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--log', help='JSON file that receives the previous values (required with --apply)')
        parser.add_argument('--revert-from', help='log file written by a previous --apply')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        if opts['revert_from']:
            report = self._revert(opts['revert_from'], opts['apply'])
        else:
            report = self._normalize(opts)
        report['mode'] = 'APPLIED' if opts['apply'] else 'DRY-RUN'
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in sorted(report.items()):
                self.stdout.write(f'{key}: {value}')

    def _normalize(self, opts):
        if opts['apply'] and not opts['log']:
            raise CommandError('--apply requires --log FILE (the undo information).')
        report, changes = {}, []
        for name, model in MODELS.items():
            rows = list(model.objects.all())
            existing = defaultdict(set)   # (unique key) -> canonical codes already present
            for row in rows:
                status, code = normalize_academic_year(row.academic_year)
                if status == RESOLVED and row.academic_year == code:
                    existing[_key(name, row)].add(code)
            counts, unresolved = Counter(), Counter()
            planned = defaultdict(list)   # (unique key, code) -> rows to convert
            for row in rows:
                counts['rows'] += 1
                status, code = normalize_academic_year(row.academic_year)
                if status == BLANK:
                    counts['blank_left_alone'] += 1
                elif status != RESOLVED:
                    counts['unresolved_left_alone'] += 1
                    unresolved[row.academic_year] += 1
                elif row.academic_year == code:
                    counts['already_canonical'] += 1
                else:
                    planned[(_key(name, row), code)].append(row)
            for (key, code), group in planned.items():
                if code in existing[key] or len(group) > 1:
                    counts['skipped_would_collide'] += len(group)   # two rows would become identical
                    continue
                row = group[0]
                changes.append({'model': name, 'pk': row.pk, 'old': row.academic_year, 'new': code})
                counts['to_convert' if not opts['apply'] else 'converted'] += 1
            report[name] = dict(counts)
            report[name + '_unresolved_values'] = dict(unresolved)
        if opts['apply'] and changes:
            with transaction.atomic():
                for c in changes:
                    MODELS[c['model']].objects.filter(pk=c['pk']).update(academic_year=c['new'])
            log = {'written_at': datetime.now(timezone.utc).isoformat(), 'changes': changes}
            with open(opts['log'], 'w', encoding='utf-8') as fh:
                json.dump(log, fh, ensure_ascii=False, indent=1)
            report['log'] = opts['log']
        elif opts['apply']:
            report['log'] = 'nothing to log (no conversions)'
        return report

    def _revert(self, path, apply):
        with open(path, encoding='utf-8') as fh:
            changes = json.load(fh)['changes']
        restore, stale = [], 0
        for c in changes:
            row = MODELS[c['model']].objects.filter(pk=c['pk']).first()
            if row is None or row.academic_year != c['new']:
                stale += 1   # the row changed since: do not overwrite someone's later edit
            else:
                restore.append(c)
        report = {'entries_in_log': len(changes), 'skipped_changed_since': stale,
                  'to_restore' if not apply else 'restored': len(restore)}
        if apply:
            with transaction.atomic():
                for c in restore:
                    MODELS[c['model']].objects.filter(pk=c['pk']).update(academic_year=c['old'])
        return report
