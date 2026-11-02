"""Seed the synthetic demo documents into ONE school and switch the ``advisor_ai`` module on as a trial.
    manage.py seed_demo_docs --school <code> --i-know-this-is-synthetic
Idempotent per title. The AI answer layer stays OFF (the SchoolAdmin switches it on, and a local provider must be configured)."""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from docqa import demo_docs, services
from docqa.models import DocumentChunk, SchoolDocument
from schools import entitlements
from schools.models import School


class Command(BaseCommand):
    help = 'Seed synthetic non-personal documents for the demo.'

    def add_arguments(self, parser):
        parser.add_argument('--school', required=True, help='School.code')
        parser.add_argument('--i-know-this-is-synthetic', action='store_true', dest='confirmed')

    def handle(self, *args, **opts):
        if not opts['confirmed']:
            raise CommandError('Pass --i-know-this-is-synthetic to confirm.')
        try:
            school = School.objects.get(code=opts['school'])
        except School.DoesNotExist:
            raise CommandError('unknown school code') from None
        made = 0
        for title, text in demo_docs.DOCS.items():
            if SchoolDocument.objects.filter(school=school, title=title).exists():
                continue
            doc = SchoolDocument.objects.create(school=school, title=title, source_name='demo', char_count=len(text))
            DocumentChunk.objects.bulk_create([DocumentChunk(document=doc, school=school, ordinal=i, text=c)
                                               for i, c in enumerate(services.chunk_text(text))])
            made += 1
        today = timezone.localdate()
        entitlements.set_module(school, 'advisor_ai', today, today + timedelta(days=365), kind=entitlements.TRIAL)
        self.stdout.write(f'created {made} document(s); advisor_ai trial on for {school.code}')
