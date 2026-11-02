"""Stage 2.2a-3 tests: year-aware historical import on the multi-year SYNTHETIC seed (ADR-0011 §5)."""
import csv
import json
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from schools.models import AcademicYear, School
from students.models import Attendance, Enrollment, Grade, ImportBatch, Student


class Base(TestCase):
    def setUp(self):
        call_command('seed_temporal_synthetic', '--i-know-this-is-synthetic', stdout=StringIO())
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nid = {s.first_name: s.national_id for s in Student.objects.all()}

    def write(self, header, rows, name='f.csv'):
        path = Path(self.tmp.name) / name
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return str(path)

    def run_cmd(self, kind, year, path, *extra, expect_error=False):
        out = StringIO()
        call_command('import_history', '--kind', kind, '--year', year, '--file', path, '--json', *extra, stdout=out)
        return json.loads(out.getvalue())

    def students_snapshot(self):
        return list(Student.objects.order_by('pk').values())


class MaxScoreOptionTests(Base):
    def test_max_score_must_be_an_integer_between_1_and_1000(self):
        """Review L-3 (decision 48): nan, inf, fractions and out-of-range values are refused with a clear error."""
        from django.core.management.base import CommandError
        path = self.write(['national_id', 'subject', 'exam_type', 'score', 'date'], [])
        for bad in ('nan', 'inf', '20.5', 'abc'):
            with self.assertRaises(CommandError, msg=bad):
                self.run_cmd('grades', '1404-1405', path, '--max-score', bad)
        for bad in ('0', '1001'):
            with self.assertRaisesMessage(CommandError, '1 to 1000'):
                self.run_cmd('grades', '1404-1405', path, '--max-score', bad)


class RosterTests(Base):
    HEADER = ['national_id', 'grade', 'status', 'class']

    def test_dry_run_writes_nothing_then_apply_creates(self):
        path = self.write(self.HEADER, [[self.nid['BadYear0'], '8', 'promoted', '8-A']])
        students = self.students_snapshot()
        enrollments = Enrollment.objects.count()
        report = self.run_cmd('roster', '1402-1403', path)
        self.assertEqual(report['mode'], 'DRY-RUN')
        self.assertEqual(report['counts']['would_create'], 1)
        self.assertEqual(Enrollment.objects.count(), enrollments)
        self.assertEqual(ImportBatch.objects.count(), 0)
        report = self.run_cmd('roster', '1402-1403', path, '--apply')
        self.assertEqual(report['counts']['created'], 1)
        e = Enrollment.objects.get(student__first_name='BadYear0', academic_year__code='1402-1403')
        self.assertEqual((e.source, e.grade, e.status, e.school_class.title), ('import', 8, 'promoted', '8-A'))
        self.assertEqual(e.import_batch_id, report['import_batch'])
        self.assertEqual(self.students_snapshot(), students)  # no Student field was touched

    def test_persian_digits_and_year_variants(self):
        path = self.write(self.HEADER, [['۹۹۰۰۰۰۰۰۱۴', '۸', 'promoted', '8-A']])
        for variant in ('۱۴۰۲-۱۴۰۳', '1402/1403', '1402', '1402-03'):
            report = self.run_cmd('roster', variant, path)
            self.assertEqual(report['academic_year'], '1402-1403')
            self.assertEqual(report['counts']['would_create'], 1)

    def test_unresolved_or_missing_year_and_missing_column(self):
        path = self.write(self.HEADER, [[self.nid['BadYear0'], '8', 'promoted', '8-A']])
        with self.assertRaises(CommandError):
            self.run_cmd('roster', '404', path)
        with self.assertRaises(CommandError):
            self.run_cmd('roster', '1401-1402', path)  # no AcademicYear row (never auto-created)
        bad = self.write(['national_id', 'grade'], [[self.nid['BadYear0'], '8']], 'bad.csv')
        with self.assertRaises(CommandError):
            self.run_cmd('roster', '1402-1403', bad)

    def test_rejections_are_reported_not_guessed(self):
        elsewhere = Student.objects.create(
            first_name='OtherSchool0', last_name='Synthetic', national_id='9900009999', grade=10, phone_number='0',
            school=School.objects.create(name='Other synthetic school', code='other-synthetic'))
        self.nid['OtherSchool0'] = elsewhere.national_id
        path = self.write(self.HEADER, [
            ['9999999999', '8', 'promoted', '8-A'],                 # unknown student
            ['12ab', '8', 'promoted', '8-A'],                       # invalid national id
            [self.nid['OtherSchool0'], '8', 'promoted', '8-A'],     # student of another school
            [self.nid['BadYear0'], '8', 'promoted', 'zzz'],         # class not in that year
            [self.nid['NoYearRow0'], '5', 'promoted', '8-A'],       # grade invalid
            [self.nid['StaleLink0'], '8', 'unknown', '8-A'],        # status invalid
            [self.nid['Cohort0'], '9', 'promoted', '8-A'],          # conflicts with existing (grade 8 in 1402-1403)
            [self.nid['Cohort1'], '8', 'promoted', '8-A'],          # identical to existing -> unchanged
        ])
        report = self.run_cmd('roster', '1402-1403', path)
        reasons = report['rejected_by_reason']
        for key in ('unknown_student', 'national_id_invalid', 'student_not_in_the_years_school',
                    'class_not_found_in_year', 'grade_invalid', 'status_invalid',
                    'conflicts_with_existing_enrollment'):
            self.assertEqual(reasons.get(key), 1, key)
        self.assertEqual(report['counts']['unchanged'], 1)
        self.assertTrue(all(set(r) == {'row', 'reason'} for r in report['rejected_rows']))  # no personal data

    def test_idempotent_and_revert(self):
        path = self.write(self.HEADER, [[self.nid['BadYear0'], '8', 'promoted', '8-A']])
        first = self.run_cmd('roster', '1402-1403', path, '--apply')
        again = self.run_cmd('roster', '1402-1403', path, '--apply')
        self.assertEqual(again['counts'].get('created', 0), 0)
        self.assertEqual(again['counts']['unchanged'], 1)
        before = Enrollment.objects.count()
        dry = json.loads(self._revert(first['import_batch'], False))
        self.assertEqual(Enrollment.objects.count(), before)
        self.assertEqual(dry['enrollments_to_delete_if_unused'], 1)
        done = json.loads(self._revert(first['import_batch'], True))
        self.assertEqual(done['enrollments_deleted'], 1)
        self.assertEqual(Enrollment.objects.count(), before - 1)
        self.assertTrue(ImportBatch.objects.get(pk=first['import_batch']).counts['reverted'])
        again = json.loads(self._revert(first['import_batch'], True))  # harmless twice
        self.assertEqual(again['enrollments_deleted'], 0)

    def _revert(self, batch, apply):
        out = StringIO()
        args = ['--revert-batch', str(batch), '--json'] + (['--apply'] if apply else [])
        call_command('import_history', *args, stdout=out)
        return out.getvalue()


class GradesTests(Base):
    HEADER = ['national_id', 'subject', 'exam_type', 'score', 'date']

    def test_apply_attaches_rows_to_the_years_enrollment(self):
        path = self.write(self.HEADER, [
            [self.nid['Cohort0'], 'math', 'midterm', '17.5', '2024-01-10'],
            [self.nid['Cohort0'], 'ریاضی', 'آزمون', '۱۶', '۲۰۲۴/۰۱/۱۱'],   # Persian label + digits + slash date
        ])
        report = self.run_cmd('grades', '1402-1403', path, '--apply')
        self.assertEqual(report['counts']['created'], 2)
        rows = Grade.objects.filter(import_batch_id=report['import_batch'])
        self.assertEqual(rows.count(), 2)
        for g in rows.select_related('enrollment__academic_year'):
            self.assertEqual(g.enrollment.academic_year.code, '1402-1403')
            self.assertEqual(g.enrollment.student_id, g.student_id)
            self.assertEqual(g.enrollment_link_source, '')
        self.assertEqual(sorted(rows.values_list('score', flat=True)), [16.0, 17.5])

    def test_rejections(self):
        mid = self.nid['MidYear0']
        path = self.write(self.HEADER, [
            [self.nid['Cohort0'], 'math', 'quiz', '25', '2024-01-10'],        # score out of range
            [self.nid['Cohort0'], 'math', 'quiz', 'abc', '2024-01-10'],       # not a number
            [self.nid['Cohort0'], 'math', 'quiz', '10', '1402/10/20'],        # Solar Hijri date
            [self.nid['Cohort0'], 'math', 'quiz', '10', '2025-01-10'],        # outside the year
            [self.nid['Cohort0'], 'cooking', 'quiz', '10', '2024-01-10'],     # subject not in vocabulary
            [self.nid['Cohort0'], 'math', 'oral', '10', '2024-01-10'],        # exam type invalid
            [self.nid['BadYear0'], 'math', 'quiz', '10', '2024-01-10'],       # no enrollment in that year
            [mid, 'math', 'quiz', '10', '2024-12-01'],                        # several enrollments in 1403-1404
        ])
        report = self.run_cmd('grades', '1402-1403', path)
        r = report['rejected_by_reason']
        self.assertEqual(r['score_out_of_range'], 1)
        self.assertEqual(r['score_not_a_number'], 1)
        self.assertEqual(r['date_looks_solar_hijri_use_gregorian'], 1)
        self.assertEqual(r['date_outside_academic_year'], 2)  # 2025-01-10 and 2024-12-01 for the 1402-1403 year
        self.assertEqual(r['subject_not_in_vocabulary'], 1)
        self.assertEqual(r['exam_type_invalid'], 1)
        self.assertEqual(r['no_enrollment_in_year'], 1)
        report = self.run_cmd('grades', '1403-1404', self.write(self.HEADER, [[mid, 'math', 'quiz', '10', '2024-12-01']], 'm.csv'))
        self.assertEqual(report['rejected_by_reason']['several_enrollments_in_year'], 1)

    def test_existing_grade_is_never_overwritten(self):
        # seeded grades are not linked (backfill not run), so they count as existing by natural key
        rows = list(Grade.objects.filter(student__first_name='Cohort0', date__range=('2023-09-23', '2024-06-21'))[:2])
        same, diff = rows
        path = self.write(self.HEADER, [
            [self.nid['Cohort0'], same.subject, same.exam_type, str(same.score), same.date.isoformat()],
            [self.nid['Cohort0'], diff.subject, diff.exam_type, str(diff.score + 1), diff.date.isoformat()],
        ])
        before = diff.score
        report = self.run_cmd('grades', '1402-1403', path, '--apply')
        self.assertEqual(report['counts']['unchanged'], 1)
        self.assertEqual(report['rejected_by_reason']['conflicts_with_existing_grade'], 1)
        diff.refresh_from_db()
        self.assertEqual(diff.score, before)
        # the same key twice in one file with different scores is rejected, not resolved by order
        path2 = self.write(self.HEADER, [
            [self.nid['Cohort0'], 'math', 'quiz', '10', '2024-03-03'],
            [self.nid['Cohort0'], 'math', 'quiz', '11', '2024-03-03'],
        ], 'dup.csv')
        report = self.run_cmd('grades', '1402-1403', path2)
        self.assertEqual(report['rejected_by_reason']['conflicting_duplicate_in_file'], 1)

    def test_idempotent_and_revert_batch(self):
        path = self.write(self.HEADER, [[self.nid['Cohort0'], 'physics', 'final', '15', '2024-02-02']])
        first = self.run_cmd('grades', '1402-1403', path, '--apply')
        second = self.run_cmd('grades', '1402-1403', path, '--apply')
        self.assertEqual(second['counts'].get('created', 0), 0)
        self.assertEqual(second['counts']['unchanged'], 1)
        total = Grade.objects.count()
        out = StringIO()
        call_command('import_history', '--revert-batch', str(first['import_batch']), '--apply', '--json', stdout=out)
        self.assertEqual(json.loads(out.getvalue())['grades_deleted'], 1)
        self.assertEqual(Grade.objects.count(), total - 1)
        self.assertEqual(ImportBatch.objects.count(), 2)  # batch rows are kept as the audit trail


class AttendanceTests(Base):
    HEADER = ['national_id', 'date', 'status', 'note']

    def test_apply_conflict_and_year_range(self):
        rows = list(Attendance.objects.filter(
            student__first_name='Cohort0', date__range=('2023-09-23', '2024-06-21')).order_by('date')[:2])
        existing, same = rows
        other = 'present' if existing.status == 'absent' else 'absent'
        path = self.write(self.HEADER, [
            [self.nid['Cohort0'], '2024-02-03', 'غائب', 'x'],                       # new, Persian label
            [self.nid['Cohort0'], existing.date.isoformat(), other, ''],            # conflicts with stored status
            [self.nid['Cohort0'], same.date.isoformat(), same.status, ''],          # identical
            [self.nid['Cohort0'], '2025-02-03', 'present', ''],                     # outside the year
        ])
        report = self.run_cmd('attendance', '1402-1403', path, '--apply')
        self.assertEqual(report['counts']['created'], 1)
        self.assertEqual(report['counts']['unchanged'], 1)
        self.assertEqual(report['rejected_by_reason']['conflicts_with_existing_attendance'], 1)
        self.assertEqual(report['rejected_by_reason']['date_outside_academic_year'], 1)
        existing.refresh_from_db()
        self.assertNotEqual(existing.status, other)
        new = Attendance.objects.get(student__first_name='Cohort0', date=date(2024, 2, 3))
        self.assertEqual((new.status, new.enrollment.academic_year.code, new.note), ('absent', '1402-1403', 'x'))


class WholeRunInvariantTests(Base):
    def test_no_student_field_changes_and_no_visibility_inputs_touched(self):
        students = self.students_snapshot()
        roster = self.write(['national_id', 'grade', 'status', 'class'],
                            [[self.nid['BadYear0'], '8', 'promoted', '8-A']], 'r.csv')
        grades = self.write(['national_id', 'subject', 'exam_type', 'score', 'date'],
                            [[self.nid['BadYear0'], 'math', 'quiz', '12', '2024-02-02']], 'g.csv')
        att = self.write(['national_id', 'date', 'status'], [[self.nid['BadYear0'], '2024-02-03', 'present']], 'a.csv')
        self.run_cmd('roster', '1402-1403', roster, '--apply')
        self.run_cmd('grades', '1402-1403', grades, '--apply')
        self.run_cmd('attendance', '1402-1403', att, '--apply')
        self.assertEqual(self.students_snapshot(), students)

    def test_year_in_two_schools_needs_a_school_code(self):
        other = School.objects.create(name='Other', code='other')
        AcademicYear.objects.create(school=other, code='1402-1403', start_date=date(2023, 9, 23), end_date=date(2024, 6, 21))
        path = self.write(['national_id', 'grade', 'status'], [[self.nid['BadYear0'], '8', 'promoted']])
        with self.assertRaises(CommandError):
            self.run_cmd('roster', '1402-1403', path)
        report = self.run_cmd('roster', '1402-1403', path, '--school-code', 'synthetic-temporal')
        self.assertEqual(report['school'], 'synthetic-temporal')
