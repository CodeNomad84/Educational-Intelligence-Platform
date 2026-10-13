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

All data is synthetic. No production code is touched by this file.
Traceability: REQ: P2-REQ-18 (class_name is not authoritative), P2-REQ-17 (Admin-only management).
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from schools.models import School, SchoolClass

from .access import ADMIN, PARENT, TEACHER
from .models import Student
from .tests import make_user

URL = '/api/students/import/'
HEADER = 'first_name,last_name,national_id,grade,class_name,phone_number,father_job,mother_job'
PERSIAN_HEADER = 'نام,نام خانوادگی,کد ملی,پایه,کلاس,شماره تماس,شغل پدر,شغل مادر'
EXISTING_KEYS = {'status', 'created', 'updated', 'errors', 'total_rows'}


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
        self.client.force_login(self.admin)

    def post(self, upload):
        return self.client.post(URL, {'file': upload})

    def student(self, national_id):
        return Student.objects.get(national_id=national_id)

    def one_school(self, code='imp-one'):
        """Establish the 'exactly one School' precondition explicitly (the test DB already holds the default
        School created by students.0009, so this replaces it instead of relying on it)."""
        SchoolClass.objects.all().delete()
        School.objects.all().delete()
        school = School.objects.create(code=code, name='Characterization School')
        self.assertEqual(School.objects.count(), 1)
        return school

    def make_existing(self, national_id='1234567890', **extra):
        data = dict(first_name='Old', last_name='Name', national_id=national_id, grade=8, phone_number='111',
                    class_name='legacy text', father_job='old job', mother_job='old job')
        data.update(extra)
        return Student.objects.create(**data)


class ImportPermissionTests(ImportCase):
    """[KEEP] Admin-only. Nothing is created for any other caller."""

    def body(self):
        return csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n')

    def test_admin_and_superuser_may_import(self):
        self.assertEqual(self.post(self.body()).status_code, 200)
        root = make_user('import_root', is_superuser=True)
        self.client.force_login(root)
        self.assertEqual(self.post(csv_upload(f'{HEADER}\nSara,Karimi,1234567891,9,9-A,9120000002,Dr,Nurse\n')
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
        allowed = self.client.post(URL, {'file': self.body()}, **as_bearer(make_user('jwt_admin', ADMIN)))
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
        self.assertEqual(set(data), EXISTING_KEYS)  # [C3c WILL CHANGE]: exact key set today
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
        self.assertEqual(self.student('1234567890').class_name, '9-A')

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

    def test_class_name_text_is_written_stripped_and_nothing_is_linked(self):
        school = self.one_school()
        klass = SchoolClass.objects.create(school=school, title='9-A')
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,  9-A  ,9120000001,Dr,Nurse\n'))
        s = self.student('1234567890')
        self.assertEqual(s.class_name, '9-A')
        self.assertIsNone(s.school_class_id)   # even though an active class '9-A' exists
        self.assertIsNone(s.school_id)         # and exactly one School exists
        self.assertEqual(klass.students.count(), 0)

    def test_unlinked_existing_student_gets_the_file_class_text(self):
        old = self.make_existing('1234567890', class_name='legacy text')
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-B,9120000001,Dr,Nurse\n'))
        old.refresh_from_db()
        self.assertEqual((old.class_name, old.school_class_id), ('9-B', None))

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

    def test_new_students_have_no_school_and_no_class(self):
        self.one_school()
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n'))
        s = self.student('1234567890')
        self.assertEqual((s.school_id, s.school_class_id), (None, None))  # [C3c WILL CHANGE] school (D1)


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

    def test_missing_class_column_blanks_an_unlinked_students_class_name(self):
        """[C3c WILL CHANGE] (not a D6 item) class_name stops being written by import in C3c-2."""
        self.make_existing('1234567890', class_name='legacy text')
        self.post(csv_upload('first_name,last_name,national_id,grade\nAli,Rezai,1234567890,9\n'))
        self.assertEqual(self.student('1234567890').class_name, '')

    def test_blank_optional_cell_is_stored_as_the_text_nan(self):
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,,Nurse\n'))
        self.assertEqual(self.student('1234567890').father_job, 'nan')

    def test_blank_class_cell_is_stored_as_the_text_nan(self):
        """[C3c WILL CHANGE] a blank class cell will no longer write anything (decision D9)."""
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,1234567890,9,,9120000001,Dr,Nurse\n'))
        self.assertEqual(self.student('1234567890').class_name, 'nan')

    def test_leading_zeros_of_numeric_looking_columns_are_lost(self):
        self.post(csv_upload(f'{HEADER}\nAli,Rezai,0123456789,9,9-A,09120000001,Dr,Nurse\n'))
        s = Student.objects.get()
        self.assertEqual((s.national_id, s.phone_number), ('123456789', '9120000001'))

    def test_a_blank_national_id_cell_makes_the_whole_column_float_text(self):
        resp = self.post(csv_upload(
            f'{HEADER}\nAli,Rezai,1234567890,9,9-A,9120000001,Dr,Nurse\n'
            'Bob,Blank,,9,9-A,9120000002,Dr,Nurse\n'))
        self.assertEqual((resp.json()['created'], resp.json()['errors']), (2, []))
        self.assertEqual(sorted(Student.objects.values_list('national_id', flat=True)),
                         ['1234567890.0', 'nan'])
