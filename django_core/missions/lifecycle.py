"""Mission slice 2b: the lifecycle of a weight set (draft > simulated > pending approval > active > retired) and the simulation.

All writes to a weight set go through here, so the rules live in one place (the model additionally refuses edits to
active/retired sets and to cells outside draft):

* ``draft``: weights and thresholds are editable (``save_draft``); columns need not sum to 100 yet.
* draft -> ``simulated`` only through ``simulate`` (every column must sum to 100, thresholds valid): the engine is rerun on the
  school's existing observations and the result is shown as AGGREGATE differences, never stored, never per student.
* simulated -> ``pending_approval`` (``submit``); pending -> ``active`` (``approve``): the previous active set becomes ``retired``
  in the same transaction. draft/simulated/pending -> draft (``reopen``) to edit again.
* Active and retired sets never change; ``clone`` creates the next version as a new draft. At most one unfinished set
  (draft, simulated or pending) exists per school.
* Reports and plans already store the ``params_version`` (the set id) they were computed with, so an activation never rewrites
  history. Any SchoolAdmin of the school may approve; a separate approver is NOT required (owner decision pending: small
  schools have one administrator).
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .engine import period_profiles
from .models import Branch, Indicator, Observation, Weight, WeightSet

UNFINISHED = (WeightSet.DRAFT, WeightSet.SIMULATED, WeightSet.PENDING)
MIN_GROUP = 5          # a simulation over fewer students than this is withheld

LIMITS = {'min_observations': (1, 20), 'min_activities': (1, 10)}


def _decimal(raw, lo, hi, name):
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        raise ValidationError(f'{name}: عدد نامعتبر.') from None
    if not (Decimal(lo) <= value <= Decimal(hi)) or value != value.quantize(Decimal('0.1')):
        raise ValidationError(f'{name}: عددی بین {lo} و {hi} با یک رقم اعشار.')
    return value


def parse_settings(post):
    """Validate the threshold fields of the editor. Returns a dict of model values; raises ValidationError."""
    out = {}
    for name, (lo, hi) in LIMITS.items():
        raw = (post.get(name) or '').strip()
        if not raw.isdigit() or not lo <= int(raw) <= hi:
            raise ValidationError(f'{name}: عدد صحیح بین {lo} و {hi}.')
        out[name] = int(raw)
    out['diff_threshold'] = _decimal(post.get('diff_threshold'), '0.5', '4.0', 'diff_threshold')
    out['strong_at'] = _decimal(post.get('strong_at'), '3.0', '5.0', 'strong_at')
    out['growth_at'] = _decimal(post.get('growth_at'), '1.0', '3.5', 'growth_at')
    if out['growth_at'] >= out['strong_at']:
        raise ValidationError('آستانهٔ «نیازمند رشد» باید کمتر از آستانهٔ «برجسته» باشد.')
    out['show_x20'] = bool(post.get('show_x20'))
    note = (post.get('note') or '').strip()
    if len(note) > 200:
        raise ValidationError('note: حداکثر ۲۰۰ نویسه.')
    out['note'] = note
    return out


def parse_cells(post, indicators, branches):
    """{(indicator_id, branch_id): percent} from the posted grid; every cell must be an integer 0..100."""
    cells = {}
    for ind in indicators:
        for br in branches:
            raw = (post.get(f'w_{ind.code}_{br.code}') or '').strip()
            if not raw.isdigit() or int(raw) > 100:
                raise ValidationError(f'وزن شاخص {ind.code} در «{br.name_fa}» باید عدد صحیح ۰ تا ۱۰۰ باشد.')
            cells[(ind.pk, br.pk)] = int(raw)
    return cells


@transaction.atomic
def save_draft(weight_set, *, settings, cells):
    weight_set = WeightSet.objects.select_for_update().get(pk=weight_set.pk)
    if weight_set.status != WeightSet.DRAFT:
        raise ValidationError('فقط پیش‌نویس قابل ویرایش است.')
    for name, value in settings.items():
        setattr(weight_set, name, value)
    weight_set.save()
    for (indicator_id, branch_id), percent in cells.items():
        Weight.objects.update_or_create(weight_set=weight_set, indicator_id=indicator_id, branch_id=branch_id,
                                        defaults={'percent': percent})
    return weight_set


def _move(weight_set, allowed_from, to, *, actor=None):
    with transaction.atomic():
        locked = WeightSet.objects.select_for_update().get(pk=weight_set.pk)
        if locked.status not in allowed_from:
            raise ValidationError('این تغییر وضعیت در وضعیت فعلی مجاز نیست.')
        locked.status = to
        locked.save()
        return locked


def reopen(weight_set):
    return _move(weight_set, (WeightSet.SIMULATED, WeightSet.PENDING), WeightSet.DRAFT)


def submit(weight_set):
    return _move(weight_set, (WeightSet.SIMULATED,), WeightSet.PENDING)


@transaction.atomic
def approve(weight_set, actor):
    locked = WeightSet.objects.select_for_update().get(pk=weight_set.pk)
    if locked.status != WeightSet.PENDING:
        raise ValidationError('فقط نسخهٔ «منتظر تأیید» فعال می‌شود.')
    if not locked.sums_ok():
        raise ValidationError('مجموع هر ستون باید ۱۰۰ باشد.')
    for old in WeightSet.objects.select_for_update().filter(school_id=locked.school_id, status=WeightSet.ACTIVE):
        old.status = WeightSet.RETIRED
        old.save()
    locked.status, locked.approved_by, locked.approved_at = WeightSet.ACTIVE, actor, timezone.now()
    locked.save()
    return locked


@transaction.atomic
def clone(source, actor):
    """Next version as a new draft with the same weights and thresholds; refused while an unfinished set exists."""
    if WeightSet.objects.filter(school_id=source.school_id, status__in=UNFINISHED).exists():
        raise ValidationError('یک نسخهٔ در حال کار (پیش‌نویس، شبیه‌سازی‌شده یا منتظر تأیید) وجود دارد؛ ابتدا آن را تمام کنید.')
    version = (WeightSet.objects.filter(school_id=source.school_id).aggregate(m=Max('version'))['m'] or 0) + 1
    copy = WeightSet.objects.create(
        school_id=source.school_id, version=version, min_observations=source.min_observations, min_activities=source.min_activities,
        diff_threshold=source.diff_threshold, show_x20=source.show_x20, strong_at=source.strong_at, growth_at=source.growth_at,
        note=f'نسخهٔ {source.version} را کپی کرد'[:200], created_by=actor)
    for w in source.weights.all():
        Weight.objects.create(weight_set=copy, indicator_id=w.indicator_id, branch_id=w.branch_id, percent=w.percent)
    return copy


def _top3(profile):
    scored = [(code, b.score) for code, b in profile.branches.items() if b.score is not None]
    return {code for code, _s in sorted(scored, key=lambda x: (-x[1], x[0]))[:3]}


def run_simulation(candidate, active, period):
    """Rerun the engine on the school's observations (period ``period``) with the ACTIVE and the CANDIDATE set; return aggregate
    differences only (no student, observer or evidence), or ``{'withheld': True}`` when fewer than MIN_GROUP students have data."""
    observations = Observation.objects.filter(session__activity__school_id=candidate.school_id)
    before = period_profiles(observations, period, weight_set=active, with_change=False)
    after = period_profiles(observations, period, weight_set=candidate, with_change=False)
    n = len(before)
    if n < MIN_GROUP:
        return {'withheld': True, 'n': n, 'min_group': MIN_GROUP}
    rows = []
    for branch in Branch.objects.all():
        pairs = [(before[sid].branches[branch.code], after[sid].branches[branch.code]) for sid in before]
        both = [(b.score, a.score) for b, a in pairs if b.score is not None and a.score is not None]
        rows.append({
            'branch': branch.name_fa,
            'mean_before': sum(b for b, _ in both) / len(both) if len(both) >= MIN_GROUP else None,
            'mean_after': sum(a for _, a in both) / len(both) if len(both) >= MIN_GROUP else None,
            'changed': sum(1 for b, a in both if abs(a - b) >= Decimal('0.01')) if len(both) >= MIN_GROUP else None,
            'scored_before': sum(1 for b, _ in pairs if b.score is not None),
            'scored_after': sum(1 for _, a in pairs if a.score is not None),
            'status_changed': sum(1 for b, a in pairs if b.status != a.status),
        })
    top_changed = sum(1 for sid in before if _top3(before[sid]) != _top3(after[sid]))
    return {'withheld': False, 'n': n, 'rows': rows, 'top3_changed': top_changed}


@transaction.atomic
def simulate(weight_set, active, period):
    """draft -> simulated (when valid) and the aggregate result. A simulated/pending set can be re-simulated without a change."""
    locked = WeightSet.objects.select_for_update().get(pk=weight_set.pk)
    if locked.status == WeightSet.DRAFT:
        if not locked.sums_ok():
            raise ValidationError('مجموع هر ستون باید ۱۰۰ باشد.')
        locked.status = WeightSet.SIMULATED
        locked.save()
    elif locked.status not in (WeightSet.SIMULATED, WeightSet.PENDING):
        raise ValidationError('فقط پیش‌نویس یا نسخهٔ شبیه‌سازی‌شده را می‌توان شبیه‌سازی کرد.')
    return locked, run_simulation(locked, active, period)
