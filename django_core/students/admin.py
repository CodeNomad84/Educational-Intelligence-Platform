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
    list_display = ['first_name', 'last_name', 'national_id', 'grade', 'school_class', 'class_name',
                    'phone_number', 'created_at']
    list_filter = ['grade', 'school_class', 'class_name', 'created_at']
    search_fields = ['first_name', 'last_name', 'national_id', 'phone_number']
    # class_name is the deprecated mirror of school_class and school is derived: neither is edited by hand.
    readonly_fields = ['class_name', 'school', 'created_at', 'updated_at']

    def get_form(self, request, obj=None, **kwargs):
        request._student_being_edited = obj  # lets the class selector keep the current (maybe inactive) class
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'school_class':
            from django.db.models import Q
            from schools.models import SchoolClass
            current = getattr(getattr(request, '_student_being_edited', None), 'school_class_id', None)
            kwargs['queryset'] = SchoolClass.objects.filter(Q(is_active=True) | Q(pk=current))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from django.contrib import messages
        from students.enrollment_sync import SKIPPED, ensure_current_enrollment
        outcome = ensure_current_enrollment(obj, source='manual')
        if outcome in SKIPPED and outcome != 'no_class':
            messages.warning(request, f'ثبت‌نام سال جاری به‌روز نشد ({outcome}).')

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