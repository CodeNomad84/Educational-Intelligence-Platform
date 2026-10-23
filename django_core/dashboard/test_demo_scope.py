"""Outside the demo settings the demo_intel pages do not exist at all (not installed, no routes, no dashboard hook)."""
from django.conf import settings
from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class DemoIsOffOutsideDemoSettingsTests(TestCase):
    def test_demo_app_and_routes_are_absent(self):
        if getattr(settings, 'DEMO_MODE', False):
            self.skipTest('demo settings: the demo pages exist here by design')
        self.assertNotIn('demo_intel', settings.INSTALLED_APPS)
        for name in ('demo_counselor', 'demo_students', 'demo_assistant'):
            with self.assertRaises(NoReverseMatch):
                reverse(f'dashboard:{name}')
        for path in ('/demo/counselor/', '/demo/students/', '/demo/assistant/'):
            self.assertEqual(self.client.get(path).status_code, 404, path)
