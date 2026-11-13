"""Audit log (2.4): who viewed/changed what, with user, school, object, action and time - and no content. Visible only to the
SchoolAdmin of the school. Synthetic data only."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from schools import audit
from schools.models import (
    AcademicYear, AuditEvent, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolStaff, TeacherAssignment)
from students.enrollment_sync import ensure_current_enrollment
from students.models import CounselorNote, Grade, Recommendation, Referral, Student

User = get_user_model()
PASSWORD = 'Str0ng-demo-pass-77'
SECRET = 'SECRET-CONTENT-123'


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
        self.b = School.objects.create(name='B', code='b')
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23),
                                        end_date=date(2026, 6, 21), is_current=True)
        self.klass = SchoolClass.objects.create(school=self.a, title='7-A', academic_year='1404-1405', grade=7)
        self.klass_b = SchoolClass.objects.create(school=self.b, title='7-B', academic_year='1404-1405', grade=7)
        self.student = self.make_student('Seven', self.klass, father_phone='09110000099')
        self.student_b = self.make_student('Bee', self.klass_b)
        self.admin = make_user('admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.admin_b = make_user('admin-b', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.admin_b, school=self.b)
        self.lead = make_user('lead', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=self.lead, school=self.a, grade=7, academic_year='1404-1405')
        self.teacher = make_user('teacher', 'Teacher', self.a)
        self.assign = TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass, subject='math')
        self.counselor = make_user('counselor', 'Counselor', self.a)
        self.parent = make_user('parent', 'Parent')
        Student.objects.filter(pk=self.student.pk).update(parent_user=self.parent)

    def make_student(self, name, klass, **extra):
        student = Student.objects.create(first_name=name, last_name='X', national_id=f'94{Student.objects.count():08d}',
                                         grade=7, phone_number='1', school=klass.school, school_class=klass, **extra)
        ensure_current_enrollment(student, source='manual')
        return student

    def last(self):
        return AuditEvent.objects.order_by('-pk').first()

    def assertEvent(self, event, user, action, school, obj=None, detail=''):
        self.assertEqual((event.username, event.action, event.school_id, event.detail), (user.username, action, school.pk, detail))
        self.assertEqual(event.user_id, user.pk)
        if obj is not None:
            self.assertEqual((event.object_type, event.object_id), (type(obj).__name__, str(obj.pk)))
        self.assertIsNotNone(event.created_at)


class EventTests(Base):
    def test_views_of_the_360_page_and_the_detail_page(self):
        self.client.force_login(self.admin)
        self.client.get(reverse('dashboard:student_360', args=[self.student.pk]))
        self.assertEvent(self.last(), self.admin, audit.VIEW_360, self.a, self.student)
        self.client.force_login(self.parent)
        self.client.get(reverse('dashboard:student_detail', args=[self.student.pk]))
        self.assertEvent(self.last(), self.parent, audit.VIEW_DETAIL, self.a, self.student)

    def test_a_refused_request_records_nothing(self):
        before = AuditEvent.objects.count()
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(reverse('dashboard:student_360', args=[self.student.pk])).status_code, 404)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('dashboard:student_360', args=[self.student.pk])).status_code, 403)
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_referral_case_view_phone_display_note_and_close(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:student_refer', args=[self.student.pk]),
                         {'counselor': self.counselor.pk, 'reason': SECRET})
        referral = Referral.objects.get()
        self.assertEvent(self.last(), self.admin, audit.REFERRAL_CREATE, self.a, referral)
        self.client.force_login(self.counselor)
        self.client.get(reverse('dashboard:counselor_case', args=[referral.pk]))
        events = list(AuditEvent.objects.order_by('-pk')[:2])
        self.assertEvent(events[0], self.counselor, audit.SHOW_PARENT_PHONES, self.a, self.student)
        self.assertEvent(events[1], self.counselor, audit.VIEW_CASE, self.a, referral)
        self.client.post(reverse('dashboard:counselor_case', args=[referral.pk]), {'text': SECRET})
        note = CounselorNote.objects.get()
        notes = AuditEvent.objects.filter(action=audit.NOTE_ADD)
        self.assertEqual(notes.count(), 1)
        self.assertEvent(notes.get(), self.counselor, audit.NOTE_ADD, self.a, note)
        self.client.post(reverse('dashboard:counselor_close', args=[referral.pk]))
        self.assertEvent(self.last(), self.counselor, audit.REFERRAL_CLOSE, self.a, referral)

    def test_grade_entry_and_delete_and_recommendation(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse('dashboard:teacher_grades', args=[self.assign.pk]),
                         {'exam_type': 'quiz', 'date': '2026-01-10', f'score_{self.student.pk}': '17'})
        grade = Grade.objects.get()
        self.assertEvent(self.last(), self.teacher, audit.GRADE_ADD, self.a, grade)
        self.client.post(reverse('dashboard:teacher_student', args=[self.assign.pk, self.student.pk]),
                         {'text': SECRET, 'visibility': 'student'})
        self.assertEvent(self.last(), self.teacher, audit.RECOMMENDATION_ADD, self.a, Recommendation.objects.get(),
                         detail='student_visible')
        self.client.post(reverse('dashboard:teacher_grade_delete', args=[self.assign.pk, grade.pk]))
        last = self.last()
        self.assertEqual((last.action, last.object_type, last.object_id), (audit.GRADE_DELETE, 'Grade', str(grade.pk)))

    def test_account_creation(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:school_staff', args=['teachers']), {
            'username': 'new-t', 'first_name': 'N', 'last_name': 'L', 'password1': PASSWORD, 'password2': PASSWORD})
        self.assertEvent(self.last(), self.admin, audit.STAFF_ACCOUNT_CREATE, self.a, User.objects.get(username='new-t'),
                         detail='teachers')
        self.client.post(reverse('dashboard:student_account', args=[self.student.pk]),
                         {'username': 'new-s', 'password1': PASSWORD, 'password2': PASSWORD})
        self.assertEvent(self.last(), self.admin, audit.STUDENT_ACCOUNT_CREATE, self.a, self.student)


class NoContentTests(Base):
    def test_no_event_field_holds_content(self):
        """Run the content-bearing actions with a marker text and phone numbers; none of it may appear in the log."""
        self.client.force_login(self.teacher)
        self.client.post(reverse('dashboard:teacher_student', args=[self.assign.pk, self.student.pk]),
                         {'text': SECRET, 'visibility': 'staff'})
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:student_refer', args=[self.student.pk]),
                         {'counselor': self.counselor.pk, 'reason': SECRET})
        self.client.force_login(self.counselor)
        referral = Referral.objects.get()
        self.client.get(reverse('dashboard:counselor_case', args=[referral.pk]))
        self.client.post(reverse('dashboard:counselor_case', args=[referral.pk]), {'text': SECRET})
        self.assertGreaterEqual(AuditEvent.objects.count(), 5)
        for event in AuditEvent.objects.all():
            blob = ' '.join(str(v) for v in (event.username, event.roles, event.action, event.object_type, event.object_id,
                                             event.detail))
            for forbidden in (SECRET, '09110000099', 'Seven'):
                self.assertNotIn(forbidden, blob)

    def test_events_are_append_only(self):
        event = audit.record(self.admin, audit.VIEW_360, self.student)
        event.detail = 'changed'
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        self.assertEqual(AuditEvent.objects.get(pk=event.pk).detail, '')


class AuditPageTests(Base):
    def setUp(self):
        super().setUp()
        audit.record(self.admin, audit.VIEW_360, self.student)
        audit.record(self.admin_b, audit.VIEW_360, self.student_b)

    def test_the_school_admin_sees_only_the_own_schools_events(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse('dashboard:school_audit'))
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn('admin', body)
        self.assertIn(f'#{self.student.pk}', body)
        self.assertNotIn('admin-b', body)
        self.client.force_login(self.admin_b)
        self.assertIn('admin-b', self.client.get(reverse('dashboard:school_audit')).content.decode())
        self.assertNotIn(f'Student #{self.student.pk}<', self.client.get(reverse('dashboard:school_audit')).content.decode()
                         .replace(f'Student #{self.student_b.pk}', ''))

    def test_the_filter(self):
        audit.record(self.admin, audit.VIEW_DETAIL, self.student)
        self.client.force_login(self.admin)
        body = self.client.get(reverse('dashboard:school_audit') + f'?action={audit.VIEW_DETAIL}').content.decode()
        self.assertIn('<td>view_student_detail</td>', body)
        self.assertNotIn('<td>view_student_360</td>', body)

    def test_other_roles_get_403_and_inactive_or_anonymous_are_refused(self):
        url = reverse('dashboard:school_audit')
        for user in (self.teacher, self.lead, self.counselor, self.parent, make_user('root', is_superuser=True)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.client.force_login(User.objects.get(pk=self.admin.pk))
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_the_admin_site_does_not_offer_the_log_to_anyone(self):
        root = make_user('root2', is_superuser=True, is_staff=True)
        self.client.force_login(root)
        self.assertEqual(self.client.get('/admin/schools/auditevent/').status_code, 403)
