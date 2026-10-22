from django import forms
from django.contrib import admin
from .models import Student
from .models import Student, Grade, Attendance
from .student_school import StudentSchoolError, allowed_school_ids, resolve_student_school



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

class StudentAdminForm(forms.ModelForm):
    """S2b: the school of a student is decided by the single rule in students/student_school.py. The ``target_school``
    field is the explicit choice for a student without a class; ``StudentAdmin.get_form`` binds the user (fail closed
    when it is missing). Open item for S9 (changes/0010 section 7): ADR-0012 section 4 says the platform role has no
    student access in the Django admin; this field exists because accounts reach this admin today."""

    target_school = forms.ModelChoiceField(queryset=None, required=False, label='مدرسه')
    bound_user = None
    bound_existing_school_id = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from schools.models import School
        self.fields['target_school'].queryset = School.objects.filter(
            pk__in=allowed_school_ids(self.bound_user)).order_by('name')

    def clean(self):
        cleaned = super().clean()
        if self.errors.get('school_class') or self.errors.get('target_school'):
            return cleaned
        target = cleaned.get('target_school')
        try:
            school_id = resolve_student_school(
                self.bound_user, school_class=cleaned.get('school_class'),
                target_school_id=target.pk if target is not None else None,
                existing_school_id=self.bound_existing_school_id, is_existing=bool(self.instance.pk))
        except StudentSchoolError as exc:
            self.add_error('school_class' if exc.code == 'class_target_mismatch' else 'target_school', exc.message)
            return cleaned
        self.instance.school_id = school_id
        return cleaned

    class Meta:
        model = Student
        fields = '__all__'


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentAdminForm
    list_display = ['first_name', 'last_name', 'national_id', 'grade', 'school_class', 'class_name',
                    'phone_number', 'created_at']
    list_filter = ['grade', 'school_class', 'class_name', 'created_at']
    search_fields = ['first_name', 'last_name', 'national_id', 'phone_number']
    # class_name is the deprecated mirror of school_class and school is derived: neither is edited by hand.
    readonly_fields = ['class_name', 'school', 'created_at', 'updated_at']

    def get_form(self, request, obj=None, **kwargs):
        request._student_being_edited = obj  # lets the class selector keep the current (maybe inactive) class
        form = super().get_form(request, obj, **kwargs)
        # Bind the acting user and the stored school to a subclass: the form class itself is shared between requests.
        return type('BoundStudentAdminForm', (form,), {
            'bound_user': request.user,
            'bound_existing_school_id': obj.school_id if obj is not None else None})

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