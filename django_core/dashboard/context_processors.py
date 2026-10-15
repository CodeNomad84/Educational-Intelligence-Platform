"""Template context: role group names come from the constants, never from literals in templates."""
from students.access import ADMIN


def role_names(request):
    return {'ADMIN_ROLE': ADMIN}
