"""Subject Teacher pages (Slice 2): enter grades and recommendations for the students of an own class assignment.

Deny by default: ``role_required(TEACHER)``, an assignment that belongs to the logged-in teacher (anyone else's is a 404),
and writes only for students the teacher may see (``visible_students``) who are currently enrolled in the assigned class,
in the assigned subject.
"""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from schools.models import TeacherAssignment
from schools.vocabulary import SUBJECT_KEYS
from students.access import TEACHER, visible_behavior_notes, visible_grades, visible_recommendations, visible_students
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, Grade, Recommendation

from schools import audit

from .behavior_views import BehaviorNoteForm
from students.scale import school_scale

from .decorators import role_required



def _my_assignments(user):
    """Active assignments of this teacher (an inactive/staff/superuser account has none, like the access layer)."""
    if not user.is_active or user.is_staff or user.is_superuser:
        return TeacherAssignment.objects.none()
    return TeacherAssignment.objects.filter(
        teacher=user, school_class__is_active=True, subject__in=SUBJECT_KEYS).select_related('school_class')


def _assignment(request, pk):
    return get_object_or_404(_my_assignments(request.user), pk=pk)


def _class_students(user, assignment):
    """Students the teacher may see who are currently enrolled in the assigned class."""
    enrolled = Enrollment.objects.filter(
        school_class=assignment.school_class, ended_on__isnull=True, status__in=CURRENT_STATUSES,
        academic_year__is_current=True).values('student_id')
    return visible_students(user).filter(pk__in=enrolled).order_by('last_name', 'first_name')


def _current_enrollment(student):
    return Enrollment.objects.filter(student=student, ended_on__isnull=True, status__in=CURRENT_STATUSES,
                                     academic_year__is_current=True).first()


class GradeSheetForm(forms.Form):
    exam_type = forms.ChoiceField(choices=Grade.EXAM_TYPE_CHOICES, label='نوع آزمون',
                                  widget=forms.Select(attrs={'class': 'form-select'}))
    date = forms.DateField(label='تاریخ آزمون', widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))


VISIBILITY_CHOICES = [('staff', 'فقط کادر مدرسه'), ('student', 'قابل نمایش به دانش‌آموز')]


class RecommendationForm(forms.Form):
    text = forms.CharField(label='توصیه', max_length=2000, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    visibility = forms.ChoiceField(label='چه کسی می‌بیند؟', choices=VISIBILITY_CHOICES, initial='staff',
                                   widget=forms.RadioSelect)


@role_required(TEACHER)
def home(request):
    return render(request, 'dashboard/teacher/home.html', {'assignments': _my_assignments(request.user)})


@role_required(TEACHER)
def grade_sheet(request, pk):
    assignment = _assignment(request, pk)
    students = list(_class_students(request.user, assignment))
    scale = school_scale(assignment.school_class.school_id)
    form = GradeSheetForm(request.POST or None)
    errors = {}
    scores = {}
    if request.method == 'POST':
        for student in students:
            raw = (request.POST.get(f'score_{student.pk}') or '').strip()
            if not raw:
                continue
            try:
                value = float(raw.replace(',', '.'))
                if not 0 <= value <= scale:
                    raise ValueError
            except ValueError:
                errors[student.pk] = f'نمره باید بین ۰ و {scale} باشد.'
                continue
            scores[student.pk] = value
        if form.is_valid() and not errors and scores:
            for student in students:
                if student.pk in scores:
                    grade = Grade.objects.create(
                        student=student, enrollment=_current_enrollment(student), subject=assignment.subject,
                        exam_type=form.cleaned_data['exam_type'], score=scores[student.pk], scale_max=scale, date=form.cleaned_data['date'])
                    audit.record(request.user, audit.GRADE_ADD, grade)
            messages.success(request, f'{len(scores)} نمره ثبت شد.')
            return redirect('dashboard:teacher_grades', pk=assignment.pk)
        if form.is_valid() and not errors and not scores:
            messages.error(request, 'هیچ نمره‌ای وارد نشده است.')
    recent = visible_grades(request.user).filter(
        student__in=[s.pk for s in students], subject=assignment.subject).select_related('student').order_by('-date', '-pk')[:30]
    rows = [{'student': s, 'value': request.POST.get(f'score_{s.pk}', '') if request.method == 'POST' else '',
             'error': errors.get(s.pk, '')} for s in students]
    return render(request, 'dashboard/teacher/grades.html', {
        'scale': scale,
        'assignment': assignment, 'rows': rows, 'form': form, 'recent': recent})


@role_required(TEACHER)
@require_POST
def grade_delete(request, pk, grade_pk):
    """A teacher may remove a grade of the own subject for a student of the own class (typing mistakes)."""
    assignment = _assignment(request, pk)
    students = _class_students(request.user, assignment).values('pk')
    grade = get_object_or_404(visible_grades(request.user), pk=grade_pk, subject=assignment.subject, student__in=students)
    audit.record(request.user, audit.GRADE_DELETE, grade)
    grade.delete()
    messages.success(request, 'نمره حذف شد.')
    return redirect('dashboard:teacher_grades', pk=assignment.pk)


@role_required(TEACHER)
def student_page(request, pk, student_pk):
    assignment = _assignment(request, pk)
    student = get_object_or_404(_class_students(request.user, assignment), pk=student_pk)
    form = RecommendationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        shared = form.cleaned_data['visibility'] == 'student'
        rec = Recommendation.objects.create(student=student, author=request.user, subject=assignment.subject,
                                            text=form.cleaned_data['text'], visible_to_student=shared)
        audit.record(request.user, audit.RECOMMENDATION_ADD, rec, detail='student_visible' if shared else 'staff_only')
        messages.success(request, 'توصیه ثبت شد.')
        return redirect('dashboard:teacher_student', pk=assignment.pk, student_pk=student.pk)
    grades = visible_grades(request.user).filter(student=student, subject=assignment.subject).order_by('-date')
    average = grades.aggregate(models.Avg('score'))['score__avg']
    return render(request, 'dashboard/teacher/student.html', {
        'assignment': assignment, 'student': student, 'form': form, 'grades': grades,
        'average': round(average, 2) if average is not None else None,
        'recommendations': visible_recommendations(request.user).filter(student=student),
        # P5-3: the teacher's own behavior entries for this student, and the form (the view re-checks the scope)
        'behavior_notes': visible_behavior_notes(request.user).filter(student=student)[:30], 'behavior_form': BehaviorNoteForm()})
