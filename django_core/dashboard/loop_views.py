"""Alerts of the intervention loop (change 0022): raise a concern, review it (accept or dismiss with a coded reason).

Base feature, not a sellable module (no ``module=``). Everything goes through ``students.access`` (raisable_students,
visible_alerts, reviewable_alerts); an object outside the scope is a 404, a wrong role a 403. Rules live in ``risk.services``.
"""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from risk.models import Alert, RiskEvent
from risk.services import LoopError, raise_alert_as, reopen_alert, review_alert
from interventions.reeval import recurrence
from students.access import (
    ADMIN, COUNSELOR, GRADE_LEAD, SENSITIVE_ALERT_TYPES, TEACHER, apply_alert_text_policy, raisable_students, reviewable_alerts, roles_for, visible_alerts, visible_plans)

from schools import audit

from .decorators import role_required

ERRORS = {
    'text_required': 'متن الزامی است.', 'bad_choice': 'مقدار انتخاب‌شده معتبر نیست.',
    'reason_required': 'برای ردکردن، دلیل را انتخاب کنید.', 'note_required': 'برای دلیل «سایر» یادداشت لازم است.',
    'already_reviewed': 'این هشدار قبلاً بررسی شده است.', 'not_dismissed': 'این هشدار ردشده نیست.',
    'bad_decision': 'تصمیم نامعتبر است.',
}
STAFF = (ADMIN, GRADE_LEAD, COUNSELOR, TEACHER)
REVIEWERS = (ADMIN, GRADE_LEAD, COUNSELOR)


class AlertForm(forms.Form):
    risk_type = forms.ChoiceField(label='نوع نگرانی', choices=RiskEvent.RiskType.choices,
                                  widget=forms.Select(attrs={'class': 'form-select'}))
    severity = forms.ChoiceField(label='شدت', choices=RiskEvent.Severity.choices,
                                 widget=forms.Select(attrs={'class': 'form-select'}))
    message = forms.CharField(label='توضیح', max_length=300,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))


def _fail(request, error):
    messages.error(request, ERRORS.get(error.code, 'درخواست انجام نشد.'))


@role_required(*STAFF)
def alert_list(request):
    status = request.GET.get('status', Alert.NEW)
    alerts = visible_alerts(request.user).select_related('student', 'risk_event', 'raised_by', 'reviewed_by').prefetch_related('rule_hits__rule')
    if status in dict(Alert.STATUS_CHOICES):
        alerts = alerts.filter(status=status)
    reviewable = set(reviewable_alerts(request.user).values_list('pk', flat=True))
    alerts = apply_alert_text_policy(request.user, alerts[:200])
    audit.record_list(request.user, 'alerts', alerts)
    for alert in alerts:     # every display of a sensitive alert's text is audit-logged (ids and the type only)
        if alert.risk_event.risk_type in SENSITIVE_ALERT_TYPES and not alert.text_hidden:
            audit.record(request.user, audit.ALERT_TEXT_VIEW, alert, detail=alert.risk_event.risk_type)
    recurred = recurrence(alerts, visible_plans(request.user))      # only plans the user may see: nothing leaks to a teacher
    for alert in alerts:
        alert.recurred_plan = recurred[alert.pk].pk if alert.pk in recurred else None
    return render(request, 'dashboard/loop/alerts.html', {
        'alerts': alerts, 'status': status, 'statuses': Alert.STATUS_CHOICES, 'reviewable': reviewable,
        'can_reopen': ADMIN in roles_for(request.user), 'reasons': Alert.DISMISS_REASONS})


@role_required(*STAFF)
def alert_new(request, pk):
    student = get_object_or_404(raisable_students(request.user), pk=pk)
    form = AlertForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            raise_alert_as(request.user, student, **form.cleaned_data)
        except LoopError as error:
            _fail(request, error)
        else:
            messages.success(request, 'نگرانی ثبت شد.')
            return redirect('dashboard:alert_list')
    return render(request, 'dashboard/loop/alert_form.html', {'form': form, 'student': student})


@role_required(*REVIEWERS)
@require_POST
def alert_review(request, pk):
    alert = get_object_or_404(reviewable_alerts(request.user), pk=pk)
    decision = Alert.ACCEPTED if request.POST.get('decision') == 'accept' else Alert.DISMISSED
    try:
        review_alert(request.user, alert, decision, reason=request.POST.get('reason', ''), note=request.POST.get('note', ''))
    except LoopError as error:
        _fail(request, error)
    else:
        messages.success(request, 'بررسی ثبت شد.')
    return redirect('dashboard:alert_list')


@role_required(ADMIN)
@require_POST
def alert_reopen(request, pk):
    alert = get_object_or_404(visible_alerts(request.user), pk=pk)
    try:
        reopen_alert(request.user, alert)
    except LoopError as error:
        _fail(request, error)
    else:
        messages.success(request, 'هشدار دوباره باز شد.')
    return redirect('dashboard:alert_list')
