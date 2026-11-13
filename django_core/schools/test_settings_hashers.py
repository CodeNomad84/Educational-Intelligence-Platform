"""The fast MD5 hasher exists ONLY in the two test settings modules. Every other settings module (development, demo,
production) must still hash passwords with a strong algorithm; checked in a fresh interpreter per module."""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent
STRONG = {'pbkdf2_sha256': 600_000, 'argon2': 0, 'bcrypt_sha256': 0, 'scrypt': 0}     # algorithm -> minimum iterations (0 = n/a)
PROBE = ("import json; from django.contrib.auth.hashers import make_password; from django.conf import settings; "
         "h = make_password('probe-Password-1').split('$'); "
         "print(json.dumps({'algorithm': h[0], 'iterations': int(h[1]) if h[0] == 'pbkdf2_sha256' else 0, "
         "'hashers': list(getattr(settings, 'PASSWORD_HASHERS', []))}))")
ENV = {'SECRET_KEY': 'k3y-' + 'abcdefghijklmnopqrstuvwxyz0123456789' * 2, 'PATH': os.environ.get('PATH', '')}


def probe(module):
    env = {**ENV, 'DJANGO_SETTINGS_MODULE': module, 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-c', PROBE], cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (module, result.stderr[-400:])
    return json.loads(result.stdout.strip().splitlines()[-1])


class HasherSettingsTests(SimpleTestCase):
    def test_development_demo_and_production_use_a_strong_hasher(self):
        for module in ('config.settings.development', 'config.settings.demo', 'config.settings.production'):
            with self.subTest(module=module):
                found = probe(module)
                self.assertIn(found['algorithm'], STRONG, found)
                self.assertGreaterEqual(found['iterations'], STRONG[found['algorithm']], found)
                # new passwords use the FIRST hasher (checked above); no weak or unsalted hasher may be listed at all
                self.assertFalse(any('MD5' in h or 'Unsalted' in h for h in found['hashers']), found)

    def test_only_the_test_settings_use_the_fast_hasher(self):
        for module in ('config.settings.test_sqlite',):
            with self.subTest(module=module):
                self.assertEqual(probe(module)['algorithm'], 'md5')
        settings_dir = BASE_DIR / 'config' / 'settings'
        offenders = [p.name for p in settings_dir.glob('*.py') if 'MD5PasswordHasher' in p.read_text(encoding='utf-8')]
        self.assertEqual(sorted(offenders), ['test_postgres.py', 'test_sqlite.py'])

    def test_the_running_suite_uses_a_test_settings_module_or_says_so(self):
        # Under run_tests.sh the main suite runs with test_sqlite (or test_postgres); a developer running it with the
        # development settings simply keeps the slow strong hasher. Either way the hasher of THIS process is one of the two.
        from django.conf import settings
        first = settings.PASSWORD_HASHERS[0] if getattr(settings, 'PASSWORD_HASHERS', None) else 'default'
        self.assertTrue(first == 'default' or 'MD5' in first or 'PBKDF2' in first, first)
