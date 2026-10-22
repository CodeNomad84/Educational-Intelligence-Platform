"""C3c-0: CHARACTERIZATION tests for ``POST /api/students/import/`` (``StudentViewSet.import_students``).

Purpose: capture the CURRENT behavior of the import BEFORE C3c changes it, so every later change is a
deliberate, reviewed diff to one of these tests. These tests describe what the code does today, including
behavior that is a known defect. They assert nothing about what the import SHOULD do.

Labels used below
  [KEEP]        behavior C3c must preserve (existing contract, Admin-only, row errors, response keys).
  [C3c WILL CHANGE]  class-related behavior that C3c-2 changes on purpose (class_name no longer written,
                class linking, school assignment, new response keys). The test is updated in that commit.
  [KNOWN ISSUE - SEPARATE FIX]  pre-existing data-quality defects (owner decision D6: NOT part of C3c;
                to be fixed in a separate approved change). They must stay exactly as they are in C3c.

C3c-2 UPDATE: the tests labelled [C3c WILL CHANGE] were updated DELIBERATELY in the commit that integrated
class resolution (each says what it recorded before). Every [KEEP] and [KNOWN ISSUE - SEPARATE FIX] test is
untouched. The new integration tests are at the end of the file.

All data is synthetic.
Traceability: REQ: P2-REQ-18 (class_name is not authoritative), P2-REQ-17 (Admin-only management).
"""
import io
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from schools.models import School, SchoolClass, SchoolMembership

from .access import ADMIN, PARENT, TEACHER
from .models import Student
from .tests import make_user

URL = '/api/students/import/'
HEADER = 'first_name,last_name,national_id,grade,class_name,phone_number,father_job,mother_job'
PERSIAN_HEADER = 'نام,نام خانوادگی,کد ملی,پایه,کلاس,شماره تماس,شغل پدر,شغل مادر'
EXISTING_KEYS = {'status', 'created', 'updated', 'errors', 'total_rows'}
NEW_KEYS = {'linked', 'preserved_links', 'class_blank', 'unmatched_classes', 'unmatched_classes_truncated'}


def csv_upload(text, name='students.csv'):
    return SimpleUploadedFile(name, text.encode('utf-8-sig'), content_type='text/csv')


def xlsx_upload(rows, name='students.xlsx'):
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return SimpleUploadedFile(
        name, buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


class ImportCase(TestCase):
    def setUp(self):
        self.admin = make_user('import_admin', ADMIN)
        # S2b: the importing admin belongs to one school (the default one the test DB holds from students.0009)
        SchoolMembership.objects.create(user=self.admin, school=School.objects.get())
        self.client.force_login(self.admin)

    def post(self, upload):
        return self.client.post(URL, {'file': upload})

    def student(self, national_id):
        return Student.objects.get(national_id=national_id)

    def one_school(self, code='imp-one'):
        """Establish the 'exactly one School' precondition explicitly (the test DB already holds the default
        School created by students.0009, so this replaces it instead of relying on it)."""
        SchoolClass.objects.all().delete()
        SchoolMembership.objects.all().delete()
        School.objects.all().delete()
        school = School.objects.create(code=code, name='Characterization School')
        self.assertEqual(School.objects.count(), 1)
        SchoolMembership.objects.create(user=self.admin, school=school)  # S2b: the importer's school
        return school

    def make_existing(self, national_id='1234567890', **extra):
        data = dict(first_name='Old', last_name='Name', national_id=national_id, grade=8, phone_number='111',
                    class_name='legacy text', father_job='old job', mother_job='old job')
        data.update(extra)
        data.setdefault('school', School.objects.order_by('pk').first())  # S6: an existing student has a school
        return Student.objects.create(**data)


class ImportPermissionTests(ImportCase):
    """[KEEP] Admin-only. Nothing is created for any other caller."""

    def body(self):
        return csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n')

    def test_admin_and_superuser_may_import(self):
        self.assertEqual(self.post(self.body()).status_code, 200)
        root = make_user('import_root', is_superuser=True)
        self.client.force_login(root)
        upload = csv_upload(f'{HEADER}\nSara,Karimi,1234567891,9,9-A,9120000002,Dr,Nurse\n')
        self.assertEqual(self.post(upload).status_code, 400)   # S2b: a superuser must name the school
        upload = csv_upload(f'{HEADER}\nSara,Karimi,1234567891,9,9-A,9120000002,Dr,Nurse\n')
        self.assertEqual(self.client.post(URL, {'file': upload, 'target_school': School.objects.get().pk}
                                          ).status_code, 200)

    def test_bearer_token_authentication_is_enforced_the_same_way(self):
        """JWT is the first configured authenticator; the endpoint must honor it and the same permission."""
        from rest_framework_simplejwt.tokens import AccessToken

        self.client.logout()

        def as_bearer(user):
            return {'HTTP_AUTHORIZATION': f'Bearer {AccessToken.for_user(user)}'}

        denied = self.client.post(URL, {'file': self.body()}, **as_bearer(make_user('jwt_parent', PARENT)))
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(Student.objects.count(), 0)
        jwt_admin = make_user('jwt_admin', ADMIN)
        SchoolMembership.objects.create(user=jwt_admin, school=School.objects.get())
        allowed = self.client.post(URL, {'file': self.body()}, **as_bearer(jwt_admin))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(Student.objects.count(), 1)
        bad = self.client.post(URL, {'file': self.body()}, HTTP_AUTHORIZATION='Bearer not-a-token')
        self.assertEqual(bad.status_code, 401)

    def test_other_roles_and_anonymous_are_refused_and_create_nothing(self):
        for user in (make_user('imp_parent', PARENT), make_user('imp_teacher', TEACHER),
                     make_user('imp_nogroup'), make_user('imp_manager', 'Manager')):
            self.client.force_login(user)
            self.assertEqual(self.post(self.body()).status_code, 403, user.username)
        self.client.logout()
        self.assertIn(self.post(self.body()).status_code, (401, 403))
        self.assertEqual(Student.objects.count(), 0)


class ImportHappyPathTests(ImportCase):
    def test_create_with_english_headers_and_response_shape(self):
        """[KEEP] existing keys and values; [C3c WILL CHANGE] the set of keys grows (additive)."""
        resp = self.post(csv_upload(
            f'{HEADER}\nAli,Rezai,1234567890,9, 9-A ,9120000001,Dr,Nurse\n'
            'Sara,Karimi,1234567891,10,10-B,9120000002,Eng,Doc\n'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual({k: data[k] for k in EXISTING_KEYS},
                         {'status': 'success', 'created': 2, 'updated': 0, 'errors': [], 'total_rows': 2})
        # [C3c WILL CHANGE] was: set(data) == EXISTING_KEYS. C3c-2 adds keys and removes none.
        self.assertEqual(set(data), EXISTING_KEYS | NEW_KEYS)
        ali = self.student('1234567890')
        self.assertEqual((ali.first_name, ali.last_name, ali.grade, ali.phone_number, ali.father_job,
                          ali.mother_job), ('Ali', 'Rezai', 9, '9120000001', 'Dr', 'Nurse'))

    def test_persian_headers_are_mapped(self):
        resp = self.post(csv_upload(f'{PERSIAN_HEADER}\nعلی,رضایی,1234567890,9,9-الف,9120000001,دکتر,پرستار\n'))
        self.assertEqual((resp.status_code, resp.json()['created']), (200, 1))
        s = self.student('1234567890')
        self.assertEqual((s.first_name, s.last_name, s.grade, s.father_job), ('علی', 'رضایی', 9, 'دکتر'))

    def test_xlsx_upload(self):
        resp = self.post(xlsx_upload([
            ['first_name', 'last_name', 'national_id', 'grade', 'class_name', 'phone_number', 'father_job',
             'mother_job'],
            ['Ali', 'Rezai', 1234567890, 9, '9-A', 9120000001, 'Dr', 'Nurse']]))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual({k: resp.json()[k] for k in EXISTING_KEYS},
                         {'status': 'success', 'created': 1, 'updated': 0, 'errors': [], 'total_rows': 1})
        # [C3c WILL CHANGE] was: class_name == '9-A'. The import no longer writes class_name; no class '9-A'
        # exists here, so it stays empty. The class column of the xlsx IS read: its value is reported.
        self.assertEqual(self.student('1234567890').class_name, '')
        self.assertEqual(resp.json()['unmatched_classes'],
                         [{'row': 2, 'value': '9-A', 'reason': 'no_active_class'}])

    def test_existing_student_is_updated_by_national_id(self):
        old = self.make_existing('1234567890')
        resp = self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n'))
        data = resp.json()
        self.assertEqual((data['created'], data['updated'], data['errors']), (0, 1, []))
        new = Student.objects.get(pk=old.pk)
        self.assertEqual((new.first_name, new.grade, new.phone_number, new.father_job),
                         ('Ali', 9, '9120000001', 'Dr'))
        self.assertEqual(Student.objects.count(), 1)

    def test_duplicate_national_id_in_one_file_creates_then_updates(self):
        resp = self.post(csv_upload(
            f'{HEADER}\nAli,One,1234567890,9,9-A,9120000001,Dr,Nurse\n'
            'Ali,Two,1234567890,10,10-A,9120000001,Dr,Nurse\n'))
        data = resp.json()
        self.assertEqual((data['created'], data['updated'], data['total_rows']), (1, 1, 2))
        self.assertEqual(self.student('1234567890').last_name, 'Two')

    def test_students_not_in_the_file_are_untouched_and_nothing_is_deleted(self):
        keep = self.make_existing('1234567899', first_name='Keep')
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n'))
        keep.refresh_from_db()
        self.assertEqual((keep.first_name, keep.class_name), ('Keep', 'legacy text'))
        self.assertEqual(Student.objects.count(), 2)

    def test_import_never_creates_schools_or_classes(self):
        before = (School.objects.count(), SchoolClass.objects.count())
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n'))
        self.assertEqual((School.objects.count(), SchoolClass.objects.count()), before)

    def test_persian_digit_grade_is_accepted(self):
        resp = self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,۹,9-A,9120000001,Dr,Nurse\n'))
        self.assertEqual(resp.json()['created'], 1)
        self.assertEqual(self.student('1234567890').grade, 9)


class ImportValidationTests(ImportCase):
    """[KEEP] file-level and row-level validation and message structure."""

    def test_row_errors_do_not_block_other_rows_and_use_file_row_numbers(self):
        resp = self.post(csv_upload(
            f'{HEADER}\n'
            'Bad,Grade,1234567801,abc,9-A,9120000001,Dr,Nurse\n'      # file row 2
            'Good,One,1234567802,9,9-A,9120000002,Dr,Nurse\n'          # file row 3
            'Low,Grade,1234567803,5,9-A,9120000003,Dr,Nurse\n'         # file row 4
            'High,Grade,1234567804,13,9-A,9120000004,Dr,Nurse\n'       # file row 5
            'Good,Two,1234567805,10,10-A,9120000005,Dr,Nurse\n'))      # file row 6
        data = resp.json()
        self.assertEqual((resp.status_code, data['created'], data['updated'], data['total_rows']),
                         (200, 2, 0, 5))
        self.assertEqual(len(data['errors']), 3)
        for needle, message in zip(('ردیف 2', 'ردیف 4', 'ردیف 5'), data['errors']):
            self.assertTrue(message.startswith(needle + ':'), message)
        self.assertEqual(sorted(Student.objects.values_list('national_id', flat=True)),
                         ['1234567802', '1234567805'])

    def test_blank_grade_is_a_row_error(self):
        resp = self.post(csv_upload(
            f'{HEADER}\nNo,Grade,1234567801,,9-A,9120000001,Dr,Nurse\nOk,Row,1234567802,9,9-A,9120000002,Dr,Nurse\n'))
        data = resp.json()
        self.assertEqual((data['created'], len(data['errors'])), (1, 1))
        self.assertTrue(data['errors'][0].startswith('ردیف 2:'))

    def test_missing_required_column_is_a_400(self):
        resp = self.post(csv_upload('first_name,last_name,grade\nAli,Rezai,9\n'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('national_id', resp.json()['error'])
        self.assertEqual(Student.objects.count(), 0)

    def test_unsupported_extension_is_a_400(self):
        resp = self.post(SimpleUploadedFile('students.txt', b'x', content_type='text/plain'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('csv, xlsx, xls', resp.json()['error'])

    def test_header_only_file_is_a_400(self):
        resp = self.post(csv_upload(HEADER + '\n'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.json())

    def test_zero_byte_file_is_refused_by_the_serializer_with_a_400(self):
        """Never reaches pandas: DRF's FileField rejects an empty upload (field error, not an 'error' key)."""
        resp = self.post(SimpleUploadedFile('empty.csv', b'', content_type='text/csv'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('file', resp.json())
        self.assertEqual(Student.objects.count(), 0)

    def test_missing_file_is_a_400_with_field_errors(self):
        resp = self.client.post(URL, {})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('file', resp.json())


class ImportClassBehaviourTests(ImportCase):
    """[C3c WILL CHANGE] how the class column is handled today (class_name is written; nothing is linked)."""

    def test_matching_active_class_is_linked_and_class_name_is_derived_not_written(self):
        """[C3c WILL CHANGE] was: class_name written (stripped) and nothing linked even with a matching
        active class and a single School. Now the matching class is linked and class_name is its mirror."""
        school = self.one_school()
        klass = SchoolClass.objects.create(school=school, title='9-A')
        resp = self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,  9-A  ,9120000001,Dr,Nurse\n'))
        s = self.student('1234567890')
        self.assertEqual((s.school_class_id, s.school_id, s.class_name), (klass.pk, school.pk, '9-A'))
        self.assertEqual(klass.students.count(), 1)
        self.assertEqual((resp.json()['linked'], resp.json()['unmatched_classes']), (1, []))

    def test_unlinked_existing_student_keeps_class_name_and_is_reported_when_class_is_unknown(self):
        """[C3c WILL CHANGE] was: class_name overwritten with the file text ('9-B'). Now class_name is left
        alone, the student stays unlinked, gets the unique School, and the class is reported."""
        school = self.one_school()
        old = self.make_existing('1234567890', class_name='legacy text')
        resp = self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-B,9120000001,Dr,Nurse\n'))
        old.refresh_from_db()
        self.assertEqual((old.class_name, old.school_class_id, old.school_id), ('legacy text', None, school.pk))
        self.assertEqual(resp.json()['unmatched_classes'],
                         [{'row': 2, 'value': '9-B', 'reason': 'no_active_class'}])

    def test_linked_student_keeps_the_link_and_the_mirror_discards_the_file_class(self):
        """[KEEP] the link is immutable. The file names ANOTHER class that really exists and is active, so a
        future change that re-links by name would be caught here. [C3c WILL CHANGE] only what is reported."""
        school = self.one_school()
        klass = SchoolClass.objects.create(school=school, title='X-1')
        other = SchoolClass.objects.create(school=school, title='Y-2')   # exists, active, same school
        linked = Student.objects.create(first_name='L', last_name='K', national_id='1234567890', grade=9,
                                        phone_number='1', school_class=klass)
        self.assertEqual((linked.class_name, linked.school_id, linked.school_class_id),
                         ('X-1', school.pk, klass.pk))
        resp = self.post(csv_upload(f'{HEADER}\nLinked,Kid,1234567890,9, Y-2 ,9120000001,Dr,Nurse\n'))
        self.assertEqual((resp.json()['updated'], resp.json()['errors']), (1, []))
        linked.refresh_from_db()
        self.assertEqual((linked.school_class_id, linked.school_id, linked.class_name),
                         (klass.pk, school.pk, 'X-1'))
        self.assertEqual(other.students.count(), 0)
        self.assertEqual(linked.first_name, 'Linked')   # other fields are still updated

    def test_linked_student_keeps_the_link_when_the_file_has_no_class_column(self):
        school = self.one_school()
        klass = SchoolClass.objects.create(school=school, title='X-1')
        linked = Student.objects.create(first_name='L', last_name='K', national_id='1234567890', grade=9,
                                        phone_number='1', school_class=klass)
        self.post(csv_upload('first_name,last_name,national_id,grade\nLinked,Kid,1234567890,9\n'))
        linked.refresh_from_db()
        self.assertEqual((linked.school_class_id, linked.school_id, linked.class_name),
                         (klass.pk, school.pk, 'X-1'))

    def test_new_students_get_the_unique_school_but_no_class_when_unresolved(self):
        """[C3c WILL CHANGE] was: school None. Decision D1: with exactly one School a new student gets it."""
        school = self.one_school()
        resp = self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n'))
        s = self.student('1234567890')
        self.assertEqual((s.school_id, s.school_class_id), (school.pk, None))
        self.assertEqual(resp.json()['linked'], 0)   # assigning the School is not a class link


class ImportKnownIssueTests(ImportCase):
    """[KNOWN ISSUE - SEPARATE FIX] Defects that exist today. C3c must NOT change any of these (owner D6).

    These tests document defects; they do NOT describe desired behavior. National-id and phone normalization
    (leading zeros, '.0' suffixes, 'nan') is potentially IDENTITY-AFFECTING data loss and needs a dedicated,
    separately approved fix with its own tests. Previously corrupted records are not repaired here.
    """

    def test_missing_optional_columns_blank_existing_phone_and_parent_jobs(self):
        """Identity-adjacent data loss. Must stay exactly as is in C3c; fixed only by its own change."""
        self.make_existing('1234567890', phone_number='9120000001', father_job='Dr', mother_job='Nurse')
        self.post(csv_upload('first_name,last_name,national_id,grade\nAli,Rezai,1234567890,9\n'))
        s = self.student('1234567890')
        self.assertEqual((s.phone_number, s.father_job, s.mother_job), ('', '', ''))

    def test_missing_class_column_no_longer_blanks_an_unlinked_students_class_name(self):
        """[C3c WILL CHANGE] was: class_name blanked to ''. The import no longer writes class_name. (The
        blanking of phone and parent jobs, a D6 known issue, is a separate test above and is unchanged.)"""
        self.make_existing('1234567890', class_name='legacy text')
        resp = self.post(csv_upload('first_name,last_name,national_id,grade\nAli,Rezai,1234567890,9\n'))
        self.assertEqual(self.student('1234567890').class_name, 'legacy text')
        self.assertEqual((resp.json()['class_blank'], resp.json()['unmatched_classes']), (1, []))

    def test_blank_optional_cell_is_stored_as_the_text_nan(self):
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,,Nurse\n'))
        self.assertEqual(self.student('1234567890').father_job, 'nan')

    def test_blank_class_cell_writes_nothing_and_is_not_reported(self):
        """[C3c WILL CHANGE] was: class_name stored as the text 'nan'. Decision D9: a blank class cell is
        counted in class_blank, writes nothing and is not an unmatched class."""
        resp = self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,,9120000001,Dr,Nurse\n'))
        self.assertEqual(self.student('1234567890').class_name, '')
        self.assertEqual((resp.json()['class_blank'], resp.json()['unmatched_classes']), (1, []))

    def test_leading_zeros_of_identifier_columns_are_kept(self):
        """[P3 CHANGED] was: leading zeros of national_id and phone_number were lost (numeric inference)."""
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,0123456789,9,9-A,09120000001,Dr,Nurse\n'))
        s = Student.objects.get()
        self.assertEqual((s.national_id, s.phone_number), ('0123456789', '09120000001'))


class ImportNationalIdValidationTests(ImportCase):
    """[P3] national_id is read as text and validated before any write (import path only)."""

    def import_ids(self, *cells):
        rows = ''.join(f'Ali{i},Rezai,{c},9,9-A,9120000001,Dr,Nurse\n' for i, c in enumerate(cells))
        return self.post(csv_upload(f'{HEADER}\n{rows}')).json()

    def stored(self):
        return sorted(Student.objects.values_list('national_id', flat=True))

    def test_blank_national_id_does_not_corrupt_other_rows(self):
        data = self.import_ids('1234567890', '')
        self.assertEqual((data['created'], self.stored()), (1, ['1234567890']))
        self.assertEqual(data['errors'], ['ردیف 3: کد ملی خالی است.'])

    def test_nan_text_national_id_is_rejected(self):
        for cell in ('nan', 'NaN', 'None', 'null'):
            with self.subTest(cell=cell):
                data = self.import_ids(cell)
                self.assertEqual((data['created'], self.stored()), (0, []))
                self.assertEqual(data['errors'], ['ردیف 2: کد ملی معتبر نیست.'])

    def test_float_text_national_id_is_rejected(self):
        data = self.import_ids('1234567890.0')
        self.assertEqual((data['created'], self.stored()), (0, []))
        self.assertEqual(data['errors'], ['ردیف 2: کد ملی معتبر نیست.'])

    def test_non_digit_national_id_is_rejected(self):
        for cell in ('12A4567890', '123-456', '12 34'):
            with self.subTest(cell=cell):
                data = self.import_ids(cell)
                self.assertEqual((data['created'], self.stored()), (0, []))
                self.assertEqual(data['errors'], ['ردیف 2: کد ملی باید فقط شامل ارقام باشد.'])

    def test_too_long_national_id_is_rejected_before_any_database_write(self):
        data = self.import_ids('12345678901')
        self.assertEqual((data['created'], self.stored()), (0, []))
        self.assertEqual(data['errors'], ['ردیف 2: کد ملی نباید بیش از ۱۰ رقم باشد.'])
        self.assertNotIn('varying', ' '.join(data['errors']))

    def test_one_to_ten_digits_are_valid_and_keep_their_text_form(self):
        data = self.import_ids('123456789', '0123456789', '7')
        self.assertEqual((data['created'], data['errors']), (3, []))
        self.assertEqual(self.stored(), ['0123456789', '123456789', '7'])

    def test_persian_and_arabic_indic_digits_are_normalised_to_ascii(self):
        data = self.import_ids('۱۲۳۴۵۶۷۸۹۰', '٠١٢٣٤٥٦٧٨٩')
        self.assertEqual((data['created'], data['errors']), (2, []))
        self.assertEqual(self.stored(), ['0123456789', '1234567890'])

    def test_identical_ids_in_different_scripts_are_one_student(self):
        data = self.import_ids('1234567890', '۱۲۳۴۵۶۷۸۹۰')
        self.assertEqual((data['created'], data['updated'], self.stored()), (1, 1, ['1234567890']))


# =====================================================================================================
# C3c-2 integration tests: class resolution during import (helper: students/class_resolution.py)
# =====================================================================================================
def nid(i):
    return f'{1000000000 + i}'


def line(national_id, grade, class_cell='', first='Ali', last='Rezai'):
    return f'{first},{last},{national_id},{grade},{class_cell},9120000001,Dr,Nurse'


def sheet(*lines):
    return csv_upload(HEADER + '\n' + '\n'.join(lines) + '\n')


class ClassImportCase(ImportCase):
    def klass(self, school, title, **extra):
        return SchoolClass.objects.create(school=school, title=title, **extra)

    def member(self, national_id, grade, klass):
        """An existing student already linked to ``klass`` (the model derives school and class_name)."""
        return Student.objects.create(first_name='M', last_name='K', national_id=national_id, grade=grade,
                                      phone_number='1', school_class=klass)

    def structure(self):
        return (School.objects.count(), SchoolClass.objects.count(),
                sorted(SchoolClass.objects.values_list('pk', 'title', 'is_active', 'academic_year')))

    def two_schools(self):
        first = self.one_school('imp-a')
        second = School.objects.create(code='imp-b', name='Second School')
        return first, second


class ImportClassResolutionTests(ClassImportCase):
    def test_one_school_and_one_active_class_link_a_new_student(self):
        school = self.one_school()
        klass = self.klass(school, '9-A')
        resp = self.post(sheet(line(nid(1), 9, ' 9-A ')))
        data = resp.json()
        s = self.student(nid(1))
        self.assertEqual((s.school_id, s.school_class_id, s.class_name), (school.pk, klass.pk, '9-A'))
        self.assertEqual((data['created'], data['linked'], data['preserved_links'], data['class_blank']),
                         (1, 1, 0, 0))
        self.assertEqual((data['unmatched_classes'], data['unmatched_classes_truncated']), ([], False))

    def test_a_class_that_exists_only_in_another_school_is_never_selected(self):
        # S2b: the import's school comes from the importer's membership (first); a class of `second` is not a candidate.
        first, second = self.two_schools()
        self.klass(second, '9-A')
        resp = self.post(sheet(line(nid(1), 9, '9-A')))
        s = self.student(nid(1))
        self.assertEqual((s.school_id, s.school_class_id), (first.pk, None))
        self.assertEqual(resp.json()['unmatched_classes'],
                         [{'row': 2, 'value': '9-A', 'reason': 'no_active_class'}])

    def test_an_importer_without_a_school_is_rejected_and_nothing_is_created(self):
        # S2b (was: zero schools -> students imported without a school): no membership, no import.
        self.one_school()
        SchoolMembership.objects.all().delete()
        resp = self.post(sheet(line(nid(1), 9, '9-A')))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('target_school', resp.json())
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(School.objects.count(), 1)   # the import never creates a School

    def test_several_schools_link_only_inside_the_importers_school(self):
        # S2b (was: several schools -> no_unique_school): the class of the importer's school is the only candidate.
        first, second = self.two_schools()
        mine = self.klass(first, '9-A')
        self.klass(second, '9-A')
        resp = self.post(sheet(line(nid(1), 9, '9-A')))
        s = self.student(nid(1))
        self.assertEqual((s.school_id, s.school_class_id), (first.pk, mine.pk))
        self.assertEqual(resp.json()['unmatched_classes'], [])
        self.assertEqual(resp.json()['linked'], 1)

    def test_no_school_or_class_is_created_activated_or_changed_on_any_path(self):
        school = self.one_school()
        self.klass(school, '9-A')
        self.klass(school, '9-Z', is_active=False)
        self.member(nid(50), 10, self.klass(school, '10-A'))
        before = self.structure()
        self.post(sheet(line(nid(1), 9, '9-A'), line(nid(2), 9, '9-Z'), line(nid(3), 9, 'missing'),
                        line(nid(4), 10, '10-A'), line(nid(5), 9, '10-A'), line(nid(6), 9, '')))
        self.assertEqual(self.structure(), before)

    def test_inactive_class_is_reported_not_linked_and_not_reactivated(self):
        school = self.one_school()
        closed = self.klass(school, '9-Z', is_active=False)
        resp = self.post(sheet(line(nid(1), 9, '9-Z')))
        self.assertIsNone(self.student(nid(1)).school_class_id)
        closed.refresh_from_db()
        self.assertFalse(closed.is_active)
        self.assertEqual(resp.json()['unmatched_classes'], [{'row': 2, 'value': '9-Z', 'reason': 'inactive_class'}])

    def test_unknown_class_is_no_active_class(self):
        self.one_school()
        resp = self.post(sheet(line(nid(1), 9, 'nowhere')))
        self.assertEqual(resp.json()['unmatched_classes'],
                         [{'row': 2, 'value': 'nowhere', 'reason': 'no_active_class'}])

    def test_duplicate_normalized_active_titles_are_ambiguous(self):
        school = self.one_school()
        self.klass(school, '9-A', academic_year='1403')
        self.klass(school, ' 9-A ', academic_year='1404')
        resp = self.post(sheet(line(nid(1), 9, '9-A')))
        self.assertIsNone(self.student(nid(1)).school_class_id)
        self.assertEqual(resp.json()['unmatched_classes'], [{'row': 2, 'value': '9-A', 'reason': 'ambiguous'}])

    def test_single_active_class_in_a_non_empty_academic_year_links_per_the_helper_policy(self):
        school = self.one_school()
        klass = self.klass(school, '9-A', academic_year='1404')
        self.post(sheet(line(nid(1), 9, '9-A')))
        self.assertEqual(self.student(nid(1)).school_class_id, klass.pk)

    def test_two_active_classes_in_different_years_stay_ambiguous_whatever_their_order(self):
        school = self.one_school()
        self.klass(school, '9-A', academic_year='1404')
        self.klass(school, '9-A', academic_year='')
        resp = self.post(sheet(line(nid(1), 9, '9-A')))
        self.assertEqual([u['reason'] for u in resp.json()['unmatched_classes']], ['ambiguous'])

    def test_blank_class_cells_are_counted_not_reported(self):
        self.one_school()
        resp = self.post(sheet(line(nid(1), 9, ''), line(nid(2), 9, '   ')))
        data = resp.json()
        self.assertEqual((data['class_blank'], data['unmatched_classes'], data['linked']), (2, [], 0))
        self.assertEqual(data['created'], 2)

    def test_old_files_without_a_class_column_import_as_before(self):
        school = self.one_school()
        resp = self.post(csv_upload('first_name,last_name,national_id,grade\nAli,Rezai,1000000001,9\n'))
        data = resp.json()
        self.assertEqual((resp.status_code, data['created'], data['errors']), (200, 1, []))
        self.assertEqual((data['class_blank'], data['unmatched_classes'], data['linked']), (1, [], 0))
        self.assertEqual(self.student(nid(1)).school_id, school.pk)

    def test_numeric_and_missing_class_cells_follow_class_text(self):
        school = self.one_school()
        klass = self.klass(school, '9')
        head = ['first_name', 'last_name', 'national_id', 'grade', 'class_name', 'phone_number', 'father_job',
                'mother_job']
        resp = self.post(xlsx_upload([
            head,
            ['A', 'R', 1000000001, 9, 9, 9120000001, 'Dr', 'N'],       # integer cell
            ['B', 'R', 1000000002, 9, 9.0, 9120000002, 'Dr', 'N'],     # whole float cell
            ['C', 'R', 1000000003, 9, None, 9120000003, 'Dr', 'N'],    # genuinely missing cell
            ['D', 'R', 1000000004, 9, 9.5, 9120000004, 'Dr', 'N'],     # not rounded to 9
        ]))
        data = resp.json()
        self.assertEqual(self.student(nid(1)).school_class_id, klass.pk)
        self.assertEqual(self.student(nid(2)).school_class_id, klass.pk)
        self.assertIsNone(self.student(nid(3)).school_class_id)
        self.assertIsNone(self.student(nid(4)).school_class_id)
        self.assertEqual((data['linked'], data['class_blank']), (2, 1))
        self.assertEqual(data['unmatched_classes'], [{'row': 5, 'value': '9.5', 'reason': 'no_active_class'}])


class ImportExistingLinkTests(ClassImportCase):
    def test_linked_student_keeps_class_school_and_mirror_and_is_not_reported(self):
        school = self.one_school()
        x = self.klass(school, 'X-1')
        self.klass(school, 'Y-2')    # an existing ACTIVE class that the file names instead
        self.member(nid(1), 9, x)
        resp = self.post(sheet(line(nid(1), 9, 'Y-2'), line(nid(2), 9, 'does-not-exist')))
        data = resp.json()
        s = self.student(nid(1))
        self.assertEqual((s.school_class_id, s.school_id, s.class_name), (x.pk, school.pk, 'X-1'))
        self.assertEqual((data['preserved_links'], data['linked']), (1, 0))
        self.assertEqual([u['row'] for u in data['unmatched_classes']], [3])   # row 2 (linked) not reported

    def test_preserved_links_counts_students_not_rows(self):
        school = self.one_school()
        x = self.klass(school, 'X-1')
        self.member(nid(1), 9, x)
        self.member(nid(2), 9, x)
        resp = self.post(sheet(line(nid(1), 9, 'X-1'), line(nid(1), 9, 'X-1'), line(nid(2), 9, ''),
                               line(nid(3), 9, 'X-1')))
        data = resp.json()
        self.assertEqual((data['preserved_links'], data['linked'], data['class_blank']), (2, 1, 0))

    def test_a_student_of_another_school_is_not_moved_or_linked(self):
        """S3: the planning reads are scoped to the importer's school, so another school's student is invisible to the
        class planning and is refused at write with the generic message (no unmatched-class entry, no oracle)."""
        first, second = self.two_schools()
        klass = self.klass(first, '9-A')
        Student.objects.create(first_name='S', last_name='K', national_id=nid(1), grade=9, phone_number='1',
                               school=second)
        with mock.patch('students.views.School.objects') as schools:
            schools.values_list.return_value = [first.pk]    # pretend `first` is the only School
            resp = self.post(sheet(line(nid(1), 9, '9-A')))
        s = self.student(nid(1))
        self.assertEqual((s.school_id, s.school_class_id), (second.pk, None))
        data = resp.json()
        self.assertEqual((data['created'], data['updated'], data['linked'], data['unmatched_classes']), (0, 0, 0, []))
        self.assertEqual(len(data['errors']), 1)
        self.assertEqual(klass.students.count(), 0)

    def test_linked_counts_only_new_class_relationships_not_school_assignment(self):
        school = self.one_school()
        self.klass(school, '9-A')
        resp = self.post(sheet(line(nid(1), 9, 'nowhere'), line(nid(2), 9, '')))
        self.assertEqual(resp.json()['linked'], 0)
        for i in (1, 2):
            self.assertEqual(self.student(nid(i)).school_id, school.pk)
            self.assertIsNone(self.student(nid(i)).school_class_id)


class ImportGradeGuardTests(ClassImportCase):
    def test_existing_grade_9_and_incoming_grade_10_block_the_link(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 9, x)
        resp = self.post(sheet(line(nid(2), 10, 'X')))
        self.assertIsNone(self.student(nid(2)).school_class_id)
        self.assertEqual(resp.json()['unmatched_classes'], [{'row': 2, 'value': 'X', 'reason': 'grade_conflict'}])
        self.assertEqual(resp.json()['created'], 1)   # the student itself is still imported

    def test_two_incoming_rows_with_different_grades_block_every_link_to_that_class(self):
        school = self.one_school()
        self.klass(school, 'X')
        resp = self.post(sheet(line(nid(1), 9, 'X'), line(nid(2), 10, 'X'), line(nid(3), 9, 'X')))
        for i in (1, 2, 3):
            self.assertIsNone(self.student(nid(i)).school_class_id, i)
        self.assertEqual([(u['row'], u['reason']) for u in resp.json()['unmatched_classes']],
                         [(2, 'grade_conflict'), (3, 'grade_conflict'), (4, 'grade_conflict')])

    def test_row_order_does_not_change_the_decisions(self):
        school = self.one_school()
        x, y, z = self.klass(school, 'X'), self.klass(school, 'Y'), self.klass(school, 'Z')
        self.member(nid(90), 9, x)
        rows = [(nid(1), 9, 'X'), (nid(2), 10, 'X'), (nid(3), 9, 'Y'), (nid(4), 10, 'Y'), (nid(5), 11, 'Z')]
        outcomes = []
        for order in (rows, list(reversed(rows)), [rows[2], rows[4], rows[0], rows[3], rows[1]]):
            Student.objects.filter(national_id__in=[r[0] for r in rows]).delete()
            self.post(sheet(*[line(*row) for row in order]))
            outcomes.append({r[0]: self.student(r[0]).school_class_id for r in rows})
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])
        self.assertEqual({k: v is not None for k, v in outcomes[0].items()},
                         {nid(1): False, nid(2): False, nid(3): False, nid(4): False, nid(5): True})

    def test_existing_members_with_inconsistent_grades_block_new_links(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 7, x)
        self.member(nid(2), 8, x)
        resp = self.post(sheet(line(nid(3), 7, 'X')))
        self.assertIsNone(self.student(nid(3)).school_class_id)
        self.assertEqual([u['reason'] for u in resp.json()['unmatched_classes']], ['grade_conflict'])

    def test_a_changed_grade_of_a_linked_member_is_used_not_the_stored_one(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 9, x)
        # the file moves the linked member to grade 10; a new grade-10 student then fits the class
        resp = self.post(sheet(line(nid(1), 10, 'X'), line(nid(2), 10, 'X')))
        self.assertEqual(self.student(nid(1)).grade, 10)
        self.assertEqual(self.student(nid(1)).school_class_id, x.pk)      # link preserved
        self.assertEqual(self.student(nid(2)).school_class_id, x.pk)      # no conflict: effective grades are {10}
        self.assertEqual((resp.json()['linked'], resp.json()['preserved_links'], resp.json()['unmatched_classes']),
                         (1, 1, []))

    def test_a_changed_grade_of_a_linked_member_can_also_create_a_conflict(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 9, x)
        # stored grade 9 would suit a grade-9 newcomer, but the member becomes grade 10 in this very file
        resp = self.post(sheet(line(nid(1), 10, 'X'), line(nid(2), 9, 'X')))
        self.assertEqual(self.student(nid(1)).school_class_id, x.pk)
        self.assertIsNone(self.student(nid(2)).school_class_id)
        self.assertEqual(resp.json()['unmatched_classes'], [{'row': 3, 'value': 'X', 'reason': 'grade_conflict'}])

    def test_a_linked_students_other_class_never_becomes_a_proposed_link(self):
        school = self.one_school()
        x, y = self.klass(school, 'X'), self.klass(school, 'Y')
        self.member(nid(1), 9, x)
        # nid(1) is linked to X and names Y with grade 9; the grade-10 newcomer must still fit Y
        resp = self.post(sheet(line(nid(1), 9, 'Y'), line(nid(2), 10, 'Y')))
        self.assertEqual(self.student(nid(1)).school_class_id, x.pk)
        self.assertEqual(self.student(nid(2)).school_class_id, y.pk)
        self.assertEqual(resp.json()['unmatched_classes'], [])

    def test_invalid_or_missing_grades_never_become_valid_grades(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        resp = self.post(sheet(line(nid(1), 'abc', 'X'), line(nid(2), '', 'X'), line(nid(3), 13, 'X'),
                               line(nid(4), 9, 'X')))
        data = resp.json()
        self.assertEqual((data['created'], len(data['errors'])), (1, 3))
        self.assertEqual(self.student(nid(4)).school_class_id, x.pk)   # the only valid row links, no conflict
        self.assertFalse(Student.objects.filter(national_id__in=[nid(1), nid(2), nid(3)]).exists())

    def test_duplicate_rows_of_one_student_with_the_same_class_link_it_once(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        resp = self.post(sheet(line(nid(1), 9, 'X'), line(nid(1), 9, 'X')))
        data = resp.json()
        self.assertEqual((data['created'], data['updated'], data['linked']), (1, 1, 1))
        self.assertEqual(self.student(nid(1)).school_class_id, x.pk)

    def test_duplicate_rows_naming_different_classes_are_ambiguous_and_not_linked(self):
        school = self.one_school()
        self.klass(school, 'X')
        self.klass(school, 'Y')
        resp = self.post(sheet(line(nid(1), 9, 'X'), line(nid(1), 9, 'Y')))
        self.assertIsNone(self.student(nid(1)).school_class_id)
        self.assertEqual([(u['row'], u['reason']) for u in resp.json()['unmatched_classes']],
                         [(2, 'ambiguous'), (3, 'ambiguous')])

    def test_duplicate_rows_with_different_grades_are_conservatively_not_linked(self):
        school = self.one_school()
        self.klass(school, 'X')
        resp = self.post(sheet(line(nid(1), 9, 'X'), line(nid(1), 10, 'X')))
        s = self.student(nid(1))
        self.assertEqual((s.grade, s.school_class_id), (10, None))     # data semantics unchanged: last row wins
        self.assertEqual([u['reason'] for u in resp.json()['unmatched_classes']], ['grade_conflict'] * 2)


class ImportResponseContractTests(ClassImportCase):
    def test_legacy_keys_keep_their_meaning_and_new_keys_are_present(self):
        school = self.one_school()
        self.klass(school, 'X')
        self.make_existing(nid(2), grade=9)
        data = self.post(sheet(line(nid(1), 9, 'X'), line(nid(2), 9, 'X'), line(nid(3), 'abc', 'X'))).json()
        self.assertEqual(set(data), EXISTING_KEYS | NEW_KEYS)
        self.assertEqual((data['status'], data['created'], data['updated'], data['total_rows']),
                         ('success', 1, 1, 3))
        self.assertEqual(len(data['errors']), 1)
        self.assertTrue(data['errors'][0].startswith('ردیف 4:'))      # file row numbering is unchanged
        self.assertEqual((data['linked'], data['preserved_links'], data['class_blank']), (2, 0, 0))

    def test_unmatched_entries_carry_class_text_row_and_reason_only(self):
        self.one_school()
        resp = self.post(sheet(line(nid(1), 9, 'ghost-class', first='Zahra', last='Mohammadi')))
        entries = resp.json()['unmatched_classes']
        self.assertEqual(entries, [{'row': 2, 'value': 'ghost-class', 'reason': 'no_active_class'}])
        dump = json.dumps(resp.json()['unmatched_classes'], ensure_ascii=False)
        for personal in ('Zahra', 'Mohammadi', nid(1), '9120000001', 'Dr', 'Nurse'):
            self.assertNotIn(personal, dump)

    def test_the_unmatched_list_is_capped_at_200_with_a_truncation_flag(self):
        self.one_school()
        exactly = self.post(sheet(*[line(nid(i), 9, f'Q{i}') for i in range(200)])).json()
        self.assertEqual((len(exactly['unmatched_classes']), exactly['unmatched_classes_truncated']), (200, False))
        over = self.post(sheet(*[line(nid(1000 + i), 9, f'R{i}') for i in range(201)])).json()
        self.assertEqual((len(over['unmatched_classes']), over['unmatched_classes_truncated']), (200, True))
        self.assertEqual((over['unmatched_classes'][0]['row'], over['unmatched_classes'][-1]['row']), (2, 201))
        self.assertEqual(over['created'], 201)   # truncation only affects the report, never the import

    def test_long_class_values_are_truncated_in_the_report(self):
        self.one_school()
        resp = self.post(sheet(line(nid(1), 9, 'Z' * 150)))
        self.assertEqual(len(resp.json()['unmatched_classes'][0]['value']), 100)

    def test_unmatched_classes_do_not_stop_valid_rows_and_row_numbers_stay_compatible(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        resp = self.post(sheet(line(nid(1), 9, 'nope'), line(nid(2), 'abc', 'X'), line(nid(3), 9, 'X')))
        data = resp.json()
        self.assertEqual((data['created'], data['linked'], data['total_rows']), (2, 1, 3))
        self.assertEqual([u['row'] for u in data['unmatched_classes']], [2])
        self.assertEqual(len(data['errors']), 1)
        self.assertTrue(data['errors'][0].startswith('ردیف 3:'))
        self.assertEqual(self.student(nid(3)).school_class_id, x.pk)
        self.assertIsNone(self.student(nid(1)).school_class_id)


# =====================================================================================================
# Write failures (C3c-2 review): decisions must rest on what is PERSISTED, and counters on what SUCCEEDED.
# A failure is injected by patching Student.save to raise a DatabaseError for one national_id (no DB-specific
# SQL, so it runs on SQLite and PostgreSQL alike). Every import write goes through update_or_create -> save(),
# so the whole path still runs: the per-row transaction, rollback, and the error report.
# =====================================================================================================
class ImportWriteFailureTests(ClassImportCase):
    def fail_writes(self, national_id, event='UPDATE'):
        """Make Student.save() fail for ``national_id`` on an UPDATE (existing row) or an INSERT (new row)."""
        from django.db import DatabaseError
        original = Student.save
        failing = (national_id, event)

        def save(instance, *args, **kwargs):
            kind = 'INSERT' if instance._state.adding else 'UPDATE'
            if (instance.national_id, kind) == failing:
                raise DatabaseError('simulated write failure')
            return original(instance, *args, **kwargs)

        patcher = mock.patch.object(Student, 'save', save)
        patcher.start()
        self.addCleanup(patcher.stop)

    def class_grades(self, klass):
        return sorted(Student.objects.filter(school_class=klass).values_list('grade', flat=True))

    def test_failed_write_of_a_linked_member_does_not_justify_new_links(self):
        """The guard must not rely on a grade that was never stored (the reviewed failure mode)."""
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 9, x)
        self.fail_writes(nid(1), 'UPDATE')      # the member's grade change (9 -> 10) cannot be stored
        resp = self.post(sheet(line(nid(1), 10, 'X'), line(nid(2), 10, 'X')))
        data = resp.json()
        member, newcomer = self.student(nid(1)), self.student(nid(2))
        self.assertEqual((member.grade, member.school_class_id), (9, x.pk))     # unchanged, still linked
        self.assertIsNone(newcomer.school_class_id)                              # NOT linked on a phantom grade
        self.assertEqual(newcomer.grade, 10)                                     # the student itself is imported
        self.assertEqual(self.class_grades(x), [9])                              # the class stays consistent
        self.assertEqual((data['created'], data['updated'], data['linked']), (1, 0, 0))
        self.assertEqual(len(data['errors']), 1)
        self.assertTrue(data['errors'][0].startswith('ردیف 2:'))
        self.assertEqual(data['unmatched_classes'], [{'row': 3, 'value': 'X', 'reason': 'grade_conflict'}])

    def test_failed_write_of_a_linked_member_still_allows_links_that_fit_the_stored_grade(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 9, x)
        self.fail_writes(nid(1), 'UPDATE')
        resp = self.post(sheet(line(nid(1), 10, 'X'), line(nid(2), 9, 'X')))
        self.assertEqual(self.student(nid(2)).school_class_id, x.pk)            # fits the persisted grade 9
        self.assertEqual(self.class_grades(x), [9, 9])
        self.assertEqual((resp.json()['linked'], resp.json()['unmatched_classes']), (1, []))

    def test_preserved_links_counts_a_linked_student_whose_row_failed(self):
        """Documented semantics: a linked student that appears in a valid row keeps its link, written or not."""
        school = self.one_school()
        x = self.klass(school, 'X')
        self.member(nid(1), 9, x)
        self.fail_writes(nid(1), 'UPDATE')
        data = self.post(sheet(line(nid(1), 10, 'X'))).json()
        self.assertEqual((data['preserved_links'], data['updated'], len(data['errors'])), (1, 0, 1))
        self.assertEqual(self.student(nid(1)).school_class_id, x.pk)

    def test_failed_insert_of_a_new_student_is_not_counted_and_leaves_nothing_behind(self):
        school = self.one_school()
        x = self.klass(school, 'X')
        self.fail_writes(nid(2), 'INSERT')
        data = self.post(sheet(line(nid(1), 9, 'X'), line(nid(2), 9, 'X'), line(nid(3), 9, 'X'))).json()
        self.assertFalse(Student.objects.filter(national_id=nid(2)).exists())
        self.assertEqual((data['created'], data['linked'], len(data['errors'])), (2, 2, 1))
        self.assertTrue(data['errors'][0].startswith('ردیف 3:'))
        self.assertEqual(self.class_grades(x), [9, 9])

    def test_failed_update_of_an_unlinked_student_keeps_it_unlinked_unscored_and_uncounted(self):
        school = self.one_school()
        self.klass(school, 'X')
        old = self.make_existing(nid(1), grade=8, school=school)
        self.fail_writes(nid(1), 'UPDATE')
        data = self.post(sheet(line(nid(1), 9, 'X'))).json()
        old.refresh_from_db()
        self.assertEqual((old.grade, old.school_id, old.school_class_id), (8, school.pk, None))   # fully rolled back
        self.assertEqual((data['linked'], data['updated'], len(data['errors'])), (0, 0, 1))

    def test_a_link_created_after_planning_is_re_read_and_never_overwritten(self):
        from students import views
        school = self.one_school()
        x, y = self.klass(school, 'X'), self.klass(school, 'Y')
        self.make_existing(nid(1), grade=9)
        real_plan = views._plan_class_links

        def plan_then_someone_else_links(rows, school_id):
            plan = real_plan(rows, school_id)   # decided: link nid(1) to X
            Student.objects.filter(national_id=nid(1)).update(school=school, school_class=y, class_name='Y')
            return plan

        with mock.patch.object(views, '_plan_class_links', plan_then_someone_else_links):
            data = self.post(sheet(line(nid(1), 9, 'X'))).json()
        s = self.student(nid(1))
        self.assertEqual((s.school_class_id, s.school_id), (y.pk, school.pk))    # the other link wins
        self.assertEqual((data['linked'], data['updated']), (0, 1))


class ImportLinkedStudentWriteTests(ClassImportCase):
    """Review C: what the import may and may not write for a student that already has a class."""

    def test_only_the_imported_fields_change_derived_fields_are_not_rewritten(self):
        school = self.one_school()
        x = self.klass(school, 'X-1')
        self.klass(school, 'Y-2')
        self.member(nid(1), 9, x)
        # simulate drift of the derived mirror: if the import rewrote class_name/school it would show here
        Student.objects.filter(national_id=nid(1)).update(class_name='drifted mirror')
        before = Student.objects.values('school_id', 'school_class_id', 'created_at').get(national_id=nid(1))
        resp = self.post(sheet(line(nid(1), 10, 'Y-2', first='Renamed')))
        s = self.student(nid(1))
        self.assertEqual((s.first_name, s.grade), ('Renamed', 10))                 # imported fields change
        self.assertEqual((s.school_id, s.school_class_id, s.class_name),
                         (before['school_id'], before['school_class_id'], 'drifted mirror'))
        self.assertEqual(s.created_at, before['created_at'])
        self.assertEqual((resp.json()['updated'], resp.json()['linked'], resp.json()['preserved_links']), (1, 0, 1))


class ImportTargetSchoolTests(ClassImportCase):
    """S2b: the school of an import comes from the importer's memberships or an explicit target, never from the file."""

    def test_several_memberships_require_a_target_and_nothing_is_read_or_written_without_it(self):
        first, second = self.two_schools()
        SchoolMembership.objects.create(user=self.admin, school=second)
        resp = self.post(sheet(line(nid(1), 9)))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('target_school', resp.json())
        self.assertEqual(Student.objects.count(), 0)
        resp = self.client.post(URL, {'file': sheet(line(nid(1), 9)), 'target_school': second.pk})
        self.assertEqual((resp.status_code, resp.json()['created']), (200, 1))
        self.assertEqual(self.student(nid(1)).school_id, second.pk)

    def test_foreign_or_unknown_target_is_rejected_generically(self):
        first, second = self.two_schools()
        answers = set()
        for target in (second.pk, 999999):
            resp = self.client.post(URL, {'file': sheet(line(nid(1), 9)), 'target_school': target})
            self.assertEqual(resp.status_code, 400)
            answers.add(str(resp.json()))
        self.assertEqual(len(answers), 1)
        self.assertEqual(Student.objects.count(), 0)

    def test_a_national_id_of_another_school_is_rejected_unchanged_and_without_revealing_it(self):
        first, second = self.two_schools()
        other = Student.objects.create(first_name='Secret', last_name='Other', national_id=nid(1), grade=8,
                                       phone_number='555', school=second)
        resp = self.post(sheet(line(nid(1), 9, '', first='Changed', last='Name'), line(nid(2), 9)))
        data = resp.json()
        self.assertEqual((resp.status_code, data['created'], data['updated']), (200, 1, 0))
        self.assertEqual(len(data['errors']), 1)
        text = data['errors'][0]
        for leak in ('Secret', 'Other', second.name, second.code, '555', 'school', 'مدرسه'):
            self.assertNotIn(leak, text)
        other.refresh_from_db()
        self.assertEqual((other.first_name, other.school_id, other.grade), ('Secret', second.pk, 8))
        self.assertEqual(self.student(nid(2)).school_id, first.pk)

    def test_a_linked_student_of_another_school_is_rejected_too(self):
        first, second = self.two_schools()
        member = self.member(nid(1), 9, self.klass(second, '9-A'))
        data = self.post(sheet(line(nid(1), 9, '9-A', first='Changed'))).json()
        self.assertEqual((data['created'], data['updated'], len(data['errors'])), (0, 0, 1))
        member.refresh_from_db()
        self.assertEqual((member.first_name, member.school_id), ('M', second.pk))

    def test_a_student_of_the_importers_school_is_updated_and_a_school_less_one_gets_the_school_once(self):
        first, second = self.two_schools()
        mine = Student.objects.create(first_name='Mine', last_name='X', national_id=nid(1), grade=8,
                                      phone_number='1', school=first)
        legacy = self.make_existing(nid(2), grade=8)
        data = self.post(sheet(line(nid(1), 9, first='Renamed'), line(nid(2), 9))).json()
        self.assertEqual((data['created'], data['updated'], data['errors']), (0, 2, []))
        mine.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual((mine.first_name, mine.school_id, legacy.school_id), ('Renamed', first.pk, first.pk))

    def test_the_school_is_never_taken_from_the_file(self):
        first, second = self.two_schools()
        text = HEADER + ',school,school_id\n' + line(nid(1), 9) + f',{second.code},{second.pk}\n'
        self.post(csv_upload(text))
        self.assertEqual(self.student(nid(1)).school_id, first.pk)
