"""Stage 2.2a-4d tests: rollover_academic_year (dry-run default, evidence only, batch-logged, reversible)."""
import csv
import json
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass
from students.models import Attendance, Enrollment, ImportBatch, Student

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.school = School.objects.create(name='A', code='a')
        self.cur = AcademicYear.objects.create(
            school=self.school, code='1404-1405', start_date=date(2025, 9, 23), end_date=date(2026, 6, 21), is_current=True)
        self.nxt = AcademicYear.objects.create(
            school=self.school, code='1405-1406', start_date=date(2026, 9, 23), end_date=date(2027, 6, 21))
        mk = lambda title, year, grade: SchoolClass.objects.create(  # noqa: E731
            school=self.school, title=title, academic_year=year, grade=grade)
        self.old = {7: mk('7-A', '1404-1405', 7), 8: mk('8-A', '۱۴۰۴', 8), 12: mk('12-A', '1404/1405', 12)}
        self.new = {8: mk('8-N', '1405-1406', 8), 9: mk('9-N', '۱۴۰۵-۱۴۰۶', 9), 7: mk('7-N', '1405', 7)}
        self.n = 0
        self.user = User.objects.create_user('lead')

    def student(self, grade, klass, enroll=True):
        self.n += 1
        s = Student.objects.create(first_name=f'S{self.n}', last_name='T', national_id=f'{self.n:010d}', grade=grade,
                                   phone_number='0', school=self.school, school_class=klass)
        if enroll:
            Enrollment.objects.create(student=s, academic_year=self.cur, school_class=klass, grade=grade, source='manual')
        return s

    def csv(self, name, header, rows):
        path = Path(self.tmp.name) / name
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return str(path)

    def class_map(self, rows=None):
        return self.csv('map.csv', ['from_class', 'to_class'], rows or [['7-A', '8-N'], ['8-A', '9-N']])

    def run_cmd(self, *args):
        out = StringIO()
        call_command('rollover_academic_year', '--json', *args, stdout=out)
        return json.loads(out.getvalue())

    def state(self):
        return (
            sorted(Enrollment.objects.values_list('pk', 'status', 'ended_on', 'school_class_id', 'grade', 'source')),
            sorted(Student.objects.values_list('pk', 'grade', 'school_class_id', 'school_id', 'class_name')),
            sorted(AcademicYear.objects.values_list('pk', 'is_current')),
            sorted(SchoolClass.objects.values_list('pk', 'is_active')),
            sorted(GradeLeadAssignment.objects.values_list('pk', 'is_active')),
        )


class RolloverTests(Base):
    def test_dry_run_is_default_and_writes_nothing(self):
        self.student(7, self.old[7])
        before = self.state()
        report = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote')
        self.assertEqual(report['mode'], 'DRY-RUN')
        self.assertEqual((report['enrollments_to_close'], report['enrollments_to_open']), (1, 1))
        self.assertEqual(self.state(), before)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_apply_promotes_graduates_and_logs_a_batch(self):
        a = self.student(7, self.old[7])
        b = self.student(8, self.old[8])
        g = self.student(12, self.old[12])
        report = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote', '--apply')
        self.assertEqual(report['outcomes'], {'promoted': 2, 'graduated': 1})
        old_a = Enrollment.objects.get(student=a, academic_year=self.cur)
        self.assertEqual((old_a.status, old_a.ended_on), ('promoted', date(2026, 6, 21)))
        new_a = Enrollment.objects.get(student=a, academic_year=self.nxt)
        self.assertEqual((new_a.grade, new_a.school_class_id, new_a.status, new_a.source, new_a.started_on, new_a.ended_on),
                         (8, self.new[8].pk, 'active', 'rollover', date(2026, 9, 23), None))
        self.assertEqual(new_a.import_batch_id, report['import_batch'])
        a.refresh_from_db(); b.refresh_from_db(); g.refresh_from_db()
        self.assertEqual((a.grade, a.school_class_id, a.class_name), (8, self.new[8].pk, '8-N'))
        self.assertEqual((b.grade, b.school_class_id), (9, self.new[9].pk))
        self.assertEqual(Enrollment.objects.get(student=g, academic_year=self.cur).status, 'graduated')
        self.assertFalse(Enrollment.objects.filter(student=g, academic_year=self.nxt).exists())
        self.assertEqual((g.grade, g.school_class_id), (12, self.old[12].pk))  # graduate's mirror untouched
        self.assertEqual(ImportBatch.objects.get(pk=report['import_batch']).kind, 'rollover')

    def test_a_school_less_student_is_skipped_in_the_plan_and_apply_does_not_abort(self):
        # S6: save() will not give a legacy row a school; the plan says so and the apply run is not rolled back
        ok = self.student(7, self.old[7])
        legacy = self.student(8, self.old[8])
        Student.objects.filter(pk=legacy.pk).update(school=None, school_class=None)  # S6-2:retire
        args = ('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote')
        plan = self.run_cmd(*args)
        self.assertEqual(plan['skipped'].get('student_without_school'), 1)
        applied = self.run_cmd(*args, '--apply')
        self.assertEqual(applied['skipped'].get('student_without_school'), 1)
        self.assertTrue(Enrollment.objects.filter(student=ok, academic_year=self.nxt).exists())
        self.assertFalse(Enrollment.objects.filter(student=legacy, academic_year=self.nxt).exists())

    def test_idempotent(self):
        self.student(7, self.old[7])
        args = ('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote', '--apply')
        self.run_cmd(*args)
        state = self.state()
        again = self.run_cmd(*args)
        self.assertEqual((again['students_considered'], again['enrollments_to_close'], again['enrollments_to_open']), (0, 0, 0))
        self.assertEqual(self.state(), state)

    def test_no_default_means_no_guess(self):
        self.student(7, self.old[7])
        before = self.state()
        report = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--apply')
        self.assertEqual(report['skipped'], {'no_outcome_given': 1})
        self.assertEqual(self.state()[:2], before[:2])

    def test_outcomes_file_overrides_and_is_validated(self):
        keep, out, wd, prom = (self.student(7, self.old[7]), self.student(7, self.old[7]),
                               self.student(8, self.old[8]), self.student(8, self.old[8]))
        outcomes = self.csv('o.csv', ['national_id', 'status'], [
            [keep.national_id, 'retained'], [out.national_id, 'transferred_out'], [wd.national_id, 'withdrawn']])
        report = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map([['7-A', '7-N'], ['8-A', '9-N']]),
                              '--outcomes', outcomes, '--default', 'promote', '--apply')
        self.assertEqual(report['outcomes'], {'retained': 1, 'transferred_out': 1, 'withdrawn': 1, 'promoted': 1})
        self.assertEqual(Enrollment.objects.get(student=keep, academic_year=self.nxt).grade, 7)  # same grade
        self.assertEqual(Enrollment.objects.get(student=out, academic_year=self.cur).status, 'transferred_out')
        self.assertFalse(Enrollment.objects.filter(student=out, academic_year=self.nxt).exists())
        bad = self.csv('bad.csv', ['national_id', 'status'], [[keep.national_id, 'flying']])
        with self.assertRaises(CommandError):
            self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--outcomes', bad)

    def test_skipped_students_are_not_half_promoted(self):
        no_class = self.student(7, None)
        no_map = self.student(8, self.old[8])
        unknown = self.student(7, self.old[7])
        conflict = self.student(7, self.old[7])
        self.new[8].grade = 12
        self.new[8].save()  # target class grade conflicts with grade 8
        both = self.csv('m.csv', ['from_class', 'to_class'], [['7-A', '8-N'], ['8-A', 'ZZ']])
        before = self.state()
        report = self.run_cmd('--to', '1405-1406', '--class-map', both, '--default', 'promote', '--apply')
        self.assertEqual(report['skipped'], {
            'enrollment_without_class': 1, 'target_class_not_found': 1, 'target_class_grade_conflict': 2})
        self.assertEqual(report['enrollments_to_open'], 0)
        self.assertEqual(self.state(), before)  # nothing changed at all, not even the old rows
        for s in (no_class, no_map, unknown, conflict):
            self.assertEqual(Enrollment.objects.filter(student=s, academic_year=self.cur, ended_on__isnull=True).count(), 1)

    def test_ambiguous_target_class_and_missing_mapping(self):
        self.student(7, self.old[7])
        self.student(8, self.old[8])
        SchoolClass.objects.create(school=self.school, title='8-N', academic_year='1405', grade=8)  # duplicate title
        report = self.run_cmd('--to', '1405-1406', '--class-map', self.csv('m2.csv', ['from_class', 'to_class'], [['7-A', '8-N']]),
                              '--default', 'promote')
        self.assertEqual(report['skipped'], {'target_class_ambiguous': 1, 'no_class_mapping': 1})

    def test_student_already_in_target_year_is_skipped(self):
        s = self.student(7, self.old[7])
        Enrollment.objects.create(student=s, academic_year=self.nxt, school_class=self.new[8], grade=8, source='import')
        report = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote')
        self.assertEqual(report['skipped'], {'already_in_target_year': 1})

    def test_flags_and_exact_revert(self):
        lead = GradeLeadAssignment.objects.create(user=self.user, school=self.school, grade=7, academic_year='1404')
        for grade, klass in ((7, self.old[7]), (8, self.old[8]), (12, self.old[12])):
            self.student(grade, klass)
        before = self.state()
        dry = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote', '--flip-current',
                           '--deactivate-old-classes', '--deactivate-old-grade-lead-assignments')
        self.assertEqual(dry['old_classes_to_deactivate'], 3)
        self.assertEqual(dry['old_grade_lead_assignments_to_deactivate'], 1)
        self.assertEqual(self.state(), before)
        applied = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote', '--flip-current',
                               '--deactivate-old-classes', '--deactivate-old-grade-lead-assignments', '--apply')
        self.assertNotEqual(self.state(), before)
        self.assertTrue(AcademicYear.objects.get(pk=self.nxt.pk).is_current)
        self.assertFalse(AcademicYear.objects.get(pk=self.cur.pk).is_current)
        self.assertFalse(SchoolClass.objects.get(pk=self.old[7].pk).is_active)
        self.assertTrue(SchoolClass.objects.get(pk=self.new[8].pk).is_active)  # target classes untouched
        lead.refresh_from_db()
        self.assertFalse(lead.is_active)
        preview = self.run_cmd('--revert-batch', str(applied['import_batch']))
        self.assertEqual(preview['enrollments_to_delete'], 2)
        self.run_cmd('--revert-batch', str(applied['import_batch']), '--apply')
        self.assertEqual(self.state(), before)  # exact
        with self.assertRaises(CommandError):
            self.run_cmd('--revert-batch', str(applied['import_batch']), '--apply')  # not twice

    def test_flags_are_opt_in(self):
        GradeLeadAssignment.objects.create(user=self.user, school=self.school, grade=7, academic_year='1404')
        self.student(7, self.old[7])
        self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote', '--apply')
        self.assertTrue(AcademicYear.objects.get(pk=self.cur.pk).is_current)
        self.assertTrue(SchoolClass.objects.get(pk=self.old[7].pk).is_active)
        self.assertTrue(GradeLeadAssignment.objects.get().is_active)

    def test_revert_is_refused_once_the_new_enrollment_is_used(self):
        s = self.student(7, self.old[7])
        applied = self.run_cmd('--to', '1405-1406', '--class-map', self.class_map(), '--default', 'promote', '--apply')
        Attendance.objects.create(student=s, date=date(2026, 10, 1), status='present',
                                 enrollment=Enrollment.objects.get(student=s, academic_year=self.nxt))
        with self.assertRaises(CommandError):
            self.run_cmd('--revert-batch', str(applied['import_batch']), '--apply')

    def test_target_year_validation(self):
        m = self.class_map()
        for to in ('404', '1409-1410', '1403-1404', '1404-1405'):
            with self.assertRaises(CommandError, msg=to):
                self.run_cmd('--to', to, '--class-map', m)
        other = School.objects.create(name='B', code='b')
        AcademicYear.objects.create(school=other, code='1404-1405', start_date=date(2025, 9, 23),
                                    end_date=date(2026, 6, 21), is_current=True)
        with self.assertRaises(CommandError):
            self.run_cmd('--to', '1405-1406', '--class-map', m)  # two schools with a current year: needs --school-code
        self.run_cmd('--to', '1405-1406', '--class-map', m, '--school-code', 'a')
