"""T3 (0037a) rendered acceptance: 0 unnamed form controls and 0 ``<th>`` without ``scope`` on the
pages each demo role can reach. Synthetic data only (``seed_demo_school``). The 0037b batch extends
this walk with distinct titles, heading-order and duplicate-id checks (0037 §7).
"""
from html.parser import HTMLParser
from io import StringIO
from urllib.parse import urljoin, urlsplit

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

ROLE_HOME = [
    ('demo_admin', 'dashboard:dashboard'),
    ('demo_lead7', 'dashboard:grade_dashboard'),
    ('demo_teacher7a', 'dashboard:teacher_home'),
    ('demo_counselor', 'dashboard:counselor_home'),
    ('demo_parent1', 'dashboard:student_list'),
    ('demo_student', 'dashboard:me_home'),
]
CONTROL_TAGS = {'input', 'select', 'textarea', 'button'}


class _Probe(HTMLParser):
    """Collects ``<th>`` cells, form controls, headings, ids and the title from one page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.th = []
        self.controls = []
        self.labels = []
        self.headings = []
        self.ids = []
        self.title = ''
        self._in_label = 0
        self._in_title = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'th':
            self.th.append(attrs)
        if tag == 'label':
            self._in_label += 1
            self.labels.append({'for': attrs.get('for'), 'text': ''})
        if tag in CONTROL_TAGS:
            self.controls.append({'tag': tag, 'attrs': attrs, 'text': '', 'in_label': self._in_label > 0})
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.headings.append(int(tag[1]))
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'title':
            self._in_title += 1

    def handle_endtag(self, tag):
        if tag == 'label':
            self._in_label = max(0, self._in_label - 1)
        if tag == 'title':
            self._in_title = max(0, self._in_title - 1)

    def handle_data(self, data):
        if self._in_label and self.labels:
            self.labels[-1]['text'] += data
        if self.controls:
            self.controls[-1]['text'] += data
        if self._in_title:
            self.title += data


def _heading_skips(headings):
    """Document-order heading levels that leap more than one level up (e.g. h1 -> h3)."""
    skips, prev = [], 0
    for level in headings:
        if prev and level > prev + 1:
            skips.append((prev, level))
        prev = level
    return skips


def _named(control, labels):
    attrs = control['attrs']
    if (attrs.get('aria-label') or '').strip() or (attrs.get('aria-labelledby') or '').strip():
        return True
    cid = attrs.get('id')
    if cid and any(l['for'] == cid and l['text'].strip() for l in labels):
        return True
    if control['in_label'] or (attrs.get('title') or '').strip():
        return True
    if control['tag'] == 'button':
        return bool(control['text'].strip())
    if control['tag'] == 'input' and (attrs.get('type') or 'text').lower() in ('submit', 'button', 'reset', 'image'):
        return bool(attrs.get('value') or attrs.get('alt'))
    return False


class _LinkProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.append(dict(attrs).get('href'))


def _links(html, base_path):
    out = []
    for href in _feed(_LinkProbe(), html).hrefs:
        href = (href or '').strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        parts = urlsplit(href)
        if parts.scheme or parts.netloc:
            continue
        url = urljoin(base_path, href.split('?')[0])
        if '/logout' in url or url == '/':
            continue
        out.append(url)
    return out


def _feed(parser, html):
    parser.feed(html)
    return parser


BARE_TITLE = 'پلتفرم هوشمند مدرسه'


class A11yRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_school', '--i-know-this-is-synthetic', '--password=x-demo-pass',
                     '--scale=0.2', stdout=StringIO())

    def _walk(self, username, home):
        self.client.force_login(User.objects.get(username=username))
        seen, queue = set(), [(reverse(home), 0)]
        bad_th, bad_ctrl, bad_title, bad_heading, bad_id = [], [], [], [], []
        while queue and len(seen) < 40:
            path, depth = queue.pop(0)
            if path in seen:
                continue
            seen.add(path)
            resp = self.client.get(path)
            if resp.status_code != 200:
                continue
            html = resp.content.decode('utf-8', 'replace')
            probe = _feed(_Probe(), html)
            bad_th += [f'{path}: <th ...>' for th in probe.th if 'scope' not in th]
            for c in probe.controls:
                if c['attrs'].get('type') == 'hidden':
                    continue
                if not _named(c, probe.labels):
                    bad_ctrl.append(f'{path}: <{c["tag"]}>')
            if not probe.title.strip() or probe.title.strip() == BARE_TITLE:
                bad_title.append(f'{path}: {probe.title.strip()!r}')
            bad_heading += [f'{path}: {a}->{b}' for a, b in _heading_skips(probe.headings)]
            dups = sorted({i for i in probe.ids if probe.ids.count(i) > 1})
            if dups:
                bad_id.append(f'{path}: {dups}')
            if depth < 2:
                queue += [(l, depth + 1) for l in _links(html, path) if l not in seen]
        return bad_th, bad_ctrl, bad_title, bad_heading, bad_id

    def _collect(self, idx):
        out = []
        for username, home in ROLE_HOME:
            out += self._walk(username, home)[idx]
        return sorted(set(out))

    def _assert_empty(self, idx, label):
        offenders = self._collect(idx)
        self.assertEqual(offenders, [], f'{label}:\n' + '\n'.join(offenders))

    def test_no_th_without_scope(self):
        self._assert_empty(0, 'th without scope')

    def test_no_unnamed_controls(self):
        self._assert_empty(1, 'unnamed controls')

    def test_page_titles_are_distinct(self):
        self._assert_empty(2, 'pages with a bare/empty title')

    def test_no_heading_skips(self):
        self._assert_empty(3, 'heading level skips')

    def test_no_duplicate_ids(self):
        self._assert_empty(4, 'duplicate ids')
