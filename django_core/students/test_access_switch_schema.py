"""S3 first step R-h (K-F6, changes/0010): the 4c counters of ``check_access_switch_ready`` have a declared schema like the
multi-school ones: named PROBLEM/INFO tuples, a producer read by a source test, and an unclassified, missing or invalid
counter is a blocker (fail closed), with or without ``--multi-school``."""
import ast
import inspect
import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from schools.models import School
from students.management.commands import check_access_switch_ready as command

TARGET = 'students.management.commands.check_access_switch_ready.access_switch_counts'


def run(*flags, patched=None):
    out = StringIO()
    rc = 0
    context = mock.patch(TARGET, patched) if patched else mock.MagicMock()
    with context:
        try:
            call_command('check_access_switch_ready', '--json', *flags, stdout=out)
        except CommandError:
            rc = 1
    return json.loads(out.getvalue()), rc


class AccessSwitchCountsSchemaTests(TestCase):
    @staticmethod
    def source_keys():
        tree = ast.parse(inspect.getsource(command.access_switch_counts).lstrip())
        keys, problems = set(), []
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'r':
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    keys.add(node.slice.value)
                else:
                    problems.append('non-literal key on r')
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'r'
                    and node.func.attr in ('update', 'setdefault', 'pop', 'popitem', 'clear', 'subtract')):
                problems.append(f'r.{node.func.attr}(...)')
        return keys, problems

    def test_every_key_written_is_declared_and_every_declared_key_has_a_producer(self):
        keys, problems = self.source_keys()
        declared = set(command.PROBLEM_KEYS) | set(command.INFO_KEYS)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(keys - declared), [])           # a new counter must be classified
        self.assertEqual(sorted(declared - keys), [])           # a declared counter must still be produced

    def test_the_tuples_are_disjoint_and_the_blocker_name_is_the_problem_tuple(self):
        self.assertEqual(set(command.PROBLEM_KEYS) & set(command.INFO_KEYS), set())
        self.assertIs(command.BLOCKERS, command.PROBLEM_KEYS)

    def test_the_tuples_have_exactly_the_expected_literal_contents(self):
        """K-F3 / review F4: moving a blocker into INFO_KEYS (or adding one) must be a visible, deliberate test change."""
        self.assertEqual(sorted(command.PROBLEM_KEYS), sorted([
            'schools_with_students_but_no_current_year', 'students_missing_current_enrollment',
            'students_class_grade_conflict_would_vanish', 'enrollment_mirror_disagreements',
            'grade_lead_assignments_with_unresolved_year', 'grade_lead_assignments_year_has_no_academic_year_row',
            'grade_lead_assignments_year_not_current', 'teacher_assignments_class_without_current_enrollments']))
        self.assertEqual(sorted(command.INFO_KEYS), sorted([
            'students', 'info_students_without_class_invisible_to_staff',
            'info_students_with_stale_or_unresolved_class_year', 'info_continuing_students_without_current_enrollment',
            'grade_lead_assignments_active', 'info_teacher_assignments_with_blank_or_invalid_subject_grant_nothing',
            'teacher_assignments_active']))

    def test_the_producer_reports_exactly_the_declared_schema(self):
        declared = set(command.PROBLEM_KEYS) | set(command.INFO_KEYS)
        self.assertEqual(set(command.access_switch_counts()), declared)       # empty database
        School.objects.create(name='A', code='a')
        self.assertEqual(set(command.access_switch_counts()), declared)

    def test_a_clean_state_is_ready_with_and_without_the_flag(self):
        for flags in ((), ('--multi-school',)):
            report, rc = run(*flags)
            self.assertEqual((report['verdict'], rc), ('READY', 0))
            for name in ('unclassified_counters', 'missing_counters', 'invalid_counters'):
                self.assertNotIn(name, report)

    def test_each_problem_key_alone_fails_the_gate(self):
        real = command.access_switch_counts
        for flags in ((), ('--multi-school',)):
            for key in command.PROBLEM_KEYS:
                with self.subTest(key=key, flags=flags):
                    report, rc = run(*flags, patched=lambda key=key: {**real(), key: 1})
                    self.assertEqual((rc, report['verdict']), (1, 'NOT READY'))
                    self.assertEqual(report['blockers_nonzero'].get(key), 1)
                    self.assertIs(report['multi_school_passed'], False)

    def test_each_info_key_alone_never_fails_the_gate(self):
        real = command.access_switch_counts
        for key in command.INFO_KEYS:
            with self.subTest(key=key):
                report, rc = run('--multi-school', patched=lambda key=key: {**real(), key: 5})
                self.assertEqual((report['verdict'], rc), ('READY', 0))

    def test_an_unclassified_counter_fails_closed(self):
        real = command.access_switch_counts
        report, rc = run(patched=lambda: {**real(), 'dummy_counter': 3})
        self.assertEqual((rc, report['verdict']), (1, 'NOT READY'))
        self.assertEqual(report['unclassified_counters'], ['dummy_counter'])
        self.assertEqual(report['blockers_nonzero'], {'unclassified_counters': 1})

    def test_a_missing_counter_fails_closed(self):
        real = command.access_switch_counts

        def without_one():
            data = real()
            data.pop('teacher_assignments_active')
            return data

        report, rc = run(patched=without_one)
        self.assertEqual((rc, report['verdict']), (1, 'NOT READY'))
        self.assertEqual(report['missing_counters'], ['teacher_assignments_active'])

    def test_an_invalid_counter_value_fails_closed(self):
        real = command.access_switch_counts
        for bad in (None, True, -1, 1.0, '2', [1], {}):
            with self.subTest(bad=repr(bad)):
                report, rc = run(patched=lambda bad=bad: {**real(), 'students': bad})
                self.assertEqual((rc, report['verdict']), (1, 'NOT READY'))
                self.assertEqual(report['invalid_counters'], ['students'])

    def test_a_4c_key_produced_by_the_readiness_counters_fails_closed_instead_of_being_overwritten(self):
        from schools import multischool_checks
        real = multischool_checks.readiness_counts
        with mock.patch.object(multischool_checks, 'readiness_counts', lambda: {**real(), 'students': 7}):
            report, rc = run('--multi-school')
        self.assertEqual(rc, 1)
        self.assertIn('students', report['unclassified_counters'])

    def test_the_two_schemas_are_disjoint(self):
        from schools import multischool_checks
        ours = set(command.PROBLEM_KEYS) | set(command.INFO_KEYS)
        theirs = set(multischool_checks.READINESS_PROBLEM_KEYS) | set(multischool_checks.READINESS_INFO_KEYS)
        self.assertEqual(ours & theirs, set())
