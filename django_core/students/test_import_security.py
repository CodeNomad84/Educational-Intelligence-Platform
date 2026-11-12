"""T8 security tests for ``POST /api/students/import/`` (H-1, M-3, M-5 of the T7 review).

``test_import_students.py`` is a CHARACTERIZATION file ("every later change is a deliberate, reviewed diff"), so it
is not the place for new guarantees: they live here. One class per finding, named after the finding.

All data is synthetic; uploads are built in memory and nothing is written to disk.
Traceability: docs/changes/0039-t8-security-fixes-PROPOSAL.md (H-1, M-3, M-5), decisions D1=a, D4=yes.
"""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from schools.models import AuditEvent, School, SchoolMembership
from students.access import ADMIN
from students.models import Student
from students.tests import make_user

URL = '/api/students/import/'
HEADER = 'first_name,last_name,national_id,grade,class_name,phone_number,father_job,mother_job'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def csv_upload(text, name='students.csv'):
    return SimpleUploadedFile(name, text.encode('utf-8-sig'), content_type='text/csv')


def csv_row(national_id, padding=0):
    """One valid data row; ``padding`` grows an IGNORED trailing column (never a model field)."""
    return f'Ali,Rezai,{national_id},8,7-A,9120000001,Dr,Nurse,{"x" * padding}\n'


class ImportSecurityCase(TestCase):
    def setUp(self):
        self.admin = make_user('import_sec_admin', ADMIN)
        SchoolMembership.objects.create(user=self.admin, school=School.objects.get())
        self.client.force_login(self.admin)

    def post(self, upload):
        return self.client.post(URL, {'file': upload})


class UploadSizeLimitTests(ImportSecurityCase):
    """H-1: an upload above the ceiling is refused BEFORE any parser sees it, and nothing is written."""

    def test_oversized_csv_is_refused_before_the_parser_runs(self):
        from students import views

        padding = views.IMPORT_MAX_BYTES + 1 - len(csv_row('9000000101').encode('utf-8-sig'))
        upload = csv_upload(HEADER + ',padding\n' + csv_row('9000000101', padding))
        self.assertGreater(upload.size, views.IMPORT_MAX_BYTES)
        with mock.patch('students.views.pd.read_csv') as read:
            response = self.post(upload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': views.IMPORT_TOO_LARGE})
        read.assert_not_called()
        self.assertEqual(Student.objects.count(), 0)

    def test_oversized_xlsx_is_refused_before_the_parser_runs(self):
        from students import views

        upload = SimpleUploadedFile('students.xlsx', b'P' * (views.IMPORT_MAX_BYTES + 1), content_type=XLSX)
        with mock.patch('students.views.pd.read_excel') as read:
            response = self.post(upload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': views.IMPORT_TOO_LARGE})
        read.assert_not_called()
        self.assertEqual(Student.objects.count(), 0)

    def test_a_file_exactly_at_the_ceiling_still_reaches_the_parser(self):
        from students import views

        prefix = HEADER + ',padding\nAli,Rezai,9000000102,8,7-A,9120000001,Dr,Nurse,'
        padding = views.IMPORT_MAX_BYTES - len((prefix + '\n').encode('utf-8-sig'))
        upload = csv_upload(prefix + 'x' * padding + '\n')
        self.assertEqual(upload.size, views.IMPORT_MAX_BYTES)
        response = self.post(upload)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()['created'], 1)
        self.assertTrue(Student.objects.filter(national_id='9000000102').exists())

    def test_a_refused_upload_writes_no_student_and_no_audit_event(self):
        from students import views

        upload = SimpleUploadedFile('students.xlsx', b'P' * (views.IMPORT_MAX_BYTES + 1), content_type=XLSX)
        self.assertEqual(self.post(upload).status_code, 400)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)


class BoundedReadTests(TestCase):
    """H-1: the declared size is a hint; the bounded read is the enforcement (a client can lie about ``size``)."""

    def test_a_stream_longer_than_its_declared_size_is_refused(self):
        from students import views

        upload = mock.Mock(size=10)
        upload.read.return_value = b'x' * (views.IMPORT_MAX_BYTES + 1)
        self.assertIsNone(views._bounded_upload(upload))
        upload.read.assert_called_once_with(views.IMPORT_MAX_BYTES + 1)

    def test_a_declared_size_over_the_ceiling_is_refused_without_reading(self):
        from students import views

        upload = mock.Mock(size=views.IMPORT_MAX_BYTES + 1)
        self.assertIsNone(views._bounded_upload(upload))
        upload.read.assert_not_called()

    def test_a_small_upload_is_returned_unchanged(self):
        from students import views

        upload = mock.Mock(size=5)
        upload.read.return_value = b'hello'
        self.assertEqual(views._bounded_upload(upload), b'hello')
