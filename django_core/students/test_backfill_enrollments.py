"""Stage 2.2a-2 tests: backfill_enrollments on the multi-year SYNTHETIC seed (ADR-0011, proposal 0003 §4).

Traceability: P2-REQ-23 (no guesses, evidence only), idempotence, exact revert, no access change.
"""
import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from schools.models import AcademicYear, School
from students.access import PARENT, visible_students
from students.models import Attendance, Enrollment, Grade, Student


def run(*args):
    out = StringIO()
    call_command('backfill_enrollments', '--json', *args, stdout=out)
    return json.loads(out.getvalue())


def snapshot():
    return (
        sorted(Grade.objects.values_list('pk', 'enrollment_id', 'enrollment_link_source')),
        sorted(Attendance.objects.values_list('pk', 'enrollment_id', 'enrollment_link_source')),
        sorted(Enrollment.objects.values_list('pk', 'source')),
    )


class SeededBase(TestCase):
    def setUp(self):
        call_command('seed_temporal_synthetic', '--i-know-this-is-synthetic', stdout=StringIO())


class SeedGuardTests(TestCase):
    def test_refuses_without_confirmation_and_on_non_empty_database(self):
        with self.assertRaises(CommandError):
            call_command('seed_temporal_synthetic', stdout=StringIO())
        call_command('seed_temporal_synthetic', '--i-know-this-is-synthetic', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('seed_temporal_synthetic', '--i-know-this-is-synthetic', stdout=StringIO())

    def test_seed_shape(self):
        call_command('seed_temporal_synthetic', '--i-know-this-is-synthetic', stdout=StringIO())
        self.assertEqual(AcademicYear.objects.filter(school__code='synthetic-temporal').count(), 3)
        self.assertEqual(Student.objects.count(), 6 + 4 + 1 + 1 + 5 + 1)  # cohorts, seniors, graduate, transfer, noise, mid-year
        # three spellings of the year on the class rows
        from schools.models import SchoolClass
        spellings = set(SchoolClass.objects.values_list('academic_year', flat=True))
        self.assertTrue({'۱۴۰۲-۱۴۰۳', '1403/1404', '1404', '404', '1401'} <= spellings)


class DryRunTests(SeededBase):
    def test_default_is_a_dry_run_and_writes_nothing(self):
        before = snapshot()
        report = run()
        self.assertEqual(report['mode'], 'backfill DRY-RUN')
        self.assertEqual(report['enrollments_to_create'], 12)
        self.assertEqual(snapshot(), before)

    def test_dry_run_predicts_what_apply_does(self):
        predicted = run()
        applied = run('--apply')
        self.assertEqual(predicted['enrollments_to_create'], applied['enrollments_created'])
        for label in ('grades', 'attendance'):
            self.assertEqual(predicted[label]['to_link'], applied[label]['linked'], label)
            for key in ('rows', 'already_linked'):
                self.assertEqual(predicted[label].get(key), applied[label].get(key))


class ApplyTests(SeededBase):
    def test_creates_only_evidenced_enrollments(self):
        report = run('--apply')
        self.assertEqual(report['mode'], 'backfill APPLIED')
        self.assertEqual(report['enrollments_created'], 12)
        skipped = report['enrollments_skipped']
        self.assertEqual(skipped['student_without_class'], 1)
        self.assertEqual(skipped['class_year_blank_or_unresolved'], 1)
        self.assertEqual(skipped['class_year_has_no_academic_year_row'], 1)
        self.assertEqual(skipped['class_link_points_to_a_past_year_not_evidenced'], 2)  # stale link + graduate
        self.assertEqual(skipped['class_grade_differs_from_student_grade'], 1)
        made = Enrollment.objects.filter(source='backfill')
        self.assertEqual(made.count(), 12)
        self.assertEqual(set(made.values_list('status', flat=True)), {'active'})
        self.assertEqual({e.academic_year.code for e in made}, {'1404-1405'})
        for e in made:
            self.assertEqual(e.grade, e.student.grade)
            self.assertEqual(e.school_class_id, e.student.school_class_id)
        skipped_names = {'NoClass0', 'BadYear0', 'NoYearRow0', 'StaleLink0', 'Graduate0', 'GradeConflict0'}
        self.assertEqual(
            set(made.values_list('student__first_name', flat=True)) & skipped_names, set())

    def test_links_rows_only_when_year_and_enrollment_are_unambiguous(self):
        run('--apply')
        for model in (Grade, Attendance):
            linked = model.objects.filter(enrollment__isnull=False)
            self.assertTrue(linked.exists())
            for row in linked.select_related('enrollment__academic_year', 'student'):
                self.assertEqual(row.enrollment.student_id, row.student_id)
                year = row.enrollment.academic_year
                self.assertTrue(year.start_date <= row.date <= year.end_date)
                self.assertEqual(row.enrollment_link_source, 'backfill')
            names = lambda qs: set(qs.values_list('student__first_name', flat=True))  # noqa: E731
            unlinked = model.objects.filter(enrollment__isnull=True)
            # no class -> no school -> never guessed; mid-year change = two enrollments in that year;
            # classes with unresolved/unknown years have no enrollment to link to
            self.assertTrue({'NoClass0', 'BadYear0', 'NoYearRow0', 'GradeConflict0', 'StaleLink0'} <= names(unlinked))
            mid_past = unlinked.filter(student__first_name='MidYear0', date__lt='2025-09-23')
            self.assertTrue(mid_past.exists())
            # cohort rows of past years were linked to the import enrollments, current to backfill ones
            cohort = linked.filter(student__first_name='Cohort0')
            self.assertEqual({r.enrollment.academic_year.code for r in cohort.select_related('enrollment__academic_year')},
                             {'1402-1403', '1403-1404', '1404-1405'})
            self.assertEqual(names(linked.filter(student__first_name='Graduate0')), {'Graduate0'})

    def test_idempotent(self):
        run('--apply')
        state = snapshot()
        again = run('--apply')
        self.assertEqual(again['enrollments_created'], 0)
        self.assertEqual(again['enrollments_skipped']['enrollment_already_exists'], 12)
        self.assertEqual(again['grades'].get('linked', 0), 0)
        self.assertEqual(again['attendance'].get('linked', 0), 0)
        self.assertEqual(snapshot(), state)

    def test_never_changes_students_or_visibility(self):
        parent = get_user_model().objects.create_user(username='parent')
        parent.groups.add(Group.objects.get_or_create(name=PARENT)[0])
        Student.objects.filter(first_name='Cohort0').update(parent_user=parent)
        students = list(Student.objects.order_by('pk').values())
        seen = sorted(visible_students(parent).values_list('pk', flat=True))
        run('--apply')
        self.assertEqual(list(Student.objects.order_by('pk').values()), students)
        self.assertEqual(sorted(visible_students(parent).values_list('pk', flat=True)), seen)

    def test_nothing_to_do_on_an_empty_database(self):
        Grade.objects.all().delete()
        Attendance.objects.all().delete()
        Enrollment.objects.all().delete()
        Student.objects.all().delete()
        report = run('--apply')
        self.assertEqual(report['enrollments_created'], 0)


class RevertTests(SeededBase):
    def test_revert_dry_run_writes_nothing(self):
        run('--apply')
        state = snapshot()
        report = run('--revert-backfill')
        self.assertEqual(report['mode'], 'revert DRY-RUN')
        self.assertGreater(report['grades_to_unlink'], 0)
        self.assertEqual(snapshot(), state)

    def test_revert_restores_the_state_before_apply(self):
        before = snapshot()
        run('--apply')
        self.assertNotEqual(snapshot(), before)
        report = run('--revert-backfill', '--apply')
        self.assertEqual(report['enrollments_deleted'], 12)
        self.assertEqual(report['enrollments_kept_because_in_use'], 0)
        self.assertEqual(snapshot(), before)
        # imported past-year enrollments were never touched
        self.assertTrue(Enrollment.objects.filter(source='import').exists())

    def test_revert_keeps_enrollments_that_something_else_now_uses(self):
        run('--apply')
        enrollment = Enrollment.objects.filter(source='backfill').first()
        manual = Grade.objects.create(
            student=enrollment.student, subject='math', exam_type='quiz', score=1,
            date=enrollment.academic_year.start_date, enrollment=enrollment)  # entered later by a person
        report = run('--revert-backfill', '--apply')
        self.assertEqual(report['enrollments_kept_because_in_use'], 1)
        manual.refresh_from_db()
        self.assertEqual(manual.enrollment_id, enrollment.pk)
        self.assertEqual(manual.enrollment_link_source, '')
        self.assertEqual(Enrollment.objects.filter(source='backfill').count(), 1)
