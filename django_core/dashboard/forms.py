# dashboard/forms.py
from django import forms
from students.models import Student

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'first_name', 'last_name', 'national_id',
            'grade', 'class_name', 'phone_number',
            'father_job', 'mother_job', 'parent_user'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام خانوادگی'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'کد ملی'}),
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'class_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'کلاس'}),
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
            'class_name': 'کلاس',
            'phone_number': 'شماره تماس',
            'father_job': 'شغل پدر',
            'mother_job': 'شغل مادر',
            'parent_user': 'والدین (کاربر)',
        }