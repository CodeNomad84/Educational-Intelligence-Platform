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


def make_student(n=1):
    return Student.objects.create(first_name="تست", last_name=f"نمونه{n}", national_id=f"900000{n:04d}",
                                  grade=10, class_name="۱۰-الف", phone_number="0900000000")


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
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {ADMIN, "Parent"})
        User = get_user_model()
        for name in ("demo_admin", "demo_counselor"):
            self.assertIn(ADMIN, roles_for(User.objects.get(username=name)), name)
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
        self.client.force_login(get_user_model().objects.get(username="demo_counselor"))
        s = Student.objects.get(first_name="علی", last_name="احمدی")
        html = self.client.get(f"/students/{s.id}/").content.decode()
        self.assertIn("کارت هوشمند", html)
        self.assertIn("قاعده", html)

    def test_assistant_answers_from_data_and_is_labelled(self):
        out = assistant.answer("کدام دانش‌آموزان نیاز به توجه دارند؟")
        self.assertTrue(out["rows"])
        self.assertIn("بازبینی انسانی", out["disclaimer"])
        why = assistant.answer("چرا علی احمدی در معرض خطر است؟")
        self.assertTrue(why["bullets"])
        self.assertEqual(why["rows"][0]["name"], "علی احمدی")
        self.assertIn("پشتیبانی نمی‌شود", assistant.answer("آب و هوا چطور است؟")["title"])
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
                                   grade=9, class_name="۹-الف", phone_number="0")

    def test_ambiguous_name(self):
        out = assistant.answer("چرا تکراری در معرض خطر است؟")
        self.assertEqual(out["title"], "لطفاً نام کامل دانش‌آموز را وارد کنید")
        self.assertEqual(len(out["bullets"]), 2)
        self.assertFalse(out["rows"])

    def test_first_and_last_names_of_different_students_are_ambiguous(self):
        out = assistant.answer("مهسا احمدی چگونه بهتر شد؟")
        self.assertEqual(out["title"], "لطفاً نام کامل دانش‌آموز را وارد کنید")

    def test_unknown_student(self):
        out = assistant.answer("چرا غزاله کوهستانی در معرض خطر است؟")
        self.assertEqual(out["title"], "دانش‌آموزی با این نام پیدا نشد")
        self.assertEqual(assistant.answer("why is Ali Ahmadi at risk")["title"], "دانش‌آموزی با این نام پیدا نشد")

    def test_improvement_question(self):
        out = assistant.answer("مهسا فرهادی چگونه بهتر شد؟")
        text = " ".join(out["bullets"])
        self.assertIn("وضعیت قبلی", text)
        self.assertIn("جلسهٔ مشاوره", text)          # the intervention
        self.assertIn("شواهد بهبود", text)
        self.assertEqual(out["rows"][0]["name"], "مهسا فرهادی")
        self.assertEqual(out["label"], "Rule-Based Prototype Assistant")

    def test_improvement_on_student_without_improvement_is_honest(self):
        out = assistant.answer("رضا کاظمی چگونه بهتر شد؟")
        self.assertIn("شواهد روشنی از بهبود دیده نمی‌شود", " ".join(out["paragraphs"]))

    def test_attention_question_not_blocked_by_name_logic(self):
        out = assistant.answer("کدام دانش‌آموزان نیاز به توجه دارند؟")
        self.assertEqual(len(out["rows"]), 9)

    def test_persian_digits_and_no_internal_ids(self):
        self.client.force_login(get_user_model().objects.get(username="demo_admin"))
        reza = Student.objects.get(first_name="رضا", last_name="کاظمی")
        pages = [self.client.get(f"/students/{reza.id}/"), self.client.get("/demo/counselor/"),
                 self.client.get("/dashboard/"),
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
