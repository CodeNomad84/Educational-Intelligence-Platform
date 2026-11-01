"""C-A Django admin closure (S9; decision pack 0028 P3-10, owner go 2026-11-01). Synthetic data only.

The admin is for platform operators (superuser, PlatformAdmin) and shows platform tables only. Student and parent accounts are
never listed, and a staff/superuser account cannot also hold a school role."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PARENT, PLATFORM_ADMIN, STUDENT, TEACHER
from students.models import Student

from .models import (
    AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolModule, SchoolStaff, TeacherAssignment)

User = get_user_model()


def make_user(username, group=None, **extra):
    user = User.objects.create_user(username=username, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class AdminClosureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name='School A', code='school-a')
        cls.root = User.objects.create_superuser('root', password='x')
        cls.platform = make_user('platform', PLATFORM_ADMIN, is_staff=True)
        cls.school_admin = make_user('schooladmin', ADMIN)
        SchoolMembership.objects.create(user=cls.school_admin, school=cls.school)
        cls.teacher = make_user('9000000001', TEACHER)
        cls.lead = make_user('9000000002', GRADE_LEAD)
        cls.counselor = make_user('9000000003', COUNSELOR)
        cls.parent = make_user('9000000004', PARENT)
        cls.student_user = make_user('9000000005', STUDENT)
        cls.plain_staff = make_user('plainstaff', is_staff=True)
        cls.fresh = make_user('fresh')

    def test_only_platform_operators_open_the_admin(self):
        ok = {self.root, self.platform}
        for user in (self.root, self.platform, self.school_admin, self.teacher, self.lead, self.counselor, self.parent,
                     self.student_user, self.plain_staff, self.fresh):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('admin:index'))
                self.assertEqual(response.status_code, 200 if user in ok else 302)
                if user not in ok:
                    self.assertIn(reverse('admin:login'), response['Location'])

    def test_school_data_tables_are_not_registered(self):
        for model in (Student, SchoolClass, TeacherAssignment, GradeLeadAssignment, AcademicYear, SchoolStaff):
            self.assertNotIn(model, admin.site._registry, model.__name__)
        for name in ('admin:students_student_changelist', 'admin:schools_schoolclass_add',
                     'admin:schools_teacherassignment_changelist', 'admin:schools_gradeleadassignment_changelist',
                     'admin:schools_academicyear_changelist', 'admin:schools_schoolstaff_changelist'):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_superuser_index_lists_platform_tables_only(self):
        self.client.force_login(self.root)
        page = self.client.get(reverse('admin:index'))
        names = {m['object_name'] for app in page.context['app_list'] for m in app['models']}
        self.assertEqual(names, {'School', 'SchoolModule', 'SchoolMembership', 'User', 'Group'})

    def test_user_list_never_shows_school_accounts(self):
        self.client.force_login(self.root)
        page = self.client.get(reverse('admin:auth_user_changelist'))
        self.assertEqual({u.username for u in page.context['cl'].result_list},
                         {'root', 'platform', 'schooladmin', 'plainstaff', 'fresh'})
        search = self.client.get(reverse('admin:auth_user_changelist'), {'q': '900000000'})
        self.assertEqual(list(search.context['cl'].result_list), [])

    def test_school_account_change_page_is_not_served(self):
        self.client.force_login(self.root)
        for user in (self.teacher, self.parent, self.student_user):
            with self.subTest(user=user.username):
                response = self.client.get(reverse('admin:auth_user_change', args=[user.pk]))
                self.assertEqual((response.status_code, response['Location']), (302, reverse('admin:index')))

    def test_school_admin_who_also_teaches_stays_listed(self):
        both = make_user('admin-teacher', ADMIN)
        both.groups.add(Group.objects.get(name=TEACHER))
        self.client.force_login(self.root)
        page = self.client.get(reverse('admin:auth_user_changelist'))
        self.assertIn('admin-teacher', {u.username for u in page.context['cl'].result_list})

    def _change(self, user, **fields):
        data = {'username': user.username, 'first_name': '', 'last_name': '', 'email': '', 'is_active': 'on',
                'date_joined_0': '2026-11-01', 'date_joined_1': '10:00:00', 'groups': [g.pk for g in user.groups.all()]}
        data.update(fields)
        return self.client.post(reverse('admin:auth_user_change', args=[user.pk]), data)

    def test_school_account_cannot_be_made_staff(self):
        self.client.force_login(self.root)
        self.assertEqual(self._change(self.school_admin, is_staff='on').status_code, 200)
        self.school_admin.refresh_from_db()
        self.assertFalse(self.school_admin.is_staff)

    def test_staff_account_cannot_get_a_school_group(self):
        self.client.force_login(self.root)
        self.assertEqual(self._change(self.platform, is_staff='on', groups=[Group.objects.get(name=ADMIN).pk]).status_code, 200)
        self.assertFalse(self.platform.groups.filter(name=ADMIN).exists())

    def test_operator_can_still_create_the_first_school_admin(self):
        """Onboarding step 3 of the platform manual: add the user, then tick the SchoolAdmin group (not staff)."""
        self.client.force_login(self.root)
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'new-admin', 'password1': 'a-Long-pass-123', 'password2': 'a-Long-pass-123', 'usable_password': 'true'})
        self.assertEqual(response.status_code, 302)
        new = User.objects.get(username='new-admin')
        self.assertEqual(self._change(new, groups=[Group.objects.get(name=ADMIN).pk]).status_code, 302)
        self.assertTrue(new.groups.filter(name=ADMIN).exists())
        self.assertEqual(self.client.get(reverse('admin:auth_user_change', args=[new.pk])).status_code, 200)
