"""Owner corrections A2-A4: counselor notes access (counselor, Grade Lead of the grade read-only, SchoolAdmin; nobody else),
parents' phone numbers only on the case page, recommendation visibility (staff-only by default). Synthetic data only."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from schools.models import (
    AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff, TeacherAssignment)
from students.access import visible_counselor_notes, visible_recommendations
from students.enrollment_sync import ensure_current_enrollment
from students.models import CounselorNote, Recommendation, Referral, Student

User = get_user_model()


def make_user(name, group=None, school=None, **extra):
    user = User.objects.create_user(name, password='x', **extra)
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    if school is not None:
        SchoolStaff.objects.create(user=user, school=school)
    return user


class Base(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        AcademicYear.objects.create(school=self.a, code='1404-1405', start_date=date(2025, 9, 23),
                                    end_date=date(2026, 6, 21), is_current=True)
        mk = lambda title, grade: SchoolClass.objects.create(  # noqa: E731
            school=self.a, title=title, academic_year='1404-1405', grade=grade)
        self.c7, self.c8 = mk('7-A', 7), mk('8-A', 8)
        self.parent = make_user('parent', 'Parent')
        self.s7 = self.student('Seven', self.c7, 7, parent_user=self.parent, father_phone='09110000007',
                               mother_phone='09120000007')
        self.s8 = self.student('Eight', self.c8, 8)
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.lead7 = make_user('lead7', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=self.lead7, school=self.a, grade=7, academic_year='1404-1405')
        self.lead8 = make_user('lead8', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=self.lead8, school=self.a, grade=8, academic_year='1404-1405')
        self.counselor = make_user('counselor', 'Counselor', self.a)
        self.teacher = make_user('teacher', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.c7, subject='math')
        self.student_user = make_user('student', 'Student')
        Student.objects.filter(pk=self.s7.pk).update(student_user=self.student_user)
        self.referral = Referral.objects.create(student=self.s7, school=self.a, counselor=self.counselor,
                                                referred_by=self.admin, reason='Reason text')
        self.note = CounselorNote.objects.create(referral=self.referral, author=self.counselor, text='Secret counselor note')

    def student(self, name, klass, grade, **extra):
        student = Student.objects.create(first_name=name, last_name='X', national_id=f'95{Student.objects.count():08d}',
                                         grade=grade, phone_number='1', school=self.a, school_class=klass, **extra)
        ensure_current_enrollment(student, source='manual')
        return student


class CounselorNoteAccessTests(Base):
    def test_who_reads_counselor_notes(self):
        expected = {self.counselor: 1, self.admin: 1, self.lead7: 1, self.lead8: 0, self.teacher: 0, self.parent: 0,
                    self.student_user: 0}
        for user, count in expected.items():
            self.assertEqual(visible_counselor_notes(user).count(), count, user.username)

    def test_the_pages(self):
        for user, shows in ((self.admin, True), (self.lead7, True), (self.lead8, None), (self.parent, False)):
            self.client.force_login(user)
            resp = self.client.get(reverse('dashboard:student_360', args=[self.s7.pk]))
            if shows is None:
                self.assertEqual(resp.status_code, 404, user.username)      # the other grade's lead cannot even open it
                continue
            self.assertEqual(resp.status_code, 200, user.username)
            (self.assertContains if shows else self.assertNotContains)(resp, 'Secret counselor note')
        for user in (self.teacher, self.student_user):
            self.client.force_login(user)
            for url in (reverse('dashboard:student_360', args=[self.s7.pk]), reverse('dashboard:me_home')):
                body = self.client.get(url).content.decode()
                self.assertNotIn('Secret counselor note', body, (user.username, url))

    def test_the_grade_lead_cannot_write_or_close(self):
        self.client.force_login(self.lead7)
        for url in (reverse('dashboard:counselor_case', args=[self.referral.pk]),
                    reverse('dashboard:counselor_close', args=[self.referral.pk])):
            self.assertEqual(self.client.post(url, {'text': 'x'}).status_code, 403)
        self.assertEqual(CounselorNote.objects.count(), 1)
        self.referral.refresh_from_db()
        self.assertEqual(self.referral.status, 'open')

    def test_the_case_page_heading_and_parent_phones(self):
        self.client.force_login(self.counselor)
        page = self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk]))
        self.assertContains(page, 'یادداشت‌های مشاور (فقط شما، مسئول پایه و مدیر مدرسه)')
        self.assertContains(page, '09110000007')
        self.assertContains(page, '09120000007')


class ParentPhonesOnlyOnTheCasePageTests(Base):
    PHONES = ('09110000007', '09120000007')

    def test_no_other_page_or_api_shows_them(self):
        for user in (self.admin, self.lead7, self.parent, self.counselor, self.teacher, self.student_user):
            self.client.force_login(user)
            for url in (reverse('dashboard:student_list'), reverse('dashboard:student_detail', args=[self.s7.pk]),
                        reverse('dashboard:student_360', args=[self.s7.pk]), reverse('dashboard:counselor_home'),
                        reverse('dashboard:grade_dashboard'), reverse('dashboard:me_home'), '/api/students/',
                        f'/api/students/{self.s7.pk}/'):
                resp = self.client.get(url)
                for phone in self.PHONES:
                    self.assertNotIn(phone, resp.content.decode(), (user.username, url))

    def test_a_closed_case_no_longer_shows_them(self):
        Referral.objects.filter(pk=self.referral.pk).update(status='closed')
        self.client.force_login(self.counselor)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk])).status_code, 404)


class RecommendationVisibilityTests(Base):
    def setUp(self):
        super().setUp()
        self.staff_only = Recommendation.objects.create(student=self.s7, author=self.teacher, subject='math',
                                                        text='Staff only text')
        self.for_student = Recommendation.objects.create(student=self.s7, author=self.teacher, subject='math',
                                                         text='Student can read this', visible_to_student=True)

    def texts(self, user):
        return set(visible_recommendations(user).values_list('text', flat=True))

    def test_who_reads_what(self):
        both = {'Staff only text', 'Student can read this'}
        only_shared = {'Student can read this'}
        self.assertEqual(self.texts(self.student_user), only_shared)
        self.assertEqual(self.texts(self.parent), only_shared)
        for user in (self.teacher, self.admin, self.lead7, self.counselor):
            self.assertEqual(self.texts(user), both, user.username)
        self.assertEqual(self.texts(self.lead8), set())
        self.assertEqual(self.texts(make_user('other-teacher', 'Teacher', self.a)), set())

    def test_the_student_page_never_shows_staff_only_text(self):
        self.client.force_login(self.student_user)
        body = self.client.get(reverse('dashboard:me_home')).content.decode()
        self.assertIn('Student can read this', body)
        self.assertNotIn('Staff only text', body)

    def test_the_teacher_form_defaults_to_staff_only_and_warns(self):
        self.client.force_login(self.teacher)
        assign = TeacherAssignment.objects.get(teacher=self.teacher)
        url = reverse('dashboard:teacher_student', args=[assign.pk, self.s7.pk])
        page = self.client.get(url)
        self.assertContains(page, 'فقط کادر مدرسه')
        self.assertContains(page, 'قابل نمایش به دانش‌آموز')
        self.assertContains(page, 'دانش‌آموز (و والدین) این متن را خواهند خواند')
        self.client.post(url, {'text': 'Default visibility', 'visibility': 'staff'})
        self.client.post(url, {'text': 'Shared with student', 'visibility': 'student'})
        self.assertFalse(Recommendation.objects.get(text='Default visibility').visible_to_student)
        self.assertTrue(Recommendation.objects.get(text='Shared with student').visible_to_student)
        self.assertEqual(self.client.post(url, {'text': 'no choice'}).status_code, 200)    # the choice is required
        self.assertFalse(Recommendation.objects.filter(text='no choice').exists())

    def test_existing_recommendations_default_to_staff_only(self):
        self.assertFalse(Recommendation._meta.get_field('visible_to_student').default)
