"""S6 requirement 1 (changes/0010): NOTHING outside ``backfill_student_school`` can give an existing school-less student
a school: API PATCH, Django admin edit, live import, dashboard form and ``Student.save()`` all refuse, and the
student stays exactly as it was. (The S2b behaviour "an edit adopts the actor's school" is retired here.)

A school-less row can only be built while ``Student.school`` is nullable; after the S6 migration these fixtures cannot
exist and the tests below are retired with it (marker ``S6-2:retire``).
"""
import json
import os
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from dashboard.forms import StudentForm
from schools.models import School, SchoolClass, SchoolMembership

from .models import SchoolAssignmentRefused, Student

User = get_user_model()
INLINES = {'grades-TOTAL_FORMS': 0, 'grades-INITIAL_FORMS': 0, 'grades-MIN_NUM_FORMS': 0, 'grades-MAX_NUM_FORMS': 1000,
           'attendances-TOTAL_FORMS': 0, 'attendances-INITIAL_FORMS': 0, 'attendances-MIN_NUM_FORMS': 0,
           'attendances-MAX_NUM_FORMS': 1000}
NID = '9300000001'


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.b = School.objects.create(name='B', code='b')
        cls.class_a = SchoolClass.objects.create(school=cls.a, title='7-A', academic_year='1404', grade=7)
        cls.group = Group.objects.get_or_create(name='SchoolAdmin')[0]

    def setUp(self):
        # S6-2:retire - a student without a school cannot exist once the column is NOT NULL
        self.legacy = Student.objects.create(first_name='Old', last_name='Row', national_id=NID, grade=7,
                                             phone_number='0', school=None)
        self.assertIsNone(self.legacy.school_id)

    def actor(self, username, *schools, superuser=False):
        if superuser:
            return User.objects.create_superuser(username, password='x')
        user = User.objects.create_user(username, password='x', is_staff=True)
        user.groups.add(self.group)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='students',
                                                             content_type__model__in=('student', 'grade', 'attendance')))
        for school in schools:
            SchoolMembership.objects.create(user=user, school=school)
        return user

    def assertUntouched(self):
        stored = Student.objects.get(pk=self.legacy.pk)
        self.assertEqual((stored.school_id, stored.school_class_id, stored.first_name, stored.class_name, stored.grade),
                         (None, None, 'Old', '', 7))


class ApiAndAdminTests(Base):
    def actors(self):
        return [self.actor('one', self.a), self.actor('two', self.a, self.b), self.actor('root', superuser=True)]

    def test_api_patch_never_gives_a_school_to_an_existing_school_less_student(self):
        payloads = ({'first_name': 'X'}, {'target_school': self.a.pk}, {'school_class': self.class_a.pk},
                    {'school_class': self.class_a.pk, 'target_school': self.a.pk}, {'school': self.a.pk})
        for user in self.actors():
            self.client.force_login(user)
            for payload in payloads:
                with self.subTest(user=user.username, payload=payload):
                    resp = self.client.patch(f'/api/students/{self.legacy.pk}/', payload, content_type='application/json')
                    self.assertNotIn(resp.status_code, (200, 201), resp.content)
                    self.assertUntouched()

    def test_django_admin_edit_never_gives_a_school_to_an_existing_school_less_student(self):
        url = f'/admin/students/student/{self.legacy.pk}/change/'
        base = {'first_name': 'Old', 'last_name': 'Row', 'national_id': NID, 'grade': 7, 'phone_number': '0',
                'class_name': '', **INLINES}
        for user in self.actors():
            self.client.force_login(user)
            for extra in ({}, {'target_school': self.a.pk}, {'school_class': self.class_a.pk}):
                with self.subTest(user=user.username, extra=extra):
                    resp = self.client.post(url, {**base, **extra})
                    if user.is_superuser:  # sees the row: the form is re-rendered with the error, nothing is saved
                        self.assertEqual(resp.status_code, 200)
                    self.assertUntouched()

    def test_live_import_never_gives_a_school_to_an_existing_school_less_student(self):
        for user in (self.actor('one', self.a), self.actor('two', self.a, self.b), self.actor('root', superuser=True)):
            self.client.force_login(user)
            csv = ('first_name,last_name,national_id,grade,class_name,phone_number,father_job,mother_job\n'
                   f'New,Name,{NID},9,7-A,09120000001,Dr,Nurse\n')
            resp = self.client.post('/api/students/import/', {
                'file': SimpleUploadedFile('s.csv', csv.encode('utf-8-sig'), content_type='text/csv'),
                'target_school': self.a.pk})
            with self.subTest(user=user.username):
                self.assertEqual(resp.json().get('updated', 0), 0, resp.content)
                self.assertUntouched()


class FormAndSaveTests(Base):
    def test_dashboard_form_refuses_an_existing_school_less_student(self):
        data = {'first_name': 'Old', 'last_name': 'Row', 'national_id': NID, 'grade': 7, 'phone_number': '0',
                'target_school': self.a.pk}
        for user in (self.actor('one', self.a), self.actor('root', superuser=True)):
            form = StudentForm(data, instance=Student.objects.get(pk=self.legacy.pk), user=user)
            with self.subTest(user=user.username):
                self.assertFalse(form.is_valid())
                self.assertUntouched()

    def test_save_refuses_a_class_link_or_a_school_for_an_existing_school_less_student(self):
        student = Student.objects.get(pk=self.legacy.pk)
        student.school_class = self.class_a
        with self.assertRaises(SchoolAssignmentRefused):
            student.save()
        student = Student.objects.get(pk=self.legacy.pk)
        student.school = self.a
        with self.assertRaises(SchoolAssignmentRefused):
            student.save()
        student = Student.objects.get(pk=self.legacy.pk)
        student.school_id = self.a.pk
        with self.assertRaises(SchoolAssignmentRefused):
            student.save(update_fields=['school'])
        self.assertUntouched()

    def test_save_still_allows_edits_that_assign_no_school(self):
        student = Student.objects.get(pk=self.legacy.pk)
        student.phone_number = '1'
        student.save()
        self.assertEqual(Student.objects.get(pk=self.legacy.pk).phone_number, '1')
        self.assertIsNone(Student.objects.get(pk=self.legacy.pk).school_id)

    def test_save_is_unchanged_for_new_students_and_students_that_have_a_school(self):
        fresh = Student.objects.create(first_name='N', last_name='S', national_id='9300000002', grade=7,
                                       phone_number='0', school_class=self.class_a)
        self.assertEqual(fresh.school_id, self.a.pk)
        fresh.school_class = None
        fresh.save()
        fresh.school_class = self.class_a
        fresh.save()
        self.assertEqual(Student.objects.get(pk=fresh.pk).school_id, self.a.pk)

    def test_a_deferred_school_field_is_not_guarded(self):
        student = Student.objects.only('first_name').get(pk=self.legacy.pk)
        student.first_name = 'Renamed'
        student.save(update_fields=['first_name'])
        self.assertEqual(Student.objects.get(pk=self.legacy.pk).first_name, 'Renamed')

    def test_a_deferred_school_field_does_not_disarm_the_guard(self):
        for load in (lambda: Student.objects.only('first_name').get(pk=self.legacy.pk),
                     lambda: Student.objects.defer('school').get(pk=self.legacy.pk)):
            student = load()
            student.school_id = self.a.pk
            with self.assertRaises(SchoolAssignmentRefused):
                student.save()
            student = load()
            student.school_class = self.class_a
            with self.assertRaises(SchoolAssignmentRefused):
                student.save()
        self.assertUntouched()

    def test_refreshing_other_fields_does_not_re_record_a_locally_assigned_school(self):
        student = Student.objects.get(pk=self.legacy.pk)
        student.school_id = self.a.pk
        student.refresh_from_db(fields=['first_name'])
        student.school_id = self.a.pk
        with self.assertRaises(SchoolAssignmentRefused):
            student.save()
        self.assertUntouched()

    def test_an_unsaved_instance_with_the_pk_of_a_school_less_row_cannot_overwrite_it(self):
        clone = Student(pk=self.legacy.pk, first_name='Old', last_name='Row', national_id=NID, grade=7,
                        phone_number='0', school=self.a)
        with self.assertRaises(SchoolAssignmentRefused):
            clone.save()
        self.assertUntouched()

    def test_an_instance_created_without_a_school_stays_guarded(self):
        fresh = Student.objects.create(first_name='N', last_name='S', national_id='9300000003', grade=7,
                                       phone_number='0', school=None)  # S6-2:retire
        fresh.school = self.a
        with self.assertRaises(SchoolAssignmentRefused):
            fresh.save()

    def test_a_refreshed_instance_sees_the_school_the_backfill_wrote(self):
        student = Student.objects.get(pk=self.legacy.pk)
        Student.objects.filter(pk=student.pk).update(school=self.a)
        student.refresh_from_db()
        student.first_name = 'After'
        student.save()  # the row has a school now: no refusal
        self.assertEqual(Student.objects.get(pk=self.legacy.pk).first_name, 'After')


class BackfillIsTheOnlyWayTests(Base):
    def test_backfill_student_school_still_populates_the_legacy_row(self):
        SchoolClass.objects.all().delete()
        School.objects.exclude(pk=School.objects.order_by('pk').first().pk).delete()  # the 'exactly one School' rule
        only = School.objects.get()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'batch.json')
            call_command('backfill_student_school', '--apply', '--batch-file', path, stdout=StringIO())
        self.assertEqual(Student.objects.get(pk=self.legacy.pk).school_id, only.pk)
