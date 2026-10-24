"""Template context: role group names come from the constants, never from literals in templates."""
from django.urls import NoReverseMatch, reverse

from schools.entitlements import MODULES, enabled_modules_for_user, trial_notices, user_school_ids
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PARENT, STUDENT, TEACHER, roles_for

from .module_info import label

_REAL_ROUTE = {'tutor_ai': 'dashboard:me_assistant', 'advisor_ai': 'dashboard:demo_assistant'}


def _module_url(key, enabled):
    if enabled and key in _REAL_ROUTE:
        try:
            return reverse(_REAL_ROUTE[key])
        except NoReverseMatch:
            pass
    return reverse('dashboard:module_info', args=[key])


def role_names(request):
    """Menus follow ALL of the user's roles (union), not the first group."""
    user = getattr(request, 'user', None)
    roles = roles_for(user)
    enabled = enabled_modules_for_user(user)
    school_ids = user_school_ids(user) if ADMIN in roles else set()
    return {'ADMIN_ROLE': ADMIN, 'IS_SCHOOL_ADMIN': ADMIN in roles, 'IS_TEACHER': TEACHER in roles,
            'IS_GRADE_LEAD': GRADE_LEAD in roles, 'IS_PARENT': PARENT in roles, 'IS_COUNSELOR': COUNSELOR in roles,
            'IS_STUDENT': STUDENT in roles,
            # ENABLED_MODULES: keys that are on (security-adjacent UI; the real gates are server-side).
            'ENABLED_MODULES': enabled,
            # VISIBLE_MODULES: all four sellable keys, locked ones included (they link to a static info page).
            'VISIBLE_MODULES': [{'key': k, 'label': label(k), 'enabled': k in enabled, 'url': _module_url(k, k in enabled)}
                                for k in MODULES],
            # SchoolAdmin banner: trials with <= 14 days left or just ended
            'TRIAL_NOTICES': [{'label': label(k), 'kind': kind, 'days': days} for k, kind, days in trial_notices(school_ids)]
            if school_ids else []}
