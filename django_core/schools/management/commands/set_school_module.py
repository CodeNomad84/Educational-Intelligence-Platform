"""Switch an optional module on (or set its end date) for a school; audit-logged. No billing, no keys.

    manage.py set_school_module <school_code> <module_key> [--starts YYYY-MM-DD] [--ends YYYY-MM-DD]
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from schools.entitlements import MODULES, set_module
from schools.models import School


class Command(BaseCommand):
    help = 'Grant an optional module to a school for a date range (audit-logged).'

    def add_arguments(self, parser):
        parser.add_argument('school_code')
        parser.add_argument('module_key', choices=MODULES)
        parser.add_argument('--starts', type=date.fromisoformat, default=None)
        parser.add_argument('--ends', type=date.fromisoformat, default=None)
        parser.add_argument('--kind', choices=('trial', 'licensed'), default='licensed',
                            help='a trial needs --ends; running it again for the same school/module extends that trial')

    def handle(self, *args, school_code, module_key, starts, ends, kind, **options):
        school = School.objects.filter(code=school_code).first()
        if school is None:
            raise CommandError('unknown school code')
        starts = starts or timezone.localdate()
        if ends and ends < starts:
            raise CommandError('--ends is before --starts')
        if kind == 'trial' and ends is None:
            raise CommandError('a trial needs --ends')
        row = set_module(school, module_key, starts, ends, kind=kind)
        self.stdout.write(f'{school.code}: {row.module_key} ({row.kind}) from {row.starts_on} to {row.ends_on or "open"}')
