"""Independent review 0027 finding 3 (owner decision 2026-10-28): the message for a national id that cannot be registered is
IDENTICAL whether the id belongs to a student of the same school or of another school, in the form, the API and the import report,
and it names no school. (The refusal itself remains: national_id is globally unique until S7.)"""
from django.urls import reverse

from dashboard.test_counselor import Base
from students.models import Student
from students.student_school import NATIONAL_ID_REFUSED

JSON = 'application/json'


class NationalIdMessageTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def payload(self, national_id):
        return {'first_name': 'N', 'last_name': 'New', 'national_id': national_id, 'grade': 7, 'phone_number': '1',
                'school_class': self.c7.pk}

    def api_error(self, national_id):
        response = self.client.post('/api/students/', self.payload(national_id), content_type=JSON)
        self.assertEqual(response.status_code, 400, response.content)
        return response.json()['national_id']

    def form_error(self, national_id):
        data = {**self.payload(national_id), 'target_school': ''}
        response = self.client.post(reverse('dashboard:student_add'), data)
        self.assertEqual(response.status_code, 200)
        return list(response.context['form'].errors['national_id'])

    def test_api_message_is_identical_for_same_school_and_other_school_ids(self):
        same, other = self.api_error(self.s7.national_id), self.api_error(self.sb.national_id)
        self.assertEqual(same, other)
        self.assertEqual(same, [NATIONAL_ID_REFUSED])

    def test_form_message_is_identical_for_same_school_and_other_school_ids(self):
        same, other = self.form_error(self.s7.national_id), self.form_error(self.sb.national_id)
        self.assertEqual(same, other)
        self.assertEqual(same, [NATIONAL_ID_REFUSED])

    def test_the_message_names_no_school_and_creates_nothing(self):
        before = Student.objects.count()
        for message in self.api_error(self.sb.national_id) + self.form_error(self.sb.national_id):
            self.assertNotIn(self.b.name, message)
            self.assertNotIn('already', message.lower())
        self.assertEqual(Student.objects.count(), before)

    def test_a_new_id_still_works_and_editing_a_student_with_its_own_id_still_works(self):
        ok = self.client.post('/api/students/', self.payload('9999999999'), content_type=JSON)
        self.assertEqual(ok.status_code, 201, ok.content)
        edit = self.client.patch(f'/api/students/{self.s7.pk}/', {'national_id': self.s7.national_id, 'phone_number': '7'},
                                 content_type=JSON)
        self.assertEqual(edit.status_code, 200, edit.content)
        clash = self.client.patch(f'/api/students/{self.s7.pk}/', {'national_id': self.sb.national_id}, content_type=JSON)
        self.assertEqual((clash.status_code, clash.json()['national_id']), (400, [NATIONAL_ID_REFUSED]))

    def test_the_import_report_uses_the_same_text(self):
        from students.views import ImportSchoolConflict
        self.assertEqual(ImportSchoolConflict.MESSAGE, NATIONAL_ID_REFUSED)
