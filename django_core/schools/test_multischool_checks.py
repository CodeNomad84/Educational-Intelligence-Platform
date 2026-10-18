"""S2 tests: the multi-school gate checks (changes/0010 S2): ``check_access_switch_ready --multi-school`` and
``compare_access_parity --multi-school``. Synthetic data only. Default invocations stay unchanged."""
import json
from datetime import date
from io import StringIO

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
        self.assertEqual(report["blockers_nonzero"], {"active_memberships_of_platform_admin_users": 1})
        self.assertEqual(report["verdict"], "NOT READY")

    def test_deactivating_the_promoted_users_membership_clears_the_blocker(self):
        user = self.member("promoted")
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        SchoolMembership.objects.filter(user=user).update(is_active=False)
        user.groups.remove(Group.objects.get(name=ADMIN))  # no longer a SchoolAdmin: promoted
        report = self.ready("--multi-school")
        self.assertEqual(report["active_memberships_of_platform_admin_users"], 0)

    def test_invalid_memberships_are_a_warning_that_does_not_change_the_verdict(self):
        user = self.member("gone")
        user.groups.clear()
        report = self.ready("--multi-school")
        self.assertEqual(report["memberships_invalid"], 1)
        self.assertEqual(report["verdict"], "READY")
        self.assertNotIn("memberships_invalid", report["blockers_nonzero"])

    def test_info_counts(self):
        self.member("sa1")
        self.member("sa2")
        report = self.ready("--multi-school")
        self.assertEqual(report["info_schools_count"], 1)
        self.assertEqual(report["info_school_admins_per_school"], {str(self.a.pk): 2})

    def test_verdict_stays_not_ready_with_a_blocker_and_ready_with_only_warnings(self):
        user = self.member("gone")
        user.groups.clear()  # warning only
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
        self.assertEqual(self.parity()["users_compared"], 0)  # neither is a scoped SchoolAdmin
        dual = self.member("dual")
        dual.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        self.assertEqual(self.parity(fail=True)["users_compared"], 1)  # a dual-role account would lose everything

    def test_default_invocation_is_unchanged(self):
        out = StringIO()
        call_command("compare_access_parity", "--json", stdout=out)
        report = json.loads(out.getvalue())
        self.assertNotIn("students_lost", report)
        self.assertIn("students_only_legacy", report)

    def test_writes_nothing(self):
        make_user("sa", ADMIN)
        self.data(self.a)
        before = (Student.objects.count(), SchoolMembership.objects.count(), Grade.objects.count())
        self.parity(fail=True)
        self.assertEqual((Student.objects.count(), SchoolMembership.objects.count(), Grade.objects.count()), before)
