"""Create the default vocabulary terms for one school or all schools. Idempotent: a (school, domain, code) that already has
any term is left alone, so it never touches a school's own changes.

    manage.py seed_vocabulary [--school CODE] [--effective-from YYYY-MM-DD]

Without --effective-from the terms start on the school's earliest academic year start, else today (so multi-year history
resolves). Synthetic/default data only; no student data.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from schools.models import School
from vocabulary.defaults import DEFAULTS
from vocabulary.models import VocabularyTerm


class Command(BaseCommand):
    help = 'Create default vocabulary terms per domain (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--school', default=None)
        parser.add_argument('--effective-from', type=date.fromisoformat, default=None)

    def handle(self, *args, school, effective_from, **options):
        schools = School.objects.all()
        if school:
            schools = schools.filter(code=school)
            if not schools:
                raise CommandError('unknown school code')
        created = 0
        for sch in schools:
            start = effective_from or (sch.academic_years.order_by('start_date').values_list('start_date', flat=True).first()
                                       or timezone.localdate())
            for domain, rows in DEFAULTS.items():
                for code, label in rows:
                    if VocabularyTerm.objects.filter(school=sch, domain=domain, code=code).exists():
                        continue
                    VocabularyTerm.objects.create(school=sch, domain=domain, code=code, label_fa=label, effective_from=start)
                    created += 1
        self.stdout.write(f'created {created} terms for {schools.count()} school(s)')
