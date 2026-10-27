"""Evaluate the ACTIVE rules of ONE school and raise alerts (0025). Cron-ready: no scheduler is built in.

Needs ``--school <code>`` as soon as more than one school exists; with exactly one school that school is used. Never "all schools".
Audited as the ``system`` actor, counts only."""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from risk import rules
from schools.command_scope import resolve_scope
from schools.models import School


class Command(BaseCommand):
    help = 'Run the active rules of one school (alerts, hits, run counts). Use --school once several schools exist.'

    def add_arguments(self, parser):
        parser.add_argument('--school', help='school code; required when more than one school exists')
        parser.add_argument('--as-of', help='evaluation date YYYY-MM-DD (default today)')

    def handle(self, *args, **options):
        school = resolve_scope(options['school'], writes=True, option='--school')
        if school is None:
            school = School.objects.order_by('pk').first()
            if school is None:
                raise CommandError('no school exists')
        try:
            as_of = date.fromisoformat(options['as_of']) if options['as_of'] else None
        except ValueError:
            raise CommandError('--as-of must be YYYY-MM-DD') from None
        for run in rules.run_school(school.pk, as_of=as_of):
            self.stdout.write(f'{run.rule.code} v{run.rule.version}: {run.status} evaluated={run.evaluated} hits={run.hits} '
                              f'alerts={run.alerts_raised} cooldown={run.skipped_cooldown} insufficient={run.skipped_insufficient}')
