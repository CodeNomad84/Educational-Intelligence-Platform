"""Pure classification of legacy ``Student.class_name`` text into class links (ADR-0004, proposal 0002 C3).

No ORM, no I/O: input is plain ``(class_name, grade)`` pairs, output is a decision per title. It is used by
``manage.py check_class_links`` (C3a); the data migration (C3b) embeds a frozen copy of the same rules and a
parity test keeps both equal, so later edits here can never change what a historical migration did.

Rules (fail closed: when in doubt, do NOT link):

1. Identity of a title = the text with whitespace runs collapsed to one space and the ends stripped.
   NOTHING else is normalized: digit script, Arabic/Persian letters, ZWNJ, case and punctuation all keep
   two titles distinct.
2. Empty / whitespace-only text is ``blank``: never a class.
3. A title longer than ``MAX_TITLE_LENGTH`` is ``too_long`` (no truncation).
4. A title seen with more than one distinct grade is ``multi_grade``: no class is created for it, so
   students stay unlinked (a bare "الف" in grades 9 and 10 is two different classes).
5. Every other title is ``linkable``.
6. Distinct titles that would collide under aggressive normalization are only REPORTED as near-duplicates;
   they are never merged and never change a decision.
"""
import re
import unicodedata
from collections import defaultdict

MAX_TITLE_LENGTH = 50  # mirrors SchoolClass.title max_length

BLANK = 'blank'
LINKABLE = 'linkable'
MULTI_GRADE = 'multi_grade'
TOO_LONG = 'too_long'

_AR_TO_FA = {'ي': 'ی', 'ى': 'ی', 'ك': 'ک'}  # ي ى ك -> ی ی ک
_DIGITS = {
    **{chr(0x06F0 + i): str(i) for i in range(10)},  # Persian digits
    **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic digits
}
_INVISIBLE = set('‌‍‎‏ ﻿‪‫‬ـ')
_SEPARATORS = set('-_/\\.‐‑‒–—―−')


def normalize_title(value):
    """Identity key of a class title: collapse whitespace runs and strip. Nothing else (rule 1)."""
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()


def near_duplicate_key(title):
    """Analysis only: equal keys mean two DISTINCT titles may be the same class spelled differently."""
    text = unicodedata.normalize('NFKC', title)
    text = ''.join(_AR_TO_FA.get(c, c) for c in text)
    text = ''.join(_DIGITS.get(c, c) for c in text)
    text = ''.join(c for c in text if c not in _INVISIBLE and c not in _SEPARATORS and not c.isspace())
    return text.casefold()


def has_digit(title):
    """True if the title contains a digit of any script (it may then state its grade)."""
    return any(c.isdigit() for c in title)


class LinkPlan:
    """Decision per normalized title, built once from every ``(class_name, grade)`` pair of the source."""

    def __init__(self, status, students, grades, blank_count, total):
        self.status = status          # normalized title -> LINKABLE | MULTI_GRADE | TOO_LONG
        self.students = students      # normalized title -> number of source students
        self.grades = grades          # normalized title -> {grade: number of students}
        self.blank_count = blank_count
        self.total = total

    def status_for(self, value):
        """Decision for a raw class_name value. ``BLANK`` for empty text; a title absent from the source
        raises ``KeyError`` (the plan only knows the data it was built from)."""
        title = normalize_title(value)
        if not title:
            return BLANK
        return self.status[title]

    def titles(self, status):
        return sorted(t for t, s in self.status.items() if s == status)

    def near_duplicate_groups(self):
        """Groups (size >= 2) of distinct titles that differ only by digit script, Arabic/Persian letters,
        invisible characters, spacing, case or punctuation. Reported only; never merged."""
        by_key = defaultdict(list)
        for title in self.status:
            by_key[near_duplicate_key(title)].append(title)
        return sorted(sorted(group) for group in by_key.values() if len(group) > 1)

    def bare_titles(self):
        """Linkable titles without any digit: the title alone cannot tell the grade, so the same text may
        later denote another grade's class. A warning only; it does not change a decision."""
        return [t for t in self.titles(LINKABLE) if not has_digit(t)]

    def summary(self):
        counts = {s: sum(self.students[t] for t in self.titles(s)) for s in (LINKABLE, MULTI_GRADE, TOO_LONG)}
        return {
            'students': self.total,
            'blank': self.blank_count,
            'linkable_students': counts[LINKABLE],
            'multi_grade_students': counts[MULTI_GRADE],
            'too_long_students': counts[TOO_LONG],
            'linkable_titles': len(self.titles(LINKABLE)),
            'multi_grade_titles': len(self.titles(MULTI_GRADE)),
            'too_long_titles': len(self.titles(TOO_LONG)),
            'near_duplicate_groups': len(self.near_duplicate_groups()),
            'bare_titles': len(self.bare_titles()),
        }


def plan_class_links(rows):
    """Build the plan from an iterable of ``(class_name, grade)``."""
    students = defaultdict(int)
    grades = defaultdict(lambda: defaultdict(int))
    blank = 0
    total = 0
    for class_name, grade in rows:
        total += 1
        title = normalize_title(class_name)
        if not title:
            blank += 1
            continue
        students[title] += 1
        grades[title][grade] += 1
    status = {}
    for title in students:
        if len(title) > MAX_TITLE_LENGTH:
            status[title] = TOO_LONG
        elif len(grades[title]) > 1:
            status[title] = MULTI_GRADE
        else:
            status[title] = LINKABLE
    return LinkPlan(status, dict(students), {t: dict(g) for t, g in grades.items()}, blank, total)
