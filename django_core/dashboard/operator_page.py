"""Platform operator overview (module key "base/platform": explicitly BASE, not a sellable module): for every school, the state of
each sellable module (locked / trial / licensed), its end date and days left, and the AI call counters against the caps.

Read only. School names, module keys and counters only: no student data and no personal names (the AI counters are counts per
school, module and day). Gate: an active staff account that is a superuser or a member of the PlatformAdmin group (the same
rule as the Django admin pages for module rows); a SchoolAdmin or any other role gets 403. Every view is audit-logged, one event
per school shown, so each school's own audit trail records that the platform looked.
"""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from schools import ai_guard, audit
from schools.entitlements import (ACTIVE_LICENSED, ACTIVE_TRIAL, LOCKED, MODULES, _active_rows, module_state)
from schools.models import AICallUsage, School

from .module_info import label

EXPIRING_DAYS = 14
STATE_LABELS = {LOCKED: 'قفل', ACTIVE_TRIAL: 'آزمایشی', ACTIVE_LICENSED: 'دارای مجوز'}
AI_MODULES = {'advisor_ai', 'tutor_ai', 'exams'}      # modules whose calls are counted by ai_guard


def is_platform_operator(user):
    from schools.admin import _is_platform_operator

    return bool(getattr(user, 'is_authenticated', False) and _is_platform_operator(user))


def _end_and_days(school_id, key, today):
    rows = list(_active_rows(school_id, key, today))
    if not rows:
        return None, None
    if any(r.ends_on is None for r in rows):
        return None, None                                  # an open-ended row: no end date
    end = max(r.ends_on for r in rows)
    return end, (end - today).days


def _usage(school, today):
    since = today - timedelta(days=29)
    rows = AICallUsage.objects.filter(school=school, day__gte=since)
    daily_cap, monthly_cap = ai_guard.caps_for(school)
    out = {}
    for key in sorted(AI_MODULES):
        mine = rows.filter(module_key=key)
        out[key] = {
            'last30': mine.aggregate(n=Sum('count'))['n'] or 0,
            'today': mine.filter(day=today).aggregate(n=Sum('count'))['n'] or 0,
            'month': mine.filter(day__year=today.year, day__month=today.month).aggregate(n=Sum('count'))['n'] or 0}
    return {'daily_cap': daily_cap, 'monthly_cap': monthly_cap, 'modules': out}


@login_required
@never_cache
def overview(request):
    if not is_platform_operator(request.user):
        raise PermissionDenied
    today = timezone.localdate()
    only_expiring = request.GET.get('expiring') == '1'
    schools = []
    for school in School.objects.order_by('name', 'pk'):
        modules = []
        for key in MODULES:
            state = module_state(school, key, today)
            end, days = _end_and_days(school.pk, key, today) if state != LOCKED else (None, None)
            modules.append({'key': key, 'label': label(key), 'state': state, 'state_label': STATE_LABELS[state], 'end': end,
                            'days': days, 'expiring': days is not None and days <= EXPIRING_DAYS})
        if only_expiring and not any(m['expiring'] for m in modules):
            continue
        schools.append({'school': school, 'modules': modules, 'usage': _usage(school, today)})
    for entry in schools:
        audit.record(request.user, audit.PLATFORM_OVERVIEW_VIEW, school=entry['school'], detail='x' if only_expiring else 'a')
    return render(request, 'dashboard/operator.html', {'schools': schools, 'only_expiring': only_expiring, 'expiring_days': EXPIRING_DAYS})
