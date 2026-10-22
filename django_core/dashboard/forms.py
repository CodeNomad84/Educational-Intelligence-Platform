# dashboard/forms.py
from django import forms
from schools.models import School, SchoolClass
from students.models import Student
from students.student_school import (
    StudentSchoolError, allowed_school_ids, class_choices, parent_choices, resolve_student_school)


class StudentForm(forms.ModelForm):
    # S2b: stateless target school for a student without a class. Offered only from the user's own schools; the
    # decision is made by the single rule in students/student_school.py (never a default, never from a file).
    target_school = forms.ModelChoiceField(
        queryset=School.objects.none(), required=False, empty_label='— مدرسه —', label='مدرسه',
        widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user  # None = fail closed: clean() rejects the form
        self.fields['target_school'].queryset = School.objects.filter(pk__in=allowed_school_ids(user)).order_by('name')
        # Class membership is chosen from existing ACTIVE classes only; classes are never auto-created
        # (ADR-0004 §6). ``class_name`` is a read-only mirror and no longer a form field.
        field = self.fields['school_class']
        field.queryset = class_choices(user, keep_pk=self.instance.school_class_id).select_related('school')
        self.fields['parent_user'].queryset = parent_choices(user, keep_pk=self.instance.parent_user_id)
        field.empty_label = '— بدون کلاس —'
        field.required = False

    def clean(self):
        cleaned = super().clean()
        if self.errors.get('school_class') or self.errors.get('target_school'):
            return cleaned  # a bad class / school choice already has its error
        target = cleaned.get('target_school')
        try:
            school_id = resolve_student_school(
                self.user, school_class=cleaned.get('school_class'),
                target_school_id=target.pk if target is not None else None,
                existing_school_id=self.instance.school_id if self.instance.pk else None)
        except StudentSchoolError as exc:
            field = 'school_class' if exc.code == 'class_target_mismatch' else 'target_school'
            self.add_error(field, exc.message)
            return cleaned
        self.instance.school_id = school_id  # ``school`` is not a form field; a class re-derives the same value in save()
        return cleaned

    class Meta:
        model = Student
        fields = [
            'first_name', 'last_name', 'national_id',
            'grade', 'school_class', 'phone_number',
            'father_job', 'mother_job', 'parent_user'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام خانوادگی'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'کد ملی'}),
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'school_class': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'شماره تماس'}),
            'father_job': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'شغل پدر'}),
            'mother_job': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'شغل مادر'}),
            'parent_user': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'national_id': 'کد ملی',
            'grade': 'پایه تحصیلی',
            'school_class': 'کلاس',
            'phone_number': 'شماره تماس',
            'father_job': 'شغل پدر',
            'mother_job': 'شغل مادر',
            'parent_user': 'والدین (کاربر)',
        }