"""``seed_customer_journey``: one demo school, all modules on, one account of each role and five students, idempotent.

Synthetic data only; every account logs in with the printed password and none is staff/superuser.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from schools.entitlements import MODULES, module_enabled
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, STUDENT, TEACHER

from .models import (
    AcademicYear,
    GradeLeadAssignment,
    School,
    SchoolClass,
    SchoolMembership,
    SchoolModule,
    SchoolStaff,
    TeacherAssignment,
)
from .management.commands.seed_customer_journey import PASSWORD, SCHOOL_CODE, YEAR_CODE
from students.models import Student

User = get_user_model()


class SeedCustomerJourneyTests(TestCase):
    def run_seed(self):
        out = StringIO()
        call_command('seed_customer_journey', stdout=out)
        return out.getvalue()

    def test_creates_everything(self):
        output = self.run_seed()

        school = School.objects.get(code=SCHOOL_CODE)
        self.assertEqual(school.name, 'مدرسه پایلوت آرمان')
        self.assertEqual(AcademicYear.objects.get(school=school, is_current=True).code, YEAR_CODE)
        self.assertTrue(SchoolClass.objects.filter(school=school, academic_year=YEAR_CODE, is_active=True).exists())

        for key in MODULES:
            self.assertTrue(module_enabled(school, key), key)

        admin = User.objects.get(username='arman_admin')
        self.assertTrue(admin.check_password(PASSWORD))
        self.assertTrue(admin.groups.filter(name=ADMIN).exists())
        self.assertTrue(SchoolMembership.objects.filter(user=admin, school=school, is_active=True).exists())

        lead = User.objects.get(username='arman_gradelead')
        self.assertTrue(lead.groups.filter(name=GRADE_LEAD).exists())
        self.assertTrue(SchoolStaff.objects.filter(user=lead, school=school).exists())
        self.assertTrue(GradeLeadAssignment.objects.filter(user=lead, school=school, academic_year=YEAR_CODE).exists())

        teacher = User.objects.get(username='arman_teacher')
        self.assertTrue(teacher.groups.filter(name=TEACHER).exists())
        self.assertTrue(SchoolStaff.objects.filter(user=teacher, school=school).exists())
        self.assertTrue(TeacherAssignment.objects.filter(teacher=teacher).exists())

        counselor = User.objects.get(username='arman_counselor')
        self.assertTrue(counselor.groups.filter(name=COUNSELOR).exists())
        self.assertTrue(SchoolStaff.objects.filter(user=counselor, school=school).exists())

        students = Student.objects.filter(school=school)
        self.assertEqual(students.count(), 5)
        for student in students:
            self.assertTrue(student.student_user_id)
            self.assertTrue(student.student_user.groups.filter(name=STUDENT).exists())
            self.assertTrue(student.student_user.check_password(PASSWORD))
            self.assertTrue(student.enrollments.filter(academic_year__is_current=True).exists())

        self.assertIn('arman_admin', output)
        self.assertIn('arman_student1', output)
        self.assertIn(PASSWORD, output)

        # School accounts must never open the Django admin.
        for user in (admin, lead, teacher, counselor, *[s.student_user for s in students]):
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)

    def test_idempotent(self):
        self.run_seed()
        before = (School.objects.count(), User.objects.count(), Student.objects.count(),
                  SchoolModule.objects.count(), SchoolStaff.objects.count())
        self.run_seed()
        after = (School.objects.count(), User.objects.count(), Student.objects.count(),
                 SchoolModule.objects.count(), SchoolStaff.objects.count())
        self.assertEqual(before, after)
