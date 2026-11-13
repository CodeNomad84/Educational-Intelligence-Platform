"""P5-3 behavior log (decision pack 0028; parents see positive entries only, owner 2026-11-01). Synthetic data only."""
from datetime import date, timedelta

from schools.models import AuditEvent, TeacherAssignment
from students.access import visible_behavior_notes
from students.models import BehaviorNote

from .test_counselor import Base, make_user


class BehaviorTests(Base):
    def setUp(self):
        super().setUp()
        self.teacher = make_user('t', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.c7, subject='math')
        self.s7.parent_user = self.parent
        self.s7.save(update_fields=['parent_user'])

    def post(self, user, student, kind='concern', day=None):
        self.client.force_login(user)
        return self.client.post(f'/students/{student.pk}/behavior/new/', {
            'kind': kind, 'category': 'participation', 'note': f'{user.username}-{kind}',
            'occurred_on': (day or date.today()).isoformat()})

    def test_writers_and_scope(self):
        for user in (self.admin, self.lead, self.teacher):
            self.assertEqual(self.post(user, self.s7).status_code, 302, user.username)
        self.assertEqual(BehaviorNote.objects.count(), 3)
        self.assertEqual(BehaviorNote.objects.first().school, self.a)
        self.assertEqual(self.post(self.teacher, self.s8).status_code, 404)         # not in the teacher's classes
        self.assertEqual(self.post(self.admin_b, self.s7).status_code, 404)         # other school
        self.assertEqual(self.post(self.lead, self.s8).status_code, 404)            # other grade
        for user in (self.parent, self.counselor):
            self.assertEqual(self.post(user, self.s7).status_code, 403, user.username)
        self.assertEqual(BehaviorNote.objects.count(), 3)
        self.assertEqual(AuditEvent.objects.filter(action='behavior_note_create').count(), 3)

    def test_future_date_refused(self):
        self.post(self.admin, self.s7, day=date.today() + timedelta(days=2))
        self.assertEqual(BehaviorNote.objects.count(), 0)

    def test_read_scopes(self):
        self.post(self.admin, self.s7, 'positive')
        self.post(self.teacher, self.s7, 'concern')
        self.post(self.lead, self.s7, 'concern')
        notes = lambda user: set(visible_behavior_notes(user).values_list('note', flat=True))   # noqa: E731
        self.assertEqual(len(notes(self.admin)), 3)
        self.assertEqual(len(notes(self.lead)), 3)
        self.assertEqual(notes(self.teacher), {'t-concern'})
        self.assertEqual(notes(self.parent), {'admin-positive'})
        self.assertEqual(notes(self.counselor), set())
        self.assertEqual(notes(self.admin_b), set())

    def test_parent_page_shows_positive_only(self):
        self.post(self.admin, self.s7, 'positive')
        self.post(self.lead, self.s7, 'concern')
        self.client.force_login(self.parent)
        page = self.client.get(f'/students/{self.s7.pk}/360/')
        self.assertContains(page, 'admin-positive')
        self.assertNotContains(page, 'lead-concern')
        self.assertIsNone(page.context['behavior_form'])
