"""Token-contrast guard (0037): parse the ``:root`` custom properties of ``eip.css`` and assert the real
foreground/background pairs against the WCAG 2.x thresholds (4.5:1 text, 3:1 non-text/graphics). Pure
arithmetic, no browser, no dependency. The card border is decorative and is recorded as exempt.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / 'dashboard/static/dashboard/css/eip.css'

# Text pairs that must be >= 4.5:1 (WCAG 1.4.3). A ``--foo`` value resolves from :root; otherwise hex.
PASSING_TEXT = [
    ('body ink on page bg', '--eip-ink', '--eip-bg'),
    ('ink-2 on page bg', '--eip-ink-2', '--eip-bg'),
    ('muted on page bg', '--eip-muted', '--eip-bg'),
    ('muted on surface-2', '--eip-muted', '--eip-surface-2'),
    ('primary on surface', '--eip-primary', '--eip-surface'),
    ('primary-ink on primary-soft', '--eip-primary-ink', '--eip-primary-soft'),
    ('eip-soon pill (ink-2 on border)', '--eip-ink-2', '--eip-border'),
    ('success on success-soft', '--eip-success', '--eip-success-soft'),
    ('warning on warning-soft', '--eip-warning', '--eip-warning-soft'),
    ('danger on danger-soft', '--eip-danger', '--eip-danger-soft'),
    ('info on info-soft', '--eip-info', '--eip-info-soft'),
    ('neutral on neutral-soft', '--eip-neutral', '--eip-neutral-soft'),
]

# Non-text / graphic pairs that must be >= 3:1 (WCAG 1.4.11).
PASSING_GRAPHIC = [
    ('warning meter fill on track', '#b8791f', '--eip-neutral-soft'),
    ('input border on surface', '--eip-border-strong', '--eip-surface'),
    ('focus ring on surface', '#2457b8', '#ffffff'),
]

# Decorative non-text edges, intentionally below 3:1 (exempt, not a failure).
DECORATIVE_EXEMPT = [
    ('card border on page bg', '--eip-border', '--eip-bg'),
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


def _resolve(value, tokens):
    return tokens[value] if value.startswith('--') else value


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
            ratio = _ratio(_resolve(fg, tokens), _resolve(bg, tokens))
            self.assertGreaterEqual(ratio, 4.5, f'{name}: {ratio:.2f}')

    def test_passing_graphic_pairs_meet_3_0(self):
        tokens = _tokens()
        for name, fg, bg in PASSING_GRAPHIC:
            ratio = _ratio(_resolve(fg, tokens), _resolve(bg, tokens))
            self.assertGreaterEqual(ratio, 3.0, f'{name}: {ratio:.2f}')

    def test_decorative_border_recorded(self):
        tokens = _tokens()
        for name, fg, bg in DECORATIVE_EXEMPT:
            ratio = _ratio(_resolve(fg, tokens), _resolve(bg, tokens))
            self.assertLess(ratio, 3.0, f'{name} is no longer below 3:1; review the exemption')

