"""C3c-1 unit tests for ``students/class_resolution.py`` (pure class-resolution decisions).

No view, no import endpoint, no pandas requirement in the helper. Most tests are database-free
(SimpleTestCase); a few use isolated Django test fixtures to prove the helper never writes and never
touches student links. Invisible characters are built with chr(). All data is synthetic.
Traceability: REQ: P2-REQ-18 (class text is not authoritative; never auto-create), P2-REQ-19 (fail closed).
Run with:  python manage.py test students.test_class_resolution
"""
import copy
import importlib.util
import inspect
import itertools
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from schools.models import School, SchoolClass

from . import class_resolution as cr
from .class_links import normalize_title
from .class_resolution import (
    AMBIGUOUS, CLASS_BLANK, GRADE_CONFLICT, INACTIVE_CLASS, NO_ACTIVE_CLASS, NO_UNIQUE_SCHOOL, RESOLVED,
    ClassCandidate, Resolution, apply_grade_guard, class_text, has_grade_conflict, resolve_class, valid_grades,
)
from .models import Student

ZWNJ = chr(0x200C)
NBSP = chr(0x00A0)
PERSIAN_9 = '۹'    # U+06F9 EXTENDED ARABIC-INDIC DIGIT NINE
ARABIC_9 = '٩'     # U+0669 ARABIC-INDIC DIGIT NINE

HAS_PANDAS = importlib.util.find_spec('pandas') is not None


def cand(pk, title, *, active=True, school=1, year=''):
    return ClassCandidate(pk=pk, title=title, is_active=active, school_id=school, academic_year=year)


def one_school(value, candidates):
    return resolve_class(value, school_ids=[1], candidates=candidates)


class ClassTextTests(SimpleTestCase):
    def test_none_empty_and_whitespace_only_are_blank(self):
        """Required case 1."""
        for value in (None, '', '   ', '\t\n ', NBSP, ' ' + NBSP + ' '):
            self.assertEqual(class_text(value), '', repr(value))
            self.assertEqual(resolve_class(value, school_ids=[1], candidates=[cand(1, '9-A')]).status,
                             CLASS_BLANK, repr(value))

    def test_missing_value_sentinels_are_blank(self):
        """Required case 2 (the sentinels)."""
        sentinels = [float('nan'), Decimal('NaN')]
        if HAS_PANDAS:
            import numpy
            import pandas
            sentinels += [numpy.nan, numpy.float32('nan'), numpy.float64('nan'), pandas.NA, pandas.NaT]
        for value in sentinels:
            self.assertEqual(class_text(value), '', repr(value))
            self.assertEqual(one_school(value, [cand(1, 'nan')]).status, CLASS_BLANK, repr(value))

    def test_the_text_nan_is_a_real_title_not_a_missing_value(self):
        """Required case 2 (the distinction): only a genuine sentinel is blank; the text is a title."""
        self.assertEqual(class_text('nan'), 'nan')
        self.assertEqual(class_text(' NaN '), 'NaN')
        self.assertEqual(one_school('nan', []).status, NO_ACTIVE_CLASS)        # reported, not silently blank
        found = one_school('nan', [cand(5, 'nan')])
        self.assertEqual((found.status, found.candidate.pk), (RESOLVED, 5))   # matches a class literally titled 'nan'

    def test_blank_is_blank_even_when_the_school_precondition_fails(self):
        for school_ids in ([], [1, 2]):
            self.assertEqual(resolve_class(None, school_ids=school_ids, candidates=[]).status, CLASS_BLANK)

    def test_whole_numbers_become_integer_text(self):
        """Required case 3."""
        self.assertEqual(class_text(9), '9')
        self.assertEqual(class_text(9.0), '9')
        self.assertEqual(class_text(10.0), '10')
        self.assertEqual(class_text(0), '0')
        self.assertEqual(one_school(9.0, [cand(7, '9')]).candidate.pk, 7)
        self.assertEqual(one_school(9, [cand(7, '9')]).candidate.pk, 7)
        if HAS_PANDAS:
            import numpy
            self.assertEqual(class_text(numpy.int64(9)), '9')
            self.assertEqual(class_text(numpy.float64(9.0)), '9')

    def test_non_integral_numbers_are_not_rounded(self):
        """Required case 4."""
        self.assertEqual(class_text(9.5), '9.5')
        self.assertEqual(class_text(9.4999), '9.4999')
        self.assertEqual(class_text(-0.5), '-0.5')
        self.assertEqual(one_school(9.5, [cand(1, '9')]).status, NO_ACTIVE_CLASS)
        self.assertEqual(one_school(9.5, [cand(1, '10')]).status, NO_ACTIVE_CLASS)

    def test_booleans_are_text_not_numbers(self):
        self.assertEqual(class_text(True), 'True')
        self.assertEqual(class_text(False), 'False')

    def test_persian_and_arabic_digits_stay_distinct_from_western(self):
        """Required case 5."""
        self.assertEqual(len({class_text(PERSIAN_9), class_text(ARABIC_9), class_text('9')}), 3)
        self.assertEqual(class_text(PERSIAN_9), PERSIAN_9)
        self.assertEqual(one_school(PERSIAN_9, [cand(1, '9')]).status, NO_ACTIVE_CLASS)
        self.assertEqual(one_school('9', [cand(1, PERSIAN_9)]).status, NO_ACTIVE_CLASS)
        self.assertEqual(one_school(PERSIAN_9, [cand(1, PERSIAN_9)]).candidate.pk, 1)
        self.assertEqual(one_school(ARABIC_9, [cand(1, PERSIAN_9)]).status, NO_ACTIVE_CLASS)

    def test_letters_zwnj_case_and_punctuation_are_not_normalized(self):
        pairs = [('ي', 'ی'), ('ك', 'ک'), ('A', 'a'), ('10-A', '10_A'), ('10-A', '10 A'),
                 ('می' + ZWNJ + 'شود', 'میشود')]
        for incoming, stored in pairs:
            self.assertEqual(one_school(incoming, [cand(1, stored)]).status, NO_ACTIVE_CLASS, (incoming, stored))
            self.assertEqual(one_school(incoming, [cand(1, incoming)]).status, RESOLVED, incoming)

    def test_whitespace_normalization_is_exactly_normalize_title(self):
        """Required case 6."""
        samples = ['  9-A  ', '9   A', '9\tA', '9\nA', NBSP + '9-A' + NBSP, '　x　', 'a  b   c']
        for text in samples:
            self.assertEqual(class_text(text), normalize_title(text), repr(text))
        self.assertEqual(one_school('  9-A  ', [cand(1, '9-A')]).candidate.pk, 1)
        self.assertEqual(one_school('9-A', [cand(1, ' 9-A ')]).candidate.pk, 1)   # stored form padded
        self.assertEqual(one_school('9   A', [cand(1, '9 A')]).candidate.pk, 1)


class SchoolPreconditionTests(SimpleTestCase):
    def test_zero_or_several_schools_resolve_nothing(self):
        """Required case 7."""
        classes = [cand(1, '9-A')]
        for school_ids in ([], [1, 2], (1, 2, 3)):
            result = resolve_class('9-A', school_ids=school_ids, candidates=classes)
            self.assertEqual((result.status, result.candidate, result.title), (NO_UNIQUE_SCHOOL, None, '9-A'))

    def test_school_ids_may_be_any_iterable(self):
        self.assertEqual(resolve_class('9-A', school_ids=iter([1]), candidates=[cand(1, '9-A')]).status, RESOLVED)
        self.assertEqual(resolve_class('9-A', school_ids={1}, candidates=[cand(1, '9-A')]).status, RESOLVED)


class MatchingTests(SimpleTestCase):
    def test_one_active_class_resolves_and_identifies_the_candidate(self):
        """Required case 8."""
        wanted = cand(11, '9-A', year='1404')
        result = one_school(' 9-A ', [cand(10, '9-B'), wanted, cand(12, '10-A')])
        self.assertEqual(result.status, RESOLVED)
        self.assertTrue(result.resolved)
        self.assertIs(result.candidate, wanted)
        self.assertEqual((result.candidate.pk, result.candidate.academic_year, result.title), (11, '1404', '9-A'))

    def test_a_class_of_another_school_never_resolves(self):
        """Required case 9."""
        self.assertEqual(one_school('9-A', [cand(1, '9-A', school=2)]).status, NO_ACTIVE_CLASS)
        # another school's ACTIVE class must not rescue an inactive class of the unique school
        mixed = [cand(1, '9-A', school=2), cand(2, '9-A', active=False, school=1)]
        result = one_school('9-A', mixed)
        self.assertEqual((result.status, result.candidate), (INACTIVE_CLASS, None))

    def test_inactive_class_is_reported_and_never_resolved(self):
        """Required case 10 (the DB-level 'never reactivated' proof is in NoSideEffectTests)."""
        result = one_school('9-A', [cand(1, '9-A', active=False)])
        self.assertEqual((result.status, result.candidate, result.title), (INACTIVE_CLASS, None, '9-A'))
        # inactive classes of other years or spellings count as 'inactive', not as 'missing'
        self.assertEqual(one_school('9-A', [cand(1, ' 9-A ', active=False, year='1403')]).status, INACTIVE_CLASS)

    def test_no_class_at_all_is_no_active_class(self):
        """Required case 11."""
        self.assertEqual(one_school('9-A', []).status, NO_ACTIVE_CLASS)
        self.assertEqual(one_school('9-A', [cand(1, '9-B'), cand(2, '10-A', active=False)]).status, NO_ACTIVE_CLASS)

    def test_duplicate_normalized_active_titles_are_ambiguous(self):
        """Required case 12."""
        result = one_school('9-A', [cand(1, '9-A'), cand(2, ' 9-A ', year='1404')])
        self.assertEqual((result.status, result.candidate), (AMBIGUOUS, None))

    def test_one_active_plus_inactive_duplicates_resolves_to_the_active_one(self):
        result = one_school('9-A', [cand(1, '9-A', active=False), cand(2, '9-A'), cand(3, '9-A', active=False)])
        self.assertEqual((result.status, result.candidate.pk), (RESOLVED, 2))

    def test_academic_years_are_handled_conservatively(self):
        """Required case 13: title-only matching, never a silent year choice."""
        # two active classes, different years -> never auto-selected
        self.assertEqual(one_school('9-A', [cand(1, '9-A', year='1403'), cand(2, '9-A', year='1404')]).status,
                         AMBIGUOUS)
        # a single active class resolves whatever its year, and exposes the year to the caller
        only = one_school('9-A', [cand(2, '9-A', year='1404')])
        self.assertEqual((only.status, only.candidate.academic_year), (RESOLVED, '1404'))
        # an inactive class of an older year does not compete with the one active class
        self.assertEqual(one_school('9-A', [cand(1, '9-A', active=False, year='1403'),
                                            cand(2, '9-A', year='1404')]).candidate.pk, 2)
        # only an inactive class of another year -> inactive, not resolved
        self.assertEqual(one_school('9-A', [cand(1, '9-A', active=False, year='1403')]).status, INACTIVE_CLASS)

    def test_no_academic_year_is_ever_preferred(self):
        """Review B: not the empty year, not the newest, not the current one; any order gives AMBIGUOUS."""
        empty_vs_year = [cand(1, '9-A', year=''), cand(2, '9-A', year='1404')]
        for ordering in itertools.permutations(empty_vs_year):
            result = one_school('9-A', list(ordering))
            self.assertEqual((result.status, result.candidate), (AMBIGUOUS, None))
        three_years = [cand(1, '9-A', year='1402'), cand(2, '9-A', year='1403'), cand(3, '9-A', year='1404')]
        for ordering in itertools.permutations(three_years):
            self.assertEqual(one_school('9-A', list(ordering)).status, AMBIGUOUS)

    def test_single_active_class_in_a_non_empty_year_resolves_and_reports_its_year(self):
        for year in ('1404', '2025-2026', ' 1404 '):
            result = one_school('9-A', [cand(9, '9-A', year=year)])
            self.assertEqual((result.status, result.candidate.pk, result.candidate.academic_year), (RESOLVED, 9, year))

    def test_resolution_is_independent_of_candidate_order(self):
        classes = [cand(1, '9-A', active=False), cand(2, '9-A'), cand(3, '9-B'), cand(4, '9-A', school=2)]
        outcomes = {one_school('9-A', list(p)).candidate.pk for p in itertools.permutations(classes)}
        self.assertEqual(outcomes, {2})


class GradeGuardTests(SimpleTestCase):
    def resolved(self, pk, title='9-A'):
        return one_school(title, [cand(pk, title)])

    def test_same_grade_members_and_incoming_rows_are_allowed(self):
        """Required case 14."""
        entries = [(self.resolved(1), 9), (self.resolved(1), 9)]
        out = apply_grade_guard(entries, {1: [9, 9]})
        self.assertEqual([r.status for r in out], [RESOLVED, RESOLVED])
        self.assertEqual([r.candidate.pk for r in out], [1, 1])
        self.assertFalse(has_grade_conflict([9], [9]))
        self.assertFalse(has_grade_conflict([], [9, 9]))
        self.assertFalse(has_grade_conflict([], []))

    def test_existing_grade_9_with_incoming_grade_10_conflicts(self):
        """Required case 15."""
        out = apply_grade_guard([(self.resolved(1), 10)], {1: [9]})
        self.assertEqual((out[0].status, out[0].candidate, out[0].title), (GRADE_CONFLICT, None, '9-A'))
        self.assertTrue(has_grade_conflict([9], [10]))

    def test_existing_members_with_two_grades_conflict_for_any_incoming_row(self):
        """Required case 16."""
        self.assertTrue(has_grade_conflict([7, 8], []))
        out = apply_grade_guard([(self.resolved(1), 7)], {1: [7, 8]})
        self.assertEqual(out[0].status, GRADE_CONFLICT)

    def test_invalid_and_missing_grades_are_ignored_and_not_rewritten(self):
        """Required case 17."""
        incoming = [None, 13, 6, 0, 'x', '', 9.5, True, 9]
        self.assertEqual(valid_grades(incoming), frozenset({9}))
        self.assertFalse(has_grade_conflict([9, 99, None], incoming))
        snapshot = list(incoming)
        entries = [(self.resolved(1), g) for g in incoming]
        out = apply_grade_guard(entries, {1: [9]})
        self.assertEqual([r.status for r in out], [RESOLVED] * len(incoming))  # nothing conflicts or is dropped
        self.assertEqual(incoming, snapshot)                                    # input untouched
        # an invalid grade must not hide a real conflict, and a whole float counts as its integer
        self.assertTrue(has_grade_conflict([9], [10, None, 'x']))
        self.assertTrue(has_grade_conflict([10], [9.0]))
        self.assertEqual(valid_grades([True, False, 9.5, '9']), frozenset())

    def test_mixed_incoming_batch_is_detected_regardless_of_row_order(self):
        """Required case 18: every permutation gives the same answer for every row."""
        class_a, class_b = self.resolved(1, '9-A'), self.resolved(2, '9-B')
        entries = [(class_a, 9), (class_a, 9), (class_a, 10), (class_a, None), (class_b, 8), (class_b, 8)]
        expected = [GRADE_CONFLICT] * 4 + [RESOLVED, RESOLVED]
        for order in itertools.permutations(range(len(entries))):
            out = apply_grade_guard([entries[i] for i in order], {})
            by_original = {original: out[position].status for position, original in enumerate(order)}
            self.assertEqual([by_original[i] for i in range(len(entries))], expected, order)

    def test_the_first_row_is_also_rejected_when_a_later_row_conflicts(self):
        """No sequential 'link early rows first' behavior: row 0 shares the class with the conflicting row."""
        entries = [(self.resolved(1), 9), (self.resolved(1), 9), (self.resolved(1), 10)]
        self.assertEqual([r.status for r in apply_grade_guard(entries, {})], [GRADE_CONFLICT] * 3)

    def test_unresolved_rows_pass_through_unchanged_and_other_classes_are_independent(self):
        blank = Resolution(CLASS_BLANK)
        missing = one_school('zzz', [])
        ok_other = self.resolved(3, '10-A')
        entries = [(blank, None), (missing, 9), (self.resolved(1), 9), (self.resolved(1), 10), (ok_other, 10)]
        out = apply_grade_guard(entries, {})
        self.assertIs(out[0], blank)
        self.assertIs(out[1], missing)
        self.assertEqual([r.status for r in out[2:]], [GRADE_CONFLICT, GRADE_CONFLICT, RESOLVED])
        self.assertIs(out[4], ok_other)
        self.assertEqual(len(out), len(entries))

    def test_effective_grade_of_a_changed_linked_member_is_honoured(self):
        """Review C: the caller passes EFFECTIVE member grades (a linked student whose grade the import
        changes contributes the new grade). The helper stays agnostic of student identity."""
        incoming_nine = [(self.resolved(1), 9)]
        self.assertEqual(apply_grade_guard(incoming_nine, {1: [9]})[0].status, RESOLVED)      # member unchanged
        self.assertEqual(apply_grade_guard(incoming_nine, {1: [10]})[0].status, GRADE_CONFLICT)  # member became 10
        self.assertEqual(apply_grade_guard([(self.resolved(1), 10)], {1: [10]})[0].status, RESOLVED)

    def test_existing_grades_are_per_class(self):
        out = apply_grade_guard([(self.resolved(1), 9), (self.resolved(2, '10-A'), 9)], {1: [9], 2: [10]})
        self.assertEqual([r.status for r in out], [RESOLVED, GRADE_CONFLICT])

    def test_any_iterable_is_accepted_and_is_consumed_safely(self):
        entries = iter([(self.resolved(1), 9), (self.resolved(1), 10)])
        out = apply_grade_guard(entries, {1: iter([9, 9]), 2: (x for x in [7, 8])})
        self.assertEqual([r.status for r in out], [GRADE_CONFLICT, GRADE_CONFLICT])
        self.assertEqual([r.status for r in apply_grade_guard([(self.resolved(1), 9)], {1: (9,)})], [RESOLVED])
        self.assertEqual([r.status for r in apply_grade_guard([(self.resolved(1), 9)], {1: {9, None}})], [RESOLVED])

    def test_inputs_are_never_mutated(self):
        first, second = self.resolved(1), self.resolved(1)
        entries = [(first, 9), (second, 10), (Resolution(CLASS_BLANK), None)]
        existing = {1: [9, 'x', None], 2: {7}}
        entries_before, existing_before = list(entries), copy.deepcopy(existing)
        out = apply_grade_guard(entries, existing)
        self.assertEqual(entries, entries_before)
        self.assertEqual(existing, existing_before)
        self.assertEqual((first.status, second.status), (RESOLVED, RESOLVED))   # originals keep their status
        self.assertEqual([r.status for r in out], [GRADE_CONFLICT, GRADE_CONFLICT, CLASS_BLANK])
        self.assertIsNot(out[0], first)                                          # a new Resolution, not a mutation

    def test_reversing_the_batch_gives_equivalent_statuses(self):
        a, b = self.resolved(1), self.resolved(2, '9-B')
        entries = [(a, 9), (b, 8), (a, 10), (b, 8), (Resolution(CLASS_BLANK), None), (one_school('?', []), 9)]
        forward = [r.status for r in apply_grade_guard(entries, {})]
        backward = [r.status for r in apply_grade_guard(list(reversed(entries)), {})]
        self.assertEqual(forward, list(reversed(backward)))

    def test_numeric_grade_types_are_handled_consistently(self):
        self.assertEqual(valid_grades([9, 9.0]), frozenset({9}))
        self.assertEqual(valid_grades([float('nan'), float('inf'), float('-inf'), 9.0000001]), frozenset())
        self.assertEqual(valid_grades([Decimal('9'), '9', b'9']), frozenset())   # not int/float: never converted
        if HAS_PANDAS:
            import numpy
            self.assertEqual(valid_grades([numpy.int64(9), numpy.float64(10.0), numpy.nan]), frozenset({9, 10}))
            self.assertTrue(has_grade_conflict([numpy.int32(9)], [numpy.float32(10.0)]))

    def test_class_without_incoming_rows_is_not_evaluated(self):
        # a class whose members already disagree is only relevant when something would be linked to it
        out = apply_grade_guard([(self.resolved(3, '10-A'), 10)], {1: [7, 8], 3: [10]})
        self.assertEqual([r.status for r in out], [RESOLVED])

    def test_empty_batch_and_missing_existing_entry(self):
        self.assertEqual(apply_grade_guard([], {}), [])
        self.assertEqual(apply_grade_guard([(self.resolved(1), 9)], {})[0].status, RESOLVED)


class ContractTests(SimpleTestCase):
    def test_status_values_and_unmatched_set_are_stable(self):
        self.assertEqual(
            [RESOLVED, CLASS_BLANK, NO_UNIQUE_SCHOOL, NO_ACTIVE_CLASS, INACTIVE_CLASS, AMBIGUOUS, GRADE_CONFLICT],
            ['resolved', 'class_blank', 'no_unique_school', 'no_active_class', 'inactive_class', 'ambiguous',
             'grade_conflict'])
        self.assertEqual(cr.UNMATCHED_STATUSES,
                         {'no_unique_school', 'no_active_class', 'inactive_class', 'ambiguous', 'grade_conflict'})
        self.assertNotIn(RESOLVED, cr.UNMATCHED_STATUSES)
        self.assertNotIn(CLASS_BLANK, cr.UNMATCHED_STATUSES)

    def test_valid_grades_come_from_the_student_model(self):
        self.assertEqual(cr.supported_grades(), frozenset({7, 8, 9, 10, 11, 12}))
        self.assertEqual(cr.supported_grades(), frozenset(v for v, _ in Student.GRADE_CHOICES))
        self.assertFalse(hasattr(cr, 'VALID_GRADES'))  # no second copy of the range at module level

    def test_module_imports_and_resolves_titles_without_django_configured(self):
        """Review A: students.models needs the app registry, so the helper must not import it at import time."""
        code = (
            "import sys\n"
            "import students.class_resolution as m\n"
            "assert 'students.models' not in sys.modules, 'models imported at import time'\n"
            "r = m.resolve_class(' 9-A ', school_ids=[1], candidates=[m.ClassCandidate(5, '9-A', True, 1)])\n"
            "assert (r.status, r.candidate.pk) == ('resolved', 5), r\n"
            "assert m.class_text(9.0) == '9' and m.class_text(float('nan')) == ''\n"
            "print('OK')\n"
        )
        env = {k: v for k, v in os.environ.items() if k != 'DJANGO_SETTINGS_MODULE'}
        done = subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, %r); ' % str(
            settings.BASE_DIR) + code], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, 'OK'), done.stderr)

    def test_the_helper_never_reads_a_clock(self):
        """Review B: no current-year inference. Checked on the AST (imports and calls), not on prose."""
        import ast
        tree = ast.parse(inspect.getsource(cr))
        imported, called = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
            elif isinstance(node, ast.Call):
                func = node.func
                called.add(getattr(func, 'attr', getattr(func, 'id', '')))
        self.assertFalse({'datetime', 'time', 'calendar', 'django.utils.timezone', 'django.utils'} & imported,
                         imported)
        self.assertFalse({'now', 'today', 'localdate', 'localtime', 'utcnow', 'time'} & called, called)

    def test_results_and_candidates_are_immutable(self):
        result = one_school('9-A', [cand(1, '9-A')])
        with self.assertRaises(FrozenInstanceError):
            result.status = GRADE_CONFLICT
        with self.assertRaises(FrozenInstanceError):
            result.candidate.is_active = False

    def test_only_resolved_results_carry_a_candidate(self):
        for result in (one_school('', []), resolve_class('x', school_ids=[], candidates=[]),
                       one_school('x', []), one_school('x', [cand(1, 'x', active=False)]),
                       one_school('x', [cand(1, 'x'), cand(2, 'x')])):
            self.assertIsNone(result.candidate)
            self.assertFalse(result.resolved)

    def test_public_functions_take_no_student_or_request_objects(self):
        for function in (resolve_class, apply_grade_guard, has_grade_conflict, valid_grades, class_text):
            names = set(inspect.signature(function).parameters)
            self.assertFalse({'student', 'students', 'request', 'user', 'queryset', 'file', 'df'} & names,
                             (function.__name__, names))

    def test_deterministic_repeat_calls(self):
        classes = [cand(1, '9-A'), cand(2, '9-A', active=False)]
        self.assertEqual(one_school(' 9-A', classes), one_school(' 9-A', classes))


class NoSideEffectTests(TestCase):
    """Real model rows: running every function must change nothing and never touch student links."""

    def snapshot(self):
        return (
            list(School.objects.order_by('pk').values_list('pk', 'name', 'code')),
            list(SchoolClass.objects.order_by('pk').values_list('pk', 'school_id', 'title', 'academic_year',
                                                                'is_active', 'updated_at')),
            list(Student.objects.order_by('pk').values_list('pk', 'class_name', 'grade', 'school_id',
                                                            'school_class_id', 'updated_at')),
        )

    def test_helper_never_creates_updates_activates_or_deletes_and_leaves_student_links_alone(self):
        """Required cases 19 and 20."""
        School.objects.all().delete()
        school = School.objects.create(name='S', code='res-s')
        active = SchoolClass.objects.create(school=school, title='9-A')
        closed = SchoolClass.objects.create(school=school, title='9-Z', is_active=False)
        linked = Student.objects.create(first_name='L', last_name='K', national_id='5000000001', grade=9,
                                        phone_number='1', school_class=active)
        Student.objects.create(first_name='U', last_name='K', national_id='5000000002', grade=10,
                               phone_number='1', class_name='free text', school=school)
        before = self.snapshot()

        candidates = [ClassCandidate.from_model(c) for c in SchoolClass.objects.all()]
        school_ids = list(School.objects.values_list('pk', flat=True))
        existing = {active.pk: list(active.students.values_list('grade', flat=True))}
        rows = [(' 9-A ', 10), ('9-Z', 9), ('missing', 9), (None, None), (9.0, 9), ('9-A', 9)]
        first = [resolve_class(v, school_ids=school_ids, candidates=candidates) for v, _g in rows]
        guarded = apply_grade_guard([(r, g) for r, (_v, g) in zip(first, rows)], existing)

        self.assertEqual([r.status for r in first],
                         [RESOLVED, INACTIVE_CLASS, NO_ACTIVE_CLASS, CLASS_BLANK, NO_ACTIVE_CLASS, RESOLVED])
        self.assertEqual([r.status for r in guarded],
                         [GRADE_CONFLICT, INACTIVE_CLASS, NO_ACTIVE_CLASS, CLASS_BLANK, NO_ACTIVE_CLASS,
                          GRADE_CONFLICT])
        self.assertEqual(self.snapshot(), before)                       # no row created, changed or deleted
        closed.refresh_from_db()
        self.assertFalse(closed.is_active)                              # inactive class was not reactivated
        linked.refresh_from_db()
        self.assertEqual(linked.school_class_id, active.pk)             # existing link untouched
        self.assertEqual(Student.objects.filter(school_class__isnull=True).count(), 1)

    def test_from_model_copies_the_facts_without_querying(self):
        school = School.objects.create(name='S2', code='res-s2')
        klass = SchoolClass.objects.create(school=school, title=' 10-B ', academic_year='1404')
        with self.assertNumQueries(0):
            candidate = ClassCandidate.from_model(klass)
        self.assertEqual(candidate, ClassCandidate(pk=klass.pk, title=' 10-B ', is_active=True,
                                                   school_id=school.pk, academic_year='1404'))
