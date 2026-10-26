"""Bulk accounts from Excel (dry run then confirm), forced first-login password change, password change from the profile
page and staff roles. Simple integration tests; synthetic data only (ids in the 9000000xxx range)."""
import io
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from schools.models import (
    AcademicYear, AccountProfile, AuditEvent, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff)
from students.models import Student

User = get_user_model()
HEAD_S = ['name', 'national_id', 'grade', 'class', 'father_national_id', 'mother_national_id', 'father_name', 'mother_name']
HEAD_T = ['name', 'national_id', 'phone']


def make_user(name, group=None, **extra):
    user = User.objects.create_user(name, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


def xlsx(students=None, teachers=None):
    book = Workbook()
    book.remove(book.active)
    if students is not None:
        ws = book.create_sheet('Students'); ws.append(HEAD_S)
        for row in students:
            ws.append(row)
        for cell in ws['A']:
            if isinstance(cell.value, str) and cell.value.startswith('='):
                cell.data_type = 's'   # a text cell that looks like a formula (what a malicious file would contain)
    if teachers is not None:
        ws = book.create_sheet('Teachers'); ws.append(HEAD_T)
        for row in teachers:
            ws.append(row)
    out = io.BytesIO(); book.save(out)
    out.name = 'accounts.xlsx'; out.seek(0)
    return out


class Base(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        self.b = School.objects.create(name='B', code='b')
        self.admin_a = make_user('admin-a', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_a, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_b, school=self.b)
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23),
                                        end_date=date(2026, 6, 21), is_current=True)
        self.class_a = SchoolClass.objects.create(school=self.a, title='7-A', academic_year='1404-1405', grade=7)
        self.class_b = SchoolClass.objects.create(school=self.b, title='7-A', academic_year='1404-1405', grade=7)
        self.client.force_login(self.admin_a)

    def upload(self, file, client=None):
        return (client or self.client).post(reverse('dashboard:school_accounts'), {'file': file})

    def confirm(self, students=None, teachers=None):
        self.assertEqual(self.upload(xlsx(students, teachers)).status_code, 302)
        return self.client.post(reverse('dashboard:school_accounts_confirm'))

    def preview(self, students=None, teachers=None):
        self.upload(xlsx(students, teachers))
        return self.client.get(reverse('dashboard:school_accounts_preview'))


class BulkAccountsTests(Base):
    STUDENTS = [
        ['Ali Test', '9000000001', 7, '7-A', '9000000101', '9000000201', 'Father One', 'Mother One'],
        ['Sara Test', '9000000002', 7, '7-A', '9000000101', '', 'Father One', ''],        # sibling: same father
        ['Omid Test', '9000000003', 7, '7-A', '', '9000000202', '', 'Mother Two'],        # no father: mother
    ]

    def test_dry_run_writes_nothing(self):
        response = self.preview(self.STUDENTS, [['Teach Er', '9000000301', '09120000000']])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), 0)
        self.assertFalse(User.objects.filter(username__startswith='90000').exists())
        self.assertFalse(AuditEvent.objects.filter(action='bulk_accounts').exists())

    def test_happy_path(self):
        response = self.confirm(self.STUDENTS, [['Teach Er', '9000000301', '09120000000']])
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        rows = list(load_workbook(io.BytesIO(response.content)).active.iter_rows(min_row=2, values_only=True))
        logins = {r[2]: r for r in rows if r[3]}
        self.assertEqual(set(logins), {'9000000001', '9000000002', '9000000003', '9000000101', '9000000202', '9000000301'})
        self.assertEqual(Student.objects.filter(school=self.a).count(), 3)
        s1, s2, s3 = (Student.objects.get(national_id=n) for n in ('9000000001', '9000000002', '9000000003'))
        self.assertEqual(s1.parent_user.username, '9000000101')
        self.assertEqual(s2.parent_user_id, s1.parent_user_id)          # one parent account, all its children
        self.assertEqual(s3.parent_user.username, '9000000202')        # no father: the mother
        self.assertEqual(s1.student_user.username, '9000000001')
        self.assertTrue(s1.enrollments.exists())
        self.assertIn('Sara', logins['9000000101'][4])                  # the parent's row lists both children
        teacher = User.objects.get(username='9000000301')
        self.assertTrue(SchoolStaff.objects.filter(user=teacher, school=self.a).exists())
        self.assertEqual(teacher.account_profile.phone, '09120000000')
        for username, row in logins.items():
            password = row[3]
            self.assertNotEqual(password, username)                      # never the national id
            self.assertGreaterEqual(len(password), 10)
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(password))
            self.assertTrue(AccountProfile.objects.get(user=user).must_change_password)
        self.assertEqual(len({r[3] for r in logins.values()}), len(logins))   # random per user
        event = AuditEvent.objects.get(action='bulk_accounts')
        self.assertEqual(event.school, self.a)
        self.assertEqual(event.detail, 's3p2t1e0f0')                     # counts only
        self.assertFalse(any(r[3] in str(vars(event)) for r in logins.values()))

    def test_rerun_creates_nothing_new_and_no_new_passwords(self):
        self.confirm(self.STUDENTS)
        before = list(User.objects.order_by('pk').values_list('password', flat=True))
        response = self.confirm(self.STUDENTS)
        self.assertEqual(response.status_code, 302)                      # no sheet: nothing was created
        self.assertEqual(list(User.objects.order_by('pk').values_list('password', flat=True)), before)

    def test_row_errors_are_listed_per_row(self):
        rows = [['A One', '9000000001', 7, '7-A', '', '', '', ''],
                ['A Dup', '9000000001', 7, '7-A', '', '', '', ''],        # duplicate in file
                ['Bad Id', '12345', 7, '7-A', '', '', '', ''],            # invalid format
                ['Short Num', 900000004, 7, '7-A', '', '', '', ''],       # numeric cell: 9 digits (lost leading zero)
                ['Bad Cls', '9000000005', 7, '9-Z', '', '', '', ''],     # class not in this school
                ['Bad Grd', '9000000006', 99, '7-A', '', '', '', '']]
        response = self.preview(rows)
        plan = response.context['plan']
        self.assertEqual([r.status for r in plan.rows], ['create', 'error', 'error', 'error', 'error', 'error'])
        self.assertEqual([r.line for r in plan.rows], [2, 3, 4, 5, 6, 7])
        self.assertIn('تکراری', plan.rows[1].message)
        self.assertIn('متن', plan.rows[3].message)

    def test_other_school_ids_get_one_generic_error(self):
        other = Student.objects.create(first_name='X', last_name='Y', national_id='9000000010', grade=7,
                                       phone_number='', school_class=self.class_b)
        teacher_b = make_user('9000000311', 'Teacher'); SchoolStaff.objects.create(user=teacher_b, school=self.b)
        parent_b = make_user('9000000111', 'Parent')
        Student.objects.filter(pk=other.pk).update(parent_user=parent_b)
        stranger = make_user('9000000012', 'Counselor')
        rows = [['Z One', '9000000010', 7, '7-A', '', '', '', ''],        # student of school B
                ['Z Two', '9000000011', 7, '7-A', '9000000111', '', '', ''],   # parent of school B's child
                ['Z Three', '9000000012', 7, '7-A', '', '', '', '']]     # id of an unrelated user
        plan = self.preview(rows, [['T One', '9000000311', ''], ['T Two', '9000000012', '']]).context['plan']
        from dashboard.bulk_accounts import GENERIC
        self.assertEqual([r.message for r in plan.rows], [GENERIC] * 5)
        self.assertEqual({r.status for r in plan.rows}, {'error'})
        self.confirm(rows)
        self.assertEqual(Student.objects.get(pk=other.pk).school_id, self.b.pk)    # untouched
        self.assertEqual(Student.objects.get(pk=other.pk).parent_user_id, parent_b.pk)
        self.assertFalse(Student.objects.filter(national_id='9000000011').exists())
        self.assertEqual(stranger.groups.count(), 1)

    def test_batch_limit_blocks_confirm(self):
        with mock.patch('dashboard.bulk_accounts.MAX_NEW_ACCOUNTS', 1):
            self.assertTrue(self.preview(self.STUDENTS).context['plan'].blocking)
            self.client.post(reverse('dashboard:school_accounts_confirm'))
        self.assertEqual(Student.objects.count(), 0)

    def test_bad_file_is_a_generic_message(self):
        bad = io.BytesIO(b'not a workbook'); bad.name = 'x.xlsx'
        response = self.upload(bad)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('Student', self.client.session.keys())

    def test_formula_like_names_are_stored_as_text_in_the_sheet(self):
        response = self.confirm([['=1+1 Evil', '9000000001', 7, '7-A', '', '', '', '']])
        cell = load_workbook(io.BytesIO(response.content)).active['B2']
        self.assertEqual(cell.data_type, 's')

    def test_no_password_in_logs(self):
        with self.assertNoLogs(level='DEBUG'):
            response = self.confirm(self.STUDENTS)
        self.assertEqual(response.status_code, 200)


class AccessTests(Base):
    def test_other_roles_and_anonymous(self):
        teacher = make_user('t', 'Teacher')
        for who in (teacher, make_user('p', 'Parent'), make_user('plain')):
            client = Client(); client.force_login(who)
            for name in ('school_accounts', 'school_accounts_preview', 'school_staff_roles', 'school_accounts_template'):
                self.assertEqual(client.get(reverse(f'dashboard:{name}')).status_code, 403, name)
            self.assertEqual(self.upload(xlsx([]), client).status_code, 403)
            self.assertEqual(client.post(reverse('dashboard:school_accounts_confirm')).status_code, 403)
        anonymous = Client()
        self.assertEqual(anonymous.get(reverse('dashboard:school_accounts')).status_code, 302)

    def test_inactive_admin_and_admin_without_membership(self):
        self.admin_a.is_active = False; self.admin_a.save()
        self.assertEqual(Client().get(reverse('dashboard:school_accounts')).status_code, 302)
        lone = make_user('lone', 'SchoolAdmin')
        client = Client(); client.force_login(lone)
        self.assertEqual(client.get(reverse('dashboard:school_accounts')).status_code, 403)

    def test_plan_of_one_school_is_not_confirmable_in_another(self):
        self.upload(xlsx([['A One', '9000000001', 7, '7-A', '', '', '', '']]))
        other = Client(); other.force_login(self.admin_b)
        self.assertEqual(other.post(reverse('dashboard:school_accounts_confirm')).status_code, 302)
        self.assertFalse(Student.objects.exists())


class PasswordTests(Base):
    def new_user_client(self):
        response = self.confirm([['Ali Test', '9000000001', 7, '7-A', '', '', '', '']])
        password = list(load_workbook(io.BytesIO(response.content)).active.iter_rows(min_row=2, values_only=True))[0][3]
        client = Client()
        self.assertTrue(client.login(username='9000000001', password=password))
        return client, password

    def test_forced_change_at_first_login(self):
        client, old = self.new_user_client()
        for url in (reverse('dashboard:me_home'), reverse('dashboard:profile'), '/students/'):
            response = client.get(url)
            self.assertRedirects(response, reverse('dashboard:password_change'), fetch_redirect_response=False)
        self.assertEqual(client.get(reverse('dashboard:password_change')).status_code, 200)
        # wrong old password, same password, weak password: refused and the flag stays
        for data in ({'old_password': 'wrong', 'new_password1': 'Brand-new-pass-1', 'new_password2': 'Brand-new-pass-1'},
                     {'old_password': old, 'new_password1': old, 'new_password2': old},
                     {'old_password': old, 'new_password1': '12345678', 'new_password2': '12345678'},
                     {'old_password': old, 'new_password1': 'abc', 'new_password2': 'abc'}):
            self.assertEqual(client.post(reverse('dashboard:password_change'), data).status_code, 200)
        self.assertTrue(AccountProfile.objects.get(user__username='9000000001').must_change_password)
        response = client.post(reverse('dashboard:password_change'), {
            'old_password': old, 'new_password1': 'Brand-new-pass-1', 'new_password2': 'Brand-new-pass-1'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AccountProfile.objects.get(user__username='9000000001').must_change_password)
        self.assertEqual(client.get(reverse('dashboard:me_home')).status_code, 200)   # still signed in, access restored
        self.assertTrue(Client().login(username='9000000001', password='Brand-new-pass-1'))
        self.assertFalse(Client().login(username='9000000001', password=old))

    def test_logout_is_allowed_while_flagged(self):
        client, _ = self.new_user_client()
        self.assertRedirects(client.get(reverse('dashboard:logout')), reverse('dashboard:login'),
                             fetch_redirect_response=False)

    def test_any_user_can_change_the_password_from_the_profile(self):
        user = make_user('someone', 'Teacher'); user.set_password('Old-password-9'); user.save()
        client = Client(); client.force_login(user)
        self.assertEqual(client.get(reverse('dashboard:profile')).status_code, 200)
        response = client.post(reverse('dashboard:password_change'), {
            'old_password': 'Old-password-9', 'new_password1': 'Newer-password-9', 'new_password2': 'Newer-password-9'})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Newer-password-9'))

    def test_accounts_without_a_profile_row_are_not_forced(self):
        user = make_user('old-account', 'Teacher')
        client = Client(); client.force_login(user)
        self.assertEqual(client.get(reverse('dashboard:profile')).status_code, 200)
        self.assertEqual(client.get(reverse('dashboard:teacher_home')).status_code, 200)

    def test_anonymous_cannot_change_a_password(self):
        self.assertEqual(Client().post(reverse('dashboard:password_change'), {}).status_code, 302)


class StaffRoleTests(Base):
    def setUp(self):
        super().setUp()
        self.staff = make_user('staff-a'); SchoolStaff.objects.create(user=self.staff, school=self.a)
        self.staff_b = make_user('staff-b'); SchoolStaff.objects.create(user=self.staff_b, school=self.b)

    def save(self, user, data):
        return self.client.post(reverse('dashboard:school_staff_roles_save', args=[user.pk]), data)

    def groups(self, user):
        return set(user.groups.values_list('name', flat=True))

    def test_assign_and_remove_roles_and_grades(self):
        self.assertEqual(self.client.get(reverse('dashboard:school_staff_roles')).status_code, 200)
        self.save(self.staff, {'teacher': 'on', 'gradelead': 'on', 'grades': ['7', '8'], 'counselor': 'on'})
        self.assertEqual(self.groups(self.staff), {'Teacher', 'GradeLead', 'Counselor'})
        self.assertEqual(set(GradeLeadAssignment.objects.filter(user=self.staff, school=self.a).values_list('grade', flat=True)),
                         {7, 8})
        self.save(self.staff, {'gradelead': 'on', 'grades': ['8']})
        self.assertEqual(self.groups(self.staff), {'GradeLead'})
        self.assertEqual(set(GradeLeadAssignment.objects.filter(user=self.staff).values_list('grade', flat=True)), {8})
        self.save(self.staff, {})
        self.assertEqual(self.groups(self.staff), set())
        self.assertFalse(GradeLeadAssignment.objects.filter(user=self.staff).exists())
        self.assertTrue(AuditEvent.objects.filter(action='staff_roles_change', school=self.a).exists())

    def test_gradelead_needs_a_grade(self):
        self.save(self.staff, {'gradelead': 'on'})
        self.assertEqual(self.groups(self.staff), set())

    def test_cannot_touch_other_school_admins_or_unknown_roles(self):
        self.assertEqual(self.save(self.staff_b, {'teacher': 'on'}).status_code, 404)    # other school's staff
        self.assertEqual(self.groups(self.staff_b), set())
        admin_staff = make_user('admin-staff', 'SchoolAdmin'); SchoolStaff.objects.create(user=admin_staff, school=self.a)
        self.assertEqual(self.save(admin_staff, {'teacher': 'on'}).status_code, 404)     # a SchoolAdmin is not re-roled here
        self.save(self.staff, {'teacher': 'on', 'schooladmin': 'on', 'SchoolAdmin': 'on', 'groups': 'SchoolAdmin'})
        self.assertEqual(self.groups(self.staff), {'Teacher'})                           # no way to add SchoolAdmin
        self.assertEqual(self.client.get(reverse('dashboard:school_staff_roles')).context['rows'][0]['person'], self.staff)

    def test_wrong_role_and_get(self):
        client = Client(); client.force_login(make_user('t2', 'Teacher'))
        self.assertEqual(client.post(reverse('dashboard:school_staff_roles_save', args=[self.staff.pk]),
                                     {'teacher': 'on'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('dashboard:school_staff_roles_save', args=[self.staff.pk])).status_code, 405)


class CollisionTests(Base):
    """Decision (recorded in the commit message): ONE username = ONE account = ONE kind of person in ONE school. Bulk import
    never merges roles or schools onto an existing account: an id that already belongs to anything other than exactly what the
    row would create/link in THIS school is one generic row error, identical for every cause, so nothing tells the importer
    whether the id exists, in which school, or in which role."""

    def generic(self):
        from dashboard.bulk_accounts import GENERIC
        return GENERIC

    def test_parent_of_school_a_is_a_generic_error_for_school_b(self):
        self.confirm([['Ali Test', '9000000001', 7, '7-A', '9000000101', '', 'Father One', '']])
        parent = User.objects.get(username='9000000101')
        client_b = Client(); client_b.force_login(self.admin_b)
        client_b.post(reverse('dashboard:school_accounts'), {'file': xlsx([['Bo Test', '9000000009', 7, '7-A', '9000000101', '', '', '']])})
        plan = client_b.get(reverse('dashboard:school_accounts_preview')).context['plan']
        self.assertEqual([(r.status, r.message) for r in plan.rows], [('error', self.generic())])
        client_b.post(reverse('dashboard:school_accounts_confirm'))
        self.assertFalse(Student.objects.filter(national_id='9000000009').exists())
        self.assertEqual(set(Student.objects.filter(parent_user=parent).values_list('school_id', flat=True)), {self.a.pk})

    def test_every_collision_gives_the_same_message_and_no_hint(self):
        teacher_a = make_user('9000000301', 'Teacher'); SchoolStaff.objects.create(user=teacher_a, school=self.a)
        parent_a = make_user('9000000111', 'Parent')
        Student.objects.create(first_name='K', last_name='A', national_id='9000000020', grade=7, phone_number='',
                               school_class=self.class_a, parent_user=parent_a)
        parent_b = make_user('9000000112', 'Parent')
        Student.objects.create(first_name='K', last_name='B', national_id='9000000021', grade=7, phone_number='',
                               school_class=self.class_b, parent_user=parent_b)
        stranger = make_user('9000000030')
        rows = [['S1', '9000000301', 7, '7-A', '', '', '', ''],         # a teacher of this school as a student
                ['S2', '9000000111', 7, '7-A', '', '', '', ''],         # a parent of this school as a student
                ['S3', '9000000021', 7, '7-A', '', '', '', ''],         # a student of school B
                ['S4', '9000000030', 7, '7-A', '', '', '', ''],         # an unrelated account
                ['S5', '9000000040', 7, '7-A', '9000000301', '', '', ''],    # this school's teacher as a parent
                ['S6', '9000000041', 7, '7-A', '9000000112', '', '', '']]    # school B's parent
        plan = self.preview(rows, [['T1', '9000000111', ''], ['T2', '9000000112', ''], ['T3', '9000000030', '']]).context['plan']
        self.assertEqual({r.status for r in plan.rows}, {'error'})
        self.assertEqual({r.message for r in plan.rows}, {self.generic()})
        text = self.preview(rows).content.decode()
        for forbidden in ('مدرسهٔ B', 'school B', self.b.name + ' ', 'B</td>'):
            self.assertNotIn(forbidden, text)
        self.confirm(rows)
        self.assertEqual(stranger.groups.count(), 0)                    # nothing was merged into the existing accounts
        self.assertEqual(set(parent_b.groups.values_list('name', flat=True)), {'Parent'})
        self.assertFalse(Student.objects.filter(national_id__in=['9000000040', '9000000041']).exists())

    def test_one_id_in_two_roles_inside_one_file_is_refused(self):
        rows = [['Ali Test', '9000000001', 7, '7-A', '9000000101', '', '', ''],
                ['Parent Dup', '9000000101', 7, '7-A', '', '', '', '']]    # the father's id as a student
        plan = self.preview(rows, [['Teach Er', '9000000101', '']]).context['plan']
        self.assertEqual([r.status for r in plan.rows], ['create', 'error', 'error'])
        self.assertNotIn('9000000101', ''.join(r.message for r in plan.rows))


class LoginSheetOnceTests(Base):
    def test_passwords_exist_only_in_the_download(self):
        import os
        import tempfile
        from django.db import connection
        from django.test import override_settings

        # The server may write only into this test's own temp dir, which is also where tempfile and MEDIA_ROOT point: files that
        # other processes (the Docker runtime, other tests) put into the global /tmp can no longer be mistaken for ours.
        with tempfile.TemporaryDirectory() as private:
            def files():
                return {os.path.join(d, f) for d, _s, fs in os.walk(private) for f in fs}

            with override_settings(MEDIA_ROOT=private), mock.patch.object(tempfile, 'tempdir', private):
                before = files()
                with self.assertNoLogs(level='DEBUG'):
                    response = self.confirm([['Ali Test', '9000000001', 7, '7-A', '9000000101', '', '', '']])
                passwords = [r[3] for r in load_workbook(io.BytesIO(response.content)).active.iter_rows(min_row=2, values_only=True) if r[3]]
                self.assertEqual(len(passwords), 2)
                self.assertEqual(files() - before, set())               # nothing written to disk by the server
        with connection.cursor() as cursor:                             # nowhere in the database in plain text
            for table in connection.introspection.table_names():
                cursor.execute(f'SELECT * FROM "{table}"')
                blob = repr(cursor.fetchall())
                for password in passwords:
                    self.assertNotIn(password, blob, table)
        self.assertNotIn('bulk_accounts', self.client.session)   # the uploaded rows are gone too
        self.assertFalse(any(p in repr(dict(self.client.session)) for p in passwords))
        shown = ' '.join(str(m) for m in self.client.get(reverse('dashboard:school_accounts')).context['messages'])
        self.assertFalse(any(p in shown for p in passwords))            # not in any message either
        again = self.client.post(reverse('dashboard:school_accounts_confirm'))   # no second download, nothing to re-send
        self.assertEqual(again.status_code, 302)
        self.assertEqual(self.client.get(reverse('dashboard:school_accounts_confirm')).status_code, 405)
        self.assertEqual(response['Cache-Control'], 'no-store')
