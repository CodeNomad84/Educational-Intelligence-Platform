"""Stage 2.2a-4a tests: ensure_current_enrollment, its call sites, and check_access_switch_ready (ADR-0011)."""
import json
from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, TeacherAssignment
from students.access import ADMIN, GRADE_LEAD, TEACHER
from students.enrollment_sync import ensure_current_enrollment
from students.models import Enrollment, Student

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='A', code='a')
        self.y_old = AcademicYear.objects.create(
            school=self.school, code='1403-1404', start_date=date(2024, 9, 23), end_date=date(2025, 6, 21))
        self.y_cur = AcademicYear.objects.create(
            school=self.school, code='1404-1405', start_date=date(2025, 9, 23), end_date=date(2026, 6, 21), is_current=True)
        self.c10a = SchoolClass.objects.create(school=self.school, title='10-A', academic_year='۱۴۰۴-۱۴۰۵', grade=10)
        self.c10b = SchoolClass.objects.create(school=self.school, title='10-B', academic_year='1404', grade=10)
        self.c_old = SchoolClass.objects.create(school=self.school, title='9-A', academic_year='1403/1404', grade=9)
        self.n = 0

    def student(self, klass=None, grade=10):
        self.n += 1
        return Student.objects.create(first_name=f'S{self.n}', last_name='T', national_id=f'{self.n:010d}',
                                      grade=grade, phone_number='0', school=self.school, school_class=klass)

    def open_rows(self, student):
        return list(Enrollment.objects.filter(student=student, ended_on__isnull=True))


class EnsureTests(Base):
    def test_created_unchanged_and_grade_update(self):
        s = self.student(self.c10a)
        self.assertEqual(ensure_current_enrollment(s), 'created')
        row, = self.open_rows(s)
        self.assertEqual((row.academic_year_id, row.school_class_id, row.grade, row.status, row.source),
                         (self.y_cur.pk, self.c10a.pk, 10, 'active', 'manual'))
        self.assertEqual(ensure_current_enrollment(s), 'unchanged')
        s.grade = 10
        self.assertEqual(Enrollment.objects.filter(student=s).count(), 1)

    def test_class_change_closes_one_row_and_opens_another(self):
        s = self.student(self.c10a)
        ensure_current_enrollment(s, today=date(2025, 10, 1))
        s.school_class = self.c10b
        s.save()
        self.assertEqual(ensure_current_enrollment(s, today=date(2026, 1, 5)), 'class_changed')
        rows = list(Enrollment.objects.filter(student=s).order_by('started_on'))
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0].ended_on, rows[0].school_class_id), (date(2026, 1, 5), self.c10a.pk))
        self.assertEqual((rows[1].ended_on, rows[1].school_class_id), (None, self.c10b.pk))

    def test_skips_are_reported_not_guessed_and_not_raised(self):
        no_class = self.student(self.c10a)
        Student.objects.filter(pk=no_class.pk).update(school_class=None)
        no_class.refresh_from_db()
        self.assertEqual(ensure_current_enrollment(no_class), 'no_class')
        self.assertEqual(ensure_current_enrollment(self.student(self.c_old, grade=9)), 'class_year_mismatch')
        bad = SchoolClass.objects.create(school=self.school, title='X', academic_year='404', grade=10)
        self.assertEqual(ensure_current_enrollment(self.student(bad)), 'class_year_mismatch')
        self.assertEqual(ensure_current_enrollment(self.student(self.c10a, grade=11)), 'class_grade_conflict')
        self.assertEqual(Enrollment.objects.count(), 0)
        AcademicYear.objects.filter(pk=self.y_cur.pk).update(is_current=False)
        self.assertEqual(ensure_current_enrollment(self.student(self.c10a)), 'no_current_year')

    def test_past_enrollments_are_never_touched(self):
        s = self.student(self.c10a)
        old = Enrollment.objects.create(student=s, academic_year=self.y_old, grade=9, status='promoted', source='import')
        ensure_current_enrollment(s)
        old.refresh_from_db()
        self.assertEqual((old.grade, old.status, old.ended_on), (9, 'promoted', None))
        self.assertEqual(Enrollment.objects.filter(student=s).count(), 2)


class CallSiteTests(Base):
    def test_admin_dashboard_and_api_paths_keep_enrollment_current(self):
        admin_user = User.objects.create_user(username='adm')
        admin_user.groups.add(Group.objects.get_or_create(name=ADMIN)[0])
        SchoolMembership.objects.create(user=admin_user, school=self.school)  # S2b: writes need a school
        # API create
        client = APIClient()
        client.force_authenticate(admin_user)
        resp = client.post('/api/students/', {
            'first_name': 'Api', 'last_name': 'T', 'national_id': '1111111111', 'grade': 10,
            'phone_number': '0', 'school_class': self.c10a.pk}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        api = Student.objects.get(national_id='1111111111')
        self.assertEqual(len(self.open_rows(api)), 1)
        # API update moves the class
        resp = client.patch(f'/api/students/{api.pk}/', {'school_class': self.c10b.pk}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Enrollment.objects.filter(student=api).count(), 2)
        # dashboard form
        self.client.force_login(admin_user)
        resp = self.client.post('/students/add/' if False else self._add_url(), {
            'first_name': 'Web', 'last_name': 'T', 'national_id': '2222222222', 'grade': 10,
            'phone_number': '0', 'school_class': self.c10a.pk})
        self.assertEqual(resp.status_code, 302, getattr(resp, 'content', b'')[:300])
        self.assertEqual(len(self.open_rows(Student.objects.get(national_id='2222222222'))), 1)

    def _add_url(self):
        from django.urls import reverse
        return reverse('dashboard:student_add')

    def test_live_import_keeps_enrollment_current(self):
        from students.views import _write_import_row, ImportRow, ClassLinkPlan
        plan = ClassLinkPlan(self.school.pk)
        plan.decisions[0] = self.c10a.pk
        row = ImportRow(0, '3333333333', {
            'first_name': 'Imp', 'last_name': 'T', 'national_id': '3333333333', 'phone_number': '0',
            'father_job': '', 'mother_job': '', 'grade': 10}, '10-A')
        student, created, link = _write_import_row(row, plan)
        self.assertTrue(created and link)
        e, = self.open_rows(student)
        self.assertEqual(e.source, 'import')


class PreflightTests(Base):
    def run_cmd(self):
        out = StringIO()
        try:
            call_command('check_access_switch_ready', '--json', stdout=out)
            failed = False
        except CommandError:
            failed = True
        return json.loads(out.getvalue()), failed

    def test_ready_when_everything_is_in_step(self):
        s = self.student(self.c10a)
        ensure_current_enrollment(s)
        lead = User.objects.create_user(username='lead')
        GradeLeadAssignment.objects.create(user=lead, school=self.school, grade=10, academic_year='1404-1405')
        t = User.objects.create_user(username='t')
        TeacherAssignment.objects.create(teacher=t, school_class=self.c10a, subject='math')
        report, failed = self.run_cmd()
        self.assertEqual((report['verdict'], failed, report['writes']), ('READY', False, 'none'))

    def test_every_blocker_is_counted_and_exit_code_is_nonzero(self):
        self.student(self.c10a)                                    # no enrollment at all
        drift = self.student(self.c10b)
        Enrollment.objects.create(student=drift, academic_year=self.y_cur, school_class=self.c10a, grade=10)  # class disagrees
        self.student(self.c_old, grade=9)                         # stale mirror: informational only
        self.student(self.c10a, grade=11)                         # class grade conflict: would vanish for staff
        lead = User.objects.create_user(username='lead')
        for year in ('404', '1405-1406', '1403-1404'):
            GradeLeadAssignment.objects.create(user=lead, school=self.school, grade=10, academic_year=year)
        t = User.objects.create_user(username='t')
        TeacherAssignment.objects.create(teacher=t, school_class=self.c10b, subject='physics')  # no current enrollments in 10-B
        TeacherAssignment.objects.create(teacher=t, school_class=self.c10a, subject='')         # grants nothing: informational
        empty = SchoolClass.objects.create(school=self.school, title='12-A', academic_year='1404-1405', grade=12)
        TeacherAssignment.objects.create(teacher=t, school_class=empty, subject='math')         # no students at all: not a blocker
        other = School.objects.create(name='B', code='b')
        SchoolClass.objects.create(school=other, title='c', academic_year='1404')
        Student.objects.create(first_name='O', last_name='T', national_id='9999999999', grade=10, phone_number='0',
                               school_class=other.classes.first())
        report, failed = self.run_cmd()
        self.assertTrue(failed)
        self.assertEqual(report['verdict'], 'NOT READY')
        self.assertEqual(report['students_missing_current_enrollment'], 1)
        self.assertEqual(report['enrollment_mirror_disagreements'], 1)
        self.assertEqual(report['info_students_with_stale_or_unresolved_class_year'], 1)
        self.assertEqual(report['students_class_grade_conflict_would_vanish'], 1)
        self.assertEqual(report['grade_lead_assignments_with_unresolved_year'], 1)
        self.assertEqual(report['grade_lead_assignments_year_has_no_academic_year_row'], 1)
        self.assertEqual(report['grade_lead_assignments_year_not_current'], 1)
        self.assertEqual(report['schools_with_students_but_no_current_year'], 1)
        self.assertEqual(report['teacher_assignments_class_without_current_enrollments'], 1)
        self.assertEqual(report['info_teacher_assignments_with_blank_or_invalid_subject_grant_nothing'], 1)

    def test_continuing_student_without_current_enrollment_is_reported_as_info(self):
        gone = self.student(self.c10a)
        Enrollment.objects.create(student=gone, academic_year=self.y_old, grade=9, status='graduated')
        stay = self.student(self.c_old, grade=9)       # mirror still points to last year's class
        Enrollment.objects.create(student=stay, academic_year=self.y_old, grade=9, status='promoted')
        report, _failed = self.run_cmd()
        self.assertEqual(report['info_continuing_students_without_current_enrollment'], 1)

    def test_empty_database_is_ready_and_writes_nothing(self):
        before = (Student.objects.count(), Enrollment.objects.count())
        report, failed = self.run_cmd()
        self.assertEqual((report['verdict'], failed), ('READY', False))
        self.assertEqual(before, (Student.objects.count(), Enrollment.objects.count()))
