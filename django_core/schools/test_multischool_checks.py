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

    def student(self, school, **extra):
        self.n += 1
        return Student.objects.create(
            first_name="S", last_name=str(self.n), national_id=f"40000000{self.n:02d}", grade=7, phone_number="1",
            school=school, **extra)

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
        report = self.ready()
        for key in ("school_admins_without_membership", "students_without_school", "school_inconsistent_rows",
                    "active_memberships_of_platform_admin_users", "memberships_invalid", "info_schools_count"):
            self.assertNotIn(key, report)
        self.assertEqual(report.get("info_students_without_school", 0), 0)  # the existing diagnostic (always 0 since S6)

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
        make_user("noone", ADMIN)  # blocker: a SchoolAdmin without membership
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
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "result":
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

    def test_school_admin_parity_always_reports_the_declared_schema(self):
        """Declared schema (K1/R-g): every classified key is reported, none other, in clean and in busy states."""
        from .multischool_checks import PARITY_INFO_KEYS, PARITY_PROBLEM_KEYS, school_admin_parity

        declared = set(PARITY_PROBLEM_KEYS) | set(PARITY_INFO_KEYS)
        self.assertEqual(set(school_admin_parity()), declared)  # empty database
        self.member("sa")
        self.student(self.a)
        self.assertEqual(set(school_admin_parity()), declared)
        make_user("noone", ADMIN)  # admin without membership: the explained_by_* branches
        self.assertEqual(set(school_admin_parity()), declared)

    def test_a_declared_counter_that_is_no_longer_reported_fails_the_gate_closed(self):
        from . import multischool_checks

        self.member("sa")
        self.student(self.a)
        real = multischool_checks.school_admin_parity
        for key in multischool_checks.PARITY_PROBLEM_KEYS + multischool_checks.PARITY_INFO_KEYS:
            def without(key=key):
                result = dict(real())
                result.pop(key)
                return result

            with self.subTest(key=key), mock.patch.object(multischool_checks, "school_admin_parity", without):
                out = StringIO()
                with self.assertRaises(CommandError):
                    call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
                report = json.loads(out.getvalue())
                self.assertEqual(report["missing_counters"], [key])
                self.assertIs(report["multi_school_passed"], False)
                self.assertEqual(report["verdict"], "FAIL")

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


class ReadinessCoverageTests(Base):
    """S2 review K1 (R-e, R-f, R-g): check_access_switch_ready --multi-school classifies every counter of
    readiness_counts(); an unclassified or a missing counter is a blocker (fail closed)."""

    def clean(self):
        self.member("sa")
        self.student(self.a)

    def gate(self, patched=None):
        from . import multischool_checks

        out = StringIO()
        rc = 0
        context = mock.patch.object(multischool_checks, "readiness_counts", patched) if patched else mock.MagicMock()
        with context:
            try:
                call_command("check_access_switch_ready", "--multi-school", "--json", stdout=out)
            except CommandError:
                rc = 1
        return json.loads(out.getvalue()), rc

    @staticmethod
    def source_report():
        """(literal keys written, problems) found in the source of readiness_counts via ast."""
        import ast
        import inspect

        from . import multischool_checks

        tree = ast.parse(inspect.getsource(multischool_checks.readiness_counts).lstrip())
        keys, problems = set(), []
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "report":
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    keys.add(node.slice.value)
                else:
                    problems.append(f"non-literal key on {node.value.id}")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "report"
                    and node.func.attr in ("update", "setdefault", "pop", "popitem", "clear")):
                problems.append(f"report.{node.func.attr}(...)")
        return keys, problems

    def test_every_literal_key_written_is_classified_and_no_indirect_write_exists(self):
        from .multischool_checks import READINESS_INFO_KEYS, READINESS_PROBLEM_KEYS

        keys, problems = self.source_report()
        self.assertTrue(keys)
        self.assertEqual(sorted(keys - set(READINESS_PROBLEM_KEYS) - set(READINESS_INFO_KEYS)), [])
        self.assertEqual(problems, [])

    def test_the_two_tuples_are_disjoint_and_the_blocker_name_is_the_problem_tuple(self):
        from .multischool_checks import MULTI_SCHOOL_BLOCKERS, READINESS_INFO_KEYS, READINESS_PROBLEM_KEYS

        self.assertEqual(set(READINESS_PROBLEM_KEYS) & set(READINESS_INFO_KEYS), set())
        self.assertIs(MULTI_SCHOOL_BLOCKERS, READINESS_PROBLEM_KEYS)

    def test_readiness_counts_always_reports_exactly_the_declared_schema(self):
        from .multischool_checks import READINESS_INFO_KEYS, READINESS_PROBLEM_KEYS, readiness_counts

        declared = set(READINESS_PROBLEM_KEYS) | set(READINESS_INFO_KEYS)
        self.assertEqual(set(readiness_counts()), declared)  # empty database
        self.clean()
        self.assertEqual(set(readiness_counts()), declared)
        make_user("noone", ADMIN)
        self.assertEqual(set(readiness_counts()), declared)

    def test_clean_state_passes_and_reports_no_unclassified_or_missing_counters(self):
        self.clean()
        report, rc = self.gate()
        self.assertEqual((report["verdict"], report["multi_school_passed"], rc), ("READY", True, 0))
        self.assertNotIn("unclassified_counters", report)
        self.assertNotIn("missing_counters", report)

    def test_each_problem_key_alone_fails_the_gate(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        for key in multischool_checks.READINESS_PROBLEM_KEYS:
            with self.subTest(key=key):
                report, rc = self.gate(lambda key=key: {**real(), key: 1})
                self.assertEqual(rc, 1)
                self.assertEqual(report["verdict"], "NOT READY")
                self.assertIs(report["multi_school_checks_run"], True)
                self.assertIs(report["multi_school_passed"], False)
                self.assertEqual(report["blockers_nonzero"], {key: 1})

    def test_each_info_key_alone_never_fails_the_gate(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        for key in multischool_checks.READINESS_INFO_KEYS:
            with self.subTest(key=key):
                value = {"9": 9} if key == "info_school_admins_per_school" else 5
                report, rc = self.gate(lambda key=key, value=value: {**real(), key: value})
                self.assertEqual((report["verdict"], report["multi_school_passed"], rc), ("READY", True, 0))

    def test_a_dummy_counter_in_readiness_counts_fails_the_gate_closed(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        report, rc = self.gate(lambda: {**real(), "dummy_counter": 3})
        self.assertEqual(rc, 1)
        self.assertEqual(report["verdict"], "NOT READY")
        self.assertIs(report["multi_school_checks_run"], True)
        self.assertIs(report["multi_school_passed"], False)
        self.assertEqual(report["unclassified_counters"], ["dummy_counter"])
        self.assertEqual(report["blockers_nonzero"], {"unclassified_counters": 1})

    def test_even_a_zero_valued_dummy_counter_fails_closed(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        report, rc = self.gate(lambda: {**real(), "dummy_counter": 0})
        self.assertEqual((rc, report["multi_school_passed"]), (1, False))

    def test_a_removed_problem_key_fails_the_gate_closed(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        for key in multischool_checks.READINESS_PROBLEM_KEYS + multischool_checks.READINESS_INFO_KEYS:
            def without(key=key):
                result = dict(real())
                result.pop(key)
                return result

            with self.subTest(key=key):
                report, rc = self.gate(without)
                self.assertEqual(rc, 1)
                self.assertEqual(report["missing_counters"], [key])
                self.assertEqual(report["blockers_nonzero"], {"missing_counters": 1})
                self.assertEqual(report["verdict"], "NOT READY")
                self.assertIs(report["multi_school_passed"], False)

    def test_a_missing_counter_is_still_present_in_the_output_as_zero(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts

        def without():
            result = dict(real())
            result.pop("students_without_school")
            return result

        report, _rc = self.gate(without)
        self.assertEqual(report["students_without_school"], 0)  # shared zero default keeps the output complete

    def test_without_the_flag_none_of_this_runs(self):
        from . import multischool_checks

        with mock.patch.object(multischool_checks, "readiness_counts", side_effect=AssertionError("must not run")):
            out = StringIO()
            call_command("check_access_switch_ready", "--json", stdout=out)
        report = json.loads(out.getvalue())
        self.assertNotIn("unclassified_counters", report)
        self.assertIs(report["multi_school_passed"], False)


class ProducerSourceTests(TestCase):
    """S2 review K-F1: the producers hold NO pre-filled defaults; each declared key is computed by exactly one
    literal-key assignment, so deleting a counter's computation is visible (to this test and to the gate)."""

    @staticmethod
    def analyse(func, name):
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(func).lstrip())
        written, problems, inits = [], [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        inits.append(ast.dump(node.value))
                    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == name:
                        if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                            written.append(target.slice.value)
                        else:
                            problems.append("non-literal key")
            if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Subscript) \
                    and isinstance(node.target.value, ast.Name) and node.target.value.id == name:
                problems.append("augmented assignment")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == name):
                problems.append(f"{name}.{node.func.attr}(...)")
        return written, problems, inits

    def check(self, func, name, problem_keys, info_keys):
        written, problems, inits = self.analyse(func, name)
        declared = set(problem_keys) | set(info_keys)
        self.assertEqual(problems, [])
        self.assertEqual(inits, [__import__("ast").dump(__import__("ast").parse("{}").body[0].value)])  # name = {} only
        self.assertEqual(sorted(set(written) - declared), [], "written but not declared")
        self.assertEqual(sorted(declared - set(written)), [], "declared but never written by the producer")
        self.assertEqual(len(written), len(set(written)), "a key is assigned more than once")

    def test_readiness_counts_writes_exactly_the_declared_keys_once_each(self):
        from .multischool_checks import READINESS_INFO_KEYS, READINESS_PROBLEM_KEYS, readiness_counts

        self.check(readiness_counts, "report", READINESS_PROBLEM_KEYS, READINESS_INFO_KEYS)

    def test_school_admin_parity_writes_exactly_the_declared_keys_once_each(self):
        from .multischool_checks import PARITY_INFO_KEYS, PARITY_PROBLEM_KEYS, school_admin_parity

        self.check(school_admin_parity, "result", PARITY_PROBLEM_KEYS, PARITY_INFO_KEYS)

    def test_the_analyser_detects_the_forbidden_patterns(self):
        """Self-test of the reader: a pre-fill, an update, a non-literal key and an augmented write are all reported."""
        def bad():
            report = dict(x=0)
            report.update({"a": 1})
            report[key] = 2
            report["b"] += 1
            return report

        written, problems, inits = self.analyse(bad, "report")
        self.assertIn("report.update(...)", problems)
        self.assertIn("non-literal key", problems)
        self.assertIn("augmented assignment", problems)
        self.assertNotEqual(inits, [__import__("ast").dump(__import__("ast").parse("{}").body[0].value)])


class CounterValueValidationTests(Base):
    """S2 review K-F2: a counter must be an int >= 0 (bool, None, list, dict, float, str, negative are invalid);
    an invalid value is a blocker of its own, whatever its truthiness."""

    BAD = (None, [], {}, True, False, -1, -7, 1.0, "1", "", [1], {"a": 1})

    def clean(self):
        self.member("sa")
        self.student(self.a)

    def readiness(self, patched):
        from . import multischool_checks

        out = StringIO()
        rc = 0
        with mock.patch.object(multischool_checks, "readiness_counts", patched):
            try:
                call_command("check_access_switch_ready", "--multi-school", "--json", stdout=out)
            except CommandError:
                rc = 1
        return json.loads(out.getvalue()), rc

    def parity(self, patched):
        from . import multischool_checks

        out = StringIO()
        rc = 0
        with mock.patch.object(multischool_checks, "school_admin_parity", patched):
            try:
                call_command("compare_access_parity", "--multi-school", "--json", stdout=out)
            except CommandError:
                rc = 1
        return json.loads(out.getvalue()), rc

    def test_invalid_problem_values_fail_the_readiness_gate_and_are_listed(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        for key in multischool_checks.READINESS_PROBLEM_KEYS:
            for bad in self.BAD:
                with self.subTest(key=key, value=repr(bad)):
                    report, rc = self.readiness(lambda key=key, bad=bad: {**real(), key: bad})
                    self.assertEqual(rc, 1)
                    self.assertEqual(report["invalid_counters"], [key])
                    self.assertEqual(report["blockers_nonzero"], {"invalid_counter_values": 1})
                    self.assertEqual(report["verdict"], "NOT READY")
                    self.assertIs(report["multi_school_passed"], False)
                    self.assertIs(report["multi_school_checks_run"], True)

    def test_invalid_info_values_fail_the_readiness_gate_too(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        for key in ("info_schools_count", "info_superusers_mapped_to_school_admin_until_s8"):
            for bad in self.BAD:
                with self.subTest(key=key, value=repr(bad)):
                    report, rc = self.readiness(lambda key=key, bad=bad: {**real(), key: bad})
                    self.assertEqual((rc, report["invalid_counters"]), (1, [key]))
        for bad in (None, [], 5, True, "x", {"1": -1}, {"1": True}, {1: 2}, {"1": 1.5}):
            with self.subTest(key="info_school_admins_per_school", value=repr(bad)):
                report, rc = self.readiness(lambda bad=bad: {**real(), "info_school_admins_per_school": bad})
                self.assertEqual((rc, report["invalid_counters"]), (1, ["info_school_admins_per_school"]))

    def test_valid_values_pass_including_zero_and_large_ints(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        for good in (0, 3):
            report, rc = self.readiness(lambda good=good: {**real(), "info_schools_count": good})
            self.assertEqual((rc, report["multi_school_passed"]), (0, True))
        report, rc = self.readiness(lambda: {**real(), "info_school_admins_per_school": {"1": 0, "22": 4}})
        self.assertEqual((rc, report["multi_school_passed"]), (0, True))

    def test_a_valid_positive_problem_value_is_a_normal_blocker_not_an_invalid_value(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        report, rc = self.readiness(lambda: {**real(), "students_without_school": 4})
        self.assertEqual(report["blockers_nonzero"], {"students_without_school": 4})
        self.assertNotIn("invalid_counters", report)

    def test_a_non_numeric_truthy_value_no_longer_breaks_the_error_message(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        out = StringIO()
        with mock.patch.object(multischool_checks, "readiness_counts", lambda: {**real(), "students_without_school": "x"}):
            with self.assertRaises(CommandError) as err:
                call_command("check_access_switch_ready", "--multi-school", "--json", stdout=out)
        self.assertIn("NOT READY", str(err.exception))

    def test_invalid_values_fail_the_parity_gate_and_are_listed(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.school_admin_parity
        for key in multischool_checks.PARITY_PROBLEM_KEYS + multischool_checks.PARITY_INFO_KEYS:
            for bad in self.BAD:
                with self.subTest(key=key, value=repr(bad)):
                    report, rc = self.parity(lambda key=key, bad=bad: {**real(), key: bad})
                    self.assertEqual(rc, 1)
                    self.assertEqual(report["invalid_counters"], [key])
                    self.assertEqual(report["verdict"], "FAIL")
                    self.assertIs(report["multi_school_passed"], False)

    def test_parity_valid_values_pass(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.school_admin_parity
        report, rc = self.parity(lambda: {**real(), "users_compared": 9})
        self.assertEqual((rc, report["multi_school_passed"]), (0, True))

    def test_checks_run_on_the_raw_result_so_defaults_cannot_hide_an_invalid_or_missing_value(self):
        from . import multischool_checks

        self.clean()
        real = multischool_checks.readiness_counts
        report, rc = self.readiness(lambda: {k: v for k, v in real().items() if k != "memberships_invalid"})
        self.assertEqual(report["missing_counters"], ["memberships_invalid"])
        self.assertEqual(report["memberships_invalid"], 0)  # output completed by the default, gate failed anyway
        self.assertEqual((rc, report["multi_school_passed"]), (1, False))
