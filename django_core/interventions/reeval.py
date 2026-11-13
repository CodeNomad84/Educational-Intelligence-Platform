"""Re-evaluation hook (change 0022): everything here is derived on read from the caller's already-scoped querysets; nothing is
stored and no label is attached to a student. A completed plan is "due" when its re-evaluation date has passed and nothing
happened for the student since it closed (no later plan, no later alert). A new alert counts as "recurred after intervention"
when a completed plan of the same kind closed in the ``RECURRENCE_DAYS`` before it."""
from datetime import timedelta

from .models import InterventionPlan
from .services import RECURRENCE_DAYS

# A plan's kind corresponds to the alert risk type of the same name.
KIND_TO_RISK = {InterventionPlan.ACADEMIC: 'academic', InterventionPlan.BEHAVIORAL: 'behavioral',
                InterventionPlan.EMOTIONAL: 'emotional', InterventionPlan.SOCIAL: 'social'}


def due_for_reevaluation(plans, alerts, today):
    """Completed plans (from ``visible_plans``) whose date passed and with no later plan or alert for the student."""
    due = []
    for plan in plans.filter(status=InterventionPlan.COMPLETED, reevaluate_on__lte=today).select_related('student', 'owner'):
        later_plan = plans.filter(student_id=plan.student_id, created_at__gt=plan.closed_at).exclude(pk=plan.pk).exists()
        later_alert = alerts.filter(student_id=plan.student_id, created_at__gt=plan.closed_at).exists()
        if not later_plan and not later_alert:
            due.append(plan)
    return due


def recurrence(alerts, plans):
    """{alert id: plan} for alerts that recurred within the window after a completed plan of the same kind."""
    alerts = list(alerts)
    closed = list(plans.filter(status=InterventionPlan.COMPLETED, closed_at__isnull=False,
                               student_id__in={a.student_id for a in alerts}))
    found = {}
    for alert in alerts:
        for plan in closed:
            if (plan.student_id == alert.student_id and KIND_TO_RISK.get(plan.intervention_type) == alert.risk_event.risk_type
                    and plan.closed_at < alert.created_at <= plan.closed_at + timedelta(days=RECURRENCE_DAYS)):
                found[alert.pk] = plan
                break
    return found
