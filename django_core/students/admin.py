from django.contrib import admin
from .models import Student
from .models import Student, Grade, Attendance



# ---------- تعریف Inline برای نمایش در صفحه‌ی دانش‌آموز ----------
class GradeInline(admin.TabularInline):
    """
    نمایش نمرات به صورت جدولی در پایین صفحه‌ی ویرایش دانش‌آموز
    """
    model = Grade
    extra = 1  # تعداد ردیف‌های خالی برای افزودن نمره جدید
    fields = ['subject', 'exam_type', 'score', 'date']
    show_change_link = True


class AttendanceInline(admin.TabularInline):
    """
    نمایش حضور و غیاب به صورت جدولی در پایین صفحه‌ی ویرایش دانش‌آموز
    """
    model = Attendance
    extra = 1  # تعداد ردیف‌های خالی برای افزودن غیبت جدید
    fields = ['date', 'status', 'note']
    show_change_link = True

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'national_id', 'grade', 'class_name', 'phone_number', 'created_at']
    list_filter = ['grade', 'class_name', 'created_at']
    search_fields = ['first_name', 'last_name', 'national_id', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    
    # ✅ این خطوط را اضافه کنید تا Inlineها در صفحه‌ی دانش‌آموز نمایش داده شوند
    inlines = [GradeInline, AttendanceInline]


# ---------- (اختیاری) ثبت مدل‌های Grade و Attendance به‌عنوان بخش مستقل در ادمین ----------
# اگر بخواهید علاوه بر Inline، یک بخش جداگانه در منوی ادمین برای مدیریت نمرات و غیبت‌ها داشته باشید، 
# این دو خط را از حالت نظر خارج کنید:

# @admin.register(Grade)
# class GradeAdmin(admin.ModelAdmin):
#     list_display = ['student', 'subject', 'exam_type', 'score', 'date']
#     list_filter = ['subject', 'exam_type']
#     search_fields = ['student__first_name', 'student__last_name']

# @admin.register(Attendance)
# class AttendanceAdmin(admin.ModelAdmin):
#     list_display = ['student', 'date', 'status']
#     list_filter = ['status', 'date']
#     search_fields = ['student__first_name', 'student__last_name']