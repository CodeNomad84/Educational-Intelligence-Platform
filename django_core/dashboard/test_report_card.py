"""P5-4 printable report card (decision pack 0028). Synthetic data only."""
from datetime import date

from schools.models import AuditEvent, TeacherAssignment
from students.models import Grade

from .test_counselor import Base, make_user


class ReportCardTests(Base):
    def setUp(self):
        super().setUp()
        self.s7.parent_user = self.parent
        self.s7.save(update_fields=['parent_user'])
        Grade.objects.create(student=self.s7, subject='math', score=18, date=date(2025, 11, 10), exam_type='quiz')
        Grade.objects.create(student=self.s7, subject='math', score=12, date=date(2026, 3, 1), exam_type='quiz')

    def get(self, user, student, term=''):
        self.client.force_login(user)
        return self.client.get(f'/students/{student.pk}/report-card/', {'term': term} if term else {})

    def test_terms_and_access(self):
        first = self.get(self.admin, self.s7, '1')
        self.assertEqual((first.status_code, first.context['overall']), (200, 18))
        self.assertEqual(self.get(self.parent, self.s7, '2').context['overall'], 12)
        self.assertEqual(self.get(self.lead, self.s7, '1').status_code, 200)
        self.assertEqual(self.get(self.parent, self.s8).status_code, 404)        # not the parent's child
        self.assertEqual(self.get(self.admin_b, self.s7).status_code, 404)       # other school
        self.assertEqual(self.get(self.admin, self.s7, 'x').status_code, 404)
        teacher = make_user('t', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=teacher, school_class=self.c7, subject='math')
        for user in (teacher, self.counselor):
            self.assertEqual(self.get(user, self.s7).status_code, 403, user.username)
        self.assertEqual(AuditEvent.objects.filter(action='report_card_view').count(), 3)
