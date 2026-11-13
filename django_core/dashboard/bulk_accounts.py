"""Bulk onboarding of student / parent / teacher accounts from one Excel file (SchoolAdmin, ONE school).

Two steps: ``build_plan`` (read-only dry run: a status and a message per row, nothing written) and ``apply_plan`` (writes,
one transaction per row). Both take the school of the acting SchoolAdmin; nothing in the file can name another school.

Rules (fail closed):
* username = national id (10 digits). A numeric Excel cell with fewer than 10 digits is an ERROR (the leading zeros are
  already lost: store the column as text), never guessed.
* A national id that belongs to a student, user or parent of ANOTHER school (or to a user of another kind) gets ONE generic
  message that says nothing about who owns it.
* Parent username = father's national id, else mother's; one parent account is linked to all its children of this school.
  An existing parent account is reused only if all its children are in this school.
* Initial passwords are random (``secrets``), shown once in the login sheet returned by the confirm step; they are never
  stored, logged or put in a message. Every created account is flagged ``must_change_password``.
* The batch is limited (``MAX_NEW_ACCOUNTS``): password hashing costs ~0.5 s per account and the request must finish.
"""
import io
import re
import secrets
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from openpyxl import Workbook, load_workbook

from schools.models import AcademicYear, AccountProfile, SchoolClass, SchoolStaff
from schools.vocabulary import GRADE_CHOICES
from students.access import PARENT, STUDENT, TEACHER
from students.enrollment_sync import ensure_current_enrollment
from students.models import Student

User = get_user_model()

MAX_FILE_BYTES = 2_000_000
MAX_ROWS_PER_SHEET = 1000
MAX_NEW_ACCOUNTS = 150
GENERIC = 'این ردیف قابل پردازش نیست (کد ملی تکراری یا متعلق به مدرسهٔ دیگر).'
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
NUMERIC = '\x00'   # marks a numeric Excel cell in an id column (the text form lost any leading zeros)
_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # no 0/O/1/l/I
VALID_GRADES = {value for value, _label in GRADE_CHOICES}

HEADERS = {
    'name': 'name', 'نام_و_نام_خانوادگی': 'name', 'نام': 'name',
    'first_name': 'first_name', 'last_name': 'last_name',
    'national_id': 'national_id', 'کد_ملی': 'national_id',
    'grade': 'grade', 'پایه': 'grade', 'class': 'class', 'کلاس': 'class',
    'father_national_id': 'father_national_id', 'کد_ملی_پدر': 'father_national_id',
    'mother_national_id': 'mother_national_id', 'کد_ملی_مادر': 'mother_national_id',
    'father_name': 'father_name', 'نام_پدر': 'father_name', 'mother_name': 'mother_name', 'نام_مادر': 'mother_name',
    'phone': 'phone', 'تلفن': 'phone',
}
SHEETS = {'students': 'students', 'دانش‌آموزان': 'students', 'teachers': 'teachers', 'معلمان': 'teachers'}
TEMPLATE_COLUMNS = {
    'Students': ['name', 'national_id', 'grade', 'class', 'father_national_id', 'mother_national_id', 'father_name',
                 'mother_name'],
    'Teachers': ['name', 'national_id', 'phone'],
}


class BadFile(Exception):
    """The upload is not a readable workbook of the expected shape (message is safe to show)."""


# --- reading the workbook ----------------------------------------------------------------------------------------------
def _text(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return str(value).strip().translate(_DIGITS)


def _split_name(full):
    parts = re.sub(r'\s+', ' ', full or '').strip().split(' ')
    parts = [p for p in parts if p]
    if not parts:
        return '', ''
    return ' '.join(parts[:-1])[:150], parts[-1][:150]


def parse_workbook(data):
    """Return ``{'students': [row, ...], 'teachers': [row, ...]}``; a row is a dict with ``line`` (sheet row number) and the
    canonical columns as text. Raises ``BadFile``."""
    if len(data) > MAX_FILE_BYTES:
        raise BadFile('فایل بزرگ‌تر از حد مجاز است.')
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:   # any parser failure is the same message; nothing of the file or the exception is echoed
        raise BadFile('فایل اکسل (xlsx) معتبر نیست.') from None
    out = {}
    for ws in book.worksheets:
        kind = SHEETS.get(re.sub(r'\s+', '', ws.title).lower())
        if kind is None or kind in out:
            continue
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            continue
        keys = [HEADERS.get(_text(h).lower().replace(' ', '_')) for h in header]
        parsed = []
        for line, cells in enumerate(rows, start=2):
            if len(parsed) >= MAX_ROWS_PER_SHEET:
                raise BadFile('تعداد ردیف‌های یک برگه بیش از حد مجاز است.')
            if not any(c not in (None, '') for c in cells):
                continue
            row = {'line': line}
            for key, cell in zip(keys, cells):
                if key:
                    row[key] = (NUMERIC + _text(cell)) if (key.endswith('national_id') and isinstance(cell, (int, float))
                                                       and not isinstance(cell, bool)) else _text(cell)
            parsed.append(row)
        out[kind] = parsed
    if not out:
        raise BadFile('برگهٔ «Students» یا «Teachers» پیدا نشد.')
    return out


def _nid(value, label):
    """``(national_id, error)`` for an optional/required cell. A leading NUMERIC marker flags a numeric Excel cell (see parse_workbook)."""
    text = (value or '').strip()
    numeric = text.startswith(NUMERIC)
    text = text[1:] if numeric else text
    if not text:
        return '', ''
    if not re.fullmatch(r'[0-9]{10}', text):
        if numeric and re.fullmatch(r'[0-9]{1,9}', text):
            return '', f'{label}: عدد با کمتر از ۱۰ رقم (صفرهای ابتدایی از دست رفته؛ ستون را به‌صورت متن ذخیره کنید).'
        return '', f'{label}: باید دقیقاً ۱۰ رقم باشد.'
    return text, ''


# --- the dry run -----------------------------------------------------------------------------------------------------
@dataclass
class RowPlan:
    sheet: str
    line: int
    kind: str                     # 'student' | 'teacher'
    name: str = ''
    national_id: str = ''
    status: str = 'error'         # create | link | exists | error
    message: str = ''
    first_name: str = ''
    last_name: str = ''
    grade: int = 0
    klass_id: int = 0
    parent_nid: str = ''
    parent_first: str = ''
    parent_last: str = ''
    parent_new: bool = False      # this row is the first one of a parent account that does not exist yet
    phone: str = ''
    notes: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status != 'error'


@dataclass
class Plan:
    rows: list
    new_accounts: int = 0
    blocking: str = ''

    @property
    def errors(self):
        return [r for r in self.rows if not r.ok]

    @property
    def counts(self):
        out = {'create': 0, 'link': 0, 'exists': 0, 'error': 0}
        for r in self.rows:
            out[r.status] += 1
        return out


def _parent_conflict(username, school):
    """None if ``username`` may be a parent of this school (absent, or a Parent whose children are all here); else a reason."""
    user = User.objects.filter(username=username).first()
    if user is None:
        return None
    school_ids = set(Student.objects.filter(parent_user=user).values_list('school_id', flat=True))
    if user.groups.filter(name=PARENT).exists() and school_ids == {school.pk}:
        return None
    return GENERIC


def build_plan(school, parsed):
    year = AcademicYear.objects.filter(school=school, is_current=True).first()
    classes = {}
    if year is not None:
        for klass in SchoolClass.objects.filter(school=school, is_active=True, academic_year=year.code):
            classes[klass.title.strip()] = klass
    seen = {}            # username -> 'student' | 'parent' | 'teacher'
    parents_new = set()
    rows = []
    for item in parsed.get('students', []):
        row = RowPlan('Students', item['line'], 'student')
        rows.append(row)
        errors = []
        if item.get('first_name') or item.get('last_name'):
            row.first_name, row.last_name = item.get('first_name', '')[:150], item.get('last_name', '')[:150]
        else:
            row.first_name, row.last_name = _split_name(item.get('name', ''))
        row.name = f'{row.first_name} {row.last_name}'.strip()
        if not row.last_name:
            errors.append('نام خالی است.')
        row.national_id, err = _nid(item.get('national_id'), 'کد ملی')
        if err or not row.national_id:
            errors.append(err or 'کد ملی خالی است.')
        try:
            row.grade = int(item.get('grade', ''))
        except ValueError:
            row.grade = 0
        if row.grade not in VALID_GRADES:
            errors.append('پایه معتبر نیست (۷ تا ۱۲).')
        klass = classes.get((item.get('class') or '').strip())
        if year is None:
            errors.append('سال تحصیلی جاری تعریف نشده است.')
        elif klass is None:
            errors.append('کلاس در سال جاری این مدرسه پیدا نشد.')
        elif klass.grade is not None and klass.grade != row.grade:
            errors.append('پایهٔ کلاس با پایهٔ ردیف نمی‌خواند.')
        else:
            row.klass_id = klass.pk
        father, err1 = _nid(item.get('father_national_id'), 'کد ملی پدر')
        mother, err2 = _nid(item.get('mother_national_id'), 'کد ملی مادر')
        errors += [e for e in (err1, err2) if e]
        if father or mother:
            row.parent_nid = father or mother
            full = item.get('father_name') if father else item.get('mother_name')
            row.parent_first, row.parent_last = _split_name(full or '')
            if not row.parent_last:
                row.parent_first, row.parent_last = ('پدر' if father else 'مادر'), row.last_name
        else:
            row.notes.append('بدون کد ملی والد: حساب والد ساخته نمی‌شود.')
        if errors:
            row.message = ' '.join(errors)
            continue
        # identity checks against the database and the file
        if row.national_id in seen:
            row.message = 'کد ملی در همین فایل تکراری است.'
            continue
        if row.parent_nid and (row.parent_nid == row.national_id or seen.get(row.parent_nid) in ('student', 'teacher')):
            row.message = 'کد ملی والد با کد ملی دیگری در فایل یکسان است.'
            continue
        existing = Student.objects.filter(national_id=row.national_id).values('school_id', 'student_user_id').first()
        user = User.objects.filter(username=row.national_id).first()
        if existing is not None and existing['school_id'] != school.pk:
            row.message = GENERIC
            continue
        if existing is not None:
            if existing['student_user_id'] is not None:
                if user is None or user.pk != existing['student_user_id']:
                    row.message = GENERIC
                    continue
                row.status = 'exists'
            else:
                if user is not None:
                    row.message = GENERIC
                    continue
                row.status = 'link'
        else:
            if user is not None:
                row.message = GENERIC
                continue
            row.status = 'create'
        if row.parent_nid:
            if _parent_conflict(row.parent_nid, school) is not None or seen.get(row.parent_nid) not in (None, 'parent'):
                row.status, row.message = 'error', GENERIC
                continue
            if not User.objects.filter(username=row.parent_nid).exists() and row.parent_nid not in parents_new:
                row.parent_new = True
                parents_new.add(row.parent_nid)
            seen[row.parent_nid] = 'parent'
        seen[row.national_id] = 'student'
    for item in parsed.get('teachers', []):
        row = RowPlan('Teachers', item['line'], 'teacher')
        rows.append(row)
        errors = []
        row.first_name, row.last_name = _split_name(item.get('name', ''))
        row.name = f'{row.first_name} {row.last_name}'.strip()
        if not row.last_name:
            errors.append('نام خالی است.')
        row.national_id, err = _nid(item.get('national_id'), 'کد ملی')
        if err or not row.national_id:
            errors.append(err or 'کد ملی خالی است.')
        phone = (item.get('phone') or '').strip()
        if phone and not re.fullmatch(r'09[0-9]{9}', phone):
            errors.append('تلفن باید به شکل 09xxxxxxxxx باشد.')
        row.phone = phone
        if errors:
            row.message = ' '.join(errors)
            continue
        if row.national_id in seen:
            row.message = 'کد ملی در همین فایل تکراری است.'
            continue
        user = User.objects.filter(username=row.national_id).first()
        if user is None:
            row.status = 'create'
        elif user.groups.filter(name=TEACHER).exists() and SchoolStaff.objects.filter(user=user, school=school).exists():
            row.status = 'exists'
        else:
            row.message = GENERIC
            continue
        seen[row.national_id] = 'teacher'
    plan = Plan(rows)
    plan.new_accounts = (sum(1 for r in rows if r.kind == 'student' and r.status in ('create', 'link'))
                         + sum(1 for r in rows if r.parent_new and r.ok)
                         + sum(1 for r in rows if r.kind == 'teacher' and r.status == 'create'))
    if plan.new_accounts > MAX_NEW_ACCOUNTS:
        plan.blocking = f'حداکثر {MAX_NEW_ACCOUNTS} حساب جدید در هر دسته مجاز است؛ فایل را (مثلاً بر اساس پایه) تقسیم کنید.'
    return plan


# --- the write ---------------------------------------------------------------------------------------------------------
def new_password():
    while True:
        password = ''.join(secrets.choice(_ALPHABET) for _ in range(10))
        if any(c.isdigit() for c in password) and any(c.isupper() for c in password) and any(c.islower() for c in password):
            return password


def _create_user(username, first, last, group_name, phone=''):
    password = new_password()
    user = User.objects.create_user(username, password=password, first_name=first, last_name=last)
    user.groups.add(Group.objects.get_or_create(name=group_name)[0])
    AccountProfile.objects.create(user=user, must_change_password=True, phone=phone)
    return user, password


def apply_plan(school, actor, plan):
    """Write every OK row of ``plan`` (re-planned just before, by the caller). Returns ``(counts, logins)``; ``logins`` holds
    the initial passwords and must only be handed to the login sheet - never stored, logged or shown elsewhere."""
    if plan.blocking:
        raise BadFile(plan.blocking)
    counts = {'student_accounts': 0, 'students_created': 0, 'parent_accounts': 0, 'parent_links': 0,
              'teacher_accounts': 0, 'existing': 0, 'failed': 0}
    logins = []
    parents = {}   # parent username -> User, only after the row that created it committed
    children = {}  # parent username -> [child names] for the login sheet
    for row in plan.rows:
        if not row.ok:
            continue
        if row.status == 'exists' and not row.parent_nid:
            counts['existing'] += 1
            continue
        local = dict.fromkeys(counts, 0)
        try:
            with transaction.atomic():
                made = []
                if row.kind == 'teacher':
                    if row.status == 'create':
                        user, pw = _create_user(row.national_id, row.first_name, row.last_name, TEACHER, row.phone)
                        SchoolStaff.objects.create(user=user, school=school, created_by=actor)
                        made.append(('معلم', row.name, row.national_id, pw, ''))
                        local['teacher_accounts'] += 1
                    else:
                        local['existing'] += 1
                else:
                    if row.status == 'create':
                        student = Student.objects.create(
                            first_name=row.first_name, last_name=row.last_name, national_id=row.national_id,
                            grade=row.grade, phone_number='', school_class=SchoolClass.objects.get(
                                pk=row.klass_id, school=school))
                        ensure_current_enrollment(student, source='import')
                        local['students_created'] += 1
                    else:
                        student = Student.objects.get(national_id=row.national_id, school=school)
                    if student.student_user_id is None:
                        user, pw = _create_user(row.national_id, row.first_name, row.last_name, STUDENT)
                        Student.objects.filter(pk=student.pk, student_user__isnull=True).update(student_user=user)
                        klass = student.school_class.title if student.school_class_id else ''
                        made.append(('دانش‌آموز', row.name, row.national_id, pw, klass))
                        local['student_accounts'] += 1
                    else:
                        local['existing'] += 1
                    if row.parent_nid:
                        parent = parents.get(row.parent_nid)
                        if parent is None:
                            parent = User.objects.filter(username=row.parent_nid).first()
                        if parent is None:
                            parent, pw = _create_user(row.parent_nid, row.parent_first, row.parent_last, PARENT)
                            made.append(('والد', f'{row.parent_first} {row.parent_last}'.strip(), row.parent_nid, pw, ''))
                            local['parent_accounts'] += 1
                        linked = Student.objects.filter(pk=student.pk, parent_user__isnull=True).update(parent_user=parent)
                        local['parent_links'] += linked
                        if linked:
                            made.append((None, row.parent_nid, row.name, None, None))
        except (IntegrityError, ValidationError, ObjectDoesNotExist):
            counts['failed'] += 1
            continue
        for key, value in local.items():
            counts[key] += value
        for item in made:
            if item[0] is None:   # a child of a parent, for the sheet
                children.setdefault(item[1], []).append(item[2])
            else:
                logins.append(item)
        if row.parent_nid and row.parent_nid not in parents:
            parent = User.objects.filter(username=row.parent_nid).first()
            if parent is not None:
                parents[row.parent_nid] = parent
    sheet = []
    for role, name, username, password, extra in logins:
        if role == 'والد':
            extra = '، '.join(children.get(username, []))
        sheet.append((role, name, username, password, extra))
    return counts, sheet


# --- files -------------------------------------------------------------------------------------------------------------
def _put(ws, row, values):
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col)
        cell.value = value
        if isinstance(value, str):
            cell.data_type = 's'   # text, never a formula, whatever the uploaded name starts with


def login_sheet(sheet):
    """xlsx bytes of the login sheet (RTL, one row per account). Contains the initial passwords: handed out once."""
    book = Workbook()
    ws = book.active
    ws.title = 'Logins'
    ws.sheet_view.rightToLeft = True
    _put(ws, 1, ['نقش', 'نام', 'نام کاربری', 'رمز اولیه', 'کلاس / فرزندان'])
    order = {'دانش‌آموز': 0, 'والد': 1, 'معلم': 2}
    for i, item in enumerate(sorted(sheet, key=lambda r: (order.get(r[0], 9), r[4], r[1])), start=2):
        _put(ws, i, list(item))
    _put(ws, len(sheet) + 3, ['پس از چاپ و تحویل، این فایل را پاک کنید. رمزها فقط یک بار نمایش داده می‌شوند و '
                              'کاربر در اولین ورود باید رمز خود را تغییر دهد.'])
    for col, width in zip('ABCDE', (12, 28, 16, 16, 40)):
        ws.column_dimensions[col].width = width
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def template_workbook():
    book = Workbook()
    book.remove(book.active)
    for title, columns in TEMPLATE_COLUMNS.items():
        ws = book.create_sheet(title)
        ws.append(columns)
        ws.sheet_view.rightToLeft = True
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
