"""C-H (P3): project deploy checks, self-hosted assets and the production settings. Synthetic values only; the secret key of the
subprocess test is generated per run and never stored."""
import os
import secrets
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from . import deploy_checks as dc


def ids(messages):
    return sorted(m.id for m in messages)


class TemplateAssetTests(TestCase):
    def test_no_first_party_template_loads_an_external_asset(self):
        self.assertEqual(dc.external_asset_references(), [])

    def test_patterns(self):
        for line in ('<script src="https://cdn.jsdelivr.net/x.js">', "<link rel='stylesheet' href='//cdn.example/x.css'>",
                     '<img src=http://x.ir/a.png>', '@import url("https://fonts.googleapis.com/css")', 'src: url(//x/f.woff2)'):
            self.assertTrue(dc.EXTERNAL_ASSET.search(line) or dc.EXTERNAL_CSS.search(line), line)
        for line in ('<a href="https://docs.example.ir">help</a>', '<script src="/static/x.js">', "url('/static/f.woff2')"):
            self.assertFalse(dc.EXTERNAL_ASSET.search(line) or dc.EXTERNAL_CSS.search(line), line)

    def test_pages_use_the_local_copies(self):
        page = self.client.get('/login/').content.decode()
        self.assertNotIn('cdn.jsdelivr', page)
        if 'bootstrap' in page:
            self.assertIn('/static/dashboard/vendor/bootstrap-5.3.0/', page)
        for path in ('bootstrap-5.3.0/bootstrap.rtl.min.css', 'bootstrap-5.3.0/bootstrap.bundle.min.js', 'vazirmatn-33.0.3/Vazirmatn-FD-Regular.woff2',
                     'bootstrap-icons-1.11.3/bootstrap-icons.min.css', 'bootstrap-icons-1.11.3/fonts/bootstrap-icons.woff2',
                     'chartjs-4.4.1/chart.umd.js'):
            self.assertTrue((settings.BASE_DIR / 'dashboard/static/dashboard/vendor' / path).is_file(), path)


class SettingChecksTests(SimpleTestCase):
    @override_settings(ALLOWED_HOSTS=['school.example.ir'], CSRF_TRUSTED_ORIGINS=['https://school.example.ir'],
                       SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
                       SECURE_HSTS_SECONDS=31536000)
    def test_good(self):
        self.assertEqual(dc.check_hosts_and_origins(None), [])

    def test_bad_hosts(self):
        for hosts in ([], ['*'], ['localhost', '127.0.0.1'], ['school.example.ir', '*']):
            with self.subTest(hosts=hosts), override_settings(ALLOWED_HOSTS=hosts, CSRF_TRUSTED_ORIGINS=[]):
                self.assertIn('eip.E001', ids(dc.check_hosts_and_origins(None)))

    @override_settings(ALLOWED_HOSTS=['a.ir'], CSRF_TRUSTED_ORIGINS=['https://a.ir', 'http://a.ir'])
    def test_plain_http_origin(self):
        self.assertIn('eip.E002', ids(dc.check_hosts_and_origins(None)))

    @override_settings(ALLOWED_HOSTS=['a.ir'], SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=None)
    def test_redirect_without_proxy_header(self):
        self.assertIn('eip.W003', ids(dc.check_hosts_and_origins(None)))

    @override_settings(ALLOWED_HOSTS=['a.ir'], SECURE_HSTS_SECONDS=3600)
    def test_staged_hsts_is_info_only(self):
        self.assertEqual(ids(dc.check_hosts_and_origins(None)), ['eip.I006'])

    def test_empty_postgres_password(self):
        engine = 'django.db.backends.postgresql'
        self.assertEqual(ids(dc.database_password_errors({'ENGINE': engine, 'PASSWORD': ''})), ['eip.E005'])
        self.assertEqual(dc.database_password_errors({'ENGINE': engine, 'PASSWORD': 'x'}), [])
        self.assertEqual(dc.database_password_errors({'ENGINE': 'django.db.backends.sqlite3'}), [])


class ProductionSettingsTests(SimpleTestCase):
    """The real production settings pass `check --deploy --fail-level WARNING` with complete values and fail without them."""

    def run_check(self, **extra):
        env = {'PATH': os.environ.get('PATH', ''), 'DJANGO_SETTINGS_MODULE': 'config.settings.production',
               'SECRET_KEY': secrets.token_urlsafe(50), 'ALLOWED_HOSTS': 'school.example.ir',
               'CSRF_TRUSTED_ORIGINS': 'https://school.example.ir', 'DB_PASSWORD': secrets.token_urlsafe(12)}
        env.update(extra)
        return subprocess.run([sys.executable, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING'],
                              cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120)

    def test_complete_configuration_passes(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('eip.I006', result.stdout + result.stderr)       # default HSTS is the staged first step

    def test_missing_values_fail(self):
        result = self.run_check(ALLOWED_HOSTS='localhost', CSRF_TRUSTED_ORIGINS='http://school.example.ir', DB_PASSWORD='')
        self.assertNotEqual(result.returncode, 0)
        for code in ('eip.E001', 'eip.E002', 'eip.E005'):
            self.assertIn(code, result.stdout + result.stderr)
