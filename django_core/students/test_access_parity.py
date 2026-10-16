"""Stage 2.2a-4b tests: legacy vs enrollment-based matching, every intended difference asserted (ADR-0011).

Nothing here switches access: ``students.access.visible_students`` is still the legacy rule (a guard test
proves it). The switch (4c) happens only after these tools show zero UNEXPLAINED differences.
"""
import inspect
import json
from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, TeacherAssignment
from students import access, access_enrollment, access_legacy
from students.access import GRADE_LEAD, PARENT, TEACHER
from students.enrollment_sync import ensure_current_enrollment
from students.models import Enrollment, Student

User = get_user_model()


def make_user(username, *groups, **extra):
    user = User.objects.create_user(username=username, **extra)
    for g in groups:
        user.groups.add(Group.objects.get_or_create(name=g)[0])
    return user


def ids(qs):
    return {s.pk: s.full_tier for s in qs}


class Base(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='A', code='a')
        self.other = School.objects.create(name='B', code='b')
        self.year = AcademicYear.objects.create(
            school=self.school, code='1404-1405', start_date=date(2025, 9, 23), end_date=date(2026, 6, 21), is_current=True)
        self.old_year = AcademicYear.objects.create(
            school=self.school, code='1403-1404', start_date=date(2024, 9, 23), end_date=date(2025, 6, 21))
        self.c10a = SchoolClass.objects.create(school=self.school, title='10-A', academic_year='1404-1405', grade=10)
        self.c10b = SchoolClass.objects.create(school=self.school, title='10-B', academic_year='1404-1405', grade=10)
        self.c11a = SchoolClass.objects.create(school=self.school, title='11-A', academic_year='1404-1405', grade=11)
        self.n = 0

    def student(self, klass, grade=10, sync=True, **kw):
        self.n += 1
        s = Student.objects.create(first_name=f'S{self.n}', last_name='T', national_id=f'{self.n:010d}', grade=grade,
                                   phone_number='0', school_class=klass, school=kw.pop('school', None), **kw)
        if sync:
            ensure_current_enrollment(s)
        return s

    def lead(self, name, grade, year, school=None):
        u = make_user(name, GRADE_LEAD)
        GradeLeadAssignment.objects.create(user=u, school=school or self.school, grade=grade, academic_year=year)
        return u

    def teacher(self, name, klass, subject='math'):
        u = make_user(name, TEACHER)
        TeacherAssignment.objects.create(teacher=u, school_class=klass, subject=subject)
        return u

    def legacy(self, u):
        return ids(access_legacy.visible_students(u))

    def new(self, u):
        return ids(access_enrollment.visible_students_by_enrollment(u))

    def report(self):
        out = StringIO()
        try:
            call_command('compare_access_parity', '--json', stdout=out)
            failed = False
        except CommandError:
            failed = True
        return json.loads(out.getvalue()), failed


class EquivalentDataTests(Base):
    def test_rules_agree_when_mirror_and_enrollment_agree(self):
        a, b, c = self.student(self.c10a), self.student(self.c10b), self.student(self.c11a, grade=11)
        parent = make_user('par', PARENT)
        a.parent_user = parent
        a.save()
        users = [self.lead('l10', 10, '1404-1405'), self.lead('l11', 11, '1404-1405'), self.teacher('t10a', self.c10a),
                 self.teacher('t11', self.c11a), parent]
        for u in users:
            self.assertEqual(self.legacy(u), self.new(u), u.username)
        self.assertEqual(set(self.new(users[0])), {a.pk, b.pk})
        report, failed = self.report()
        self.assertFalse(failed)
        self.assertEqual((report['students_only_legacy'], report['students_only_new'], report['tier_differences'],
                          report['unexplained']), (0, 0, 0, 0))
        self.assertGreater(report['students_in_both'], 0)

    def test_properties_hold_in_both_rules(self):
        s = self.student(self.c10a)
        other_school_class = SchoolClass.objects.create(school=self.other, title='x', academic_year='1404-1405')
        lo, to = self.lead('lo', 10, '1404-1405', school=self.other), self.teacher('to', other_school_class)
        for fn in (self.legacy, self.new):
            # other school's lead / teacher see nothing of this school
            self.assertEqual(fn(lo), {})
            self.assertEqual(fn(to), {})
        lead = self.lead('lx', 10, '1404-1405')
        for mutate, label in ((lambda: setattr(lead, 'is_staff', True), 'staff'), (lambda: setattr(lead, 'is_active', False), 'inactive')):
            mutate()
            lead.save()
            self.assertEqual((self.legacy(lead), self.new(lead)), ({}, {}), label)
        lead2 = self.lead('ly', 10, '1404-1405')
        lead2.groups.clear()
        self.assertEqual((self.legacy(lead2), self.new(lead2)), ({}, {}))
        blank = make_user('tb', TEACHER)
        TeacherAssignment.objects.create(teacher=blank, school_class=self.c10a, subject='')
        self.assertEqual((self.legacy(blank), self.new(blank)), ({}, {}))
        inactive = self.teacher('ti', self.c10b)
        self.c10b.is_active = False
        self.c10b.save()
        self.assertEqual((self.legacy(inactive), self.new(inactive)), ({}, {}))
        self.assertTrue(s.pk)


class IntendedDifferenceTests(Base):
    """Each difference is a bug the switch fixes; each must be classified, never UNEXPLAINED."""

    def assert_explained(self, category, **counts):
        report, failed = self.report()
        self.assertFalse(failed, report)
        self.assertEqual(report['unexplained'], 0)
        self.assertEqual(report['explained_by'].get(category), counts.get('n', 1), report)
        return report

    def test_a_promoted_student_with_stale_mirror(self):
        old_class = SchoolClass.objects.create(school=self.school, title='9-A', academic_year='1403/1404', grade=9)
        # promoted: the current enrollment says grade 10 / 10-A, the mirror still points to last year's class
        s = self.student(old_class, grade=9, sync=False)
        Enrollment.objects.create(student=s, academic_year=self.year, school_class=self.c10a, grade=10)
        old_lead = self.lead('old', 9, '1403/1404')
        new_lead = self.lead('new', 10, '1404-1405')
        self.assertEqual(set(self.legacy(old_lead)), {s.pk})
        self.assertEqual(set(self.new(old_lead)), set())
        self.assertEqual(set(self.legacy(new_lead)), set())
        self.assertEqual(set(self.new(new_lead)), {s.pk})
        self.assert_explained('mirror_class_year_differs_from_current_year', n=2)

    def test_b_year_spelling_variant(self):
        klass = SchoolClass.objects.create(school=self.school, title='10-V', academic_year='۱۴۰۴-۱۴۰۵', grade=10)
        s = self.student(klass)
        lead = self.lead('lv', 10, '1404')
        self.assertEqual(set(self.legacy(lead)), set())   # string equality misses
        self.assertEqual(set(self.new(lead)), {s.pk})
        self.assert_explained('assignment_year_spelling_variant')

    def test_c_enrollment_without_class_mirror(self):
        s = self.student(None, sync=False, school=self.school)
        Enrollment.objects.create(student=s, academic_year=self.year, school_class=None, grade=10)
        lead = self.lead('lc', 10, '1404-1405')
        self.assertEqual((set(self.legacy(lead)), set(self.new(lead))), (set(), {s.pk}))
        self.assert_explained('enrollment_without_class_mirror')

    def test_d_mirror_grade_and_class_differ_from_enrollment(self):
        no_grade = SchoolClass.objects.create(school=self.school, title='mix', academic_year='1404-1405')
        s = self.student(no_grade, grade=11, sync=False)       # mirror says grade 11
        Enrollment.objects.create(student=s, academic_year=self.year, school_class=no_grade, grade=10)  # enrollment says 10
        l10, l11 = self.lead('d10', 10, '1404-1405'), self.lead('d11', 11, '1404-1405')
        self.assertEqual((set(self.legacy(l10)), set(self.new(l10))), (set(), {s.pk}))
        self.assertEqual((set(self.legacy(l11)), set(self.new(l11))), ({s.pk}, set()))
        self.assert_explained('mirror_grade_differs_from_enrollment', n=2)

    def test_d_teacher_class_from_enrollment(self):
        s = self.student(self.c10a, sync=False)
        Enrollment.objects.create(student=s, academic_year=self.year, school_class=self.c10b, grade=10)
        ta, tb = self.teacher('ta', self.c10a), self.teacher('tb', self.c10b)
        self.assertEqual((set(self.legacy(ta)), set(self.new(ta))), ({s.pk}, set()))
        self.assertEqual((set(self.legacy(tb)), set(self.new(tb))), (set(), {s.pk}))
        self.assert_explained('mirror_class_differs_from_enrollment_class', n=2)

    def test_e_school_without_current_year(self):
        s = self.student(self.c10a)
        lead = self.lead('le', 10, '1404-1405')
        AcademicYear.objects.filter(pk=self.year.pk).update(is_current=False)
        self.assertEqual((set(self.legacy(lead)), set(self.new(lead))), ({s.pk}, set()))
        self.assert_explained('school_has_no_current_year')

    def test_tier_difference_is_classified(self):
        klass = SchoolClass.objects.create(school=self.school, title='10-V', academic_year='۱۴۰۴-۱۴۰۵', grade=10)
        s = self.student(klass)
        u = self.lead('both', 10, '1404')
        u.groups.add(Group.objects.get_or_create(name=TEACHER)[0])
        TeacherAssignment.objects.create(teacher=u, school_class=klass, subject='math')
        self.assertEqual((self.legacy(u), self.new(u)), ({s.pk: False}, {s.pk: True}))
        report = self.assert_explained('assignment_year_spelling_variant')
        self.assertEqual(report['tier_differences'], 1)


class UnexplainedAndToolTests(Base):
    def test_a_difference_outside_the_list_fails_the_gate(self):
        """A student the legacy rule shows but who has NO current enrollment (here a class-grade conflict that the
        sync refused to enroll) is not an intended difference: it must be fixed, not explained away."""
        s = self.student(self.c10a, grade=11)       # class grade 10 vs student grade 11: sync skips it
        t = self.teacher('tc', self.c10a)
        self.assertEqual((set(self.legacy(t)), set(self.new(t))), ({s.pk}, set()))
        report, failed = self.report()
        self.assertTrue(failed)
        self.assertEqual(report['unexplained'], 1)
        s.grade = 10
        s.save()
        ensure_current_enrollment(s)
        report, failed = self.report()
        self.assertFalse(failed)
        self.assertEqual(report['unexplained'], 0)

    def test_command_writes_nothing(self):
        self.student(self.c10a)
        self.lead('lw', 10, '1404-1405')
        before = (Student.objects.count(), Enrollment.objects.count(), GradeLeadAssignment.objects.count())
        self.report()
        self.assertEqual(before, (Student.objects.count(), Enrollment.objects.count(), GradeLeadAssignment.objects.count()))

    def test_empty_database(self):
        report, failed = self.report()
        self.assertFalse(failed)
        self.assertEqual(report['users_compared'], 0)


class NoSwitchYetTests(Base):
    def test_production_rule_is_still_the_legacy_rule(self):
        """4b changes no access. REMOVE/REPLACE this test in the 4c switch commit (it asserts the pre-switch state)."""
        self.student(self.c10a)
        users = [self.lead('l', 10, '1404-1405'), self.teacher('t', self.c10a), self.lead('lv', 10, '1404')]
        for u in users:
            self.assertEqual(ids(access.visible_students(u)), self.legacy(u), u.username)

    def test_legacy_copy_is_verbatim_until_the_switch(self):
        for name in ('_grade_lead_q', '_teacher_assignments', '_full_tier_q', 'visible_students'):
            self.assertEqual(inspect.getsource(getattr(access, name)), inspect.getsource(getattr(access_legacy, name)), name)


class SeededParityTests(TestCase):
    """The multi-year SYNTHETIC seed after the backfill: parity except the one student the sync refuses."""

    def setUp(self):
        call_command('seed_temporal_synthetic', '--i-know-this-is-synthetic', stdout=StringIO())
        call_command('backfill_enrollments', '--apply', stdout=StringIO())
        school = School.objects.get(code='synthetic-temporal')
        for grade in (9, 10, 11, 12):
            u = make_user(f'lead{grade}', GRADE_LEAD)
            GradeLeadAssignment.objects.create(user=u, school=school, grade=grade, academic_year='1404')  # class spelling
        for klass in SchoolClass.objects.filter(school=school, academic_year='1404', title__in=['9-A', '10-A', '11-A', '12-A']):
            u = make_user(f'teacher_{klass.title}', TEACHER)
            TeacherAssignment.objects.create(teacher=u, school_class=klass, subject='math')
        self.parent = make_user('seed_parent', PARENT)
        Student.objects.filter(first_name='Cohort0').update(parent_user=self.parent)

    def run_report(self):
        out = StringIO()
        try:
            call_command('compare_access_parity', '--json', stdout=out)
            failed = False
        except CommandError:
            failed = True
        return json.loads(out.getvalue()), failed

    def test_only_the_conflict_student_is_flagged_and_fixing_it_gives_zero(self):
        report, failed = self.run_report()
        self.assertTrue(failed)
        # GradeConflict0 (class grade 10, student grade 11, not enrolled) is seen by two users: lead11 and teacher_10-A
        self.assertEqual(report['unexplained'], 2)
        self.assertGreater(report['students_in_both'], 20)
        s = Student.objects.get(first_name='GradeConflict0')
        s.grade = 10
        s.save()
        ensure_current_enrollment(s)
        report, failed = self.run_report()
        self.assertFalse(failed, report)
        self.assertEqual((report['students_only_legacy'], report['students_only_new'], report['tier_differences']), (0, 0, 0))
