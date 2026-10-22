"""S6-2 tests for ``students.0015_student_school_not_null`` (changes/0010 S6; owner approval 2026-10-23).

Run through ``MigrationExecutor`` with HISTORICAL models on the disposable test database (never a real database), on
SQLite and on PostgreSQL (``scripts/run_tests.sh all``). Synthetic data only.

Once the column is NOT NULL a school-less student cannot exist, so everything that needs one lives here: the state is
built at ``students.0014`` (nullable), the tools run against it, and the migration is applied. Proves:
  * the guard REFUSES while any student has no school, changes nothing, and names the tools that fix it;
  * only ``backfill_student_school`` (and its revert) can make the migration possible;
  * forward and reverse work, and afterwards NOT NULL holds at the database for create, bulk_create, bulk_update,
    queryset update and raw SQL (these bypass ``save()``; the constraint is what stops them).
"""
import importlib
import io
import json
import os
import tempfile
from contextlib import redirect_stdout
from unittest import mock

from django.core.management import call_command
from schools import batch_log
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import QuerySet
from django.test import TransactionTestCase

BEFORE = [('students', '0014_rollover_choices')]
AFTER = [('students', '0015_student_school_not_null')]
MODULE = 'students.migrations.0015_student_school_not_null'


def school_is_nullable():
    with connection.cursor() as cursor:
        columns = {c.name: c.null_ok for c in connection.introspection.get_table_description(cursor, 'students_student')}
    return columns['school_id']


class MigrationCase(TransactionTestCase):
    """Starts every test at students.0014 with a blank slate; restores the latest schema afterwards."""

    def setUp(self):
        self.migrate(BEFORE)
        apps = MigrationExecutor(connection).loader.project_state(BEFORE).apps
        self.School = apps.get_model('schools', 'School')
        self.SchoolClass = apps.get_model('schools', 'SchoolClass')
        self.Student = apps.get_model('students', 'Student')
        for model in (self.Student, self.SchoolClass, self.School):
            model.objects.all().delete()
        self.n = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def tearDown(self):
        self.Student.objects.all().delete()   # leftovers must not trip the guard when the schema is restored
        with redirect_stdout(io.StringIO()):
            call_command('migrate', verbosity=0)

    # -- helpers ---------------------------------------------------------------------------------------------
    def migrate(self, targets):
        MigrationExecutor(connection).migrate(targets)

    def applied(self):
        return AFTER[0] in MigrationRecorder(connection).applied_migrations()

    def school(self, code='s1'):
        return self.School.objects.create(code=code, name=f'School {code}')

    def student(self, school=None, klass=None):
        self.n += 1
        return self.Student.objects.create(
            first_name=f'F{self.n}', last_name=f'L{self.n}', national_id=f'71{self.n:08d}', grade=7, phone_number='0',
            school=school, school_class=klass)

    def refuses(self):
        """Apply 0015; it must raise the guard's exception and leave the database exactly as it was."""
        guard = importlib.import_module(MODULE).StudentsWithoutSchool
        before = sorted(self.Student.objects.values_list('pk', 'school_id'))
        with self.assertRaises(guard) as ctx:
            self.migrate(AFTER)
        self.assertFalse(self.applied())
        self.assertTrue(school_is_nullable())
        self.assertEqual(sorted(self.Student.objects.values_list('pk', 'school_id')), before)
        return str(ctx.exception)

    def run_cmd(self, name, *args):
        out = io.StringIO()
        try:
            call_command(name, *args, stdout=out)
        except CommandError as exc:
            return out.getvalue() + f'\nCommandError: {exc}'
        return out.getvalue()

    def batch(self, name='batch.json'):
        return os.path.join(self.tmp.name, name)


class GuardTests(MigrationCase):
    def test_the_guard_refuses_while_any_student_has_no_school_and_changes_nothing(self):
        school = self.school()
        self.student(school)
        self.student(None)
        message = self.refuses()
        self.assertIn('1 student(s) have no school', message)
        self.assertIn('check_student_school_ready', message)
        self.assertIn('backfill_student_school', message)

    def test_the_guard_counts_every_student_without_a_school(self):
        self.school()
        for _ in range(3):
            self.student(None)
        self.assertIn('3 student(s) have no school', self.refuses())

    def test_the_migration_never_assigns_a_school_itself_even_with_one_school(self):
        self.school()
        s = self.student(None)
        self.refuses()
        self.assertIsNone(self.Student.objects.get(pk=s.pk).school_id)

    def test_it_applies_when_every_student_has_a_school_and_when_there_are_no_students(self):
        self.migrate(AFTER)
        self.assertTrue(self.applied())
        self.assertFalse(school_is_nullable())

    def test_forward_then_reverse_keeps_the_rows_and_makes_the_column_nullable_again(self):
        school = self.school()
        kept = self.student(school).pk
        self.migrate(AFTER)
        self.assertFalse(school_is_nullable())
        self.migrate(BEFORE)
        self.assertFalse(self.applied())
        self.assertTrue(school_is_nullable())
        self.assertEqual(self.Student.objects.get(pk=kept).school_id, school.pk)
        self.student(None)                       # reversible schema: a NULL row is possible again
        self.assertIsNone(self.Student.objects.latest('pk').school_id)


class ToolsTests(MigrationCase):
    """The only way to make 0015 possible is the backfill; the read-only tools report the same picture."""

    def test_check_student_school_ready_says_not_ready_exactly_when_the_guard_refuses(self):
        school = self.school()
        self.student(school)
        report = self.run_cmd('check_student_school_ready')
        self.assertIn('READY', report)
        self.assertNotIn('NOT READY', report)
        self.migrate(AFTER)                      # ready: applies
        self.migrate(BEFORE)
        self.student(None)
        self.assertIn('NOT READY', self.run_cmd('check_student_school_ready'))
        self.refuses()

    def test_backfill_dry_run_is_the_default_and_writes_nothing(self):
        self.school()
        s = self.student(None)
        out = self.run_cmd('backfill_student_school')
        self.assertIn('writes: none', out)
        self.assertIsNone(self.Student.objects.get(pk=s.pk).school_id)
        self.refuses()

    def test_apply_needs_a_batch_file(self):
        self.school()
        self.student(None)
        self.assertIn('CommandError', self.run_cmd('backfill_student_school', '--apply'))
        self.refuses()

    def test_apply_with_one_school_makes_the_migration_possible_and_changes_only_null_rows(self):
        only = self.school('only')
        had = self.student(only)
        null = self.student(None)
        self.refuses()
        self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch())
        self.assertEqual(self.Student.objects.get(pk=null.pk).school_id, only.pk)
        self.assertEqual(self.Student.objects.get(pk=had.pk).school_id, only.pk)
        self.migrate(AFTER)
        self.assertTrue(self.applied())

    def test_a_student_that_already_has_a_school_is_never_changed(self):
        # a second School exists; the NULL class-less row stays unresolved, the other student keeps its school
        a, b = self.school('a'), self.school('b')
        had = self.student(b)
        self.student(None)
        self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch())
        self.assertEqual(self.Student.objects.get(pk=had.pk).school_id, b.pk)
        self.assertIn('1 student(s) have no school', self.refuses())
        self.assertIsNotNone(a.pk)

    def test_with_several_schools_nothing_is_guessed_and_the_guard_still_refuses(self):
        self.school('a')
        self.school('b')
        s = self.student(None)
        out = self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch())
        self.assertIsNone(self.Student.objects.get(pk=s.pk).school_id, out)
        self.assertIn('NOT READY', self.run_cmd('check_student_school_ready'))
        self.refuses()

    def test_inconsistent_school_is_only_counted_and_blocks_readiness(self):
        a, b = self.school('a'), self.school('b')
        klass = self.SchoolClass.objects.create(school=a, title='7-A', academic_year='1404', grade=7)
        s = self.student(a, klass)
        self.Student.objects.filter(pk=s.pk).update(school=b)       # disagrees with its class
        self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch())
        self.assertEqual(self.Student.objects.get(pk=s.pk).school_id, b.pk)    # never changed by the tool
        self.assertIn('students_whose_school_differs_from_their_class_school: 1', self.run_cmd('check_student_school_ready'))

    def test_the_backfill_is_idempotent(self):
        self.school()
        self.student(None)
        self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch('one.json'))
        again = self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch('two.json'))
        self.assertNotIn('Traceback', again)
        self.migrate(AFTER)
        self.assertTrue(self.applied())

    def test_an_existing_batch_file_is_never_overwritten(self):
        self.school()
        s = self.student(None)
        path = self.batch()
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('keep')
        self.assertIn('CommandError', self.run_cmd('backfill_student_school', '--apply', '--batch-file', path))
        self.assertEqual(open(path, encoding='utf-8').read(), 'keep')
        self.assertIsNone(self.Student.objects.get(pk=s.pk).school_id)

    def test_reverting_the_batch_makes_the_guard_refuse_again(self):
        self.school()
        s = self.student(None)
        path = self.batch()
        self.run_cmd('backfill_student_school', '--apply', '--batch-file', path)
        self.assertIsNotNone(self.Student.objects.get(pk=s.pk).school_id)
        self.run_cmd('backfill_student_school', '--revert-batch', path)
        self.assertIsNone(self.Student.objects.get(pk=s.pk).school_id)
        self.refuses()

    def test_revert_leaves_a_student_whose_school_changed_since(self):
        only, other = self.school('only'), self.school('other')
        s = self.student(None)
        path = self.batch()
        self.run_cmd('backfill_student_school', '--apply', '--batch-file', path)
        self.Student.objects.filter(pk=s.pk).update(school=other)
        self.run_cmd('backfill_student_school', '--revert-batch', path)
        self.assertEqual(self.Student.objects.get(pk=s.pk).school_id, other.pk)
        self.assertIsNotNone(only.pk)

    def test_a_row_that_got_a_school_after_planning_is_not_in_the_batch_and_not_reverted(self):
        from schools import batch_log
        only = self.school()
        s1, s2 = self.student(None), self.student(None)
        real = batch_log.ensure_new

        def school_s2_then_check(path):
            self.Student.objects.filter(pk=s2.pk).update(school=only)
            return real(path)

        path = self.batch()
        with mock.patch.object(batch_log, 'ensure_new', school_s2_then_check):
            self.run_cmd('backfill_student_school', '--apply', '--batch-file', path)
        with open(path, encoding='utf-8') as handle:
            self.assertEqual([a['student_id'] for a in json.load(handle)['assignments']], [s1.pk])
        self.run_cmd('backfill_student_school', '--revert-batch', path)
        self.assertEqual(self.Student.objects.get(pk=s2.pk).school_id, only.pk)

    def test_the_multi_school_gate_counts_a_real_school_less_row(self):
        from schools.multischool_checks import readiness_counts
        self.school()
        self.student(None)
        self.assertEqual(readiness_counts()['students_without_school'], 1)

    def test_the_readiness_report_reads_the_real_column_nullability(self):
        import json as _json
        self.school()
        self.student(None)
        self.assertTrue(_json.loads(self.run_cmd('check_student_school_ready', '--json').split('\nCommandError')[0])
                        ['school_column_is_nullable'])

    def test_the_student_lock_of_the_backfill_names_the_student_table_only(self):
        self.school()
        self.student(None)
        calls = []
        real = QuerySet.select_for_update

        def wrapper(qs, *args, **kwargs):
            calls.append((qs.model.__name__, tuple(kwargs.get('of', ()))))
            return real(qs, *args, **kwargs)

        with mock.patch.object(QuerySet, 'select_for_update', wrapper):
            self.run_cmd('backfill_student_school', '--apply', '--batch-file', self.batch())
        students = [c for c in calls if c[0] == 'Student']
        self.assertTrue(students)
        self.assertTrue(all(c[1] == ('self',) for c in students), calls)

    def test_the_hostile_batch_files_are_rejected_without_touching_rows(self):
        self.school()
        s = self.student(None)
        path = self.batch()
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'command': 'backfill_student_school', 'version': 1, 'school_id': 1,
                       'assignments': [{'student_id': True, 'school_id': 1}]}, handle)
        self.assertIn('CommandError', self.run_cmd('backfill_student_school', '--revert-batch', path))
        self.assertIsNone(self.Student.objects.get(pk=s.pk).school_id)


class NotNullAtTheDatabaseTests(MigrationCase):
    """After 0015 the constraint, not save(), stops every write that bypasses save() (closes review finding F3)."""

    def setUp(self):
        super().setUp()
        self.keep = self.student(self.school()).pk
        self.migrate(AFTER)
        from students.models import Student
        self.Real = Student

    def fails(self, action):
        with self.assertRaises(IntegrityError), transaction.atomic():
            action()
        self.assertIsNotNone(self.Real.objects.get(pk=self.keep).school_id)

    def test_create(self):
        self.fails(lambda: self.Real.objects.create(first_name='N', last_name='S', national_id='7199999991', grade=7,
                                                    phone_number='0', school_id=None))

    def test_bulk_create(self):
        self.fails(lambda: self.Real.objects.bulk_create([self.Real(
            first_name='N', last_name='S', national_id='7199999992', grade=7, phone_number='0', school_id=None)]))

    def test_bulk_update(self):
        student = self.Real.objects.get(pk=self.keep)
        student.school_id = None
        self.fails(lambda: self.Real.objects.bulk_update([student], ['school']))

    def test_queryset_update(self):
        self.fails(lambda: self.Real.objects.filter(pk=self.keep).update(school=None))

    def test_raw_sql(self):
        def raw():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE students_student SET school_id = NULL WHERE id = %s', [self.keep])
        self.fails(raw)

    def test_the_readiness_report_says_the_column_is_not_nullable(self):
        out = io.StringIO()
        call_command('check_student_school_ready', '--json', stdout=out)
        self.assertFalse(json.loads(out.getvalue())['school_column_is_nullable'])

    def test_reverting_a_backfill_batch_after_0015_is_refused_clearly_and_changes_nothing(self):
        path = self.batch()
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'command': 'backfill_student_school', 'version': batch_log.VERSION, 'school_id': 1,
                       'assignments': [{'student_id': self.keep, 'school_id': 1}]}, handle)
        out = io.StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command('backfill_student_school', '--revert-batch', path, stdout=out)
        self.assertIn('NOT NULL since students.0015', str(ctx.exception))
        self.assertIsNotNone(self.Real.objects.get(pk=self.keep).school_id)

    def test_save_still_works_for_a_student_with_a_school(self):
        student = self.Real.objects.get(pk=self.keep)
        student.first_name = 'Renamed'
        student.save()
        self.assertEqual(self.Real.objects.get(pk=self.keep).first_name, 'Renamed')
