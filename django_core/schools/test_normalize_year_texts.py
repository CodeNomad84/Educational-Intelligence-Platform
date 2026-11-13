"""normalize_year_texts: dry-run default, canonical-only, never guesses, revertible through its log."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import GradeLeadAssignment, School, SchoolClass

User = get_user_model()


class NormalizeTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = str(Path(self.tmp.name) / 'undo.json')
        self.school = School.objects.create(name='A', code='a')
        mk = lambda title, year: SchoolClass.objects.create(school=self.school, title=title, academic_year=year)  # noqa: E731
        self.c = {
            'variant': mk('7-A', '۱۴۰۴/۱۴۰۵'), 'short': mk('7-B', '1404'), 'canon': mk('8-A', '1404-1405'),
            'blank': mk('8-B', ''), 'bad': mk('9-A', '404'), 'gregorian': mk('9-B', '2025'),
            'other_year': mk('10-A', '1403/1404'),
        }
        user = User.objects.create_user('lead')
        self.lead = GradeLeadAssignment.objects.create(user=user, school=self.school, grade=7, academic_year='1404')
        self.lead2 = GradeLeadAssignment.objects.create(user=user, school=self.school, grade=8, academic_year='1404-1405')

    def run_cmd(self, *args):
        out = StringIO()
        if '--apply' in args and '--revert-from' not in args and '--school-code' not in args:
            args = (*args, '--school-code', 'a')                         # S4(c): a write needs the school once several exist
        call_command('normalize_year_texts', '--json', *args, stdout=out)
        return json.loads(out.getvalue())

    def values(self):
        return (sorted(SchoolClass.objects.values_list('pk', 'academic_year')),
                sorted(GradeLeadAssignment.objects.values_list('pk', 'academic_year')))

    def test_dry_run_is_default_and_writes_nothing(self):
        before = self.values()
        report = self.run_cmd()
        self.assertEqual(report['mode'], 'DRY-RUN')
        self.assertEqual(report['SchoolClass']['to_convert'], 3)       # variant, short, other_year
        self.assertEqual(report['SchoolClass']['already_canonical'], 1)
        self.assertEqual(report['SchoolClass']['blank_left_alone'], 1)
        self.assertEqual(report['SchoolClass']['unresolved_left_alone'], 2)
        self.assertEqual(report['SchoolClass_unresolved_values'], {'404': 1, '2025': 1})
        self.assertEqual(report['GradeLeadAssignment']['to_convert'], 1)
        self.assertEqual(self.values(), before)

    def test_apply_needs_a_log_and_converts_only_the_unambiguous(self):
        with self.assertRaises(CommandError):
            self.run_cmd('--apply')
        report = self.run_cmd('--apply', '--log', self.log)
        self.assertEqual(report['SchoolClass']['converted'], 3)
        self.assertEqual(SchoolClass.objects.get(pk=self.c['variant'].pk).academic_year, '1404-1405')
        self.assertEqual(SchoolClass.objects.get(pk=self.c['short'].pk).academic_year, '1404-1405')
        self.assertEqual(SchoolClass.objects.get(pk=self.c['other_year'].pk).academic_year, '1403-1404')
        for key, expected in (('blank', ''), ('bad', '404'), ('gregorian', '2025')):
            self.assertEqual(SchoolClass.objects.get(pk=self.c[key].pk).academic_year, expected)  # never guessed
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.academic_year, '1404-1405')
        log = json.load(open(self.log, encoding='utf-8'))
        self.assertEqual(len(log['changes']), 4)
        self.assertEqual({c['old'] for c in log['changes']}, {'۱۴۰۴/۱۴۰۵', '1404', '1403/1404'})

    def test_idempotent(self):
        self.run_cmd('--apply', '--log', self.log)
        state = self.values()
        again = self.run_cmd('--apply', '--log', self.log)
        self.assertEqual(again['SchoolClass'].get('converted', 0), 0)
        self.assertEqual(self.values(), state)

    def test_revert_restores_exactly_and_skips_later_edits(self):
        before = self.values()
        self.run_cmd('--apply', '--log', self.log)
        SchoolClass.objects.filter(pk=self.c['short'].pk).update(academic_year='1404-1405 edited')  # edited since
        preview = self.run_cmd('--revert-from', self.log)
        self.assertEqual((preview['to_restore'], preview['skipped_changed_since']), (3, 1))
        self.run_cmd('--revert-from', self.log, '--apply')
        self.assertEqual(SchoolClass.objects.get(pk=self.c['short'].pk).academic_year, '1404-1405 edited')
        SchoolClass.objects.filter(pk=self.c['short'].pk).update(academic_year='1404')
        self.assertEqual(self.values(), before)

    def test_collisions_are_skipped_not_forced(self):
        a = SchoolClass.objects.create(school=self.school, title='11-A', academic_year='1404')
        b = SchoolClass.objects.create(school=self.school, title='11-A', academic_year='۱۴۰۴-۱۴۰۵')  # same title, same year
        c = SchoolClass.objects.create(school=self.school, title='11-B', academic_year='1404')
        SchoolClass.objects.create(school=self.school, title='11-B', academic_year='1404-1405')       # canonical twin exists
        report = self.run_cmd('--apply', '--log', self.log)
        self.assertEqual(report['SchoolClass']['skipped_would_collide'], 3)
        for row, expected in ((a, '1404'), (b, '۱۴۰۴-۱۴۰۵'), (c, '1404')):
            row.refresh_from_db()
            self.assertEqual(row.academic_year, expected)

    def test_normalising_makes_legacy_string_matching_agree(self):
        """The reason the command exists: a lead spelled '1404' now equals the class text."""
        self.run_cmd('--apply', '--log', self.log)
        lead_years = set(GradeLeadAssignment.objects.values_list('academic_year', flat=True))
        class_years = set(SchoolClass.objects.filter(title__in=['7-A', '7-B']).values_list('academic_year', flat=True))
        self.assertEqual(lead_years, {'1404-1405'})
        self.assertEqual(class_years, {'1404-1405'})
