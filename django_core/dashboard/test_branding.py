"""T10 branding: the product name lives in settings and is rendered, never typed into a template.

Why a test: the name used to be the literal ``پلتفرم هوشمند مدرسه`` in three templates and in the a11y
test's expected bare title. A release gate that changes the brand must not leave a stale copy behind, and
the next school must not have to edit templates. Synthetic data only; no fixtures needed.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.html import escape

# The pre-T10 literals. They must not come back: the name comes from settings.PLATFORM_NAME.
LEGACY_NAMES = ('پلتفرم هوشمند مدرسه', 'به پلتفرم مدرسه')
TEMPLATE_APPS = ('dashboard', 'demo_intel', 'exams', 'missions', 'risk', 'docqa', 'schools', 'students', 'interventions')


class BrandingSettingsTests(SimpleTestCase):
    def test_both_names_are_configured(self):
        self.assertTrue(settings.PLATFORM_NAME.strip(), 'PLATFORM_NAME is empty')
        self.assertTrue(settings.PLATFORM_NAME_EN.strip(), 'PLATFORM_NAME_EN is empty')

    def test_no_template_carries_the_name_as_a_literal(self):
        offenders, checked = [], 0
        for app in TEMPLATE_APPS:                 # by path, not by INSTALLED_APPS: demo_intel is demo-settings only
            root = Path(settings.BASE_DIR) / app / 'templates'
            for tpl in sorted(root.rglob('*.html')) if root.is_dir() else []:
                checked += 1
                text = tpl.read_text(encoding='utf-8')
                for legacy in LEGACY_NAMES:
                    if legacy in text:
                        offenders.append(f'{app}: {tpl.relative_to(root)} ({legacy})')
                if settings.PLATFORM_NAME in text:
                    offenders.append(f'{app}: {tpl.relative_to(root)} (hard-coded PLATFORM_NAME)')
        self.assertGreater(checked, 0, 'no templates were found: the scan is vacuous')
        self.assertEqual(offenders, [], 'brand literals in templates:\n' + '\n'.join(offenders))


class BrandingRenderTests(TestCase):
    def test_login_page_shows_the_platform_name_and_metadata(self):
        resp = self.client.get(reverse('dashboard:login'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn(f'<h1 class="h4 mb-1">{settings.PLATFORM_NAME}</h1>', html)
        self.assertIn('<meta name="application-name"', html)
        self.assertIn(escape(settings.PLATFORM_NAME_EN), html)   # <meta name="description"> (HTML-escaped: "&amp;")
        self.assertIn(f'<title>ورود — {settings.PLATFORM_NAME}</title>', html)
        for legacy in LEGACY_NAMES:
            self.assertNotIn(legacy, html)
