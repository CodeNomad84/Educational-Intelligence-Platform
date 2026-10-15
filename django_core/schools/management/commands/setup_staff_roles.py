"""Create the ADR-0005 staff role groups with zero model permissions (proposal 0002 C4, ADR-0005 §9).

    manage.py setup_staff_roles                              create groups, verify zero permissions, report
    manage.py setup_staff_roles --fix                        also remove any permission found on those groups
    manage.py setup_staff_roles --grant-admin-assignments    also grant the school-structure permissions to
                                                             the existing ``Admin`` group (never ``auth.*``)

Creating a group changes nobody's access: ``roles_for()`` does not read the new groups until C5a, and the
groups carry no model permissions. The command never creates users and never sets ``is_staff`` or
``is_superuser``. ``Admin`` is not renamed here (ADR-0010).
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from students.access import ADMIN, COUNSELOR, GRADE_LEAD, TEACHER

STAFF_ROLE_GROUPS = (TEACHER, GRADE_LEAD, COUNSELOR)

# model -> permission actions granted to the Admin group (schools app only; ADR-0003 §6, ADR-0005 §9).
# School is view-only (its add/delete stay superuser-only in the admin); classes cannot be deleted from here.
ADMIN_ASSIGNMENT_GRANTS = {
    'school': ('view',),
    'schoolclass': ('view', 'add', 'change'),
    'teacherassignment': ('view', 'add', 'change', 'delete'),
}


class Command(BaseCommand):
    help = 'Create the Teacher/GradeLead/Counselor groups with zero model permissions; optional Admin grants.'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true',
                            help='remove any model permission found on the staff role groups (listed first)')
        parser.add_argument('--grant-admin-assignments', action='store_true',
                            help='grant school-structure permissions to the existing Admin group')

    def handle(self, *args, **opts):
        violations = 0
        for name in STAFF_ROLE_GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            self.stdout.write(f'group {name}: {"created" if created else "exists"}')
            codenames = sorted(group.permissions.values_list('content_type__app_label', 'codename'))
            if not codenames:
                self.stdout.write('  permissions: 0 (ok)')
                continue
            listing = ', '.join(f'{app}.{code}' for app, code in codenames)
            if opts['fix']:
                group.permissions.clear()
                self.stdout.write(self.style.WARNING(f'  removed {len(codenames)} permission(s): {listing}'))
            else:
                violations += len(codenames)
                self.stdout.write(self.style.ERROR(
                    f'  VIOLATION: {len(codenames)} permission(s): {listing} (re-run with --fix to remove)'))

        if opts['grant_admin_assignments']:
            self._grant_admin()

        if violations:
            raise CommandError(
                f'{violations} model permission(s) found on staff role groups; nothing was removed '
                '(use --fix to remove them).'
            )
        self.stdout.write(self.style.SUCCESS('staff role groups: zero model permissions'))

    def _grant_admin(self):
        try:
            admin_group = Group.objects.get(name=ADMIN)
        except Group.DoesNotExist:
            raise CommandError(f'Group "{ADMIN}" does not exist; create it first (nothing was granted).')
        wanted = []
        for model, actions in ADMIN_ASSIGNMENT_GRANTS.items():
            for action in actions:
                wanted.append(f'{action}_{model}')
        perms = list(Permission.objects.filter(content_type__app_label='schools', codename__in=wanted))
        missing = sorted(set(wanted) - {p.codename for p in perms})
        if missing:
            raise CommandError(f'Permissions not found (run migrate first): {", ".join(missing)}')
        admin_group.permissions.add(*perms)
        self.stdout.write(f'granted to {ADMIN}: ' + ', '.join(sorted(p.codename for p in perms)))
        self.stdout.write('note: members still need is_staff to open the admin site; this command never sets it.')
