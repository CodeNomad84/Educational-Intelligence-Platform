"""P6-2 in-app notifications (decision 51). Creation and reading both go through the access layer: a row is made only for a user who
can already review the alert / see the plan, and a row is shown only while that is still true. No text is stored."""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction

from students.access import reviewable_alerts, visible_plans

from .models import Notification

log = logging.getLogger(__name__)
TEXT = {Notification.ALERT_NEW: 'هشدار جدیدی برای بررسی دارید.',
        Notification.FOLLOWUP_DUE: 'سررسید یک برنامهٔ مداخله نزدیک است یا گذشته است.'}
DUE_SOON_DAYS = 7


def _candidates(student):
    """Users who MIGHT review this student's alerts; the access layer (``reviewable_alerts``) is the authority afterwards."""
    from schools.models import GradeLeadAssignment
    from students.access import ADMIN
    from students.models import Referral

    # SchoolAdmins by group (memberships are read only inside schools/); ``reviewable_alerts`` decides who really qualifies
    ids = set(get_user_model().objects.filter(groups__name=ADMIN, is_active=True).values_list('pk', flat=True))
    ids |= set(GradeLeadAssignment.objects.filter(school_id=student.school_id, grade=student.grade).values_list('user_id', flat=True))
    ids |= set(Referral.objects.filter(student=student, status='open').values_list('counselor_id', flat=True))
    return get_user_model().objects.filter(pk__in=ids, is_active=True)


def notify_alert(alert):
    """One ``alert_new`` row per user who can review ``alert``. Never raises: a failure is logged and the alert stays."""
    try:
        with transaction.atomic():
            for user in _candidates(alert.student):
                if reviewable_alerts(user).filter(pk=alert.pk).exists():
                    Notification.objects.get_or_create(user=user, school_id=alert.school_id, kind=Notification.ALERT_NEW, alert=alert)
    except Exception:       # noqa: BLE001 - notifications are secondary to the alert itself
        log.exception('notify_alert failed for alert %s', alert.pk)


def notify_due_plans(school_id, today):
    """``followup_due`` rows for open plans due within ``DUE_SOON_DAYS`` (or overdue), to the plan owner if the owner can see the plan.
    Idempotent per (user, plan, due date). Returns the number created."""
    from interventions.models import InterventionPlan

    created = 0
    plans = InterventionPlan.objects.filter(school_id=school_id, status__in=('planned', 'active'),
                                            due_date__lte=today + timedelta(days=DUE_SOON_DAYS)).select_related('owner')
    for plan in plans:
        owner = plan.owner
        if not owner.is_active or not visible_plans(owner).filter(pk=plan.pk).exists():
            continue
        _row, new = Notification.objects.get_or_create(user=owner, school_id=school_id, kind=Notification.FOLLOWUP_DUE, plan=plan,
                                                       due_on=plan.due_date)
        created += new
    return created


def visible_notifications(user):
    """The user's own rows whose alert / plan is STILL in the user's scope. Anything else is hidden, never shown stale."""
    if not getattr(user, 'is_authenticated', False):
        return Notification.objects.none()
    alerts, plans = reviewable_alerts(user), visible_plans(user)
    own = Notification.objects.filter(user=user)
    return own.filter(alert__in=alerts) | own.filter(plan__in=plans)


def unread_count(user):
    return visible_notifications(user).filter(read_at__isnull=True).count()
