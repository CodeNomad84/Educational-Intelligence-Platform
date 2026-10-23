"""Slice 4a: referral to a counselor and the counselor pages. An unreferred student is a 404, another school is a 404,
wrong roles get 403, inactive accounts are refused; counselor notes are readable only by the counselor and the SchoolAdmin."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff
from students.access import visible_counselor_notes, visible_students
from students.enrollment_sync import ensure_current_enrollment
from students.models import CounselorNote, Referral, Student

User = get_user_model()
PASSWORD = 'Str0ng-demo-pass-77'


def make_user(name, group=None, school=None, **extra):
    user = User.objects.create_user(name, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    if school is not None and group != 'SchoolAdmin':
        SchoolStaff.objects.create(user=user, school=school)
    return user


class Base(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        self.b = School.objects.create(name='B', code='b')
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23),
                                        end_date=date(2026, 6, 21), is_current=True)
        mk = lambda school, title, grade: SchoolClass.objects.create(  # noqa: E731
            school=school, title=title, academic_year='1404-1405', grade=grade)
        self.c7, self.c8, self.cb = mk(self.a, '7-A', 7), mk(self.a, '8-A', 8), mk(self.b, '7-B', 7)
        self.s7 = self.student('Seven', self.c7, 7)
        self.s8 = self.student('Eight', self.c8, 8)
        self.sb = self.student('Bee', self.cb, 7)
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_b, school=self.b)
        self.lead = make_user('lead', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=self.lead, school=self.a, grade=7, academic_year='1404-1405')
        self.counselor = make_user('counselor', 'Counselor', self.a)
        self.counselor_b = make_user('counselor-b', 'Counselor', self.b)
        self.parent = make_user('parent', 'Parent')

    def student(self, name, klass, grade):
        student = Student.objects.create(first_name=name, last_name='X', national_id=f'98{Student.objects.count():08d}',
                                         grade=grade, phone_number='1', school=klass.school, school_class=klass)
        ensure_current_enrollment(student, source='manual')
        return student

    def refer(self, student, counselor, by=None, reason='Frequent absences'):
        return Referral.objects.create(student=student, school=student.school, counselor=counselor,
                                       referred_by=by or self.admin, reason=reason)


class ReferralCreationTests(Base):
    def post(self, user, student, counselor, reason='Needs support'):
        self.client.force_login(user)
        return self.client.post(reverse('dashboard:student_refer', args=[student.pk]),
                                {'counselor': counselor.pk, 'reason': reason})

    def test_admin_and_grade_lead_can_refer_within_scope(self):
        self.assertEqual(self.post(self.admin, self.s8, self.counselor).status_code, 302)
        self.assertEqual(self.post(self.lead, self.s7, self.counselor).status_code, 302)
        self.assertEqual(Referral.objects.count(), 2)
        r = Referral.objects.get(student=self.s7)
        self.assertEqual((r.school_id, r.referred_by_id, r.status), (self.a.pk, self.lead.pk, 'open'))

    def test_scope_limits(self):
        self.assertEqual(self.post(self.lead, self.s8, self.counselor).status_code, 404)        # another grade
        self.assertEqual(self.post(self.admin, self.sb, self.counselor).status_code, 404)       # another school
        self.assertEqual(self.post(self.admin_b, self.s7, self.counselor_b).status_code, 404)
        self.assertFalse(Referral.objects.exists())

    def test_a_counselor_of_another_school_or_an_inactive_one_is_refused(self):
        self.post(self.admin, self.s7, self.counselor_b)
        User.objects.filter(pk=self.counselor.pk).update(is_active=False)
        self.post(self.admin, self.s7, self.counselor)
        self.assertFalse(Referral.objects.exists())

    def test_duplicate_open_referral_is_refused(self):
        self.post(self.admin, self.s7, self.counselor)
        self.post(self.admin, self.s7, self.counselor, 'again')
        self.assertEqual(Referral.objects.count(), 1)

    def test_other_roles_get_403(self):
        for user in (self.parent, self.counselor, make_user('teacher', 'Teacher', self.a),
                     make_user('root', is_superuser=True)):
            self.assertEqual(self.post(user, self.s7, self.counselor).status_code, 403, user.username)

    def test_the_360_page_offers_the_form_and_lists_referrals_to_admin_but_not_to_parents(self):
        self.refer(self.s7, self.counselor, reason='Visible reason')
        s7_parent = make_user('p7', 'Parent')
        Student.objects.filter(pk=self.s7.pk).update(parent_user=s7_parent)
        self.client.force_login(self.admin)
        page = self.client.get(reverse('dashboard:student_360', args=[self.s7.pk]))
        self.assertContains(page, reverse('dashboard:student_refer', args=[self.s7.pk]))
        self.assertContains(page, 'Visible reason')
        self.client.force_login(s7_parent)
        page = self.client.get(reverse('dashboard:student_360', args=[self.s7.pk]))
        self.assertNotContains(page, 'Visible reason')


class CounselorAccessTests(Base):
    def setUp(self):
        super().setUp()
        self.referral = self.refer(self.s7, self.counselor)

    def test_the_counselor_sees_only_referred_students(self):
        self.assertEqual(set(visible_students(self.counselor).values_list('pk', flat=True)), {self.s7.pk})
        self.client.force_login(self.counselor)
        home = self.client.get(reverse('dashboard:counselor_home')).content.decode()
        self.assertIn('Seven', home)
        self.assertNotIn('Eight', home)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk])).status_code, 200)

    def test_unreferred_other_school_and_other_counselors_cases_are_404(self):
        foreign_case = Referral.objects.create(student=self.sb, school=self.b, counselor=self.counselor_b,
                                               referred_by=self.admin_b, reason='b case')
        self.client.force_login(self.counselor)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_case', args=[foreign_case.pk])).status_code, 404)
        self.client.force_login(self.counselor_b)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk])).status_code, 404)
        self.assertEqual(self.client.get(f'/students/{self.s7.pk}/').status_code, 403)   # no list/detail pages for this role

    def test_the_case_page_shows_the_summary_and_the_reason_and_is_read_only(self):
        self.client.force_login(self.counselor)
        page = self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk]))
        self.assertContains(page, 'Frequent absences')
        self.assertContains(page, self.s7.national_id)
        self.assertEqual(self.client.get(reverse('dashboard:student_360', args=[self.s7.pk])).status_code, 403)

    def test_notes_are_visible_only_to_the_counselor_and_the_school_admin(self):
        self.client.force_login(self.counselor)
        self.client.post(reverse('dashboard:counselor_case', args=[self.referral.pk]), {'text': 'Private counselor note'})
        note = CounselorNote.objects.get()
        self.assertEqual((note.author_id, note.referral_id), (self.counselor.pk, self.referral.pk))
        self.assertContains(self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk])),
                            'Private counselor note')
        readers = {self.counselor: 1, self.admin: 1, self.admin_b: 0, self.counselor_b: 0, self.lead: 0, self.parent: 0}
        for user, count in readers.items():
            self.assertEqual(visible_counselor_notes(user).count(), count, user.username)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard:student_360', args=[self.s7.pk])), 'Private counselor note')
        self.client.force_login(self.lead)
        self.assertNotContains(self.client.get(reverse('dashboard:student_360', args=[self.s7.pk])), 'Private counselor note')

    def test_closing_the_case_ends_the_access(self):
        self.client.force_login(self.counselor)
        self.client.post(reverse('dashboard:counselor_close', args=[self.referral.pk]))
        self.referral.refresh_from_db()
        self.assertEqual(self.referral.status, 'closed')
        self.assertEqual(visible_students(self.counselor).count(), 0)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk])).status_code, 404)

    def test_a_counselor_who_moved_school_or_lost_staff_status_sees_nothing(self):
        SchoolStaff.objects.filter(user=self.counselor).update(school=self.b)
        self.assertEqual(visible_students(self.counselor).count(), 0)

    def test_wrong_roles_get_403_and_inactive_is_refused(self):
        urls = [reverse('dashboard:counselor_home'), reverse('dashboard:counselor_case', args=[self.referral.pk])]
        for user in (self.admin, self.lead, self.parent, make_user('teacher', 'Teacher', self.a),
                     make_user('root', is_superuser=True)):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, (user.username, url))
        User.objects.filter(pk=self.counselor.pk).update(is_active=False)
        self.client.force_login(User.objects.get(pk=self.counselor.pk))
        self.assertEqual(self.client.get(urls[0]).status_code, 302)
        self.assertEqual(visible_students(User.objects.get(pk=self.counselor.pk)).count(), 0)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard:counselor_home')).status_code, 302)


class SchoolAdminCounselorPagesTests(Base):
    def test_the_school_admin_creates_a_counselor_account(self):
        self.client.force_login(self.admin)
        url = reverse('dashboard:school_staff', args=['counselors'])
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(url, {'username': 'new-counselor', 'first_name': 'N', 'last_name': 'L',
                                      'password1': PASSWORD, 'password2': PASSWORD})
        user = User.objects.get(username='new-counselor')
        self.assertRedirects(resp, reverse('dashboard:school_staff_detail', args=['counselors', user.pk]))
        self.assertEqual((user.school_staff.school_id, user.groups.get().name), (self.a.pk, 'Counselor'))
        self.assertEqual(self.client.get(resp['Location']).status_code, 200)
        other = reverse('dashboard:school_staff_detail', args=['counselors', self.counselor_b.pk])
        self.assertEqual(self.client.get(other).status_code, 404)
