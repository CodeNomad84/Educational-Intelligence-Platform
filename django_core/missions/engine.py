"""Mission module, Slice 2: the rule engine, exactly as the weight guide describes it. Deterministic, no ML, no storage.

Nothing here is persisted: a profile is computed on demand from the observations the CALLER may see (pass
``visible_observations(user)``; the engine adds no access rule of its own) and from one ``WeightSet`` version. The result
is "initial, not validated, not a decision" and never a stored label or rank.

Per indicator: valid evidence = scored rows ("not observed" excluded); rows of one activity sharing a non-blank
``dedupe_key`` count as ONE evidence (their mean); evidence is averaged per activity, then activities are averaged with
equal weight (a busier activity gains no weight). Fewer than ``min_observations`` evidences in ``min_activities``
activities = provisional. Per branch: sum(indicator score x weight / 100); a branch with a positive-weight indicator that
has no valid observation has NO score (``None``, listed in ``missing``), never a 0 or 1. Periods are never blended; the
change against the previous period is reported next to the current one.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Indicator, Period, WeightSet

NOTICE = 'اولیه، اعتبارسنجی‌نشده و تصمیم نیست'   # shown with every result

NEEDS_MORE = 'needs_more_observation'
NEEDS_DIFF = 'needs_difference_review'
USABLE = 'usable_for_initial_suggestion'
STATUS_LABELS = {NEEDS_MORE: 'نیازمند تکمیل مشاهده', NEEDS_DIFF: 'نیازمند بررسی تفاوت‌ها', USABLE: 'قابل استفاده برای پیشنهاد اولیه'}

TWO_PLACES = Decimal('0.01')


def _q(value):
    return None if value is None else Decimal(value).quantize(TWO_PLACES)


def _mean(values):
    return Decimal(sum(values)) / len(values)


@dataclass
class IndicatorResult:
    code: int
    score: Decimal | None = None              # aggregated 1..5, None when nothing valid was observed
    evidences: int = 0                        # independent valid evidences (after de-duplication)
    activities: int = 0
    provisional: bool = True
    per_activity: dict = field(default_factory=dict)   # activity_id -> mean (preserved, never hidden in the average)
    per_observer: dict = field(default_factory=dict)   # observer_id -> mean over that observer's own rows
    activity_spread: Decimal = Decimal(0)
    observer_spread: Decimal = Decimal(0)
    differs: bool = False
    status: str = NEEDS_MORE
    change: Decimal | None = None             # vs previous period; None when either side has no score


@dataclass
class BranchResult:
    code: str
    score: Decimal | None = None              # 1..5
    score_x20: Decimal | None = None          # only when the weight set says so
    missing: list = field(default_factory=list)        # positive-weight indicators with no valid observation
    provisional: list = field(default_factory=list)    # positive-weight indicators still provisional
    differing: list = field(default_factory=list)      # positive-weight indicators whose situations/observers differ
    status: str = NEEDS_MORE
    change: Decimal | None = None


@dataclass
class Profile:
    student_id: int
    period_id: int
    params_version: int                       # WeightSet.pk
    indicators: dict                          # code -> IndicatorResult
    branches: dict                            # branch code -> BranchResult
    previous_period_id: int | None = None
    notice: str = NOTICE


def aggregate_indicator(code, rows, weight_set):
    """``rows``: iterable of ``(activity_id, observer_id, score, dedupe_key)`` of ONE student and indicator, "not observed"
    rows already left out."""
    rows = list(rows)
    by_activity = {}
    for activity_id, _observer, score, key in rows:
        by_activity.setdefault(activity_id, {})
        group = key or object()                       # a blank key is its own independent evidence
        by_activity[activity_id].setdefault(group, []).append(score)
    per_activity = {a: _mean([_mean(v) for v in groups.values()]) for a, groups in by_activity.items()}
    evidences = sum(len(groups) for groups in by_activity.values())
    result = IndicatorResult(code=code, evidences=evidences, activities=len(per_activity), per_activity=per_activity)
    if not per_activity:
        return result
    result.score = _mean(per_activity.values())
    result.provisional = evidences < weight_set.min_observations or len(per_activity) < weight_set.min_activities
    observers = {}
    for _activity, observer_id, score, _key in rows:
        observers.setdefault(observer_id, []).append(score)
    result.per_observer = {o: _mean(v) for o, v in observers.items()}
    threshold = Decimal(weight_set.diff_threshold)
    spread = lambda values: (max(values) - min(values)) if len(values) > 1 else Decimal(0)
    result.activity_spread, result.observer_spread = spread(list(per_activity.values())), spread(list(result.per_observer.values()))
    result.differs = result.activity_spread >= threshold or result.observer_spread >= threshold
    result.status = NEEDS_MORE if result.provisional else NEEDS_DIFF if result.differs else USABLE
    return result


def aggregate_branch(branch_code, percents, indicators, weight_set):
    """``percents``: {indicator_code: percent} of this branch; ``indicators``: {code: IndicatorResult}."""
    result = BranchResult(code=branch_code)
    positive = {code: p for code, p in percents.items() if p > 0}       # a zero weight never blocks or affects the branch
    result.missing = sorted(c for c in positive if indicators[c].score is None)
    result.provisional = sorted(c for c in positive if indicators[c].score is not None and indicators[c].provisional)
    result.differing = sorted(c for c in positive if indicators[c].score is not None and indicators[c].differs)
    if not result.missing:
        result.score = sum((indicators[c].score * p / 100 for c, p in positive.items()), Decimal(0))
        if weight_set.show_x20:
            result.score_x20 = result.score * 20
    result.status = NEEDS_MORE if result.missing or result.provisional else NEEDS_DIFF if result.differing else USABLE
    return result


def _weights(weight_set):
    table = {}
    for indicator_code, branch_code, percent in weight_set.weights.values_list('indicator__code', 'branch__code', 'percent'):
        table.setdefault(branch_code, {})[indicator_code] = percent
    return table


def build_profile(student_id, period_id, rows, weight_set, table=None, indicator_codes=None):
    """``rows``: ``(indicator_code, activity_id, observer_id, score, dedupe_key)`` of ONE student in ONE period."""
    table = table if table is not None else _weights(weight_set)
    codes = indicator_codes if indicator_codes is not None else list(Indicator.objects.values_list('code', flat=True))
    grouped = {}
    for indicator_code, activity_id, observer_id, score, key in rows:
        grouped.setdefault(indicator_code, []).append((activity_id, observer_id, score, key))
    indicators = {c: aggregate_indicator(c, grouped.get(c, ()), weight_set) for c in codes}
    branches = {b: aggregate_branch(b, percents, indicators, weight_set) for b, percents in table.items()}
    return Profile(student_id, period_id, weight_set.pk, indicators, branches)


def _rows_by_student(observations, period, student_ids=None):
    qs = observations.filter(session__activity__period=period, not_observed=False, score__isnull=False)
    if student_ids is not None:
        qs = qs.filter(student_id__in=student_ids)
    grouped = {}
    for student_id, code, activity_id, observer_id, score, key in qs.values_list(
            'student_id', 'indicator__code', 'session__activity_id', 'session__observer_id', 'score', 'dedupe_key'):
        grouped.setdefault(student_id, []).append((code, activity_id, observer_id, Decimal(score), key))
    return grouped


def previous_period(period):
    """The nearest earlier period of the same school (by academic year start, then creation); None for the first."""
    earlier = Period.objects.filter(school_id=period.school_id).exclude(pk=period.pk)
    key = (period.academic_year.start_date, period.pk)
    earlier = [p for p in earlier.select_related('academic_year') if (p.academic_year.start_date, p.pk) < key]
    return max(earlier, key=lambda p: (p.academic_year.start_date, p.pk), default=None)


def _attach_change(current, previous):
    for code, ind in current.indicators.items():
        before = previous.indicators[code].score
        ind.change = ind.score - before if ind.score is not None and before is not None else None
    for code, br in current.branches.items():
        before = previous.branches[code].score
        br.change = br.score - before if br.score is not None and before is not None else None
    current.previous_period_id = previous.period_id


def active_weight_set(school):
    ws = WeightSet.objects.filter(school=school, status=WeightSet.ACTIVE).first()
    if ws is None:
        raise ValueError('no active weight set for this school')
    return ws


def period_profiles(observations, period, student_ids=None, weight_set=None, with_change=True):
    """{student_id: Profile} for the students that have visible valid observations in ``period``. ``observations`` is the
    caller's already-scoped queryset. The previous period is computed from the same scope, never blended in."""
    ws = weight_set or active_weight_set(period.school_id)
    table, codes = _weights(ws), list(Indicator.objects.values_list('code', flat=True))
    profiles = {sid: build_profile(sid, period.pk, rows, ws, table, codes)
                for sid, rows in _rows_by_student(observations, period, student_ids).items()}
    before = previous_period(period) if with_change else None
    if before is not None and profiles:
        for sid, rows in _rows_by_student(observations, before, list(profiles)).items():
            _attach_change(profiles[sid], build_profile(sid, before.pk, rows, ws, table, codes))
    return profiles


def student_profile(student, observations, period, weight_set=None):
    """One student's profile (an empty one, all "needs more observation", when nothing is visible)."""
    ws = weight_set or active_weight_set(period.school_id)
    found = period_profiles(observations, period, [student.pk], ws)
    return found.get(student.pk) or build_profile(student.pk, period.pk, [], ws)
