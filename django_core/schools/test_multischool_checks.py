"""S2 tests: the multi-school gate checks (changes/0010 S2): ``check_access_switch_ready --multi-school`` and
``compare_access_parity --multi-school``. Synthetic data only. Default invocations stay unchanged."""
import json
from datetime import date
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from students.models import Attendance, Enrollment, Grade, Student

from .models import AcademicYear, School, SchoolClass, SchoolMembership

User = get_user_model()
ADMIN, PLATFORM_ADMIN = "SchoolAdmin", "PlatformAdmin"


def make_user(username, *groups, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    return user


class Base(TestCase):
    def setUp(self):
        self.a = School.objects.order_by("pk").first() or School.objects.create(name="A", code="a")
        self.year(self.a)  # a school with students needs a current year for the existing gate
        self.n = 0

    def student(self, school=None, **extra):
        self.n += 1
        student = Student.objects.create(
            first_name="S", last_name=str(self.n), national_id=f"40000000{self.n:02d}", grade=7, phone_number="1",
            **extra)
        Student.objects.filter(pk=student.pk).update(school=school)
        return Student.objects.get(pk=student.pk)

    def year(self, school, code="1404-1405", current=True):
        year, _ = AcademicYear.objects.get_or_create(
            school=school, code=code,
            defaults=dict(start_date=date(2025, 9, 23), end_date=date(2026, 6, 21), is_current=current))
        return year

    def member(self, username, school=None, **extra):
        user = make_user(username, ADMIN, **extra)
        SchoolMembership.objects.create(user=user, school=school or self.a)
        return user


class ReadinessTests(Base):
    def ready(self, *args, fail=False):
        out = StringIO()
        if fail:
            with self.assertRaises(CommandError):
                call_command("check_access_switch_ready", "--json", *args, stdout=out)
        else:
            call_command("check_access_switch_ready", "--json", *args, stdout=out)
        return json.loads(out.getvalue())

    def raw(self, *args):
        """Report whatever the verdict (the existing gate may add its own blockers)."""
        out = StringIO()
        try:
            call_command("check_access_switch_ready", "--json", *args, stdout=out)
        except CommandError:
            pass
        return json.loads(out.getvalue())

    def test_clean_state_is_ready_with_and_without_the_flag(self):
        self.member("sa")
        self.student(self.a)
        for args in ((), ("--multi-school",)):
            report = self.ready(*args)
            self.assertEqual(report["verdict"], "READY")

    def test_default_output_is_unchanged_without_the_flag(self):
        make_user("sa", ADMIN)  # a SchoolAdmin without membership
        self.student(None)  # a student without school
        report = self.ready()
        for key in ("school_admins_without_membership", "students_without_school", "school_inconsistent_rows",
                    "active_memberships_of_platform_admin_users", "memberships_invalid", "info_schools_count"):
            self.assertNotIn(key, report)
        self.assertEqual(report["info_students_without_school"], 1)  # the existing diagnostic

    def test_school_admin_without_membership_is_a_blocker(self):
        make_user("sa", ADMIN)
        report = self.ready("--multi-school", fail=True)
        self.assertEqual(report["school_admins_without_membership"], 1)
        self.assertEqual(report["verdict"], "NOT READY")
        self.assertIn("school_admins_without_membership", report["blockers_nonzero"])

    def test_zero_case_school_admin_with_membership(self):
        self.member("sa")
        self.assertEqual(self.ready("--multi-school")["school_admins_without_membership"], 0)

    def test_inactive_superuser_and_non_members_are_not_counted_as_school_admins(self):
        make_user("off", ADMIN, is_active=False)
        make_user("root", ADMIN, is_superuser=True)
        make_user("teacher", "Teacher")
        report = self.ready("--multi-school")
        self.assertEqual(report["school_admins_without_membership"], 0)
        self.assertEqual(report["info_superusers_mapped_to_school_admin_until_s8"], 1)

    def test_inactive_membership_counts_as_without_membership(self):
        user = self.member("sa")
        SchoolMembership.objects.filter(user=user).update(is_active=False)
        self.assertEqual(self.ready("--multi-school", fail=True)["school_admins_without_membership"], 1)

    def test_students_without_school_is_a_blocker_only_with_the_flag(self):
        self.student(None)
        self.assertEqual(self.ready("--multi-school", fail=True)["students_without_school"], 1)
        self.assertEqual(self.ready(fail=False)["verdict"], "READY")  # unchanged default gate

    def test_students_without_school_zero_case(self):
        self.member("sa")
        self.student(self.a)
        self.assertEqual(self.ready("--multi-school")["students_without_school"], 0)

    def test_inconsistent_student_school_versus_class_school(self):
        other = School.objects.create(name="B", code="b")
        klass = SchoolClass.objects.create(school=self.a, title="7-A", academic_year="1404-1405", grade=7)
        s = self.student(self.a, school_class=klass)
        self.assertEqual(self.raw("--multi-school")["school_inconsistent_rows"], 0)
        Student.objects.filter(pk=s.pk).update(school=other)
        self.assertEqual(self.raw("--multi-school")["school_inconsistent_rows"], 1)

    def test_inconsistent_enrollment_year_school(self):
        other = School.objects.create(name="B", code="b")
        s = self.student(self.a)
        year_b = self.year(other)
        Enrollment.objects.create(student=s, academic_year=year_b, grade=7, status="active", source="manual")
        self.assertEqual(self.ready("--multi-school", fail=True)["school_inconsistent_rows"], 1)

    def test_consistent_enrollment_is_not_counted(self):
        self.member("sa")
        s = self.student(self.a)
        Enrollment.objects.create(student=s, academic_year=self.year(self.a), grade=7, status="active", source="manual")
        self.assertEqual(self.ready("--multi-school")["school_inconsistent_rows"], 0)

    def test_inconsistent_grade_and_attendance_enrollment_links(self):
        s1, s2 = self.student(self.a), self.student(self.a)
        year = self.year(self.a)
        e1 = Enrollment.objects.create(student=s1, academic_year=year, grade=7, status="active", source="manual")
        Grade.objects.create(student=s2, enrollment=e1, subject="math", exam_type="quiz", score=10, date="2026-01-01")
        Attendance.objects.create(student=s2, enrollment=e1, date="2026-01-02", status="present")
        Grade.objects.create(student=s1, enrollment=e1, subject="math", exam_type="quiz", score=10, date="2026-01-03")
        self.assertEqual(self.ready("--multi-school", fail=True)["school_inconsistent_rows"], 2)

    def test_active_membership_of_a_platform_admin_user_is_a_blocker(self):
        user = self.member("promoted")
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        report = self.ready("--multi-school", fail=True)
        self.assertEqual(report["active_memberships_of_platform_admin_users"], 1)
        self.assertEqual(report["school_admins_without_membership"], 1)  # the helper returns the empty set for them

    def test_promoted_user_with_an_active_membership_blocks_on_its_own(self):
        """D-MS-9: the runbook step was forgotten; this is the only blocker that fires."""
        user = self.member("promoted")
        user.groups.remove(Group.objects.get(name=ADMIN))
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        report = self.ready("--multi-school", fail=True)
        # a membership of a PlatformAdmin user is always also an invalid membership (D3), so both blockers fire
        self.assertEqual(report["blockers_nonzero"], {"active_memberships_of_platform_admin_users": 1,
                                                      "memberships_invalid": 1})
        self.assertEqual(report["verdict"], "NOT READY")

    def test_deactivating_the_promoted_users_membership_clears_the_blocker(self):
        user = self.member("promoted")
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        SchoolMembership.objects.filter(user=user).update(is_active=False)
        user.groups.remove(Group.objects.get(name=ADMIN))  # no longer a SchoolAdmin: promoted
        report = self.ready("--multi-school")
        self.assertEqual(report["active_memberships_of_platform_admin_users"], 0)

    def test_invalid_memberships_are_a_blocker(self):
        """S2 review D3: a dormant grant is exactly what the gate must catch."""
        user = self.member("gone")
        user.groups.clear()
        report = self.ready("--multi-school", fail=True)
        self.assertEqual(report["memberships_invalid"], 1)
        self.assertEqual(report["verdict"], "NOT READY")
        self.assertEqual(report["blockers_nonzero"], {"memberships_invalid": 1})

    def test_invalid_memberships_zero_case_and_deactivation_clears_it(self):
        user = self.member("gone")
        user.groups.clear()
        SchoolMembership.objects.filter(user=user).update(is_active=False)  # what --deactivate does
        self.assertEqual(self.ready("--multi-school")["memberships_invalid"], 0)

    def test_invalid_memberships_are_not_a_blocker_without_the_flag(self):
        user = self.member("gone")
        user.groups.clear()
        self.assertEqual(self.ready()["verdict"], "READY")

    def test_no_school_admin_while_students_exist_is_a_blocker(self):
        """S2 review D1: the gate must not pass vacuously."""
        self.student(self.a)
        report = self.ready("--multi-school", fail=True)
        self.assertEqual(report["no_school_admin_while_students_exist"], 1)
        # the school of that student is also uncovered (E1); D1 stays the blocker for installations without any admin
        self.assertEqual(report["blockers_nonzero"], {"no_school_admin_while_students_exist": 1,
                                                      "schools_with_students_but_no_school_admin": 1})

    def test_no_school_admin_zero_cases(self):
        self.assertEqual(self.ready("--multi-school")["no_school_admin_while_students_exist"], 0)  # no students
        self.member("sa")
        self.student(self.a)
        self.assertEqual(self.ready("--multi-school")["no_school_admin_while_students_exist"], 0)  # an admin exists

    def test_superuser_only_installation_with_students_blocks(self):
        make_user("root", ADMIN, is_superuser=True)
        self.student(self.a)
        self.assertEqual(self.ready("--multi-school", fail=True)["no_school_admin_while_students_exist"], 1)

    def test_not_run_line_without_the_flag_and_run_line_with_it(self):
        """The S3 gate needs the flag: the default output says so, in text and in JSON."""
        out = StringIO()
        call_command("check_access_switch_ready", stdout=out)
        self.assertIn("multi-school checks: NOT RUN", out.getvalue())
        self.assertNotIn("multi-school checks: RUN", out.getvalue().replace("NOT RUN", ""))
        self.assertEqual(self.ready()["multi_school_checks"], "NOT RUN")
        out = StringIO()
        call_command("check_access_switch_ready", "--multi-school", stdout=out)
        self.assertIn("multi-school checks: RUN", out.getvalue())
        self.assertNotIn("NOT RUN", out.getvalue())
        self.assertEqual(self.ready("--multi-school")["multi_school_checks"], "RUN")

    def test_info_counts(self):
        self.member("sa1")
        self.member("sa2")
        report = self.ready("--multi-school")
        self.assertEqual(report["info_schools_count"], 1)
        self.assertEqual(report["info_school_admins_per_school"], {str(self.a.pk): 2})

    def test_verdict_stays_not_ready_with_a_blocker_and_ready_with_only_info(self):
        self.member("sa1")
        self.member("sa2")
        make_user("root", ADMIN, is_superuser=True)  # info only
        self.assertEqual(self.ready("--multi-school")["verdict"], "READY")
        self.student(None)  # blocker
        self.assertEqual(self.ready("--multi-school", fail=True)["verdict"], "NOT READY")


class SchoolAdminParityTests(Base):
    def parity(self, *args, fail=False):
        out = StringIO()
        if fail:
            with self.assertRaises(CommandError):
                call_command("compare_access_parity", "--multi-school", "--json", *args, stdout=out)
        else:
            call_command("compare_access_parity", "--multi-school", "--json", *args, stdout=out)
        return json.loads(out.getvalue())

    def data(self, school):
        s = self.student(school)
        Grade.objects.create(student=s, subject="math", exam_type="quiz", score=10, date="2026-01-01")
        Attendance.objects.create(student=s, date="2026-01-02", status="present")
        return s

    def test_one_school_every_admin_a_member_is_zero_difference(self):
        self.member("sa1")
        self.member("sa2")
        self.data(self.a)
        report = self.parity()
        self.assertEqual((report["users_compared"], report["students_lost"], report["grades_lost"],
                          report["attendances_lost"]), (2, 0, 0, 0))

    def test_admin_without_membership_loses_everything(self):
        make_user("sa", ADMIN)
        self.data(self.a)
        report = self.parity(fail=True)
        self.assertEqual((report["students_lost"], report["grades_lost"], report["attendances_lost"]), (1, 1, 1))
        self.assertEqual(report["explained_by_no_valid_membership"], 1)

    def test_student_without_school_is_lost_and_explained(self):
        self.member("sa")
        self.data(None)
        report = self.parity(fail=True)
        self.assertEqual(report["students_lost"], 1)
        self.assertEqual(report["explained_by_student_without_school"], 1)

    def test_other_school_rows_are_lost_for_a_single_school_member(self):
        other = School.objects.create(name="B", code="b")
        self.member("sa")
        self.data(self.a)
        self.data(other)
        report = self.parity(fail=True)
        self.assertEqual((report["students_lost"], report["grades_lost"], report["attendances_lost"]), (1, 1, 1))
        self.assertEqual(report["explained_by_student_in_school_without_membership"], 1)

    def test_member_of_both_schools_loses_nothing(self):
        other = School.objects.create(name="B", code="b")
        user = self.member("sa")
        SchoolMembership.objects.create(user=user, school=other)
        self.data(self.a)
        self.data(other)
        self.assertEqual(self.parity()["students_lost"], 0)

    def test_superuser_inactive_and_dual_role_handling(self):
        make_user("root", ADMIN, is_superuser=True)
        make_user("off", ADMIN, is_active=False)
        self.data(self.a)
        report = self.parity(fail=True)  # neither is a scoped SchoolAdmin: D1, the comparison would pass vacuously
        self.assertEqual((report["users_compared"], report["no_school_admin_while_students_exist"]), (0, 1))
        dual = self.member("dual")
        dual.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        self.assertEqual(self.parity(fail=True)["users_compared"], 1)  # a dual-role account would lose everything

    def test_no_school_admin_while_students_exist_fails(self):
        """S2 review D1."""
        self.data(self.a)
        report = self.parity(fail=True)
        self.assertEqual(report["no_school_admin_while_students_exist"], 1)

    def test_no_school_admin_and_no_students_passes(self):
        self.assertEqual(self.parity()["users_compared"], 0)

    def test_invalid_active_membership_fails_the_parity_gate(self):
        """S2 review D3: zero lost rows is not enough while a dormant grant exists."""
        user = self.member("sa")
        orphan = self.member("gone")
        orphan.groups.clear()
        report = self.parity(fail=True)
        self.assertEqual((report["memberships_invalid"], report["students_lost"]), (1, 0))
        SchoolMembership.objects.filter(user=orphan).update(is_active=False)
        self.assertEqual(self.parity()["memberships_invalid"], 0)
        self.assertIsNotNone(user.pk)

    def test_not_run_and_run_lines(self):
        out = StringIO()
        call_command("compare_access_parity", stdout=out)
        self.assertIn("multi-school checks: NOT RUN", out.getvalue())
        out = StringIO()
        call_command("compare_access_parity", "--multi-school", stdout=out)
        self.assertIn("multi-school checks: RUN", out.getvalue())
        self.assertNotIn("NOT RUN", out.getvalue())

    def test_default_invocation_is_unchanged_apart_from_the_not_run_line(self):
        out = StringIO()
        call_command("compare_access_parity", "--json", stdout=out)
        report = json.loads(out.getvalue())
        self.assertNotIn("students_lost", report)
        self.assertIn("students_only_legacy", report)
        self.assertEqual(report["multi_school_checks"], "NOT RUN")

    def test_writes_nothing(self):
        make_user("sa", ADMIN)
        self.data(self.a)
        before = (Student.objects.count(), SchoolMembership.objects.count(), Grade.objects.count())
        self.parity(fail=True)
        self.assertEqual((Student.objects.count(), SchoolMembership.objects.count(), Grade.objects.count()), before)


class SchoolsWithoutAdminCoverTests(Base):
    """S2 review E1: a school that has students needs a valid SchoolAdmin of its own, not just 'some admin exists'."""

    def ready(self, *args):
        out = StringIO()
        try:
            call_command("check_access_switch_ready", "--json", "--multi-school", *args, stdout=out)
        except CommandError:
            pass
        return json.loads(out.getvalue())

    def parity(self):
        out = StringIO()
        try:
            call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
            failed = False
        except CommandError:
            failed = True
        return json.loads(out.getvalue()), failed

    def two_schools(self):
        self.b = School.objects.create(name="B", code="b")
        self.year(self.b)
        self.member("admin_a", self.a)
        self.student(self.a)
        self.student(self.b)

    def test_school_with_students_and_no_admin_is_a_blocker_even_when_another_school_has_one(self):
        self.two_schools()
        report = self.ready()
        self.assertEqual(report["schools_with_students_but_no_school_admin"], 1)
        self.assertEqual(report["no_school_admin_while_students_exist"], 0)  # D1 does not fire: an admin exists
        self.assertIn("schools_with_students_but_no_school_admin", report["blockers_nonzero"])
        self.assertEqual(report["verdict"], "NOT READY")

    def test_zero_case_every_school_with_students_has_an_admin(self):
        self.two_schools()
        self.member("admin_b", self.b)
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 0)

    def test_one_admin_member_of_both_schools_covers_both(self):
        self.two_schools()
        user = User.objects.get(username="admin_a")
        SchoolMembership.objects.create(user=user, school=self.b)
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 0)

    def test_a_school_without_students_needs_no_admin(self):
        self.member("admin_a", self.a)
        self.student(self.a)
        School.objects.create(name="B", code="b")
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 0)

    def test_students_without_a_school_are_not_counted_here(self):
        self.member("admin_a", self.a)
        self.student(None)
        report = self.ready()
        self.assertEqual(report["schools_with_students_but_no_school_admin"], 0)
        self.assertEqual(report["students_without_school"], 1)

    def test_only_a_valid_admin_covers_a_school(self):
        self.two_schools()
        for name, kwargs in (("off", {"is_active": False}), ("root", {"is_superuser": True})):
            user = make_user(name, ADMIN, **kwargs)
            SchoolMembership.objects.create(user=user, school=self.b)  # bypasses clean()
        dual = self.member("dual", self.b)
        dual.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        gone = self.member("gone", self.b)
        gone.groups.clear()
        inactive_row = make_user("rowoff", ADMIN)
        SchoolMembership.objects.create(user=inactive_row, school=self.b, is_active=False)
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 1)

    def test_a_valid_admin_added_to_the_uncovered_school_clears_it(self):
        self.two_schools()
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 1)
        self.member("admin_b", self.b)
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 0)

    def test_count_is_per_school(self):
        self.two_schools()
        third = School.objects.create(name="C", code="c")
        self.year(third)
        self.student(third)
        self.assertEqual(self.ready()["schools_with_students_but_no_school_admin"], 2)

    def test_parity_fails_on_an_uncovered_school_and_reports_the_count(self):
        self.two_schools()
        report, failed = self.parity()
        self.assertTrue(failed)
        self.assertEqual(report["schools_with_students_but_no_school_admin"], 1)

    def test_parity_zero_case(self):
        self.member("admin_a", self.a)
        self.student(self.a)
        report, failed = self.parity()
        self.assertFalse(failed)
        self.assertEqual(report["schools_with_students_but_no_school_admin"], 0)

    def test_parity_is_not_misled_by_a_second_admin_of_the_covered_school(self):
        self.two_schools()
        self.member("admin_a2", self.a)
        report, failed = self.parity()
        self.assertTrue(failed)
        self.assertEqual(report["schools_with_students_but_no_school_admin"], 1)


class ParityCoverageTests(Base):
    """S2 review J1: every counter school_admin_parity() can return must be classified, or the gate cannot pass."""

    @staticmethod
    def produced_keys():
        """String keys written into the result Counter by school_admin_parity (read from its source)."""
        import ast
        import inspect

        from . import multischool_checks

        tree = ast.parse(inspect.getsource(multischool_checks.school_admin_parity).lstrip())
        keys = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "out":
                index = node.slice
                if isinstance(index, ast.Constant) and isinstance(index.value, str):
                    keys.add(index.value)
        return keys

    def test_every_produced_counter_is_classified_as_problem_or_info(self):
        from .multischool_checks import PARITY_INFO_KEYS, PARITY_PROBLEM_KEYS

        produced = self.produced_keys()
        self.assertTrue(produced)  # the reader works
        self.assertEqual(sorted(produced - set(PARITY_PROBLEM_KEYS) - set(PARITY_INFO_KEYS)), [])

    def test_the_two_lists_are_disjoint_and_every_problem_has_a_text(self):
        from .multischool_checks import PARITY_INFO_KEYS, PARITY_PROBLEM_KEYS, PARITY_PROBLEM_TEXT

        self.assertEqual(set(PARITY_PROBLEM_KEYS) & set(PARITY_INFO_KEYS), set())
        self.assertEqual(set(PARITY_PROBLEM_KEYS), set(PARITY_PROBLEM_TEXT))

    def test_every_problem_key_is_produced_or_defaulted(self):
        """No dead entries: each problem key comes from school_admin_parity or from the command's zero defaults."""
        from .multischool_checks import PARITY_PROBLEM_KEYS

        defaults = {"students_lost", "grades_lost", "attendances_lost"}
        self.assertEqual(set(PARITY_PROBLEM_KEYS) - self.produced_keys() - defaults, set())

    def test_an_unclassified_counter_makes_the_command_fail_closed_even_when_everything_else_is_clean(self):
        self.member("sa")
        self.student(self.a)
        from . import multischool_checks

        real = multischool_checks.school_admin_parity
        with mock.patch.object(multischool_checks, "school_admin_parity", lambda: {**real(), "dummy_counter": 3}):
            out = StringIO()
            with self.assertRaises(CommandError) as err:
                call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
        report = json.loads(out.getvalue())
        self.assertIs(report["multi_school_checks_run"], True)
        self.assertIs(report["multi_school_passed"], False)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["unclassified_counters"], ["dummy_counter"])
        self.assertIn("dummy_counter", str(err.exception))

    def test_the_same_clean_state_passes_without_the_dummy_counter(self):
        self.member("sa")
        self.student(self.a)
        out = StringIO()
        call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
        report = json.loads(out.getvalue())
        self.assertIs(report["multi_school_passed"], True)
        self.assertNotIn("unclassified_counters", report)

    def test_each_problem_key_alone_fails_the_gate(self):
        from . import multischool_checks

        self.member("sa")
        self.student(self.a)
        real = multischool_checks.school_admin_parity
        for key in multischool_checks.PARITY_PROBLEM_KEYS:
            with self.subTest(key=key), mock.patch.object(
                    multischool_checks, "school_admin_parity", lambda key=key: {**real(), key: 1}):
                out = StringIO()
                with self.assertRaises(CommandError):
                    call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
                report = json.loads(out.getvalue())
                self.assertIs(report["multi_school_passed"], False)
                self.assertEqual(report["verdict"], "FAIL")

    def test_informational_keys_alone_never_fail_the_gate(self):
        from . import multischool_checks

        self.member("sa")
        self.student(self.a)
        real = multischool_checks.school_admin_parity
        for key in multischool_checks.PARITY_INFO_KEYS:
            with self.subTest(key=key), mock.patch.object(
                    multischool_checks, "school_admin_parity", lambda key=key: {**real(), key: 5}):
                out = StringIO()
                call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
                self.assertIs(json.loads(out.getvalue())["multi_school_passed"], True)
