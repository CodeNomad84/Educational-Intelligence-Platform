"""Owner decision 2026-10-26 (earlier correction A3): a Grade Lead MAY read the counselor's notes of students of the own grade.
These tests pin what that access is and is not: read only, enrollment-based grade scope in the own school, tied to an existing
referral, audit-logged (page event plus counselor_note_view). See SECURITY.md (counselor notes) for the decision."""
from django.urls import reverse

from dashboard.test_counselor import Base, make_user
from schools.models import AuditEvent, GradeLeadAssignment
from students.access import visible_counselor_notes
from students.models import CounselorNote, Referral

NOTE = 'COUNSELOR-NOTE-text-xyz'


class LeadReadsCounselorNotesTests(Base):
    def setUp(self):
        super().setUp()
        self.referral = self.refer(self.s7, self.counselor)
        self.note = CounselorNote.objects.create(referral=self.referral, author=self.counselor, text=NOTE)
        self.lead8 = make_user('lead8', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=self.lead8, school=self.a, grade=8, academic_year='1404-1405')
        self.lead_b = make_user('lead-b', 'GradeLead', self.b)
        GradeLeadAssignment.objects.create(user=self.lead_b, school=self.b, grade=7, academic_year='1404-1405')

    def page(self, user, student=None):
        self.client.force_login(user)
        return self.client.get(reverse('dashboard:student_360', args=[(student or self.s7).pk]))

    def test_the_lead_of_the_own_grade_reads_the_note_text(self):
        self.assertContains(self.page(self.lead), NOTE)

    def test_scope_is_the_own_grade_in_the_own_school(self):
        self.assertEqual(set(visible_counselor_notes(self.lead).values_list('pk', flat=True)), {self.note.pk})
        for user in (self.lead8, self.lead_b):                       # another grade, another school
            self.assertEqual(visible_counselor_notes(user).count(), 0, user.username)
            self.assertEqual(self.page(user).status_code, 404, user.username)

    def test_scope_follows_the_enrollment_not_the_note(self):
        GradeLeadAssignment.objects.filter(user=self.lead).update(grade=9)      # the lead no longer covers grade 7
        self.assertEqual(visible_counselor_notes(self.lead).count(), 0)
        self.assertEqual(self.page(self.lead).status_code, 404)
        GradeLeadAssignment.objects.filter(user=self.lead).update(grade=7, is_active=False)
        self.assertEqual(visible_counselor_notes(self.lead).count(), 0)

    def test_it_is_read_only(self):
        self.client.force_login(self.lead)
        case = reverse('dashboard:counselor_case', args=[self.referral.pk])
        self.assertEqual(self.client.get(case).status_code, 403)                                  # the case page is counselor-only
        self.assertEqual(self.client.post(case, {'text': 'lead writes'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('dashboard:counselor_close', args=[self.referral.pk])).status_code, 403)
        self.assertEqual(CounselorNote.objects.count(), 1)
        self.assertEqual(Referral.objects.get(pk=self.referral.pk).status, 'open')

    def test_there_is_no_other_route_that_writes_a_note(self):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        writers = []
        for path in list((root / 'dashboard').glob('*.py')) + list((root / 'students').glob('*.py')):
            if path.name.startswith('test') or path.name in ('models.py',):
                continue
            if re.search(r'CounselorNote\.objects\.create|CounselorNote\(', path.read_text(encoding='utf-8')):
                writers.append(path.name)
        self.assertEqual(writers, ['counselor_views.py'])                                         # the counselor-only case view

    def test_notes_exist_only_through_a_referral(self):
        other = self.s8
        self.assertFalse(Referral.objects.filter(student=other).exists())
        self.assertEqual(CounselorNote.objects.filter(referral__student=other).count(), 0)      # no referral, no note, nothing to read
        page = self.page(self.lead8, other)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, NOTE)
        self.assertFalse(page.context['counselor_notes'])

    def test_a_closed_referral_keeps_its_notes_readable_for_the_lead_only(self):
        """Owner decision 2026-10-28: the Grade Lead is unchanged; the SchoolAdmin gets metadata only after close; the Counselor none."""
        Referral.objects.filter(pk=self.referral.pk).update(status='closed')
        self.assertContains(self.page(self.lead), NOTE)                                  # unchanged (owner decision 2026-10-26)
        self.assertEqual(visible_counselor_notes(self.counselor).count(), 0)             # the counselor loses it on close
        self.assertEqual(visible_counselor_notes(self.admin).count(), 0)                 # no text path for the admin any more
        page = self.page(self.admin)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, NOTE)
        self.assertContains(page, 'متن این یادداشت‌ها برای مدیر نمایش داده نمی‌شود')       # existence and date only
        self.assertEqual(len(page.context['closed_note_dates']), 1)
        self.assertFalse(page.context['counselor_notes'])

    def test_the_admin_reads_the_text_while_the_referral_is_open(self):
        self.assertContains(self.page(self.admin), NOTE)
        self.assertEqual(self.page(self.admin).context['closed_note_dates'], [])

    def test_no_note_view_event_for_the_admin_when_only_metadata_is_shown(self):
        Referral.objects.filter(pk=self.referral.pk).update(status='closed')
        AuditEvent.objects.all().delete()
        self.page(self.admin)
        self.assertFalse(AuditEvent.objects.filter(action='counselor_note_view').exists())
        self.page(self.lead)
        self.assertEqual(AuditEvent.objects.get(action='counselor_note_view').username, 'lead')

    def test_the_metadata_queryset_is_empty_for_every_other_role(self):
        from students.access import counselor_note_metadata
        Referral.objects.filter(pk=self.referral.pk).update(status='closed')
        self.assertEqual(counselor_note_metadata(self.admin).count(), 1)
        for user in (self.lead, self.counselor, self.admin_b, self.parent, make_user('t', 'Teacher', self.a)):
            self.assertEqual(counselor_note_metadata(user).count(), 0, user.username)

    def test_reads_are_audit_logged_at_page_level_without_content(self):
        AuditEvent.objects.all().delete()
        self.page(self.lead)
        rows = list(AuditEvent.objects.order_by('pk').values_list('username', 'action', 'object_type', 'detail'))
        self.assertEqual(rows, [('lead', 'view_student_360', 'Student', ''), ('lead', 'counselor_note_view', 'Student', 'n1')])
        every = ' '.join(f'{a} {b} {c} {d} {e}' for a, b, c, d, e in AuditEvent.objects.values_list(
            'username', 'action', 'object_type', 'object_id', 'detail'))
        self.assertNotIn('NOTE-text', every)

    def test_note_view_event_for_every_role_that_reads_text(self):
        for user in (self.lead, self.admin):
            AuditEvent.objects.all().delete()
            self.page(user)
            event = AuditEvent.objects.get(action='counselor_note_view')
            self.assertEqual((event.username, event.detail, event.school_id), (user.username, 'n1', self.a.pk), user.username)
        AuditEvent.objects.all().delete()
        self.client.force_login(self.counselor)
        self.assertContains(self.client.get(reverse('dashboard:counselor_case', args=[self.referral.pk])), NOTE)
        event = AuditEvent.objects.get(action='counselor_note_view')
        self.assertEqual((event.username, event.object_type, event.detail), ('counselor', 'Referral', 'n1'))

    def test_no_note_view_event_when_no_note_text_is_displayed(self):
        AuditEvent.objects.all().delete()
        self.page(self.lead8, self.s8)                                  # no referral, no note: page shown, no text
        self.assertFalse(AuditEvent.objects.filter(action='counselor_note_view').exists())
        self.assertTrue(AuditEvent.objects.filter(action='view_student_360').exists())
        self.page(self.lead_b)                                          # 404: nothing shown
        self.assertFalse(AuditEvent.objects.filter(action='counselor_note_view').exists())

    def test_parent_teacher_and_student_never_read_notes(self):
        teacher = make_user('t', 'Teacher', self.a)
        for user in (self.parent, teacher):
            self.assertEqual(visible_counselor_notes(user).count(), 0, user.username)
