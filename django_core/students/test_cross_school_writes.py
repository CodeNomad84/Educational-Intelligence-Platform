"""S4 read-through (docs/changes/0019): every WRITE path reachable from a SchoolAdmin or a Subject Teacher of school A is refused
for objects of school B, and nothing changes. Two schools, one admin each. The only data API is /api/students/ (list, retrieve,
create, update, partial_update, destroy, import, features, predict); the other writes are dashboard pages. Synthetic data only."""
import io
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from dashboard.test_counselor import Base, make_user
from schools.models import (AcademicYear, AccountProfile, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff,
                            TeacherAssignment)
from schools.module_grants import grant
from students.models import Grade, Student

User = get_user_model()
REFUSED = (403, 404)


class CrossSchoolWrites(Base):
    def setUp(self):
        super().setUp()
        grant(self.a)
        grant(self.b)
        self.year_b = AcademicYear.objects.get(school=self.b)
        self.teacher_a = make_user('ta', 'Teacher', self.a)
        self.assign_a = TeacherAssignment.objects.create(teacher=self.teacher_a, school_class=self.c7, subject='math')
        self.teacher_b = make_user('tb', 'Teacher', self.b)
        self.assign_b = TeacherAssignment.objects.create(teacher=self.teacher_b, school_class=self.cb, subject='math')
        self.lead_b = make_user('lead-b', 'GradeLead', self.b)
        self.lead_assign_b = GradeLeadAssignment.objects.create(user=self.lead_b, school=self.b, grade=7, academic_year='1404-1405')
        self.grade_b = Grade.objects.create(student=self.sb, subject='math', exam_type='quiz', score=11, date=date(2026, 1, 1))
        self.foreign_parent = make_user('par-b', 'Parent', self.b)
        self.client.force_login(self.admin)
        self.snapshot = self.state()

    def state(self):
        return {
            'students': sorted(Student.objects.values_list('pk', 'first_name', 'grade', 'school_id', 'school_class_id', 'parent_user_id')),
            'grades': sorted(Grade.objects.values_list('pk', 'score')),
            'users': sorted(User.objects.values_list('pk', 'username', 'is_active')),
            'years': sorted(AcademicYear.objects.values_list('pk', 'is_current')),
            'classes': sorted(SchoolClass.objects.values_list('pk', 'title', 'is_active')),
            'assignments': sorted(TeacherAssignment.objects.values_list('pk')) + sorted(GradeLeadAssignment.objects.values_list('pk')),
            'groups': sorted(User.groups.through.objects.values_list('user_id', 'group_id')),
            'profiles': sorted(AccountProfile.objects.values_list('user_id', 'must_change_password')),
        }

    def refused(self, response, label):
        self.assertIn(response.status_code, REFUSED + (400,), label)
        self.assertEqual(self.state(), self.snapshot, f'{label}: state changed')


class ApiTests(CrossSchoolWrites):
    def test_update_patch_delete_of_a_foreign_student_are_404_and_change_nothing(self):
        url = f'/api/students/{self.sb.pk}/'
        body = {'first_name': 'Hacked', 'last_name': 'X', 'national_id': self.sb.national_id, 'grade': 7, 'phone_number': '1'}
        for label, response in (('put', self.client.put(url, body, content_type='application/json')),
                                ('patch', self.client.patch(url, {'first_name': 'Hacked'}, content_type='application/json')),
                                ('delete', self.client.delete(url)),
                                ('get', self.client.get(url)),
                                ('features', self.client.get(url + 'features/')),
                                ('predict', self.client.get(url + 'predict/'))):
            self.assertEqual(response.status_code, 404, label)
        self.assertEqual(self.state(), self.snapshot)

    def test_create_with_a_foreign_class_or_target_school_is_refused(self):
        base = {'first_name': 'New', 'last_name': 'X', 'national_id': '9400000001', 'grade': 7, 'phone_number': '1'}
        self.refused(self.client.post('/api/students/', {**base, 'school_class': self.cb.pk}, content_type='application/json'), 'foreign class')
        self.refused(self.client.post('/api/students/', {**base, 'target_school': self.b.pk}, content_type='application/json'), 'foreign school')

    def test_moving_an_own_student_into_a_foreign_class_is_refused(self):
        response = self.client.patch(f'/api/students/{self.s7.pk}/', {'school_class': self.cb.pk}, content_type='application/json')
        self.refused(response, 'move class')
        self.s7.refresh_from_db()
        self.assertEqual((self.s7.school_id, self.s7.school_class_id), (self.a.pk, self.c7.pk))

    def test_assigning_a_foreign_parent_is_refused(self):
        self.refused(self.client.patch(f'/api/students/{self.s7.pk}/', {'parent_user': self.foreign_parent.pk}, content_type='application/json'),
                     'foreign parent')

    def test_import_into_a_foreign_target_school_is_refused(self):
        csv = 'national_id,first_name,last_name,grade,phone_number\n9400000002,Imp,Orted,7,1\n'
        upload = SimpleUploadedFile('s.csv', csv.encode(), content_type='text/csv')
        response = self.client.post('/api/students/import/', {'file': upload, 'target_school': self.b.pk})
        self.refused(response, 'import to B')

    def test_import_cannot_overwrite_a_foreign_student_by_national_id(self):
        csv = f'national_id,first_name,last_name,grade,phone_number\n{self.sb.national_id},Over,Written,9,1\n'
        upload = SimpleUploadedFile('s.csv', csv.encode(), content_type='text/csv')
        self.client.post('/api/students/import/', {'file': upload, 'target_school': self.a.pk})
        self.sb.refresh_from_db()
        self.assertEqual((self.sb.first_name, self.sb.grade, self.sb.school_id), ('Bee', 7, self.b.pk))

    def test_non_admin_roles_cannot_write_at_all(self):
        for user in (self.lead, self.counselor, self.parent, self.teacher_a):
            self.client.force_login(user)
            for label, response in (('post', self.client.post('/api/students/', {'first_name': 'x'}, content_type='application/json')),
                                    ('patch', self.client.patch(f'/api/students/{self.s7.pk}/', {'first_name': 'x'}, content_type='application/json')),
                                    ('delete', self.client.delete(f'/api/students/{self.s7.pk}/'))):
                self.assertEqual(response.status_code, 403, (user.username, label))
        self.assertEqual(self.state(), self.snapshot)


class DashboardAdminTests(CrossSchoolWrites):
    def test_student_pages_and_account_creation(self):
        for label, response in (
                ('detail', self.client.get(reverse('dashboard:student_detail', args=[self.sb.pk]))),
                ('360', self.client.get(reverse('dashboard:student_360', args=[self.sb.pk]))),
                ('account', self.client.post(reverse('dashboard:student_account', args=[self.sb.pk]), {'username': 'x'})),
                ('refer', self.client.post(reverse('dashboard:student_refer', args=[self.sb.pk]), {'counselor': self.counselor.pk, 'reason': 'x'}))):
            self.refused(response, label)

    def test_student_add_with_a_foreign_class_creates_nothing(self):
        response = self.client.post(reverse('dashboard:student_add'), {
            'first_name': 'New', 'last_name': 'X', 'national_id': '9400000003', 'grade': 7, 'phone_number': '1', 'school_class': self.cb.pk})
        self.assertEqual(response.status_code, 200)                     # the form is shown again with an error
        self.assertEqual(self.state(), self.snapshot)

    def test_school_pages_refuse_objects_of_another_school(self):
        staff_b = SchoolStaff.objects.get(user=self.teacher_b)
        for label, response in (
                ('year current', self.client.post(reverse('dashboard:school_year_current', args=[self.year_b.pk]))),
                ('class edit', self.client.post(reverse('dashboard:school_class_edit', args=[self.cb.pk]), {'title': 'Hacked', 'grade': 7})),
                ('staff detail', self.client.get(reverse('dashboard:school_staff_detail', args=['teachers', self.teacher_b.pk]))),
                ('staff active', self.client.post(reverse('dashboard:school_staff_active', args=['teachers', self.teacher_b.pk]))),
                ('assignment delete', self.client.post(reverse('dashboard:school_assignment_delete',
                                                               args=['teachers', self.teacher_b.pk, self.assign_b.pk]))),
                ('lead assignment delete', self.client.post(reverse('dashboard:school_assignment_delete',
                                                                    args=['gradeleads', self.lead_b.pk, self.lead_assign_b.pk]))),
                ('reset', self.client.post(reverse('dashboard:school_reset', args=[self.teacher_b.pk]))),
                ('roles', self.client.post(reverse('dashboard:school_staff_roles_save', args=[self.teacher_b.pk]), {'teacher': 'on', 'counselor': 'on'}))):
            self.refused(response, label)
        self.assertTrue(SchoolStaff.objects.filter(pk=staff_b.pk).exists())

    def test_the_other_admin_is_equally_refused_on_school_a(self):
        self.client.force_login(self.admin_b)
        before = self.state()
        for response in (self.client.patch(f'/api/students/{self.s7.pk}/', {'first_name': 'x'}, content_type='application/json'),
                         self.client.delete(f'/api/students/{self.s7.pk}/'),
                         self.client.post(reverse('dashboard:school_year_current', args=[AcademicYear.objects.get(school=self.a).pk])),
                         self.client.post(reverse('dashboard:school_reset', args=[self.teacher_a.pk]))):
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.state(), before)


class DashboardTeacherTests(CrossSchoolWrites):
    def test_a_teacher_cannot_reach_grades_or_students_of_another_school(self):
        self.client.force_login(self.teacher_a)
        grades = Grade.objects.count()
        for label, response in (
                ('foreign assignment sheet', self.client.get(reverse('dashboard:teacher_grades', args=[self.assign_b.pk]))),
                ('foreign assignment post', self.client.post(reverse('dashboard:teacher_grades', args=[self.assign_b.pk]), {'score': 20})),
                ('delete a foreign grade through the own sheet', self.client.post(
                    reverse('dashboard:teacher_grade_delete', args=[self.assign_a.pk, self.grade_b.pk]))),
                ('delete through the foreign sheet', self.client.post(
                    reverse('dashboard:teacher_grade_delete', args=[self.assign_b.pk, self.grade_b.pk]))),
                ('foreign student page', self.client.get(reverse('dashboard:teacher_student', args=[self.assign_a.pk, self.sb.pk])))):
            self.assertEqual(response.status_code, 404, label)
        self.assertEqual(Grade.objects.count(), grades)
        self.assertEqual(Grade.objects.get(pk=self.grade_b.pk).score, 11)
