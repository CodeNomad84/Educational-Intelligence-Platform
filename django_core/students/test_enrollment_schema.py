"""Stage 2.2a-1 tests: Enrollment/ImportBatch schema, nullable links, no access change, backfill report.

All data is synthetic. Traceability: ADR-0011 stage 2.2a-1.
"""
import json
from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from schools.models import AcademicYear, School, SchoolClass
from students.access import PARENT, visible_students
from students.models import Attendance, Enrollment, Grade, ImportBatch, Student

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="A", code="a")
        self.other = School.objects.create(name="B", code="b")
        self.y1 = AcademicYear.objects.create(
            school=self.school, code="1403-1404", start_date=date(2024, 9, 23), end_date=date(2025, 6, 21))
        self.y2 = AcademicYear.objects.create(
            school=self.school, code="1404-1405", start_date=date(2025, 9, 23), end_date=date(2026, 6, 21),
            is_current=True)
        self.klass = SchoolClass.objects.create(school=self.school, title="10-A", academic_year="۱۴۰۴-۱۴۰۵", grade=10)
        self.n = 0

    def student(self, klass=None, grade=10, **kw):
        self.n += 1
        return Student.objects.create(
            first_name=f"S{self.n}", last_name="T", national_id=f"{self.n:010d}", grade=grade,
            phone_number="0", school=self.school, school_class=klass, **kw)


class EnrollmentSchemaTests(Base):
    def test_one_open_enrollment_per_student_year(self):
        s = self.student(self.klass)
        Enrollment.objects.create(student=s, academic_year=self.y2, school_class=self.klass, grade=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(student=s, academic_year=self.y2, school_class=self.klass, grade=10)
        # a class change closes one row and opens another
        Enrollment.objects.filter(student=s).update(ended_on=date(2026, 1, 1), started_on=date(2025, 9, 23))
        Enrollment.objects.create(student=s, academic_year=self.y2, school_class=self.klass, grade=10)
        # another year is independent
        Enrollment.objects.create(student=s, academic_year=self.y1, grade=9, status='promoted')

    def test_end_not_before_start(self):
        s = self.student()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(student=s, academic_year=self.y1, grade=9,
                                      started_on=date(2025, 1, 2), ended_on=date(2025, 1, 1))

    def test_clean_school_consistency(self):
        s = self.student(self.klass)
        foreign = SchoolClass.objects.create(school=self.other, title="10-A", academic_year="1404")
        with self.assertRaises(ValidationError) as ctx:
            Enrollment(student=s, academic_year=self.y2, school_class=foreign, grade=10).full_clean()
        self.assertIn("school_class", ctx.exception.message_dict)
        Enrollment(student=s, academic_year=self.y2, school_class=self.klass, grade=10).full_clean()
        with self.assertRaises(ValidationError):
            Enrollment(student=s, academic_year=self.y2, school_class=self.klass, grade=5).full_clean()

    def test_clean_rejects_a_student_of_another_school_than_the_year(self):
        s = self.student(self.klass)                       # a student of self.school
        other_year = AcademicYear.objects.create(
            school=self.other, code="1404-1405", start_date=date(2025, 9, 23), end_date=date(2026, 6, 21))
        with self.assertRaises(ValidationError) as ctx:
            Enrollment(student=s, academic_year=other_year, grade=10).full_clean()
        self.assertIn("academic_year", ctx.exception.message_dict)
        Enrollment(student=s, academic_year=self.y2, grade=10).full_clean()

    def test_history_is_protected_from_deletion(self):
        s = self.student(self.klass)
        enr = Enrollment.objects.create(student=s, academic_year=self.y2, school_class=self.klass, grade=10)
        Grade.objects.create(student=s, enrollment=enr, subject="math", exam_type="quiz", score=15, date=date(2026, 1, 1))
        for obj in (s, self.y2, self.klass, enr):
            with self.assertRaises(ProtectedError), transaction.atomic():
                obj.delete()

    def test_grade_and_attendance_links_are_nullable_and_optional(self):
        s = self.student()
        g = Grade.objects.create(student=s, subject="math", exam_type="quiz", score=10, date=date(2026, 1, 1))
        a = Attendance.objects.create(student=s, date=date(2026, 1, 2), status="present")
        self.assertIsNone(g.enrollment_id)
        self.assertIsNone(a.enrollment_id)

    def test_import_batch(self):
        batch = ImportBatch.objects.create(kind="grades", academic_year=self.y1, file_sha256="0" * 64, counts={"rows": 3})
        s = self.student()
        Enrollment.objects.create(student=s, academic_year=self.y1, grade=9, source="import", import_batch=batch)
        with self.assertRaises(ProtectedError), transaction.atomic():
            batch.delete()


class NoAccessChangeTests(Base):
    def test_enrollment_alone_grants_and_removes_nothing(self):
        """Stage 2.2a-1 guard: visibility is still decided by Student.school_class/grade, not by enrollments."""
        parent = User.objects.create_user(username="p")
        parent.groups.add(Group.objects.get_or_create(name=PARENT)[0])
        own = self.student(self.klass, parent_user=parent)
        other = self.student(self.klass)
        Enrollment.objects.create(student=other, academic_year=self.y2, school_class=self.klass, grade=10)
        self.assertEqual({s.pk for s in visible_students(parent)}, {own.pk})
        stranger = User.objects.create_user(username="x")
        self.assertEqual(list(visible_students(stranger)), [])


class CheckEnrollmentBackfillTests(Base):
    def report(self):
        out = StringIO()
        call_command('check_enrollment_backfill', '--json', stdout=out)
        return json.loads(out.getvalue())

    def test_counts_and_nothing_written(self):
        unresolved_cls = SchoolClass.objects.create(school=self.school, title="X", academic_year="404")
        noyear_cls = SchoolClass.objects.create(school=self.school, title="Y", academic_year="1399")
        a = self.student(self.klass)                       # candidate 1404-1405
        b = self.student(self.klass, grade=11)             # candidate, class grade (10) differs
        self.student(None)                                 # no class
        self.student(unresolved_cls)                       # unresolved year
        self.student(noyear_cls)                           # resolved, no AcademicYear row
        for s, day in ((a, date(2026, 1, 5)), (a, date(2024, 10, 1)), (a, date(2025, 7, 1)), (b, date(2026, 2, 1))):
            Grade.objects.create(student=s, subject="math", exam_type="quiz", score=10, date=day)
        Attendance.objects.create(student=a, date=date(2026, 1, 6), status="absent")
        counts_before = (Student.objects.count(), Grade.objects.count(), Enrollment.objects.count())

        r = self.report()
        self.assertEqual(r['students'], 5)
        self.assertEqual(r['students_with_candidate_enrollment'], 2)
        self.assertEqual(r['students_without_class_no_enrollment_would_be_created'], 1)
        self.assertEqual(r['students_class_year_blank_or_unresolved'], 1)
        self.assertEqual(r['students_class_year_resolved_but_no_academic_year_row'], 1)
        self.assertEqual(r['candidates_where_class_grade_differs_from_student_grade'], 1)
        # grades: 2026-01-05 -> 1404-1405 would_link; 2026-02-01 (b) would_link;
        # 2024-10-01 -> 1403-1404 but student has no enrollment there; 2025-07-01 -> in no year
        self.assertEqual(r['grades']['rows'], 4)
        self.assertEqual(r['grades']['would_link'], 2)
        self.assertEqual(r['grades']['year_found_but_student_has_no_enrollment_in_it_unlinked'], 1)
        self.assertEqual(r['grades']['date_in_no_year_unlinked'], 1)
        self.assertEqual(r['attendance']['would_link'], 1)
        self.assertEqual(counts_before, (Student.objects.count(), Grade.objects.count(), Enrollment.objects.count()))

    def test_already_linked_and_existing_enrollment_are_counted(self):
        s = self.student(self.klass)
        enr = Enrollment.objects.create(student=s, academic_year=self.y1, grade=9, status='promoted')
        Grade.objects.create(student=s, enrollment=enr, subject="math", exam_type="quiz", score=10, date=date(2025, 1, 1))
        Grade.objects.create(student=s, subject="math", exam_type="quiz", score=10, date=date(2025, 2, 1))  # y1, enrolled
        r = self.report()
        self.assertEqual(r['students_already_with_enrollment'], 1)
        self.assertEqual(r['grades']['already_linked'], 1)
        self.assertEqual(r['grades']['would_link'], 1)

    def test_empty_database_and_text_output(self):
        Student.objects.all().delete()
        out = StringIO()
        call_command('check_enrollment_backfill', stdout=out)
        self.assertIn('writes: none', out.getvalue())
