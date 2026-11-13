"""Rule-quality aggregates for the SchoolAdmin (0025 f): per rule code, how many of its alerts were raised, accepted and dismissed
(by reason code). Counts only; any number under MIN_GROUP is withheld (None), and a rule with fewer than MIN_GROUP alerts shows
nothing at all. No per-student rows, no names, no alert ids."""
from collections import defaultdict

from django.db.models import Count

from .models import Alert, RuleHit
from .rules import MIN_GROUP


def rule_quality(school_id):
    counts = defaultdict(lambda: defaultdict(int))
    rows = (RuleHit.objects.filter(school_id=school_id)
            .values('rule__code', 'alert__status', 'alert__dismiss_reason').annotate(n=Count('pk')))
    for row in rows:
        key = 'dismissed:' + row['alert__dismiss_reason'] if row['alert__status'] == Alert.DISMISSED else row['alert__status']
        counts[row['rule__code']][key] += row['n']
    out = []
    shown = lambda n: n if n >= MIN_GROUP else None      # noqa: E731
    for code in sorted(counts):
        c = counts[code]
        raised = sum(c.values())
        if raised < MIN_GROUP:
            out.append({'code': code, 'raised': None, 'accepted': None, 'dismissed': {}, 'withheld': True})
            continue
        accepted = shown(c.get(Alert.ACCEPTED, 0))
        dismissed = {reason: shown(c.get('dismissed:' + reason, 0)) for reason, _label in Alert.DISMISS_REASONS
                     if c.get('dismissed:' + reason, 0)}
        withheld_cell = accepted is None or None in dismissed.values()
        # When any cell is withheld the row total is hidden too, so a withheld cell cannot be recovered by subtraction.
        out.append({'code': code, 'raised': None if withheld_cell else raised, 'accepted': accepted, 'withheld': False,
                    'dismissed': dismissed})
    return out
