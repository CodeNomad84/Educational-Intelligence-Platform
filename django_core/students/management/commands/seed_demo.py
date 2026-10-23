# DEMO SCOPE — whole file. Synthetic data for the school-meeting demo. Safe to delete with the demo_intel app.
"""Seed the SEPARATE demo database with fully synthetic students.

    DJANGO_SETTINGS_MODULE=config.settings.demo python manage.py migrate
    DJANGO_SETTINGS_MODULE=config.settings.demo python manage.py seed_demo [--reset] [--password ...]

Safety: refuses to run unless the demo settings are active AND the database file is demo_db.sqlite3.
All names, national ids (9000000xxx range) and phone numbers are fictional.
"""
import random
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from students.access import ADMIN
from students.enrollment_sync import ensure_current_enrollment
from students.models import Attendance, Grade, Student

SUBJECTS = ["math", "physics", "chemistry", "literature", "english", "arabic"]
EXAM_OFFSETS = [115, 100, 85, 70, 55, 40, 25, 10]  # days ago; 40/25/10 fall in the "recent" window
CLASSES = [(9, "۹-الف"), (9, "۹-ب"), (10, "۱۰-الف"), (10, "۱۰-ب"), (11, "۱۱-الف")]

FIRST = ["علی", "محمد", "رضا", "امیر", "حسین", "مهدی", "سینا", "آرین", "پارسا", "کیان", "بردیا", "آرمان",
         "یاسین", "نیما", "سارا", "نیلوفر", "مهسا", "الهام", "زهرا", "مریم", "فاطمه", "ترانه", "آیدا", "هستی",
         "نگار", "غزل", "پریسا", "کیمیا", "ملیکا", "باران"]
LAST = ["احمدی", "رضایی", "کریمی", "موسوی", "حسینی", "صادقی", "نوری", "فرهادی", "کاظمی", "جعفری", "سلیمانی",
        "رحیمی", "باقری", "عباسی", "مرادی", "نجفی", "یوسفی", "شریفی", "قاسمی", "اکبری", "طاهری", "رستمی",
        "حیدری", "امینی", "زارعی", "کیانی", "منصوری", "پناهی", "ملکی", "سعیدی"]

# Scripted storylines (each one is a talking point for the demo). Offsets are "days ago".
STORIES = [
    dict(key="attendance_ali", first="علی", last="احمدی", grade=10, cls="۱۰-الف",
         base=15.5, recent_subject={"math": -4.5}, recent_delta=-0.5, abs_earlier=0.04, abs_recent=0.20,
         late_recent=2,
         obs=[(70, "positive", "positive", "مشارکت فعال در کلاس ریاضی"),
              (24, "participation", "negative", "کاهش مشارکت در بحث کلاسی"),
              (12, "participation", "negative", "سکوت و عدم پاسخ‌گویی در کلاس")],
         interventions=[], counseling=[]),
    dict(key="attendance_decline", first="نیلوفر", last="موسوی", grade=9, cls="۹-ب",
         base=15.0, recent_delta=-0.7, abs_earlier=0.03, abs_recent=0.30, late_recent=6,
         obs=[(20, "social", "negative", "انزوا در زنگ تفریح")], interventions=[], counseling=[]),
    dict(key="grade_deterioration", first="پارسا", last="نوری", grade=11, cls="۱۱-الف",
         base=14.5, recent_subject={"math": -7.0, "physics": -6.0}, recent_delta=-3.0,
         abs_earlier=0.02, abs_recent=0.05,
         obs=[(22, "academic", "negative", "عدم انجام تکالیف"), (9, "academic", "negative", "نمرهٔ کوییز بسیار پایین")],
         interventions=[], counseling=[]),
    dict(key="behavior_warning", first="آرمان", last="رحیمی", grade=9, cls="۹-الف",
         base=14.0, recent_delta=-0.3, abs_earlier=0.05, abs_recent=0.08, late_recent=6,
         obs=[(26, "discipline", "negative", "درگیری لفظی با هم‌کلاسی"),
              (21, "discipline", "negative", "اخلال در نظم کلاس"),
              (15, "social", "negative", "تعارض با گروه دوستان"),
              (8, "discipline", "negative", "خروج بدون اجازه از کلاس"),
              (3, "discipline", "negative", "بی‌توجهی به تذکر معلم")],
         interventions=[], counseling=[]),
    dict(key="improving_after_intervention", first="مهسا", last="فرهادی", grade=10, cls="۱۰-ب",
         base=11.5, recent_delta=3.8, abs_earlier=0.22, abs_recent=0.05,
         obs=[(40, "discipline", "negative", "غیبت‌های مکرر و بی‌انگیزگی"),
              (14, "positive", "positive", "مشارکت بهتر در کلاس"),
              (6, "positive", "positive", "تحویل به‌موقع تکالیف")],
         interventions=[(50, "counselor_meeting", "active", "جلسات هفتگی مشاوره", ""),
                        (50, "attendance_plan", "active", "برنامهٔ پیگیری حضور با خانواده", "")],
         counseling=[(50, "جلسهٔ اول: بررسی علت غیبت‌ها و تعیین هدف‌های کوتاه‌مدت (داده نمایشی)"),
                     (30, "جلسهٔ پیگیری: بهبود حضور؛ ادامهٔ برنامه (داده نمایشی)")]),
    dict(key="stable_low_risk", first="کیان", last="صادقی", grade=10, cls="۱۰-ب",
         base=15.0, recent_delta=0.0, abs_earlier=0.03, abs_recent=0.03, obs=[], interventions=[], counseling=[]),
    dict(key="high_performer", first="آرین", last="جعفری", grade=11, cls="۱۱-الف",
         base=18.3, recent_delta=0.3, abs_earlier=0.01, abs_recent=0.01,
         obs=[(30, "positive", "positive", "ارائهٔ عالی در کلاس"), (18, "positive", "positive", "کمک به هم‌کلاسی‌ها"),
              (5, "positive", "positive", "برنده مسابقهٔ علمی مدرسه")],
         interventions=[], counseling=[]),
    dict(key="multi_factor_high_1", first="رضا", last="کاظمی", grade=9, cls="۹-ب",
         base=14.5, recent_subject={"math": -5.0}, recent_delta=-2.0, abs_earlier=0.06, abs_recent=0.28,
         obs=[(27, "participation", "negative", "کاهش مشارکت"), (19, "discipline", "negative", "غیبت از کلاس بدون اطلاع"),
              (11, "social", "negative", "تعارض با دوستان"), (4, "discipline", "negative", "بی‌توجهی به تذکر")],
         interventions=[(3, "parent_contact", "planned", "جلسه با والدین برنامه‌ریزی شد", "")],
         counseling=[(6, "ارجاع اولیه به مشاور پس از گزارش معلمان (داده نمایشی)")]),
    dict(key="multi_factor_high_2", first="سینا", last="باقری", grade=11, cls="۱۱-الف",
         base=13.0, recent_subject={"physics": -3.5}, recent_delta=-3.5, abs_earlier=0.05, abs_recent=0.25,
         obs=[(20, "academic", "negative", "افت محسوس تمرکز"), (7, "participation", "negative", "عدم ارائهٔ تکلیف")],
         interventions=[], counseling=[]),
]

CONCERN_FILLERS = 3  # fillers with an emerging-concern pattern (Medium)
OBS_NEUTRAL = ["مشارکت متوسط در کلاس", "رفتار عادی", "تکالیف به‌موقع"]


class Command(BaseCommand):
    help = "Seed the separate demo database with synthetic students (DEMO SCOPE)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")
        parser.add_argument("--password", default=None, help="Password for the demo users (default: random).")
        parser.add_argument("--school", default=None, help="Code of the School the demo students belong to "
                            "(required when more than one School exists; with exactly one it is used).")

    # ---------------------------------------------------------------------------------------------
    def handle(self, *args, **opts):
        self._guard()
        school = self._school(opts["school"])  # validated BEFORE anything is deleted (--reset)
        from demo_intel.engine import analyze_students
        from demo_intel.models import CounselingNote, InterventionRecord, StudentObservation

        self.rng = random.Random(20261013)  # fixed => repeatable demo
        self.today = timezone.localdate()
        self.school_days = [self.today - timedelta(days=d) for d in range(120, -1, -1)
                            if (self.today - timedelta(days=d)).weekday() not in (3, 4)]

        if opts["reset"]:
            self._reset()
        elif Student.objects.exists():
            raise CommandError("Demo DB already has students. Use --reset to rebuild it.")

        with transaction.atomic():
            profiles = self._build_profiles()
            year, classes = self._structure(school)
            students = []
            for idx, p in enumerate(profiles, start=1):
                s = Student.objects.create(
                    first_name=p["first"], last_name=p["last"], national_id=f"9000{idx:06d}",
                    grade=p["grade"], class_name=p["cls"], phone_number=f"0900000{idx:04d}", school=school,
                    school_class=classes[p["cls"]])
                ensure_current_enrollment(s, source="manual")
                students.append((s, p))
                self._attendance(s, p)
                self._grades(s, p)
                for days_ago, cat, sent, note in p.get("obs", []):
                    StudentObservation.objects.create(
                        student=s, date=self.today - timedelta(days=days_ago), category=cat, sentiment=sent, note=note)
                for days_ago, kind, status, desc, outcome in p.get("interventions", []):
                    InterventionRecord.objects.create(
                        student=s, kind=kind, status=status, description=desc, outcome=outcome,
                        start_date=self.today - timedelta(days=days_ago))
                for days_ago, summary in p.get("counseling", []):
                    CounselingNote.objects.create(
                        student=s, date=self.today - timedelta(days=days_ago),
                        counselor_name="مشاور نمایشی", summary=summary)
            password = opts["password"] or secrets.token_urlsafe(9)
            self._users(password, students, school, year, classes)

        results = analyze_students(Student.objects.all(), self.today)
        dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for r in results.values():
            dist[r["level"]] += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(students)} synthetic students. Risk distribution: {dist}"))
        self.stdout.write("Demo users (all synthetic):  demo_admin / demo_counselor / demo_parent / demo_teacher / demo_gradelead")
        self.stdout.write(self.style.WARNING(f"Password: {password}"))

    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def _school(code):
        """S2b: every demo student gets an explicit school; no hidden default when several Schools exist."""
        from schools.models import School
        if code is not None:  # "" is a mistake (e.g. an empty shell variable), never "not given"
            try:
                return School.objects.get(code=code)
            except School.DoesNotExist:
                raise CommandError(f"No School with code '{code}'.")
        schools = list(School.objects.all()[:2])
        if len(schools) == 1:
            return schools[0]
        raise CommandError("Pass --school <code>: " + ("no School exists." if not schools else "several Schools exist."))

    def _guard(self):
        if not getattr(settings, "DEMO_MODE", False):
            raise CommandError("DEMO_MODE is off. Run with DJANGO_SETTINGS_MODULE=config.settings.demo.")
        name = Path(str(settings.DATABASES["default"]["NAME"])).name
        if name != getattr(settings, "DEMO_DB_FILENAME", "demo_db.sqlite3"):
            raise CommandError(f"Refusing to seed database '{name}': only demo_db.sqlite3 is allowed.")

    def _reset(self):
        from demo_intel.models import CounselingNote, InterventionRecord, StudentObservation
        from students.models import Enrollment
        for model in (StudentObservation, CounselingNote, InterventionRecord, Attendance, Grade, Enrollment, Student):
            model.objects.all().delete()
        get_user_model().objects.filter(username__startswith="demo_").delete()

    def _build_profiles(self):
        profiles = [dict(p) for p in STORIES]
        used = {(p["first"], p["last"]) for p in profiles}
        hero_first = {p["first"] for p in profiles}  # reserved so each hero identity stays unique and memorable
        hero_last = {p["last"] for p in profiles}
        first_pool = [n for n in FIRST if n not in hero_first]
        last_pool = [n for n in LAST if n not in hero_last]
        slots = []
        counts = {c: 0 for _, c in CLASSES}
        for p in profiles:
            counts[p["cls"]] += 1
        while len(profiles) + len(slots) < 40:
            grade, cls = min(CLASSES, key=lambda gc: counts[gc[1]])
            counts[cls] += 1
            slots.append((grade, cls))
        # Exactly CONCERN_FILLERS fillers get an "emerging concern" pattern (-> Medium); every other filler is
        # bounded so it can never reach Medium. This keeps the distribution at 2 High / 7 Medium / 31 Low.
        concern_idx = set(self.rng.sample(range(len(slots)), CONCERN_FILLERS))
        for i, (grade, cls) in enumerate(slots):
            while True:
                first, last = self.rng.choice(first_pool), self.rng.choice(last_pool)
                if (first, last) not in used:
                    used.add((first, last))
                    break
            base = min(19.0, max(13.3, self.rng.gauss(14.8, 1.6)))
            drift = self.rng.uniform(-0.8, 0.5)
            p = dict(first=first, last=last, grade=grade, cls=cls, base=base, recent_delta=drift,
                     abs_earlier=min(0.05, max(0.0, self.rng.gauss(0.03, 0.015))), obs=[],
                     interventions=[], counseling=[])
            p["abs_recent"] = p["abs_earlier"]
            p["late_recent"] = 0 if i not in concern_idx else 1
            if i in concern_idx:  # emerging concern: rising absence + two negative observations (-> Medium)
                p["abs_earlier"], p["abs_recent"] = 0.03, 0.20
                p["obs"] += [(self.rng.randint(4, 12), "participation", "negative", "کاهش تمرکز و مشارکت"),
                             (self.rng.randint(13, 26), "social", "negative", "کم‌حرفی و فاصله از هم‌کلاسی‌ها")]
            if self.rng.random() < 0.5:
                p["obs"].append((self.rng.randint(5, 60), "participation", "neutral", self.rng.choice(OBS_NEUTRAL)))
            if self.rng.random() < 0.2:
                p["obs"].append((self.rng.randint(5, 25), "positive", "positive", "تلاش و پیشرفت قابل‌توجه"))
            if self.rng.random() < 0.1:
                p["obs"].append((self.rng.randint(5, 25), "discipline", "negative", "تذکر انضباطی جزئی"))
            profiles.append(p)
        return profiles

    def _attendance(self, student, p):
        recent_start = self.today - timedelta(days=30)
        windows = {
            "earlier": ([d for d in self.school_days if d <= recent_start], p.get("abs_earlier", 0.03)),
            "recent": ([d for d in self.school_days if d > recent_start], p.get("abs_recent", 0.03)),
        }
        for name, (days, rate) in windows.items():
            shuffled = days[:]
            self.rng.shuffle(shuffled)
            n_abs = round(rate * len(days))
            n_late = p.get("late_recent", 1 if self.rng.random() < 0.3 else 0) if name == "recent" else \
                (1 if self.rng.random() < 0.4 else 0)
            absent, late, sick = shuffled[:n_abs], shuffled[n_abs:n_abs + n_late], \
                shuffled[n_abs + n_late:n_abs + n_late + (1 if self.rng.random() < 0.3 else 0)]
            labels = {d: "absent" for d in absent}
            labels.update({d: "late" for d in late})
            labels.update({d: "sick" for d in sick})
            Attendance.objects.bulk_create(
                Attendance(student=student, date=d, status=labels.get(d, "present")) for d in days)

    def _grades(self, student, p):
        recent_cut = self.today - timedelta(days=45)
        subject_bias = {s: self.rng.gauss(0, 0.9) for s in SUBJECTS}
        rows = []
        for offset in EXAM_OFFSETS:
            date = self.today - timedelta(days=offset)
            recent = date > recent_cut
            for subj in SUBJECTS:
                mean = p["base"] + subject_bias[subj]
                if recent:
                    mean += p.get("recent_delta", 0.0) + p.get("recent_subject", {}).get(subj, 0.0)
                score = round(min(20.0, max(0.0, self.rng.gauss(mean, 0.7))), 1)
                rows.append(Grade(student=student, subject=subj, score=score, date=date,
                                  exam_type="midterm" if EXAM_OFFSETS.index(offset) % 3 == 0 else "quiz"))
        Grade.objects.bulk_create(rows)

    def _structure(self, school):
        """Slice 1: a current academic year and the classes of the demo, so the SchoolAdmin pages have something to show."""
        from datetime import date

        from schools.models import AcademicYear, SchoolClass
        first = self.today.year - 621 if (self.today.month, self.today.day) >= (9, 23) else self.today.year - 622
        code = f"{first}-{first + 1}"
        AcademicYear.objects.filter(school=school, is_current=True).exclude(code=code).update(is_current=False)
        year, _ = AcademicYear.objects.get_or_create(school=school, code=code, defaults=dict(
            start_date=date(first + 621, 9, 23), end_date=date(first + 622, 6, 21), is_current=True))
        if not year.is_current:
            AcademicYear.objects.filter(pk=year.pk).update(is_current=True)
        classes = {title: SchoolClass.objects.get_or_create(
            school=school, academic_year=code, title=title, defaults=dict(grade=grade))[0] for grade, title in CLASSES}
        return year, classes

    def _users(self, password, students, school, year, classes):
        User = get_user_model()
        from schools.models import SchoolMembership
        admin_g, _ = Group.objects.get_or_create(name=ADMIN)
        parent_g, _ = Group.objects.get_or_create(name="Parent")
        for username, first, last, group in [
            ("demo_admin", "مدیر", "نمایشی", admin_g),
            ("demo_parent", "ولی", "نمایشی", parent_g),
        ]:
            user, _ = User.objects.get_or_create(username=username, defaults=dict(first_name=first, last_name=last))
            user.set_password(password)
            user.save()
            user.groups.set([group])
            if group is admin_g:   # S3: a SchoolAdmin reads exactly the schools of its memberships
                SchoolMembership.objects.update_or_create(user=user, school=school, defaults={"is_active": True})
            if username == "demo_parent":
                child = next(s for s, p in students if p.get("key") == "improving_after_intervention")
                child.parent_user = user
                child.save(update_fields=["parent_user"])

        self._staff(password, school, year, classes, students)

    def _staff(self, password, school, year, classes, students):
        """Slice 1: a demo Subject Teacher (math in two classes) and a demo Grade Lead (grade 10), school staff accounts."""
        from schools.models import GradeLeadAssignment, SchoolStaff, TeacherAssignment
        User = get_user_model()
        for username, first, last, group in (("demo_teacher", "معلم", "نمایشی", "Teacher"),
                                             ("demo_gradelead", "مربی", "نمایشی", "GradeLead"),
                                             ("demo_counselor", "مشاور", "نمایشی", "Counselor")):
            user, _ = User.objects.get_or_create(username=username, defaults=dict(first_name=first, last_name=last))
            user.set_password(password)
            user.is_staff = False
            user.save()
            user.groups.set([Group.objects.get_or_create(name=group)[0]])
            SchoolStaff.objects.update_or_create(user=user, defaults={"school": school})
            if group == "Teacher":
                for title in ("۹-الف", "۱۰-الف"):
                    TeacherAssignment.objects.get_or_create(teacher=user, school_class=classes[title], subject="math")
            else:
                GradeLeadAssignment.objects.get_or_create(user=user, school=school, grade=10, academic_year=year.code)
        self._referral(school, students)

    def _referral(self, school, students):
        """Slice 4a: one open demo referral (SchoolAdmin -> counselor) so the counselor pages have a case to show."""
        from students.models import Referral
        User = get_user_model()
        child = next(s for s, p in students if p.get("key") == "attendance_ali")
        Referral.objects.create(student=child, school=school, counselor=User.objects.get(username="demo_counselor"),
                                referred_by=User.objects.get(username="demo_admin"),
                                reason="غیبت‌های مکرر در هفته‌های اخیر؛ لطفاً گفت‌وگو با دانش‌آموز و خانواده.")
