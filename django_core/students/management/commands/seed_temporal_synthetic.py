"""SYNTHETIC multi-year seed to exercise the temporal model and ``backfill_enrollments`` (ADR-0011).

    manage.py seed_temporal_synthetic --i-know-this-is-synthetic

Creates one school ``synthetic-temporal`` with three academic years (the current one and two past ones, year
spelling variants on the class rows), cohorts that were promoted year by year, a graduate, a transfer, and
deliberate noise (student without class, unresolved/unknown class years, a stale link to a past-year class, a
class-grade conflict). Past-year enrollments are created with ``source='import'`` as a stand-in for the future
historical import. Names and ids are synthetic. The command REFUSES to run unless the student table is empty, so
it can never be mixed into real data. Dates use a fixed calendar (no ``today``), so runs are reproducible.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools.models import AcademicYear, School, SchoolClass
from students.models import Attendance, Enrollment, Grade, Student

YEARS = [  # code, start, end, spelling used on its class rows
    ('1402-1403', date(2023, 9, 23), date(2024, 6, 21), '۱۴۰۲-۱۴۰۳'),
    ('1403-1404', date(2024, 9, 23), date(2025, 6, 21), '1403/1404'),
    ('1404-1405', date(2025, 9, 23), date(2026, 6, 21), '1404'),
]
SUBJECTS = ['math', 'physics', 'literature']


class Command(BaseCommand):
    help = "Seed a multi-year SYNTHETIC dataset into an EMPTY database (refuses otherwise)."

    def add_arguments(self, parser):
        parser.add_argument('--i-know-this-is-synthetic', action='store_true', dest='confirmed')

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts['confirmed']:
            raise CommandError('Pass --i-know-this-is-synthetic to confirm.')
        if Student.objects.exists():
            raise CommandError('Refusing: the student table is not empty (synthetic data is never mixed with real data).')
        school, _ = School.objects.get_or_create(code='synthetic-temporal', defaults={'name': 'Synthetic School'})
        year_rows = {}
        for code, start, end, _spelling in YEARS:
            year_rows[code] = AcademicYear.objects.create(
                school=school, code=code, start_date=start, end_date=end, is_current=(code == '1404-1405'))
        spelling = {code: sp for code, _s, _e, sp in YEARS}

        def klass(code, grade, suffix, year_text=None, class_grade='same'):
            return SchoolClass.objects.create(
                school=school, title=f'{grade}-{suffix}', academic_year=year_text if year_text is not None else spelling[code],
                grade=grade if class_grade == 'same' else class_grade, is_active=(code == '1404-1405'))

        # classes per year: grade 8..11 in 1402-1403, 9..12 in 1403-1404 and 1404-1405 (cohort moves up)
        classes = {}
        for code, grades in (('1402-1403', (7, 8, 9, 10, 11, 12)), ('1403-1404', (8, 9, 10, 11, 12)),
                             ('1404-1405', (9, 10, 11, 12))):
            for g in grades:
                classes[(code, g)] = klass(code, g, 'A')
        counter = {'n': 0}

        def student(first, grade, cls, in_school=True):
            counter['n'] += 1
            return Student.objects.create(
                first_name=first, last_name='Synthetic', national_id=f"99{counter['n']:08d}", grade=grade,
                phone_number='0000000000', school=school if in_school else None, school_class=cls)

        def enroll(st, code, grade, cls, status, source='import'):
            return Enrollment.objects.create(
                student=st, academic_year=year_rows[code], school_class=cls, grade=grade, status=status, source=source)

        def activity(st, code, base):
            start = year_rows[code].start_date
            for k, subject in enumerate(SUBJECTS):
                for m in range(3):
                    Grade.objects.create(student=st, subject=subject, exam_type='quiz', score=min(20, base + k + m),
                                         date=start + timedelta(days=40 + 60 * m + k))
            for d in range(0, 120, 7):
                Attendance.objects.create(student=st, date=start + timedelta(days=d), status='absent' if d % 35 == 0 else 'present')

        # cohorts promoted year by year: in 1404-1405 they are grade 10 (came from 8 -> 9 -> 10)
        for i in range(6):
            st = student(f'Cohort{i}', 10, classes[('1404-1405', 10)])
            for code, g in (('1402-1403', 8), ('1403-1404', 9)):
                enroll(st, code, g, classes[(code, g)], 'promoted')
                activity(st, code, 10 + i % 4)
            activity(st, '1404-1405', 11 + i % 4)  # current year: enrollment comes from the backfill
        for i in range(4):  # grade 11 now
            st = student(f'Senior{i}', 11, classes[('1404-1405', 11)])
            for code, g in (('1402-1403', 9), ('1403-1404', 10)):
                enroll(st, code, g, classes[(code, g)], 'promoted')
                activity(st, code, 12)
            activity(st, '1404-1405', 12)
        # a graduate: finished grade 12 in 1403-1404 (record stays, not in the current year)
        grad = student('Graduate0', 12, classes[('1403-1404', 12)])
        enroll(grad, '1402-1403', 11, classes[('1402-1403', 11)], 'promoted')
        enroll(grad, '1403-1404', 12, classes[('1403-1404', 12)], 'graduated')
        activity(grad, '1402-1403', 13)
        activity(grad, '1403-1404', 14)
        # a transfer-in during the current year with only current activity
        activity(student('Transfer0', 9, classes[('1404-1405', 9)]), '1404-1405', 9)

        # --- deliberate noise (everything below must be skipped, never guessed) ---
        # NoClass0 is the ONE deliberately school-less synthetic student (a legacy dirty row for the roster/enrollment
        # tests, 'student has no school'); every other student gets the synthetic school. It must go when S6 makes
        # Student.school NOT NULL (changes/0010).
        activity(student('NoClass0', 10, None, in_school=False), '1404-1405', 11)  # no class, no school
        bad = SchoolClass.objects.create(school=school, title='X-bad', academic_year='404', grade=10, is_active=True)
        activity(student('BadYear0', 10, bad), '1404-1405', 11)                         # unresolved year text
        unknown = SchoolClass.objects.create(school=school, title='X-1401', academic_year='1401', grade=10, is_active=True)
        activity(student('NoYearRow0', 10, unknown), '1404-1405', 11)                   # no AcademicYear row
        activity(student('StaleLink0', 9, classes[('1403-1404', 9)]), '1403-1404', 11)  # linked to a past-year class
        activity(student('GradeConflict0', 11, classes[('1404-1405', 10)]), '1404-1405', 11)  # class grade 10, student 11
        # several enrollments in one year (mid-year class change): rows there must stay unlinked
        mid = student('MidYear0', 10, classes[('1404-1405', 10)])
        Enrollment.objects.create(
            student=mid, academic_year=year_rows['1403-1404'], school_class=classes[('1403-1404', 9)], grade=9,
            status='transferred_out', source='import', started_on=date(2024, 9, 23), ended_on=date(2025, 1, 1))
        enroll(mid, '1403-1404', 9, classes[('1403-1404', 9)], 'promoted')
        activity(mid, '1403-1404', 10)

        self.stdout.write(self.style.SUCCESS(
            f'synthetic: students={Student.objects.count()} classes={SchoolClass.objects.count()} '
            f'years={AcademicYear.objects.count()} enrollments={Enrollment.objects.count()} '
            f'grades={Grade.objects.count()} attendance={Attendance.objects.count()}'))
