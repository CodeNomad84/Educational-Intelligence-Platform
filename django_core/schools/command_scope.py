"""One rule for maintenance commands that can touch the data of several schools (S4(c), docs/changes/0019).

With exactly one School the old behaviour is unchanged. With more than one, a command that WRITES must be told which school
(``--school``/``--school-code``) or, for the seed commands whose purpose is "every school", must be given ``--all-schools``
explicitly; otherwise it stops with a clear message before anything is read or written. Read-only reports may still cover all
schools. ``schools/test_command_scope.py`` lists every management command and fails when a new one is not classified.
"""
from django.core.management.base import CommandError

from .models import School


def resolve_scope(code, *, writes, all_schools=False, option='--school-code'):
    """Return the ``School`` to work on, or ``None`` meaning "every school" (only when allowed)."""
    if code:
        school = School.objects.filter(code=code).first()
        if school is None:
            raise CommandError('unknown school code')
        return school
    if writes and not all_schools and School.objects.count() > 1:
        raise CommandError(f'more than one school exists: pass {option} <school code> '
                           f'(or --all-schools where the command allows it); nothing was changed.')
    return None
