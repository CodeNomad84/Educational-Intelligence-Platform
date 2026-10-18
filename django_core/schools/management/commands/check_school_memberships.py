"""Report orphan school memberships and deactivate them (changes/0010 S2; S1 review findings F2, F4, G3, H2; D-MS-9).

    manage.py check_school_memberships [--json]
    manage.py check_school_memberships --deactivate                                  dry-run: what would be deactivated
    manage.py check_school_memberships --deactivate --apply --batch-file PATH        deactivate (batch-logged)
    manage.py check_school_memberships --revert-batch PATH                           re-activate exactly that batch

Counts and ids only, no names. An ORPHAN is a membership whose user no longer qualifies (inactive account,
superuser, outside ``SchoolAdmin``, also ``PlatformAdmin``). The report exits 1 while ACTIVE orphans exist.
``--deactivate`` only sets ``is_active=False`` and never deletes; it is a dry-run unless ``--apply`` is given,
and ``--apply`` needs a new ``--batch-file``. Nothing here grants access.

RUNBOOK (owner decision D-MS-9, option B): when a user is promoted to PlatformAdmin, deactivate that user's school
memberships first or immediately after (run this command with --deactivate --apply). A promoted user must not be
left with active memberships; the readiness check blocks S3 while any exist.
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from schools import batch_log
from schools.membership_audit import REASONS, classify_memberships
from schools.models import SchoolMembership

COMMAND = 'check_school_memberships'


class Command(BaseCommand):
    help = 'Report orphan school memberships; optionally deactivate them (dry-run by default, batch-logged, revertible).'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')
        parser.add_argument('--deactivate', action='store_true', help='deactivate active orphan memberships')
        parser.add_argument('--apply', action='store_true', help='write (with --deactivate; needs --batch-file)')
        parser.add_argument('--batch-file', help='new file that records the affected membership ids')
        parser.add_argument('--revert-batch', help='batch file to revert')

    def handle(self, *args, **opts):
        if opts['revert_batch']:
            return self._revert(opts)
        rows = classify_memberships()
        active = [r for r in rows if r['is_active']]
        orphans_active = [r for r in active if r['reason']]
        by_reason = Counter(r['reason'] for r in orphans_active)
        report = {
            'memberships_total': len(rows),
            'memberships_active': len(active),
            'orphan_active_total': len(orphans_active),
            'orphan_active_by_reason': {k: by_reason[k] for k in REASONS if by_reason[k]},
            'orphan_inactive_total': sum(1 for r in rows if not r['is_active'] and r['reason']),
            'active_memberships_of_platform_admin_users': sum(1 for r in active if r['user_in_platform_admin']),
            'writes': 'none',
        }
        if opts['deactivate']:
            ids = sorted(r['id'] for r in orphans_active)
            report['would_deactivate'] = len(ids)
            if opts['apply']:
                if not opts['batch_file']:
                    raise CommandError('--apply needs --batch-file (a new file that records the affected ids).')
                batch_log.write_batch(opts['batch_file'], COMMAND, {'membership_ids': ids})
                with transaction.atomic():
                    SchoolMembership.objects.filter(pk__in=ids, is_active=True).update(
                        is_active=False, updated_at=timezone.now())
                report['writes'] = f'deactivated {len(ids)}; batch file written'
            else:
                report['mode'] = 'dry-run (nothing written)'
        self._print(report, opts)
        if report['orphan_active_total'] and not opts['deactivate']:  # report mode: exit 1 while active orphans exist
            raise CommandError(f"{report['orphan_active_total']} active orphan membership(s).")

    def _revert(self, opts):
        data = batch_log.read_batch(opts['revert_batch'], COMMAND)
        ids = batch_log.int_list(data, 'membership_ids')
        with transaction.atomic():
            restored = SchoolMembership.objects.filter(pk__in=ids, is_active=False).update(
                is_active=True, updated_at=timezone.now())
        missing = len(ids) - SchoolMembership.objects.filter(pk__in=ids).count()
        self._print({'batch_rows': len(ids), 'reactivated': restored, 'rows_missing': missing,
                     'already_active': len(ids) - restored - missing,
                     'warning': 'reverting re-activates exactly the batch rows; an orphan row stays an orphan',
                     'writes': 'reverted'}, opts)

    def _print(self, report, opts):
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                self.stdout.write(f'{key}: {value}')
