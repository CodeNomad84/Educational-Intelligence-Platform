"""Step 0 (cross-school write hole): classes and parents offered to a user are those of the user's own schools, in the API,
the dashboard form and the Django admin; the admin write permission refuses inactive accounts."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from dashboard.forms import StudentForm
from schools.models import School, SchoolClass, SchoolMembership
from students.models import Student
from students.permissions import IsAdminUser

User = get_user_model()


def make_user(name, group=None, **extra):
    user = User.objects.create_user(name, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class OwnSchoolChoicesTests(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        self.b = School.objects.create(name='B', code='b')
        self.class_a = SchoolClass.objects.create(school=self.a, title='7-A', academic_year='1404', grade=7)
        self.class_b = SchoolClass.objects.create(school=self.b, title='7-B', academic_year='1404', grade=7)
        self.admin = make_user('admin-a', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.parent_a = make_user('parent-a', 'Parent')
        self.parent_b = make_user('parent-b', 'Parent')
        Student.objects.create(first_name='K', last_name='A', national_id='9500000001', grade=7, phone_number='1',
                               school=self.a, parent_user=self.parent_a)
        Student.objects.create(first_name='K', last_name='B', national_id='9500000002', grade=7, phone_number='1',
                               school=self.b, parent_user=self.parent_b)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def body(self, **extra):
        return {'first_name': 'N', 'last_name': 'S', 'national_id': '9500000009', 'grade': 7, 'phone_number': '1', **extra}

    # --- API
    def test_api_accepts_own_class_and_own_parent(self):
        resp = self.api.post('/api/students/', self.body(school_class=self.class_a.pk, parent_user=self.parent_a.pk),
                             format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_api_refuses_a_class_of_another_school_like_a_missing_one(self):
        foreign = self.api.post('/api/students/', self.body(school_class=self.class_b.pk), format='json')
        missing = self.api.post('/api/students/', self.body(school_class=999999), format='json')
        self.assertEqual((foreign.status_code, missing.status_code), (400, 400))
        self.assertEqual(foreign.json(), missing.json())
        self.assertFalse(Student.objects.filter(national_id='9500000009').exists())

    def test_api_refuses_a_parent_of_another_school(self):
        resp = self.api.post('/api/students/', self.body(parent_user=self.parent_b.pk), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_api_update_cannot_move_a_student_to_another_schools_class(self):
        student = Student.objects.get(national_id='9500000001')
        resp = self.api.patch(f'/api/students/{student.pk}/', {'school_class': self.class_b.pk}, format='json')
        self.assertEqual(resp.status_code, 400)
        student.refresh_from_db()
        self.assertEqual((student.school_id, student.school_class_id), (self.a.pk, None))

    # --- dashboard form
    def test_dashboard_form_offers_only_own_classes_and_parents(self):
        form = StudentForm(user=self.admin)
        self.assertEqual(list(form.fields['school_class'].queryset), [self.class_a])
        self.assertEqual(list(form.fields['parent_user'].queryset), [self.parent_a])

    def test_dashboard_form_rejects_a_foreign_class(self):
        data = {'first_name': 'N', 'last_name': 'S', 'national_id': '9500000009', 'grade': 7, 'phone_number': '1',
                'school_class': self.class_b.pk}
        form = StudentForm(data, user=self.admin)
        self.assertFalse(form.is_valid())
        self.assertIn('school_class', form.errors)

    # --- write permission
    def test_admin_permission_refuses_inactive_accounts_and_other_roles(self):
        def allowed(user):
            request = RequestFactory().post('/api/students/')
            request.user = user
            return IsAdminUser().has_permission(request, None)
        self.assertTrue(allowed(self.admin))
        self.assertFalse(allowed(make_user('off-admin', 'SchoolAdmin', is_active=False)))
        self.assertFalse(allowed(make_user('off-root', is_superuser=True, is_active=False)))
        self.assertFalse(allowed(make_user('teacher', 'Teacher')))
        self.assertFalse(allowed(self.parent_a))
