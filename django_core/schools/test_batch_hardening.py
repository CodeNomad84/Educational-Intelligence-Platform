"""S2 hardening tests (review findings B1-B4, B6, B8, C1-C3, F5): hostile or hand-edited batch files, flag
combinations, batches that record only rows actually updated. Synthetic data only."""
import json
import os
import tempfile
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from schools import batch_log
from students.models import Student

from .models import School, SchoolMembership

User = get_user_model()
ADMIN, PLATFORM_ADMIN = "SchoolAdmin", "PlatformAdmin"

CHECK = "check_school_memberships"
BACKFILL_M = "backfill_school_memberships"
BACKFILL_S = "backfill_student_school"


def make_user(username, *groups, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    return user


class ValidatorTests(SimpleTestCase):
    def test_valid_id_accepts_only_real_positive_bounded_ints(self):
        for ok in (1, 2, 10 ** 9, batch_log.MAX_ID):
            self.assertTrue(batch_log.valid_id(ok), ok)
        for bad in (True, False, 0, -1, batch_log.MAX_ID + 1, 2 ** 64, 1.0, 1.5, "1", "", None, [1], {"a": 1}):
            self.assertFalse(batch_log.valid_id(bad), repr(bad))

    def test_id_rows_requires_every_field_in_every_row(self):
        good = {"rows": [{"a": 1, "b": 2}]}
        self.assertEqual(batch_log.id_rows(good, "rows", ("a", "b")), [{"a": 1, "b": 2}])
        for bad in ({"rows": "x"}, {"rows": [1]}, {"rows": [{"a": 1}]}, {"rows": [{"a": True, "b": 2}]},
                    {"rows": [{"a": 1, "b": 2 ** 63}]}, {}, {"rows": None}):
            with self.assertRaises(CommandError):
                batch_log.id_rows(bad, "rows", ("a", "b"))


class Base(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.school = School.objects.order_by("pk").first() or School.objects.create(name="A", code="a")
        self.assertEqual(School.objects.count(), 1)

    def path(self, name="batch.json"):
        return os.path.join(self.tmp.name, name)

    def write(self, name, payload):
        with open(self.path(name), "w", encoding="utf-8") as handle:
            if isinstance(payload, str):
                handle.write(payload)
            else:
                json.dump(payload, handle)
        return self.path(name)

    def run_cmd(self, name, *args):
        out = StringIO()
        call_command(name, *args, stdout=out)
        return out.getvalue()

    def run_json(self, name, *args):
        return json.loads(self.run_cmd(name, *args, "--json"))


class HostileBatchTests(Base):
    """Every revert rejects malformed or hand-edited files with a CommandError (never a traceback) and writes nothing."""

    ROW = {CHECK: {"id": 1, "user_id": 1, "school_id": 1},
           BACKFILL_M: {"id": 1, "user_id": 1},
           BACKFILL_S: {"student_id": 1, "school_id": 1}}
    KEY = {CHECK: "memberships", BACKFILL_M: "memberships", BACKFILL_S: "assignments"}

    def payload(self, command, rows, **extra):
        data = {"command": command, "version": batch_log.VERSION, self.KEY[command]: rows, **extra}
        if command == BACKFILL_M:
            data.setdefault("school_id", 1)
        return data

    def test_rejected_values_in_every_id_field(self):
        bad_values = (True, False, 0, -5, 2 ** 63, 2 ** 80, 1.0, "1", "1 OR 1=1", None, [1], {"x": 1})
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            for field in self.ROW[command]:
                for bad in bad_values:
                    row = {**self.ROW[command], field: bad}
                    path = self.write("h.json", self.payload(command, [row]))
                    with self.subTest(command=command, field=field, value=repr(bad)), self.assertRaises(CommandError):
                        self.run_cmd(command, "--revert-batch", path)

    def test_school_id_of_the_membership_backfill_batch_is_validated(self):
        for bad in (True, 0, -1, 2 ** 63, "1", None):
            path = self.write("h.json", self.payload(BACKFILL_M, [self.ROW[BACKFILL_M]], school_id=bad))
            with self.subTest(value=repr(bad)), self.assertRaises(CommandError):
                self.run_cmd(BACKFILL_M, "--revert-batch", path)

    def test_missing_fields_wrong_containers_and_structure(self):
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            key = self.KEY[command]
            cases = {
                "no_key": {"command": command, "version": batch_log.VERSION, "school_id": 1},
                "key_not_list": {"command": command, "version": batch_log.VERSION, key: {"a": 1}, "school_id": 1},
                "row_not_dict": {"command": command, "version": batch_log.VERSION, key: [1, 2], "school_id": 1},
                "row_missing_field": {"command": command, "version": batch_log.VERSION, key: [{}], "school_id": 1},
                "top_level_list": [1, 2, 3],
                "top_level_string": "x",
                "old_version": {"command": command, "version": 1, key: [], "school_id": 1},
                "future_version": {"command": command, "version": 99, key: [], "school_id": 1},
                "foreign_command": {"command": "something_else", "version": batch_log.VERSION, key: [], "school_id": 1},
            }
            for name, payload in cases.items():
                path = self.write("h.json", payload)
                with self.subTest(command=command, case=name), self.assertRaises(CommandError):
                    self.run_cmd(command, "--revert-batch", path)

    def test_unreadable_files(self):
        deep = "[" * 200000 + "]" * 200000
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            for name, text in (("junk", "not json"), ("empty", ""), ("truncated", '{"command": "'), ("deep", deep),
                               ("nan", '{"command": NaN}')):
                path = self.write("h.json", text)
                with self.subTest(command=command, case=name), self.assertRaises(CommandError):
                    self.run_cmd(command, "--revert-batch", path)
            with self.subTest(command=command, case="missing"), self.assertRaises(CommandError):
                self.run_cmd(command, "--revert-batch", self.path("does-not-exist.json"))
            with self.subTest(command=command, case="directory"), self.assertRaises(CommandError):
                self.run_cmd(command, "--revert-batch", self.tmp.name)

    def test_extra_keys_are_ignored_and_a_valid_empty_batch_reverts_nothing(self):
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            path = self.write("ok.json", self.payload(command, [], note="extra", created_at="x"))
            self.assertEqual(self.run_json(command, "--revert-batch", path)["writes"], "reverted")

    def test_a_hostile_batch_changes_no_database_row(self):
        user = make_user("sa", ADMIN)
        SchoolMembership.objects.create(user=user, school=self.school)
        student = Student.objects.create(
            first_name="S", last_name="1", national_id="5000000001", grade=7, phone_number="1")
        Student.objects.filter(pk=student.pk).update(school=self.school)
        before = (list(SchoolMembership.objects.values_list("pk", "user_id", "school_id", "is_active")),
                  list(Student.objects.values_list("pk", "school_id")))
        rows = [{"id": True, "user_id": 1, "school_id": 1}, {"id": 2 ** 63, "user_id": 1, "school_id": 1}]
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            path = self.write("h.json", self.payload(command, rows))
            with self.assertRaises(CommandError):
                self.run_cmd(command, "--revert-batch", path)
        after = (list(SchoolMembership.objects.values_list("pk", "user_id", "school_id", "is_active")),
                 list(Student.objects.values_list("pk", "school_id")))
        self.assertEqual(after, before)


class RevertVerifiesRowsTests(Base):
    def test_deactivation_revert_verifies_user_and_school(self):
        other_school = School.objects.create(name="B", code="b")
        users = [make_user(f"o{i}", ADMIN) for i in range(3)]
        rows = [SchoolMembership.objects.create(user=u, school=self.school) for u in users]
        for u in users:
            u.groups.clear()  # orphans
        self.run_cmd(CHECK, "--deactivate", "--apply", "--batch-file", self.path())
        with open(self.path(), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(sorted((m["id"], m["user_id"], m["school_id"]) for m in data["memberships"]),
                         sorted((r.pk, r.user_id, self.school.pk) for r in rows))
        # hand-edit the batch: row 0 keeps its values, row 1 gets a wrong user, row 2 a wrong school
        edited = {**data, "memberships": [
            {"id": rows[0].pk, "user_id": rows[0].user_id, "school_id": self.school.pk},
            {"id": rows[1].pk, "user_id": rows[0].user_id, "school_id": self.school.pk},
            {"id": rows[2].pk, "user_id": rows[2].user_id, "school_id": other_school.pk}]}
        path = self.write("edited.json", edited)
        report = self.run_json(CHECK, "--revert-batch", path)
        self.assertEqual((report["reactivated"], report["left_alone_user_or_school_differs"]), (1, 2))
        for r in rows:
            r.refresh_from_db()
        self.assertEqual([r.is_active for r in rows], [True, False, False])

    def test_deactivation_revert_leaves_rows_that_are_not_in_the_batch(self):
        a, b = make_user("a", ADMIN), make_user("b", ADMIN)
        ra = SchoolMembership.objects.create(user=a, school=self.school)
        rb = SchoolMembership.objects.create(user=b, school=self.school, is_active=False)  # inactive before
        a.groups.clear()
        self.run_cmd(CHECK, "--deactivate", "--apply", "--batch-file", self.path())
        self.run_cmd(CHECK, "--revert-batch", self.path())
        ra.refresh_from_db()
        rb.refresh_from_db()
        self.assertEqual((ra.is_active, rb.is_active), (True, False))

    def test_membership_backfill_revert_verifies_user_and_school(self):
        users = [make_user(f"m{i}", ADMIN) for i in range(2)]
        self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path())
        with open(self.path(), encoding="utf-8") as handle:
            data = json.load(handle)
        by_user = {m["user_id"]: m["id"] for m in data["memberships"]}
        edited = {**data, "memberships": [
            {"id": by_user[users[0].pk], "user_id": users[0].pk},
            {"id": by_user[users[1].pk], "user_id": users[0].pk}]}  # wrong user for the second row
        report = self.run_json(BACKFILL_M, "--revert-batch", self.write("edited.json", edited))
        self.assertEqual((report["deleted"], report["left_alone_changed_since"]), (1, 1))
        self.assertEqual(SchoolMembership.objects.count(), 1)
        wrong_school = {**data, "school_id": self.school.pk + 1000}
        report = self.run_json(BACKFILL_M, "--revert-batch", self.write("wrong.json", wrong_school))
        self.assertEqual(report["deleted"], 0)
        self.assertEqual(SchoolMembership.objects.count(), 1)


class ActuallyUpdatedTests(Base):
    """B4/C1: the batch lists the rows that were actually updated, not the plan."""

    def test_deactivate_batch_excludes_a_row_that_changed_after_planning(self):
        a, b = make_user("a", ADMIN), make_user("b", ADMIN)
        ra = SchoolMembership.objects.create(user=a, school=self.school)
        rb = SchoolMembership.objects.create(user=b, school=self.school)
        a.groups.clear()
        b.groups.clear()
        real_ensure_new = batch_log.ensure_new

        def deactivate_b_then_check(path):
            SchoolMembership.objects.filter(pk=rb.pk).update(is_active=False)  # changes between plan and write
            return real_ensure_new(path)

        with mock.patch.object(batch_log, "ensure_new", deactivate_b_then_check):
            report = self.run_json(CHECK, "--deactivate", "--apply", "--batch-file", self.path())
        with open(self.path(), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual([m["id"] for m in data["memberships"]], [ra.pk])
        self.assertEqual(report["would_deactivate"], 1)

    def test_student_batch_excludes_a_row_that_got_a_school_after_planning(self):
        s1 = Student.objects.create(first_name="S", last_name="1", national_id="5100000001", grade=7, phone_number="1")
        s2 = Student.objects.create(first_name="S", last_name="2", national_id="5100000002", grade=7, phone_number="1")
        Student.objects.update(school=None)
        real_ensure_new = batch_log.ensure_new

        def school_s2_then_check(path):
            Student.objects.filter(pk=s2.pk).update(school=self.school)
            return real_ensure_new(path)

        with mock.patch.object(batch_log, "ensure_new", school_s2_then_check):
            report = self.run_json(BACKFILL_S, "--apply", "--batch-file", self.path())
        with open(self.path(), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual([a["student_id"] for a in data["assignments"]], [s1.pk])
        self.assertEqual((report["planned"], report["writes"]), (2, "set 1; batch file written"))
        # reverting must not null s2: it was never written by this run
        self.run_cmd(BACKFILL_S, "--revert-batch", self.path())
        s2.refresh_from_db()
        self.assertEqual(s2.school_id, self.school.pk)

    def test_membership_backfill_refuses_when_the_database_returns_no_ids(self):
        make_user("sa", ADMIN)
        with mock.patch.object(SchoolMembership.objects, "bulk_create",
                               return_value=[SchoolMembership(user_id=1, school_id=1)]):
            with self.assertRaises(CommandError):
                self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path())
        self.assertFalse(os.path.exists(self.path()))


class BatchFileFailureTests(Base):
    def test_a_failing_write_removes_the_file_and_rolls_the_rows_back(self):
        make_user("sa", ADMIN)
        with mock.patch("schools.batch_log.json.dump", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(CommandError):
                self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path())
        self.assertFalse(os.path.exists(self.path()))
        self.assertEqual(SchoolMembership.objects.count(), 0)

    def test_an_unwritable_directory_is_a_command_error_and_rolls_back(self):
        make_user("sa", ADMIN)
        with self.assertRaises(CommandError):
            self.run_cmd(BACKFILL_M, "--apply", "--batch-file", os.path.join(self.tmp.name, "no", "such", "dir.json"))
        self.assertEqual(SchoolMembership.objects.count(), 0)

    def test_an_existing_path_fails_before_any_database_work(self):
        make_user("sa", ADMIN)
        self.write("taken.json", "keep")
        with mock.patch.object(SchoolMembership.objects, "bulk_create") as bulk:
            with self.assertRaises(CommandError):
                self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path("taken.json"))
        bulk.assert_not_called()

    def test_a_dangling_symlink_is_not_followed(self):
        make_user("sa", ADMIN)
        link = self.path("link.json")
        os.symlink(self.path("target.json"), link)
        with self.assertRaises(CommandError):
            self.run_cmd(BACKFILL_M, "--apply", "--batch-file", link)
        self.assertFalse(os.path.exists(self.path("target.json")))


class FlagCombinationTests(Base):
    BAD = {
        CHECK: [("--apply",), ("--batch-file", "X"), ("--deactivate", "--batch-file", "X"),
                ("--revert-batch", "X", "--apply"), ("--revert-batch", "X", "--deactivate"),
                ("--revert-batch", "X", "--batch-file", "Y")],
        BACKFILL_M: [("--batch-file", "X"), ("--revert-batch", "X", "--apply"),
                     ("--revert-batch", "X", "--batch-file", "Y")],
        BACKFILL_S: [("--batch-file", "X"), ("--accept-visibility-change",),
                     ("--revert-batch", "X", "--apply"), ("--revert-batch", "X", "--batch-file", "Y"),
                     ("--revert-batch", "X", "--accept-visibility-change")],
    }

    def test_invalid_combinations_are_rejected_and_write_nothing(self):
        user = make_user("orphan", ADMIN)
        row = SchoolMembership.objects.create(user=user, school=self.school)
        user.groups.clear()
        make_user("sa", ADMIN)
        for command, combos in self.BAD.items():
            # X is a VALID empty batch of the command, so only the flag rule can reject a combination
            valid = {"command": command, "version": batch_log.VERSION, "school_id": 1,
                     "memberships": [], "assignments": []}
            self.write(f"valid-{command}.json", valid)
            for combo in combos:
                args = [self.path(f"valid-{command}.json") if a == "X" else self.path("new.json") if a == "Y" else a
                        for a in combo]
                with self.subTest(command=command, args=combo), self.assertRaises(CommandError):
                    self.run_cmd(command, *args)
        row.refresh_from_db()
        self.assertTrue(row.is_active)
        self.assertEqual(SchoolMembership.objects.count(), 1)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), sorted(f"valid-{c}.json" for c in self.BAD))  # no new file

    def test_apply_without_deactivate_is_an_error_even_when_there_is_nothing_to_report(self):
        make_user("sa", ADMIN)
        with self.assertRaises(CommandError):
            self.run_cmd(CHECK, "--apply")
        with self.assertRaises(CommandError):
            self.run_cmd(CHECK, "--apply", "--batch-file", self.path())
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_valid_combinations_still_work(self):
        make_user("sa", ADMIN)
        self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path("a.json"))
        self.run_cmd(BACKFILL_M, "--revert-batch", self.path("a.json"))
        self.run_cmd(CHECK, "--deactivate")
        self.run_cmd(CHECK, "--deactivate", "--apply", "--batch-file", self.path("b.json"))
        self.run_cmd(BACKFILL_S, "--apply", "--batch-file", self.path("c.json"), "--accept-visibility-change")


class EmptyAndOddOptionValueTests(Base):
    """S2 review R2: a GIVEN option with an empty value is an error, never 'absent' (no silent dry-run)."""

    def valid_batch(self, command):
        return self.write("v.json", {"command": command, "version": batch_log.VERSION, "school_id": 1,
                                     "memberships": [], "assignments": []})

    def test_empty_revert_batch_is_an_error_not_a_dry_run(self):
        make_user("orphan", ADMIN).groups.clear()
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            for value in ("", "   "):
                with self.subTest(command=command, value=repr(value), style="argv"), self.assertRaises(CommandError):
                    self.run_cmd(command, "--revert-batch", value)
                with self.subTest(command=command, value=repr(value), style="kwargs"), self.assertRaises(CommandError):
                    call_command(command, revert_batch=value, stdout=StringIO())

    def test_empty_batch_file_is_an_error_even_without_apply(self):
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            for args in (("--batch-file", ""), ("--apply", "--batch-file", ""), ("--apply", "--batch-file", " ")):
                extra = ("--deactivate",) if command == CHECK and "--apply" in args else ()
                with self.subTest(command=command, args=args), self.assertRaises(CommandError):
                    self.run_cmd(command, *extra, *args)

    def test_nul_byte_in_a_path_option_is_rejected_up_front_before_any_database_work(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            with self.subTest(command=command, option="revert"):
                with CaptureQueriesContext(connection) as ctx, self.assertRaises(CommandError) as err:
                    call_command(command, revert_batch="a\0b.json", stdout=StringIO())
                self.assertIn("NUL byte", str(err.exception))
                self.assertEqual(len(ctx.captured_queries), 0)
            with self.subTest(command=command, option="batch"):
                extra = {"deactivate": True} if command == CHECK else {}
                with CaptureQueriesContext(connection) as ctx, self.assertRaises(CommandError) as err:
                    call_command(command, apply=True, batch_file="a\0b.json", stdout=StringIO(), **extra)
                self.assertIn("NUL byte", str(err.exception))
                self.assertEqual(len(ctx.captured_queries), 0)

    def test_write_batch_itself_turns_a_nul_path_into_a_command_error(self):
        with self.assertRaises(CommandError):
            batch_log.write_batch("a\0b.json", "x", {})

    def test_empty_options_write_nothing(self):
        user = make_user("sa", ADMIN)
        before = SchoolMembership.objects.count()
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            with self.assertRaises(CommandError):
                self.run_cmd(command, "--apply", *(("--deactivate",) if command == CHECK else ()), "--batch-file", "")
        self.assertEqual(SchoolMembership.objects.count(), before)
        self.assertIsNotNone(user.pk)

    def test_a_normal_path_still_works(self):
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            self.assertEqual(self.run_json(command, "--revert-batch", self.valid_batch(command))["writes"], "reverted")


class VersionMessageTests(Base):
    def test_unsupported_version_is_named_and_distinct_from_a_wrong_command(self):
        for command in (CHECK, BACKFILL_M, BACKFILL_S):
            path = self.write("old.json", {"command": command, "version": 1})
            with self.assertRaises(CommandError) as ctx:
                self.run_cmd(command, "--revert-batch", path)
            self.assertIn("Unsupported batch version 1", str(ctx.exception))
            self.assertIn("older version", str(ctx.exception))
            path = self.write("foreign.json", {"command": "other", "version": batch_log.VERSION})
            with self.assertRaises(CommandError) as ctx:
                self.run_cmd(command, "--revert-batch", path)
            self.assertIn("not a batch file", str(ctx.exception))
            self.assertNotIn("Unsupported", str(ctx.exception))

    def test_a_hostile_version_value_is_not_echoed(self):
        path = self.write("v.json", {"command": CHECK, "version": "<script>x</script>"})
        with self.assertRaises(CommandError) as ctx:
            self.run_cmd(CHECK, "--revert-batch", path)
        self.assertIn("Unsupported batch version unknown", str(ctx.exception))
        self.assertNotIn("script", str(ctx.exception))


class WriteBatchCleanupTests(Base):
    def test_keyboard_interrupt_and_memory_error_remove_the_file_roll_back_and_propagate(self):
        make_user("sa", ADMIN)
        for exc in (KeyboardInterrupt, MemoryError):
            with self.subTest(exc=exc.__name__):
                with mock.patch("schools.batch_log.json.dump", side_effect=exc()):
                    with self.assertRaises(exc):
                        self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path())
                self.assertFalse(os.path.exists(self.path()))
                self.assertEqual(SchoolMembership.objects.count(), 0)

    def test_only_the_file_this_call_created_is_removed(self):
        """A file swapped onto the path while the write was failing must survive."""
        target = self.path("swap.json")

        def swap_then_fail(*args, **kwargs):
            os.unlink(target)
            with open(target, "w", encoding="utf-8") as other:
                other.write("somebody else's file")
            raise OSError(28, "No space left on device")

        with mock.patch("schools.batch_log.json.dump", side_effect=swap_then_fail):
            with self.assertRaises(CommandError):
                batch_log.write_batch(target, "x", {})
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "somebody else's file")

    def test_the_created_file_is_removed_when_it_is_still_the_same_file(self):
        target = self.path("same.json")
        with mock.patch("schools.batch_log.json.dump", side_effect=OSError(5, "I/O error")):
            with self.assertRaises(CommandError):
                batch_log.write_batch(target, "x", {})
        self.assertFalse(os.path.exists(target))

    def test_mode_is_0600(self):
        batch_log.write_batch(self.path("m.json"), "x", {})
        self.assertEqual(os.stat(self.path("m.json")).st_mode & 0o777, 0o600)


class RowLockTests(Base):
    """S2 review R8: the row locks name only the table being changed ('self') and use a stable primary-key order,
    so PostgreSQL does not also lock the joined School rows (observed on PostgreSQL 16, see Change Report 0012)."""

    def record(self):
        from django.db.models.query import QuerySet

        calls = []
        original = QuerySet.select_for_update

        def wrapper(qs, *args, **kwargs):
            calls.append((qs.model.__name__, kwargs.get("of"), args))
            return original(qs, *args, **kwargs)

        return calls, mock.patch.object(QuerySet, "select_for_update", wrapper)

    def test_every_lock_in_the_three_commands_names_self_only(self):
        calls, patch = self.record()
        user = make_user("sa", ADMIN)
        orphan = make_user("orphan", ADMIN)
        SchoolMembership.objects.create(user=orphan, school=self.school)
        orphan.groups.clear()
        Student.objects.create(first_name="S", last_name="1", national_id="6100000001", grade=7, phone_number="1")
        Student.objects.update(school=None)
        with patch:
            self.run_cmd(CHECK, "--deactivate", "--apply", "--batch-file", self.path("a.json"))
            self.run_cmd(CHECK, "--revert-batch", self.path("a.json"))
            self.run_cmd(BACKFILL_M, "--apply", "--batch-file", self.path("b.json"))
            self.run_cmd(BACKFILL_M, "--revert-batch", self.path("b.json"))
            self.run_cmd(BACKFILL_S, "--apply", "--batch-file", self.path("c.json"))
        self.assertTrue(calls)
        self.assertEqual({(model, of) for model, of, _args in calls},
                         {("SchoolMembership", ("self",)), ("Student", ("self",))})
        self.assertIsNotNone(user.pk)

    def test_locked_rows_come_back_in_primary_key_order(self):
        users = [make_user(f"o{i}", ADMIN) for i in range(3)]
        rows = [SchoolMembership.objects.create(user=u, school=self.school) for u in users]
        for u in users:
            u.groups.clear()
        self.run_cmd(CHECK, "--deactivate", "--apply", "--batch-file", self.path())
        with open(self.path(), encoding="utf-8") as handle:
            ids = [m["id"] for m in json.load(handle)["memberships"]]
        self.assertEqual(ids, sorted(r.pk for r in rows))


class MachineReadableGateKeyTests(Base):
    """The documented S3 gate relies on `multi_school_checks_run` in the JSON of BOTH commands."""

    def test_key_is_false_without_and_true_with_the_flag_in_both_commands(self):
        for command in ("check_access_switch_ready", "compare_access_parity"):
            for flag, expected in (((), False), (("--multi-school",), True)):
                out = StringIO()
                try:
                    call_command(command, "--json", *flag, stdout=out)
                except CommandError:
                    pass
                report = json.loads(out.getvalue())
                with self.subTest(command=command, flag=flag):
                    self.assertIs(report["multi_school_checks_run"], expected)
                    self.assertEqual(report["multi_school_checks"], "RUN" if expected else "NOT RUN")

    def test_key_is_present_even_when_the_command_fails(self):
        make_user("sa", ADMIN)  # a SchoolAdmin without membership: both gate commands fail
        Student.objects.create(first_name="S", last_name="1", national_id="6200000001", grade=7, phone_number="1")
        Student.objects.update(school=self.school)
        for command in ("check_access_switch_ready", "compare_access_parity"):
            out = StringIO()
            with self.assertRaises(CommandError):
                call_command(command, "--json", "--multi-school", stdout=out)
            self.assertIs(json.loads(out.getvalue())["multi_school_checks_run"], True)

    def test_text_output_does_not_print_the_json_only_key(self):
        for command in ("check_access_switch_ready", "compare_access_parity"):
            out = StringIO()
            try:
                call_command(command, stdout=out)
            except CommandError:
                pass
            self.assertNotIn("multi_school_checks_run", out.getvalue())
            self.assertIn("multi-school checks: NOT RUN", out.getvalue())


class LockQuerySqlTests(Base):
    """The lock queries carry no join and are ordered by primary key (SQL as executed; FOR UPDATE itself is a no-op
    on SQLite and is checked on PostgreSQL separately)."""

    def test_no_join_and_primary_key_order(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        users = [make_user(f"o{i}", ADMIN) for i in range(2)]
        for u in users:
            SchoolMembership.objects.create(user=u, school=self.school)
            u.groups.clear()
        Student.objects.create(first_name="S", last_name="1", national_id="6300000001", grade=7, phone_number="1")
        Student.objects.update(school=None)
        with CaptureQueriesContext(connection) as ctx:
            self.run_cmd(CHECK, "--deactivate", "--apply", "--batch-file", self.path("a.json"))
            self.run_cmd(CHECK, "--revert-batch", self.path("a.json"))
            self.run_cmd(BACKFILL_S, "--apply", "--batch-file", self.path("c.json"))
        locking = [q["sql"] for q in ctx.captured_queries
                   if q["sql"].startswith("SELECT") and "ORDER BY" in q["sql"]
                   and ('"schools_schoolmembership"."id" IN (' in q["sql"] or '"students_student"."school_id" IS NULL' in q["sql"]
                        and '"students_student"."id" IN (' in q["sql"]
                        or 'WHERE "schools_schoolmembership"."id" =' in q["sql"])]
        self.assertTrue(locking)
        for sql in locking:
            self.assertNotIn("JOIN", sql, sql)
            self.assertRegex(sql, r'ORDER BY "(schools_schoolmembership|students_student)"\."id" ASC|ORDER BY 1 ASC', sql)
