"""One-time population of ``SchoolMembership`` for existing SchoolAdmins (changes/0010 S2). Run while ONE School exists.

    manage.py backfill_school_memberships [--json]                                 dry-run (default): counts only
    manage.py backfill_school_memberships --apply --batch-file PATH               create the memberships (batch-logged)
    manage.py backfill_school_memberships --revert-batch PATH                     delete exactly the rows of that batch

Evidence-only, like ``backfill_enrollments``: with EXACTLY ONE School every active, non-superuser user of group
``SchoolAdmin`` who is not in ``PlatformAdmin`` and has no membership row yet gets a membership in that School.
With zero or several Schools nothing is guessed: the command prints the eligible user ids and ``--apply`` is
refused. Existing rows (active or inactive) are never modified: an inactive row is not re-activated. Created rows
have no ``created_by``. A revert deletes only batch rows that are still active and unchanged in school and user.
The command grants nothing by itself: no visibility rule reads memberships before stage S3.
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools import batch_log
from schools.models import School, SchoolMembership
from students.access import ADMIN, PLATFORM_ADMIN

COMMAND = 'backfill_school_memberships'


class Command(BaseCommand):
    help = 'Create a membership in the only School for every eligible SchoolAdmin (dry-run by default, batch-logged).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write (needs --batch-file)')
        parser.add_argument('--batch-file', help='new file that records the created membership rows')
        parser.add_argument('--revert-batch', help='batch file to revert')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        batch_log.reject_flag_combinations(opts, revert='revert_batch', needs_apply=('batch_file',))
        if opts['revert_batch']:
            return self._revert(opts)
        User = get_user_model()
        school_ids = list(School.objects.order_by('pk').values_list('pk', flat=True))
        in_group = set(User.objects.filter(groups__name=ADMIN).values_list('pk', flat=True))
        platform = set(User.objects.filter(groups__name=PLATFORM_ADMIN).values_list('pk', flat=True))
        accounts = {u['pk']: u for u in User.objects.filter(pk__in=in_group).values('pk', 'is_active', 'is_superuser')}
        have_row = set(SchoolMembership.objects.values_list('user_id', flat=True))
        eligible, skipped = [], {'inactive_account': 0, 'superuser': 0, 'also_platform_admin': 0, 'already_has_membership': 0}
        for pk in sorted(in_group):
            account = accounts[pk]
            if not account['is_active']:
                skipped['inactive_account'] += 1
            elif account['is_superuser']:
                skipped['superuser'] += 1
            elif pk in platform:
                skipped['also_platform_admin'] += 1
            elif pk in have_row:
                skipped['already_has_membership'] += 1
            else:
                eligible.append(pk)
        report = {
            'schools': len(school_ids),
            'school_admin_group_members': len(in_group),
            'eligible': len(eligible),
            'skipped': skipped,
            'writes': 'none',
        }
        if len(school_ids) != 1:
            report['mode'] = 'NOT APPLICABLE: exactly one School is required; nothing is guessed'
            report['eligible_user_ids'] = eligible
            self._print(report, opts)
            if opts['apply']:
                raise CommandError('Refused: exactly one School is required (found %d).' % len(school_ids))
            return
        school_id = school_ids[0]
        report['would_create'] = len(eligible)
        if opts['apply']:
            if not opts['batch_file']:
                raise CommandError('--apply needs --batch-file (a new file that records the created rows).')
            batch_log.ensure_new(opts['batch_file'])
            with transaction.atomic():
                # the batch file is written inside the transaction, before it commits: if writing it fails (existing
                # file, unwritable path) the rows are rolled back; a batch that outlives a failed commit lists rows that
                # do not exist, and the revert leaves missing rows alone
                rows = SchoolMembership.objects.bulk_create(
                    [SchoolMembership(user_id=pk, school_id=school_id) for pk in eligible])
                if not all(row.pk for row in rows):
                    raise CommandError('The database did not return the new ids; nothing was written.')
                batch_log.write_batch(opts['batch_file'], COMMAND, {
                    'school_id': school_id,
                    'memberships': [{'id': row.pk, 'user_id': row.user_id} for row in rows]})
            report['writes'] = f'created {len(rows)}; batch file written'
        else:
            report['mode'] = 'dry-run (nothing written)'
        self._print(report, opts)

    def _revert(self, opts):
        data = batch_log.read_batch(opts['revert_batch'], COMMAND)
        school_id = batch_log.require_valid_id(data, 'school_id')
        entries = batch_log.id_rows(data, 'memberships', ('id', 'user_id'))
        deleted = changed = missing = 0
        with transaction.atomic():
            for entry in entries:
                row = SchoolMembership.objects.select_for_update().filter(pk=entry['id']).first()
                if row is None:
                    missing += 1
                elif row.user_id != entry['user_id'] or row.school_id != school_id or not row.is_active:
                    changed += 1  # modified or deactivated since: left alone
                else:
                    row.delete()
                    deleted += 1
        self._print({'batch_rows': len(entries), 'deleted': deleted, 'left_alone_changed_since': changed,
                     'rows_missing': missing, 'writes': 'reverted'}, opts)

    def _print(self, report, opts):
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                self.stdout.write(f'{key}: {value}')
