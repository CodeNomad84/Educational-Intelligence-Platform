"""Password reset by a Grade Lead (school setting, own grade only) and by the SchoolAdmin. Negative tests first. Synthetic data."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from schools.models import (
    AcademicYear, AccountProfile, AuditEvent, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff)
from students.enrollment_sync import ensure_current_enrollment
from students.models import Student

User = get_user_model()
OLD = 'Old-password-1'


def make_user(name, *groups, **extra):
    user = User.objects.create_user(name, password=OLD, **extra)
    for group in groups:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])   # speed only: the tests check behavior, not hashing
class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.a = School.objects.create(name='A', code='a', grade_leads_may_reset_passwords=True)
        self.b = School.objects.create(name='B', code='b', grade_leads_may_reset_passwords=True)
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23),
                                        end_date=date(2026, 6, 21), is_current=True)
        self.c7 = SchoolClass.objects.create(school=self.a, title='7-A', academic_year='1404-1405', grade=7)
        self.c8 = SchoolClass.objects.create(school=self.a, title='8-A', academic_year='1404-1405', grade=8)
        self.cb = SchoolClass.objects.create(school=self.b, title='7-A', academic_year='1404-1405', grade=7)
        self.admin = make_user('admin-a', 'SchoolAdmin'); SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin'); SchoolMembership.objects.create(user=self.admin_b, school=self.b)
        self.lead = make_user('lead-a', 'GradeLead'); SchoolStaff.objects.create(user=self.lead, school=self.a)
        GradeLeadAssignment.objects.create(user=self.lead, school=self.a, grade=7, academic_year='1404-1405')
        self.s7, self.stu7, self.par7 = self.family('9000000001', self.c7, 7)
        self.s8, self.stu8, self.par8 = self.family('9000000002', self.c8, 8)
        self.sb, self.stub, self.parb = self.family('9000000003', self.cb, 7)
        self.client.force_login(self.lead)

    def family(self, nid, klass, grade):
        student_user = make_user(nid, 'Student')
        parent = make_user('p' + nid, 'Parent')
        student = Student.objects.create(first_name='S', last_name=nid, national_id=nid, grade=grade, phone_number='',
                                         school_class=klass, student_user=student_user, parent_user=parent)
        ensure_current_enrollment(student, source='import')
        return student, student_user, parent

    def reset(self, user, client=None):
        return (client or self.client).post(reverse('dashboard:grade_reset', args=[user.pk]))

    def unchanged(self, *users):
        for user in users:
            user.refresh_from_db()
            self.assertTrue(user.check_password(OLD), user.username)
        self.assertFalse(AuditEvent.objects.filter(action='password_reset').exists())


class GradeLeadResetTests(Base):
    def test_happy_path_student_and_parent(self):
        for target, parent in ((self.stu7, False), (self.par7, True)):
            self.client.logout(); self.client.force_login(self.lead)
            response = self.reset(target)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Cache-Control'], 'no-store')
            password = response.context['password']
            self.assertIn(password, response.content.decode())
            self.assertEqual(response.context['is_parent'], parent)
            if parent:
                self.assertIn('هویت', response.content.decode())
            target.refresh_from_db()
            self.assertTrue(target.check_password(password))
            self.assertNotEqual(password, target.username)
            self.assertTrue(AccountProfile.objects.get(user=target).must_change_password)
            event = AuditEvent.objects.filter(action='password_reset', object_id=str(target.pk)).get()
            self.assertEqual((event.user, event.school, event.object_type, event.detail), (self.lead, self.a, 'User', 'gradelead'))

    def test_the_list_page_shows_only_own_grade(self):
        response = self.client.get(reverse('dashboard:grade_resets'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['student'] for r in response.context['rows']], [self.s7])

    def test_forced_change_and_throttle_cleared(self):
        for _ in range(5):
            Client().post(reverse('dashboard:login'), {'username': self.stu7.username, 'password': 'wrong'})
        self.assertEqual(Client().post(reverse('dashboard:login'), {'username': self.stu7.username, 'password': OLD}).status_code, 429)
        password = self.reset(self.stu7).context['password']
        user_client = Client()
        self.assertEqual(user_client.post(reverse('dashboard:login'), {'username': self.stu7.username, 'password': password}).status_code, 302)
        self.assertRedirects(user_client.get(reverse('dashboard:me_home')), reverse('dashboard:password_change'),
                             fetch_redirect_response=False)
        self.assertFalse(Client().login(username=self.stu7.username, password=OLD))   # the old password is gone

    def test_setting_off_is_403_everywhere(self):
        School.objects.filter(pk=self.a.pk).update(grade_leads_may_reset_passwords=False)
        self.assertEqual(self.client.get(reverse('dashboard:grade_resets')).status_code, 403)
        self.assertEqual(self.reset(self.stu7).status_code, 403)
        self.assertEqual(self.reset(self.par7).status_code, 403)
        self.unchanged(self.stu7, self.par7)

    def test_other_grade_and_other_school_are_404(self):
        for target in (self.stu8, self.par8, self.stub, self.parb):
            self.assertEqual(self.reset(target).status_code, 404, target.username)
        self.unchanged(self.stu8, self.par8, self.stub, self.parb)

    def test_parent_with_a_child_outside_the_grade_is_404(self):
        sibling = Student.objects.create(first_name='S', last_name='sib', national_id='9000000099', grade=8, phone_number='',
                                         school_class=self.c8, parent_user=self.par7)
        ensure_current_enrollment(sibling, source='import')
        self.assertEqual(self.reset(self.par7).status_code, 404)
        self.unchanged(self.par7)

    def test_teacher_counselor_admin_and_staff_targets_are_refused(self):
        teacher = make_user('teacher-a', 'Teacher'); counselor = make_user('couns-a', 'Counselor')
        for user in (teacher, counselor, self.admin, self.lead):
            self.assertIn(self.reset(user).status_code, (403, 404), user.username)
        # in scope (linked to a grade-7 student) but not a plain Student / Parent account
        staff_parent = make_user('9000000071', 'Parent', is_staff=True)
        super_parent = make_user('9000000072', 'Parent', is_superuser=True)
        school_staff_parent = make_user('9000000073', 'Parent'); SchoolStaff.objects.create(user=school_staff_parent, school=self.a)
        for i, user in enumerate((staff_parent, super_parent, school_staff_parent, teacher, counselor, self.admin)):
            extra = Student.objects.create(first_name='S', last_name='x', national_id=f'90000001{i:02d}', grade=7, phone_number='',
                                           school_class=self.c7, parent_user=user)
            ensure_current_enrollment(extra, source='import')
            self.assertEqual(self.reset(user).status_code, 403, user.username)
        self.unchanged(teacher, counselor, self.admin, staff_parent, super_parent, school_staff_parent)

    def test_self_reset_is_refused(self):
        self.lead.groups.add(Group.objects.get_or_create(name='Parent')[0])
        Student.objects.filter(pk=self.s7.pk).update(parent_user=self.lead)
        self.assertEqual(self.reset(self.lead).status_code, 403)
        self.unchanged(self.lead)

    def test_dual_role_target_is_refused(self):
        dual = make_user('9000000081', 'Student', 'Teacher')
        Student.objects.filter(pk=self.s7.pk).update(student_user=dual)
        self.assertEqual(self.reset(dual).status_code, 403)
        both = make_user('9000000082', 'Student', 'Parent')
        Student.objects.filter(pk=self.s7.pk).update(parent_user=both)
        self.assertEqual(self.reset(both).status_code, 403)
        self.unchanged(dual, both)

    def test_inactive_target_and_inactive_actor_are_refused(self):
        User.objects.filter(pk=self.stu7.pk).update(is_active=False)
        self.assertEqual(self.reset(self.stu7).status_code, 403)
        self.unchanged(self.par7)
        User.objects.filter(pk=self.lead.pk).update(is_active=False)
        self.assertIn(self.reset(self.par7).status_code, (302, 403))
        self.assertTrue(User.objects.get(pk=self.par7.pk).check_password(OLD))
        self.assertFalse(AuditEvent.objects.filter(action='password_reset').exists())

    def test_other_roles_and_get_are_refused(self):
        for who in (make_user('t1', 'Teacher'), make_user('p1', 'Parent'), self.admin):
            client = Client(); client.force_login(who)
            self.assertEqual(self.reset(self.stu7, client).status_code, 403, who.username)
            self.assertEqual(client.get(reverse('dashboard:grade_resets')).status_code, 403)
        self.assertEqual(Client().post(reverse('dashboard:grade_reset', args=[self.stu7.pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('dashboard:grade_reset', args=[self.stu7.pk])).status_code, 405)
        self.unchanged(self.stu7)

    def test_grade_lead_scope_does_not_widen_through_a_second_role(self):
        # a Teacher/GradeLead sees grade-8 students as a teacher; the reset page still uses the grade-lead grant only
        self.lead.groups.add(Group.objects.get_or_create(name='Teacher')[0])
        from schools.models import TeacherAssignment
        TeacherAssignment.objects.create(teacher=self.lead, school_class=self.c8, subject='math')
        self.assertEqual(self.reset(self.stu8).status_code, 404)
        self.unchanged(self.stu8)

    def test_hourly_cap_refuses_and_flags_for_the_admin(self):
        for _ in range(20):
            from schools import audit
            audit.record(self.lead, audit.PASSWORD_RESET, self.stu7, school=self.a, detail='gradelead')
        response = self.reset(self.par7)
        self.assertEqual(response.status_code, 429)
        self.assertTrue(User.objects.get(pk=self.par7.pk).check_password(OLD))
        self.assertTrue(AuditEvent.objects.filter(action='password_reset_capped', school=self.a, user=self.lead).exists())
        admin_client = Client(); admin_client.force_login(self.admin)
        page = admin_client.get(reverse('dashboard:school_audit'))
        self.assertIn('password_reset_capped', page.content.decode())

    def test_password_is_nowhere_but_the_response(self):
        with self.assertNoLogs(level='DEBUG'):
            response = self.reset(self.stu7)
        password = response.context['password']
        with connection.cursor() as cursor:
            for table in connection.introspection.table_names():
                cursor.execute(f'SELECT * FROM "{table}"')
                self.assertNotIn(password, repr(cursor.fetchall()), table)
        self.assertNotIn(password, repr(dict(self.client.session)))
        self.assertFalse(any(password in str(m) for m in response.context['messages']))
        self.assertNotIn(password, self.client.get(reverse('dashboard:grade_resets')).content.decode())


class AdminResetTests(Base):
    def setUp(self):
        super().setUp()
        self.client.logout(); self.client.force_login(self.admin)

    def reset_admin(self, user, client=None):
        return (client or self.client).post(reverse('dashboard:school_reset', args=[user.pk]))

    def test_admin_resets_student_parent_and_staff_of_the_own_school(self):
        teacher = make_user('teacher-a', 'Teacher'); SchoolStaff.objects.create(user=teacher, school=self.a)
        for target in (self.stu8, self.par8, teacher):          # any grade: the admin is school-wide
            response = self.reset_admin(target)
            self.assertEqual(response.status_code, 200)
            target.refresh_from_db()
            self.assertTrue(target.check_password(response.context['password']))
            self.assertTrue(AccountProfile.objects.get(user=target).must_change_password)
            self.assertEqual(AuditEvent.objects.get(action='password_reset', object_id=str(target.pk)).detail, 'admin')
        page = self.client.get(reverse('dashboard:school_resets'))
        self.assertEqual(page.status_code, 200)
        self.assertIn(self.stu7, list(page.context['people']))

    def test_admin_refusals(self):
        other_admin = make_user('admin-a2', 'SchoolAdmin'); SchoolMembership.objects.create(user=other_admin, school=self.a)
        SchoolStaff.objects.create(user=other_admin, school=self.a)
        for user in (self.admin, other_admin):
            self.assertEqual(self.reset_admin(user).status_code, 403 if user is other_admin else 404, user.username)
        for user in (self.stub, self.parb, self.admin_b):        # other school
            self.assertEqual(self.reset_admin(user).status_code, 404)
        User.objects.filter(pk=self.stu7.pk).update(is_active=False)
        self.assertEqual(self.reset_admin(self.stu7).status_code, 403)
        both = Student.objects.create(first_name='S', last_name='b', national_id='9000000098', grade=7, phone_number='',
                                      school_class=self.cb, parent_user=self.par7)
        self.assertEqual(self.reset_admin(self.par7).status_code, 404)    # also a parent in another school
        self.assertEqual(self.client.get(reverse('dashboard:school_reset', args=[self.par8.pk])).status_code, 405)
        self.unchanged(other_admin, self.stub, self.parb, self.stu7, self.par7)

    def test_other_roles_cannot_use_the_admin_pages(self):
        for who in (self.lead, make_user('t9', 'Teacher')):
            client = Client(); client.force_login(who)
            self.assertEqual(self.reset_admin(self.stu7, client).status_code, 403)
            self.assertEqual(client.get(reverse('dashboard:school_resets')).status_code, 403)
            self.assertEqual(client.post(reverse('dashboard:school_resets_setting'), {'enabled': 'on'}).status_code, 403)

    def test_only_the_school_admin_changes_the_setting_and_it_is_logged(self):
        School.objects.filter(pk=self.a.pk).update(grade_leads_may_reset_passwords=False)
        self.client.post(reverse('dashboard:school_resets_setting'), {'enabled': 'on'})
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertTrue(self.a.grade_leads_may_reset_passwords)
        self.assertEqual(AuditEvent.objects.filter(action='reset_setting_change', school=self.a, detail='on').count(), 1)
        self.client.post(reverse('dashboard:school_resets_setting'), {'enabled': 'on'})    # unchanged: no new event
        self.assertEqual(AuditEvent.objects.filter(action='reset_setting_change').count(), 1)
        self.client.post(reverse('dashboard:school_resets_setting'), {})
        self.a.refresh_from_db()
        self.assertFalse(self.a.grade_leads_may_reset_passwords)
        self.assertTrue(AuditEvent.objects.filter(action='reset_setting_change', detail='off').exists())
        # the admin of school B can only change B
        other = Client(); other.force_login(self.admin_b)
        School.objects.filter(pk=self.b.pk).update(grade_leads_may_reset_passwords=False)
        other.post(reverse('dashboard:school_resets_setting'), {'enabled': 'on'})
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertTrue(self.b.grade_leads_may_reset_passwords)
        self.assertFalse(self.a.grade_leads_may_reset_passwords)

    def test_default_is_off(self):
        self.assertFalse(School.objects.create(name='C', code='c').grade_leads_may_reset_passwords)


class SelfCheckUnitTest(TestCase):
    def test_self_is_refused_independently_of_the_group_rules(self):
        from dashboard.password_reset import _ineligible_for_gradelead
        user = make_user('p1', 'Parent')
        self.assertEqual(_ineligible_for_gradelead(user, user), 'self')
        self.assertEqual(_ineligible_for_gradelead(make_user('x', 'GradeLead'), user), '')
