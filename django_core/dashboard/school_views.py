"""SchoolAdmin pages (Slice 1): academic year, classes, teachers and grade leads of ONE school, in the dashboard (no Django
admin). Deny by default: ``role_required(ADMIN)`` plus a school taken from the user's own memberships
(``allowed_school_ids``); every object is looked up inside that school, so another school's id is a 404."""
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, TeacherAssignment
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, TEACHER, visible_students
from students.student_school import allowed_school_ids

from .decorators import role_required
from .school_forms import (
    AcademicYearForm, GradeLeadAssignmentForm, SchoolClassForm, StaffAccountForm, TeacherAssignmentForm,
    staff_queryset, suggested_year)

KINDS = {'teachers': (TEACHER, 'معلم‌ها', 'معلم'), 'gradeleads': (GRADE_LEAD, 'مربیان پایه', 'مربی پایه'),
         'counselors': (COUNSELOR, 'مشاوران', 'مشاور')}


def _current_school(request):
    ids = allowed_school_ids(request.user)
    if not ids:
        raise PermissionDenied
    try:
        wanted = int(request.GET.get('school') or request.session.get('school_id') or 0)
    except (TypeError, ValueError):
        wanted = 0
    chosen = wanted if wanted in ids else min(ids)
    request.session['school_id'] = chosen
    return School.objects.get(pk=chosen)


def school_page(view):
    @role_required(ADMIN)
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        school = _current_school(request)
        return view(request, school, *args, **kwargs)
    return wrapped


def _render(request, school, template, **context):
    schools = School.objects.filter(pk__in=allowed_school_ids(request.user)).order_by('name')
    return render(request, f'dashboard/school/{template}', {'school': school, 'my_schools': schools, **context})


def _kind(kind):
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


@school_page
def home(request, school):
    year = AcademicYear.objects.filter(school=school, is_current=True).first()
    counts = {
        'classes': SchoolClass.objects.filter(school=school).count(),
        'students': visible_students(request.user).filter(school=school).count(),
        'teachers': staff_queryset(school, TEACHER).count(),
        'gradeleads': staff_queryset(school, GRADE_LEAD).count(),
        'counselors': staff_queryset(school, COUNSELOR).count(),
    }
    return _render(request, school, 'home.html', year=year, counts=counts)


# --- academic years ---------------------------------------------------------------------------------------------
@school_page
def years(request, school):
    if request.method == 'POST':
        form = AcademicYearForm(request.POST, school=school)
        if form.is_valid():
            year = form.save(commit=False)
            year.school = school
            year.is_current = not AcademicYear.objects.filter(school=school, is_current=True).exists()
            year.save()
            messages.success(request, 'سال تحصیلی ثبت شد.' + (' (به‌عنوان سال جاری)' if year.is_current else ''))
            return redirect('dashboard:school_years')
    else:
        form = AcademicYearForm(school=school, initial=suggested_year(school))
    return _render(request, school, 'years.html', form=form,
                   years=AcademicYear.objects.filter(school=school).order_by('-start_date'))


@school_page
@require_POST
def year_set_current(request, school, pk):
    year = get_object_or_404(AcademicYear, pk=pk, school=school)
    with transaction.atomic():
        AcademicYear.objects.filter(school=school, is_current=True).exclude(pk=year.pk).update(is_current=False)
        AcademicYear.objects.filter(pk=year.pk).update(is_current=True)
    messages.success(request, f'سال جاری: {year.code}. ثبت‌نام‌های سال جدید با ابزار «backfill_enrollments» یا هنگام ثبت دانش‌آموز ساخته می‌شوند.')
    return redirect('dashboard:school_years')


# --- classes ------------------------------------------------------------------------------------------------------
@school_page
def classes(request, school):
    rows = SchoolClass.objects.filter(school=school).order_by('-academic_year', 'grade', 'title')
    return _render(request, school, 'classes.html', classes=rows)


@school_page
def class_edit(request, school, pk=None):
    instance = get_object_or_404(SchoolClass, pk=pk, school=school) if pk else None
    form = SchoolClassForm(request.POST or None, instance=instance, school=school)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.school = school
        saved.save()
        messages.success(request, 'کلاس ذخیره شد.')
        return redirect('dashboard:school_classes')
    return _render(request, school, 'form.html', form=form, heading='ویرایش کلاس' if instance else 'کلاس جدید',
                   back='dashboard:school_classes')


# --- teachers and grade leads --------------------------------------------------------------------------------------
@school_page
def staff_list(request, school, kind):
    group, title, noun = _kind(kind)
    form = StaffAccountForm(request.POST or None, school=school, group_name=group, created_by=request.user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'حساب {noun} ساخته شد: {user.username}')
        return redirect('dashboard:school_staff_detail', kind=kind, pk=user.pk)
    return _render(request, school, 'staff_list.html', kind=kind, title=title, noun=noun, form=form,
                   people=staff_queryset(school, group))


@school_page
def staff_detail(request, school, kind, pk):
    group, title, noun = _kind(kind)
    person = get_object_or_404(staff_queryset(school, group), pk=pk)
    if kind == 'counselors':   # a counselor has no assignments: access comes from referrals
        return _render(request, school, 'staff_detail.html', kind=kind, title=title, noun=noun, person=person, form=None,
                       assignments=[])
    if kind == 'teachers':
        form = TeacherAssignmentForm(request.POST or None, school=school, teacher=person, created_by=request.user)
        rows = TeacherAssignment.objects.filter(teacher=person, school_class__school=school).select_related('school_class')
    else:
        form = GradeLeadAssignmentForm(request.POST or None, school=school, lead=person, created_by=request.user)
        rows = GradeLeadAssignment.objects.filter(user=person, school=school)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'تخصیص ثبت شد.')
        return redirect('dashboard:school_staff_detail', kind=kind, pk=person.pk)
    return _render(request, school, 'staff_detail.html', kind=kind, title=title, noun=noun, person=person, form=form,
                   assignments=rows)


@school_page
@require_POST
def assignment_delete(request, school, kind, pk, assignment_pk):
    group, _title, _noun = _kind(kind)
    person = get_object_or_404(staff_queryset(school, group), pk=pk)
    if kind == 'counselors':
        raise Http404
    if kind == 'teachers':
        get_object_or_404(TeacherAssignment, pk=assignment_pk, teacher=person, school_class__school=school).delete()
    else:
        get_object_or_404(GradeLeadAssignment, pk=assignment_pk, user=person, school=school).delete()
    messages.success(request, 'تخصیص حذف شد.')
    return redirect('dashboard:school_staff_detail', kind=kind, pk=person.pk)


@school_page
@require_POST
def staff_toggle_active(request, school, kind, pk):
    group, _title, noun = _kind(kind)
    person = get_object_or_404(staff_queryset(school, group), pk=pk)
    person.is_active = not person.is_active
    person.save(update_fields=['is_active'])
    messages.success(request, f'حساب {noun} {"فعال" if person.is_active else "غیرفعال"} شد.')
    return redirect('dashboard:school_staff_detail', kind=kind, pk=person.pk)
