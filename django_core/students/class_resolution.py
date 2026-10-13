"""Pure class-resolution decisions for importing class text (ADR-0004, proposal 0002, C3c-1).

NOT wired into any view yet (C3c-2 does that). The module knows nothing about HTTP, uploaded files, pandas,
serializers, students or the database: callers pass plain values and ``ClassCandidate`` records, and receive
immutable ``Resolution`` results. It never creates, updates, activates or deletes anything.

Two passes (the second is what makes grade safety independent of row order):

    1. per row    resolve_class(raw_cell, school_ids=..., candidates=...)  -> Resolution
    2. whole file apply_grade_guard([(resolution, grade), ...], existing_grades_by_class)  -> [Resolution]

Statuses
    resolved          exactly one active class matched; ``candidate`` identifies it (no re-query by title)
    class_blank       the cell is empty/missing: nothing to resolve, NOT an unmatched class
    no_unique_school  zero or more than one School exists: no class is matched at all
    no_active_class   no class of the school has that title
    inactive_class    classes with that title exist but none is active (never reactivated)
    ambiguous         more than one active class has that title (e.g. several academic years)
    grade_conflict    linking would put more than one distinct valid grade into the class

Rules (all deterministic):
  * Title identity is ``class_links.normalize_title`` only: trim and collapse whitespace. Persian/Arabic
    digits, ي/ی, ك/ک, ZWNJ, case and punctuation keep titles DISTINCT.
  * Blank = None, empty/whitespace text, NaN (float/numpy/Decimal), pandas NA/NaT (detected by type name, so
    pandas is not imported). The TEXT "nan" is NOT blank: it is a legitimate (if useless) title. Callers must
    pass the raw cell, never ``str(cell)``, or a missing cell would be indistinguishable from the text "nan".
  * Numeric cells: integers and whole floats become integer text (``9.0`` -> ``"9"``); non-integral numbers
    keep their text (``9.5`` -> ``"9.5"``). Booleans are not numbers here (``True`` -> ``"True"``).
  * Only classes of THE unique school are considered. The caller passes every School id; the helper never
    queries and never creates a School.
  * KNOWN LIMITATION (academic year): the incoming data carries no academic year and there is no approved
    year-selection policy, so matching is by title only and NO year is ever preferred (not the empty year,
    not the newest, not the current one; the machine clock is never consulted). Several active classes with
    the same title (any years) are ``ambiguous``. A single active class resolves whatever its year; the
    candidate carries ``academic_year`` so the caller can see and report it. A year policy is an owner
    decision for later.
  * Grades: valid grades are those of ``Student.GRADE_CHOICES`` (7-12), read lazily from the model (single
    source of truth; importing this module does not require Django to be configured). ``None``, blanks,
    out-of-range and non-numeric values are ignored for conflict detection and never rewritten. A whole float
    such as 9.0 counts as 9; ``True``, 9.5, NaN and numeric text such as ``'9'`` do not.
"""
import numbers
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .class_links import normalize_title

RESOLVED = 'resolved'
CLASS_BLANK = 'class_blank'
NO_UNIQUE_SCHOOL = 'no_unique_school'
NO_ACTIVE_CLASS = 'no_active_class'
INACTIVE_CLASS = 'inactive_class'
AMBIGUOUS = 'ambiguous'
GRADE_CONFLICT = 'grade_conflict'

# Statuses that C3c-2 reports in ``unmatched_classes`` (a blank cell and a resolved row are not unmatched).
UNMATCHED_STATUSES = frozenset({NO_UNIQUE_SCHOOL, NO_ACTIVE_CLASS, INACTIVE_CLASS, AMBIGUOUS, GRADE_CONFLICT})

_supported_grades = None


def supported_grades():
    """Grades the Student model supports (7-12), from ``Student.GRADE_CHOICES``.

    Imported lazily on first use: ``students.models`` needs the Django app registry (it calls
    ``get_user_model()`` at import time), and this module must stay importable, and its title/class logic
    usable, without Django configured. There is deliberately no second copy of the range here.
    """
    global _supported_grades
    if _supported_grades is None:
        from .models import Student
        _supported_grades = frozenset(value for value, _label in Student.GRADE_CHOICES)
    return _supported_grades


@dataclass(frozen=True)
class ClassCandidate:
    """The facts about one existing class that resolution needs. Built by the caller, never by this module."""
    pk: int
    title: str
    is_active: bool
    school_id: int
    academic_year: str = ''

    @classmethod
    def from_model(cls, school_class):
        """Duck-typed copy of a ``SchoolClass`` row (no model import, no query)."""
        return cls(pk=school_class.pk, title=school_class.title, is_active=school_class.is_active,
                   school_id=school_class.school_id, academic_year=school_class.academic_year or '')


@dataclass(frozen=True)
class Resolution:
    status: str
    candidate: Optional[ClassCandidate] = None   # set only when status == RESOLVED
    title: str = ''                              # normalized incoming class text ('' when blank)

    @property
    def resolved(self):
        return self.status == RESOLVED


# --- cell handling ----------------------------------------------------------------------------------------
def _is_missing(value):
    if value is None:
        return True
    if type(value).__name__ in ('NAType', 'NaTType'):  # pandas.NA / pandas.NaT, without importing pandas
        return True
    if isinstance(value, Decimal):
        return value.is_nan()
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return value != value  # NaN (float, numpy.float32/64)
    return False


def class_text(value):
    """Normalized class title for a raw cell, or '' when the cell is blank (see module rules)."""
    if _is_missing(value):
        return ''
    if isinstance(value, bool):
        text = str(value)
    elif isinstance(value, numbers.Integral):
        text = str(int(value))
    elif isinstance(value, numbers.Real):
        number = float(value)
        text = str(int(number)) if number.is_integer() else str(value)
    else:
        text = str(value)
    return normalize_title(text)


# --- pass 1: one row --------------------------------------------------------------------------------------
def resolve_class(value, *, school_ids, candidates):
    """Resolve one raw class cell against the classes of the unique school.

    ``school_ids``: ids of ALL existing Schools (the caller reads them; this function never queries).
    ``candidates``: ``ClassCandidate`` records; only those of the unique school are considered.
    """
    title = class_text(value)
    if not title:
        return Resolution(CLASS_BLANK)
    school_ids = list(school_ids)
    if len(school_ids) != 1:
        return Resolution(NO_UNIQUE_SCHOOL, title=title)
    school_id = school_ids[0]
    same_title = [c for c in candidates if c.school_id == school_id and normalize_title(c.title) == title]
    active = [c for c in same_title if c.is_active]
    if len(active) == 1:
        return Resolution(RESOLVED, candidate=active[0], title=title)
    if len(active) > 1:
        return Resolution(AMBIGUOUS, title=title)
    if same_title:
        return Resolution(INACTIVE_CLASS, title=title)
    return Resolution(NO_ACTIVE_CLASS, title=title)


# --- pass 2: the whole batch ------------------------------------------------------------------------------
def valid_grades(values):
    """The distinct valid grades in ``values`` (7-12). Everything else is ignored, never converted."""
    allowed = supported_grades()
    found = set()
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, numbers.Integral):
            grade = int(value)
        elif isinstance(value, numbers.Real) and float(value).is_integer():
            grade = int(float(value))
        else:
            continue
        if grade in allowed:
            found.add(grade)
    return frozenset(found)


def has_grade_conflict(existing_grades, incoming_grades):
    """True when the existing members and the incoming rows together span more than one valid grade."""
    return len(valid_grades(existing_grades) | valid_grades(incoming_grades)) > 1


def apply_grade_guard(entries, existing_grades_by_class):
    """Order-independent grade safety for a whole batch.

    CONTRACT: the caller must hand over a COMPLETE, PRE-COLLECTED batch. Linking anything before this call
    has seen every row makes the outcome depend on row order.

    ``entries``: sequence of ``(Resolution, grade)`` for EVERY row that would otherwise be linked to a class
        (rows that resolved ``resolved``; other statuses pass through untouched). Rows of students whose class
        link is immutable are NOT entries: they are not being linked.
    ``existing_grades_by_class``: ``{class_pk: iterable of the EFFECTIVE grades of its current members}``.
        "Effective" means the grade after this import: a member whose grade the import will change
        contributes the NEW grade, because preserving a link does not hide a changed grade from the class it
        already belongs to. Building that mapping needs student identity, so it is the caller's job; this
        function only ever sees plain grade values and is agnostic to students.

    For each class, the grades of its existing members and of EVERY incoming row that resolved to it are
    pooled first; if more than one valid grade results, all of that class's incoming rows become
    ``grade_conflict``. Other rows are returned unchanged. The result list is aligned with ``entries`` and
    does not depend on their order. A class that has no incoming resolved row is not evaluated (nothing would
    be linked to it). Inputs (entries, Resolutions, candidates, grade collections) are never mutated; any
    iterable of grades, including a one-shot iterator, is accepted.
    """
    entries = list(entries)
    pooled = {}
    for resolution, grade in entries:
        if resolution.resolved:
            pooled.setdefault(resolution.candidate.pk, set()).update(valid_grades([grade]))
    conflicted = {
        pk for pk, incoming in pooled.items()
        if has_grade_conflict(existing_grades_by_class.get(pk, ()), incoming)
    }
    return [
        Resolution(GRADE_CONFLICT, title=resolution.title)
        if resolution.resolved and resolution.candidate.pk in conflicted else resolution
        for resolution, _grade in entries
    ]
