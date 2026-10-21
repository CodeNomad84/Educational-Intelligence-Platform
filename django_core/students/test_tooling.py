"""Tests of the test tooling itself: config.settings.test_postgres and scripts/run_tests.sh (modes, hard failures,
cleanup, no secret on a command line). The script is only run with a FAKE ``docker`` (a shell script that logs its
arguments) and a restricted PATH: no real container, image or network is touched."""
import importlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]   # the repository root on the host, /repo inside the PostgreSQL test container
SCRIPT = ROOT / "scripts" / "run_tests.sh"
SETTINGS_MODULE = "config.settings.test_postgres"
TOOLS = ("dirname", "date", "head", "od", "tr", "mktemp", "cp", "rm", "seq", "sleep", "cat", "mkdir")


def load_settings(env):
    sys.modules.pop(SETTINGS_MODULE, None)
    with mock.patch.dict(os.environ, env, clear=False):
        for name in ("TEST_PG_HOST", "TEST_PG_PASSWORD", "TEST_PG_NAME", "TEST_PG_USER", "TEST_PG_PORT"):
            if name not in env:
                os.environ.pop(name, None)
        try:
            return importlib.import_module(SETTINGS_MODULE)
        finally:
            sys.modules.pop(SETTINGS_MODULE, None)


class TestPostgresSettingsTests(SimpleTestCase):
    GOOD = {"TEST_PG_HOST": "pg.test", "TEST_PG_PASSWORD": "pw-for-tests"}

    def test_reads_everything_from_the_environment(self):
        module = load_settings({**self.GOOD, "TEST_PG_NAME": "eip_test_x", "TEST_PG_USER": "u", "TEST_PG_PORT": "5544"})
        db = module.DATABASES["default"]
        self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((db["HOST"], db["PASSWORD"], db["NAME"], db["USER"], db["PORT"]),
                         ("pg.test", "pw-for-tests", "eip_test_x", "u", "5544"))

    def test_defaults_for_name_user_port_only(self):
        db = load_settings(self.GOOD).DATABASES["default"]
        self.assertEqual((db["NAME"], db["USER"], db["PORT"]), ("eip_test", "eip_test", "5432"))

    def test_host_and_password_have_no_default(self):
        for missing in ("TEST_PG_HOST", "TEST_PG_PASSWORD"):
            env = {k: v for k, v in self.GOOD.items() if k != missing}
            with self.subTest(missing=missing), self.assertRaises(ImproperlyConfigured):
                load_settings(env)
            with self.subTest(empty=missing), self.assertRaises(ImproperlyConfigured):
                load_settings({**self.GOOD, missing: ""})

    def test_a_real_looking_database_name_is_refused(self):
        for name in ("school_db", "postgres", "test_eip", ""):
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured):
                load_settings({**self.GOOD, "TEST_PG_NAME": name})

    def test_no_password_literal_in_the_file(self):
        text = (ROOT / "django_core" / "config" / "settings" / "test_postgres.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"""['"]PASSWORD['"]\s*:\s*['"][^'"]""", text))


class RunTestsScriptTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        for tool in TOOLS:
            real = shutil.which(tool)
            self.assertIsNotNone(real, tool)
            (self.bin / tool).symlink_to(real)
        self.log = Path(self.tmp.name) / "docker.log"

    def fake_docker(self, **fail):
        """A fake `docker`: logs one line per call; exits 1 for the calls named in `fail` (e.g. info=True,
        inspect_pg=True, inspect_django=True, run_test=True)."""
        script = f"""#!/bin/bash
echo "$*" >> "{self.log}"
case "$1 $2" in
  "info "*) exit {1 if fail.get('info') else 0} ;;
  "image inspect")
     case "$3" in
       pgvector/*) exit {1 if fail.get('inspect_pg') else 0} ;;
       *) exit {1 if fail.get('inspect_django') else 0} ;;
     esac ;;
esac
if [ "$1" = "exec" ]; then exit 0; fi
if [ "$1" = "run" ] && [[ " $* " == *" test "* ]]; then exit {1 if fail.get('run_test') else 0}; fi
exit 0
"""
        path = self.bin / "docker"
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_script(self, *args, extra_env=None):
        env = {"PATH": str(self.bin), "HOME": self.tmp.name}
        env.update(extra_env or {})
        return subprocess.run(["/bin/bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=120)

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    # ---- usage and defaults
    def test_unknown_mode_and_extra_arguments_are_usage_errors(self):
        for args in (("bogus",), ("pg", "extra"), ("--help",)):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_default_mode_is_sqlite_and_the_original_message_is_kept(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('MODE="${1:-sqlite}"', text)
        self.assertIn("ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)", text)

    # ---- hard failures: nothing is started
    def test_pg_mode_fails_hard_without_the_docker_command(self):
        result = self.run_script("pg")
        self.assertEqual(result.returncode, 3)
        self.assertIn("docker command is not installed", result.stderr)

    def test_pg_mode_fails_hard_when_the_daemon_is_unreachable(self):
        self.fake_docker(info=True)
        result = self.run_script("pg")
        self.assertEqual(result.returncode, 3)
        self.assertIn("daemon", result.stderr)
        self.assertEqual([c for c in self.calls() if not c.startswith("info")], [])

    def test_pg_mode_fails_hard_when_the_postgres_image_is_missing_and_never_pulls(self):
        self.fake_docker(inspect_pg=True)
        result = self.run_script("pg")
        self.assertEqual(result.returncode, 3)
        self.assertIn("pgvector/pgvector:pg16", result.stderr)
        calls = self.calls()
        self.assertFalse([c for c in calls if c.startswith(("pull", "run", "build", "network"))], calls)

    def test_pg_mode_fails_hard_when_the_selected_django_image_is_missing(self):
        self.fake_docker(inspect_django=True)
        result = self.run_script("pg", extra_env={"DJANGO_IMAGE": "my/django:none"})
        self.assertEqual(result.returncode, 3)
        self.assertIn("my/django:none", result.stderr)
        self.assertFalse([c for c in self.calls() if c.startswith(("pull", "run", "build", "network"))])

    def test_all_mode_does_not_fall_back_to_sqlite_only_when_docker_is_missing(self):
        """`all` runs sqlite first (not stubbed here), so check the order instead: a restricted PATH has no python for
        the sqlite part and fails before PostgreSQL; the pg prerequisites are checked in `pg` mode above."""
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(text.index("run_sqlite\n    run_pg"), text.index("ALL DJANGO CHECKS AND TESTS PASSED ON SQLITE AND POSTGRESQL"))

    # ---- happy path with the fake docker
    def test_pg_mode_builds_runs_cleans_up_and_keeps_the_password_off_the_command_line(self):
        self.fake_docker()
        result = self.run_script("pg")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("POSTGRESQL CHECKS AND TESTS PASSED", result.stdout)
        calls = self.calls()
        joined = "\n".join(calls)
        self.assertTrue(any(c.startswith("build -q -t eip-test-django:local") for c in calls), calls)
        self.assertTrue(any(c.startswith("network create eip-test-net-") for c in calls))
        self.assertTrue(any(c.startswith("run -d --rm --name eip-test-pg-") for c in calls))
        self.assertIn("--tmpfs /var/lib/postgresql/data", joined)
        self.assertTrue(any(c.startswith("rm -f eip-test-pg-") for c in calls), "container not removed")
        self.assertTrue(any(c.startswith("network rm eip-test-net-") for c in calls), "network not removed")
        # three Django steps, all with the test_postgres settings and read-only source
        steps = [c for c in calls if "python -B manage.py" in c]
        self.assertEqual(len(steps), 3, steps)
        self.assertTrue(all("config.settings.test_postgres" in c and "/repo/django_core:ro" in c and "/repo/scripts:ro" in c
                            for c in steps))
        for step in steps:  # exactly two read-only mounts, laid out like the repository; never the repository root
            self.assertEqual(sorted(re.findall(r":(/repo/[^:\s]+):ro", step)), ["/repo/django_core", "/repo/scripts"], step)
        self.assertTrue(any("manage.py test students dashboard schools" in c for c in steps))
        self.assertFalse(any("demo" in c for c in steps))
        # the password reaches docker through the environment: only the variable NAME is on the command line
        self.assertNotRegex(joined, r"[0-9a-f]{32}")
        self.assertIn("-e POSTGRES_PASSWORD ", joined + " ")
        self.assertIn("-e TEST_PG_PASSWORD", joined)
        self.assertNotIn("PASSWORD=", joined)

    def test_a_failing_test_step_fails_the_script_and_still_cleans_up(self):
        self.fake_docker(run_test=True)
        result = self.run_script("pg")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PASSED", result.stdout)
        calls = self.calls()
        self.assertTrue(any(c.startswith("rm -f eip-test-pg-") for c in calls))
        self.assertTrue(any(c.startswith("network rm eip-test-net-") for c in calls))

    def test_selected_django_image_is_used_and_not_built(self):
        self.fake_docker()
        result = self.run_script("pg", extra_env={"DJANGO_IMAGE": "my/django:ok"})
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertFalse(any(c.startswith("build") for c in calls))
        self.assertTrue(all("my/django:ok" in c for c in calls if "manage.py" in c))

    def test_cleanup_state_is_global_so_the_exit_trap_can_always_see_it(self):
        """Regression: with `local NET/PGC` the EXIT trap hit 'PGC: unbound variable' on bash 5.2 when set -e ended the
        script inside the function, and the container and network were left behind."""
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"local[^\n]*\b(NET|PGC)\b")
        self.assertRegex(text, r'(?m)^PGC=""$')
        self.assertRegex(text, r'(?m)^NET=""$')
        self.assertRegex(text, r"(?m)^cleanup_pg\(\) \{")
        self.assertIn("trap cleanup_pg EXIT INT TERM", text)

    def test_each_run_uses_fresh_names(self):
        self.fake_docker()
        first = self.run_script("pg")
        names_one = {m for c in self.calls() for m in re.findall(r"eip-test-(?:pg|net)-[0-9-]+", c)}
        self.log.unlink()
        second = self.run_script("pg")
        names_two = {m for c in self.calls() for m in re.findall(r"eip-test-(?:pg|net)-[0-9-]+", c)}
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        self.assertTrue(names_one and names_two)
        self.assertFalse(names_one & names_two)
