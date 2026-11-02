"""Template context: role group names come from the constants, never from literals in templates."""
from django.urls import NoReverseMatch, reverse

from schools.entitlements import MODULES, enabled_modules_for_user, trial_notices, user_school_ids
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PARENT, STUDENT, TEACHER, roles_for

from .module_info import label
from .operator_page import is_platform_operator

# Top-bar role label (design system P8-3), in this order.
ROLE_LABELS = ((ADMIN, 'مدیر مدرسه'), (GRADE_LEAD, 'مربی پایه'), (COUNSELOR, 'مشاور'), (TEACHER, 'معلم'), (PARENT, 'ولی'),
               (STUDENT, 'دانش‌آموز'))
_REAL_ROUTE = {'tutor_ai': 'dashboard:me_assistant', 'advisor_ai': 'dashboard:demo_assistant'}


def _module_url(key, enabled):
    if enabled and key in _REAL_ROUTE:
        try:
            return reverse(_REAL_ROUTE[key])
        except NoReverseMatch:
            pass
    return reverse('dashboard:module_info', args=[key])


def _school_name(school_ids):
    if len(school_ids) > 1:
        return f'{len(school_ids)} مدرسه'
    from schools.models import School
    return School.objects.filter(pk__in=school_ids).values_list('name', flat=True).first() or '' if school_ids else ''


def role_names(request):
    """Menus follow ALL of the user's roles (union), not the first group."""
    user = getattr(request, 'user', None)
    roles = roles_for(user)
    enabled = enabled_modules_for_user(user)
    school_ids = user_school_ids(user) if ADMIN in roles else set()
    own_schools = school_ids or (user_school_ids(user) if roles else set())
    resets_on = False
    if GRADE_LEAD in roles:     # the menu entry only exists where the SchoolAdmin allowed it (otherwise the page is a 403)
        from schools.models import School
        resets_on = School.objects.filter(pk__in=user_school_ids(user), grade_leads_may_reset_passwords=True).exists()
    notif = 0
    if roles & {ADMIN, GRADE_LEAD, COUNSELOR}:
        from risk.notifications import unread_count      # P6-2: only rows still inside the user's alert / plan scope
        notif = unread_count(user)
    return {'GRADE_RESETS_ENABLED': resets_on, 'NOTIF_COUNT': notif, 'ADMIN_ROLE': ADMIN, 'IS_SCHOOL_ADMIN': ADMIN in roles, 'IS_TEACHER': TEACHER in roles,
            'IS_GRADE_LEAD': GRADE_LEAD in roles, 'IS_PARENT': PARENT in roles, 'IS_COUNSELOR': COUNSELOR in roles,
            'IS_STUDENT': STUDENT in roles, 'IS_PLATFORM_OPERATOR': is_platform_operator(user),
            # Top bar only: the user's own school (from the schools the user already belongs to) and role label.
            'SCHOOL_NAME': _school_name(own_schools),
            'ROLE_LABEL': '، '.join(text for role, text in ROLE_LABELS if role in roles)
            or ('مدیر پلتفرم' if is_platform_operator(user) else ''),
            # ENABLED_MODULES: keys that are on (security-adjacent UI; the real gates are server-side).
            'ENABLED_MODULES': enabled,
            # VISIBLE_MODULES: all four sellable keys, locked ones included (they link to a static info page).
            'VISIBLE_MODULES': [{'key': k, 'label': label(k), 'enabled': k in enabled, 'url': _module_url(k, k in enabled)}
                                for k in MODULES],
            # SchoolAdmin banner: trials with <= 14 days left or just ended
            'TRIAL_NOTICES': [{'label': label(k), 'kind': kind, 'days': days} for k, kind, days in trial_notices(school_ids)]
            if school_ids else []}
