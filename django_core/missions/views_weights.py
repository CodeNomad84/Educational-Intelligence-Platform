"""Mission slice 2b pages: the SchoolAdmin edits and approves the weights through the lifecycle in ``lifecycle.py``.

Gate on every view: ``role_required(ADMIN, module='mission')`` + the weight set must belong to a school of the admin's own
memberships with the module on (else 404) + ``require_module``. Only the SchoolAdmin: Grade Lead, teachers, counselor and the
platform operator are refused. Audit stores the version and a status code, never numbers. No export.
"""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.decorators import require_module, role_required
from schools import audit
from students.access import ADMIN, school_ids_for_admin

from . import lifecycle
from .access import MODULE, enabled_school_ids
from .engine import active_weight_set
from .models import Branch, Indicator, WeightSet
from .report import FOOTER, pick_period


def _own_set(request, pk):
    allowed = school_ids_for_admin(request.user) & enabled_school_ids(request.user)
    weight_set = get_object_or_404(WeightSet.objects.filter(school_id__in=allowed or [0]), pk=pk)
    require_module(weight_set.school_id, MODULE)
    return weight_set


def _grid(weight_set, indicators, branches):
    cells = {(i, b): p for i, b, p in weight_set.weights.values_list('indicator_id', 'branch_id', 'percent')}
    return [{'indicator': ind, 'cells': [{'branch': br, 'value': cells.get((ind.pk, br.pk), 0)} for br in branches]} for ind in indicators]


def _sums(rows, branches):
    return [sum(row['cells'][n]['value'] for row in rows) for n in range(len(branches))]


@role_required(ADMIN, module=MODULE)
@require_http_methods(['GET', 'POST'])
@never_cache
def detail(request, pk):
    weight_set = _own_set(request, pk)
    indicators, branches = list(Indicator.objects.all()), list(Branch.objects.all())
    errors = []
    if request.method == 'POST':
        if weight_set.status != WeightSet.DRAFT:
            raise Http404
        try:
            settings = lifecycle.parse_settings(request.POST)
            cells = lifecycle.parse_cells(request.POST, indicators, branches)
        except ValidationError as exc:
            errors = exc.messages
        else:
            lifecycle.save_draft(weight_set, settings=settings, cells=cells)
            audit.record(request.user, audit.MISSION_WEIGHTS_SAVE, weight_set, school=weight_set.school_id, detail=f'v{weight_set.version}')
            messages.success(request, 'پیش‌نویس ذخیره شد.')
            return redirect('missions:weight_detail', pk=weight_set.pk)
    rows = _grid(weight_set, indicators, branches)
    if request.method == 'POST' and errors:                              # keep what the admin typed
        for row in rows:
            for cell in row['cells']:
                raw = (request.POST.get(f'w_{row["indicator"].code}_{cell["branch"].code}') or '').strip()
                cell['value'] = int(raw) if raw.isdigit() else cell['value']
    unfinished = WeightSet.objects.filter(school_id=weight_set.school_id, status__in=lifecycle.UNFINISHED).exists()
    return render(request, 'missions/weight_detail.html', {
        'ws': weight_set, 'rows': rows, 'branches': branches, 'sums': _sums(rows, branches), 'errors': errors, 'footer': FOOTER,
        'editable': weight_set.status == WeightSet.DRAFT, 'can_clone': not unfinished,
        'transitions': {'simulate': weight_set.status in (WeightSet.DRAFT, WeightSet.SIMULATED, WeightSet.PENDING),
                        'submit': weight_set.status == WeightSet.SIMULATED, 'approve': weight_set.status == WeightSet.PENDING,
                        'reopen': weight_set.status in (WeightSet.SIMULATED, WeightSet.PENDING)}})


@role_required(ADMIN, module=MODULE)
@require_POST
def action(request, pk):
    weight_set = _own_set(request, pk)
    what = request.POST.get('action')
    try:
        if what == 'simulate':
            period, _ = pick_period(weight_set.school_id, request.POST.get('period'))
            active = active_weight_set(weight_set.school_id)
            if period is None:
                raise ValidationError('دوره‌ای تعریف نشده است.')
            weight_set, result = lifecycle.simulate(weight_set, active, period)
            audit.record(request.user, audit.MISSION_WEIGHTS_SIMULATE, weight_set, school=weight_set.school_id, detail=f'n{result["n"]}')
            return redirect(f"{reverse('missions:weight_simulation', args=[weight_set.pk])}?period={period.pk}")
        elif what == 'submit':
            weight_set = lifecycle.submit(weight_set)
        elif what == 'reopen':
            weight_set = lifecycle.reopen(weight_set)
        elif what == 'approve':
            weight_set = lifecycle.approve(weight_set, request.user)
        elif what == 'clone':
            weight_set = lifecycle.clone(weight_set, request.user)
        else:
            raise Http404
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return redirect('missions:weight_detail', pk=weight_set.pk)
    audit.record(request.user, audit.MISSION_WEIGHTS_STATUS, weight_set, school=weight_set.school_id, detail=f'{what}:v{weight_set.version}')
    messages.success(request, 'انجام شد.')
    return redirect('missions:weight_detail', pk=weight_set.pk)


@role_required(ADMIN, module=MODULE)
@never_cache
def simulation(request, pk):
    """The aggregate difference between the active set and this set; recomputed on read, never stored."""
    weight_set = _own_set(request, pk)
    if weight_set.status not in (WeightSet.DRAFT, WeightSet.SIMULATED, WeightSet.PENDING):
        raise Http404
    period, periods = pick_period(weight_set.school_id, request.GET.get('period'))
    try:
        active = active_weight_set(weight_set.school_id)
    except ValueError:
        active = None
    result = lifecycle.run_simulation(weight_set, active, period) if (period and active) else None
    return render(request, 'missions/weight_simulation.html', {'ws': weight_set, 'active': active, 'period': period, 'periods': periods,
                                                               'result': result, 'footer': FOOTER})
