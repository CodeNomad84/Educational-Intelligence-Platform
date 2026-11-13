"""Alert services (change 0022). Views stay thin: every rule lives here and in ``students.access``.

``raise_alert`` is the single entry point (a rule engine will call it later with ``raised_by=None``). ``raise_alert_as`` adds
the permission check for a person. A review is ONE conditional UPDATE (``status='new'`` in the WHERE), so two reviewers can
never both win. Audit rows hold ids and codes only.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from schools import audit
from students.access import ADMIN, COUNSELOR, TEACHER, raisable_students, reviewable_alerts, roles_for, visible_alerts

from .models import Alert, RiskEvent


class LoopError(Exception):
    """A request that breaks a rule of the loop (bad transition, missing reason...). ``code`` is a short fixed token."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def raise_alert(student, *, risk_type, severity, message, explanation, detected_by, raised_by=None, risk_score=None):
    """Create one RiskEvent and its Alert for ``student`` (school copied from the student). No permission check here."""
    if not message or not explanation:
        raise LoopError('text_required')
    with transaction.atomic():
        event = RiskEvent.objects.create(
            school_id=student.school_id, student=student, risk_type=risk_type, severity=severity,
            detected_by=detected_by, explanation=explanation, risk_score=risk_score)
        alert = Alert.objects.create(school_id=student.school_id, student=student, risk_event=event,
                                     raised_by=raised_by, message=message)
    from .notifications import notify_alert      # P6-2: after the alert is committed to the transaction; never blocks it

    notify_alert(alert)
    return alert


def _detected_by(user):
    roles = roles_for(user)
    return (RiskEvent.DetectedBy.COUNSELOR if COUNSELOR in roles else
            RiskEvent.DetectedBy.TEACHER if TEACHER in roles and ADMIN not in roles else RiskEvent.DetectedBy.ADMIN)


def raise_alert_as(user, student, *, risk_type, severity, message):
    if not raisable_students(user).filter(pk=student.pk).exists():
        raise PermissionDenied
    if risk_type not in RiskEvent.RiskType.values or severity not in RiskEvent.Severity.values:
        raise LoopError('bad_choice')
    # The person's one text is both the alert message and the event explanation (the event must carry a reason).
    alert = raise_alert(student, risk_type=risk_type, severity=severity, message=message, explanation=message,
                        detected_by=_detected_by(user), raised_by=user)
    audit.record(user, audit.ALERT_RAISE, alert, detail=risk_type)
    return alert


def review_alert(user, alert, decision, reason='', note=''):
    """Accept or dismiss a NEW alert. Dismissal needs a reason code; ``other`` needs a note."""
    if not reviewable_alerts(user).filter(pk=alert.pk).exists():
        raise PermissionDenied
    note = (note or '').strip()
    if decision == Alert.ACCEPTED:
        reason = ''
    elif decision == Alert.DISMISSED:
        if reason not in dict(Alert.DISMISS_REASONS):
            raise LoopError('reason_required')
        if reason == 'other' and not note:
            raise LoopError('note_required')
    else:
        raise LoopError('bad_decision')
    changed = Alert.objects.filter(pk=alert.pk, status=Alert.NEW).update(
        status=decision, reviewed_by=user, reviewed_at=timezone.now(), dismiss_reason=reason, review_note=note[:300])
    if not changed:
        raise LoopError('already_reviewed')
    audit.record(user, audit.ALERT_REVIEW, alert, detail=decision if decision == Alert.ACCEPTED else f'dismissed:{reason}')


def reopen_alert(user, alert):
    """SchoolAdmin only: a dismissed alert becomes NEW again."""
    from students.access import school_ids_for_admin

    if ADMIN not in roles_for(user) or alert.school_id not in school_ids_for_admin(user) \
            or not visible_alerts(user).filter(pk=alert.pk).exists():
        raise PermissionDenied
    changed = Alert.objects.filter(pk=alert.pk, status=Alert.DISMISSED).update(
        status=Alert.NEW, reviewed_by=None, reviewed_at=None, dismiss_reason='', review_note='')
    if not changed:
        raise LoopError('not_dismissed')
    audit.record(user, audit.ALERT_REOPEN, alert)
