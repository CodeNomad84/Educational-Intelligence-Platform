# students/views.py
import pandas as pd
from io import BytesIO, TextIOWrapper
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from .models import Student
from django.db.models import Avg
import requests
from .serializers import StudentSerializer, FileUploadSerializer
from .permissions import IsAdminUser  # فقط ادمین بتواند آپلود کند

class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]  # پیش‌فرض
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['grade', 'first_name', 'last_name', 'class_name']
    search_fields = ['first_name', 'last_name', 'national_id']
    ordering_fields = ['first_name', 'last_name', 'grade', 'created_at']
    ordering = ['first_name']

    def get_permissions(self):
        # همان قوانین قبلی
        if self.action == 'import_students':
            return [IsAdminUser()]  # فقط ادمین اجازه‌ی آپلود دارد
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        # همان فیلترهای قبلی
        user = self.request.user
        if not user or not user.is_authenticated:
            return Student.objects.none()
        if user.groups.filter(name='Admin').exists():
            return Student.objects.all()
        if user.groups.filter(name='Teacher').exists():
            return Student.objects.all()
        if user.groups.filter(name='Parent').exists():
            # در این مرحله، والدین فقط فرزندان خودشان را می‌بینند
            return Student.objects.filter(parent_user=user)
        return Student.objects.none()

    # ✅ اکشن جدید برای آپلود فایل
    @action(detail=False, methods=['post'], url_path='import')
    def import_students(self, request):
        serializer = FileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        file_extension = file.name.split('.')[-1].lower()
        
        try:
            # خواندن فایل بر اساس پسوند
            if file_extension == 'csv':
                # برای CSV باید encoding را utf-8-sig در نظر بگیریم تا فارسی به درستی خوانده شود
                df = pd.read_csv(TextIOWrapper(file, encoding='utf-8-sig'))
            elif file_extension in ['xlsx', 'xls']:
                df = pd.read_excel(BytesIO(file.read()))
            else:
                return Response(
                    {'error': 'فرمت فایل پشتیبانی نمی‌شود. فقط csv, xlsx, xls مجاز است.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # حذف رکوردهای خالی (NaN) برای جلوگیری از خطا
            df = df.dropna(how='all')
            
            if df.empty:
                return Response(
                    {'error': 'فایل خالی است یا داده‌ای در آن وجود ندارد.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # استانداردسازی نام ستون‌ها (حذف فاصله‌های اضافی و تبدیل به حروف کوچک)
            df.columns = df.columns.str.strip().str.lower()
            
            # مپ کردن ستون‌های احتمالی به نام فیلدهای مدل
            # کاربر می‌تواند ستون‌هایی با نام 'نام', 'نام خانوادگی', 'کد ملی' و ... داشته باشد
            column_mapping = {
                'نام': 'first_name',
                'نام خانوادگی': 'last_name',
                'نام خانوادگى': 'last_name',  # احتمال اشتباه تایپی
                'کد ملی': 'national_id',
                'کدملی': 'national_id',
                'پایه': 'grade',
                'پایه تحصیلی': 'grade',
                'کلاس': 'class_name',
                'شماره تماس': 'phone_number',
                'تلفن': 'phone_number',
                'موبایل': 'phone_number',
                'شغل پدر': 'father_job',
                'شغل مادر': 'mother_job',
            }
            
            # تغییر نام ستون‌ها در دیتافریم
            df = df.rename(columns=column_mapping)
            
            # لیست ستون‌های اجباری که حتماً باید در فایل باشند
            required_columns = ['first_name', 'last_name', 'national_id', 'grade']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                return Response(
                    {'error': f'ستون‌های اجباری ({", ".join(missing_columns)}) در فایل وجود ندارند.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # تبدیل دیتافریم به لیست دیکشنری و پردازش رکوردها
            created_count = 0
            updated_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    # بررسی وجود کد ملی
                    national_id = str(row.get('national_id', '')).strip()
                    if not national_id:
                        errors.append(f"ردیف {index+2}: کد ملی خالی است.")
                        continue

                    # ساخت دیکشنری داده‌ها
                    data = {
                        'first_name': str(row.get('first_name', '')).strip(),
                        'last_name': str(row.get('last_name', '')).strip(),
                        'national_id': national_id,
                        'class_name': str(row.get('class_name', '')).strip(),
                        'phone_number': str(row.get('phone_number', '')).strip(),
                        'father_job': str(row.get('father_job', '')).strip(),
                        'mother_job': str(row.get('mother_job', '')).strip(),
                    }
                    
                    # پردازش پایه (Grade)
                    grade_value = row.get('grade')
                    if pd.isna(grade_value):
                        errors.append(f"ردیف {index+2}: پایه تحصیلی خالی است.")
                        continue
                    
                    try:
                        data['grade'] = int(float(grade_value))
                    except (ValueError, TypeError):
                        errors.append(f"ردیف {index+2}: مقدار پایه ({grade_value}) معتبر نیست.")
                        continue

                    # اعتبارسنجی پایه (بین ۷ تا ۱۲)
                    if data['grade'] not in [7, 8, 9, 10, 11, 12]:
                        errors.append(f"ردیف {index+2}: پایه باید بین ۷ تا ۱۲ باشد.")
                        continue

                    # ایجاد یا بروزرسانی رکورد بر اساس کد ملی
                    student, created = Student.objects.update_or_create(
                        national_id=data['national_id'],
                        defaults=data
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    errors.append(f"ردیف {index+2}: خطا - {str(e)}")

            return Response({
                'status': 'success',
                'created': created_count,
                'updated': updated_count,
                'errors': errors,
                'total_rows': len(df)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'خطا در پردازش فایل: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    @action(detail=True, methods=['get'], url_path='predict')
    def predict_status(self, request, pk=None):
        """
        دریافت اطلاعات یک دانش‌آموز و ارسال به FastAPI برای پیش‌بینی وضعیت
        """
        student = self.get_object()
        
        # در دنیای واقعی، اینجا باید میانگین نمرات و غیبت را از پایگاه داده محاسبه کنید.
        # فعلاً برای تست، از داده‌های ساختگی استفاده می‌کنیم.
        # بعداً که مدل‌های Grade و Attendance را ساختیم، این مقادیر واقعی می‌شوند.
        
        # داده‌های تستی (فرض می‌کنیم این دانش‌آموز نمره ۱۸ و ۱ جلسه غیبت دارد)
        test_data = {
            "avg_score": 18.0,
            "absences": 1
        }
        
        try:
            # ارسال درخواست به FastAPI (از داخل شبکه‌ی Docker با نام سرویس)
            fastapi_url = "http://fastapi:8001/predict/"
            response = requests.post(fastapi_url, json=test_data, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            return Response({
                "student": f"{student.first_name} {student.last_name}",
                "prediction_result": result
            })
            
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"خطا در ارتباط با سرویس هوش مصنوعی: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    @action(detail=True, methods=['get'], url_path='features')
    def get_features(self, request, pk=None):
        student = self.get_object()
        grades = student.grades.all()
        avg_score = grades.aggregate(Avg('score'))['score__avg'] or 0
        attendances = student.attendances.all()
        total_absences = attendances.filter(status='absent').count()
        total_lates = attendances.filter(status='late').count()
        total_days = attendances.count()
        attendance_rate = 1 - (total_absences / (total_days + 1))
        
        data = {
            "grade": student.grade,
            "attendance_rate": round(attendance_rate, 2),
            "avg_completion_rate": 0.8,  # از مدل Homework محاسبه شود
            "avg_exam_score": round(avg_score, 2),
            "total_absences": total_absences,
            "total_lates": total_lates,
            "total_communications": 3,  # از مدل Communication محاسبه شود
            "completed_homework": 12    # از مدل Homework محاسبه شود
        }
        return Response(data)
    
    def predict_status(self, request, pk=None):
        student = self.get_object()
        
        # محاسبه‌ی میانگین نمرات دانش‌آموز (از تمام نمرات ثبت‌شده)
        grades = student.grades.all()
        if grades.exists():
            avg_score = grades.aggregate(Avg('score'))['score__avg']
        else:
            avg_score = 10.0  # مقدار پیش‌فرض در صورت نداشتن نمره
        
        # محاسبه‌ی تعداد غیبت‌های غیرموجه (غائب) - فرض می‌کنیم وضعیت 'absent' نشان‌دهنده‌ی غیبت است
        absences_count = student.attendances.filter(status='absent').count()
        
        # داده‌های ورودی برای FastAPI
        input_data = {
            "avg_score": round(avg_score, 2),
            "absences": absences_count
        }
        
        try:
            fastapi_url = "http://fastapi:8001/predict/"
            response = requests.post(fastapi_url, json=input_data, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            return Response({
                "student": f"{student.first_name} {student.last_name}",
                "input_data": input_data,
                "prediction_result": result
            })
            
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"خطا در ارتباط با سرویس هوش مصنوعی: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
    # students/views.py (در کلاس StudentViewSet)
@action(detail=True, methods=['get'], url_path='predict')
def predict_status(self, request, pk=None):
    student = self.get_object()
    
    # محاسبه‌ی ویژگی‌های مورد نیاز (بر اساس داده‌های موجود)
    grades = student.grades.all()
    attendances = student.attendances.all()
    # فرض می‌کنیم مدل‌های Homework و TeacherComment را هم اضافه کرده‌اید
    # یا حداقل داده‌های مشابه را از مدل‌های موجود استخراج کنید
    
    avg_score = grades.aggregate(models.Avg('score'))['score__avg'] or 0
    total_absences = attendances.filter(status='absent').count()
    total_lates = attendances.filter(status='late').count()
    attendance_rate = 1 - (total_absences / (attendances.count() + 1))  # +1 برای جلوگیری از تقسیم بر صفر
    
    # برای تکمیل ویژگی‌های دیگر، ممکن است نیاز به مدل‌های جدید داشته باشید
    # فعلاً با داده‌های موجود، یک درخواست نمونه می‌سازیم
    input_data = {
        "grade": student.grade,
        "attendance_rate": round(attendance_rate, 2),
        "avg_completion_rate": 0.8,  # نمونه
        "avg_exam_score": round(avg_score, 2),
        "total_absences": total_absences,
        "total_lates": total_lates,
        "total_communications": 3,  # نمونه
        "completed_homework": 12  # نمونه
    }
    
    try:
        fastapi_url = "http://fastapi:8001/predict/"
        response = requests.post(fastapi_url, json=input_data, timeout=5)
        response.raise_for_status()
        result = response.json()
        
        return Response({
            "student": f"{student.first_name} {student.last_name}",
            "input_data": input_data,
            "prediction_result": result
        })
        
    except requests.exceptions.RequestException as e:
        return Response(
            {"error": f"خطا در ارتباط با سرویس AI: {str(e)}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )