"""S2b commit 2: the API (StudentSerializer) and the dashboard form assign a school through resolve_student_school."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import School, SchoolClass, SchoolMembership

from .models import Student

User = get_user_model()
GENERIC = 'This school is not available to your account.'


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.b = School.objects.create(name='B', code='b')
        cls.class_a = SchoolClass.objects.create(school=cls.a, title='7-A', academic_year='1404', grade=7)
        cls.class_b = SchoolClass.objects.create(school=cls.b, title='7-B', academic_year='1404', grade=7)
        cls.group = Group.objects.get_or_create(name='SchoolAdmin')[0]

    def admin(self, username, *schools):
        user = User.objects.create_user(username, password='x', is_staff=True)
        user.groups.add(self.group)
        for school in schools:
            SchoolMembership.objects.create(user=user, school=school)
        return user

    n = 0

    def payload(self, **extra):
        Base.n += 1
        return {'first_name': 'N', 'last_name': 'T', 'national_id': f'{9000000000 + Base.n}', 'grade': 7,
                'phone_number': '0', **extra}


class ApiCreateTests(Base):
    def post(self, user, **extra):
        self.client.force_login(user)
        return self.client.post('/api/students/', self.payload(**extra), content_type='application/json')

    def test_one_membership_implies_the_school(self):
        resp = self.post(self.admin('one', self.a))
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Student.objects.get(pk=resp.json()['id']).school_id, self.a.pk)
        self.assertNotIn('target_school', resp.json())

    def test_several_memberships_require_a_target(self):
        user = self.admin('two', self.a, self.b)
        resp = self.post(user)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('target_school', resp.json())
        resp = self.post(user, target_school=self.b.pk)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Student.objects.get(pk=resp.json()['id']).school_id, self.b.pk)

    def test_no_membership_is_rejected_even_with_a_class_or_target(self):
        user = self.admin('none')
        for extra in ({}, {'school_class': self.class_a.pk}, {'target_school': self.a.pk}):
            with self.subTest(extra=extra):
                self.assertEqual(self.post(user, **extra).status_code, 400)
        self.assertFalse(Student.objects.filter(national_id__startswith='9').exists())

    def test_foreign_target_and_foreign_class_are_rejected_with_one_generic_message(self):
        user = self.admin('one', self.a)
        messages = set()
        for extra in ({'target_school': self.b.pk}, {'target_school': 999999}, {'school_class': self.class_b.pk}):
            resp = self.post(user, **extra)
            self.assertEqual(resp.status_code, 400, extra)
            messages.add(str(sorted(v[0] for v in resp.json().values())))   # the field may differ, the message may not
        self.assertEqual(len(messages), 1)  # an existing school, a missing one and a foreign class: identical answer
        for text in messages:
            self.assertIn(GENERIC, text)
        self.assertFalse(Student.objects.filter(national_id__startswith='9').exists())

    def test_class_and_target_that_disagree_are_rejected(self):
        resp = self.post(self.admin('two', self.a, self.b), school_class=self.class_a.pk, target_school=self.b.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('school_class', resp.json())

    def test_a_class_decides_the_school(self):
        resp = self.post(self.admin('two', self.a, self.b), school_class=self.class_b.pk)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Student.objects.get(pk=resp.json()['id']).school_id, self.b.pk)

    def test_superuser_must_name_a_school(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertEqual(self.post(root).status_code, 400)
        resp = self.post(root, target_school=self.b.pk)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Student.objects.get(pk=resp.json()['id']).school_id, self.b.pk)

    def test_garbage_targets_are_validation_errors_not_server_errors(self):
        user = self.admin('two', self.a, self.b)
        for bad in ('abc', True, 1.5, [1], {'a': 1}, '1e999'):
            with self.subTest(bad=bad):
                self.assertEqual(self.post(user, target_school=bad).status_code, 400)
        self.client.force_login(user)
        raw = '{"first_name":"N","last_name":"T","national_id":"9099999999","grade":7,"phone_number":"0","target_school":1e999}'
        self.assertEqual(self.client.post('/api/students/', raw, content_type='application/json').status_code, 400)

    def test_platform_admin_cannot_create(self):
        user = self.admin('dual', self.a)
        user.groups.add(Group.objects.get_or_create(name='PlatformAdmin')[0])
        self.assertEqual(self.post(user).status_code, 400)


class ApiUpdateTests(Base):
    def setUp(self):
        self.student_a = Student.objects.create(first_name='S', last_name='A', national_id='9100000001', grade=7,
                                                phone_number='0', school_class=self.class_a)
        self.student_b = Student.objects.create(first_name='S', last_name='B', national_id='9100000002', grade=7,
                                                phone_number='0', school_class=self.class_b)

    def patch(self, user, student, payload):
        self.client.force_login(user)
        return self.client.patch(f'/api/students/{student.pk}/', payload, content_type='application/json')

    def test_school_of_an_existing_student_cannot_change(self):
        user = self.admin('two', self.a, self.b)
        for payload in ({'target_school': self.b.pk}, {'school_class': self.class_b.pk}):
            with self.subTest(payload=payload):
                self.assertEqual(self.patch(user, self.student_a, payload).status_code, 400)
        self.student_a.refresh_from_db()
        self.assertEqual((self.student_a.school_id, self.student_a.school_class_id), (self.a.pk, self.class_a.pk))

    def test_an_edit_that_leaves_the_school_alone_works_with_several_memberships(self):
        user = self.admin('two', self.a, self.b)
        resp = self.patch(user, self.student_a, {'first_name': 'Renamed'})
        self.assertEqual(resp.status_code, 200, resp.content)
        resp = self.patch(user, self.student_a, {'school_class': None})  # unlinking the class keeps the school
        self.assertEqual(resp.status_code, 200, resp.content)
        self.student_a.refresh_from_db()
        self.assertEqual((self.student_a.school_id, self.student_a.school_class_id), (self.a.pk, None))

    def test_admin_of_one_school_cannot_edit_a_student_of_another(self):
        # S3: the other school's student is not even visible (404), so there is nothing to edit
        self.assertEqual(self.patch(self.admin('one', self.a), self.student_b, {'first_name': 'X'}).status_code, 404)
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.first_name, 'S')


class DashboardFormTests(Base):
    def setUp(self):
        self.url = reverse('dashboard:student_add')

    def form_post(self, user, **extra):
        self.client.force_login(user)
        return self.client.post(self.url, {**self.payload(), **extra})

    def test_target_school_choices_are_the_users_schools_only(self):
        self.client.force_login(self.admin('one', self.a))
        field = self.client.get(self.url).context['form'].fields['target_school']
        self.assertEqual(list(field.queryset), [self.a])

    def test_implied_required_and_explicit(self):
        resp = self.form_post(self.admin('one', self.a))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Student.objects.order_by('-pk').first().school_id, self.a.pk)
        two = self.admin('two', self.a, self.b)
        self.assertEqual(self.form_post(two).status_code, 200)  # re-rendered with the error
        self.assertEqual(self.form_post(two, target_school=self.b.pk).status_code, 302)
        self.assertEqual(Student.objects.order_by('-pk').first().school_id, self.b.pk)

    def test_foreign_or_unknown_target_is_rejected(self):
        user = self.admin('one', self.a)
        before = Student.objects.count()
        for pk in (self.b.pk, 999999):
            self.assertEqual(self.form_post(user, target_school=pk).status_code, 200)
        self.assertEqual(Student.objects.count(), before)

    def test_foreign_class_and_class_target_disagreement_are_rejected(self):
        before = Student.objects.count()
        self.assertEqual(self.form_post(self.admin('one', self.a), school_class=self.class_b.pk).status_code, 200)
        two = self.admin('two', self.a, self.b)
        self.assertEqual(self.form_post(two, school_class=self.class_a.pk, target_school=self.b.pk).status_code, 200)
        self.assertEqual(Student.objects.count(), before)

    def test_no_membership_and_missing_user_are_rejected(self):
        before = Student.objects.count()
        self.assertEqual(self.form_post(self.admin('none')).status_code, 200)
        self.assertEqual(Student.objects.count(), before)
        from dashboard.forms import StudentForm
        form = StudentForm({**self.payload()})  # no user: fail closed
        self.assertFalse(form.is_valid())

    def test_class_decides_the_school_in_the_form(self):
        two = self.admin('two', self.a, self.b)
        self.assertEqual(self.form_post(two, school_class=self.class_b.pk).status_code, 302)
        self.assertEqual(Student.objects.order_by('-pk').first().school_id, self.b.pk)
