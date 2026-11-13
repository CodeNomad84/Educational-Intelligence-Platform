"""Prepare the mission module for one or all schools: default vocabulary terms, the first ACTIVE weight set, and one
observation period in the current academic year. Idempotent. Synthetic/default data only.

    manage.py seed_mission [--school CODE] [--period-label LABEL]
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from missions.models import Period
from missions.weights import ensure_default_weight_set
from schools.command_scope import resolve_scope
from schools.models import AcademicYear, School


class Command(BaseCommand):
    help = 'Seed vocabulary, default weight set and a period for the mission module (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--school', default=None)
        parser.add_argument('--all-schools', action='store_true', help='required to seed every school when more than one exists')
        parser.add_argument('--period-label', default='دورهٔ اول')

    def handle(self, *args, school, period_label, **options):
        chosen = resolve_scope(school, writes=True, all_schools=options['all_schools'], option='--school')
        schools = School.objects.filter(pk=chosen.pk) if chosen else School.objects.all()
        for sch in schools:
            call_command('seed_vocabulary', school=sch.code, stdout=StringIO())
            ws, created = ensure_default_weight_set(sch)
            year = AcademicYear.objects.filter(school=sch, is_current=True).first()
            period = Period.objects.get_or_create(school=sch, academic_year=year, label=period_label)[1] if year else False
            if options['verbosity']:
                self.stdout.write(f'{sch.code}: weight set v{ws.version} {"created" if created else "kept"}; '
                                  f'period {"created" if period else "kept/none (no current year)"}')
