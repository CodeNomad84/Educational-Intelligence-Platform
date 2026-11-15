# Create your views here.
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.db.models import Avg 
from django.db import models
from students.models import Student, Grade, Attendance
import requests
from django.core.exceptions import ImproperlyConfigured, PermissionDenied

from config.service_auth import service_headers
from students.access import (
    ADMIN, COUNSELOR, GRADE_LEAD, STUDENT, TEACHER, PARENT, roles_for, search_students, visible_attendances, visible_grades,
    visible_recommendations, visible_students,
)
from schools import audit

from . import throttle
from .decorators import role_required
from .home import home_url_for, safe_next
from students.enrollment_sync import ensure_current_enrollment

# M-3 (T7): the AI service's error text (response body or exception) is never shown to a user - it can carry DB hosts,
# model paths or provider messages. The user gets these fixed sentences; the detail goes to the server log.
AI_SERVICE_ERROR = 'خطا در سرویس هوش مصنوعی (کد {status}).'
AI_UNREACHABLE = 'خطا در ارتباط با سرویس هوش مصنوعی.'

logger = logging.getLogger(__name__)

# صفحه‌ی ورود
def login_view(request):
    status = 200
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        locked = throttle.is_locked(request, username)   # refused before the password is looked at; same answer for any name
        user = None if locked else authenticate(request, username=username, password=password)
        if locked:
            status = 429
            messages.error(request, throttle.LOCKED_MESSAGE)
        elif user is not None:
            throttle.record_success(username)
            login(request, user)
            return redirect(safe_next(request) or home_url_for(user))
        else:
            throttle.record_failure(request, username)
            messages.error(request, 'نام کاربری یا رمز عبور اشتباه است.')
    # DEMO SCOPE begin — standalone demo login (vendored assets, DEMO banner); original template kept for non-demo runs
    from django.conf import settings as _demo_settings
    if getattr(_demo_settings, 'DEMO_MODE', False):
        return render(request, 'demo_intel/login.html', status=status)
    # DEMO SCOPE end
    return render(request, 'dashboard/login.html', status=status)

# خروج از حساب
def logout_view(request):
    logout(request)
    return redirect('dashboard:login')

# داشبورد اصلی (فقط کاربران لاگین‌شده)
@login_required
def dashboard_view(request):
    roles = roles_for(request.user)
    if request.user.is_superuser and request.user.is_active:
        return redirect('/admin/')   # Slice 0: the superuser is the platform account; it has no school data here
    if ADMIN not in roles:  # school-wide aggregates: SchoolAdmin only
        if roles & {PARENT, GRADE_LEAD, TEACHER, COUNSELOR, STUDENT}:
            # Aggregates are SchoolAdmin only; every other role lands on its own home.
            return redirect(home_url_for(request.user))
        raise PermissionDenied
    # P5-1 principal dashboard: one school chosen among the user's memberships, every number from the user's own visible_*
    # scopes (dashboard/principal.py). The demo engine's school view moved to /demo/school/ (DEMO SCOPE).
    from .principal import principal_dashboard
    return principal_dashboard(request)

# لیست دانش‌آموزان
@role_required(ADMIN, GRADE_LEAD, TEACHER, PARENT)
def student_list_view(request):
    students = search_students(visible_students(request.user), request.GET.get('search'))
    grade = request.GET.get('grade', '')
    if grade.isdigit():   # a Grade Lead lands on the list of the own grade (?grade=N); the scope itself is unchanged
        students = students.filter(grade=int(grade))
    audit.record_list(request.user, 'students', students)
    roles = roles_for(request.user)
    # P5-2: support levels only for the review scope (SchoolAdmin, Grade Lead); a Teacher or Parent gets none
    levels = {}
    if roles & {ADMIN, GRADE_LEAD}:
        from interventions.support import levels_for_user
        levels = levels_for_user(request.user)
    rows = list(students)
    for student in rows:
        student.support = levels.get(student.pk)
    return render(request, 'dashboard/student_list.html', {'students': rows, 'show_support': bool(roles & {ADMIN, GRADE_LEAD}),
                                                            'search': request.GET.get('search', '')})

# جزئیات یک دانش‌آموز + نمایش آزمایشی وضعیت (خروجی مدل، برچسب «نمایشی» — تغییر ۰۰۴۴)
# dashboard/views.py (قسمت student_detail_view)

@role_required(ADMIN, GRADE_LEAD, TEACHER, PARENT)
def student_detail_view(request, pk):
    # Object-level access: the lookup is scoped to the students this user may see,
    # so another family's child is a 404 (not a 403, to avoid confirming it exists).
    student = get_object_or_404(visible_students(request.user), pk=pk)
    audit.record(request.user, audit.VIEW_DETAIL, student)
    # DEMO SCOPE begin — demo intelligence profile for staff (parents keep the original page)
    from django.conf import settings as _demo_settings
    if getattr(_demo_settings, 'DEMO_MODE', False) and ADMIN in roles_for(request.user):
        from demo_intel.views import student_profile
        return student_profile(request, student)
    # DEMO SCOPE end
    # Only rows the user's grants cover: own-subject grades for a Subject Teacher, no attendance for them.
    grades = visible_grades(request.user).filter(student=student)
    attendances = visible_attendances(request.user).filter(student=student)
    
    # ---------- محاسبه‌ی ویژگی‌های مورد نیاز ----------
    # 1. میانگین نمرات
    avg_score = grades.aggregate(models.Avg('score'))['score__avg'] or 0
    avg_score = round(avg_score, 2)
    
    # 2. تعداد غیبت‌ها و تاخیرها
    total_absences = attendances.filter(status='absent').count()
    total_lates = attendances.filter(status='late').count()
    total_days = attendances.count()
    
    # 3. نرخ حضور (درصد)
    attendance_rate = 1 - (total_absences / (total_days + 1))  # +1 برای جلوگیری از تقسیم بر صفر
    attendance_rate = round(attendance_rate, 3)
    
    # 4. نرخ تکمیل تکالیف (اگر مدل Homework ندارید، از مقدار پیش‌فرض استفاده کنید)
    # در اینجا فرض می‌کنیم ۸۰٪ از تکالیف انجام شده (می‌توانید بعداً با مدل Homework دقیق‌تر کنید)
    avg_completion_rate = 0.8
    
    # 5. تعداد ارتباطات (اگر مدل Communication ندارید، از تعداد نظرات معلم استفاده کنید)
    # در اینجا تعداد نظرات معلم را به‌عنوان ارتباط در نظر می‌گیریم
    # اگر ندارید، از ۰ یا مقدار پیش‌فرض استفاده کنید
    if not hasattr(student, 'teacher_comments'):
        total_communications = 3  # مقدار پیش‌فرض
    else:
        total_communications = student.teacher_comments.count()# اگر مدل TeacherComment دارید

    
    # 6. تعداد تکالیف انجام‌شده (پیش‌فرض)
    completed_homework = 12  # مقدار پیش‌فرض

    # F02 (change 0044): avg_completion_rate, total_communications and completed_homework above are placeholders -
    # nothing writes the Homework / TeacherParentCommunication tables yet. The page therefore labels the result
    # «نمایشی / داده‌های تکمیلی موجود نیست» and never calls it a real prediction.
    
    # ساخت دیکشنری ورودی برای FastAPI (با ۸ ویژگی)
    input_data = {
        "grade": student.grade,
        "attendance_rate": attendance_rate,
        "avg_completion_rate": avg_completion_rate,
        "avg_exam_score": avg_score,
        "total_absences": total_absences,
        "total_lates": total_lates,
        "total_communications": total_communications,
        "completed_homework": completed_homework
    }
    
    # ---------- ارسال درخواست به FastAPI ----------
    prediction_result = None
    if request.GET.get('predict') == 'true' and ADMIN in roles_for(request.user):  # Admin only (S-04)
        try:
            fastapi_url = "http://fastapi:8001/predict/"
            response = requests.post(
                fastapi_url, json=input_data, headers=service_headers(request.user), timeout=5
            )
            if response.status_code == 200:
                prediction_result = response.json()
            else:
                logger.warning('AI predict failed with status %s: %s', response.status_code, response.text[:200])
                prediction_result = {"error": AI_SERVICE_ERROR.format(status=response.status_code)}
        except ImproperlyConfigured:
            prediction_result = {"error": "سرویس AI پیکربندی نشده است."}
        except requests.exceptions.RequestException as e:
            logger.warning('AI predict is unreachable: %s', e, exc_info=True)
            prediction_result = {"error": AI_UNREACHABLE}

    context = {
        'student': student,
        'grades': grades,
        'attendances': attendances,
        'avg_score': avg_score,
        'absences_count': total_absences,
        'prediction': prediction_result,
        'can_predict': ADMIN in roles_for(request.user),
        'recommendations': visible_recommendations(request.user).filter(student=student),
    }
    return render(request, 'dashboard/student_detail.html', context)



from .forms import StudentForm

@role_required(ADMIN)
def student_create_view(request):
    """افزودن دانش‌آموز جدید"""
    if request.method == 'POST':
        form = StudentForm(request.POST, user=request.user)
        if form.is_valid():
            student = form.save()
            ensure_current_enrollment(student, source='manual')  # keeps the current-year enrollment in step
            messages.success(request, 'دانش‌آموز با موفقیت اضافه شد.')
            return redirect('dashboard:student_list')
        else:
            messages.error(request, 'خطا در ثبت اطلاعات. لطفاً دوباره تلاش کنید.')
    else:
        form = StudentForm(user=request.user)
    
    return render(request, 'dashboard/student_form.html', {'form': form})