"""scripts/preflight.py (P9): the deployment preflight refuses weak or unfilled environments and never prints a value."""
import contextlib
import importlib.util
import io
import secrets
import tempfile
import unittest
from pathlib import Path

from django.conf import settings

SCRIPT = Path(settings.BASE_DIR).parent / 'scripts' / 'preflight.py'
PROFILES = Path(settings.BASE_DIR).parent / 'deploy' / 'profiles'


@unittest.skipUnless(SCRIPT.exists(), 'repository root not mounted (container run)')
class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('preflight', SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def good(self, **over):
        env = {'SECRET_KEY': secrets.token_urlsafe(60), 'SERVICE_JWT_SECRET': secrets.token_urlsafe(40),
               'DB_ADMIN_PASSWORD': secrets.token_urlsafe(20), 'DB_OWNER_PASSWORD': secrets.token_urlsafe(20),
               'DB_APP_PASSWORD': secrets.token_urlsafe(20), 'ALLOWED_HOSTS': 'platform.real-school.ir',
               'CSRF_TRUSTED_ORIGINS': 'https://platform.real-school.ir', 'EIP_BACKUP_PUBKEY': '/etc/eip/k.asc'}
        env.update(over)
        return env

    def test_a_filled_environment_is_ready(self):
        self.assertEqual(self.mod.check(self.good()), [])

    def test_each_weakness_is_a_problem(self):
        same = secrets.token_urlsafe(30)
        cases = {'placeholder': {'SECRET_KEY': 'CHANGE_ME_' + 'x' * 60}, 'short secret': {'SERVICE_JWT_SECRET': 'abc'},
                 'equal passwords': {'DB_OWNER_PASSWORD': same, 'DB_APP_PASSWORD': same}, 'debug': {'DEBUG': 'True'},
                 'wildcard host': {'ALLOWED_HOSTS': '*'}, 'localhost': {'ALLOWED_HOSTS': 'localhost'},
                 'http origin': {'CSRF_TRUSTED_ORIGINS': 'http://platform.real-school.ir'}, 'no backup key': {'EIP_BACKUP_PUBKEY': ''},
                 'ssl redirect off': {'SECURE_SSL_REDIRECT': '0'}, 'superuser app role': {'DB_USER': 'school_user'}}
        for label, over in cases.items():
            self.assertTrue(self.mod.check(self.good(**over)), label)
        self.assertTrue(self.mod.check(self.good(ALLOWED_HOSTS='a.real.ir,b.real.ir,c.real.ir'), 'dedicated'))
        self.assertTrue(self.mod.check({}), 'empty')

    def test_the_shipped_profile_examples_cannot_be_used_unfilled_and_output_has_no_values(self):
        for name in ('shared-iranian-server.env.example', 'dedicated-school-server.env.example'):
            env = self.mod.parse(PROFILES / name)
            self.assertTrue(self.mod.check(env), name)
        with tempfile.NamedTemporaryFile('w', suffix='.env', delete=False) as fh:
            fh.write('SECRET_KEY=VERY-SECRET-VALUE-123\nDEBUG=True\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.mod.main(['preflight', fh.name])
        self.assertEqual(code, 1)
        self.assertNotIn('VERY-SECRET-VALUE', out.getvalue())
        Path(fh.name).unlink()
