"""Create a school's first parameter version: the owner-confirmed default table as an ACTIVE ``WeightSet`` (version 1).
Idempotent: a school that already has any weight set is left alone."""
from django.db import transaction
from django.utils import timezone

from .defaults import BRANCHES, DIFF_THRESHOLD, MIN_ACTIVITIES, MIN_OBSERVATIONS, WEIGHTS
from .models import Branch, Indicator, Weight, WeightSet


@transaction.atomic
def ensure_default_weight_set(school, *, actor=None):
    """Return ``(weight_set, created)``."""
    existing = WeightSet.objects.filter(school=school).first()
    if existing:
        return existing, False
    ws = WeightSet.objects.create(school=school, version=1, min_observations=MIN_OBSERVATIONS, min_activities=MIN_ACTIVITIES,
                                  diff_threshold=DIFF_THRESHOLD, note='default (owner-confirmed table, not validated)', created_by=actor)
    indicators, branches = {i.code: i for i in Indicator.objects.all()}, {b.code: b for b in Branch.objects.all()}
    for row, indicator_code in zip(WEIGHTS, sorted(indicators)):
        for percent, (branch_code, _f, _n) in zip(row, BRANCHES):
            Weight.objects.create(weight_set=ws, indicator=indicators[indicator_code], branch=branches[branch_code], percent=percent)
    ws.status, ws.approved_by, ws.approved_at = WeightSet.ACTIVE, actor, timezone.now()
    ws.save()
    return ws, True
