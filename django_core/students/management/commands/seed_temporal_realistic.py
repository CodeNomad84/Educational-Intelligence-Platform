"""REALISTIC-SIZE SYNTHETIC multi-year seed for loading tests of the temporal tools (ADR-0011).

    manage.py seed_temporal_realistic --i-know-this-is-synthetic [--scale 1.0]

About 240 students over three academic years (1402-1403, 1403-1404, current 1404-1405): cohorts that are promoted
year by year, retained / transferred-out / withdrawn students, yearly intakes and transfers-in, graduates, parents,
Grade Leads and Teachers, grades and attendance for every student-year, and DELIBERATE DIRTY DATA that the tools must
surface (never silently fix): class spelling variants of the same year, classes whose year text does not resolve,
class-grade conflicts, students without a class, students whose mirror still points to a past-year class, Grade
Lead assignments spelled differently from the class years, teacher assignments with a blank subject.
Past-year enrollments are created (``source='import'``, closed); CURRENT-year enrollments are NOT created, so that
``backfill_enrollments`` has real work. Deterministic (fixed random seed, no ``today``). Refuses to run unless the
student table is empty, so it can never be mixed into real data. Names and ids are synthetic.
"""
import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, TeacherAssignment
from students.models import Attendance, Enrollment, Grade, Student

YEARS = [
    ('1402-1403', date(2023, 9, 23), date(2024, 6, 21), ['1402-1403', '۱۴۰۲-۱۴۰۳', '1402']),
    ('1403-1404', date(2024, 9, 23), date(2025, 6, 21), ['1403-1404', '1403/1404', '۱۴۰۳']),
    ('1404-1405', date(2025, 9, 23), date(2026, 6, 21), ['1404-1405', '۱۴۰۴-۱۴۰۵', '1404', '1404/1405']),
]
SUBJECTS = ['math', 'physics', 'literature']
SUBJECT_POOL = ['math', 'physics', 'chemistry', 'biology', 'literature', 'english', 'arabic', 'history']


class Command(BaseCommand):
    help = "Seed a realistic-size multi-year SYNTHETIC dataset into an EMPTY database (refuses otherwise)."

    def add_arguments(self, parser):
        parser.add_argument('--i-know-this-is-synthetic', action='store_true', dest='confirmed')
        parser.add_argument('--scale', type=float, default=1.0, help='cohort size multiplier (tests use a small value)')

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts['confirmed']:
            raise CommandError('Pass --i-know-this-is-synthetic to confirm.')
        if Student.objects.exists():
            raise CommandError('Refusing: the student table is not empty (synthetic data is never mixed with real data).')
        rng = random.Random(20261016)
        cohort = max(2, round(28 * opts['scale']))
        school = School.objects.create(name='Synthetic Large School', code='synthetic-large')
        years = {}
        for code, start, end, _v in YEARS:
            years[code] = AcademicYear.objects.create(
                school=school, code=code, start_date=start, end_date=end, is_current=(code == '1404-1405'))
        current = '1404-1405'

        classes = {}  # (code, grade, section) -> SchoolClass
        for code, _s, _e, variants in YEARS:
            for grade in range(7, 13):
                for section in 'AB':
                    classes[(code, grade, section)] = SchoolClass.objects.create(
                        school=school, title=f'{grade}-{section}', academic_year=rng.choice(variants), grade=grade,
                        is_active=(code == current))
        bad_classes = [
            SchoolClass.objects.create(school=school, title=f'X-{i}', academic_year=text, grade=None, is_active=True)
            for i, text in enumerate(['404', '۱۴۰', 'سال جاری'], start=1)
        ]

        # ---- life of every student: list of (year_code, grade, status) ----
        students = []   # dicts: {idx, path: [(code, grade, section, status)], intake}
        counter = {'n': 0}

        def new_student(code, grade, status='active'):
            counter['n'] += 1
            s = {'idx': counter['n'], 'path': [], 'start': code}
            s['pending'] = (code, grade, status)
            students.append(s)
            return s

        for grade in range(7, 13):
            for _ in range(cohort):
                new_student(YEARS[0][0], grade)
        for yi, (code, _s, _e, _v) in enumerate(YEARS):
            if yi > 0:
                for _ in range(cohort):
                    new_student(code, 7)                                    # yearly intake
                for _ in range(max(1, cohort // 5)):
                    new_student(code, rng.randint(8, 11), 'transferred_in')  # transfers in
            for s in students:
                if s.get('pending') is None or s['pending'][0] != code:
                    continue
                _c, grade, status = s.pop('pending')
                section = rng.choice('AB')
                if code == current:
                    s['path'].append((code, grade, section, 'active'))
                    continue
                r = rng.random()
                if grade == 12:
                    outcome = 'graduated'
                elif r < 0.03:
                    outcome = 'retained'
                elif r < 0.06:
                    outcome = 'transferred_out'
                elif r < 0.09:
                    outcome = 'withdrawn'
                else:
                    outcome = 'promoted'
                s['path'].append((code, grade, section, outcome))
                nxt = YEARS[yi + 1][0]
                if outcome == 'promoted':
                    s['pending'] = (nxt, grade + 1, 'active')
                elif outcome == 'retained':
                    s['pending'] = (nxt, grade, 'active')

        # ---- Student rows: the mirror is the LAST known state ----
        active_now = [s for s in students if s['path'][-1][0] == current]
        rng.shuffle(active_now)
        dirty = {'conflict': active_now[:6], 'no_class': active_now[6:11], 'bad_year_class': active_now[11:17],
                 'past_year_mirror': active_now[17:25]}
        rows = []
        for s in students:
            code, grade, section, status = s['path'][-1]
            klass = classes[(code, grade, section)]
            if s in dirty['conflict']:
                klass = classes[(code, grade + 1 if grade < 12 else grade - 1, section)]
            elif s in dirty['no_class']:
                klass = None
            elif s in dirty['bad_year_class']:
                klass = bad_classes[s['idx'] % 3]
            elif s in dirty['past_year_mirror'] and len(s['path']) > 1:
                pc, pg, ps, _st = s['path'][-2]
                klass = classes[(pc, pg, ps)]
            s['mirror_class'] = klass
            rows.append(Student(
                first_name=f"Syn{s['idx']:03d}", last_name='Student', national_id=f"98{s['idx']:08d}", grade=grade,
                phone_number=f"090000{s['idx']:05d}", school=klass.school if klass else school,
                school_class=klass, class_name=klass.title if klass else ''))
        Student.objects.bulk_create(rows)
        by_idx = {int(st.national_id[2:]): st for st in Student.objects.all()}

        # ---- past-year enrollments (closed, source import); the CURRENT year is left to the backfill ----
        enrollments = []
        for s in students:
            for code, grade, section, status in s['path']:
                if code == current:
                    continue
                y = years[code]
                enrollments.append(Enrollment(
                    student=by_idx[s['idx']], academic_year=y, school_class=classes[(code, grade, section)], grade=grade,
                    status=status, source='import', started_on=y.start_date, ended_on=y.end_date))
        Enrollment.objects.bulk_create(enrollments)

        # ---- grades and attendance for every student-year ----
        grade_rows, att_rows = [], []
        for s in students:
            st = by_idx[s['idx']]
            for code, grade, _sec, _status in s['path']:
                y = years[code]
                base = rng.randint(10, 17)
                for k, subject in enumerate(SUBJECTS):
                    for m, offset in enumerate((45, 120, 200)):
                        grade_rows.append(Grade(student=st, subject=subject, exam_type=('midterm', 'quiz', 'final')[m],
                                                score=max(0, min(20, base + rng.randint(-3, 3))), date=y.start_date + timedelta(days=offset + k)))
                for d in range(10, 240, 9):
                    att_rows.append(Attendance(student=st, date=y.start_date + timedelta(days=d),
                                               status=rng.choices(['present', 'absent', 'late', 'sick'], [88, 5, 5, 2])[0]))
        Grade.objects.bulk_create(grade_rows, batch_size=2000)
        Attendance.objects.bulk_create(att_rows, batch_size=2000)

        # ---- users and assignments ----
        User = get_user_model()

        def user(name, group):
            u = User.objects.create_user(username=name)
            u.set_unusable_password()
            u.save()
            u.groups.add(Group.objects.get_or_create(name=group)[0])
            return u

        spelled = {7: '1404', 8: '۱۴۰۴-۱۴۰۵', 9: '1404/1405', 10: '1404-1405', 11: '1404', 12: '۱۴۰۴'}
        for grade, text in spelled.items():
            GradeLeadAssignment.objects.create(user=user(f'syn_lead{grade}', 'GradeLead'), school=school, grade=grade,
                                               academic_year=text)
        n_teachers = 0
        for (code, grade, section), klass in classes.items():
            if code != current:
                continue
            n_teachers += 1
            TeacherAssignment.objects.create(teacher=user(f'syn_teacher_{grade}{section}', 'Teacher'), school_class=klass,
                                             subject=SUBJECT_POOL[n_teachers % len(SUBJECT_POOL)])
        blank_user = user('syn_teacher_blank', 'Teacher')
        TeacherAssignment.objects.create(teacher=blank_user, school_class=classes[(current, 8, 'A')], subject='')
        parents = [user(f'syn_parent{i}', 'Parent') for i in range(20)]
        for p, s in zip(parents, [x for x in active_now if x not in dirty['no_class']][:20]):
            Student.objects.filter(pk=by_idx[s['idx']].pk).update(parent_user=p)

        self.stdout.write(self.style.SUCCESS(
            f"synthetic-large: students={Student.objects.count()} classes={SchoolClass.objects.count()} "
            f"enrollments={Enrollment.objects.count()} grades={Grade.objects.count()} attendance={Attendance.objects.count()} "
            f"| dirty: class_grade_conflict={len(dirty['conflict'])} no_class={len(dirty['no_class'])} "
            f"unresolved_class_year={len(dirty['bad_year_class'])} past_year_mirror={len(dirty['past_year_mirror'])}"))
