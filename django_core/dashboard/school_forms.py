"""Forms of the SchoolAdmin pages (Slice 1). Every form is built for ONE school (the admin's current school): choices
are that school's rows only, and the school of a saved row is set server-side, never taken from the request."""
from datetime import date

from django.utils import timezone
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from schools.models import AcademicYear, GradeLeadAssignment, SchoolClass, SchoolStaff, TeacherAssignment

User = get_user_model()
WIDGET = {'class': 'form-control'}
SELECT = {'class': 'form-select'}


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ['code', 'label', 'start_date', 'end_date']
        widgets = {
            'code': forms.TextInput(attrs={**WIDGET, 'placeholder': '1404-1405'}),
            'label': forms.TextInput(attrs=WIDGET),
            'start_date': forms.DateInput(attrs={**WIDGET, 'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={**WIDGET, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.instance.school = school

    def clean_code(self):
        code = self.cleaned_data['code']
        if AcademicYear.objects.filter(school=self.school, code=code).exists():
            raise forms.ValidationError('این سال تحصیلی قبلاً ثبت شده است.')
        return code


class SchoolClassForm(forms.ModelForm):
    academic_year = forms.ChoiceField(label='سال تحصیلی', widget=forms.Select(attrs=SELECT))

    class Meta:
        model = SchoolClass
        fields = ['title', 'grade', 'academic_year', 'is_active']
        widgets = {'title': forms.TextInput(attrs=WIDGET), 'grade': forms.Select(attrs=SELECT)}

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.instance.school = school
        codes = list(AcademicYear.objects.filter(school=school).order_by('-start_date').values_list('code', flat=True))
        current = self.instance.academic_year
        if current and current not in codes:
            codes.append(current)   # a legacy class keeps its (non-canonical) year text
        self.fields['academic_year'].choices = [(c, c) for c in codes]
        self.fields['grade'].required = True
        self.fields['grade'].choices = [c for c in self.fields['grade'].choices if c[0] != '']

    def clean(self):
        cleaned = super().clean()
        title, year = cleaned.get('title'), cleaned.get('academic_year')
        if title and year is not None and SchoolClass.objects.filter(
                school=self.school, academic_year=year, title=title).exclude(pk=self.instance.pk).exists():
            self.add_error('title', 'کلاسی با این عنوان در همین سال تحصیلی وجود دارد.')
        return cleaned


def staff_queryset(school, group_name):
    return User.objects.filter(school_staff__school=school, groups__name=group_name).select_related(
        'school_staff').order_by('last_name', 'username')


class StaffAccountForm(UserCreationForm):
    """Creates a Teacher / Grade Lead account that belongs to the school. Never staff, never superuser."""
    first_name = forms.CharField(label='نام', max_length=150)
    last_name = forms.CharField(label='نام خانوادگی', max_length=150)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name')

    def __init__(self, *args, school, group_name, created_by, **kwargs):
        super().__init__(*args, **kwargs)
        self.school, self.group_name, self.created_by = school, group_name, created_by
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if len(password or '') < 8:   # the project configures no password validators; staff accounts get a minimum
            raise forms.ValidationError('رمز عبور باید دست‌کم ۸ نویسه باشد.')
        return password

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.is_staff = False
            user.is_superuser = False
            user.save()
            user.groups.add(Group.objects.get_or_create(name=self.group_name)[0])
            SchoolStaff.objects.create(user=user, school=self.school, created_by=self.created_by)
        return user


class TeacherAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeacherAssignment
        fields = ['school_class', 'subject']
        widgets = {'school_class': forms.Select(attrs=SELECT), 'subject': forms.Select(attrs=SELECT)}

    def __init__(self, *args, school, teacher, created_by, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.teacher = teacher
        self.instance.created_by = created_by
        self.fields['school_class'].queryset = SchoolClass.objects.filter(school=school, is_active=True)
        self.fields['subject'].required = True
        self.fields['subject'].choices = [c for c in self.fields['subject'].choices if c[0] != '']

    def clean(self):
        cleaned = super().clean()
        klass, subject = cleaned.get('school_class'), cleaned.get('subject')
        if klass and subject and TeacherAssignment.objects.filter(
                teacher=self.instance.teacher, school_class=klass, subject=subject).exists():
            raise forms.ValidationError('این تخصیص قبلاً ثبت شده است.')
        return cleaned


class GradeLeadAssignmentForm(forms.ModelForm):
    academic_year = forms.ChoiceField(label='سال تحصیلی', widget=forms.Select(attrs=SELECT))

    class Meta:
        model = GradeLeadAssignment
        fields = ['grade', 'academic_year']
        widgets = {'grade': forms.Select(attrs=SELECT)}

    def __init__(self, *args, school, lead, created_by, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = lead
        self.instance.school = school
        self.instance.created_by = created_by
        codes = AcademicYear.objects.filter(school=school).order_by('-start_date').values_list('code', flat=True)
        self.fields['academic_year'].choices = [(c, c) for c in codes]
        self.fields['grade'].choices = [c for c in self.fields['grade'].choices if c[0] != '']

    def clean(self):
        cleaned = super().clean()
        grade, year = cleaned.get('grade'), cleaned.get('academic_year')
        if grade and year and GradeLeadAssignment.objects.filter(
                user=self.instance.user, school=self.instance.school, grade=grade, academic_year=year).exists():
            raise forms.ValidationError('این تخصیص قبلاً ثبت شده است.')
        return cleaned


def suggested_year(school):
    """Defaults for the next academic year form: the year after the latest one (Gregorian dates, Mehr 1 - Shahrivar 31)."""
    latest = AcademicYear.objects.filter(school=school).order_by('-start_date').first()
    if latest is None:
        today = timezone.localdate()
        first = today.year - 622 if today.month >= 3 else today.year - 623   # Solar Hijri start year, roughly
    else:
        first = int(latest.code.split('-')[0]) + 1
    return {'code': f'{first}-{first + 1}', 'start_date': date(first + 621, 9, 23), 'end_date': date(first + 622, 6, 21)}
