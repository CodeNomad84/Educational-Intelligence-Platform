"""S4(c) (docs/changes/0019): maintenance commands that can touch several schools. (1) every management command is classified, so a
new command cannot slip in unreviewed; (2) the four commands that write across all schools require an explicit school (or
--all-schools) once more than one School exists, and behave as before with exactly one. Synthetic data only."""
import json
import os
import tempfile
from datetime import date
from io import StringIO

from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import TestCase

from missions.models import Period, WeightSet
from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass
from students.models import Enrollment, Student
from vocabulary.models import VocabularyTerm

NEEDS_SCHOOL = {'run_rules', 'seed_rules', 'seed_mission', 'seed_vocabulary', 'normalize_year_texts', 'backfill_enrollments'}
SINGLE_SCHOOL = {   # act on exactly one school, or refuse when it is ambiguous
    'set_school_module', 'seed_demo', 'rollover_academic_year', 'import_history', 'backfill_school_memberships',
    'backfill_student_school'}
PLATFORM_WIDE = {   # not school data (global groups/rubric), batch-logged platform repair, or creates its own synthetic school
    'setup_staff_roles', 'setup_platform_role', 'create_school', 'load_mission_rubric', 'check_school_memberships', 'seed_temporal_synthetic',
    'seed_temporal_realistic'}
READ_ONLY = {
    'check_academic_years', 'check_assignment_subjects', 'check_access_switch_ready', 'check_class_links', 'check_enrollment_backfill',
    'check_student_school_ready', 'compare_access_parity', 'demo_check'}
CLASSES = (NEEDS_SCHOOL, SINGLE_SCHOOL, PLATFORM_WIDE, READ_ONLY)
FIRST_PARTY_APPS = {'students', 'schools', 'missions', 'vocabulary', 'demo_intel', 'dashboard', 'exams', 'governance', 'risk', 'interventions',
                    'academics', 'behavior', 'accounts', 'core'}


class ClassificationTests(TestCase):
    def test_every_first_party_command_is_classified_exactly_once(self):
        found = {name for name, app in get_commands().items() if app in FIRST_PARTY_APPS}
        classified = set().union(*CLASSES)
        self.assertEqual(sum(len(c) for c in CLASSES), len(classified), 'a command is in two classes')
        self.assertEqual(sorted(found - classified), [],
                         'new management command(s) not classified in schools/test_command_scope.py: decide needs-school / '
                         'single-school / platform-wide / read-only (S4(c), docs/changes/0019)')
        self.assertEqual(sorted(classified - found - {'demo_check'}), [], 'classified but not found (renamed or removed?)')   # demo_check: demo settings only


class TwoSchoolBase(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        self.b = School.objects.create(name='B', code='b')
        self.assertGreater(School.objects.count(), 1)          # the migration's default school makes it three


class SeedCommandTests(TwoSchoolBase):
    def test_seed_vocabulary(self):
        with self.assertRaisesMessage(CommandError, 'more than one school exists'):
            call_command('seed_vocabulary', verbosity=0)
        self.assertFalse(VocabularyTerm.objects.exists())
        call_command('seed_vocabulary', '--school', 'a', verbosity=0)
        self.assertEqual(set(VocabularyTerm.objects.values_list('school__code', flat=True)), {'a'})
        call_command('seed_vocabulary', '--all-schools', verbosity=0)
        self.assertEqual(set(VocabularyTerm.objects.values_list('school__code', flat=True)), {'a', 'b', 'default'})
        with self.assertRaises(CommandError):
            call_command('seed_vocabulary', '--school', 'nope', verbosity=0)

    def test_seed_mission(self):
        with self.assertRaisesMessage(CommandError, 'more than one school exists'):
            call_command('seed_mission', verbosity=0)
        self.assertFalse(WeightSet.objects.exists())
        call_command('seed_mission', '--school', 'b', verbosity=0)
        self.assertEqual(set(WeightSet.objects.values_list('school__code', flat=True)), {'b'})
        call_command('seed_mission', '--all-schools', verbosity=0)
        self.assertEqual(set(WeightSet.objects.values_list('school__code', flat=True)), {'a', 'b', 'default'})

    def test_with_exactly_one_school_nothing_changes(self):
        School.objects.exclude(code='a').delete()
        self.assertEqual(School.objects.count(), 1)
        call_command('seed_vocabulary', verbosity=0)
        call_command('seed_mission', verbosity=0)
        self.assertEqual(set(WeightSet.objects.values_list('school__code', flat=True)), {'a'})


class YearAndEnrollmentCommandTests(TwoSchoolBase):
    def setUp(self):
        super().setUp()
        self.klass = {}
        self.student = {}
        for school in (self.a, self.b):
            AcademicYear.objects.create(school=school, code='1404-1405', start_date=date(2025, 9, 23), end_date=date(2026, 6, 21), is_current=True)
            self.klass[school.code] = SchoolClass.objects.create(school=school, title='7-A', academic_year='1404', grade=7)   # un-normalised text
            self.student[school.code] = Student.objects.create(
                first_name=school.code, last_name='S', national_id=f'95{school.pk:08d}', grade=7, phone_number='0', school=school,
                school_class=self.klass[school.code])
        self.log = os.path.join(tempfile.mkdtemp(), 'log.json')

    def only_school_a(self):
        Student.objects.filter(school=self.b).delete()
        SchoolClass.objects.filter(school=self.b).delete()
        AcademicYear.objects.filter(school=self.b).delete()
        School.objects.exclude(code='a').delete()
        self.assertEqual(School.objects.count(), 1)

    def run_year(self, *args):
        out = StringIO()
        call_command('normalize_year_texts', '--json', *args, stdout=out)
        return json.loads(out.getvalue())

    def test_normalize_year_texts(self):
        report = self.run_year()                                           # a dry run may read every school
        self.assertEqual(report['mode'], 'DRY-RUN')
        with self.assertRaisesMessage(CommandError, 'more than one school exists'):
            self.run_year('--apply', '--log', self.log)
        self.assertEqual(set(SchoolClass.objects.values_list('academic_year', flat=True)), {'1404'})
        self.run_year('--apply', '--log', self.log, '--school-code', 'a')
        self.assertEqual(SchoolClass.objects.get(school=self.a).academic_year, '1404-1405')
        self.assertEqual(SchoolClass.objects.get(school=self.b).academic_year, '1404')             # untouched

    def test_normalize_year_texts_one_school_unchanged(self):
        self.only_school_a()
        self.run_year('--apply', '--log', self.log)
        self.assertEqual(SchoolClass.objects.get(school=self.a).academic_year, '1404-1405')

    def run_enrol(self, *args):
        out = StringIO()
        call_command('backfill_enrollments', '--json', *args, stdout=out)
        return json.loads(out.getvalue())

    def test_backfill_enrollments(self):
        SchoolClass.objects.update(academic_year='1404-1405')
        self.assertIn('enrollments_to_create', self.run_enrol())            # a dry run may read every school
        for args in (('--apply',), ('--revert-backfill', '--apply')):
            with self.assertRaisesMessage(CommandError, 'more than one school exists'):
                self.run_enrol(*args)
        self.assertFalse(Enrollment.objects.exists())
        self.run_enrol('--apply', '--school-code', 'a')
        self.assertEqual(list(Enrollment.objects.values_list('student__school__code', flat=True)), ['a'])
        self.run_enrol('--apply', '--school-code', 'b')
        self.assertEqual(sorted(Enrollment.objects.values_list('student__school__code', flat=True)), ['a', 'b'])
        self.run_enrol('--revert-backfill', '--apply', '--school-code', 'a')
        self.assertEqual(list(Enrollment.objects.values_list('student__school__code', flat=True)), ['b'])   # only school a was reverted

    def test_backfill_enrollments_one_school_unchanged(self):
        SchoolClass.objects.update(academic_year='1404-1405')
        self.only_school_a()
        self.run_enrol('--apply')
        self.assertEqual(Enrollment.objects.count(), 1)
