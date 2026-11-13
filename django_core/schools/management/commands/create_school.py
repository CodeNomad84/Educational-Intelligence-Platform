"""Create a school (platform operator, terminal only); audit-logged and seeded with the default vocabulary.

    manage.py create_school <code> <name>

The code is the permanent school key (a slug, unique). One transaction: the School row, a ``school_create`` audit event
(actor ``system``, no content) and ``seed_vocabulary --school <code>``. Accounts, memberships and modules stay the separate
steps of ``docs/manuals/platform-admin.md``.
"""
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_slug
from django.db import transaction

from schools import audit
from schools.models import School


class Command(BaseCommand):
    help = 'Create a school with an audit event and its default vocabulary.'

    def add_arguments(self, parser):
        parser.add_argument('code', help='permanent school key (letters, digits, - and _)')
        parser.add_argument('name')

    def handle(self, *args, code, name, **options):
        name = name.strip()
        if not name:
            raise CommandError('the name is empty')
        try:
            validate_slug(code)
        except ValidationError:
            raise CommandError('the code may contain only letters, digits, - and _')
        if len(code) > School._meta.get_field('code').max_length:
            raise CommandError('the code is too long')
        if School.objects.filter(code=code).exists():
            raise CommandError('a school with this code already exists; nothing was changed')
        with transaction.atomic():
            school = School.objects.create(code=code, name=name[:School._meta.get_field('name').max_length])
            audit.record(audit.SYSTEM, audit.SCHOOL_CREATE, school, school=school, detail='cmd')
            call_command('seed_vocabulary', '--school', code, stdout=self.stdout)
        self.stdout.write(f'{school.code}: created. Next: SchoolAdmin account, membership, modules '
                          f'(docs/manuals/platform-admin.md).')
