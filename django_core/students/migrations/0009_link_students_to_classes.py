"""Link existing students to classes from their legacy ``class_name`` text (ADR-0004, proposal 0002, C3b).

DATA MIGRATION, SELF-CONTAINED. It uses historical models only (``apps.get_model``) and a FROZEN copy of the
classification rules of ``students/class_links.py`` as reviewed in C3a. It deliberately imports neither
runtime models nor ``students.class_links``: later edits to those can never change what this migration did.
A parity test keeps the frozen copy equal to ``class_links.py`` for as long as both are meant to agree.

Rules (fail closed: when in doubt do NOT link):
  * Title identity = whitespace trimmed and collapsed, NOTHING else (digit script, Arabic/Persian letters,
    ZWNJ, case, punctuation keep titles distinct; near-duplicates are never merged).
  * Blank, > 50 chars, or a title seen with more than one distinct grade (counted over ALL students,
    including already-linked ones) -> no class, students stay unlinked.
  * Target = default school, academic_year ''. Exact-title ACTIVE class -> reuse. Exact-title INACTIVE
    class -> skip and report (never reactivated). A class whose stored title only NORMALIZES to the same
    identity -> collision: skip and report. A same-title class in another year is ignored. Otherwise create.
  * Only students with school_class IS NULL are linked; ``school`` is set to the default school; remaining
    unlinked students get ``school`` only where it is NULL.
  * ``class_name``, ``updated_at``, existing links and existing classes are never modified; no
    TeacherAssignment is created; nothing is deleted. Writes use QuerySet.update().
  * Default school: exactly one -> use it; none -> create (code 'default', name settings.DEFAULT_SCHOOL_NAME,
    fails clearly if blank or > 200 chars); more than one -> change nothing and report.
  * Atomic: any error rolls back everything this migration did.

Reverse is a NO-OP. Reversing only to students.0008 keeps the links and the classes created here. To restore
the pre-C3 schema: ``migrate students 0007`` and then ``migrate schools zero`` (class_name was never touched).
PostgreSQL is not verified (deferred gate); only portable ORM operations are used.
"""
import logging
import re
from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import migrations

logger = logging.getLogger('students.migrations.0009_link_students_to_classes')

MAX_TITLE_LENGTH = 50      # SchoolClass.title max_length
SCHOOL_NAME_MAX = 200      # School.name max_length
CHUNK_SIZE = 500           # keeps IN (...) lists far below database variable limits

LINKABLE = 'linkable'
MULTI_GRADE = 'multi_grade'
TOO_LONG = 'too_long'


# --- frozen classification (mirror of students/class_links.py as of C3a) -----------------------------------
def _normalize(value):
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()


def _classify(rows):
    """``rows`` = iterable of (class_name, grade). Returns (status_by_title, students_by_title, blank_count)."""
    students = defaultdict(int)
    grades = defaultdict(set)
    blank = 0
    for class_name, grade in rows:
        title = _normalize(class_name)
        if not title:
            blank += 1
            continue
        students[title] += 1
        grades[title].add(grade)
    status = {}
    for title in students:
        if len(title) > MAX_TITLE_LENGTH:
            status[title] = TOO_LONG
        elif len(grades[title]) > 1:
            status[title] = MULTI_GRADE
        else:
            status[title] = LINKABLE
    return status, dict(students), blank


def _chunks(items, size=CHUNK_SIZE):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --- the migration ----------------------------------------------------------------------------------------
def _new_report(total):
    return {
        'students': total, 'schools_found': 0, 'school_created': False, 'noop_multiple_schools': False,
        'already_linked_untouched': 0,
        'linked_students': 0, 'classes_created': 0, 'classes_reused': 0,
        'blank_students': 0,
        'multi_grade_titles': 0, 'multi_grade_students': 0,
        'too_long_titles': 0, 'too_long_students': 0,
        'inactive_class_titles': 0, 'inactive_class_students': 0,
        'normalization_collision_titles': 0, 'normalization_collision_students': 0,
        'school_set_on_unlinked': 0,
    }


def _resolve_school(School, report):
    count = School.objects.count()
    report['schools_found'] = count
    if count > 1:
        report['noop_multiple_schools'] = True
        return None
    if count == 1:
        return School.objects.get()
    name = getattr(settings, 'DEFAULT_SCHOOL_NAME', 'Default School')
    if not isinstance(name, str) or not name.strip():
        raise ImproperlyConfigured(
            'students.0009: DEFAULT_SCHOOL_NAME is empty; set a school name and re-run migrate. '
            'Nothing was changed.')
    if len(name) > SCHOOL_NAME_MAX:
        raise ImproperlyConfigured(
            f'students.0009: DEFAULT_SCHOOL_NAME is {len(name)} characters (maximum {SCHOOL_NAME_MAX}); '
            'it is never truncated. Set a shorter name and re-run migrate. Nothing was changed.')
    report['school_created'] = True
    return School.objects.create(code='default', name=name)


def _link_title(Student, school, school_class, raw_variants):
    """Link the unlinked students whose raw class_name is one of ``raw_variants``. Returns rows updated."""
    updated = 0
    for chunk in _chunks(sorted(raw_variants)):
        updated += (Student.objects
                    .filter(school_class__isnull=True, class_name__in=chunk)
                    .update(school=school, school_class=school_class))
    return updated


def _link(apps):
    School = apps.get_model('schools', 'School')
    SchoolClass = apps.get_model('schools', 'SchoolClass')
    Student = apps.get_model('students', 'Student')

    rows = list(Student.objects.values_list('class_name', 'grade', 'school_class_id'))
    report = _new_report(len(rows))
    report['already_linked_untouched'] = sum(1 for _c, _g, link in rows if link is not None)

    school = _resolve_school(School, report)
    if school is None:
        return report  # multiple schools: no class creation, no linking, no school assignment

    status, _counts, _blank = _classify([(c, g) for c, g, _l in rows])

    # Only UNLINKED students can be touched; student counts below refer to them.
    unlinked_by_title = defaultdict(int)
    variants = defaultdict(set)
    for class_name, _grade, link in rows:
        title = _normalize(class_name)
        if not title:
            if link is None:
                report['blank_students'] += 1
            continue
        variants[title].add(class_name)
        if link is None:
            unlinked_by_title[title] += 1

    existing = defaultdict(list)  # normalized stored title -> [(pk, stored title, is_active)]
    for pk, title, active in SchoolClass.objects.filter(school=school, academic_year='').values_list(
            'pk', 'title', 'is_active'):
        existing[_normalize(title)].append((pk, title, active))

    for title in sorted(status):
        n_unlinked = unlinked_by_title.get(title, 0)
        outcome = status[title]
        if outcome == TOO_LONG:
            report['too_long_titles'] += 1
            report['too_long_students'] += n_unlinked
            continue
        if outcome == MULTI_GRADE:
            report['multi_grade_titles'] += 1
            report['multi_grade_students'] += n_unlinked
            continue

        if n_unlinked == 0:
            continue  # nothing to link (all its students are already linked): no class work, no noise

        same_identity = existing.get(title, [])
        if any(stored != title for _pk, stored, _a in same_identity):
            report['normalization_collision_titles'] += 1
            report['normalization_collision_students'] += n_unlinked
            continue
        if same_identity:
            pk, _stored, active = same_identity[0]
            if not active:
                report['inactive_class_titles'] += 1
                report['inactive_class_students'] += n_unlinked
                continue
            school_class = SchoolClass.objects.get(pk=pk)
            report['classes_reused'] += 1
        else:
            school_class = SchoolClass.objects.create(
                school=school, academic_year='', title=title, is_active=True)
            report['classes_created'] += 1
        report['linked_students'] += _link_title(Student, school, school_class, variants[title])

    report['school_set_on_unlinked'] = (
        Student.objects.filter(school_class__isnull=True, school__isnull=True).update(school=school))
    return report


def _emit(report):
    line = 'students.0009 link_students_to_classes: ' + ', '.join(
        f'{key}={value}' for key, value in sorted(report.items()))
    anomalies = report['noop_multiple_schools'] or any(report[k] for k in (
        'multi_grade_students', 'too_long_students', 'inactive_class_students',
        'normalization_collision_students', 'blank_students'))
    logger.log(logging.WARNING if anomalies else logging.INFO, line)
    if report['students'] or report['noop_multiple_schools']:
        print(line)  # counts only: no names, national ids or other personal data


def link_students_to_classes(apps, schema_editor):
    _emit(_link(apps))


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ('schools', '0001_initial'),
        ('students', '0008_student_school_student_school_class_and_more'),
    ]

    operations = [
        migrations.RunPython(link_students_to_classes, migrations.RunPython.noop),
    ]
