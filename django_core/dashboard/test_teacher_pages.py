"""Slice 2: the Subject Teacher enters grades and recommendations. Happy path, other class / school / teacher is 404,
wrong role 403, inactive account refused, and who can read the recommendations. Synthetic data only."""
import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import (
    AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, TeacherAssignment)
from students.access import visible_recommendations
from students.enrollment_sync import ensure_current_enrollment
from students.models import Grade, Recommendation, Student

User = get_user_model()


def make_user(name, group=None, **extra):
    user = User.objects.create_user(name, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class Base(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        self.b = School.objects.create(name='B', code='b')
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23),
                                        end_date=date(2026, 6, 21), is_current=True)
        mk = lambda school, title: SchoolClass.objects.create(  # noqa: E731
            school=school, title=title, academic_year='1404-1405', grade=7)
        self.class_a, self.class_a2, self.class_b = mk(self.a, '7-A'), mk(self.a, '7-A2'), mk(self.b, '7-B')
        self.parent = make_user('parent', 'Parent')
        self.s1 = self.student('S1', self.class_a, parent_user=self.parent)
        self.s2 = self.student('S2', self.class_a2)
        self.sb = self.student('SB', self.class_b)
        self.teacher = make_user('teacher', 'Teacher')
        self.teacher2 = make_user('teacher2', 'Teacher')
        self.assign = TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.class_a, subject='math')
        self.assign2 = TeacherAssignment.objects.create(teacher=self.teacher2, school_class=self.class_a2, subject='math')
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.other_admin = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.other_admin, school=self.b)
        self.lead = make_user('lead', 'GradeLead')
        GradeLeadAssignment.objects.create(user=self.lead, school=self.a, grade=7, academic_year='1404-1405')
        self.client.force_login(self.teacher)

    def student(self, name, klass, **extra):
        student = Student.objects.create(first_name=name, last_name='X', national_id=f'96{Student.objects.count():08d}',
                                         grade=7, phone_number='1', school=klass.school, school_class=klass, **extra)
        ensure_current_enrollment(student, source='manual')
        return student

    def grades_url(self, assign=None):
        return reverse('dashboard:teacher_grades', args=[(assign or self.assign).pk])


class GradeTests(Base):
    def test_pages_render_and_show_only_the_own_class(self):
        self.assertContains(self.client.get(reverse('dashboard:teacher_home')), '7-A')
        body = self.client.get(self.grades_url()).content.decode()
        body = re.sub(r'value="[A-Za-z0-9]{32,}"', 'value=""', body)    # a random CSRF token can contain 'S2' or 'SB' by chance
        self.assertIn('S1', body)
        self.assertNotIn('S2', body)
        self.assertNotIn('SB', body)

    def test_entering_grades_saves_the_assigned_subject_for_the_class_students(self):
        resp = self.client.post(self.grades_url(), {
            'exam_type': 'quiz', 'date': '2026-01-10', f'score_{self.s1.pk}': '17.5',
            f'score_{self.s2.pk}': '19', f'score_{self.sb.pk}': '19'})   # students of other classes/schools are ignored
        self.assertEqual(resp.status_code, 302)
        grade = Grade.objects.get()
        self.assertEqual((grade.student_id, grade.subject, grade.score, grade.exam_type), (self.s1.pk, 'math', 17.5, 'quiz'))
        self.assertIsNotNone(grade.enrollment_id)

    def test_invalid_scores_save_nothing(self):
        for bad in ('25', '-1', 'abc'):
            resp = self.client.post(self.grades_url(), {'exam_type': 'quiz', 'date': '2026-01-10',
                                                        f'score_{self.s1.pk}': bad})
            self.assertEqual(resp.status_code, 200, bad)
        self.assertFalse(Grade.objects.exists())

    def test_an_empty_sheet_or_missing_date_saves_nothing(self):
        self.assertEqual(self.client.post(self.grades_url(), {'exam_type': 'quiz', 'date': '2026-01-10'}).status_code, 200)
        self.assertEqual(self.client.post(self.grades_url(), {'exam_type': 'quiz', f'score_{self.s1.pk}': '10'}).status_code, 200)
        self.assertFalse(Grade.objects.exists())

    def test_delete_own_grade_only(self):
        mine = Grade.objects.create(student=self.s1, subject='math', exam_type='quiz', score=10, date='2026-01-01')
        other_subject = Grade.objects.create(student=self.s1, subject='physics', exam_type='quiz', score=10, date='2026-01-01')
        other_class = Grade.objects.create(student=self.s2, subject='math', exam_type='quiz', score=10, date='2026-01-01')
        for grade in (other_subject, other_class):
            url = reverse('dashboard:teacher_grade_delete', args=[self.assign.pk, grade.pk])
            self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(Grade.objects.count(), 3)
        self.client.post(reverse('dashboard:teacher_grade_delete', args=[self.assign.pk, mine.pk]))
        self.assertFalse(Grade.objects.filter(pk=mine.pk).exists())


class RecommendationTests(Base):
    def add(self, text='Needs more practice'):
        return self.client.post(reverse('dashboard:teacher_student', args=[self.assign.pk, self.s1.pk]), {'text': text, 'visibility': 'staff'})

    def test_teacher_adds_a_recommendation_and_sees_it(self):
        self.assertEqual(self.add().status_code, 302)
        rec = Recommendation.objects.get()
        self.assertEqual((rec.student_id, rec.author_id, rec.subject), (self.s1.pk, self.teacher.pk, 'math'))
        self.assertContains(self.client.get(reverse('dashboard:teacher_student', args=[self.assign.pk, self.s1.pk])),
                            'Needs more practice')

    def test_who_can_read_it(self):
        self.add()
        # staff-only by default (owner correction A4): the parent does not read it
        expected = {self.teacher: 1, self.admin: 1, self.lead: 1, self.parent: 0, self.teacher2: 0, self.other_admin: 0}
        for user, count in expected.items():
            self.assertEqual(visible_recommendations(user).count(), count, user.username)
        for user, status in ((self.admin, 200), (self.parent, 200), (self.lead, 200), (self.other_admin, 404)):
            self.client.force_login(user)
            resp = self.client.get(reverse('dashboard:student_detail', args=[self.s1.pk]))
            self.assertEqual(resp.status_code, status, user.username)
            if status == 200 and user != self.parent:
                self.assertContains(resp, 'Needs more practice')
            if user == self.parent:
                self.assertNotContains(resp, 'Needs more practice')

    def test_an_inactive_or_unrelated_account_reads_none(self):
        self.add()
        User.objects.filter(pk=self.parent.pk).update(is_active=False)
        self.assertEqual(visible_recommendations(User.objects.get(pk=self.parent.pk)).count(), 0)
        self.assertEqual(visible_recommendations(make_user('nobody')).count(), 0)


class AccessTests(Base):
    PAGES = lambda self: [  # noqa: E731
        ('get', reverse('dashboard:teacher_home')), ('get', self.grades_url()), ('post', self.grades_url()),
        ('get', reverse('dashboard:teacher_student', args=[self.assign.pk, self.s1.pk])),
        ('post', reverse('dashboard:teacher_student', args=[self.assign.pk, self.s1.pk]))]

    def test_other_teachers_assignment_and_foreign_students_are_404(self):
        self.client.force_login(self.teacher2)
        for method, url in self.PAGES()[1:]:
            self.assertEqual(getattr(self.client, method)(url).status_code, 404, (method, url))
        self.client.force_login(self.teacher)
        for student in (self.s2, self.sb):   # a student of another class / school through the own assignment
            url = reverse('dashboard:teacher_student', args=[self.assign.pk, student.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {'text': 'x'}).status_code, 404)
        self.assertFalse(Recommendation.objects.exists())

    def test_other_roles_get_403(self):
        for user in (self.parent, self.admin, self.lead, make_user('root', is_superuser=True)):
            self.client.force_login(user)
            for method, url in self.PAGES():
                self.assertEqual(getattr(self.client, method)(url).status_code, 403, (user.username, url))

    def test_anonymous_inactive_and_staff_accounts(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard:teacher_home')).status_code, 302)
        User.objects.filter(pk=self.teacher.pk).update(is_active=False)
        self.client.force_login(User.objects.get(pk=self.teacher.pk))
        self.assertEqual(self.client.get(self.grades_url()).status_code, 302)       # session refused
        User.objects.filter(pk=self.teacher.pk).update(is_active=True, is_staff=True)
        self.client.force_login(User.objects.get(pk=self.teacher.pk))
        self.assertEqual(self.client.get(self.grades_url()).status_code, 404)       # staff accounts hold no teacher grant

    def test_an_inactive_class_closes_the_page(self):
        SchoolClass.objects.filter(pk=self.class_a.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.grades_url()).status_code, 404)
