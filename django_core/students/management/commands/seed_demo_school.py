"""Demo school for presentations to principals: a believable Persian school with ~200 SYNTHETIC students.

    manage.py seed_demo_school --i-know-this-is-synthetic [--password P] [--scale 1.0]

Refuses unless the student table is empty. Names are fictional, national ids are in the 9001xxxxxx range, phone numbers are
fake. Dates are RELATIVE to the day of seeding (the academic year is stamped to start 150 days earlier so the 12-week
attendance trend and the three grade periods of the 360 are filled). Patterns: most students steady; some with a grade
drop, a long absence run, behavior concerns, or strong improvement; alerts and intervention plans are created through the
normal services so the three support levels, review states and plan outcomes all appear. Deterministic (fixed seed).
"""
import random
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from interventions import services as plans
from risk import services as alerts
from risk.models import Alert, RiskEvent
from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass, SchoolMembership, TeacherAssignment
from students.enrollment_sync import ensure_current_enrollment
from students.models import Attendance, BehaviorNote, Grade, Recommendation, Student

YEAR = '1405-1406'
SCHOOL = 'دبیرستان نمونهٔ سپهر'
SUBJECTS = {7: ['math', 'literature', 'english', 'religious', 'social'], 8: ['math', 'literature', 'english', 'arabic', 'social'],
            9: ['math', 'literature', 'english', 'arabic', 'geography'], 10: ['math', 'physics', 'chemistry', 'literature', 'english'],
            11: ['math', 'physics', 'chemistry', 'biology', 'literature'], 12: ['math', 'physics', 'chemistry', 'biology', 'english']}
FIRST = ['علی', 'محمد', 'رضا', 'امیر', 'حسین', 'مهدی', 'سینا', 'آرین', 'پارسا', 'کیان', 'بردیا', 'آرمان', 'یاسین', 'نیما', 'سارا',
         'نیلوفر', 'مهسا', 'الهام', 'زهرا', 'مریم', 'فاطمه', 'ترانه', 'آیدا', 'هستی', 'نگار', 'غزل', 'پریسا', 'کیمیا', 'ملیکا', 'باران']
LAST = ['احمدی', 'رضایی', 'کریمی', 'موسوی', 'حسینی', 'صادقی', 'نوری', 'فرهادی', 'کاظمی', 'جعفری', 'سلیمانی', 'رحیمی', 'باقری',
        'عباسی', 'مرادی', 'نجفی', 'یوسفی', 'شریفی', 'قاسمی', 'اکبری', 'طاهری', 'رستمی', 'حیدری', 'امینی', 'زارعی', 'کیانی',
        'منصوری', 'پناهی', 'ملکی', 'سعیدی']
STAFF = [('مریم', 'کاظمی'), ('حمید', 'نیکخواه'), ('زهرا', 'صالحی'), ('رضا', 'بهرامی'), ('سمیرا', 'دلاوری'), ('امیرحسین', 'توکلی'),
         ('لیلا', 'فرجی'), ('محسن', 'ایزدی'), ('شیدا', 'قنبری'), ('کامران', 'آذر'), ('نرگس', 'مهدوی'), ('بهرام', 'سلطانی'),
         ('فاطمه', 'پورمحمدی'), ('سعید', 'عطایی'), ('ندا', 'شجاعی'), ('وحید', 'رنجبر'), ('مینا', 'کرمی'), ('هادی', 'صفایی')]


class Command(BaseCommand):
    help = 'Seed a synthetic demo school (~200 students) into an EMPTY database.'

    def add_arguments(self, parser):
        parser.add_argument('--i-know-this-is-synthetic', action='store_true', dest='confirmed')
        parser.add_argument('--password', help='password for every demo login (default: random, printed once)')
        parser.add_argument('--scale', type=float, default=1.0)

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts['confirmed']:
            raise CommandError('Pass --i-know-this-is-synthetic to confirm.')
        if Student.objects.exists():
            raise CommandError('Refusing: the student table is not empty.')
        rng = random.Random(14051102)
        password = opts['password'] or secrets.token_urlsafe(9)
        today = timezone.localdate()
        start = today - timedelta(days=150)
        school = School.objects.create(name=SCHOOL, code='sepehr-demo')
        AcademicYear.objects.create(school=school, code=YEAR, label='سال تحصیلی ۱۴۰۵-۱۴۰۶', start_date=start,
                                    end_date=start + timedelta(days=270), is_current=True)
        User = get_user_model()
        staff_names = iter(STAFF * 3)

        def user(username, group):
            first, last = next(staff_names)
            u = User.objects.create_user(username=username, password=password, first_name=first, last_name=last)
            u.groups.add(Group.objects.get_or_create(name=group)[0])
            return u

        admin = user('demo_admin', 'SchoolAdmin')
        SchoolMembership.objects.create(user=admin, school=school)
        leads = {g: user(f'demo_lead{g}', 'GradeLead') for g in SUBJECTS}
        for g, u in leads.items():
            GradeLeadAssignment.objects.create(user=u, school=school, grade=g, academic_year=YEAR)
        counselor = user('demo_counselor', 'Counselor')
        per_class = max(3, round(17 * opts['scale']))
        students, used = [], set()
        for grade in SUBJECTS:
            for section in ('الف', 'ب'):
                klass = SchoolClass.objects.create(school=school, title=f'{grade}-{section}', academic_year=YEAR, grade=grade)
                teacher = user(f'demo_teacher{grade}{"ab"[section == "ب"]}', 'Teacher')
                for subject in SUBJECTS[grade][:2]:
                    TeacherAssignment.objects.create(teacher=teacher, school_class=klass, subject=subject)
                for _ in range(per_class):
                    while True:
                        name = (rng.choice(FIRST), rng.choice(LAST))
                        if name not in used:
                            used.add(name)
                            break
                    n = len(students) + 1
                    s = Student.objects.create(first_name=name[0], last_name=name[1], national_id=f'9001{n:06d}', grade=grade,
                                               phone_number=f'0900000{n:04d}', school=school, school_class=klass)
                    ensure_current_enrollment(s)
                    students.append(s)
        rng.shuffle(students)
        k = len(students)
        groups = {'drop': students[:k // 10], 'absent': students[k // 10:k // 10 + k // 14],
                  'both': students[k // 10 + k // 14:k // 10 + k // 14 + 6], 'strong': students[-k // 12:], 'concern': students[-k // 12 - 12:-k // 12]}
        tag = {s.pk: g for g, members in groups.items() for s in members}
        enrollments = {e.student_id: e for e in __import__('students.models', fromlist=['Enrollment']).Enrollment.objects.all()}

        grade_rows, att_rows = [], []
        offsets = [140, 125, 110, 95, 80, 65, 50, 38, 26, 14, 5]
        for s in students:
            pattern = tag.get(s.pk, 'steady')
            base = min(19, max(7, rng.gauss(14.5, 2.4) + (2.5 if pattern == 'strong' else 0)))
            for si, subject in enumerate(SUBJECTS[s.grade]):
                for oi, off in enumerate(offsets):
                    score = base + rng.gauss(0, 1.1) + (0.8 if pattern == 'strong' and off < 60 else 0)
                    if pattern in ('drop', 'both') and off <= 50 and si < 3:
                        score -= 4.5 + rng.random()
                    grade_rows.append(Grade(student=s, enrollment=enrollments.get(s.pk), subject=subject,
                                            exam_type=('quiz', 'midterm', 'quiz', 'project', 'final')[oi % 5],
                                            score=round(max(2, min(20, score)), 1), date=today - timedelta(days=off + si)))
            p_abs = {'absent': 0.07, 'both': 0.07}.get(pattern, 0.04)
            for d in range(150, 0, -1):
                day = today - timedelta(days=d)
                if day.weekday() in (4,):       # Friday
                    continue
                rate = p_abs + (0.25 if pattern in ('absent', 'both') and d <= 40 else 0)
                status = 'absent' if rng.random() < rate else ('late' if rng.random() < 0.04 else ('sick' if rng.random() < 0.01 else 'present'))
                att_rows.append(Attendance(student=s, date=day, status=status))
        Grade.objects.bulk_create(grade_rows, batch_size=3000)
        Attendance.objects.bulk_create(att_rows, batch_size=3000)

        concerns = ['حواس‌پرتی مکرر در کلاس', 'عدم انجام تکلیف', 'تأخیر در ورود به کلاس', 'اختلال در نظم کلاس']
        praises = ['کمک به هم‌کلاسی', 'مشارکت فعال در بحث کلاسی', 'تلاش چشمگیر در پروژه', 'مسئولیت‌پذیری در کار گروهی']
        for s in students:
            pattern = tag.get(s.pk, 'steady')
            lead = leads[s.grade]
            if pattern in ('concern', 'both'):
                for off in (30, 18, 7):
                    BehaviorNote.objects.create(school=school, student=s, kind='concern', category='conduct', note=rng.choice(concerns),
                                                occurred_on=today - timedelta(days=off), recorded_by=lead)
            if pattern == 'strong' or rng.random() < 0.15:
                BehaviorNote.objects.create(school=school, student=s, kind='positive', category=rng.choice(['kindness', 'effort', 'participation']),
                                            note=rng.choice(praises), occurred_on=today - timedelta(days=rng.randint(3, 60)), recorded_by=lead)
            if pattern in ('drop', 'both'):
                Recommendation.objects.create(student=s, subject='math', author=TeacherAssignment.objects.filter(
                    school_class=s.school_class).first().teacher, text='افت نمره در آزمون‌های اخیر؛ مرور مباحث و جلسهٔ رفع اشکال پیشنهاد می‌شود.',
                    visible_to_student=False)

        # alerts and plans through the normal services (support levels are DERIVED from these)
        due = today + timedelta(days=30)
        n_plans = 0
        for s in groups['drop'] + groups['both']:
            a = alerts.raise_alert(s, risk_type='academic', severity='orange', detected_by=RiskEvent.DetectedBy.ADMIN, raised_by=leads[s.grade],
                                   message='افت محسوس نمرات چند درس در ۵۰ روز اخیر', explanation='میانگین سه درس نسبت به دورهٔ قبل کاهش یافته است.')
            if n_plans < 14 and s in groups['both']:           # level 3: open plan + urgent alert still unreviewed
                alerts.review_alert(leads[s.grade], a, Alert.ACCEPTED); a.refresh_from_db()
                plans.create_plan(leads[s.grade], s, intervention_type='academic', goal='بازگشت میانگین به سطح قبل',
                                  action_plan='کلاس جبرانی کوچک‌گروهی و بازبینی هفتگی نمرات.', start_date=today - timedelta(days=10), due_date=due, alert=a)
                alerts.raise_alert(s, risk_type='attendance', severity='orange', detected_by=RiskEvent.DetectedBy.ADMIN, raised_by=leads[s.grade],
                                   message='افزایش غیبت در ۴۰ روز اخیر', explanation='نرخ غیبت نسبت به دورهٔ قبل بیشتر شده است.')
            elif s in groups['drop'][: len(groups['drop']) // 2]:   # level 2: accepted alert with an open plan
                alerts.review_alert(leads[s.grade], a, Alert.ACCEPTED); a.refresh_from_db()
                p = plans.create_plan(leads[s.grade], s, intervention_type='academic', goal='تقویت درس ریاضی',
                                      action_plan='هم‌یار آموزشی و تمرین هفتگی.', start_date=today - timedelta(days=20), due_date=due, alert=a)
                plans.start_plan(leads[s.grade], p)
                n_plans += 1
        for s in groups['absent']:
            a = alerts.raise_alert(s, risk_type='attendance', severity='yellow', detected_by=RiskEvent.DetectedBy.ADMIN, raised_by=leads[s.grade],
                                   message='غیبت‌های متوالی در یک ماه اخیر', explanation='تعداد غیبت از آستانهٔ معمول بیشتر است.')
            if rng.random() < 0.4:
                alerts.review_alert(leads[s.grade], a, Alert.DISMISSED, reason='other', note='تماس با خانواده؛ بیماری تأیید شد.')
        call_command('seed_strategies', school=school.pk, stdout=open('/dev/null', 'w'))

        # a handful of parent / student accounts for the walk-through
        for i, s in enumerate(students[:6]):
            p = User.objects.create_user(username=f'demo_parent{i + 1}', password=password, first_name='ولی', last_name=s.last_name)
            p.groups.add(Group.objects.get_or_create(name='Parent')[0])
            Student.objects.filter(pk=s.pk).update(parent_user=p)
        st = students[6]
        su = User.objects.create_user(username='demo_student', password=password, first_name=st.first_name, last_name=st.last_name)
        su.groups.add(Group.objects.get_or_create(name='Student')[0])
        Student.objects.filter(pk=st.pk).update(student_user=su)
        self.stdout.write(self.style.SUCCESS(
            f'{SCHOOL}: students={len(students)} grades={len(grade_rows)} attendance={len(att_rows)} alerts={Alert.objects.count()} '
            f'plans={plans.InterventionPlan.objects.count()}'))
        self.stdout.write(f'logins: demo_admin, demo_lead7..12, demo_teacher7a.., demo_counselor, demo_parent1..6, demo_student | password: {password}')
