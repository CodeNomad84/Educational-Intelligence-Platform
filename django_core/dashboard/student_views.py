"""Student pages (Slice 4b): a student sees ONLY their own grades and the teachers' feedback about them, and a study-assistant
page that is a DEMO STUB (see ``students.study_assistant``: rule-based, in memory, no external service). The SchoolAdmin
creates the student's account from the Student 360 page. Deny by default through ``students.access``."""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from schools import audit
from schools import ai_guard
from students import study_assistant
from students.access import ADMIN, STUDENT, visible_grades, visible_recommendations, visible_students

from .decorators import role_required
from .student360 import grades_by_year

User = get_user_model()


def _me(request):
    student = visible_students(request.user).first()
    if student is None:
        raise Http404
    return student


@role_required(STUDENT)
def home(request):
    student = _me(request)
    return render(request, 'dashboard/me/home.html', {
        'student': student,
        'grade_years': grades_by_year(visible_grades(request.user).filter(student=student)),
        'recommendations': visible_recommendations(request.user).filter(student=student).select_related('author'),
    })


class QuestionForm(forms.Form):
    question = forms.CharField(label='سؤال یا درسی که دربارهٔ آن می‌پرسید', max_length=study_assistant.MAX_QUESTION, required=False,
                               widget=forms.TextInput(attrs={'class': 'form-control'}))


@role_required(STUDENT, module='tutor_ai')
def assistant(request):
    student = _me(request)
    form = QuestionForm(request.POST or None)
    reply = None
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            ai_guard.consume(student.school_id, 'tutor_ai')   # per-school cap, checked before any answer/LLM call
        except ai_guard.AICapReached as cap:
            messages.error(request, cap.message_fa)
            status = 429
        else:
            summary = study_assistant.subject_summary(visible_grades(request.user).filter(student=student))
            reply = study_assistant.answer(form.cleaned_data['question'], summary)   # in memory only: nothing stored or sent
    return render(request, 'dashboard/me/assistant.html', {
        'form': form, 'reply': reply, 'notice': study_assistant.STUB_NOTICE}, status=status)


class StudentAccountForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)

    def __init__(self, *args, student, created_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if len(password or '') < 8:
            raise forms.ValidationError('رمز عبور باید دست‌کم ۸ نویسه باشد.')
        return password

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.first_name, user.last_name = self.student.first_name, self.student.last_name
            user.is_staff = user.is_superuser = False
            user.save()
            user.groups.add(Group.objects.get_or_create(name=STUDENT)[0])
            type(self.student).objects.filter(pk=self.student.pk).update(student_user=user)
        return user


@role_required(ADMIN)
@require_POST
def create_account(request, pk):
    student = get_object_or_404(visible_students(request.user).filter(full_tier=True), pk=pk)
    if student.student_user_id:
        messages.error(request, 'این دانش‌آموز قبلاً حساب دارد.')
        return redirect('dashboard:student_360', pk=student.pk)
    form = StudentAccountForm(request.POST, student=student)
    if form.is_valid():
        user = form.save()
        audit.record(request.user, audit.STUDENT_ACCOUNT_CREATE, student)
        messages.success(request, f'حساب دانش‌آموز ساخته شد: {user.username}')
    else:
        messages.error(request, 'حساب ساخته نشد: ' + ' '.join(e for errs in form.errors.values() for e in errs))
    return redirect('dashboard:student_360', pk=student.pk)
