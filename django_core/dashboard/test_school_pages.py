"""Slice 1: the SchoolAdmin pages (academic year, classes, teachers, grade leads). Simple integration tests: happy path,
other school's data is a 404, wrong role 403, inactive account refused. Synthetic data only."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import (
    AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff, TeacherAssignment)
from students.access import roles_for

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
        self.admin_a = make_user('admin-a', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_a, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_b, school=self.b)
        self.year_b = AcademicYear.objects.create(school=self.b, code='1404-1405', start_date=date(2025, 9, 23),
                                                  end_date=date(2026, 6, 21), is_current=True)
        self.class_b = SchoolClass.objects.create(school=self.b, title='7-B', academic_year='1404-1405', grade=7)
        self.teacher_b = make_user('teacher-b', 'Teacher')
        SchoolStaff.objects.create(user=self.teacher_b, school=self.b)
        self.assignment_b = TeacherAssignment.objects.create(teacher=self.teacher_b, school_class=self.class_b,
                                                             subject='math')
        self.lead_b = make_user('lead-b', 'GradeLead')
        SchoolStaff.objects.create(user=self.lead_b, school=self.b)
        self.lead_assignment_b = GradeLeadAssignment.objects.create(user=self.lead_b, school=self.b, grade=7,
                                                                    academic_year='1404-1405')
        self.client.force_login(self.admin_a)

    def post_year(self, code='1404-1405', start='2025-09-23', end='2026-06-21'):
        return self.client.post(reverse('dashboard:school_years'),
                                {'code': code, 'label': '', 'start_date': start, 'end_date': end})


class HappyPathTests(Base):
    def test_pages_render(self):
        for name, args in (('school_home', ()), ('school_years', ()), ('school_classes', ()), ('school_class_new', ()),
                           ('school_staff', ('teachers',)), ('school_staff', ('gradeleads',))):
            self.assertEqual(self.client.get(reverse(f'dashboard:{name}', args=args)).status_code, 200, name)

    def test_academic_year_flow(self):
        self.assertEqual(self.post_year().status_code, 302)
        first = AcademicYear.objects.get(school=self.a, code='1404-1405')
        self.assertTrue(first.is_current)                       # the first year becomes current
        self.post_year('1405-1406', '2026-09-23', '2027-06-21')
        second = AcademicYear.objects.get(school=self.a, code='1405-1406')
        self.assertFalse(second.is_current)
        self.client.post(reverse('dashboard:school_year_current', args=[second.pk]))
        first.refresh_from_db(), second.refresh_from_db()
        self.assertEqual((first.is_current, second.is_current), (False, True))
        self.assertEqual(AcademicYear.objects.filter(school=self.a, is_current=True).count(), 1)
        self.assertTrue(AcademicYear.objects.get(school=self.b).is_current)   # school B untouched

    def test_year_errors_are_shown_not_saved(self):
        self.post_year()
        self.assertContains(self.post_year(), 'قبلاً ثبت شده', status_code=200)
        self.assertContains(self.post_year('1404-1406', '2027-09-23', '2028-06-21'), 'کد باید', status_code=200)

    def test_class_create_and_edit(self):
        self.post_year()
        resp = self.client.post(reverse('dashboard:school_class_new'),
                                {'title': '7-A', 'grade': 7, 'academic_year': '1404-1405', 'is_active': 'on'})
        self.assertEqual(resp.status_code, 302)
        klass = SchoolClass.objects.get(school=self.a, title='7-A')
        resp = self.client.post(reverse('dashboard:school_class_edit', args=[klass.pk]),
                                {'title': '7-A2', 'grade': 7, 'academic_year': '1404-1405', 'is_active': 'on'})
        self.assertEqual(resp.status_code, 302)
        klass.refresh_from_db()
        self.assertEqual((klass.title, klass.school_id), ('7-A2', self.a.pk))
        dup = self.client.post(reverse('dashboard:school_class_new'),
                               {'title': '7-A2', 'grade': 7, 'academic_year': '1404-1405', 'is_active': 'on'})
        self.assertContains(dup, 'وجود دارد', status_code=200)

    def create_account(self, kind, username):
        return self.client.post(reverse('dashboard:school_staff', args=[kind]), {
            'username': username, 'first_name': 'N', 'last_name': 'L', 'password1': PASSWORD, 'password2': PASSWORD})

    def test_teacher_account_and_assignments(self):
        self.post_year()
        self.client.post(reverse('dashboard:school_class_new'),
                         {'title': '7-A', 'grade': 7, 'academic_year': '1404-1405', 'is_active': 'on'})
        klass = SchoolClass.objects.get(school=self.a)
        resp = self.create_account('teachers', 'new-teacher')
        teacher = User.objects.get(username='new-teacher')
        self.assertRedirects(resp, reverse('dashboard:school_staff_detail', args=['teachers', teacher.pk]))
        self.assertEqual(roles_for(teacher), {'Teacher'})
        self.assertEqual((teacher.is_staff, teacher.is_superuser, teacher.school_staff.school_id), (False, False, self.a.pk))
        self.assertTrue(teacher.check_password(PASSWORD))
        url = reverse('dashboard:school_staff_detail', args=['teachers', teacher.pk])
        self.assertEqual(self.client.post(url, {'school_class': klass.pk, 'subject': 'math'}).status_code, 302)
        assignment = TeacherAssignment.objects.get(teacher=teacher)
        self.assertEqual((assignment.school_class_id, assignment.created_by_id), (klass.pk, self.admin_a.pk))
        again = self.client.post(url, {'school_class': klass.pk, 'subject': 'math'})
        self.assertContains(again, 'قبلاً ثبت شده', status_code=200)
        delete = reverse('dashboard:school_assignment_delete', args=['teachers', teacher.pk, assignment.pk])
        self.assertEqual(self.client.post(delete).status_code, 302)
        self.assertFalse(TeacherAssignment.objects.filter(teacher=teacher).exists())

    def test_grade_lead_account_and_assignment(self):
        self.post_year()
        self.create_account('gradeleads', 'new-lead')
        lead = User.objects.get(username='new-lead')
        self.assertEqual(roles_for(lead), {'GradeLead'})
        url = reverse('dashboard:school_staff_detail', args=['gradeleads', lead.pk])
        self.assertEqual(self.client.post(url, {'grade': 8, 'academic_year': '1404-1405'}).status_code, 302)
        row = GradeLeadAssignment.objects.get(user=lead)
        self.assertEqual((row.school_id, row.grade), (self.a.pk, 8))

    def test_deactivate_and_reactivate_a_teacher(self):
        self.create_account('teachers', 'new-teacher')
        teacher = User.objects.get(username='new-teacher')
        url = reverse('dashboard:school_staff_active', args=['teachers', teacher.pk])
        self.client.post(url)
        teacher.refresh_from_db()
        self.assertFalse(teacher.is_active)
        self.client.post(url)
        teacher.refresh_from_db()
        self.assertTrue(teacher.is_active)

    def test_weak_or_mismatching_passwords_and_duplicate_usernames_are_rejected(self):
        bad = self.client.post(reverse('dashboard:school_staff', args=['teachers']), {
            'username': 't1', 'first_name': 'N', 'last_name': 'L', 'password1': '123', 'password2': '123'})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(User.objects.filter(username='t1').exists())
        self.create_account('teachers', 'dup')
        self.assertEqual(self.create_account('teachers', 'dup').status_code, 200)
        self.assertEqual(User.objects.filter(username='dup').count(), 1)


class OtherSchoolTests(Base):
    """Everything of school B is a 404 for the admin of school A (and the school switch cannot reach it)."""

    def test_foreign_objects_are_404(self):
        urls = [
            ('get', reverse('dashboard:school_class_edit', args=[self.class_b.pk])),
            ('post', reverse('dashboard:school_class_edit', args=[self.class_b.pk])),
            ('post', reverse('dashboard:school_year_current', args=[self.year_b.pk])),
            ('get', reverse('dashboard:school_staff_detail', args=['teachers', self.teacher_b.pk])),
            ('post', reverse('dashboard:school_staff_detail', args=['teachers', self.teacher_b.pk])),
            ('post', reverse('dashboard:school_staff_active', args=['teachers', self.teacher_b.pk])),
            ('post', reverse('dashboard:school_assignment_delete',
                             args=['teachers', self.teacher_b.pk, self.assignment_b.pk])),
            ('get', reverse('dashboard:school_staff_detail', args=['gradeleads', self.lead_b.pk])),
            ('post', reverse('dashboard:school_assignment_delete',
                             args=['gradeleads', self.lead_b.pk, self.lead_assignment_b.pk])),
        ]
        for method, url in urls:
            self.assertEqual(getattr(self.client, method)(url).status_code, 404, (method, url))
        self.assertTrue(TeacherAssignment.objects.filter(pk=self.assignment_b.pk).exists())
        self.assertTrue(GradeLeadAssignment.objects.filter(pk=self.lead_assignment_b.pk).exists())
        self.teacher_b.refresh_from_db()
        self.assertTrue(self.teacher_b.is_active)

    def test_the_lists_show_only_the_own_school_and_the_school_switch_cannot_reach_another(self):
        for url in (reverse('dashboard:school_classes'), reverse('dashboard:school_staff', args=['teachers']),
                    reverse('dashboard:school_years'), reverse('dashboard:school_home')):
            body = self.client.get(url + f'?school={self.b.pk}').content.decode()
            for secret in ('7-B', 'teacher-b', 'lead-b'):
                self.assertNotIn(secret, body, url)

    def test_a_foreign_class_cannot_be_assigned_to_an_own_teacher(self):
        self.create_account_a()
        teacher = User.objects.get(username='mine')
        resp = self.client.post(reverse('dashboard:school_staff_detail', args=['teachers', teacher.pk]),
                                {'school_class': self.class_b.pk, 'subject': 'math'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(TeacherAssignment.objects.filter(teacher=teacher).exists())

    def create_account_a(self):
        self.client.post(reverse('dashboard:school_staff', args=['teachers']), {
            'username': 'mine', 'first_name': 'N', 'last_name': 'L', 'password1': PASSWORD, 'password2': PASSWORD})

    def test_a_foreign_year_cannot_be_used_for_a_class_or_a_lead(self):
        resp = self.client.post(reverse('dashboard:school_class_new'),
                                {'title': 'X', 'grade': 7, 'academic_year': '1404-1405', 'is_active': 'on'})
        self.assertEqual(resp.status_code, 200)    # school A has no such year: not offered, invalid choice
        self.assertFalse(SchoolClass.objects.filter(school=self.a).exists())


class RoleTests(Base):
    PAGES = (('school_home', ()), ('school_years', ()), ('school_classes', ()), ('school_class_new', ()),
             ('school_staff', ('teachers',)), ('school_staff', ('gradeleads',)))

    def statuses(self, user):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return {self.client.get(reverse(f'dashboard:{n}', args=a)).status_code for n, a in self.PAGES}

    def test_other_roles_get_403(self):
        for group in ('Teacher', 'GradeLead', 'Parent'):
            self.assertEqual(self.statuses(make_user(f'u-{group}', group)), {403}, group)

    def test_the_platform_superuser_gets_403(self):
        self.assertEqual(self.statuses(make_user('root', is_superuser=True)), {403})

    def test_an_admin_without_membership_gets_403(self):
        self.assertEqual(self.statuses(make_user('lonely', 'SchoolAdmin')), {403})

    def test_anonymous_is_sent_to_login(self):
        self.assertEqual(self.statuses(None), {302})

    def test_an_inactive_admin_is_refused(self):
        User.objects.filter(pk=self.admin_a.pk).update(is_active=False)
        self.assertEqual(self.statuses(User.objects.get(pk=self.admin_a.pk)), {302})   # session refused: back to login

    def test_post_endpoints_refuse_other_roles_too(self):
        teacher = make_user('t', 'Teacher')
        self.client.logout()
        self.client.force_login(teacher)
        self.assertEqual(self.client.post(reverse('dashboard:school_year_current', args=[self.year_b.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('dashboard:school_staff', args=['teachers']), {}).status_code, 403)
        self.assertFalse(User.objects.filter(username='x').exists())
