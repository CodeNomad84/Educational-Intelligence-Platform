"""Token-contrast guard (0037b): parse the ``:root`` custom properties of ``eip.css`` and assert the
real foreground/background pairs against the WCAG 2.x thresholds (4.5:1 text, 3:1 non-text/graphics).
Pure arithmetic, no browser, no dependency.

The six pairs that still fail today are listed explicitly in ``EXPECTED_FAILURES`` and are asserted to
*still* be below threshold; 0037c fixes them, at which point that regression marker fails and the pair
is moved up into ``PASSING_TEXT``/``PASSING_GRAPHIC``. The card border is decorative and is recorded as
exempt, not a failure.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / 'dashboard/static/dashboard/css/eip.css'

# Text pairs that must be >= 4.5:1 (WCAG 1.4.3). Referenced by :root token name.
PASSING_TEXT = [
    ('body ink on page bg', '--eip-ink', '--eip-bg'),
    ('ink-2 on page bg', '--eip-ink-2', '--eip-bg'),
    ('primary on surface', '--eip-primary', '--eip-surface'),
    ('primary-ink on primary-soft', '--eip-primary-ink', '--eip-primary-soft'),
    ('success on success-soft', '--eip-success', '--eip-success-soft'),
    ('warning on warning-soft', '--eip-warning', '--eip-warning-soft'),
    ('danger on danger-soft', '--eip-danger', '--eip-danger-soft'),
    ('info on info-soft', '--eip-info', '--eip-info-soft'),
    ('neutral on neutral-soft', '--eip-neutral', '--eip-neutral-soft'),
]

# Explicit expected-failure list (resolved in 0037c / T5). (name, fg hex, bg hex, threshold).
EXPECTED_FAILURES = [
    ('muted on surface-2 (text)', '#6b7686', '#f8fafc', 4.5),
    ('muted on page bg (text)', '#6b7686', '#f4f6fa', 4.5),
    ('eip-soon pill (text)', '#6b7686', '#e3e8ef', 4.5),
    ('warning meter fill (graphic)', '#e0a43a', '#eef1f5', 3.0),
    ('input border on white (graphic)', '#cfd6e1', '#ffffff', 3.0),
    ('focus ring on white (graphic)', '#9cb3df', '#ffffff', 3.0),  # rgba(36,87,184,.45) blended on white
]

# Decorative non-text edges, intentionally below 3:1 (exempt, not a failure).
DECORATIVE_EXEMPT = [
    ('card border on page bg', '#e3e8ef', '#f4f6fa'),
]


def _tokens():
    text = CSS.read_text(encoding='utf-8')
    m = re.search(r':root\s*\{(.*?)\}', text, re.S)
    tokens = {}
    for name, val in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', m.group(1)):
        val = val.strip().lower()
        if re.fullmatch(r'#[0-9a-f]{3}(?:[0-9a-f]{3})?', val):
            tokens[name] = val
    return tokens


def _hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def chan(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _ratio(fg, bg):
    l1, l2 = _luminance(_hex_to_rgb(fg)), _luminance(_hex_to_rgb(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


class ContrastTokenTests(SimpleTestCase):
    def test_passing_text_pairs_meet_4_5(self):
        tokens = _tokens()
        for name, fg, bg in PASSING_TEXT:
            self.assertIn(fg, tokens, f'missing token {fg}')
            self.assertIn(bg, tokens, f'missing token {bg}')
            ratio = _ratio(tokens[fg], tokens[bg])
            self.assertGreaterEqual(ratio, 4.5, f'{name}: {ratio:.2f}')

    def test_expected_failures_still_below_threshold(self):
        # Regression marker: these must stay below threshold until 0037c fixes them; when one is
        # fixed this fails, reminding us to move it into PASSING_TEXT / PASSING_GRAPHIC.
        for name, fg, bg, threshold in EXPECTED_FAILURES:
            ratio = _ratio(fg, bg)
            self.assertLess(ratio, threshold, f'{name} now passes ({ratio:.2f} >= {threshold}); move it up')

    def test_decorative_border_recorded(self):
        for name, fg, bg in DECORATIVE_EXEMPT:
            self.assertLess(_ratio(fg, bg), 3.0, f'{name} is no longer below 3:1; review the exemption')
