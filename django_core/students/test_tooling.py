"""Tests of the test tooling itself: config.settings.test_postgres and scripts/run_tests.sh (modes, hard failures,
cleanup, no secret on a command line). The script is only run with a FAKE ``docker`` (a shell script that logs its
arguments) and a restricted PATH: no real container, image or network is touched."""
import errno
import importlib
import ipaddress
import os
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]   # the repository root on the host, /repo inside the PostgreSQL test container
SCRIPT = ROOT / "scripts" / "run_tests.sh"
SETTINGS_MODULE = "config.settings.test_postgres"
TOOLS = ("dirname", "date", "head", "od", "tr", "mktemp", "cp", "rm", "seq", "sleep", "cat", "mkdir")
# local-only files of django_core that the script hides from the test container (bind-mounted /dev/null / empty tmpfs)
HIDDEN_FILES = ("db.sqlite3", "demo_db.sqlite3", "data.xlsx", "data.ods")
APP_DIR = ROOT / "django_core"


def hidden_files_present():
    """The files the script should overlay, computed the same way from what exists on THIS side."""
    names = [n for n in HIDDEN_FILES if (APP_DIR / n).exists()]
    names += sorted(p.name for p in APP_DIR.glob(".env*") if p.exists())
    return names


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
if [ "$1" = "build" ]; then {'sleep 30; ' if fail.get('sleep_build') else ''}exit {1 if fail.get('build') else 0}; fi
if [ "$1" = "run" ] && [[ " $* " == *" test "* ]]; then {'sleep 30; ' if fail.get('sleep_test') else ''}exit {1 if fail.get('run_test') else 0}; fi
exit 0
"""
        path = self.bin / "docker"
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_script(self, *args, extra_env=None):
        self.tmpdir = Path(self.tmp.name) / "tmpdir"
        self.tmpdir.mkdir(exist_ok=True)
        env = {"PATH": str(self.bin), "HOME": self.tmp.name, "TMPDIR": str(self.tmpdir)}
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
        self.assertTrue(any(c.startswith("network create --internal eip-test-net-") for c in calls),
                        "the test network must be --internal (no route to the outside)")
        self.assertEqual(list(self.tmpdir.iterdir()), [], "the temporary build context must be removed")
        self.assertTrue(any(c.startswith("run -d --rm --name eip-test-pg-") for c in calls))
        self.assertIn("--tmpfs /var/lib/postgresql/data", joined)
        self.assertTrue(any(c.startswith("rm -f eip-test-pg-") for c in calls), "container not removed")
        self.assertTrue(any(c.startswith("network rm eip-test-net-") for c in calls), "network not removed")
        # three Django steps, all with the test_postgres settings and read-only source
        steps = [c for c in calls if "python -B manage.py" in c]
        self.assertEqual(len(steps), 3, steps)
        self.assertTrue(all("config.settings.test_postgres" in c and "/repo/django_core:ro" in c and "/repo/scripts:ro" in c
                            for c in steps))
        expected = sorted(["/repo/django_core", "/repo/scripts"] + [f"/repo/django_core/{n}" for n in hidden_files_present()])
        for step in steps:  # two read-only source mounts + the /dev/null overlays; never the repository root
            self.assertEqual(sorted(re.findall(r":(/repo/[^:\s]+):ro(?:\s|$)", step)), expected, step)
        self.assertTrue(any("manage.py test students dashboard schools" in c for c in steps))
        self.assertFalse(any("demo_intel" in c or "config.settings.demo" in c for c in steps))
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
        self.assertIn("trap cleanup_pg EXIT", text)

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

    # ---- isolation: internal network, hidden local files, build outside the internal network
    def test_the_network_is_internal_and_the_image_build_runs_before_it_exists(self):
        self.fake_docker()
        self.assertEqual(self.run_script("pg").returncode, 0)
        calls = self.calls()
        build = next(i for i, c in enumerate(calls) if c.startswith("build "))
        network = next(i for i, c in enumerate(calls) if c.startswith("network create"))
        self.assertLess(build, network)
        self.assertNotIn("--network", calls[build])
        self.assertIn("--internal", calls[network])

    def test_local_only_files_are_hidden_from_the_test_container(self):
        self.fake_docker()
        self.assertEqual(self.run_script("pg").returncode, 0)
        steps = [c for c in self.calls() if "python -B manage.py" in c]
        names = hidden_files_present()
        for step in steps:
            for name in names:
                self.assertIn(f"-v /dev/null:/repo/django_core/{name}:ro", step)
            if (APP_DIR / ".venv").is_dir():
                self.assertIn("--tmpfs /repo/django_core/.venv:ro,size=64k", step)
            # only existing files are overlaid (a missing mount point cannot be created in a read-only mount)
            for name in HIDDEN_FILES:
                if not (APP_DIR / name).exists():
                    self.assertNotIn(f"/repo/django_core/{name}", step)
            self.assertIn("-e EIP_TEST_CONTAINER=1", step)
            self.assertIn("-e EIP_TEST_STRICT_GATEWAY", step)
        pg_start = next(c for c in self.calls() if c.startswith("run -d "))
        self.assertNotIn("EIP_TEST_CONTAINER", pg_start)
        self.assertNotIn("/repo/", pg_start)  # the database container mounts nothing from the repository

    # ---- traps: the temporary build context, INT and TERM
    def test_a_failed_build_exits_3_and_removes_the_build_context(self):
        self.fake_docker(build=True)
        result = self.run_script("pg")
        self.assertEqual(result.returncode, 3)
        self.assertIn("building", result.stderr)
        self.assertEqual(list(self.tmpdir.iterdir()), [])
        self.assertFalse([c for c in self.calls() if c.startswith(("network", "run"))])

    def run_and_signal(self, sig, wait_for):
        proc = subprocess.Popen(
            ["/bin/bash", str(SCRIPT), "pg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={"PATH": str(self.bin), "HOME": self.tmp.name, "TMPDIR": str(self.tmpdir)}, start_new_session=True)
        deadline = time.time() + 30
        while time.time() < deadline and not any(c.startswith(wait_for) or wait_for in c for c in self.calls()):
            time.sleep(0.05)
        self.assertTrue(any(wait_for in c for c in self.calls()), "the awaited docker call never happened")
        time.sleep(0.2)
        os.killpg(proc.pid, sig)
        try:
            proc.communicate(timeout=30)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
        return proc.returncode

    def test_sigint_during_the_build_exits_130_and_removes_the_build_context(self):
        self.tmpdir = Path(self.tmp.name) / "tmpdir"
        self.tmpdir.mkdir(exist_ok=True)
        self.fake_docker(sleep_build=True)
        self.assertEqual(self.run_and_signal(signal.SIGINT, "build "), 130)
        self.assertEqual(list(self.tmpdir.iterdir()), [])
        self.assertFalse([c for c in self.calls() if c.startswith("network")])

    def test_sigterm_during_the_test_run_exits_143_and_removes_container_and_network(self):
        self.tmpdir = Path(self.tmp.name) / "tmpdir"
        self.tmpdir.mkdir(exist_ok=True)
        self.fake_docker(sleep_test=True)
        self.assertEqual(self.run_and_signal(signal.SIGTERM, "manage.py test"), 143)
        calls = self.calls()
        self.assertTrue(any(c.startswith("rm -f eip-test-pg-") for c in calls))
        self.assertTrue(any(c.startswith("network rm eip-test-net-") for c in calls))
        self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_the_cleanup_removes_the_build_context_variable_only_when_it_is_a_directory(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^CTX=""$')
        self.assertIn('if [ -n "${CTX:-}" ] && [ -d "$CTX" ]; then rm -rf -- "$CTX"; fi', text)
        self.assertIn("trap cleanup_pg EXIT", text)
        self.assertIn("trap 'exit 130' INT", text)
        self.assertIn("trap 'exit 143' TERM", text)


# ---- parsers for /proc/net/route and /proc/net/ipv6_route (sample-tested on the host, used inside the container)
def ipv4_routes(text):
    """[(network, prefix_len, gateway, iface)] from /proc/net/route (little-endian hex fields)."""
    routes = []
    for line in text.strip().splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8:
            continue
        iface, dest, gateway, mask = fields[0], fields[1], fields[2], fields[7]
        net = ipaddress.ip_address(socket.inet_ntoa(struct.pack("<L", int(dest, 16))))
        prefix = bin(int(mask, 16)).count("1")
        routes.append((ipaddress.ip_network(f"{net}/{prefix}", strict=False), prefix,
                       socket.inet_ntoa(struct.pack("<L", int(gateway, 16))), iface))
    return routes


def has_ipv4_default_route(text):
    return any(prefix == 0 for _net, prefix, _gw, _iface in ipv4_routes(text))


def has_ipv6_default_route(text):
    """A default route through a real device; the kernel's 'reject' placeholder routes on lo are not routes."""
    for line in text.strip().splitlines():
        fields = line.split()
        if len(fields) < 10:
            continue
        dest, prefix, flags, iface = fields[0], int(fields[1], 16), int(fields[8], 16), fields[9]
        if dest == "0" * 32 and prefix == 0 and iface != "lo" and not flags & 0x0200:
            return True
    return False


# observed with Docker 29.9.0, 2026-10-22: an INTERNAL network (172.22.0.0/16, gateway field 172.22.0.1) and a normal one
ROUTE_INTERNAL = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eth0\t000016AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0
"""
ROUTE_NORMAL = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eth0\t00000000\t010017AC\t0003\t0\t0\t0\t00000000\t0\t0\t0
eth0\t000017AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0
"""
IPV6_PLACEHOLDERS = """00000000000000000000000000000000 00 00000000000000000000000000000000 00 00000000000000000000000000000000 ffffffff 00000001 00000000 00200200       lo
00000000000000000000000000000001 80 00000000000000000000000000000000 00 00000000000000000000000000000000 00000000 00000004 00000000 80200001       lo
"""
IPV6_REAL_DEFAULT = IPV6_PLACEHOLDERS + "00000000000000000000000000000000 00 fe800000000000000000000000000001 00 00000000000000000000000000000000 00000400 00000001 00000000 00000003     eth0\n"


class RouteParserTests(SimpleTestCase):
    """The parsers behind the container-only network test, on real /proc/net samples: the test cannot pass vacuously."""

    def test_internal_network_has_no_default_route_and_one_on_link_subnet(self):
        routes = ipv4_routes(ROUTE_INTERNAL)
        self.assertFalse(has_ipv4_default_route(ROUTE_INTERNAL))
        self.assertEqual([(str(net), iface) for net, _p, _g, iface in routes], [("172.22.0.0/16", "eth0")])

    def test_a_normal_network_has_a_default_route(self):
        self.assertTrue(has_ipv4_default_route(ROUTE_NORMAL))
        self.assertEqual(sorted(str(net) for net, *_ in ipv4_routes(ROUTE_NORMAL)), ["0.0.0.0/0", "172.23.0.0/16"])

    def test_ipv6_placeholder_routes_on_lo_are_not_a_default_route_but_a_real_one_is(self):
        self.assertFalse(has_ipv6_default_route(IPV6_PLACEHOLDERS))
        self.assertTrue(has_ipv6_default_route(IPV6_REAL_DEFAULT))

    def test_empty_or_garbage_tables_have_no_default_route(self):
        for text in ("", "Iface\tDestination\n", "garbage\nmore garbage\n"):
            self.assertFalse(has_ipv4_default_route(text))
            self.assertFalse(has_ipv6_default_route(text))


@unittest.skipUnless(os.environ.get("EIP_TEST_CONTAINER") == "1", "runs only inside the PostgreSQL test container")
class InsideTheTestContainerTests(SimpleTestCase):
    """Executed by `scripts/run_tests.sh pg` INSIDE the container: the isolation really holds."""

    UNREACHABLE = (errno.ENETUNREACH, errno.EHOSTUNREACH)
    OFF_LINK_PROBES = (("1.1.1.1", 53), ("8.8.8.8", 53), ("169.254.169.254", 80), ("172.17.0.1", 22),
                       ("10.0.0.1", 53), ("192.168.1.1", 53), ("172.16.0.1", 53))
    GATEWAY_PORTS = (22, 80, 443, 5432, 6379, 8000, 8001, 9000, 11434)

    def own_networks(self):
        return [net for net, prefix, _gw, _iface in ipv4_routes(Path("/proc/net/route").read_text()) if prefix > 0]

    def test_there_is_no_default_route(self):
        """U1: the strongest, version-independent proof of --internal: nothing routes beyond the own subnet."""
        self.assertFalse(has_ipv4_default_route(Path("/proc/net/route").read_text()), "IPv4 default route present")
        self.assertFalse(has_ipv6_default_route(Path("/proc/net/ipv6_route").read_text()), "IPv6 default route present")
        self.assertEqual(len(self.own_networks()), 1, "expected exactly one connected subnet")

    def test_off_link_addresses_are_unreachable_not_merely_unanswered(self):
        """U1: only ENETUNREACH / EHOSTUNREACH count. A timeout or a refusal would also happen on an offline machine."""
        own = self.own_networks()
        probed = 0
        for host, port in self.OFF_LINK_PROBES:
            if any(ipaddress.ip_address(host) in net for net in own):
                continue  # an address on the own subnet is on-link, covered by the gateway test
            probed += 1
            with self.subTest(host=host):
                try:
                    socket.create_connection((host, port), timeout=3).close()
                except OSError as exc:
                    self.assertIn(exc.errno, self.UNREACHABLE, f"{host}:{port} -> {exc!r}")
                else:
                    self.fail(f"{host}:{port} is reachable")
        self.assertGreaterEqual(probed, 5)

    def test_dns_resolves_the_database_container_and_nothing_else(self):
        """U1 positive control: name resolution works for the test network, and an external name fails to resolve."""
        host = os.environ["TEST_PG_HOST"]
        infos = socket.getaddrinfo(host, 5432, type=socket.SOCK_STREAM)
        self.assertTrue(infos, "the database container name must resolve")
        address = ipaddress.ip_address(infos[0][4][0])
        self.assertTrue(any(address in net for net in self.own_networks()), "the database is on the own subnet")
        with self.assertRaises(socket.gaierror) as ctx:
            socket.getaddrinfo("example.org", 80)
        self.assertIn(ctx.exception.errno, (socket.EAI_AGAIN, socket.EAI_NONAME), repr(ctx.exception))

    def test_the_database_container_is_reachable_over_tcp(self):
        """U1 positive control: --internal does not break container-to-container traffic."""
        socket.create_connection((os.environ["TEST_PG_HOST"], 5432), timeout=10).close()

    def test_gateway_observation_is_recorded_and_strict_mode_can_forbid_any_host_service(self):
        """U2. The gateway address of an internal network is ON-LINK: a connection to it is answered (REFUSED or
        CONNECTED), not "unreachable". So a service the host binds to all interfaces is reachable from the test
        container even on an --internal network. OBSERVED with Docker 29.9.0 on the development machine (2026-10-22):
        172.22.0.1 answers; ports 22, 80, 443, 5432, 6379, 8000, 8001, 9000 are REFUSED; 11434 (the host's Ollama,
        listening on *:11434) CONNECTS. No workaround is built (see Change Report 0012). This test records the outcome in
        its output and fails only when EIP_TEST_STRICT_GATEWAY=1 is set on the host (passed through by the script) and a
        host service answers."""
        gateways = {net.network_address + 1 for net in self.own_networks()}
        self.assertTrue(gateways)
        connected, refused, other = [], [], []
        for gateway in sorted(gateways):
            for port in self.GATEWAY_PORTS:
                try:
                    socket.create_connection((str(gateway), port), timeout=3).close()
                    connected.append(f"{gateway}:{port}")
                except OSError as exc:
                    (refused if exc.errno == errno.ECONNREFUSED else other).append(
                        f"{gateway}:{port}={errno.errorcode.get(exc.errno, type(exc).__name__)}")
        sys.stderr.write(f"\nGATEWAY OBSERVATION (U2): connected={connected} refused={len(refused)} other={other}\n")
        self.assertEqual(len(connected) + len(refused) + len(other), len(gateways) * len(self.GATEWAY_PORTS))
        if os.environ.get("EIP_TEST_STRICT_GATEWAY") == "1":
            self.assertEqual(connected, [], "a host service answers on the network gateway from inside the test container")

    def test_local_only_files_are_not_visible(self):
        app = Path("/repo/django_core")
        for name in HIDDEN_FILES:
            path = app / name
            if path.exists():
                self.assertEqual(path.stat().st_size, 0, f"{name} is visible")
                self.assertEqual(path.read_bytes(), b"")
        for path in app.glob(".env*"):
            self.assertEqual(path.stat().st_size, 0, f"{path.name} is visible")
        venv = app / ".venv"
        if venv.exists():
            self.assertEqual(list(venv.iterdir()), [], ".venv is visible")

    def test_the_repository_root_is_not_mounted(self):
        for name in (".env", ".env.fastapi", "data", "docs", ".git"):
            self.assertFalse(Path("/repo", name).exists(), name)
        self.assertEqual(sorted(p.name for p in Path("/repo").iterdir()), ["django_core", "scripts"])

    def test_the_source_is_read_only(self):
        with self.assertRaises(OSError):
            (Path("/repo/django_core") / "_write_probe").write_text("x")
