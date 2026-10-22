"""S2 tests: backfill_school_memberships and check_school_memberships (changes/0010 S2, D-MS-9 option B).

Traceability: S1 review findings F2, F4, G3, H2. Synthetic data only. Tools grant nothing by themselves: a guard
test proves visibility is identical before and after they run.
"""
import json
import os
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from students.access import ADMIN, PARENT, PLATFORM_ADMIN, TEACHER, school_ids_for_admin, visible_students
from students.models import Student

from .models import School, SchoolMembership

User = get_user_model()


def make_user(username, *groups, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    return user


class ToolCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name="batch.json"):
        return os.path.join(self.tmp.name, name)

    def run_cmd(self, name, *args):
        out = StringIO()
        call_command(name, *args, stdout=out)
        return out.getvalue()

    def run_json(self, name, *args):
        return json.loads(self.run_cmd(name, *args, "--json"))


class BackfillSchoolMembershipsTests(ToolCase):
    def setUp(self):
        super().setUp()
        # a default School may already exist (students/0009 creates it); the tools need exactly one
        self.school = School.objects.order_by("pk").first() or School.objects.create(name="A", code="a")
        self.assertEqual(School.objects.count(), 1)
        self.sa1 = make_user("sa1", ADMIN)
        self.sa2 = make_user("sa2", ADMIN)

    def test_dry_run_is_the_default_and_writes_nothing(self):
        report = self.run_json("backfill_school_memberships")
        self.assertEqual(report["eligible"], 2)
        self.assertEqual(report["would_create"], 2)
        self.assertIn("dry-run", report["mode"])
        self.assertEqual(SchoolMembership.objects.count(), 0)

    def test_apply_needs_a_batch_file(self):
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--apply")
        self.assertEqual(SchoolMembership.objects.count(), 0)

    def test_apply_creates_exactly_the_eligible_rows_and_a_batch_file(self):
        make_user("off", ADMIN, is_active=False)
        make_user("root", ADMIN, is_superuser=True)
        make_user("both", ADMIN, PLATFORM_ADMIN)
        make_user("teacher", TEACHER)
        make_user("nobody")
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        self.assertEqual(
            sorted(SchoolMembership.objects.values_list("user__username", flat=True)), ["sa1", "sa2"])
        row = SchoolMembership.objects.get(user=self.sa1)
        self.assertEqual((row.school_id, row.is_active, row.created_by_id), (self.school.pk, True, None))
        row.full_clean()
        with open(self.path(), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["command"], "backfill_school_memberships")
        self.assertEqual(sorted(e["user_id"] for e in data["memberships"]), sorted([self.sa1.pk, self.sa2.pk]))

    def test_skip_counts_are_reported(self):
        make_user("off", ADMIN, is_active=False)
        make_user("root", ADMIN, is_superuser=True)
        make_user("both", ADMIN, PLATFORM_ADMIN)
        SchoolMembership.objects.create(user=self.sa2, school=self.school)
        skipped = self.run_json("backfill_school_memberships")["skipped"]
        self.assertEqual(skipped, {"inactive_account": 1, "superuser": 1, "also_platform_admin": 1,
                                   "already_has_membership": 1})

    def test_is_idempotent(self):
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path("one.json"))
        report = self.run_json("backfill_school_memberships")
        self.assertEqual(report["eligible"], 0)
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path("two.json"))
        self.assertEqual(SchoolMembership.objects.count(), 2)

    def test_an_existing_inactive_row_is_neither_duplicated_nor_reactivated(self):
        row = SchoolMembership.objects.create(user=self.sa1, school=self.school, is_active=False)
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        row.refresh_from_db()
        self.assertFalse(row.is_active)
        self.assertEqual(SchoolMembership.objects.filter(user=self.sa1).count(), 1)

    def test_an_existing_batch_file_is_never_overwritten_and_nothing_is_written(self):
        with open(self.path(), "w", encoding="utf-8") as handle:
            handle.write("keep")
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        self.assertEqual(SchoolMembership.objects.count(), 0)
        with open(self.path(), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "keep")

    def test_with_two_schools_nothing_is_guessed_and_apply_is_refused(self):
        School.objects.create(name="B", code="b")
        report = self.run_json("backfill_school_memberships")
        self.assertIn("NOT APPLICABLE", report["mode"])
        self.assertEqual(sorted(report["eligible_user_ids"]), sorted([self.sa1.pk, self.sa2.pk]))
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        self.assertEqual(SchoolMembership.objects.count(), 0)
        self.assertFalse(os.path.exists(self.path()))

    def test_with_no_school_apply_is_refused(self):
        School.objects.all().delete()
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())

    def test_revert_deletes_exactly_the_batch_rows(self):
        keeper = make_user("keeper", ADMIN)
        SchoolMembership.objects.create(user=keeper, school=self.school)  # pre-existing, not in the batch
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        report = self.run_json("backfill_school_memberships", "--revert-batch", self.path())
        self.assertEqual(report["deleted"], 2)
        self.assertEqual(list(SchoolMembership.objects.values_list("user__username", flat=True)), ["keeper"])

    def test_revert_leaves_a_row_deactivated_since_alone(self):
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        SchoolMembership.objects.filter(user=self.sa1).update(is_active=False)
        report = self.run_json("backfill_school_memberships", "--revert-batch", self.path())
        self.assertEqual((report["deleted"], report["left_alone_changed_since"]), (1, 1))
        self.assertTrue(SchoolMembership.objects.filter(user=self.sa1).exists())

    def test_revert_rejects_a_foreign_or_malformed_batch(self):
        with open(self.path("bad.json"), "w", encoding="utf-8") as handle:
            json.dump({"command": "check_school_memberships", "version": 2, "memberships": []}, handle)
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--revert-batch", self.path("bad.json"))
        with open(self.path("junk.json"), "w", encoding="utf-8") as handle:
            handle.write("not json")
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--revert-batch", self.path("junk.json"))
        with self.assertRaises(CommandError):
            self.run_cmd("backfill_school_memberships", "--revert-batch", self.path("missing.json"))

    def test_tool_gives_school_admins_their_school_and_changes_nobody_elses_visibility(self):
        # S3: a SchoolAdmin sees exactly the schools of the active memberships, so this tool is what turns the read
        # access of the eligible admins ON; every other account is unaffected.
        parent = make_user("parent", PARENT)
        student = Student.objects.create(
            first_name="A", last_name="B", national_id="2000000001", grade=7, phone_number="1",
            parent_user=parent, school=School.objects.order_by('pk').first())

        def snapshot():
            return {u.username: sorted(visible_students(u).values_list("pk", flat=True))
                    for u in User.objects.order_by("username")}

        before = snapshot()
        self.run_cmd("backfill_school_memberships", "--apply", "--batch-file", self.path())
        after = snapshot()
        admins = {self.sa1.username, self.sa2.username}
        self.assertTrue(all(before[name] == [] for name in admins))
        self.assertTrue(all(after[name] == [student.pk] for name in admins))
        self.assertEqual({k: v for k, v in after.items() if k not in admins},
                         {k: v for k, v in before.items() if k not in admins})


class CheckSchoolMembershipsTests(ToolCase):
    def setUp(self):
        super().setUp()
        # a default School may already exist (students/0009 creates it); the tools need exactly one
        self.school = School.objects.order_by("pk").first() or School.objects.create(name="A", code="a")
        self.assertEqual(School.objects.count(), 1)

    def member(self, username, *, setup=None, **row):
        user = make_user(username, ADMIN)
        membership = SchoolMembership.objects.create(user=user, school=self.school, **row)
        if setup == "inactive_user":
            User.objects.filter(pk=user.pk).update(is_active=False)
        elif setup == "superuser":
            User.objects.filter(pk=user.pk).update(is_superuser=True)
        elif setup == "left_group":
            user.groups.clear()
        elif setup == "platform":
            user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        return membership

    def test_clean_state_reports_zero_and_exits_zero(self):
        self.member("ok")
        report = self.run_json("check_school_memberships")
        self.assertEqual((report["memberships_total"], report["memberships_active"], report["orphan_active_total"]),
                         (1, 1, 0))
        self.assertEqual(report["orphan_active_by_reason"], {})

    def test_each_orphan_class_is_reported_and_the_report_exits_one(self):
        for setup in ("inactive_user", "superuser", "left_group", "platform"):
            self.member(f"u_{setup}", setup=setup)
        self.member("ok")
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("check_school_memberships", "--json", stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(report["orphan_active_by_reason"], {
            "user_inactive": 1, "user_superuser": 1, "user_outside_school_admin_group": 1,
            "user_in_platform_admin": 1})
        self.assertEqual(report["orphan_active_total"], 4)
        self.assertEqual(report["active_memberships_of_platform_admin_users"], 1)

    def test_first_matching_reason_wins_in_the_order_of_clean(self):
        row = self.member("multi", setup="platform")
        User.objects.filter(pk=row.user_id).update(is_active=False)
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("check_school_memberships", "--json", stdout=out)
        self.assertEqual(json.loads(out.getvalue())["orphan_active_by_reason"], {"user_inactive": 1})

    def test_platform_admin_user_is_counted_even_when_another_reason_matches_first(self):
        row = self.member("both", setup="platform")
        User.objects.filter(pk=row.user_id).update(is_active=False)
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("check_school_memberships", "--json", stdout=out)
        self.assertEqual(json.loads(out.getvalue())["active_memberships_of_platform_admin_users"], 1)

    def test_inactive_orphans_are_counted_apart_and_do_not_fail_the_report(self):
        self.member("old", setup="left_group", is_active=False)
        report = self.run_json("check_school_memberships")
        self.assertEqual((report["orphan_active_total"], report["orphan_inactive_total"]), (0, 1))

    def test_deactivate_dry_run_is_the_default_and_writes_nothing(self):
        row = self.member("dual", setup="platform")
        report = self.run_json("check_school_memberships", "--deactivate")
        self.assertEqual(report["would_deactivate"], 1)
        self.assertIn("dry-run", report["mode"])
        row.refresh_from_db()
        self.assertTrue(row.is_active)

    def test_deactivate_apply_needs_a_batch_file(self):
        self.member("dual", setup="platform")
        with self.assertRaises(CommandError):
            self.run_cmd("check_school_memberships", "--deactivate", "--apply")

    def test_deactivate_apply_deactivates_exactly_the_active_orphans_and_never_deletes(self):
        healthy = self.member("ok")
        dual = self.member("dual", setup="platform")
        gone = self.member("gone", setup="left_group")
        old = self.member("old", setup="inactive_user", is_active=False)
        self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path())
        for row in (healthy, dual, gone, old):
            row.refresh_from_db()
        self.assertEqual((healthy.is_active, dual.is_active, gone.is_active, old.is_active),
                         (True, False, False, False))
        self.assertEqual(SchoolMembership.objects.count(), 4)
        with open(self.path(), encoding="utf-8") as handle:
            self.assertEqual(sorted(m["id"] for m in json.load(handle)["memberships"]), sorted([dual.pk, gone.pk]))
        report = self.run_json("check_school_memberships")
        self.assertEqual(report["orphan_active_total"], 0)

    def test_deactivate_is_idempotent(self):
        self.member("dual", setup="platform")
        self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path("a.json"))
        report = self.run_json("check_school_memberships", "--deactivate")
        self.assertEqual(report["would_deactivate"], 0)

    def test_existing_batch_file_is_never_overwritten(self):
        row = self.member("dual", setup="platform")
        with open(self.path(), "w", encoding="utf-8") as handle:
            handle.write("keep")
        with self.assertRaises(CommandError):
            self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path())
        row.refresh_from_db()
        self.assertTrue(row.is_active)

    def test_revert_reactivates_exactly_the_batch_rows(self):
        dual = self.member("dual", setup="platform")
        other = self.member("other", setup="left_group", is_active=False)  # inactive before, not in the batch
        self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path())
        report = self.run_json("check_school_memberships", "--revert-batch", self.path())
        self.assertEqual(report["reactivated"], 1)
        dual.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((dual.is_active, other.is_active), (True, False))

    def test_revert_rejects_a_foreign_batch(self):
        with open(self.path(), "w", encoding="utf-8") as handle:
            json.dump({"command": "backfill_school_memberships", "version": 2, "memberships": [{"id": 1, "user_id": 1, "school_id": 1}]}, handle)
        with self.assertRaises(CommandError):
            self.run_cmd("check_school_memberships", "--revert-batch", self.path())

    def test_revert_rejects_a_malformed_id_list(self):
        with open(self.path(), "w", encoding="utf-8") as handle:
            json.dump({"command": "check_school_memberships", "version": 2, "memberships": [{"id": "1; drop", "user_id": 1, "school_id": 1}]}, handle)
        with self.assertRaises(CommandError):
            self.run_cmd("check_school_memberships", "--revert-batch", self.path())

    def test_a_re_added_user_regains_nothing_until_the_row_is_reactivated(self):
        """Review finding F4 / D-MS-9: the stale scope does not come back silently."""
        row = self.member("returning")
        user = row.user
        user.groups.clear()
        self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path())
        user.groups.add(Group.objects.get(name=ADMIN))
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=user.pk)), set())
        SchoolMembership.objects.filter(pk=row.pk).update(is_active=True)  # explicit platform action
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=user.pk)), {self.school.pk})

    def test_promotion_runbook_a_promoted_user_ends_with_no_active_membership(self):
        row = self.member("promoted")
        row.user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        self.assertEqual(self.run_json("check_school_memberships", "--deactivate")["would_deactivate"], 1)
        self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path())
        self.assertEqual(self.run_json("check_school_memberships")["active_memberships_of_platform_admin_users"], 0)

    def test_tool_changes_nobodys_visibility(self):
        parent = make_user("parent", PARENT)
        Student.objects.create(first_name="A", last_name="B", national_id="2000000002", grade=7, phone_number="1",
                               parent_user=parent, school=School.objects.order_by('pk').first())
        self.member("dual", setup="platform")   # an invalid membership already grants nothing (S3), so deactivating it changes nothing

        def snapshot():
            return {u.username: sorted(visible_students(u).values_list("pk", flat=True))
                    for u in User.objects.order_by("username")}

        before = snapshot()
        self.run_cmd("check_school_memberships", "--deactivate", "--apply", "--batch-file", self.path())
        self.assertEqual(snapshot(), before)
