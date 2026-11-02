"""Create in-app 'follow-up due' notifications for ONE school (P6-2). Cron-ready, idempotent. Needs ``--school <code>`` once several
schools exist. Counts only on stdout; no student data."""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from risk.notifications import notify_due_plans
from schools.command_scope import resolve_scope
from schools.models import School


class Command(BaseCommand):
    help = 'Create follow-up-due notifications for the open plans of one school.'

    def add_arguments(self, parser):
        parser.add_argument('--school', help='school code; required when more than one school exists')

    def handle(self, *args, **options):
        school = resolve_scope(options['school'], writes=True, option='--school') or School.objects.order_by('pk').first()
        if school is None:
            raise CommandError('no school exists')
        self.stdout.write(f'created {notify_due_plans(school.pk, timezone.localdate())} notification(s)')
