"""S2b commit 3 tested the Django-admin student form. Since C-A (S9; decision pack 0028 P3-10) students are not in the Django
admin at all: the school of a new student is decided on the school pages and the API (``students/student_school.py``, tested
in ``test_student_school.py``, ``test_own_school_choices.py`` and the dashboard form tests). These tests pin the closure."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from schools.models import School, SchoolMembership

from .models import Student

User = get_user_model()
ADD = '/admin/students/student/add/'


class StudentAdminClosedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.student = Student.objects.create(first_name='N', last_name='T', national_id='9200000001', grade=7,
                                             phone_number='0', school=cls.a)

    def test_superuser_finds_no_student_pages(self):
        self.client.force_login(User.objects.create_superuser('root', password='x'))
        for url in (ADD, '/admin/students/student/', f'/admin/students/student/{self.student.pk}/change/'):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertNotContains(self.client.get('/admin/'), 'students/student')

    def test_staff_school_admin_is_refused_by_the_site(self):
        user = User.objects.create_user('sa', password='x', is_staff=True)
        user.groups.add(Group.objects.get_or_create(name='SchoolAdmin')[0])
        SchoolMembership.objects.create(user=user, school=self.a)
        self.client.force_login(user)
        response = self.client.post(ADD, {'first_name': 'X'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
        self.assertEqual(Student.objects.count(), 1)
