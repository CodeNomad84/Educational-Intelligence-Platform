"""Load the rubric levels from the owner's local guide: manage.py load_mission_rubric /path/to/guide.docx

The file stays on the owner's disk (docs/qalamestaan/ is git-ignored); only the database receives the text. Idempotent."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from missions.models import Indicator, RubricLevel
from missions.rubric import parse_rubric_docx


class Command(BaseCommand):
    help = 'Load rubric levels (1-5 per indicator) from a local .docx guide into the database.'

    def add_arguments(self, parser):
        parser.add_argument('path')

    @transaction.atomic
    def handle(self, *args, path, **options):
        try:
            rubric = parse_rubric_docx(path)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'cannot read the rubric: {exc}')
        indicators = {i.code: i for i in Indicator.objects.all()}
        for code, levels in rubric.items():
            for score, text in levels.items():
                RubricLevel.objects.update_or_create(indicator=indicators[code], score=score, defaults={'text': text})
        self.stdout.write(f'loaded {sum(len(v) for v in rubric.values())} levels for {len(rubric)} indicators')
