"""Create the full demo customer journey for E2E UI testing (platform operator, terminal only).

    manage.py seed_customer_journey

Idempotent. It creates (or reuses) one school «مدرسه پایلوت آرمان» with an active academic year, switches
every sellable module on for that school, and creates one SchoolAdmin, one Grade Lead, one Teacher, one
Counselor and five Students — all with the same password ``Test@1234`` so the tester can log in immediately.
The accounts are school accounts (never staff/superuser), so they exercise the exact same RBAC the real
users hit. A clean table of usernames / passwords / roles is printed to the console. Synthetic data only.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from schools import audit
from schools.entitlements import LICENSED, MODULES, set_module
from schools.models import (
    AcademicYear,
    GradeLeadAssignment,
    School,
    SchoolClass,
    SchoolMembership,
    SchoolStaff,
    TeacherAssignment,
)
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, STUDENT, TEACHER
from students.enrollment_sync import ensure_current_enrollment
from students.models import Student

User = get_user_model()

PASSWORD = 'Test@1234'
SCHOOL_CODE = 'arman-pilot'
SCHOOL_NAME = 'مدرسه پایلوت آرمان'
YEAR_CODE = '1405-1406'
YEAR_LABEL = 'سال تحصیلی 1405-1406'

ROLE_LABELS = {
    ADMIN: 'مدیر مدرسه',
    GRADE_LEAD: 'مربی پایه',
    TEACHER: 'معلم',
    COUNSELOR: 'مشاور',
    STUDENT: 'دانش‌آموز',
}

# (first name, last name) for the five demo students.
STUDENT_NAMES = (
    ('علی', 'احمدی'),
    ('زهرا', 'محمدی'),
    ('محمد', 'کریمی'),
    ('فاطمه', 'حسینی'),
    ('رضا', 'رضایی'),
)


class Command(BaseCommand):
    help = 'Seed one demo school with every role and all modules for end-to-end UI testing.'

    def handle(self, *args, **options):
        today = timezone.localdate()

        # 1. School + current academic year + one class.
        school, _created = School.objects.get_or_create(code=SCHOOL_CODE, defaults={'name': SCHOOL_NAME})
        if not _created and school.name != SCHOOL_NAME:
            School.objects.filter(pk=school.pk).update(name=SCHOOL_NAME)
            school.refresh_from_db()

        # Only one current year per school may exist; make YEAR_CODE the current one.
        AcademicYear.objects.filter(school=school, is_current=True).exclude(code=YEAR_CODE).update(is_current=False)
        year, _ = AcademicYear.objects.get_or_create(
            school=school, code=YEAR_CODE,
            defaults={'label': YEAR_LABEL, 'start_date': date(2026, 9, 23),
                      'end_date': date(2027, 6, 21), 'is_current': True})
        if not year.is_current:
            AcademicYear.objects.filter(school=school, is_current=True).exclude(pk=year.pk).update(is_current=False)
            year.is_current = True
            year.save(update_fields=['is_current'])

        klass, _ = SchoolClass.objects.get_or_create(
            school=school, academic_year=YEAR_CODE, title='کلاس ۷ الف',
            defaults={'grade': 7, 'is_active': True})
        if not klass.is_active:
            SchoolClass.objects.filter(pk=klass.pk).update(is_active=True)

        # 2. Every sellable module on for this school (licensed, open-ended).
        for key in MODULES:
            set_module(school, key, today, ends_on=None, kind=LICENSED, actor=audit.SYSTEM)

        # 3. Accounts — one per role.
        rows = []
        rows.append(self._staff('arman_admin', 'مدیر', 'پایلوت', ADMIN, school, klass))
        rows.append(self._staff('arman_gradelead', 'مربی', 'پایه', GRADE_LEAD, school, klass))
        rows.append(self._staff('arman_teacher', 'معلم', 'پایلوت', TEACHER, school, klass))
        rows.append(self._staff('arman_counselor', 'مشاور', 'پایلوت', COUNSELOR, school, klass))

        for index, (first, last) in enumerate(STUDENT_NAMES, start=1):
            username = f'arman_student{index}'
            user = self._user(username, first, last, STUDENT)
            student, _ = Student.objects.get_or_create(
                national_id=f'100000000{index}',
                defaults={'first_name': first, 'last_name': last, 'grade': 7,
                          'phone_number': f'0900000000{index}', 'school_class': klass,
                          'student_user': user})
            changed = False
            if student.school_class_id != klass.pk:
                student.school_class = klass
                changed = True
            if student.grade != 7:
                student.grade = 7
                changed = True
            if student.first_name != first or student.last_name != last:
                student.first_name, student.last_name = first, last
                changed = True
            if student.student_user_id != user.pk:
                student.student_user = user
                changed = True
            if changed:
                student.save()
            ensure_current_enrollment(student, source='manual')
            rows.append((ROLE_LABELS[STUDENT], user.username))

        self._print_table(school, rows)

    def _staff(self, username, first, last, role, school, klass):
        """Create a staff account and its school link(s); returns (role_label, username)."""
        user = self._user(username, first, last, role)
        SchoolStaff.objects.get_or_create(user=user, school=school)
        if role == ADMIN:
            membership, _ = SchoolMembership.objects.get_or_create(user=user, school=school)
            if not membership.is_active:
                SchoolMembership.objects.filter(pk=membership.pk).update(is_active=True)
        elif role == GRADE_LEAD:
            GradeLeadAssignment.objects.update_or_create(
                user=user, school=school, grade=7, academic_year=YEAR_CODE,
                defaults={'is_active': True})
        elif role == TEACHER:
            TeacherAssignment.objects.get_or_create(teacher=user, school_class=klass, subject='math')
        return ROLE_LABELS[role], user.username

    def _user(self, username, first, last, role):
        """Create or reset one school account to a known, loggable state (never staff/superuser)."""
        group = Group.objects.get_or_create(name=role)[0]
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(username, password=PASSWORD, first_name=first, last_name=last)
        else:
            user.set_password(PASSWORD)
            user.first_name = first
            user.last_name = last
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.save()
        user.groups.set([group])
        # A forced password change would block the first login; the seed must not require it.
        from schools.models import AccountProfile
        AccountProfile.objects.filter(user=user, must_change_password=True).update(must_change_password=False)
        return user

    def _print_table(self, school, rows):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('حساب‌های آزمایشی سفر مشتری آماده شدند.'))
        self.stdout.write('=' * 64)
        self.stdout.write(f'مدرسه: {school.name}  (کد: {school.code})')
        self.stdout.write(f'سال تحصیلی جاری: {YEAR_CODE} · رمز عبور همه: {PASSWORD}')
        self.stdout.write('=' * 64)
        self.stdout.write(f'{"نقش":<14} | {"نام کاربری":<20} | {"رمز عبور"}')
        self.stdout.write('-' * 64)
        for role, username in rows:
            self.stdout.write(f'{role:<14} | {username:<20} | {PASSWORD}')
        self.stdout.write('-' * 64)
        self.stdout.write('نکته: برای دیدن پرونده در صفحهٔ مشاور، ابتدا با مدیر مدرسه یک ارجاع ایجاد کنید.')
        self.stdout.write('')
