"""S2 tests: backfill_student_school (changes/0010 S2). Synthetic data only.

Rules: a student that already has a school is never changed; a class gives its school; no class and exactly one
School gives that School; several Schools: nothing is guessed. Dry-run default, batch-logged, revertible.
"""
import json
import os
import tempfile
from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from schools.models import AcademicYear, School, SchoolClass
from students.access import visible_students
from students.management.commands.backfill_student_school import plan_assignments
from students.models import Enrollment, Student

User = get_user_model()


class PlanTests(SimpleTestCase):
    def test_rules_in_order(self):
        rows = [(1, 7), (2, None), (3, 8)]
        self.assertEqual(plan_assignments(rows, [5]), ({1: 7, 2: 5, 3: 8}, 0))

    def test_several_schools_guess_nothing_for_classless_students(self):
        rows = [(1, 7), (2, None)]
        self.assertEqual(plan_assignments(rows, [5, 6]), ({1: 7}, 1))

    def test_no_school_guess_nothing(self):
        self.assertEqual(plan_assignments([(1, None)], []), ({}, 1))

    def test_a_class_school_wins_over_the_only_school(self):
        self.assertEqual(plan_assignments([(1, 9)], [5]), ({1: 9}, 0))


class BackfillStudentSchoolTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.school = School.objects.order_by("pk").first() or School.objects.create(name="A", code="a")
        self.assertEqual(School.objects.count(), 1)
        self.n = 0

    def path(self, name="batch.json"):
        return os.path.join(self.tmp.name, name)

    def student(self, school="none", **extra):
        self.n += 1
        student = Student.objects.create(
            first_name="S", last_name=str(self.n), national_id=f"30000000{self.n:02d}", grade=7, phone_number="1",
            **extra)
        if school == "keep":
            pass  # save() derived the school from the class
        elif school == "none":
            Student.objects.filter(pk=student.pk).update(school=None)
        else:
            Student.objects.filter(pk=student.pk).update(school=school)
        return Student.objects.get(pk=student.pk)

    def run_cmd(self, *args):
        out = StringIO()
        call_command("backfill_student_school", *args, stdout=out)
        return out.getvalue()

    def run_json(self, *args):
        return json.loads(self.run_cmd(*args, "--json"))

    def test_dry_run_is_the_default_and_writes_nothing(self):
        s = self.student()
        report = self.run_json()
        self.assertEqual((report["students_without_school"], report["would_set_to_the_only_school"]), (1, 1))
        self.assertIn("dry-run", report["mode"])
        s.refresh_from_db()
        self.assertIsNone(s.school_id)

    def test_apply_needs_a_batch_file(self):
        self.student()
        with self.assertRaises(CommandError):
            self.run_cmd("--apply")

    def test_apply_with_one_school_fills_classless_students_only_where_null(self):
        keep = self.student(school=self.school)
        a, b = self.student(), self.student()
        self.run_cmd("--apply", "--batch-file", self.path())
        for s in (keep, a, b):
            s.refresh_from_db()
        self.assertEqual((keep.school_id, a.school_id, b.school_id), (self.school.pk,) * 3)
        with open(self.path(), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(sorted(i["student_id"] for i in data["assignments"]), sorted([a.pk, b.pk]))

    def test_a_student_that_already_has_a_school_is_never_changed(self):
        other = School.objects.create(name="B", code="b")
        s = self.student(school=other)
        self.run_cmd("--apply", "--batch-file", self.path())
        s.refresh_from_db()
        self.assertEqual(s.school_id, other.pk)

    def test_with_several_schools_classless_students_stay_null(self):
        School.objects.create(name="B", code="b")
        s = self.student()
        report = self.run_json()
        self.assertEqual((report["would_set_to_the_only_school"], report["unresolved_stay_null"]), (0, 1))
        self.run_cmd("--apply", "--batch-file", self.path())
        s.refresh_from_db()
        self.assertIsNone(s.school_id)

    def test_students_with_a_class_already_have_a_school_and_are_untouched(self):
        klass = SchoolClass.objects.create(school=self.school, title="7-A", academic_year="1404-1405", grade=7)
        s = self.student(school="keep", school_class=klass)
        self.assertEqual(self.run_json()["students_without_school"], 0)

    def test_inconsistent_school_is_only_counted(self):
        other = School.objects.create(name="B", code="b")
        klass = SchoolClass.objects.create(school=self.school, title="7-A", academic_year="1404-1405", grade=7)
        s = self.student(school="keep", school_class=klass)
        Student.objects.filter(pk=s.pk).update(school=other)
        report = self.run_json()
        self.assertEqual(report["info_students_with_school_differing_from_class_school_not_changed"], 1)
        self.run_cmd("--apply", "--batch-file", self.path())
        s.refresh_from_db()
        self.assertEqual(s.school_id, other.pk)

    def test_is_idempotent(self):
        self.student()
        self.run_cmd("--apply", "--batch-file", self.path("a.json"))
        self.assertEqual(self.run_json()["students_without_school"], 0)

    def test_existing_batch_file_is_never_overwritten_and_nothing_is_written(self):
        s = self.student()
        with open(self.path(), "w", encoding="utf-8") as handle:
            handle.write("keep")
        with self.assertRaises(CommandError):
            self.run_cmd("--apply", "--batch-file", self.path())
        s.refresh_from_db()
        self.assertIsNone(s.school_id)

    def test_revert_restores_null_for_exactly_the_batch(self):
        pre = self.student(school=self.school)
        a = self.student()
        self.run_cmd("--apply", "--batch-file", self.path())
        report = self.run_json("--revert-batch", self.path())
        self.assertEqual(report["reverted_to_null"], 1)
        a.refresh_from_db()
        pre.refresh_from_db()
        self.assertIsNone(a.school_id)
        self.assertEqual(pre.school_id, self.school.pk)

    def test_revert_leaves_a_student_whose_school_changed_since(self):
        a = self.student()
        self.run_cmd("--apply", "--batch-file", self.path())
        self.assertEqual(Student.objects.get(pk=a.pk).school_id, self.school.pk)
        other = School.objects.create(name="B", code="b")  # created after the apply: the batch needs exactly one School
        Student.objects.filter(pk=a.pk).update(school=other)
        self.assertEqual(self.run_json("--revert-batch", self.path())["reverted_to_null"], 0)
        a.refresh_from_db()
        self.assertEqual(a.school_id, other.pk)

    def test_revert_leaves_a_student_that_got_a_class_since(self):
        a = self.student()
        self.run_cmd("--apply", "--batch-file", self.path())
        klass = SchoolClass.objects.create(school=self.school, title="7-A", academic_year="1404-1405", grade=7)
        Student.objects.filter(pk=a.pk).update(school_class=klass)
        self.assertEqual(self.run_json("--revert-batch", self.path())["reverted_to_null"], 0)
        a.refresh_from_db()
        self.assertEqual(a.school_id, self.school.pk)

    def test_revert_rejects_foreign_malformed_and_hostile_batches(self):
        cases = {
            "foreign.json": {"command": "check_school_memberships", "version": 2, "assignments": []},
            "text.json": {"command": "backfill_student_school", "version": 2, "assignments": "all"},
            "bool.json": {"command": "backfill_student_school", "version": 2,
                          "assignments": [{"student_id": True, "school_id": 1}]},
            "str.json": {"command": "backfill_student_school", "version": 2,
                         "assignments": [{"student_id": "1 OR 1=1", "school_id": 1}]},
        }
        for name, payload in cases.items():
            with open(self.path(name), "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            with self.subTest(name=name), self.assertRaises(CommandError):
                self.run_cmd("--revert-batch", self.path(name))

    def test_apply_is_refused_when_staff_would_newly_see_a_student_with_a_current_enrollment(self):
        year = AcademicYear.objects.create(
            school=self.school, code="1404-1405", start_date=date(2025, 9, 23), end_date=date(2026, 6, 21),
            is_current=True)
        s = self.student()
        Enrollment.objects.create(student=s, academic_year=year, grade=7, status="active", source="manual")
        report = self.run_json()
        self.assertEqual(report["students_with_current_enrollment_that_staff_would_newly_see"], 1)
        with self.assertRaises(CommandError):
            self.run_cmd("--apply", "--batch-file", self.path())
        s.refresh_from_db()
        self.assertIsNone(s.school_id)
        self.run_cmd("--apply", "--batch-file", self.path(), "--accept-visibility-change")
        s.refresh_from_db()
        self.assertEqual(s.school_id, self.school.pk)

    def test_no_visibility_change_without_a_current_enrollment(self):
        parent = User.objects.create_user("parent")
        group = __import__("django.contrib.auth.models", fromlist=["Group"]).Group.objects.create(name="Parent")
        parent.groups.add(group)
        s = self.student()
        Student.objects.filter(pk=s.pk).update(parent_user=parent)
        staff = User.objects.create_user("lead")

        def snapshot():
            return {u.username: sorted(visible_students(u).values_list("pk", flat=True)) for u in User.objects.all()}

        before = snapshot()
        self.run_cmd("--apply", "--batch-file", self.path())
        self.assertEqual(snapshot(), before)
        self.assertIsNotNone(staff.pk)
