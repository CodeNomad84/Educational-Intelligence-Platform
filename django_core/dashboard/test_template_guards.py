"""Static guard (decision 48): ``|jdate`` produces 1405/08/10, which is NOT a valid value for ``<input type=date>``: it must never
appear inside a value=, min= or max= attribute (the picker and the browser need Gregorian ISO)."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ATTR = re.compile(r'''\b(?:value|min|max)\s*=\s*(["'])(?:(?!\1).)*\|\s*jdate(?:(?!\1).)*\1''', re.S)


class JdateNotInInputAttributesTests(SimpleTestCase):
    def test_no_template_puts_jdate_in_value_min_or_max(self):
        offenders = []
        for path in Path(settings.BASE_DIR).rglob('*.html'):
            if '.venv' in path.parts or 'staticfiles' in path.parts:
                continue
            if ATTR.search(path.read_text(encoding='utf-8')):
                offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(offenders, [])

# 0037b markup lint (docs/changes/0037-ux-audit-PROPOSAL.md §8, check 1): every <th> has scope,
# every Bootstrap icon is aria-hidden, every <canvas> has a name, every template extending
# base.html defines a title. Scoped to the audit's templates: dashboard + risk.
A11Y_RULES = {
    'th_without_scope': re.compile(r'<th\b(?![^>]*\bscope=)'),
    'icon_without_aria_hidden': re.compile(r'<i class="bi [^"]*"(?![^>]*aria-hidden)'),
    'canvas_without_name': re.compile(r'<canvas(?![^>]*(aria-label|role=))'),
}

A11Y_TEMPLATE_DIRS = ['dashboard/templates', 'risk/templates']


class A11yLintTests(SimpleTestCase):
    def _templates(self):
        base = Path(settings.BASE_DIR)
        for rel in A11Y_TEMPLATE_DIRS:
            d = base / rel
            if d.is_dir():
                yield from d.rglob('*.html')

    def _offenders(self, name):
        out = []
        for path in self._templates():
            text = path.read_text(encoding='utf-8')
            for m in A11Y_RULES[name].finditer(text):
                out.append(f'{path.relative_to(settings.BASE_DIR)}: {m.group(0)}')
        return out

    def test_th_have_scope(self):
        self.assertEqual(self._offenders('th_without_scope'), [])

    def test_icons_are_aria_hidden(self):
        self.assertEqual(self._offenders('icon_without_aria_hidden'), [])

    def test_canvases_have_a_name(self):
        self.assertEqual(self._offenders('canvas_without_name'), [])

    def test_extends_base_has_title(self):
        offenders = []
        for path in self._templates():
            text = path.read_text(encoding='utf-8')
            if "{% extends 'dashboard/base.html' %}" in text and '{% block title %}' not in text:
                offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(offenders, [])

