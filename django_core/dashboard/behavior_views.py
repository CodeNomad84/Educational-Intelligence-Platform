"""Behavior log entries (decision pack 0028 P5-3): staff record a short positive or concern entry. Base feature (no module).
Who may record: SchoolAdmin, Grade Lead (their students) and a Subject Teacher (students of their classes): the student is looked
up inside ``behavior_writable_students``, so anyone else gets a 404. Who reads what: ``students.access.visible_behavior_notes``."""
from datetime import date

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from schools import audit
from students.access import ADMIN, GRADE_LEAD, TEACHER, behavior_writable_students, roles_for
from students.models import BehaviorNote

from .decorators import role_required


class BehaviorNoteForm(forms.ModelForm):
    class Meta:
        model = BehaviorNote
        fields = ['kind', 'category', 'note', 'occurred_on']
        widgets = {'kind': forms.Select(attrs={'class': 'form-select'}), 'category': forms.Select(attrs={'class': 'form-select'}),
                   'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'maxlength': 300}),
                   'occurred_on': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['occurred_on'].initial = date.today

    def clean_occurred_on(self):
        day = self.cleaned_data['occurred_on']
        if day > date.today():
            raise forms.ValidationError('تاریخ نمی‌تواند در آینده باشد.')
        return day


@require_POST
@role_required(ADMIN, GRADE_LEAD, TEACHER)
def behavior_new(request, pk):
    student = get_object_or_404(behavior_writable_students(request.user), pk=pk)
    form = BehaviorNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.student, note.recorded_by = student, request.user
        note.save()
        audit.record(request.user, audit.BEHAVIOR_NOTE_CREATE, note, school=student.school_id, detail=note.kind)
        messages.success(request, 'یادداشت رفتاری ثبت شد.')
    else:
        messages.error(request, 'یادداشت ثبت نشد: ' + ' '.join(e for errs in form.errors.values() for e in errs))
    if roles_for(request.user) & {ADMIN, GRADE_LEAD}:
        return redirect('dashboard:student_360', pk=student.pk)
    return redirect(request.POST.get('back') if request.POST.get('back', '').startswith('/teacher/') else 'dashboard:teacher_home')
