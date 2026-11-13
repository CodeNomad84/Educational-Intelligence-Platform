"""Mission module: evaluation hook for a LATER comparison of the rules against a model on held-out, anonymised data.

Nothing here trains, calls or stores a model, and nothing leaves the process: these are plain functions a future offline
study can call. Rows carry a salted pseudonym, the grade and the rule outputs only (no name, id, observer or evidence text).
Pass a random ``salt`` per study and keep it out of the dataset, so the pseudonyms cannot be linked back. Exports for users stay off.
"""
import hashlib
import secrets

from .engine import period_profiles


def anonymised_rows(observations, period, salt=None, student_grades=None):
    """List of dicts, one per student with valid observations in ``period``: pseudonym, grade, indicator scores,
    branch scores and the evidence status of each. ``student_grades`` is an optional {student_id: grade}."""
    salt = salt or secrets.token_hex(16)
    rows = []
    for student_id, profile in period_profiles(observations, period, with_change=False).items():
        pseudonym = hashlib.sha256(f'{salt}:{student_id}'.encode()).hexdigest()[:16]
        rows.append({
            'pid': pseudonym, 'grade': (student_grades or {}).get(student_id), 'params_version': profile.params_version,
            'indicators': {c: (float(i.score) if i.score is not None else None) for c, i in profile.indicators.items()},
            'branches': {b: (float(r.score) if r.score is not None else None) for b, r in profile.branches.items()},
            'status': {b: r.status for b, r in profile.branches.items()},
        })
    return rows


def top_k_agreement(rows, other_scores, k=3):
    """Mean overlap (0..1) between the rules' top-k branches and another scorer's top-k, over pseudonyms present in both.
    ``other_scores``: {pid: {branch_code: score}}. Ties and unscored branches (None) are left out; the value is an
    agreement figure for a study, not an accuracy claim."""
    def top(scores):
        ranked = sorted((b for b, s in scores.items() if s is not None), key=lambda b: (-scores[b], b))
        return set(ranked[:k])

    overlaps = [len(top(r['branches']) & top(other_scores[r['pid']])) / k for r in rows if r['pid'] in other_scores]
    return sum(overlaps) / len(overlaps) if overlaps else None
