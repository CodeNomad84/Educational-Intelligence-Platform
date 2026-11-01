"""Counselor pages and referrals (Slice 4a). A counselor sees ONLY students with an open referral to them (list + a read-only
case page with the 360 summary and the referral reason) and writes counselor notes that only the counselor and the
SchoolAdmin can read. SchoolAdmin and Grade Lead (own grade) refer a student from the Student 360 page.
Deny by default: everything goes through ``students.access`` (visible_students / visible_referrals / visible_counselor_notes)."""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from students.access import (
    ADMIN, COUNSELOR, GRADE_LEAD, visible_counselor_notes, visible_referrals, visible_students)
from students.models import CounselorNote, Referral

from schools import audit

from .decorators import role_required
from .school_forms import staff_queryset
from .student360 import summary_context


class ReferralForm(forms.Form):
    counselor = forms.ModelChoiceField(queryset=None, label='مشاور', widget=forms.Select(attrs={'class': 'form-select'}))
    reason = forms.CharField(label='دلیل ارجاع', max_length=500,
                             widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

    def __init__(self, *args, student, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        # only active counselors of the student's own school
        self.fields['counselor'].queryset = staff_queryset(student.school, COUNSELOR).filter(is_active=True)

    def clean_counselor(self):
        counselor = self.cleaned_data['counselor']
        if Referral.objects.filter(student=self.student, counselor=counselor, status='open').exists():
            raise forms.ValidationError('برای این مشاور ارجاع باز وجود دارد.')
        return counselor


class NoteForm(forms.Form):
    text = forms.CharField(label='یادداشت', max_length=2000,
                           widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))


@role_required(ADMIN, GRADE_LEAD)
@require_POST
def student_refer(request, pk):
    student = get_object_or_404(visible_students(request.user).filter(full_tier=True).select_related('school'), pk=pk)
    form = ReferralForm(request.POST, student=student)
    if form.is_valid():
        referral = Referral.objects.create(student=student, school=student.school, counselor=form.cleaned_data['counselor'],
                                           referred_by=request.user, reason=form.cleaned_data['reason'])
        audit.record(request.user, audit.REFERRAL_CREATE, referral)
        messages.success(request, 'دانش‌آموز به مشاور ارجاع شد.')
    else:
        messages.error(request, 'ارجاع ثبت نشد: ' + ' '.join(e for errs in form.errors.values() for e in errs))
    return redirect('dashboard:student_360', pk=student.pk)


@role_required(COUNSELOR)
def home(request):
    referrals = visible_referrals(request.user).filter(counselor=request.user).select_related('student')
    audit.record_list(request.user, 'referrals', referrals)
    return render(request, 'dashboard/counselor/home.html', {'referrals': referrals})


def _case(request, pk):
    referral = get_object_or_404(visible_referrals(request.user).filter(counselor=request.user), pk=pk)
    student = get_object_or_404(visible_students(request.user), pk=referral.student_id)
    return referral, student


@role_required(COUNSELOR)
def case(request, pk):
    referral, student = _case(request, pk)
    form = NoteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        note = CounselorNote.objects.create(referral=referral, author=request.user, text=form.cleaned_data['text'])
        audit.record(request.user, audit.NOTE_ADD, note)
        messages.success(request, 'یادداشت ثبت شد.')
        return redirect('dashboard:counselor_case', pk=referral.pk)
    audit.record(request.user, audit.VIEW_CASE, referral)
    audit.record(request.user, audit.SHOW_PARENT_PHONES, student)    # the case page displays the parents' phone numbers
    context = summary_context(request, student)
    notes = list(visible_counselor_notes(request.user).filter(referral=referral).select_related('author'))
    if notes:       # note text is rendered on this page: counts only in the audit event
        audit.record(request.user, audit.COUNSELOR_NOTE_VIEW, referral, detail=f'n{len(notes)}')
    context.update(referral=referral, form=form, notes=notes)
    return render(request, 'dashboard/counselor/case.html', context)


@role_required(COUNSELOR)
@require_POST
def case_close(request, pk):
    referral, _student = _case(request, pk)
    referral.status = 'closed'
    referral.closed_at = timezone.now()
    referral.save(update_fields=['status', 'closed_at'])
    audit.record(request.user, audit.REFERRAL_CLOSE, referral)
    messages.success(request, 'پرونده بسته شد؛ دسترسی مشاور به این دانش‌آموز پایان یافت.')
    return redirect('dashboard:counselor_home')
