"""Create the empty ``PlatformAdmin`` group (ADR-0012, proposal changes/0010, stage S1).

    manage.py setup_platform_role          create the group if missing, verify it has no permissions, report
    manage.py setup_platform_role --fix    also remove any permission found on the group

The group is created with ZERO model permissions and no members: creating it changes nobody's access
(``roles_for`` does not recognise it, ``PLATFORM_ADMIN`` is not in ``ALL_ROLES``). The command never creates
users and never sets ``is_staff`` or ``is_superuser``. The permissions the role will hold are granted by a later
stage, and the command will list them explicitly then.
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from students.access import PLATFORM_ADMIN


class Command(BaseCommand):
    help = 'Create the PlatformAdmin group with zero model permissions and no members.'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='remove any model permission found on the group')

    def handle(self, *args, **opts):
        group, created = Group.objects.get_or_create(name=PLATFORM_ADMIN)
        self.stdout.write(f'group {PLATFORM_ADMIN}: {"created" if created else "exists"}')
        codenames = sorted(group.permissions.values_list('content_type__app_label', 'codename'))
        if codenames:
            listing = ', '.join(f'{app}.{code}' for app, code in codenames)
            if opts['fix']:
                group.permissions.clear()
                self.stdout.write(self.style.WARNING(f'  removed {len(codenames)} permission(s): {listing}'))
            else:
                raise CommandError(
                    f'{len(codenames)} model permission(s) found on {PLATFORM_ADMIN}: {listing} '
                    '(nothing was removed; re-run with --fix).')
        else:
            self.stdout.write('  permissions: 0 (ok)')
        self.stdout.write(f'  members: {group.user_set.count()}')
        self.stdout.write(self.style.SUCCESS(f'{PLATFORM_ADMIN}: zero model permissions'))
