"""Intervention services (change 0022): plans, status changes, follow-ups, outcome. Rules live here and in ``students.access``.

Status moves are ONE conditional UPDATE each (the expected current status in the WHERE). Follow-ups are append-only and
only while the plan is active. Audit rows hold ids and codes only, never text.
"""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from risk.models import Alert
from risk.services import LoopError
from schools import audit
from students.access import (ADMIN, may_cancel_or_reassign_plan, may_edit_plan, plan_students, roles_for,
                             valid_plan_owner)

from .models import InterventionFollowUp, InterventionPlan

REEVALUATE_DAYS = 30        # default re-evaluation date after closing (owner, 2026-10-26)
RECURRENCE_DAYS = 90        # window in which a new alert of the same type counts as "recurred after intervention"


def create_plan(user, student, *, intervention_type, goal, action_plan, start_date, due_date, owner=None, alert=None):
    if not plan_students(user).filter(pk=student.pk).exists():
        raise PermissionDenied
    owner = owner or user
    if intervention_type not in dict(InterventionPlan.TYPE_CHOICES):
        raise LoopError('bad_choice')
    goal, action_plan = (goal or '').strip(), (action_plan or '').strip()
    if not goal or not action_plan:
        raise LoopError('text_required')
    if due_date < start_date:
        raise LoopError('bad_dates')
    is_admin = ADMIN in roles_for(user)
    if owner.pk != user.pk and not is_admin:
        raise PermissionDenied
    if intervention_type == InterventionPlan.EMOTIONAL and owner.pk != user.pk:
        raise PermissionDenied          # the admin never writes the text of an emotional plan
    if not valid_plan_owner(owner, student, intervention_type):
        raise LoopError('bad_owner')
    if alert is not None:
        if alert.student_id != student.pk or alert.status != Alert.ACCEPTED:
            raise LoopError('alert_not_accepted')
    plan = InterventionPlan.objects.create(
        school_id=student.school_id, student=student, alert=alert, owner=owner, created_by=user,
        intervention_type=intervention_type, goal=goal[:300], action_plan=action_plan[:1000],
        start_date=start_date, due_date=due_date)
    audit.record(user, audit.INTERVENTION_CREATE, plan, detail=intervention_type)
    return plan


def _move(user, plan, expected, **fields):
    changed = InterventionPlan.objects.filter(pk=plan.pk, status__in=expected).update(**fields)
    if not changed:
        raise LoopError('bad_transition')


def start_plan(user, plan):
    if not may_edit_plan(user, plan):
        raise PermissionDenied
    _move(user, plan, [InterventionPlan.PLANNED], status=InterventionPlan.ACTIVE)
    audit.record(user, audit.INTERVENTION_STATUS, plan, detail=InterventionPlan.ACTIVE)


def complete_plan(user, plan, outcome, note='', reevaluate_on=None):
    if not may_edit_plan(user, plan):
        raise PermissionDenied
    if outcome not in dict(InterventionPlan.OUTCOME_CHOICES):
        raise LoopError('outcome_required')
    now = timezone.now()
    _move(user, plan, [InterventionPlan.ACTIVE], status=InterventionPlan.COMPLETED, outcome=outcome,
          outcome_note=(note or '').strip()[:500], closed_at=now,
          reevaluate_on=reevaluate_on or (now.date() + timedelta(days=REEVALUATE_DAYS)))
    audit.record(user, audit.INTERVENTION_STATUS, plan, detail=InterventionPlan.COMPLETED)
    audit.record(user, audit.INTERVENTION_OUTCOME, plan, detail=outcome)


def cancel_plan(user, plan):
    if not may_cancel_or_reassign_plan(user, plan):
        raise PermissionDenied
    _move(user, plan, [InterventionPlan.PLANNED, InterventionPlan.ACTIVE], status=InterventionPlan.CANCELLED,
          closed_at=timezone.now())
    audit.record(user, audit.INTERVENTION_STATUS, plan, detail=InterventionPlan.CANCELLED)


def reassign_plan(user, plan, new_owner):
    """SchoolAdmin (or the owner) hands the plan to another valid owner; an emotional plan only to a Counselor/Grade Lead who sees the student."""
    if not may_cancel_or_reassign_plan(user, plan):
        raise PermissionDenied
    if ADMIN not in roles_for(user) and plan.owner_id != user.pk:
        raise PermissionDenied
    if not valid_plan_owner(new_owner, plan.student, plan.intervention_type):
        raise LoopError('bad_owner')
    _move(user, plan, [InterventionPlan.PLANNED, InterventionPlan.ACTIVE], owner=new_owner)
    audit.record(user, audit.INTERVENTION_OWNER, plan)


def add_followup(user, plan, followup_date, note, assessment):
    if not may_edit_plan(user, plan):
        raise PermissionDenied
    note = (note or '').strip()
    if not note:
        raise LoopError('text_required')
    if assessment not in dict(InterventionFollowUp.ASSESSMENT_CHOICES):
        raise LoopError('bad_choice')
    if followup_date > timezone.localdate():
        raise LoopError('bad_dates')
    with transaction.atomic():
        # Lock the row and re-check the status: a follow-up can only be added while the plan is active.
        locked = InterventionPlan.objects.select_for_update().get(pk=plan.pk)
        if locked.status != InterventionPlan.ACTIVE:
            raise LoopError('bad_transition')
        followup = InterventionFollowUp.objects.create(plan=locked, author=user, followup_date=followup_date,
                                                       progress_note=note[:1000], assessment=assessment)
    audit.record(user, audit.FOLLOWUP_ADD, plan, detail=assessment)
    return followup
