# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.db.models import Avg 
from django.db import models
from students.models import Student, Grade, Attendance
import requests

# صفحه‌ی ورود
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard:dashboard')
        else:
            messages.error(request, 'نام کاربری یا رمز عبور اشتباه است.')
    return render(request, 'dashboard/login.html')

# خروج از حساب
def logout_view(request):
    logout(request)
    return redirect('login')

# داشبورد اصلی (فقط کاربران لاگین‌شده)
@login_required
def dashboard_view(request):
    total_students = Student.objects.count()
    total_grades = Grade.objects.count()
    total_attendances = Attendance.objects.count()
    avg_grade_all = Grade.objects.aggregate(avg=models.Avg('score'))['avg'] or 0
        
    context = {
        'total_students': total_students,
        'total_grades': total_grades,
        'total_attendances': total_attendances,
        'avg_grade_all': round(avg_grade_all, 2),
        'user': request.user,
    }
    return render(request, 'dashboard/dashboard.html', context)

# لیست دانش‌آموزان
@login_required
def student_list_view(request):
    students = Student.objects.all()
    search_query = request.GET.get('search')
    if search_query:
        students = students.filter(
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(national_id__icontains=search_query)
        )
    return render(request, 'dashboard/student_list.html', {'students': students})

# جزئیات یک دانش‌آموز + نمایش نتیجه‌ی پیش‌بینی
# dashboard/views.py (قسمت student_detail_view)

@login_required
def student_detail_view(request, pk):
    student = get_object_or_404(Student, pk=pk)
    grades = student.grades.all()
    attendances = student.attendances.all()
    
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
    if request.GET.get('predict') == 'true':
        try:
            fastapi_url = "http://fastapi:8001/predict/"
            response = requests.post(fastapi_url, json=input_data, timeout=5)
            if response.status_code == 200:
                prediction_result = response.json()
            else:
                prediction_result = {
                    "error": f"خطا در سرویس AI: {response.status_code} - {response.text}"
                }
        except requests.exceptions.RequestException as e:
            prediction_result = {"error": f"خطا در ارتباط با سرویس AI: {str(e)}"}

    context = {
        'student': student,
        'grades': grades,
        'attendances': attendances,
        'avg_score': avg_score,
        'absences_count': total_absences,
        'prediction': prediction_result,
        'input_data': input_data,  # برای نمایش در قالب (اختیاری)
    }
    return render(request, 'dashboard/student_detail.html', context)

# آپلود فایل (فقط ادمین)
@login_required
def upload_students_view(request):
    if not request.user.is_superuser and not request.user.groups.filter(name='Admin').exists():
        messages.error(request, 'شما اجازه‌ی دسترسی به این بخش را ندارید.')
        return redirect('dashboard')
    
    if request.method == 'POST' and request.FILES.get('file'):
        # اینجا همان منطق import_students که قبلاً در API نوشته‌ایم را می‌توانیم صدا بزنیم
        # اما برای جلوگیری از تکرار کد، بهتر است از خود API استفاده کنیم (یا کد را کپی کنیم)
        # فعلاً برای سادگی، یک پیام موفقیت نمایش می‌دهیم:
        messages.success(request, 'فایل با موفقیت آپلود شد! (منطق پردازش اضافه خواهد شد)')
        return redirect('upload_students')
    
    return render(request, 'dashboard/upload.html')

@login_required
def chat_view(request):
    if request.method == 'POST':
        query = request.POST.get('query')
        if query:
            try:
                fastapi_url = "http://fastapi:8001/chat/"
                response = requests.post(fastapi_url, json={"query": query}, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    return render(request, 'dashboard/chat.html', {
                        'query': query,
                        'answer': result.get('answer'),
                        'sources': result.get('sources', [])
                    })
                else:
                    error_msg = f"خطا در سرویس AI: {response.status_code}"
            except requests.exceptions.RequestException as e:
                error_msg = f"خطا در ارتباط با سرویس AI: {str(e)}"
            
            return render(request, 'dashboard/chat.html', {
                'query': query,
                'error': error_msg
            })
    
    return render(request, 'dashboard/chat.html')

@login_required
def library_view(request):
    """
    صفحه‌ی کتابخانه: نمایش لیست اسناد و فرم آپلود
    """
    # دریافت لیست اسناد از FastAPI (اختیاری)
    documents = []
    try:
        response = requests.get("http://fastapi:8001/documents/list/", timeout=5)
        if response.status_code == 200:
            documents = response.json().get('documents', [])
    except:
        pass  # در صورت عدم دسترسی، لیست خالی می‌ماند

    context = {
        'documents': documents,
    }
    return render(request, 'dashboard/library.html', context)

@login_required
def upload_document_view(request):
    if request.method != 'POST':
        return redirect('dashboard:library')
    
    uploaded_file = request.FILES.get('document_file')
    if not uploaded_file:
        messages.error(request, 'لطفاً یک فایل انتخاب کنید.')
        return redirect('dashboard:library')
    
    # بررسی حجم
    if uploaded_file.size > 10 * 1024 * 1024:
        messages.error(request, 'حجم فایل نباید بیشتر از ۱۰ مگابایت باشد.')
        return redirect('dashboard:library')
    
    # بررسی فرمت
    allowed_extensions = ['.pdf', '.docx', '.doc']
    file_name = uploaded_file.name.lower()
    if not any(file_name.endswith(ext) for ext in allowed_extensions):
        messages.error(request, 'فرمت فایل پشتیبانی نمی‌شود. فقط PDF و Word مجاز است.')
        return redirect('dashboard:library')
    
    try:
        files = {'file': (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)}
        response = requests.post(
            "http://fastapi:8001/upload-document/",
            files=files,
            timeout=3000  # افزایش timeout به ۳۰۰ ثانیه
        )
        
        if response.status_code == 200:
            result = response.json()
            messages.success(
                request, 
                f"فایل با موفقیت آپلود شد و به {result.get('chunks', 0)} بخش تقسیم شد."
            )
        else:
            error_detail = response.json().get('detail', 'خطای ناشناخته')
            messages.error(request, f"خطا در آپلود: {error_detail}")
            
    except requests.exceptions.Timeout:
        messages.error(request, 'زمان پردازش فایل بیش از حد مجاز بود. لطفاً فایل کوچک‌تری انتخاب کنید.')
    except requests.exceptions.RequestException as e:
        messages.error(request, f"خطا در ارتباط با سرویس AI: {str(e)}")
    
    return redirect('dashboard:library')

@login_required
def delete_document_view(request):
    """حذف یک فایل (همه بخش‌ها) از کتابخانه"""
    if request.method != 'POST':
        return redirect('dashboard:library')
    
    parent_id = request.POST.get('parent_id')  # ✅ دریافت parent_id به جای doc_id
    if not parent_id:
        messages.error(request, 'شناسه فایل ارسال نشد.')
        return redirect('dashboard:library')
    
    try:
        response = requests.delete(
            f"http://fastapi:8001/documents/parent/{parent_id}",
            timeout=5
        )
        if response.status_code == 200:
            messages.success(request, 'فایل با موفقیت حذف شد.')
        else:
            error_detail = response.json().get('detail', 'خطای ناشناخته')
            messages.error(request, f'خطا در حذف فایل: {error_detail}')
    except requests.exceptions.RequestException as e:
        messages.error(request, f'خطا در ارتباط با سرویس AI: {str(e)}')
    
    return redirect('dashboard:library')


from .forms import StudentForm

@login_required
def student_create_view(request):
    """افزودن دانش‌آموز جدید"""
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'دانش‌آموز با موفقیت اضافه شد.')
            return redirect('dashboard:student_list')
        else:
            messages.error(request, 'خطا در ثبت اطلاعات. لطفاً دوباره تلاش کنید.')
    else:
        form = StudentForm()
    
    return render(request, 'dashboard/student_form.html', {'form': form})