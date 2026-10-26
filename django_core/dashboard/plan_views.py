"""Intervention plans of the loop (change 0022): create (from an accepted alert or directly), start, follow-up, complete with an
outcome, cancel, reassign. Base feature (no ``module=``). Reads go through ``students.access``: the plan list and the plan page
show METADATA to every reviewer; the text of an ``emotional`` plan and its follow-ups only to its owner and a Counselor with an
open referral (``may_read_plan_text``), and every plan page view is audit-logged (``intervention_view``, text|meta). Rules in
``interventions.services``."""
from datetime import date

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from interventions.models import InterventionFollowUp, InterventionPlan
from interventions.reeval import due_for_reevaluation
from interventions.services import (add_followup, cancel_plan, complete_plan, create_plan, reassign_plan, start_plan)
from risk.services import LoopError
from schools import audit
from students.access import (
    ADMIN, COUNSELOR, GRADE_LEAD, SENSITIVE_ALERT_TYPES, apply_alert_text_policy, may_cancel_or_reassign_plan, may_edit_plan, may_read_plan_text, plan_students,
    reviewable_alerts, roles_for, valid_plan_owner, visible_alerts, visible_followups, visible_plans)

from .decorators import role_required
from .loop_views import ERRORS
from .school_forms import staff_queryset

REVIEWERS = (ADMIN, GRADE_LEAD, COUNSELOR)
ERRORS = {**ERRORS, 'bad_owner': 'مسئول انتخاب‌شده مجاز نیست.', 'bad_dates': 'تاریخ‌ها معتبر نیستند.',
          'alert_not_accepted': 'هشدار باید پذیرفته‌شده و مربوط به همین دانش‌آموز باشد.',
          'bad_transition': 'این تغییر وضعیت مجاز نیست.', 'outcome_required': 'نتیجه را انتخاب کنید.'}
DATE = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d')


def _owner_candidates(school, student, kind):
    """Users who may own a plan of this kind for the student (the form shows only these; the service re-checks)."""
    users = {u.pk: u for role in (GRADE_LEAD, COUNSELOR, ADMIN) for u in staff_queryset(school, role)}
    return [u for u in users.values() if u.is_active and valid_plan_owner(u, student, kind)]


class PlanForm(forms.Form):
    intervention_type = forms.ChoiceField(label='نوع مداخله', choices=InterventionPlan.TYPE_CHOICES,
                                          widget=forms.Select(attrs={'class': 'form-select'}))
    goal = forms.CharField(label='هدف', max_length=300, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))
    action_plan = forms.CharField(label='برنامه اقدام', max_length=1000,
                                  widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}))
    start_date = forms.DateField(label='شروع', widget=DATE, initial=date.today)
    due_date = forms.DateField(label='سررسید', widget=DATE)
    owner = forms.IntegerField(label='مسئول', required=False, widget=forms.Select(attrs={'class': 'form-select'}))


class FollowUpForm(forms.Form):
    followup_date = forms.DateField(label='تاریخ', widget=DATE, initial=date.today)
    assessment = forms.ChoiceField(label='ارزیابی', choices=InterventionFollowUp.ASSESSMENT_CHOICES,
                                   widget=forms.Select(attrs={'class': 'form-select'}))
    progress_note = forms.CharField(label='یادداشت پیشرفت', max_length=1000,
                                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))


def _fail(request, error):
    messages.error(request, ERRORS.get(error.code, 'درخواست انجام نشد.'))


@role_required(*REVIEWERS)
def plan_list(request):
    plans = visible_plans(request.user).select_related('student', 'owner')
    status = request.GET.get('status', 'open')
    if status == 'open':
        plans = plans.filter(status__in=[InterventionPlan.PLANNED, InterventionPlan.ACTIVE])
    elif status in dict(InterventionPlan.STATUS_CHOICES):
        plans = plans.filter(status=status)
    due = due_for_reevaluation(visible_plans(request.user), visible_alerts(request.user), date.today())
    return render(request, 'dashboard/loop/plans.html', {
        'due': due, 'plans': plans[:200], 'status': status, 'statuses': [('open', 'باز')] + InterventionPlan.STATUS_CHOICES})


@role_required(*REVIEWERS)
def plan_new(request, pk):
    student = get_object_or_404(plan_students(request.user).select_related('school'), pk=pk)
    alert = None
    raw = request.GET.get('alert') or request.POST.get('alert')
    if raw:
        if not raw.isdigit():
            raise Http404
        alert = get_object_or_404(reviewable_alerts(request.user).filter(student=student), pk=int(raw))
        alert = apply_alert_text_policy(request.user, [alert])[0]
        if alert.risk_event.risk_type in SENSITIVE_ALERT_TYPES and not alert.text_hidden:
            audit.record(request.user, audit.ALERT_TEXT_VIEW, alert, detail=alert.risk_event.risk_type)
    is_admin = ADMIN in roles_for(request.user)
    form = PlanForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        owner = None
        if is_admin and data['owner']:
            owner = next((u for u in _owner_candidates(student.school, student, data['intervention_type'])
                          if u.pk == data['owner']), None)
            if owner is None:
                messages.error(request, ERRORS['bad_owner'])
        if not (is_admin and data['owner'] and owner is None):
            try:
                plan = create_plan(request.user, student, intervention_type=data['intervention_type'], goal=data['goal'],
                                   action_plan=data['action_plan'], start_date=data['start_date'], due_date=data['due_date'],
                                   owner=owner, alert=alert)
            except LoopError as error:
                _fail(request, error)
            else:
                messages.success(request, 'برنامهٔ مداخله ثبت شد.')
                return redirect('dashboard:plan_detail', pk=plan.pk)
    return render(request, 'dashboard/loop/plan_form.html', {
        'form': form, 'student': student, 'alert': alert, 'is_admin': is_admin,
        'owners': _owner_candidates(student.school, student, 'academic') if is_admin else []})


@role_required(*REVIEWERS)
def plan_detail(request, pk):
    plan = get_object_or_404(visible_plans(request.user).select_related('student', 'owner', 'alert'), pk=pk)
    text = may_read_plan_text(request.user, plan)
    audit.record(request.user, audit.INTERVENTION_VIEW, plan, detail='text' if text else 'meta')
    followups = plan.followups.all()
    context = {
        'plan': plan, 'text': text, 'student': plan.student,
        'followups': visible_followups(request.user).filter(plan=plan) if text else [],
        'followup_count': followups.count(), 'last_followup': followups.first(),
        'can_edit': may_edit_plan(request.user, plan), 'can_manage': may_cancel_or_reassign_plan(request.user, plan),
        'followup_form': FollowUpForm(), 'outcomes': InterventionPlan.OUTCOME_CHOICES,
        'owners': [u for u in _owner_candidates(plan.school, plan.student, plan.intervention_type) if u.pk != plan.owner_id],
    }
    return render(request, 'dashboard/loop/plan_detail.html', context)


def _plan_for_action(request, pk):
    return get_object_or_404(visible_plans(request.user), pk=pk)


def _act(request, pk, fn, ok, *args, **kwargs):
    plan = _plan_for_action(request, pk)
    try:
        fn(request.user, plan, *args, **kwargs)
    except LoopError as error:
        _fail(request, error)
    else:
        messages.success(request, ok)
    return redirect('dashboard:plan_detail', pk=plan.pk)


@role_required(*REVIEWERS)
@require_POST
def plan_start(request, pk):
    return _act(request, pk, start_plan, 'برنامه فعال شد.')


@role_required(*REVIEWERS)
@require_POST
def plan_cancel(request, pk):
    return _act(request, pk, cancel_plan, 'برنامه لغو شد.')


@role_required(*REVIEWERS)
@require_POST
def plan_complete(request, pk):
    return _act(request, pk, complete_plan, 'برنامه بسته شد.', request.POST.get('outcome', ''), request.POST.get('note', ''))


@role_required(*REVIEWERS)
@require_POST
def plan_reassign(request, pk):
    plan = _plan_for_action(request, pk)
    new_owner = next((u for u in _owner_candidates(plan.school, plan.student, plan.intervention_type)
                      if str(u.pk) == request.POST.get('owner')), None)
    if new_owner is None:
        messages.error(request, ERRORS['bad_owner'])
        return redirect('dashboard:plan_detail', pk=plan.pk)
    return _act(request, pk, reassign_plan, 'مسئول تغییر کرد.', new_owner)


@role_required(*REVIEWERS)
@require_POST
def plan_followup(request, pk):
    form = FollowUpForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'پیگیری ثبت نشد: اطلاعات ناقص یا نامعتبر است.')
        return redirect('dashboard:plan_detail', pk=_plan_for_action(request, pk).pk)
    data = form.cleaned_data
    return _act(request, pk, add_followup, 'پیگیری ثبت شد.', data['followup_date'], data['progress_note'], data['assessment'])
