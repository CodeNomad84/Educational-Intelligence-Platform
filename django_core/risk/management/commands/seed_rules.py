"""Create the four starter rules as DRAFTS for ONE school (0025). Idempotent: a code that already exists is left alone.

The thresholds are a first proposal ported from the demo and are NOT validated: the school's own teachers must review them
before anyone activates a rule (activation is a separate, human step in the rules pages)."""
from django.core.management.base import BaseCommand, CommandError

from risk.models import Rule
from risk.rules import STARTERS
from schools.command_scope import resolve_scope
from schools.models import School

LABEL = ' (پیشنهاد اولیه، اعتبارسنجی‌نشده)'


class Command(BaseCommand):
    help = 'Create the 4 starter rules as drafts for one school. Use --school once several schools exist.'

    def add_arguments(self, parser):
        parser.add_argument('--school', help='school code; required when more than one school exists')

    def handle(self, *args, **options):
        school = resolve_scope(options['school'], writes=True, option='--school') or School.objects.order_by('pk').first()
        if school is None:
            raise CommandError('no school exists')
        made = 0
        for code, spec in STARTERS.items():
            _rule, created = Rule.objects.get_or_create(
                school=school, code=code, version=1,
                defaults=dict(kind=code, title=spec['title'] + LABEL, risk_type=spec['risk_type'], severity=spec['severity'],
                              connective=spec['connective'], clauses=spec['clauses'], cooldown_days=14))
            made += created
        self.stdout.write(f'{school.code}: {made} starter draft(s) created, {len(STARTERS) - made} already existed')
