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
