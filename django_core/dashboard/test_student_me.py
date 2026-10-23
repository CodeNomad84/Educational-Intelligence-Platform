"""Slice 4b: the Student role (own grades + feedback) and the DEMO STUB study assistant. Own data only, other roles 403,
inactive refused, no network use by the stub. Synthetic data only."""
import inspect
import socket
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import AcademicYear, School, SchoolClass, SchoolMembership, TeacherAssignment
from students import study_assistant
from students.access import visible_grades, visible_recommendations, visible_students
from students.enrollment_sync import ensure_current_enrollment
from students.models import Attendance, Grade, Recommendation, Student

User = get_user_model()
PASSWORD = 'Str0ng-demo-pass-77'


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
        self.ca, self.cb = mk(self.a, '7-A'), mk(self.b, '7-B')
        self.me = self.student('Me', self.ca)
        self.mate = self.student('Mate', self.ca)
        self.far = self.student('Far', self.cb)
        self.user = make_user('student-me', 'Student')
        Student.objects.filter(pk=self.me.pk).update(student_user=self.user)
        self.teacher = make_user('teacher', 'Teacher')
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.ca, subject='math')
        for student, scores in ((self.me, (10, 12)), (self.mate, (19, 20)), (self.far, (5, 6))):
            enrollment = student.enrollments.get()
            for i, score in enumerate(scores):
                Grade.objects.create(student=student, enrollment=enrollment, subject='math', exam_type='quiz',
                                     score=score, date=f'2026-01-0{i + 1}')
        Attendance.objects.create(student=self.me, date='2026-01-02', status='absent')
        Recommendation.objects.create(student=self.me, author=self.teacher, subject='math', text='Practise fractions daily')
        Recommendation.objects.create(student=self.mate, author=self.teacher, subject='math', text='Mate secret feedback')
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_b, school=self.b)

    def student(self, name, klass):
        student = Student.objects.create(first_name=name, last_name='X', national_id=f'99{Student.objects.count():08d}',
                                         grade=7, phone_number='1', school=klass.school, school_class=klass)
        ensure_current_enrollment(student, source='manual')
        return student


class OwnDataTests(Base):
    def test_a_student_sees_only_their_own_grades_and_feedback(self):
        self.client.force_login(self.user)
        body = self.client.get(reverse('dashboard:me_home')).content.decode()
        self.assertIn('Me', body)
        self.assertIn('11.0', body)                    # own math average (10, 12)
        self.assertIn('Practise fractions daily', body)
        for secret in ('Mate', 'Far', 'Mate secret feedback', '19.5', self.me.national_id):
            self.assertNotIn(secret, body)

    def test_the_access_layer_gives_the_student_no_more_than_their_own_record(self):
        self.assertEqual(set(visible_students(self.user).values_list('pk', flat=True)), {self.me.pk})
        self.assertEqual({g.student_id for g in visible_grades(self.user)}, {self.me.pk})
        self.assertEqual(visible_recommendations(self.user).count(), 1)
        self.assertEqual(visible_students(self.user).get().full_tier, False)     # not a full-detail grant

    def test_no_attendance_staff_pages_or_other_children(self):
        from students.access import visible_attendances
        self.assertEqual(visible_attendances(self.user).count(), 0)
        self.client.force_login(self.user)
        for url in (reverse('dashboard:student_list'), reverse('dashboard:student_detail', args=[self.me.pk]),
                    reverse('dashboard:student_360', args=[self.me.pk]), reverse('dashboard:teacher_home'),
                    reverse('dashboard:school_home'), reverse('dashboard:counselor_home')):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        api = self.client.get('/api/students/').json()
        rows = api['results'] if isinstance(api, dict) else api
        self.assertEqual([r['id'] for r in rows], [self.me.pk])
        self.assertNotIn('national_id', rows[0])
        self.assertEqual(self.client.get(f'/api/students/{self.mate.pk}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/students/{self.me.pk}/').status_code, 403)

    def test_login_lands_on_my_page(self):
        from dashboard.home import home_url_for
        self.assertEqual(home_url_for(self.user), '/me/')

    def test_other_roles_get_403_and_inactive_or_unlinked_are_refused(self):
        for user in (self.admin, self.teacher, make_user('parent', 'Parent'), make_user('root', is_superuser=True)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('dashboard:me_home')).status_code, 403, user.username)
            self.assertEqual(self.client.get(reverse('dashboard:me_assistant')).status_code, 403, user.username)
        self.client.force_login(make_user('unlinked', 'Student'))
        self.assertEqual(self.client.get(reverse('dashboard:me_home')).status_code, 404)    # a Student account without a student
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.client.force_login(User.objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(reverse('dashboard:me_home')).status_code, 302)
        self.assertEqual(visible_students(User.objects.get(pk=self.user.pk)).count(), 0)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard:me_home')).status_code, 302)


class AssistantStubTests(Base):
    def test_the_stub_answers_from_own_grades_and_is_labelled(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse('dashboard:me_assistant'))
        self.assertContains(page, 'DEMO STUB')
        resp = self.client.post(reverse('dashboard:me_assistant'), {'question': 'math'})
        self.assertContains(resp, '11.0')
        self.assertContains(resp, 'DEMO STUB')

    def test_empty_question_uses_the_weakest_subject_and_no_grades_is_handled(self):
        summary = study_assistant.subject_summary(Grade.objects.filter(student=self.me))
        self.assertIn('ریاضی', study_assistant.answer('', summary))
        self.assertIn('هنوز نمره‌ای', study_assistant.answer('x', {}))

    def test_the_stub_makes_no_network_call_and_stores_nothing(self):
        source = inspect.getsource(study_assistant)
        for forbidden in ('requests', 'urllib', 'http.client', 'socket', 'httpx', 'subprocess', 'objects.create', '.save('):
            self.assertNotIn(forbidden, source)
        self.assertTrue(study_assistant.DEMO_STUB)
        self.client.force_login(self.user)
        before = (Grade.objects.count(), Recommendation.objects.count())
        with mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('network used')), \
                mock.patch('requests.post', side_effect=AssertionError('network used')), \
                mock.patch('requests.get', side_effect=AssertionError('network used')):
            resp = self.client.post(reverse('dashboard:me_assistant'), {'question': 'math'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((Grade.objects.count(), Recommendation.objects.count()), before)


class AccountCreationTests(Base):
    def post(self, user, student, username='new-student'):
        self.client.force_login(user)
        return self.client.post(reverse('dashboard:student_account', args=[student.pk]),
                                {'username': username, 'password1': PASSWORD, 'password2': PASSWORD})

    def test_the_school_admin_creates_the_account_of_a_student(self):
        self.assertEqual(self.post(self.admin, self.mate).status_code, 302)
        account = User.objects.get(username='new-student')
        self.mate.refresh_from_db()
        self.assertEqual((self.mate.student_user_id, account.groups.get().name, account.is_staff), (account.pk, 'Student', False))
        self.client.logout()
        self.assertTrue(self.client.login(username='new-student', password=PASSWORD))
        self.assertContains(self.client.get(reverse('dashboard:me_home')), 'Mate')
        self.assertContains(self.client.get(reverse('dashboard:me_home')), '19.5')

    def test_scope_and_roles(self):
        self.assertEqual(self.post(self.admin_b, self.mate, 'x1').status_code, 404)             # another school
        self.assertEqual(self.post(self.admin, self.far, 'x2').status_code, 404)
        for user in (self.teacher, make_user('parent', 'Parent'), self.user, make_user('root', is_superuser=True)):
            self.assertEqual(self.post(user, self.mate, 'x3').status_code, 403, user.username)
        self.assertFalse(User.objects.filter(username__startswith='x').exists())

    def test_a_student_with_an_account_gets_no_second_one_and_weak_passwords_fail(self):
        self.post(self.admin, self.me, 'second')            # self.me already has an account
        self.assertFalse(User.objects.filter(username='second').exists())
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:student_account', args=[self.mate.pk]),
                         {'username': 'weak', 'password1': '123', 'password2': '123'})
        self.assertFalse(User.objects.filter(username='weak').exists())

    def test_the_360_page_shows_the_form_or_the_account(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard:student_360', args=[self.mate.pk])),
                            reverse('dashboard:student_account', args=[self.mate.pk]))
        self.assertContains(self.client.get(reverse('dashboard:student_360', args=[self.me.pk])), 'student-me')
