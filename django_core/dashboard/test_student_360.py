"""Slice 3: the Student 360 page. Happy path per role, other school / other child / other grade is a 404, wrong role 403,
inactive refused. Synthetic data only."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import AuditEvent, AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, TeacherAssignment
from students.enrollment_sync import ensure_current_enrollment
from students.models import Attendance, Grade, Recommendation, Student

User = get_user_model()


def make_user(name, group=None, **extra):
    user = User.objects.create_user(name, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class Base(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='School A', code='a')
        self.b = School.objects.create(name='School B', code='b')
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23),
                                        end_date=date(2026, 6, 21), is_current=True)
        mk = lambda school, title, grade: SchoolClass.objects.create(  # noqa: E731
            school=school, title=title, academic_year='1404-1405', grade=grade)
        self.c7, self.c8, self.cb = mk(self.a, '7-A', 7), mk(self.a, '8-A', 8), mk(self.b, '7-B', 7)
        self.parent = make_user('parent', 'Parent')
        self.other_parent = make_user('parent2', 'Parent')
        self.child = self.student('Child', self.c7, 7, parent_user=self.parent)
        self.grade8 = self.student('Eight', self.c8, 8, parent_user=self.other_parent)
        self.foreign = self.student('Foreign', self.cb, 7)
        Grade.objects.create(student=self.child, enrollment=self.child.enrollments.get(), subject='math',
                             exam_type='quiz', score=16, date='2026-01-01')
        Grade.objects.create(student=self.child, enrollment=self.child.enrollments.get(), subject='math',
                             exam_type='final', score=18, date='2026-01-20')
        Attendance.objects.create(student=self.child, date='2026-01-02', status='present')
        Attendance.objects.create(student=self.child, date='2026-01-03', status='absent')
        teacher = make_user('teacher', 'Teacher')
        TeacherAssignment.objects.create(teacher=teacher, school_class=self.c7, subject='math')
        Recommendation.objects.create(student=self.child, author=teacher, subject='math', text='Keep practising fractions',
                                      visible_to_student=True)
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_b, school=self.b)
        self.lead = make_user('lead', 'GradeLead')
        GradeLeadAssignment.objects.create(user=self.lead, school=self.a, grade=7, academic_year='1404-1405')
        self.teacher = teacher

    def student(self, name, klass, grade, **extra):
        student = Student.objects.create(first_name=name, last_name='X', national_id=f'97{Student.objects.count():08d}',
                                         grade=grade, phone_number='1', school=klass.school, school_class=klass, **extra)
        ensure_current_enrollment(student, source='manual')
        return student

    def url(self, student):
        return reverse('dashboard:student_360', args=[student.pk])

    def status(self, user, student):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return self.client.get(self.url(student)).status_code


class HappyPathTests(Base):
    def test_each_role_sees_the_page_of_its_student(self):
        for user in (self.admin, self.lead, self.parent):
            self.client.force_login(user)
            resp = self.client.get(self.url(self.child))
            self.assertEqual(resp.status_code, 200, user.username)
            body = resp.content.decode()
            self.assertNotIn(self.child.national_id, body)     # masked by default
            self.assertIn('******' + self.child.national_id[-4:], body)
            reveal = self.client.post(reverse('dashboard:reveal_national_id', args=[self.child.pk]))
            self.assertEqual(reveal.json()['national_id'], self.child.national_id)
            self.assertTrue(AuditEvent.objects.filter(action='national_id_reveal', user=user).exists())
            self.assertIn('1404-1405', body)                   # enrollment path / grades per year
            self.assertIn('17.0', body)                        # math average of 16 and 18
            self.assertIn('Keep practising fractions', body)   # the teacher's recommendation
            self.assertIn('50', body)                          # attendance: 1 of 2 days present

    def test_the_lists_link_to_the_page(self):
        for user in (self.admin, self.lead, self.parent):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse('dashboard:student_list')), self.url(self.child))

    def test_the_grade_lead_lands_on_the_dashboard_and_the_list_filters_by_grade(self):
        from dashboard.home import home_url_for
        self.assertEqual(home_url_for(self.lead), '/grade/')
        self.client.force_login(self.lead)
        body = self.client.get('/students/?grade=7').content.decode()
        self.assertIn('Child', body)
        self.assertNotIn('Eight', body)


class ScopeTests(Base):
    def test_other_school_child_and_grade_are_404(self):
        self.assertEqual(self.status(self.admin, self.foreign), 404)        # another school
        self.assertEqual(self.status(self.admin_b, self.child), 404)
        self.assertEqual(self.status(self.parent, self.grade8), 404)        # someone else's child
        self.assertEqual(self.status(self.parent, self.foreign), 404)
        self.assertEqual(self.status(self.lead, self.grade8), 404)          # another grade of the same school
        self.assertEqual(self.status(self.lead, self.foreign), 404)
        self.assertEqual(self.status(self.admin, self.grade8), 200)         # the admin sees the whole own school

    def test_wrong_roles_get_403(self):
        for user in (self.teacher, make_user('root', is_superuser=True), make_user('nobody')):
            self.assertEqual(self.status(user, self.child), 403, user.username)

    def test_anonymous_and_inactive_accounts_are_refused(self):
        self.assertEqual(self.status(None, self.child), 302)
        for user in (self.admin, self.lead, self.parent):
            User.objects.filter(pk=user.pk).update(is_active=False)
            self.assertEqual(self.status(User.objects.get(pk=user.pk), self.child), 302, user.username)   # session refused

    def test_the_page_does_not_leak_other_childrens_data(self):
        self.client.force_login(self.parent)
        body = self.client.get(self.url(self.child)).content.decode()
        for secret in ('Eight', 'Foreign', self.grade8.national_id, self.foreign.national_id):
            self.assertNotIn(secret, body)


class GradeDashboardTests(Base):
    """Owner correction A1: the Grade Lead dashboard shows only the own grade of the own school."""

    def setUp(self):
        super().setUp()
        self.bad = self.student('Weak', self.c7, 7)
        for score in (4, 6):
            Grade.objects.create(student=self.bad, enrollment=self.bad.enrollments.get(), subject='math',
                                 exam_type='quiz', score=score, date='2026-01-05')
        Grade.objects.create(student=self.grade8, enrollment=self.grade8.enrollments.get(), subject='math',
                             exam_type='quiz', score=2, date='2026-01-05')            # grade 8: must not appear
        Grade.objects.create(student=self.foreign, enrollment=self.foreign.enrollments.get(), subject='math',
                             exam_type='quiz', score=1, date='2026-01-05')            # other school: must not appear

    def test_counts_classes_and_attention_cover_only_the_own_grade(self):
        from dashboard.grade_dashboard import grade_overview
        o = grade_overview(self.lead)
        self.assertEqual(o['total'], 2)                                   # Child and Weak, not Eight, not Foreign
        self.assertEqual([c['name'] for c in o['classes']], ['7-A'])
        self.assertEqual([a['student'].pk for a in o['attention']], [self.bad.pk])
        self.assertEqual(sum(o['score_buckets']['values']), 4)             # 2 grades of Child + 2 of Weak

    def test_the_page_shows_no_other_grade_or_school(self):
        self.client.force_login(self.lead)
        resp = self.client.get(reverse('dashboard:grade_dashboard'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Weak', body)
        self.assertIn(reverse('dashboard:student_360', args=[self.bad.pk]), body)
        for secret in ('Eight', 'Foreign', '8-A', '7-B'):
            self.assertNotIn(secret, body)

    def test_wrong_roles_get_403_and_inactive_or_anonymous_are_refused(self):
        url = reverse('dashboard:grade_dashboard')
        for user in (self.admin, self.parent, self.teacher, make_user('root', is_superuser=True)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        User.objects.filter(pk=self.lead.pk).update(is_active=False)
        self.client.force_login(User.objects.get(pk=self.lead.pk))
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_a_grade_lead_without_assignment_sees_an_empty_dashboard(self):
        self.client.force_login(make_user('lead2', 'GradeLead'))
        resp = self.client.get(reverse('dashboard:grade_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Child', resp.content.decode())
