"""S2b commit 3: the Django admin save assigns the school through resolve_student_school."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from schools.models import School, SchoolClass, SchoolMembership

from .models import Student

User = get_user_model()
INLINES = {'grades-TOTAL_FORMS': 0, 'grades-INITIAL_FORMS': 0, 'grades-MIN_NUM_FORMS': 0, 'grades-MAX_NUM_FORMS': 1000,
           'attendances-TOTAL_FORMS': 0, 'attendances-INITIAL_FORMS': 0, 'attendances-MIN_NUM_FORMS': 0,
           'attendances-MAX_NUM_FORMS': 1000}
ADD = '/admin/students/student/add/'


class StudentAdminSchoolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.b = School.objects.create(name='B', code='b')
        cls.class_a = SchoolClass.objects.create(school=cls.a, title='7-A', academic_year='1404', grade=7)
        cls.class_b = SchoolClass.objects.create(school=cls.b, title='7-B', academic_year='1404', grade=7)
        cls.group = Group.objects.get_or_create(name='SchoolAdmin')[0]

    n = 0

    def staff(self, username, *schools):
        user = User.objects.create_user(username, password='x', is_staff=True)
        user.groups.add(self.group)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='students',
                                                             content_type__model__in=('student', 'grade', 'attendance')))
        for school in schools:
            SchoolMembership.objects.create(user=user, school=school)
        return user

    def data(self, **extra):
        StudentAdminSchoolTests.n += 1
        return {'first_name': 'N', 'last_name': 'T', 'national_id': f'{9200000000 + self.n}', 'grade': 7,
                'phone_number': '0', 'class_name': '', **INLINES, **extra}

    def add(self, user, **extra):
        self.client.force_login(user)
        return self.client.post(ADD, self.data(**extra))

    def test_the_form_offers_the_target_school_field_from_the_users_schools(self):
        self.client.force_login(self.staff('one', self.a))
        resp = self.client.get(ADD)
        self.assertEqual(resp.status_code, 200)
        field = resp.context['adminform'].form.fields['target_school']
        self.assertEqual(list(field.queryset), [self.a])

    def test_one_membership_implies_two_require_a_target(self):
        self.assertEqual(self.add(self.staff('one', self.a)).status_code, 302)
        self.assertEqual(Student.objects.get().school_id, self.a.pk)
        two = self.staff('two', self.a, self.b)
        self.assertEqual(self.add(two).status_code, 200)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(self.add(two, target_school=self.b.pk).status_code, 302)
        self.assertEqual(Student.objects.order_by('-pk').first().school_id, self.b.pk)

    def test_foreign_target_foreign_class_and_disagreement_are_rejected(self):
        one = self.staff('one', self.a)
        self.assertEqual(self.add(one, target_school=self.b.pk).status_code, 200)
        self.assertEqual(self.add(one, school_class=self.class_b.pk).status_code, 200)
        two = self.staff('two', self.a, self.b)
        self.assertEqual(self.add(two, school_class=self.class_a.pk, target_school=self.b.pk).status_code, 200)
        self.assertEqual(Student.objects.count(), 0)

    def test_no_membership_is_rejected(self):
        self.assertEqual(self.add(self.staff('none')).status_code, 200)
        self.assertEqual(Student.objects.count(), 0)

    def test_superuser_must_name_a_school(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertEqual(self.add(root).status_code, 200)
        self.assertEqual(self.add(root, target_school=self.b.pk).status_code, 302)
        self.assertEqual(Student.objects.get().school_id, self.b.pk)

    def test_a_class_decides_the_school(self):
        self.assertEqual(self.add(self.staff('two', self.a, self.b), school_class=self.class_b.pk).status_code, 302)
        self.assertEqual(Student.objects.get().school_id, self.b.pk)

    def test_an_existing_students_school_cannot_be_changed(self):
        student = Student.objects.create(first_name='S', last_name='A', national_id='9200009999', grade=7,
                                         phone_number='0', school_class=self.class_a)
        two = self.staff('two', self.a, self.b)
        self.client.force_login(two)
        url = f'/admin/students/student/{student.pk}/change/'
        base = {**self.data(national_id='9200009999'), 'grades-INITIAL_FORMS': 0}
        for extra in ({'target_school': self.b.pk}, {'school_class': self.class_b.pk}):
            self.assertEqual(self.client.post(url, {**base, **extra}).status_code, 200, extra)
        student.refresh_from_db()
        self.assertEqual((student.school_id, student.school_class_id), (self.a.pk, self.class_a.pk))
        self.assertEqual(self.client.post(url, {**base, 'school_class': self.class_a.pk}).status_code, 302)
