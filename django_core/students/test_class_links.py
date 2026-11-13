"""C3a tests: pure class-link classification, the read-only report command and the default-school setting.

All data is synthetic. Traceability: REQ: P2-REQ-18 (class_name is a mirror; never auto-create),
P2-REQ-19 (migrated data never grants access; near-duplicates are reported, not merged).
Run with:  python manage.py test students.test_class_links
"""
import io
import json
import os

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from schools.models import School, SchoolClass

from .class_links import (
    BLANK, LINKABLE, MAX_TITLE_LENGTH, MULTI_GRADE, TOO_LONG,
    near_duplicate_key, normalize_title, plan_class_links,
)
from .models import Student

# Spellings used below (escapes keep the differences visible)
PERSIAN_10A = '۱۰-الف'    # ۱۰-الف
ARABIC_10A = '١٠-الف'     # ١٠-الف (Arabic-Indic digits)
ASCII_10A = '10-الف'                # 10-الف


class NormalizeTitleTests(SimpleTestCase):
    def test_trims_and_collapses_whitespace_only(self):
        """REQ: P2-REQ-18"""
        self.assertEqual(normalize_title('  ' + PERSIAN_10A + '  '), PERSIAN_10A)
        self.assertEqual(normalize_title('a   b'), 'a b')
        self.assertEqual(normalize_title('a\t\n b'), 'a b')
        self.assertEqual(normalize_title('a b'), 'a b')          # NBSP is whitespace
        self.assertEqual(normalize_title('a　b'), 'a b')          # ideographic space
        self.assertEqual(normalize_title(None), '')
        self.assertEqual(normalize_title('   '), '')

    def test_nothing_else_is_normalized(self):
        """REQ: P2-REQ-19: distinct spellings stay distinct identities."""
        pairs = [
            ('می‌شود', 'میشود'),  # ZWNJ kept
            ('ي', 'ی'),                                                         # Arabic vs Persian yeh
            ('ك', 'ک'),                                                         # Arabic vs Persian kaf
            (PERSIAN_10A, ASCII_10A), (PERSIAN_10A, ARABIC_10A),                          # digit scripts
            ('A-1', 'a-1'),                                                               # case
            ('10-A', '10_A'), ('10-A', '10 A'),                                           # punctuation / space
        ]
        for left, right in pairs:
            self.assertNotEqual(normalize_title(left), normalize_title(right), (left, right))

    def test_is_idempotent(self):
        once = normalize_title('  a \t b  ')
        self.assertEqual(normalize_title(once), once)


class PlanClassLinksTests(SimpleTestCase):
    def plan(self, *rows):
        return plan_class_links(list(rows))

    def test_blank_values_are_never_classes(self):
        """REQ: P2-REQ-18"""
        plan = self.plan(('', 9), ('   ', 9), (None, 10), (' ', 10), ('\t', 8))
        self.assertEqual((plan.blank_count, plan.total, plan.status), (5, 5, {}))
        for value in ('', '   ', None, ' '):
            self.assertEqual(plan.status_for(value), BLANK)

    def test_single_grade_title_is_linkable_and_padding_is_same_identity(self):
        plan = self.plan((PERSIAN_10A, 10), ('  ' + PERSIAN_10A + ' ', 10), (PERSIAN_10A, 10))
        self.assertEqual(plan.status, {PERSIAN_10A: LINKABLE})
        self.assertEqual(plan.students[PERSIAN_10A], 3)
        self.assertEqual(plan.status_for(' ' + PERSIAN_10A), LINKABLE)

    def test_multi_grade_title_is_ambiguous_and_never_linkable(self):
        """Decision 1: a title seen with more than one grade is neither created nor linked."""
        bare = 'الف'  # الف
        plan = self.plan((bare, 9), (bare, 10), (bare, 9))
        self.assertEqual(plan.status[bare], MULTI_GRADE)
        self.assertEqual(plan.grades[bare], {9: 2, 10: 1})
        self.assertEqual(plan.titles(LINKABLE), [])
        self.assertEqual(plan.summary()['multi_grade_students'], 3)

    def test_padded_variants_across_grades_are_still_multi_grade(self):
        plan = self.plan(('X', 9), (' X ', 10))
        self.assertEqual(plan.status, {'X': MULTI_GRADE})

    def test_distinct_spellings_with_different_grades_are_distinct_linkable_identities(self):
        """Decision 2: never merged, so no false ambiguity and no over-grant."""
        plan = self.plan((PERSIAN_10A, 10), (ASCII_10A, 11))
        self.assertEqual(plan.status, {PERSIAN_10A: LINKABLE, ASCII_10A: LINKABLE})
        self.assertEqual(plan.near_duplicate_groups(), [sorted([PERSIAN_10A, ASCII_10A])])

    def test_length_boundary(self):
        ok, too_long = 'x' * MAX_TITLE_LENGTH, 'x' * (MAX_TITLE_LENGTH + 1)
        plan = self.plan((ok, 9), (too_long, 9), ('  ' + ok + '  ', 9))
        self.assertEqual(plan.status[ok], LINKABLE)
        self.assertEqual(plan.status[too_long], TOO_LONG)

    def test_too_long_takes_precedence_over_multi_grade(self):
        title = 'y' * (MAX_TITLE_LENGTH + 5)
        self.assertEqual(self.plan((title, 8), (title, 9)).status[title], TOO_LONG)

    def test_unknown_title_raises(self):
        with self.assertRaises(KeyError):
            self.plan(('A', 9)).status_for('B')

    def test_near_duplicate_groups_cover_digits_letters_invisibles_case_and_dashes(self):
        zwnj = 'می‌ترا'
        titles = [PERSIAN_10A, ARABIC_10A, ASCII_10A, '10 الف', '10_الف',
                  'يك', 'یک', zwnj, zwnj.replace('‌', ''), 'Room-1', 'room-1', 'solo']
        plan = self.plan(*[(t, 9) for t in titles])
        groups = plan.near_duplicate_groups()
        flat = {t for g in groups for t in g}
        self.assertEqual(len(groups), 4)
        self.assertNotIn('solo', flat)
        self.assertEqual(sorted(len(g) for g in groups), [2, 2, 2, 5])
        self.assertEqual(set(plan.status.values()), {LINKABLE})  # grouping never changes a decision

    def test_near_duplicate_key_is_analysis_only(self):
        self.assertEqual(near_duplicate_key(PERSIAN_10A), near_duplicate_key(ASCII_10A))
        self.assertNotEqual(normalize_title(PERSIAN_10A), normalize_title(ASCII_10A))

    def test_bare_titles_are_a_warning_only(self):
        bare = 'الف'
        plan = self.plan((bare, 9), (PERSIAN_10A, 10), ('Z', 8), ('Z', 9))
        self.assertEqual(plan.bare_titles(), [bare])   # Z is multi-grade, not linkable
        self.assertEqual(plan.status[bare], LINKABLE)  # the warning does not change the decision

    def test_summary_counts_students_and_titles(self):
        plan = self.plan((PERSIAN_10A, 10), (PERSIAN_10A, 10), ('M', 9), ('M', 10), ('t' * 60, 9), ('', 9))
        self.assertEqual(plan.summary(), {
            'students': 6, 'blank': 1, 'linkable_students': 2, 'multi_grade_students': 2,
            'too_long_students': 1, 'linkable_titles': 1, 'multi_grade_titles': 1, 'too_long_titles': 1,
            'near_duplicate_groups': 0, 'bare_titles': 0})

    def test_accepts_a_generator_and_empty_input(self):
        self.assertEqual(plan_class_links(iter(())).total, 0)
        self.assertEqual(plan_class_links((v, 9) for v in ('a', 'b')).total, 2)

    def test_input_order_does_not_matter(self):
        rows = [('A', 9), ('A', 10), ('B', 9), (' B', 9), ('', 9), ('C', 8)]
        forward, backward = plan_class_links(rows), plan_class_links(reversed(rows))
        self.assertEqual(forward.status, backward.status)
        self.assertEqual(forward.summary(), backward.summary())


class DefaultSchoolNameSettingTests(SimpleTestCase):
    def test_default_is_neutral_unless_configured(self):
        """Decision 3: neutral default; a deployment configures the real name explicitly."""
        self.assertEqual(settings.DEFAULT_SCHOOL_NAME, os.environ.get('DEFAULT_SCHOOL_NAME', 'Default School'))
        self.assertTrue(settings.DEFAULT_SCHOOL_NAME.strip())


class CheckClassLinksCommandTests(TestCase):
    """The command is a read-only rehearsal: it SELECTs and prints titles and counts only."""

    def student(self, n, class_name, grade, **extra):
        return Student.objects.create(first_name=f'Fn{n}', last_name=f'Ln{n}', national_id=f'80000{n:05d}',
                                      grade=grade, phone_number='0', class_name=class_name,
                                      **{'school': School.objects.order_by('pk').first(), **extra})

    def run_report(self, *args):
        out = io.StringIO()
        call_command('check_class_links', *args, stdout=out)
        return out.getvalue()

    def snapshot(self):
        return (list(Student.objects.order_by('pk').values_list('pk', 'class_name', 'grade', 'school_id',
                                                                'school_class_id')),
                School.objects.count(), SchoolClass.objects.count())

    def test_report_counts_and_ambiguity(self):
        """REQ: P2-REQ-18, P2-REQ-19"""
        bare = 'الف'
        self.student(1, PERSIAN_10A, 10)
        self.student(2, ' ' + PERSIAN_10A + ' ', 10)
        self.student(3, bare, 9)
        self.student(4, bare, 10)
        self.student(5, ASCII_10A, 10)
        self.student(6, '', 8)
        # An over-limit legacy name can only be stored where varchar(50) is not enforced (SQLite); PostgreSQL
        # cannot hold it, so it is not written there. The rule is asserted at the planner level for every backend.
        over_limit_stored = connection.vendor == 'sqlite'
        if over_limit_stored:
            self.student(7, 'z' * 80, 8)
        total = 7 if over_limit_stored else 6
        data = json.loads(self.run_report('--json'))
        self.assertEqual((data['students'], data['already_linked'], data['candidates']), (total, 0, total))
        self.assertEqual(data['candidate_outcome'], {
            'would_link': 3, 'blank_left_unlinked': 1, 'multi_grade_left_unlinked': 2,
            'too_long_left_unlinked': 1 if over_limit_stored else 0})
        self.assertEqual(plan_class_links([('z' * 80, 8)]).titles('too_long'), ['z' * 80])
        self.assertEqual(sorted(data['titles']['linkable']), sorted([PERSIAN_10A, ASCII_10A]))
        self.assertEqual(list(data['titles']['multi_grade']), [bare])
        self.assertEqual(data['near_duplicate_groups'], [sorted([PERSIAN_10A, ASCII_10A])])
        self.assertEqual(data['writes'], 'none')

    def test_title_used_by_a_linked_student_of_another_grade_is_ambiguous(self):
        """Conservative: ambiguity is judged on all students, candidates are the unlinked ones."""
        school = School.objects.create(name='S', code='s')
        klass = SchoolClass.objects.create(school=school, title='B-1')
        self.student(1, 'ignored', 9, school_class=klass)       # mirrored to 'B-1' by save()
        self.student(2, 'B-1', 10)                              # unlinked, other grade
        data = json.loads(self.run_report('--json'))
        self.assertEqual((data['already_linked'], data['candidates']), (1, 1))
        self.assertEqual(data['candidate_outcome']['multi_grade_left_unlinked'], 1)
        self.assertEqual(data['candidate_outcome']['would_link'], 0)

    def test_command_is_read_only_and_selects_only(self):
        """REQ: P2-REQ-19: no class is created, nothing is linked, no write statement is issued."""
        self.student(1, PERSIAN_10A, 10)
        self.student(2, '', 9)
        before = self.snapshot()
        with CaptureQueriesContext(connection) as ctx:
            self.run_report()
            self.run_report('--json')
        self.assertTrue(ctx.captured_queries)
        for query in ctx.captured_queries:
            self.assertTrue(query['sql'].lstrip().upper().startswith('SELECT'), query['sql'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(SchoolClass.objects.count(), 0)

    def test_output_has_titles_and_counts_but_no_personal_data(self):
        self.student(1, PERSIAN_10A, 10)
        text = self.run_report() + self.run_report('--json')
        self.assertIn('nothing was written', text)
        self.assertIn(PERSIAN_10A, text)
        for personal in ('Fn1', 'Ln1', '8000000001'):  # first name, last name, national id
            self.assertNotIn(personal, text)

    def test_runs_on_an_empty_database(self):
        data = json.loads(self.run_report('--json'))
        self.assertEqual((data['students'], data['candidates']), (0, 0))
        self.assertIn('CLASS LINK REPORT', self.run_report())
