"""Classification of ``SchoolMembership`` rows against the current account state (changes/0010 S2).

One place, used by ``check_school_memberships`` and by the readiness check. Reasons follow the order of
``SchoolMembership.clean`` (first match wins): inactive account, superuser, outside ``SchoolAdmin``, also
``PlatformAdmin``. A row is an ORPHAN when its user no longer qualifies; an active orphan grants nothing today
(``school_ids_for_admin`` re-checks), but it would come back if the user's groups changed again.
"""
from collections import defaultdict

from django.contrib.auth import get_user_model

from students.access import ADMIN, PLATFORM_ADMIN

INACTIVE_USER = 'user_inactive'
SUPERUSER = 'user_superuser'
OUTSIDE_GROUP = 'user_outside_school_admin_group'
PLATFORM = 'user_in_platform_admin'
REASONS = (INACTIVE_USER, SUPERUSER, OUTSIDE_GROUP, PLATFORM)


def classify_memberships():
    """Return a list of dicts: ``id, user_id, school_id, is_active, reason`` (None when the user qualifies) and
    ``user_in_platform_admin`` (True whenever the user holds PlatformAdmin, whatever the first reason is)."""
    from schools.models import SchoolMembership

    User = get_user_model()
    rows = list(SchoolMembership.objects.values('id', 'user_id', 'school_id', 'is_active'))
    user_ids = {r['user_id'] for r in rows}
    users = {u['pk']: u for u in User.objects.filter(pk__in=user_ids).values('pk', 'is_active', 'is_superuser')}
    groups = defaultdict(set)
    for user_id, name in User.groups.through.objects.filter(
            user_id__in=user_ids, group__name__in=(ADMIN, PLATFORM_ADMIN)).values_list('user_id', 'group__name'):
        groups[user_id].add(name)
    out = []
    for r in rows:
        user = users.get(r['user_id'])
        held = groups.get(r['user_id'], set())
        if user is None or not user['is_active']:
            reason = INACTIVE_USER
        elif user['is_superuser']:
            reason = SUPERUSER
        elif ADMIN not in held:
            reason = OUTSIDE_GROUP
        elif PLATFORM_ADMIN in held:
            reason = PLATFORM
        else:
            reason = None
        out.append({**r, 'reason': reason, 'user_in_platform_admin': PLATFORM_ADMIN in held})
    return out
