# dashboard/forms.py
from django import forms
from schools.models import SchoolClass
from students.models import Student

class StudentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Class membership is chosen from existing ACTIVE classes only; classes are never auto-created
        # (ADR-0004 §6). ``class_name`` is a read-only mirror and no longer a form field.
        field = self.fields['school_class']
        field.queryset = SchoolClass.objects.filter(is_active=True).select_related('school')
        field.empty_label = '— بدون کلاس —'
        field.required = False

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