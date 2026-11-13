"""CSV import of exam questions (exams Slice 2): a dry-run parse that writes nothing, then an apply step that re-checks every
row against the database as it is NOW. Imported questions are always DRAFTS (``source='csv'``) of the importing teacher; they
need the usual approval before an exam can use them.

Columns (header row, any order, case-insensitive): ``topic`` (a topic code of the teacher's subject, e.g. math.ch3.fractions),
``stem``, ``correct`` (the number 1-5 of the right option) and for each option 1-5: ``o<i>_text`` and ``o<i>_expl``. An option
needs both its text and its explanation. Excel/Google Sheets export works (UTF-8, comma, semicolon or tab separated).
"""
import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from .models import Option, Question

MAX_BYTES = 200 * 1024
MAX_ROWS = 200
MAX_OPTIONS = 5
TEMPLATE_HEADER = ['topic', 'stem', 'correct'] + [c for i in range(1, MAX_OPTIONS + 1) for c in (f'o{i}_text', f'o{i}_expl')]


class BadFile(Exception):
    """The whole file is refused (size, encoding, header); nothing is parsed."""


@dataclass
class Row:
    line: int
    topic_code: str = ''
    topic_id: int | None = None
    stem: str = ''
    options: list = field(default_factory=list)      # [{'i': 1, 'text': .., 'explanation': ..}]
    correct: str = ''
    errors: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def as_session(self):
        return {'line': self.line, 'topic_code': self.topic_code, 'stem': self.stem, 'correct': self.correct,
                'options': self.options}


def template_csv():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(TEMPLATE_HEADER)
    writer.writerow(['math.ch3.fractions', 'حاصل ۱/۲ + ۱/۲ کدام است؟', '2', '۰', 'نه: این تفریق است.', '۱', 'درست: دو نیم یک کل است.',
                     '۲', 'نه: دو کل نمی‌شود.', '', '', '', ''])
    return '﻿' + out.getvalue()


def _rows(raw):
    if len(raw) > MAX_BYTES:
        raise BadFile('اندازهٔ فایل بیش از حد مجاز است.')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise BadFile('فایل باید UTF-8 باشد (در اکسل: Save as ← CSV UTF-8).') from None
    if not text.strip():
        raise BadFile('فایل خالی است.')
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = [h.strip().lower() for h in next(reader, [])]
    missing = [c for c in ('topic', 'stem', 'correct', 'o1_text', 'o1_expl', 'o2_text', 'o2_expl') if c not in header]
    if missing:
        raise BadFile('ستون‌های لازم در ردیف عنوان نیست: ' + '، '.join(missing))
    out = []
    for line, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        out.append((line, dict(zip(header, (c.strip() for c in cells)))))
    if len(out) > MAX_ROWS:
        raise BadFile(f'حداکثر {MAX_ROWS} ردیف در هر فایل.')
    if not out:
        raise BadFile('ردیف دادهٔ پرسشی نیست.')
    return out


def parse(raw, topics_by_code, existing_stems):
    """Dry run. ``topics_by_code``: {code: VocabularyTerm pk} of the teacher's subject and school. ``existing_stems``: stems
    already in that bank. Returns a list of ``Row`` (check ``row.ok``); raises ``BadFile`` for an unusable file."""
    rows, seen = [], set(existing_stems)
    for line, cells in _rows(raw):
        row = Row(line=line, topic_code=cells.get('topic', ''), stem=cells.get('stem', ''), correct=cells.get('correct', ''))
        row.topic_id = topics_by_code.get(row.topic_code)
        if row.topic_id is None:
            row.errors.append('مبحث در مبحث‌های این درس نیست.')
        if not row.stem or len(row.stem) > 2000:
            row.errors.append('متن پرسش لازم است (حداکثر ۲۰۰۰ نویسه).')
        elif row.stem in seen:
            row.errors.append('پرسشی با همین متن از قبل هست.')
        for i in range(1, MAX_OPTIONS + 1):
            text, expl = cells.get(f'o{i}_text', ''), cells.get(f'o{i}_expl', '')
            if not (text or expl):
                continue
            if not text or len(text) > 300:
                row.errors.append(f'گزینهٔ {i}: متن لازم است (حداکثر ۳۰۰).')
            if not expl or len(expl) > 1000:
                row.errors.append(f'گزینهٔ {i}: توضیح لازم است (حداکثر ۱۰۰۰).')
            row.options.append({'i': i, 'text': text, 'explanation': expl})
        if len(row.options) < 2:
            row.errors.append('دست‌کم دو گزینه لازم است.')
        if row.correct not in {str(o['i']) for o in row.options}:
            row.errors.append('ستون correct باید شمارهٔ یک گزینهٔ پرشده باشد.')
        if row.ok:
            seen.add(row.stem)
        rows.append(row)
    return rows


def rows_from_session(items, topics_by_code, existing_stems):
    """Re-validate rows stored in the session against the database as it is now (topics may have been retired, stems added)."""
    raw = io.StringIO()
    writer = csv.writer(raw)
    writer.writerow(TEMPLATE_HEADER)
    for item in items:
        opts = {o['i']: o for o in item['options']}
        cells = [item['topic_code'], item['stem'], item['correct']]
        for i in range(1, MAX_OPTIONS + 1):
            cells += [opts.get(i, {}).get('text', ''), opts.get(i, {}).get('explanation', '')]
        writer.writerow(cells)
    return parse(raw.getvalue().encode('utf-8'), topics_by_code, existing_stems)


def apply(rows, *, school_id, subject, author):
    """Create the valid rows as draft questions (one transaction per row). Returns ``(created, failed)``."""
    created = failed = 0
    for row in rows:
        if not row.ok:
            continue
        try:
            with transaction.atomic():
                question = Question.objects.create(school_id=school_id, subject=subject, topic_id=row.topic_id, stem=row.stem,
                                                   status=Question.DRAFT, source='csv', author=author)
                for order, o in enumerate(row.options, start=1):
                    Option.objects.create(question=question, order=order, text=o['text'], explanation=o['explanation'],
                                          is_correct=str(o['i']) == row.correct)
            created += 1
        except Exception:                      # a database rule refused the row: counted, never half-written
            failed += 1
    return created, failed
