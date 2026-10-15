"""Academic-year code normalisation and date lookup (ADR-0011, proposal 0003 §3.1).

Pure functions, no database access. A value that does not resolve to exactly one Solar Hijri start year is
``unresolved``: callers report it and never guess (fail closed).

Accepted spellings of the year 1404-1405: ``1404``, ``1404-1405``, ``1404/1405``, ``1404-05``, ``1404_1405``,
``۱۴۰۴-۱۴۰۵`` (Persian or Arabic-Indic digits), with spaces or dashes around the separator. Rejected:
two different year spans (``1404-1407``), three or fewer digits, Gregorian-looking years, free words.
"""
import re

RESOLVED, BLANK, UNRESOLVED = 'resolved', 'blank', 'unresolved'
MIN_YEAR, MAX_YEAR = 1300, 1499  # Solar Hijri start years accepted

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_SEPARATORS = re.compile(r'[\s\-–—_/\\.]+')
CODE_RE = re.compile(r'^(\d{4})-(\d{4})$')


def normalize_academic_year(value):
    """Return ``(status, code)``; ``code`` is ``'YYYY-YYYY'`` only when ``status == RESOLVED``."""
    text = (value or '').translate(_DIGITS).strip()
    if not text:
        return BLANK, None
    parts = [p for p in _SEPARATORS.split(text) if p]
    if not parts or not all(p.isdigit() for p in parts) or len(parts) > 2:
        return UNRESOLVED, None
    first = parts[0]
    if len(first) != 4:
        return UNRESOLVED, None
    start = int(first)
    if not MIN_YEAR <= start <= MAX_YEAR:
        return UNRESOLVED, None
    if len(parts) == 1:
        return RESOLVED, f'{start}-{start + 1}'
    second = parts[1]
    if len(second) == 4 and int(second) == start + 1:
        return RESOLVED, f'{start}-{start + 1}'
    if len(second) == 2 and int(second) == (start + 1) % 100:
        return RESOLVED, f'{start}-{start + 1}'
    return UNRESOLVED, None


def year_for_date(ranges, day):
    """``ranges``: iterable of ``(code, start_date, end_date)`` of ONE school. Returns the list of codes whose
    inclusive range contains ``day`` (0 = none, more than 1 = overlapping ranges; the caller reports both)."""
    return [code for code, start, end in ranges if start <= day <= end]
