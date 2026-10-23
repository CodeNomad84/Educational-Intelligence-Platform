"""SchoolAdmin pages: bulk accounts from Excel (dry-run preview, then confirm) and staff roles. Same gate as the other
school pages (``school_page``: role SchoolAdmin + a school from the user's own memberships); everything is written for that
school only. The uploaded rows live in the session until confirmed or cancelled (30 minutes); passwords are never stored."""
import time

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from schools import audit
from schools.models import AcademicYear, GradeLeadAssignment, SchoolStaff
from schools.vocabulary import GRADE_CHOICES
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PLATFORM_ADMIN, TEACHER

from . import bulk_accounts as bulk
from .school_views import _render, school_page

User = get_user_model()
SESSION_KEY = 'bulk_accounts'
SESSION_SECONDS = 30 * 60
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _stored(request, school):
    data = request.session.get(SESSION_KEY)
    if not data or data.get('school') != school.pk or time.time() - data.get('ts', 0) > SESSION_SECONDS:
        request.session.pop(SESSION_KEY, None)
        return None
    return data['rows']


@school_page
def accounts(request, school):
    if request.method == 'POST':
        upload = request.FILES.get('file')
        if upload is None or upload.size > bulk.MAX_FILE_BYTES:
            messages.error(request, 'فایل اکسل (حداکثر ۲ مگابایت) را انتخاب کنید.')
            return redirect('dashboard:school_accounts')
        try:
            parsed = bulk.parse_workbook(upload.read())
        except bulk.BadFile as exc:
            messages.error(request, str(exc))
            return redirect('dashboard:school_accounts')
        request.session[SESSION_KEY] = {'school': school.pk, 'ts': time.time(), 'rows': parsed}
        return redirect('dashboard:school_accounts_preview')
    return _render(request, school, 'accounts.html', max_new=bulk.MAX_NEW_ACCOUNTS)


@school_page
def accounts_template(request, school):
    response = HttpResponse(bulk.template_workbook(), content_type=XLSX)
    response['Content-Disposition'] = 'attachment; filename="accounts-template.xlsx"'
    return response


@school_page
def accounts_preview(request, school):
    parsed = _stored(request, school)
    if parsed is None:
        messages.error(request, 'فایلی برای پیش‌نمایش نیست؛ دوباره بارگذاری کنید.')
        return redirect('dashboard:school_accounts')
    plan = bulk.build_plan(school, parsed)
    return _render(request, school, 'accounts_preview.html', plan=plan, counts=plan.counts,
                   can_confirm=not plan.blocking and plan.new_accounts + plan.counts['exists'] > 0
                   and any(r.ok for r in plan.rows))


@school_page
@require_POST
def accounts_cancel(request, school):
    request.session.pop(SESSION_KEY, None)
    return redirect('dashboard:school_accounts')


@school_page
@require_POST
def accounts_confirm(request, school):
    parsed = _stored(request, school)
    if parsed is None:
        messages.error(request, 'فایلی برای تأیید نیست؛ دوباره بارگذاری کنید.')
        return redirect('dashboard:school_accounts')
    plan = bulk.build_plan(school, parsed)   # re-planned against the database as it is NOW
    try:
        counts, sheet = bulk.apply_plan(school, request.user, plan)
    except bulk.BadFile as exc:
        messages.error(request, str(exc))
        return redirect('dashboard:school_accounts_preview')
    request.session.pop(SESSION_KEY, None)
    audit.record(request.user, audit.BULK_ACCOUNTS, school=school, detail='s{}p{}t{}e{}f{}'.format(
        counts['student_accounts'], counts['parent_accounts'], counts['teacher_accounts'], len(plan.errors),
        counts['failed']))
    summary = ('حساب‌ها ساخته شد: دانش‌آموز {student_accounts}، والد {parent_accounts}، معلم {teacher_accounts}؛ '
               'ردیف خطادار {errors}، ناموفق {failed}.').format(errors=len(plan.errors), **counts)
    if not sheet:
        messages.warning(request, 'حساب جدیدی ساخته نشد. ' + summary)
        return redirect('dashboard:school_accounts')
    messages.success(request, summary + ' برگهٔ ورود دانلود شد؛ رمزها دیگر نمایش داده نمی‌شوند.')
    response = HttpResponse(bulk.login_sheet(sheet), content_type=XLSX)
    response['Content-Disposition'] = 'attachment; filename="login-sheet.xlsx"'
    response['Cache-Control'] = 'no-store'
    return response


# --- staff roles ------------------------------------------------------------------------------------------------------
ROLE_FIELDS = (('teacher', TEACHER, 'T'), ('gradelead', GRADE_LEAD, 'G'), ('counselor', COUNSELOR, 'C'))


def _staff(school):
    """Staff accounts of THIS school that a SchoolAdmin may re-role: never a SchoolAdmin / PlatformAdmin / superuser."""
    return (User.objects.filter(school_staff__school=school, is_active=True, is_superuser=False)
            .exclude(groups__name__in=(ADMIN, PLATFORM_ADMIN)).distinct().order_by('last_name', 'username'))


@school_page
def staff_roles(request, school):
    year = AcademicYear.objects.filter(school=school, is_current=True).first()
    rows = []
    for person in _staff(school):
        held = set(person.groups.values_list('name', flat=True))
        grades = set(GradeLeadAssignment.objects.filter(
            user=person, school=school, academic_year=year.code).values_list('grade', flat=True)) if year else set()
        rows.append({'person': person, 'teacher': TEACHER in held, 'gradelead': GRADE_LEAD in held,
                     'counselor': COUNSELOR in held, 'grades': grades})
    return _render(request, school, 'staff_roles.html', rows=rows, year=year, grade_choices=GRADE_CHOICES)


@school_page
@require_POST
def staff_roles_save(request, school, pk):
    person = get_object_or_404(_staff(school), pk=pk)
    year = AcademicYear.objects.filter(school=school, is_current=True).first()
    wanted = {name for field, name, _c in ROLE_FIELDS if request.POST.get(field)}
    grades = set()
    for value in request.POST.getlist('grades'):
        if value.isdigit() and int(value) in {g for g, _l in GRADE_CHOICES}:
            grades.add(int(value))
    if GRADE_LEAD in wanted and not grades:
        messages.error(request, 'برای نقش مربی پایه، دست‌کم یک پایه انتخاب کنید.')
        return redirect('dashboard:school_staff_roles')
    if GRADE_LEAD in wanted and year is None:
        messages.error(request, 'ابتدا سال تحصیلی جاری را تعریف کنید.')
        return redirect('dashboard:school_staff_roles')
    with transaction.atomic():
        for _field, name, _c in ROLE_FIELDS:   # only these three groups are ever touched
            group = Group.objects.get_or_create(name=name)[0]
            if name in wanted:
                person.groups.add(group)
            else:
                person.groups.remove(group)
        mine = GradeLeadAssignment.objects.filter(user=person, school=school)
        if GRADE_LEAD not in wanted:
            mine.delete()
        else:
            mine.filter(academic_year=year.code).exclude(grade__in=grades).delete()
            for grade in grades:
                GradeLeadAssignment.objects.get_or_create(
                    user=person, school=school, grade=grade, academic_year=year.code, defaults={'created_by': request.user})
    audit.record(request.user, audit.STAFF_ROLES_CHANGE, person, school=school,
                 detail=','.join(code for _f, name, code in ROLE_FIELDS if name in wanted))
    messages.success(request, 'نقش‌ها ذخیره شد.')
    return redirect('dashboard:school_staff_roles')
