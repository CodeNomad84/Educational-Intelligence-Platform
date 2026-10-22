"""C3b tests for ``students.0009_link_students_to_classes`` (proposal 0002, ADR-0004).

The migration is exercised through ``MigrationExecutor`` and HISTORICAL models on the disposable test
database (never a real database). All data is synthetic.
Traceability: REQ: P2-REQ-18 (class_name untouched, never auto-merge), P2-REQ-19 (migrated data never grants
access, fail closed).
Run with:  python manage.py test students.test_migration_0009
"""
import ast
import importlib
import io
import random
import re
from contextlib import redirect_stdout
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from .class_links import plan_class_links

BEFORE = [('students', '0008_student_school_student_school_class_and_more')]
AFTER = [('students', '0009_link_students_to_classes')]
MODULE = 'students.migrations.0009_link_students_to_classes'
OLD = datetime(2020, 1, 1, 12, 0, tzinfo=dt_timezone.utc)

PERSIAN_10A = '۱۰-الف'   # ۱۰-الف
ASCII_10A = '10-الف'               # 10-الف
BARE = 'الف'                       # الف
ZWNJ = chr(0x200C)   # zero-width non-joiner, built with chr() so an editor can never strip it
NBSP = chr(0x00A0)   # no-break space, same reason


def migration_module():
    return importlib.import_module(MODULE)


class MigrationCase(TransactionTestCase):
    """Starts every test at students.0008 with a blank slate; restores the latest schema afterwards."""

    def setUp(self):
        self.migrate(BEFORE)
        apps = MigrationExecutor(connection).loader.project_state(BEFORE).apps
        self.School = apps.get_model('schools', 'School')
        self.SchoolClass = apps.get_model('schools', 'SchoolClass')
        self.TeacherAssignment = apps.get_model('schools', 'TeacherAssignment')
        self.Student = apps.get_model('students', 'Student')
        self.User = apps.get_model('auth', 'User')
        for model in (self.TeacherAssignment, self.Student, self.SchoolClass, self.School):
            model.objects.all().delete()
        self.n = 0

    def tearDown(self):
        self.Student.objects.all().delete()   # S6-2: rows without a school would make students.0015 refuse
        with redirect_stdout(io.StringIO()):  # re-applies 0009 on leftover test data; keep the log quiet
            call_command('migrate', verbosity=0)  # back to the latest schema for the next test

    # -- helpers ------------------------------------------------------------------------------------------
    def migrate(self, targets):
        MigrationExecutor(connection).migrate(targets)

    def apply(self):
        """Run students.0009 and return {counter: value} parsed from its (personal-data-free) output line."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.migrate(AFTER)
        self.output = buf.getvalue()
        return self.parse(self.output)

    @staticmethod
    def parse(text):
        match = re.search(r'link_students_to_classes: (.*)', text)
        if not match:
            return {}
        out = {}
        for pair in match.group(1).split(', '):
            key, _, value = pair.partition('=')
            out[key] = {'True': True, 'False': False}.get(value, int(value) if value.lstrip('-').isdigit() else value)
        return out

    def applied(self):
        return ('students', '0009_link_students_to_classes') in MigrationRecorder(connection).applied_migrations()

    def school(self, code='s1', name='School One'):
        return self.School.objects.create(code=code, name=name)

    def klass(self, school, title, *, year='', active=True):
        return self.SchoolClass.objects.create(school=school, title=title, academic_year=year, is_active=active)

    def student(self, class_name, grade, *, school=None, school_class=None):
        self.n += 1
        row = self.Student.objects.create(
            first_name=f'F{self.n}', last_name=f'L{self.n}', national_id=f'70{self.n:08d}', grade=grade,
            phone_number='0', class_name=class_name, school=school, school_class=school_class)
        self.Student.objects.filter(pk=row.pk).update(updated_at=OLD)  # auto_now only fires on save()
        return row.pk

    def row(self, pk):
        return self.Student.objects.get(pk=pk)

    def snapshot(self):
        return {s.pk: (s.class_name.encode(), s.updated_at, s.school_id, s.school_class_id)
                for s in self.Student.objects.all()}

    def assert_class_name_and_updated_at_unchanged(self, before):
        after = self.snapshot()
        self.assertEqual(set(before), set(after))
        for pk, (name, stamp, _school, _klass) in before.items():
            self.assertEqual(after[pk][0], name, f'class_name changed for student {pk}')
            self.assertEqual(after[pk][1], stamp, f'updated_at changed for student {pk}')

    def assert_constraint_holds(self):
        self.assertEqual(self.Student.objects.filter(school_class__isnull=False, school__isnull=True).count(), 0)
        for s in self.Student.objects.filter(school_class__isnull=False).select_related('school_class'):
            self.assertEqual(s.school_id, s.school_class.school_id)


class LinkingRulesTests(MigrationCase):
    def test_full_matrix_with_one_school(self):
        """REQ: P2-REQ-18, P2-REQ-19"""
        school = self.school()
        ids = {
            'a1': self.student(PERSIAN_10A, 10), 'a2': self.student('  ' + PERSIAN_10A + ' ', 10),
            'ascii': self.student(ASCII_10A, 10),
            'b': self.student('ب', 9),
            'blank': self.student('', 9), 'blank_ws': self.student(' \t ', 9),
            'multi9': self.student(BARE, 9), 'multi10': self.student(BARE, 10),
            'fifty': self.student('x' * 50, 8),
            'ar_yeh': self.student('يك', 8), 'fa_yeh': self.student('یک', 8),
            'zwnj': self.student('می' + ZWNJ + 'شود', 8),
            'no_zwnj': self.student('میشود', 8),
        }
        # An over-limit legacy name can only be stored where varchar(50) is not enforced (SQLite). On PostgreSQL
        # the column rejects it, so it cannot exist there and is not written; the rule itself is asserted at the
        # planner level below for every backend.
        over_limit_stored = connection.vendor == 'sqlite'
        if over_limit_stored:
            ids['fifty_one'] = self.student('y' * 51, 8)
        before = self.snapshot()
        report = self.apply()

        titles = {c.title for c in self.SchoolClass.objects.all()}
        self.assertEqual(titles, {PERSIAN_10A, ASCII_10A, 'ب', 'x' * 50, 'يك', 'یک',
                                  'می' + ZWNJ + 'شود', 'میشود'})
        for c in self.SchoolClass.objects.all():
            self.assertEqual((c.school_id, c.academic_year, c.is_active), (school.pk, '', True))
        self.assertEqual(self.row(ids['a1']).school_class_id, self.row(ids['a2']).school_class_id)
        self.assertNotEqual(self.row(ids['a1']).school_class_id, self.row(ids['ascii']).school_class_id)
        for key in ('blank', 'blank_ws', 'multi9', 'multi10') + (('fifty_one',) if over_limit_stored else ()):
            self.assertIsNone(self.row(ids[key]).school_class_id, key)
        for pk in ids.values():
            self.assertEqual(self.row(pk).school_id, school.pk)  # every student gets the default school
        self.assert_class_name_and_updated_at_unchanged(before)
        self.assert_constraint_holds()
        self.assertEqual((report['linked_students'], report['classes_created'], report['blank_students'],
                          report['multi_grade_titles'], report['multi_grade_students'],
                          report['too_long_titles'], report['too_long_students']),
                         (9, 8, 2, 1, 2) + ((1, 1) if over_limit_stored else (0, 0)))
        plan = plan_class_links([('y' * 51, 8), ('x' * 50, 8)])   # backend-independent rule: 51 is too long, 50 fits
        self.assertEqual((plan.titles('too_long'), plan.titles('linkable')), (['y' * 51], ['x' * 50]))

    def test_no_teacher_assignment_is_created_and_existing_ones_survive(self):
        """REQ: P2-REQ-19"""
        school = self.school()
        klass = self.klass(school, 'T')
        teacher = self.User.objects.create(username='t1')
        self.TeacherAssignment.objects.create(teacher=teacher, school_class=klass)
        self.student('T', 9)
        self.student('U', 9)
        self.apply()
        self.assertEqual(self.TeacherAssignment.objects.count(), 1)
        self.assertEqual(self.User.objects.count(), 1)

    def test_output_has_counts_only(self):
        self.school()
        self.student('Secret Class Name', 9)
        self.apply()
        self.assertIn('linked_students=1', self.output)
        for personal in ('F1', 'L1', '7000000001', 'Secret'):
            self.assertNotIn(personal, self.output)

    def test_large_title_with_more_variants_than_one_chunk(self):
        school = self.school()
        # 520 distinct raw spellings of the single title 'T', each within the real 50-character column
        spellings = [' ' * left + 'T' + ' ' * right
                     for left in range(0, 50) for right in range(0, 50 - left)][:520]
        self.assertEqual(len(set(spellings)), 520)
        self.assertTrue(all(len(s) <= 50 for s in spellings))
        ids = [self.student(s, 9) for s in spellings]
        report = self.apply()
        self.assertEqual(self.SchoolClass.objects.filter(school=school).count(), 1)
        self.assertEqual(self.Student.objects.filter(school_class__isnull=False).count(), len(ids))
        self.assertEqual(report['linked_students'], 520)

    def test_school_already_populated_is_respected(self):
        school = self.school()
        with_class = self.student('T', 9, school=school)
        blank = self.student('', 9, school=school)
        before = self.snapshot()
        self.apply()
        self.assertEqual(self.row(with_class).school_id, school.pk)
        self.assertIsNotNone(self.row(with_class).school_class_id)
        self.assertEqual((self.row(blank).school_id, self.row(blank).school_class_id), (school.pk, None))
        self.assert_class_name_and_updated_at_unchanged(before)


class ExistingClassTests(MigrationCase):
    def test_active_exact_class_is_reused_not_duplicated(self):
        school = self.school()
        klass = self.klass(school, 'T')
        pk = self.student(' T ', 9)
        report = self.apply()
        self.assertEqual(self.SchoolClass.objects.count(), 1)
        self.assertEqual(self.row(pk).school_class_id, klass.pk)
        self.assertEqual((report['classes_reused'], report['classes_created']), (1, 0))

    def test_inactive_exact_class_is_skipped_and_not_reactivated(self):
        school = self.school()
        klass = self.klass(school, 'T', active=False)
        pk = self.student('T', 9)
        before = self.snapshot()
        report = self.apply()
        self.assertFalse(self.SchoolClass.objects.get(pk=klass.pk).is_active)
        self.assertEqual(self.SchoolClass.objects.count(), 1)
        self.assertIsNone(self.row(pk).school_class_id)
        self.assertEqual(self.row(pk).school_id, school.pk)
        self.assertEqual((report['inactive_class_titles'], report['inactive_class_students']), (1, 1))
        self.assert_class_name_and_updated_at_unchanged(before)

    def test_same_title_only_in_another_year_is_not_used(self):
        school = self.school()
        other_year = self.klass(school, 'T', year='1404')
        pk = self.student('T', 9)
        self.apply()
        self.assertEqual(self.SchoolClass.objects.count(), 2)
        new = self.SchoolClass.objects.get(school=school, title='T', academic_year='')
        self.assertEqual(self.row(pk).school_class_id, new.pk)
        self.assertEqual(self.Student.objects.filter(school_class=other_year).count(), 0)

    def test_normalization_collision_with_stored_title_links_nothing_and_creates_nothing(self):
        school = self.school()
        padded = self.klass(school, 'T ')          # stored form differs, identity is the same
        pk = self.student('T', 9)
        report = self.apply()
        self.assertEqual(list(self.SchoolClass.objects.values_list('title', flat=True)), ['T '])
        self.assertEqual(self.SchoolClass.objects.get(pk=padded.pk).title, 'T ')
        self.assertIsNone(self.row(pk).school_class_id)
        self.assertEqual((report['normalization_collision_titles'], report['normalization_collision_students']),
                         (1, 1))

    def test_collision_wins_even_when_the_exact_class_also_exists(self):
        school = self.school()
        self.klass(school, 'T')
        self.klass(school, 'T ')
        pk = self.student('T', 9)
        self.apply()
        self.assertEqual(self.SchoolClass.objects.count(), 2)
        self.assertIsNone(self.row(pk).school_class_id)

    def test_already_linked_students_are_untouched_even_with_different_legacy_text(self):
        school = self.school()
        klass = self.klass(school, 'X')
        linked = self.student('old legacy text', 9, school=school, school_class=klass)
        unlinked = self.student('old legacy text', 9)
        before = self.snapshot()
        report = self.apply()
        self.assertEqual(self.row(linked).school_class_id, klass.pk)
        self.assertNotEqual(self.row(unlinked).school_class_id, klass.pk)
        self.assertEqual(report['already_linked_untouched'], 1)
        self.assert_class_name_and_updated_at_unchanged(before)

    def test_multi_grade_title_counts_already_linked_students(self):
        """A linked student of another grade makes the title ambiguous for the unlinked one."""
        school = self.school()
        klass = self.klass(school, 'M')
        linked = self.student('M', 9, school=school, school_class=klass)
        unlinked = self.student('M', 10)
        self.apply()
        self.assertEqual(self.row(linked).school_class_id, klass.pk)
        self.assertIsNone(self.row(unlinked).school_class_id)
        self.assertEqual(self.SchoolClass.objects.count(), 1)


class SchoolResolutionTests(MigrationCase):
    def test_zero_schools_creates_the_default_school(self):
        pk = self.student('T', 9)
        with override_settings(DEFAULT_SCHOOL_NAME='Test School'):
            report = self.apply()
        school = self.School.objects.get()
        self.assertEqual((school.code, school.name), ('default', 'Test School'))
        self.assertTrue(report['school_created'])
        self.assertEqual(self.row(pk).school_id, school.pk)
        self.assertIsNotNone(self.row(pk).school_class_id)

    def test_zero_schools_uses_the_neutral_default_name(self):
        self.student('T', 9)
        self.apply()
        self.assertEqual(self.School.objects.get().name, settings.DEFAULT_SCHOOL_NAME)

    def test_one_school_is_used_and_nothing_is_created(self):
        school = self.school(code='real', name='Real School')
        self.student('T', 9)
        report = self.apply()
        self.assertEqual(self.School.objects.count(), 1)
        self.assertFalse(report['school_created'])
        self.assertEqual(self.Student.objects.get().school_id, school.pk)

    def test_multiple_schools_is_a_reported_noop(self):
        self.school('a', 'A')
        self.school('b', 'B')
        pk = self.student('T', 9)
        before = self.snapshot()
        report = self.apply()
        self.assertTrue(report['noop_multiple_schools'])
        self.assertEqual(self.SchoolClass.objects.count(), 0)
        self.assertEqual((self.row(pk).school_id, self.row(pk).school_class_id), (None, None))
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.applied())  # the migration itself still completes

    def test_overlong_or_blank_default_name_fails_clearly_and_changes_nothing(self):
        self.student('T', 9)
        for bad in ('n' * 201, '   '):
            with override_settings(DEFAULT_SCHOOL_NAME=bad):
                with self.assertRaises(ImproperlyConfigured):
                    self.migrate(AFTER)
            self.assertEqual(self.School.objects.count(), 0)
            self.assertEqual(self.SchoolClass.objects.count(), 0)
            self.assertFalse(self.applied())

    def test_failure_partway_rolls_everything_back(self):
        """Atomic: a crash after the school and a class were created leaves no trace."""
        self.student('A', 9)
        self.student('B', 9)
        module = migration_module()
        real, calls = module._link_title, []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('simulated failure on the second title')
            return real(*args, **kwargs)

        with mock.patch.object(module, '_link_title', flaky):
            with self.assertRaises(RuntimeError):
                self.migrate(AFTER)
        self.assertEqual((self.School.objects.count(), self.SchoolClass.objects.count()), (0, 0))
        self.assertEqual(self.Student.objects.filter(school__isnull=False).count(), 0)
        self.assertEqual(self.Student.objects.filter(school_class__isnull=False).count(), 0)
        self.assertFalse(self.applied())


class ReverseAndIdempotenceTests(MigrationCase):
    def test_reverse_to_0008_retains_links_and_classes(self):
        self.school()
        pk = self.student('T', 9)
        self.apply()
        linked_to = self.row(pk).school_class_id
        self.assertIsNotNone(linked_to)
        self.migrate(BEFORE)  # reverse = no-op
        self.assertFalse(self.applied())
        self.assertEqual(self.row(pk).school_class_id, linked_to)
        self.assertEqual(self.SchoolClass.objects.count(), 1)
        self.assertEqual(self.row(pk).class_name, 'T')

    def test_reapply_is_idempotent(self):
        self.school()
        self.student('T', 9)
        self.student('U', 10)
        self.student('', 9)
        self.student(BARE, 9)
        self.student(BARE, 10)
        self.apply()
        first = (self.snapshot(), sorted(self.SchoolClass.objects.values_list('pk', 'title')))
        self.migrate(BEFORE)
        report = self.apply()
        second = (self.snapshot(), sorted(self.SchoolClass.objects.values_list('pk', 'title')))
        self.assertEqual(first, second)
        self.assertEqual((report['linked_students'], report['classes_created']), (0, 0))

    def test_migration_declares_noop_reverse_atomic_and_reviewed_dependencies(self):
        module = migration_module()
        migration = module.Migration
        self.assertTrue(migration.atomic)
        self.assertEqual(sorted(migration.dependencies), sorted([
            ('schools', '0001_initial'),
            ('students', '0008_student_school_student_school_class_and_more')]))
        (operation,) = migration.operations
        self.assertIs(operation.reverse_code, migrations.RunPython.noop)


class FrozenLogicParityTests(SimpleTestCase):
    FIXTURES = [
        (PERSIAN_10A, 10), ('  ' + PERSIAN_10A + ' ', 10), (ASCII_10A, 10), ('١٠-الف', 10),
        (BARE, 9), (BARE, 10), (' ' + BARE, 8), ('', 9), ('   ', 9), (None, 9), (NBSP, 9),
        ('x' * 50, 8), ('x' * 51, 8), (' ' + 'x' * 50 + ' ', 8),
        ('می' + ZWNJ + 'شود', 8), ('میشود', 8),
        ('يك', 8), ('یک', 9), ('A-1', 9), ('a-1', 9), ('10_A', 9), ('10 A', 9),
    ]

    def assert_parity(self, rows):
        frozen_status, frozen_students, frozen_blank = migration_module()._classify(rows)
        plan = plan_class_links(rows)
        self.assertEqual(frozen_status, plan.status)
        self.assertEqual(frozen_students, plan.students)
        self.assertEqual(frozen_blank, plan.blank_count)

    def test_parity_on_the_approved_fixtures(self):
        self.assert_parity(self.FIXTURES)

    def test_parity_on_a_deterministic_randomized_corpus(self):
        alphabet = ['الف', 'ب', 'x', '1', '۱', '١', ' ', '\t', NBSP, ZWNJ,
                    '-', '_', 'ي', 'ی', 'ك', 'ک', 'A', 'a']
        rng = random.Random(20261014)
        # About a third of the titles come from a small pool, so the SAME title recurs with different grades
        # (multi-grade) and in padded spellings; the rest are fully random (mostly unique or over 50 chars).
        pool = [''.join(rng.choices(alphabet, k=rng.randint(1, 8))) for _ in range(25)]
        rows = []
        for _ in range(600):
            if rng.random() < 0.35:
                title = ' ' * rng.randint(0, 2) + rng.choice(pool) + ' ' * rng.randint(0, 2)
            else:
                title = ''.join(rng.choices(alphabet, k=rng.randint(0, 70)))
            rows.append((title, rng.choice([7, 8, 9, 10, 11])))
        plan = plan_class_links(rows)
        # The corpus must actually exercise every decision, otherwise parity on it proves little.
        self.assertEqual(set(plan.status.values()), {'linkable', 'multi_grade', 'too_long'})
        self.assertGreater(plan.blank_count, 0)
        self.assert_parity(rows)
        for size in (1, 2, 5):  # small corpora hit different branches (single grade, empty, all blank)
            self.assert_parity(rows[:size])
        self.assert_parity([])

    def test_helper_functions_agree(self):
        module = migration_module()
        from .class_links import MAX_TITLE_LENGTH, normalize_title
        self.assertEqual(module.MAX_TITLE_LENGTH, MAX_TITLE_LENGTH)
        for value in [v for v, _g in self.FIXTURES] + ['\t a \n b ']:
            self.assertEqual(module._normalize(value), normalize_title(value))

    def test_migration_module_imports_no_runtime_models_or_helpers(self):
        path = Path(migration_module().__file__)
        tree = ast.parse(path.read_text(encoding='utf-8'))
        imported, violations = [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or '')
                if node.level:  # `from ..class_links import x` / `from .. import models` reach app code too
                    violations.append(f'relative import (level {node.level}, module {node.module!r})')
            elif isinstance(node, ast.Call):
                func = node.func
                called = getattr(func, 'attr', getattr(func, 'id', ''))
                if called in ('import_module', '__import__'):
                    violations.append(f'dynamic import via {called}()')
        self.assertTrue(imported)
        for name in imported:
            if name in ('students', 'schools') or name.startswith(('students.', 'schools.')):
                violations.append(f'import of {name}')
            if 'get_user_model' in name:
                violations.append(f'import of {name}')
        self.assertEqual(violations, [])
        source = path.read_text(encoding='utf-8')
        for model in ("apps.get_model('schools', 'School')", "apps.get_model('schools', 'SchoolClass')",
                      "apps.get_model('students', 'Student')"):
            self.assertIn(model, source)
        self.assertNotIn('TeacherAssignment', source.split('"""', 2)[2])  # never touched outside the docstring
