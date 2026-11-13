"""Database access of the live student import (changes/0010 S3), kept OUT of the view module so that no raw
``Student.objects`` read remains in ``students/views.py`` (``QuerysetChokePointTests`` has an empty allow-list).

Every read here is scoped to the school of the import (``school_id``, resolved ONCE from the importer's validated
membership by ``resolve_student_school``): students of other schools are invisible to the planning reads. The only
one function that must look across schools is ``locked_state``: ``national_id`` is globally
unique until S7, so the write step has to detect that an id belongs to ANOTHER school (it returns only the ids of
school and class, never data) and then refuse the row. A test pins which functions may omit ``school_id``.
"""
from django.db import IntegrityError, transaction

from .models import Student

CHUNK = 500


def _chunks(items, size=CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def linked_national_ids(school_id, national_ids):
    """National ids, among ``national_ids``, of students OF THIS SCHOOL that already have a class link."""
    found = set()
    for chunk in _chunks(set(national_ids)):
        found.update(Student.objects.filter(school_id=school_id, national_id__in=chunk, school_class__isnull=False)
                     .values_list('national_id', flat=True))
    return found


def existing_state(school_id, national_ids):
    """``{national_id: school_class_id}`` of the students OF THIS SCHOOL among ``national_ids``."""
    state = {}
    for chunk in _chunks(set(national_ids)):
        for nid, class_id in Student.objects.filter(school_id=school_id, national_id__in=chunk).values_list(
                'national_id', 'school_class_id'):
            state[nid] = class_id
    return state


def grades_by_class(school_id, class_ids):
    """``{class_id: [grade, ...]}`` of the students of THIS SCHOOL linked to ``class_ids`` (as persisted)."""
    grades = {}
    for chunk in _chunks(set(class_ids)):
        for grade, class_id in Student.objects.filter(school_id=school_id, school_class_id__in=chunk).values_list(
                'grade', 'school_class_id'):
            grades.setdefault(class_id, []).append(grade)
    return grades


def locked_state(national_id):
    """CROSS-SCHOOL by necessity (global uniqueness until S7): ``{'school_id', 'school_class_id'}`` of the student with
    this national id, locked for update where the database supports it, or ``None``. Used only to refuse a row."""
    return (Student.objects.select_for_update().filter(national_id=national_id)
            .values('school_id', 'school_class_id').first())


class ImportConflict(Exception):
    """The write lost a race (or hit the global ``national_id`` uniqueness): another school's student owns the id."""


def write_row(school_id, national_id, defaults):
    """Conditional write (S4(a)): UPDATE only a student of THIS school (row-locked where the database supports it); otherwise
    INSERT and let the unique ``national_id`` decide - an ``IntegrityError`` (another school, or a concurrent import, got
    there first) becomes ``ImportConflict``. Nothing of another school is ever read for update or overwritten, whatever
    ``locked_state`` saw a moment earlier (a lock on a row that does not exist yet locks nothing, and SQLite has no row lock)."""
    existing = Student.objects.select_for_update().filter(school_id=school_id, national_id=national_id).first()
    if existing is not None:
        for field, value in defaults.items():
            setattr(existing, field, value)
        # like update_or_create: persist only the fields being written (+ auto_now ones), so derived mirrors are not rewritten
        existing.save(update_fields=list(defaults) + [f.name for f in Student._meta.concrete_fields if getattr(f, 'auto_now', False)])
        return existing, False
    try:
        with transaction.atomic():
            return Student.objects.create(**{**defaults, 'national_id': national_id}), True
    except IntegrityError:
        raise ImportConflict() from None


# Functions allowed to omit ``school_id`` (pinned by a test); every other function of this module must take it.
CROSS_SCHOOL_BY_NECESSITY = ('locked_state',)
