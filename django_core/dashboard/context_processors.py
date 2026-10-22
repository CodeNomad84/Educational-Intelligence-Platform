"""Template context: role group names come from the constants, never from literals in templates."""
from students.access import ADMIN, TEACHER, roles_for


def role_names(request):
    """Menus follow ALL of the user's roles (union), not the first group."""
    user = getattr(request, 'user', None)
    roles = roles_for(user)
    return {'ADMIN_ROLE': ADMIN, 'IS_SCHOOL_ADMIN': ADMIN in roles, 'IS_TEACHER': TEACHER in roles}
