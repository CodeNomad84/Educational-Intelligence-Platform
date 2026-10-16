"""Year-aware historical import (ADR-0011 §5, proposal 0003 stage 2.2a-3).

Three kinds of file, always for ONE academic year chosen by the admin (never read from the rows):

    roster      national_id, grade, status [, class]      -> Enrollment rows
    grades      national_id, subject, exam_type, score, date -> Grade rows attached to the year's enrollment
    attendance  national_id, date, status [, note]        -> Attendance rows attached to the year's enrollment

Rules: existing students only (an unknown national id is rejected, never created); the import never writes a
``Student`` field (grade, school_class, class_name stay as they are); an existing record is never overwritten
(identical = ``unchanged``, different = rejected as a conflict); anything unresolved or ambiguous is rejected
with a reason and a row number; Persian/Arabic-Indic digits are accepted; dates must be Gregorian. Everything
written carries ``source='import'`` (enrollments) and the ``ImportBatch`` of the run.
"""
import hashlib
import math
import re
from collections import Counter, defaultdict
from datetime import date

import pandas as pd

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import SchoolClass
from schools.vocabulary import SUBJECT_CHOICES
from students.models import Attendance, Enrollment, Grade, Student
from students.views import _clean_national_id  # same validation as the live student import

KINDS = ('roster', 'grades', 'attendance')
REJECT_LIST_LIMIT = 200
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

HEADERS = {
    'national_id': 'national_id', 'کد ملی': 'national_id', 'کدملی': 'national_id',
    'grade': 'grade', 'پایه': 'grade', 'پایه تحصیلی': 'grade',
    'class': 'class', 'کلاس': 'class', 'class_name': 'class',
    'status': 'status', 'وضعیت': 'status',
    'subject': 'subject', 'درس': 'subject',
    'exam_type': 'exam_type', 'نوع آزمون': 'exam_type',
    'score': 'score', 'نمره': 'score',
    'date': 'date', 'تاریخ': 'date',
    'note': 'note', 'یادداشت': 'note',
}
REQUIRED = {
    'roster': ('national_id', 'grade', 'status'),
    'grades': ('national_id', 'subject', 'exam_type', 'score', 'date'),
    'attendance': ('national_id', 'date', 'status'),
}


def _label_map(choices):
    out = {}
    for key, label in choices:
        out[str(key)] = key
        out[str(label)] = key
    return out


SUBJECTS = _label_map(SUBJECT_CHOICES)
EXAM_TYPES = _label_map(Grade.EXAM_TYPE_CHOICES)
ATT_STATUS = _label_map(Attendance.STATUS_CHOICES)
ENR_STATUS = _label_map(Enrollment.STATUS_CHOICES)
GRADES = _label_map(Student.GRADE_CHOICES)


class FileError(Exception):
    """The whole file is unusable (missing required column, unreadable)."""


def read_rows(path, kind):
    """Return ``(rows, sha256)``; rows are dicts of stripped strings keyed by canonical column names."""
    with open(path, 'rb') as fh:
        raw = fh.read()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        if str(path).lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(path, dtype=str, keep_default_na=False)
        else:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    except Exception as exc:  # unreadable file
        raise FileError(f'فایل قابل خواندن نیست: {exc}')
    df.columns = [HEADERS.get(str(c).strip().lower(), HEADERS.get(str(c).strip(), str(c).strip())) for c in df.columns]
    missing = [c for c in REQUIRED[kind] if c not in df.columns]
    if missing:
        raise FileError(f'ستون‌های اجباری وجود ندارند: {", ".join(missing)}')
    rows = []
    for number, record in enumerate(df.to_dict('records'), start=2):  # row 1 is the header
        row = {k: ('' if v is None else str(v).strip()) for k, v in record.items()}
        if any(row.values()):
            row['_row'] = number
            rows.append(row)
    return rows, sha


def parse_date(text):
    """Gregorian ``YYYY-MM-DD`` / ``YYYY/MM/DD`` (Persian digits ok). Returns ``(date, error)``."""
    value = (text or '').translate(_DIGITS).strip()
    m = re.fullmatch(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', value)
    if not m:
        return None, 'date_format_invalid'
    y, mo, d = (int(x) for x in m.groups())
    if y < 1700:
        return None, 'date_looks_solar_hijri_use_gregorian'
    try:
        return date(y, mo, d), ''
    except ValueError:
        return None, 'date_invalid'


def parse_score(text, max_score):
    value = (text or '').translate(_DIGITS).replace('٫', '.').replace(',', '.').strip()
    try:
        score = float(value)
    except ValueError:
        return None, 'score_not_a_number'
    if math.isnan(score) or math.isinf(score) or score < 0 or score > max_score:
        return None, 'score_out_of_range'
    return score, ''


def _year_classes(academic_year):
    """Classes of the year's school whose free-text year normalises to the year code: title -> [pk]."""
    out = defaultdict(list)
    for pk, title, year in SchoolClass.objects.filter(school_id=academic_year.school_id).values_list(
            'pk', 'title', 'academic_year'):
        status, code = normalize_academic_year(year)
        if status == RESOLVED and code == academic_year.code:
            out[title.strip()].append(pk)
    return out


def run(kind, academic_year, rows, *, apply, batch=None, max_score=20.0):
    """Validate every row; write only when ``apply``. Returns the report dict. Caller wraps in a transaction."""
    counts = Counter()
    rejected = []

    def reject(row, reason):
        counts['rejected'] += 1
        counts[f'rejected:{reason}'] += 1
        if len(rejected) < REJECT_LIST_LIMIT:
            rejected.append({'row': row['_row'], 'reason': reason})

    # students by cleaned national id (read once)
    parsed = []
    for row in rows:
        counts['rows'] += 1
        nid, error = _clean_national_id(row.get('national_id'))
        if error:
            reject(row, 'national_id_invalid')
            continue
        parsed.append((row, nid))
    students = {
        nid: (pk, school_id) for pk, nid, school_id in Student.objects.filter(
            national_id__in={nid for _r, nid in parsed}).values_list('pk', 'national_id', 'school_id')
    }
    known = []
    for row, nid in parsed:
        if nid not in students:
            reject(row, 'unknown_student')
        elif students[nid][1] != academic_year.school_id:
            reject(row, 'student_not_in_the_years_school')
        else:
            known.append((row, students[nid][0]))

    handler = {'roster': _roster, 'grades': _grades, 'attendance': _attendance}[kind]
    handler(known, academic_year, counts, reject, apply=apply, batch=batch, max_score=max_score)
    summary = {k: v for k, v in counts.items() if not k.startswith('rejected:')}
    reasons = {k.split(':', 1)[1]: v for k, v in counts.items() if k.startswith('rejected:')}
    return {'kind': kind, 'academic_year': academic_year.code, 'counts': summary, 'rejected_by_reason': reasons,
            'rejected_rows': rejected, 'rejected_rows_listed_limit': REJECT_LIST_LIMIT}


def _enrollments_by_student(academic_year, student_ids):
    out = defaultdict(list)
    for e in Enrollment.objects.filter(academic_year=academic_year, student_id__in=student_ids):
        out[e.student_id].append(e)
    return out


def _roster(known, academic_year, counts, reject, *, apply, batch, max_score):
    classes = _year_classes(academic_year)
    existing = _enrollments_by_student(academic_year, {sid for _r, sid in known})
    seen = {}
    for row, sid in known:
        grade = GRADES.get(row.get('grade', '').translate(_DIGITS).strip())
        if grade is None:
            reject(row, 'grade_invalid')
            continue
        grade = int(grade)
        status = ENR_STATUS.get(row.get('status', '').strip())
        if status is None:
            reject(row, 'status_invalid')
            continue
        class_pk = None
        title = row.get('class', '').strip()
        if title:
            options = classes.get(title, [])
            if len(options) != 1:
                reject(row, 'class_not_found_in_year' if not options else 'class_title_ambiguous_in_year')
                continue
            class_pk = options[0]
        wanted = (class_pk, grade, status)
        if sid in seen:
            if seen[sid] == wanted:
                counts['duplicate_in_file'] += 1
            else:
                reject(row, 'conflicting_duplicate_in_file')
            continue
        seen[sid] = wanted
        current = existing.get(sid, [])
        if len(current) > 1:
            reject(row, 'several_enrollments_already_in_year')
        elif current:
            e = current[0]
            if (e.school_class_id, e.grade, e.status) == wanted:
                counts['unchanged'] += 1
            else:
                reject(row, 'conflicts_with_existing_enrollment')
        else:
            counts['created' if apply else 'would_create'] += 1
            if apply:
                Enrollment.objects.create(
                    student_id=sid, academic_year=academic_year, school_class_id=class_pk, grade=grade,
                    status=status, source='import', import_batch=batch)


def _one_enrollment(sid, academic_year, by_student, row, reject):
    found = by_student.get(sid, [])
    if len(found) == 1:
        return found[0]
    reject(row, 'no_enrollment_in_year' if not found else 'several_enrollments_in_year')
    return None


def _in_year(day, academic_year):
    return academic_year.start_date <= day <= academic_year.end_date


def _grades(known, academic_year, counts, reject, *, apply, batch, max_score):
    by_student = _enrollments_by_student(academic_year, {sid for _r, sid in known})
    existing = {
        (sid, subject, exam, day): score for sid, subject, exam, day, score in Grade.objects.filter(
            student_id__in={sid for _r, sid in known}, date__range=(academic_year.start_date, academic_year.end_date),
        ).values_list('student_id', 'subject', 'exam_type', 'date', 'score')
    }
    seen = {}
    for row, sid in known:
        subject = SUBJECTS.get(row.get('subject', '').strip())
        exam = EXAM_TYPES.get(row.get('exam_type', '').strip())
        day, derr = parse_date(row.get('date'))
        score, serr = parse_score(row.get('score'), max_score)
        if subject is None:
            reject(row, 'subject_not_in_vocabulary')
        elif exam is None:
            reject(row, 'exam_type_invalid')
        elif derr:
            reject(row, derr)
        elif not _in_year(day, academic_year):
            reject(row, 'date_outside_academic_year')
        elif serr:
            reject(row, serr)
        else:
            enrollment = _one_enrollment(sid, academic_year, by_student, row, reject)
            if enrollment is None:
                continue
            key = (sid, subject, exam, day)
            if key in seen:
                if seen[key] == score:
                    counts['duplicate_in_file'] += 1
                else:
                    reject(row, 'conflicting_duplicate_in_file')
                continue
            seen[key] = score
            if key in existing:
                if existing[key] == score:
                    counts['unchanged'] += 1
                else:
                    reject(row, 'conflicts_with_existing_grade')
                continue
            counts['created' if apply else 'would_create'] += 1
            if apply:
                Grade.objects.create(student_id=sid, enrollment=enrollment, subject=subject, exam_type=exam,
                                     score=score, date=day, import_batch=batch)


def _attendance(known, academic_year, counts, reject, *, apply, batch, max_score):
    by_student = _enrollments_by_student(academic_year, {sid for _r, sid in known})
    existing = {
        (sid, day): status for sid, day, status in Attendance.objects.filter(
            student_id__in={sid for _r, sid in known}, date__range=(academic_year.start_date, academic_year.end_date),
        ).values_list('student_id', 'date', 'status')
    }
    seen = {}
    for row, sid in known:
        status = ATT_STATUS.get(row.get('status', '').strip())
        day, derr = parse_date(row.get('date'))
        if status is None:
            reject(row, 'status_invalid')
        elif derr:
            reject(row, derr)
        elif not _in_year(day, academic_year):
            reject(row, 'date_outside_academic_year')
        else:
            enrollment = _one_enrollment(sid, academic_year, by_student, row, reject)
            if enrollment is None:
                continue
            key = (sid, day)
            if key in seen:
                if seen[key] == status:
                    counts['duplicate_in_file'] += 1
                else:
                    reject(row, 'conflicting_duplicate_in_file')
                continue
            seen[key] = status
            if key in existing:
                if existing[key] == status:
                    counts['unchanged'] += 1
                else:
                    reject(row, 'conflicts_with_existing_attendance')
                continue
            counts['created' if apply else 'would_create'] += 1
            if apply:
                Attendance.objects.create(student_id=sid, enrollment=enrollment, date=day, status=status,
                                          note=row.get('note', ''), import_batch=batch)
