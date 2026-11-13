# DEMO SCOPE — whole file. Run with:
#   DJANGO_SETTINGS_MODULE=config.settings.demo python manage.py test demo_intel
import unittest
from datetime import timedelta

from django.conf import settings

if not getattr(settings, "DEMO_MODE", False):
    raise unittest.SkipTest("demo_intel tests need config.settings.demo")

import copy  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402
from django.test import TestCase, override_settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from demo_intel import assistant  # noqa: E402
from demo_intel.engine import analyze_student, analyze_students  # noqa: E402
from demo_intel.models import InterventionRecord, StudentObservation  # noqa: E402
from students.access import ADMIN, roles_for  # noqa: E402
from students.models import Attendance, Grade, Student  # noqa: E402


def _school_days(today, n=100):
    return [today - timedelta(days=d) for d in range(n) if (today - timedelta(days=d)).weekday() not in (3, 4)]


def _demo_school():
    from schools.models import School
    return School.objects.order_by("pk").first()


def make_student(n=1):
    return Student.objects.create(first_name="تست", last_name=f"نمونه{n}", national_id=f"900000{n:04d}",
                                  grade=10, class_name="۱۰-الف", phone_number="0900000000",
                                  school=_demo_school())


class EngineTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

    def _attendance(self, s, recent_abs, base_abs):
        recent = [d for d in _school_days(self.today) if d > self.today - timedelta(days=30)]
        base = [d for d in _school_days(self.today)
                if self.today - timedelta(days=90) < d <= self.today - timedelta(days=30)]
        for days, k in ((recent, recent_abs), (base, base_abs)):
            for i, d in enumerate(days):
                Attendance.objects.create(student=s, date=d, status="absent" if i < k else "present")

    def test_no_data_is_low_with_no_reasons(self):
        r = analyze_student(make_student(), self.today)
        self.assertEqual((r["level"], r["score"], r["reasons"]), ("LOW", 0, []))
        self.assertTrue(r["recommendations"])

    def test_attendance_shift_is_explained(self):
        s = make_student()
        self._attendance(s, recent_abs=8, base_abs=1)
        r = analyze_student(s, self.today)
        rules = [x["rule"] for x in r["reasons"]]
        self.assertIn("attendance_shift", rules)
        self.assertTrue(all(x["text"] and "points" in x for x in r["reasons"]))
        self.assertGreaterEqual(r["score"], 30)

    def test_subject_drop_and_low_average(self):
        s = make_student()
        for off, score in ((100, 16), (80, 16), (60, 16), (30, 6), (20, 6), (10, 6)):
            Grade.objects.create(student=s, subject="math", exam_type="quiz", score=score,
                                 date=self.today - timedelta(days=off))
        rules = [x["rule"] for x in analyze_student(s, self.today)["reasons"]]
        self.assertIn("subject_drop", rules)
        self.assertIn("low_average", rules)

    def test_negative_observations_scale_and_levels(self):
        s = make_student()
        for i in range(4):
            StudentObservation.objects.create(student=s, date=self.today - timedelta(days=i + 1),
                                              category="discipline", sentiment="negative")
        r = analyze_student(s, self.today)
        self.assertEqual(r["score"], 25)
        self.assertEqual(r["level"], "LOW")

    def test_protective_factor_lowers_score(self):
        s = make_student()
        self._attendance(s, recent_abs=0, base_abs=12)
        InterventionRecord.objects.create(student=s, kind="attendance_plan", status="active",
                                          start_date=self.today - timedelta(days=40))
        r = analyze_student(s, self.today)
        self.assertIn("intervention_improving", [x["rule"] for x in r["reasons"]])
        self.assertEqual(r["score"], 0)


@override_settings(DATABASES={"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}})
class SeedAndViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)

    def test_seed_data_shape(self):
        self.assertEqual(Student.objects.count(), 40)
        self.assertGreaterEqual(len({s.class_name for s in Student.objects.all()}), 4)
        res = analyze_students()
        levels = {r["level"] for r in res.values()}
        self.assertEqual(levels, {"HIGH", "MEDIUM", "LOW"})
        self.assertTrue(StudentObservation.objects.exists() and InterventionRecord.objects.exists())

    def test_seed_refuses_non_demo_database(self):
        with override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "/x/db.sqlite3"}}):
            with self.assertRaises(CommandError):
                call_command("seed_demo", "--reset", verbosity=0)

    def test_seed_creates_schooladmin_group_and_admin_roles(self):
        """seed_demo must use the ADMIN constant (ADR-0010): SchoolAdmin exists and the pre-rename group name does not."""
        self.assertEqual(ADMIN, "SchoolAdmin")
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {ADMIN, "Parent", "Teacher", "GradeLead", "Counselor", "Student", "PlatformAdmin"})
        User = get_user_model()
        self.assertIn(ADMIN, roles_for(User.objects.get(username="demo_admin")))
        self.assertEqual(roles_for(User.objects.get(username="demo_counselor")), {"Counselor"})   # Slice 4a: a real role
        self.assertNotIn(ADMIN, roles_for(User.objects.get(username="demo_parent")))

    def test_admin_role_demo_login_reaches_admin_pages(self):
        """Real password login (not force_login) as the Admin-role demo user reaches the 403-guarded demo pages."""
        self.assertTrue(self.client.login(username="demo_admin", password="Test-pass-123"))
        for url in ("/dashboard/", "/demo/counselor/", "/demo/students/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_roles(self):
        c = self.client
        c.get("/dashboard/")
        self.assertEqual(c.get("/demo/counselor/").status_code, 302)  # anonymous -> login
        c.force_login(get_user_model().objects.get(username="demo_admin"))
        for url in ("/dashboard/", "/demo/counselor/", "/demo/students/", "/demo/assistant/"):
            self.assertEqual(c.get(url).status_code, 200, url)
        c.force_login(get_user_model().objects.get(username="demo_parent"))
        self.assertEqual(c.get("/demo/counselor/").status_code, 403)
        self.assertEqual(c.get("/demo/assistant/").status_code, 403)
        self.assertEqual(c.get("/demo/students/").status_code, 403)

    def test_parent_sees_only_own_child_without_risk_card(self):
        user = get_user_model().objects.get(username="demo_parent")
        self.client.force_login(user)
        own = Student.objects.get(parent_user=user)
        other = Student.objects.exclude(parent_user=user).first()
        r = self.client.get(f"/students/{own.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("lvl-", r.content.decode())
        self.assertEqual(self.client.get(f"/students/{other.id}/").status_code, 404)

    def test_staff_profile_shows_intelligence_card(self):
        self.client.force_login(get_user_model().objects.get(username="demo_admin"))
        s = Student.objects.get(first_name="علی", last_name="احمدی")
        html = self.client.get(f"/students/{s.id}/").content.decode()
        self.assertIn("کارت هوشمند", html)
        self.assertIn("قاعده", html)

    def test_assistant_answers_from_data_and_is_labelled(self):
        out = assistant.answer("کدام دانش‌آموزان نیاز به توجه دارند؟", students=Student.objects.all())
        self.assertTrue(out["rows"])
        self.assertIn("بازبینی انسانی", out["disclaimer"])
        why = assistant.answer("چرا علی احمدی در معرض خطر است؟", students=Student.objects.all())
        self.assertTrue(why["bullets"])
        self.assertEqual(why["rows"][0]["name"], "علی احمدی")
        self.assertIn("پشتیبانی نمی‌شود", assistant.answer("آب و هوا چطور است؟", students=Student.objects.all())["title"])
        self.assertEqual(why["label"], "Rule-Based Prototype Assistant")

    def test_assistant_never_reads_counseling_text(self):
        import inspect
        from demo_intel import assistant as a, engine as e
        for mod in (a, e):
            src = inspect.getsource(mod)
            self.assertNotIn("CounselingNote.objects", src)
            self.assertNotIn(".summary", src)


# ----------------------------------------------------------------------------------------------------------
# Hardening tests
# ----------------------------------------------------------------------------------------------------------
import re  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

from django.core.management import call_command as _call  # noqa: E402,F811

from demo_intel import preflight  # noqa: E402

SCRIPT = Path(settings.BASE_DIR).parent / "scripts" / "start_demo.sh"
DEMO_DB = {"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}}
REAL_DB = {"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/db.sqlite3"}}


class StartConfigurationTests(TestCase):
    def test_configuration_problems(self):
        with override_settings(DATABASES=DEMO_DB):
            self.assertEqual(preflight.configuration_problems(), [])
        with override_settings(DATABASES=REAL_DB):
            self.assertTrue(any("db.sqlite3" in p for p in preflight.configuration_problems()))
        with override_settings(DATABASES=DEMO_DB, DEMO_MODE=False):
            self.assertTrue(any("DEMO_MODE" in p for p in preflight.configuration_problems()))

    def test_demo_check_refuses_real_database(self):
        with override_settings(DATABASES=REAL_DB):
            with self.assertRaises(CommandError) as ctx:
                call_command("demo_check", verbosity=0)
        self.assertIn("WRONG CONFIGURATION", str(ctx.exception))

    def test_demo_check_staleness(self):
        fresh = {"database": "demo_db.sqlite3", "students": 40, "seed_date": None, "age_days": 0}
        stale = {**fresh, "age_days": 5}
        with override_settings(DATABASES=DEMO_DB):
            with mock.patch.object(preflight, "status", return_value=fresh):
                call_command("demo_check", verbosity=0)
            with mock.patch.object(preflight, "status", return_value=stale):
                with self.assertRaises(CommandError):
                    call_command("demo_check", verbosity=0)
                call_command("demo_check", "--allow-stale", verbosity=0)

    def test_demo_check_detects_pending_migrations_without_changing_anything(self):
        from django.db.migrations.recorder import MigrationRecorder

        from django.db.migrations.loader import MigrationLoader

        Applied = MigrationRecorder.Migration
        self.assertEqual(preflight.pending_migrations(), [])
        # Simulate a database that is exactly one migration behind: forget a migration that NOTHING depends on.
        # (Removing a record below an applied dependent would make the history inconsistent, and the same-app
        # leaf is not enough: another app may depend on it. A true leaf has no children at all.) Prefer the
        # students migration, which is what the guard exists for; fall back to any project-app leaf.
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        true_leaves = sorted(key for key, node in graph.node_map.items() if not node.children
                             and key[0] not in {"admin", "auth", "contenttypes", "sessions"})
        self.assertTrue(true_leaves)
        app, newest = next((k for k in true_leaves if k[0] == "students"), true_leaves[0])
        expected = [f"{app}.{newest}"]
        Applied.objects.filter(app=app, name=newest).delete()
        before = sorted(Applied.objects.values_list("app", "name"))
        self.assertEqual(preflight.pending_migrations(), expected)
        with override_settings(DATABASES=DEMO_DB):
            with self.assertRaises(CommandError) as ctx:
                call_command("demo_check", verbosity=0)
        message = str(ctx.exception)
        self.assertIn("unapplied migration", message)
        self.assertIn("start_demo.sh --reseed", message)
        self.assertIn("Nothing was changed", message)
        self.assertIn("nothing will be run for you", message)
        self.assertIn("DESTRUCTIVE", message)  # --reseed is presented as a data-resetting action, never run
        self.assertLess(message.index("manage.py migrate"), message.index("--reseed"))  # safe option first
        # read-only: nothing was applied or recorded, and the check still reports the same backlog
        self.assertEqual(sorted(Applied.objects.values_list("app", "name")), before)
        self.assertEqual(preflight.pending_migrations(), expected)

    def test_settings_module_is_the_demo_one(self):
        self.assertEqual(settings.SETTINGS_MODULE if hasattr(settings, "SETTINGS_MODULE") else "config.settings.demo",
                         "config.settings.demo")
        self.assertEqual(settings.DEMO_DB_FILENAME, "demo_db.sqlite3")

    def test_launcher_script(self):
        text = SCRIPT.read_text()
        self.assertTrue(SCRIPT.stat().st_mode & 0o111, "start_demo.sh must be executable")

    def test_reseed_deletes_only_the_demo_db_before_migrating_and_explains_a_migrate_failure(self):
        """An old demo_db.sqlite3 (students without school) must never block --reseed: the file is removed BEFORE migrate."""
        text = SCRIPT.read_text(encoding="utf-8")
        rm = text.index('rm -f -- "$DEMO_DB"')
        self.assertLess(rm, text.index("manage.py migrate --noinput"))
        self.assertIn('DEMO_DB="$APP/demo_db.sqlite3"', text)
        self.assertIn('"$(basename "$DEMO_DB")" = "demo_db.sqlite3"', text)
        self.assertEqual(text.count("rm -f"), 1)                      # nothing else is ever deleted
        self.assertIn("MIGRATE FAILED", text)
        self.assertIn("scripts/start_demo.sh --reseed", text)
        for needle in ("config.settings.demo", "--noreload", "DEMO MODE ACTIVE" if False else "demo_check",
                       "REFUSING TO START"):
            self.assertIn(needle, text)
        self.assertEqual(subprocess.run(["bash", "-n", str(SCRIPT)]).returncode, 0)

    def test_launcher_fails_fast_on_wrong_settings(self):
        env = {**__import__("os").environ, "DJANGO_SETTINGS_MODULE": "config.settings.development"}
        r = subprocess.run([str(SCRIPT), "--check"], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSING TO START", r.stderr)


@override_settings(DATABASES=DEMO_DB)
class SeedStabilityTests(TestCase):
    HEROES = {("علی", "احمدی"): "MEDIUM", ("نیلوفر", "موسوی"): "MEDIUM", ("پارسا", "نوری"): "MEDIUM",
              ("آرمان", "رحیمی"): "MEDIUM", ("رضا", "کاظمی"): "HIGH", ("سینا", "باقری"): "HIGH",
              ("مهسا", "فرهادی"): "LOW", ("آرین", "جعفری"): "LOW", ("کیان", "صادقی"): "LOW"}

    def test_distribution_and_heroes_stable_across_days(self):
        import datetime as dt
        for k in (0, 1, 2, 3, 4, 5, 6):  # a full week incl. Thu/Fri
            day = dt.date(2026, 10, 13) + dt.timedelta(days=k)
            with mock.patch("django.utils.timezone.localdate", return_value=day):
                _call("seed_demo", "--reset", "--password", "x", verbosity=0)
                res = analyze_students(today=day)
            dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            for r in res.values():
                dist[r["level"]] += 1
            self.assertEqual(dist, {"HIGH": 2, "MEDIUM": 7, "LOW": 31}, day)
            for (first, last), level in self.HEROES.items():
                s = Student.objects.get(first_name=first, last_name=last)
                self.assertEqual(res[s.id]["level"], level, (day, first, last))

    def test_hero_identities_are_unique(self):
        _call("seed_demo", "--reset", "--password", "x", verbosity=0)
        for first, last in self.HEROES:
            self.assertEqual(Student.objects.filter(last_name=last).count(), 1, last)
            self.assertEqual(Student.objects.filter(first_name=first).count(), 1, first)


@override_settings(DATABASES=DEMO_DB)
class HardeningViewAndAssistantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)
        for first in ("ژاله", "ژیلا"):
            Student.objects.create(first_name=first, last_name="تکراری", national_id="9100" + str(ord(first[1]))[:6],
                                   grade=9, class_name="۹-الف", phone_number="0", school=_demo_school())

    def test_ambiguous_name(self):
        out = assistant.answer("چرا تکراری در معرض خطر است؟", students=Student.objects.all())
        self.assertEqual(out["title"], "لطفاً نام کامل دانش‌آموز را وارد کنید")
        self.assertEqual(len(out["bullets"]), 2)
        self.assertFalse(out["rows"])

    def test_first_and_last_names_of_different_students_are_ambiguous(self):
        out = assistant.answer("مهسا احمدی چگونه بهتر شد؟", students=Student.objects.all())
        self.assertEqual(out["title"], "لطفاً نام کامل دانش‌آموز را وارد کنید")

    def test_unknown_student(self):
        out = assistant.answer("چرا غزاله کوهستانی در معرض خطر است؟", students=Student.objects.all())
        self.assertEqual(out["title"], "دانش‌آموزی با این نام پیدا نشد")
        self.assertEqual(assistant.answer("why is Ali Ahmadi at risk", students=Student.objects.all())["title"], "دانش‌آموزی با این نام پیدا نشد")

    def test_improvement_question(self):
        out = assistant.answer("مهسا فرهادی چگونه بهتر شد؟", students=Student.objects.all())
        text = " ".join(out["bullets"])
        self.assertIn("وضعیت قبلی", text)
        self.assertIn("جلسهٔ مشاوره", text)          # the intervention
        self.assertIn("شواهد بهبود", text)
        self.assertEqual(out["rows"][0]["name"], "مهسا فرهادی")
        self.assertEqual(out["label"], "Rule-Based Prototype Assistant")

    def test_improvement_on_student_without_improvement_is_honest(self):
        out = assistant.answer("رضا کاظمی چگونه بهتر شد؟", students=Student.objects.all())
        self.assertIn("شواهد روشنی از بهبود دیده نمی‌شود", " ".join(out["paragraphs"]))

    def test_attention_question_not_blocked_by_name_logic(self):
        out = assistant.answer("کدام دانش‌آموزان نیاز به توجه دارند؟", students=Student.objects.all())
        self.assertEqual(len(out["rows"]), 9)

    def test_persian_digits_and_no_internal_ids(self):
        self.client.force_login(get_user_model().objects.get(username="demo_admin"))
        reza = Student.objects.get(first_name="رضا", last_name="کاظمی")
        pages = [self.client.get(f"/students/{reza.id}/"), self.client.get("/demo/counselor/"),
                 self.client.get("/demo/school/"),   # the demo engine page (the principal dashboard took /dashboard/)
                 self.client.post("/demo/assistant/", {"query": "چرا رضا کاظمی در معرض خطر است؟"})]
        for r in pages:
            html = r.content.decode()
            self.assertNotRegex(html, r"[0-9]٪", r.request["PATH_INFO"])
            self.assertNotIn("attendance_shift", html)
            self.assertNotIn("subject_drop", html)
        self.assertIn("کاهش حضور و غیاب", pages[0].content.decode())

    def test_chart_labels_use_persian_digits(self):
        from demo_intel.analytics import school_overview
        from django.utils import timezone as tz
        students = list(Student.objects.all())
        o = school_overview(students, analyze_students(students), tz.localdate())
        for label in o["attendance_trend"]["labels"] + o["academic_trend"]["labels"]:
            self.assertNotRegex(label, r"[0-9]")

    def test_demo_login_page(self):
        r = self.client.get("/")
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("DEMO", html)
        self.assertNotIn("cdn.jsdelivr", html)
        r = self.client.post("/login/", {"username": "demo_admin", "password": "wrong"})
        self.assertContains(r, "رمز عبور اشتباه")
        r = self.client.post("/login/", {"username": "demo_admin", "password": "Test-pass-123"})
        self.assertEqual(r.status_code, 302)

    def test_parent_page_has_no_ai_button_or_dead_links(self):
        user = get_user_model().objects.get(username="demo_parent")
        self.client.force_login(user)
        own = Student.objects.get(parent_user=user)
        html = self.client.get(f"/students/{own.id}/").content.decode()
        self.assertNotIn("پیش‌بینی وضعیت با هوش مصنوعی", html)
        self.assertNotIn("/chat/", html)
        self.assertNotIn("/library/", html)

    def test_permissions_preserved(self):
        c = self.client
        user = get_user_model()
        c.force_login(user.objects.get(username="demo_parent"))
        for url in ("/demo/counselor/", "/demo/students/", "/demo/assistant/"):
            self.assertEqual(c.get(url).status_code, 403, url)
        self.assertEqual(c.post("/demo/assistant/", {"query": "x"}).status_code, 403)
        c.logout()
        for url in ("/demo/counselor/", "/demo/assistant/", "/dashboard/"):
            self.assertEqual(c.get(url).status_code, 302, url)


@override_settings(DATABASES={"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}})
class SeedDemoSchoolTests(TestCase):
    """S2b: every demo student gets an explicit school; no hidden default when several Schools exist."""

    def test_the_only_school_is_used_and_every_student_has_it(self):
        from schools.models import School
        only = School.objects.get()
        call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(set(Student.objects.values_list("school_id", flat=True)), {only.pk})

    def test_several_schools_need_the_school_option(self):
        from schools.models import School
        School.objects.create(name="Second", code="second")
        with self.assertRaises(CommandError):
            call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(Student.objects.count(), 0)

    def test_an_empty_school_option_is_an_error_even_with_a_single_school(self):
        from schools.models import School
        self.assertEqual(School.objects.count(), 1)  # the case where "" used to silently pick the sole School
        with self.assertRaises(CommandError):
            call_command("seed_demo", "--school", "", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(Student.objects.count(), 0)

    def test_the_school_option_picks_the_school_and_unknown_codes_fail(self):
        from schools.models import School
        School.objects.create(name="Second", code="second")
        with self.assertRaises(CommandError):
            call_command("seed_demo", "--school", "nope", "--password", "Test-pass-123", verbosity=0)
        call_command("seed_demo", "--school", "second", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(set(Student.objects.values_list("school__code", flat=True)), {"second"})


@override_settings(DATABASES={"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}})
class SeedDemoResetOrderTests(TestCase):
    """A bad --school must be reported BEFORE --reset deletes anything."""

    def setUp(self):
        from schools.models import School
        call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)
        School.objects.create(name="Second", code="second")  # now several Schools exist
        self.before = (Student.objects.count(), StudentObservation.objects.count(),
                       get_user_model().objects.filter(username__startswith="demo_").count())
        self.assertGreater(self.before[0], 0)

    def after(self):
        return (Student.objects.count(), StudentObservation.objects.count(),
                get_user_model().objects.filter(username__startswith="demo_").count())

    def test_reset_without_school_deletes_nothing(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", "--reset", verbosity=0)
        self.assertEqual(self.after(), self.before)

    def test_reset_with_a_mistyped_school_deletes_nothing(self):
        for bad in ("secnd", ""):
            with self.assertRaises(CommandError):
                call_command("seed_demo", "--reset", "--school", bad, verbosity=0)
            self.assertEqual(self.after(), self.before)

    def test_reset_with_a_valid_school_still_rebuilds(self):
        call_command("seed_demo", "--reset", "--school", "second", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(set(Student.objects.values_list("school__code", flat=True)), {"second"})


@override_settings(DATABASES={"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}})
class DemoLoginLandingTests(TestCase):
    """Every demo user logs in with the printed password (real login, not force_login), lands on the page of the role and
    finds the links of the role there. A safe ``next`` is honoured, an unsafe one is not."""
    PASSWORD = "Test-pass-123"
    # username -> (landing URL, links that must be on the landing page)
    EXPECTED = {
        "demo_admin": ("/school/", ["/school/years/", "/school/classes/", "/school/teachers/", "/school/gradeleads/"]),
        "demo_teacher": ("/teacher/", ["/teacher/", "/students/"]),
        "demo_gradelead": ("/grade/", ["/grade/", "/students/"]),
        "demo_parent": ("/students/", ["/students/"]),
        "demo_counselor": ("/counselor/", ["/counselor/"]),
        "demo_student": ("/me/", ["/me/", "/me/assistant/"]),
    }

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", cls.PASSWORD, verbosity=0)

    def login(self, username, **extra):
        return self.client.post("/login/", {"username": username, "password": self.PASSWORD, **extra})

    def test_each_demo_user_lands_on_its_page_with_its_own_links(self):
        for username, (landing, links) in self.EXPECTED.items():
            with self.subTest(user=username):
                self.client.logout()
                resp = self.login(username)
                self.assertEqual((resp.status_code, resp["Location"]), (302, landing))
                page = self.client.get(landing)
                self.assertEqual(page.status_code, 200)
                body = page.content.decode()
                for link in links:
                    self.assertIn(f'href="{link}"', body)

    def test_a_safe_next_is_honoured_and_unsafe_ones_are_ignored(self):
        resp = self.client.get("/school/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/login/?next=/school/")
        self.assertEqual(self.login("demo_admin", next="/school/years/")["Location"], "/school/years/")
        for bad in ("https://evil.example/", "//evil.example/", "javascript:alert(1)"):
            self.client.logout()
            self.assertEqual(self.login("demo_admin", next=bad)["Location"], "/school/", bad)

    def test_login_via_the_query_string_next_of_the_redirect(self):
        resp = self.client.post("/login/?next=/school/classes/", {"username": "demo_admin", "password": self.PASSWORD})
        self.assertEqual(resp["Location"], "/school/classes/")

    def test_the_login_form_carries_next(self):
        self.assertContains(self.client.get("/login/?next=/school/"), 'name="next" value="/school/"')


@override_settings(DATABASES={"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}})
class DemoMissionTests(TestCase):
    """The demo school has every sellable module licensed and a small synthetic mission dataset, so each role can reach the
    observation grid, the report and both forms; a school created later stays locked."""
    PASSWORD = "Test-pass-123"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", cls.PASSWORD, verbosity=0)

    def as_user(self, username):
        self.client.logout()
        self.assertEqual(self.client.post("/login/", {"username": username, "password": self.PASSWORD}).status_code, 302)

    def test_all_modules_are_licensed_for_the_demo_school_only(self):
        from schools.entitlements import ACTIVE_LICENSED, LOCKED, MODULES, module_state
        from schools.models import School
        demo = School.objects.get()
        self.assertEqual({k: module_state(demo, k) for k in MODULES}, {k: ACTIVE_LICENSED for k in MODULES})
        other = School.objects.create(name="Real", code="real")                 # a school added later: everything locked
        self.assertEqual({module_state(other, k) for k in MODULES}, {LOCKED})

    def test_every_role_reaches_its_mission_pages(self):
        from missions.models import ActivityChoice, Observation, ParentMeeting
        self.assertTrue(Observation.objects.exists() and ActivityChoice.objects.exists() and ParentMeeting.objects.exists())
        student = ActivityChoice.objects.get().student
        grid = reverse_("missions:grid", Activity_pk())
        pages = {
            "demo_gradelead": [grid, reverse_("missions:students"), reverse_("missions:report", student.pk),
                               reverse_("missions:choices", student.pk), reverse_("missions:meetings", student.pk)],
            "demo_teacher": [reverse_("missions:activities"), grid, reverse_("missions:students")],
            "demo_admin": [reverse_("missions:aggregate")],
        }
        for username, urls in pages.items():
            self.as_user(username)
            for url in urls:
                with self.subTest(user=username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        self.as_user("demo_counselor")                                            # only through the open referral
        self.assertEqual(self.client.get(reverse_("missions:students")).status_code, 200)
        self.assertEqual(self.client.get(reverse_("missions:report", student.pk)).status_code, 200)    # the referred student
        other = Observation.objects.exclude(student=student).first().student
        self.assertEqual(self.client.get(reverse_("missions:report", other.pk)).status_code, 404)

    def test_the_demo_report_shows_data_and_the_aggregate_is_not_suppressed(self):
        from missions.models import ActivityChoice
        student = ActivityChoice.objects.get().student
        self.as_user("demo_gradelead")
        page = self.client.get(reverse_("missions:report", student.pk))
        self.assertContains(page, "مشاهدهٔ نمایشی")
        self.assertTrue(any(b["scored"] for b in page.context["branches"]))
        self.assertFalse(page.context["situations"] == [])                        # the two observers differ on one indicator
        self.as_user("demo_admin")
        group = self.client.get(reverse_("missions:aggregate")).context["blocks"][0]["groups"][0]
        self.assertFalse(group["suppressed"])

    def test_reset_removes_mission_data_without_a_protected_error(self):
        from missions.models import Observation
        call_command("seed_demo", "--reset", "--password", self.PASSWORD, verbosity=0)
        self.assertTrue(Observation.objects.exists())


def reverse_(name, *args):
    from django.urls import reverse
    return reverse(name, args=list(args))


def Activity_pk():
    from missions.models import Activity
    return Activity.objects.first().pk


class DemoPagesAreSchoolScopedTests(TestCase):
    """Stabilisation B2: the demo pages show only the students the user may read (no more ``Student.objects.all()``)."""

    def setUp(self):
        from schools.models import School, SchoolMembership
        User = get_user_model()
        self.a = School.objects.create(name="A", code="a")
        self.b = School.objects.create(name="B", code="b")
        from schools.module_grants import grant
        grant(self.a, "advisor_ai")
        grant(self.b, "advisor_ai")
        for code, school in (("alpha", self.a), ("bravo", self.b)):
            Student.objects.create(first_name=code.title(), last_name=code.title() + "son", national_id=f"93{ord(code[0])}00000", grade=9,
                                   phone_number="1", school=school, class_name="9-A")
        self.admin = User.objects.create_user("scoped-admin", password="x")
        self.admin.groups.add(Group.objects.get_or_create(name=ADMIN)[0])
        SchoolMembership.objects.create(user=self.admin, school=self.a)
        self.client.force_login(self.admin)

    def test_every_demo_page_shows_only_the_own_school(self):
        for url in ("/dashboard/", "/demo/counselor/", "/demo/students/", "/demo/assistant/?q=Alpha"):
            body = self.client.get(url).content.decode()
            self.assertNotIn("Bravo", body, url)
        self.assertIn("Alpha", self.client.get("/demo/students/").content.decode())

    def test_the_assistant_never_names_or_counts_another_schools_student(self):
        out = assistant.answer("چرا Bravo Bravoson در معرض خطر است؟", students=Student.objects.filter(school=self.a))
        self.assertEqual(out["title"], "دانش‌آموزی با این نام پیدا نشد")
        with self.assertRaises(TypeError):
            assistant.answer("x")          # the student set is mandatory: no hidden global query

    def test_rule_based_risk_pages_are_base_and_only_the_assistant_needs_advisor_ai(self):
        from schools.models import SchoolModule
        SchoolModule.objects.all().delete()
        for url in ("/dashboard/", "/demo/counselor/", "/demo/students/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/demo/assistant/?q=Alpha").status_code, 403)
        from schools.module_grants import grant
        grant(self.a, "advisor_ai")
        self.assertEqual(self.client.get("/demo/assistant/?q=Alpha").status_code, 200)
        grant(self.b, "advisor_ai")
        SchoolModule.objects.filter(school=self.a).delete()          # only the other school has it
        self.assertEqual(self.client.get("/demo/assistant/?q=Alpha").status_code, 403)

    def test_the_assistant_call_cap_blocks_with_a_message(self):
        self.a.ai_daily_cap = 1
        self.a.save()
        self.assertEqual(self.client.get("/demo/assistant/?q=Alpha").status_code, 200)
        capped = self.client.get("/demo/assistant/?q=Alpha")
        self.assertEqual(capped.status_code, 429)
        self.assertContains(capped, "سقف روزانه", status_code=429)

    def test_the_platform_superuser_sees_no_students_on_the_demo_pages(self):
        root = get_user_model().objects.create_superuser("scoped-root", password="x")
        self.client.force_login(root)
        for url in ("/demo/students/", "/demo/counselor/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)


@override_settings(DATABASES={"default": {**copy.deepcopy(settings.DATABASES["default"]), "NAME": "/x/demo_db.sqlite3"}})
class DemoExamsTests(TestCase):
    """The demo school has a published synthetic practice exam: the teacher sees the bank, the demo student can play it."""
    PASSWORD = "Test-pass-123"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", cls.PASSWORD, verbosity=0)

    def login(self, username):
        self.client.logout()
        self.assertEqual(self.client.post("/login/", {"username": username, "password": self.PASSWORD}).status_code, 302)

    def test_teacher_bank_and_student_player(self):
        from exams.models import Exam, Option, Question
        exam = Exam.objects.get()
        self.assertEqual((Question.objects.count(), Option.objects.filter(explanation="").count(), exam.published), (3, 0, True))
        self.login("demo_teacher")
        self.assertContains(self.client.get("/exams/teacher/"), "تمرین کسرها")
        self.login("demo_student")
        self.assertContains(self.client.get("/exams/"), "تمرین کسرها")
        self.assertEqual(self.client.get(f"/exams/{exam.pk}/play/").status_code, 200)

    def test_reset_clears_exam_data_without_a_protected_error(self):
        from exams.models import Exam
        call_command("seed_demo", "--reset", "--password", self.PASSWORD, verbosity=0)
        self.assertEqual(Exam.objects.count(), 1)


@override_settings(DATABASES=DEMO_DB)
class SeedDemoInterventionLoopTests(TestCase):
    """Change 0022: the demo seed builds a synthetic intervention loop, and --reset removes it before the students (PROTECT)."""

    def test_seeded_loop_and_reset(self):
        from interventions.models import InterventionPlan
        from risk.models import Alert
        call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(set(Alert.objects.values_list("status", flat=True)), {"new", "dismissed", "accepted"})
        self.assertEqual(set(InterventionPlan.objects.values_list("status", flat=True)), {"active", "completed"})
        emotional = InterventionPlan.objects.get(intervention_type="emotional")
        self.assertEqual(emotional.owner.username, "demo_counselor")
        client = self.client_class()
        client.login(username="demo_admin", password="Test-pass-123")
        page = client.get("/interventions/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.context["due"]), 1)                     # the completed plan whose date has passed
        self.assertNotContains(page, "[نمایشی] هدف عاطفی")
        call_command("seed_demo", "--reset", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(InterventionPlan.objects.count(), 3)                  # rebuilt, not doubled
        self.assertEqual(Alert.objects.count(), 3)


@override_settings(DATABASES=DEMO_DB)
class SeedDemoPlatformAccountTests(TestCase):
    """The demo seed has a synthetic PlatformAdmin: staff, zero model permissions, no school role, lands on the operator page."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", "Test-pass-123", verbosity=0)

    def test_account_shape(self):
        user = get_user_model().objects.get(username="demo_platform")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["PlatformAdmin"])
        self.assertEqual(user.groups.get().permissions.count(), 0)
        self.assertEqual(roles_for(user), set())
        from schools.models import SchoolMembership
        self.assertFalse(SchoolMembership.objects.filter(user=user).exists())

    def test_login_lands_on_the_operator_page_and_sees_no_students(self):
        response = self.client.post("/login/", {"username": "demo_platform", "password": "Test-pass-123"})
        self.assertRedirects(response, "/platform/modules/", fetch_redirect_response=False)
        page = self.client.get("/platform/modules/")
        self.assertEqual(page.status_code, 200)
        names = " ".join(Student.objects.values_list("first_name", flat=True))
        # T10: the operator page shows the product name, and a seeded student is called "آرمان", which is part of
        # "سکوی آموزشی-تربیتی آرمان نو". Drop the brand before the substring check: it is not student data.
        html = page.content.decode().replace(settings.PLATFORM_NAME, "")
        self.assertFalse(any(n and n in html for n in names.split()[:5]))
        self.assertEqual(self.client.get("/students/").status_code, 403)
        self.assertEqual(self.client.get("/school/").status_code, 403)

    def test_reset_keeps_exactly_one_platform_account(self):
        call_command("seed_demo", "--reset", "--password", "Test-pass-123", verbosity=0)
        self.assertEqual(get_user_model().objects.filter(username="demo_platform").count(), 1)
