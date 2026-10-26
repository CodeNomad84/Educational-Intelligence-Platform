"""F3 (owner decision 2026-10-26): the message and the review note of an `emotional` or `family` alert are readable only by the
raiser and a Counselor with an OPEN referral; SchoolAdmin and Grade Lead see metadata only and can still review."""
from django.urls import reverse

from risk.loop_testing import LoopBase
from risk.models import Alert
from risk.services import review_alert
from schools.models import AuditEvent
from students.access import apply_alert_text_policy, visible_alert_notes, visible_alert_texts
from students.models import Referral

NOTE = 'REVIEW-NOTE-xyz'


class AlertTextTests(LoopBase):
    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)
        mk = lambda kind, by, msg: self.alert(by=by, risk_type=kind, message=msg)   # noqa: E731
        self.plain = mk('academic', self.teacher, 'MSG-academic')
        self.emo_c = mk('emotional', self.counselor, 'MSG-emotional-by-counselor')
        self.fam_t = mk('family', self.teacher, 'MSG-family-by-teacher')
        self.emo_l = mk('emotional', self.lead, 'MSG-emotional-by-lead')
        for alert in (self.plain, self.emo_c, self.fam_t, self.emo_l):
            review_alert(self.lead, alert, Alert.DISMISSED, reason='other', note=NOTE)   # `other` works without reading the text

    def texts(self, user):
        return set(visible_alert_texts(user).values_list('pk', flat=True))

    def notes(self, user):
        return set(visible_alert_notes(user).values_list('pk', flat=True))

    def test_message_matrix(self):
        p, ec, ft, el = self.plain.pk, self.emo_c.pk, self.fam_t.pk, self.emo_l.pk
        expected = {
            self.admin: {p},                  # metadata only for the sensitive ones
            self.lead: {p, el},               # plus the one the lead raised
            self.counselor: {p, ec, ft, el},  # open referral: every sensitive alert of the student
            self.teacher: {p, ft},            # only what the teacher raised, sensitive or not
            self.admin_b: set(), self.lead_b: set(), self.counselor_b: set(), self.lead8: set(),
            self.parent: set(), self.student_user: set(),
        }
        for user, want in expected.items():
            self.assertEqual(self.texts(user), want, user.username)

    def test_note_matrix(self):
        p, ec, ft, el = self.plain.pk, self.emo_c.pk, self.fam_t.pk, self.emo_l.pk
        expected = {
            self.admin: {p}, self.lead: {p, el}, self.counselor: {p, ec, ft, el},
            self.teacher: set(),              # a teacher never reads a reviewer's note
            self.admin_b: set(), self.lead_b: set(), self.counselor_b: set(), self.parent: set(),
        }
        for user, want in expected.items():
            self.assertEqual(self.notes(user), want, user.username)

    def rendered(self, user):
        self.client.force_login(user)
        return self.client.get(reverse('dashboard:alert_list') + '?status=dismissed').content.decode()

    def test_rendered_pages_follow_the_matrix(self):
        for user, shown, hidden in (
                (self.admin, ['MSG-academic'], ['MSG-emotional-by-counselor', 'MSG-family-by-teacher', 'MSG-emotional-by-lead']),
                (self.lead, ['MSG-academic', 'MSG-emotional-by-lead'], ['MSG-emotional-by-counselor', 'MSG-family-by-teacher']),
                (self.counselor, ['MSG-academic', 'MSG-emotional-by-counselor', 'MSG-family-by-teacher', 'MSG-emotional-by-lead'], []),
                (self.teacher, ['MSG-academic', 'MSG-family-by-teacher'], ['MSG-emotional-by-counselor', 'MSG-emotional-by-lead'])):
            html = self.rendered(user)
            for text in shown:
                self.assertIn(text, html, (user.username, text))
            for text in hidden:
                self.assertNotIn(text, html, (user.username, text))
        self.assertNotIn(NOTE, self.rendered(self.teacher))
        self.assertIn(NOTE, self.rendered(self.counselor))
        # the metadata is still there for the admin: type, status, reason code
        html = self.rendered(self.admin)
        self.assertIn('ردشده', html)
        self.assertIn('سایر', html)
        self.assertEqual(html.count('متن برای شما نمایش داده نمی‌شود'), 3)

    def test_the_policy_blanks_the_objects_not_just_the_template(self):
        alerts = apply_alert_text_policy(self.admin, Alert.objects.filter(pk__in=[self.emo_c.pk, self.plain.pk]).order_by('pk'))
        by_pk = {a.pk: a for a in alerts}
        self.assertEqual((by_pk[self.emo_c.pk].message, by_pk[self.emo_c.pk].review_note, by_pk[self.emo_c.pk].text_hidden), ('', '', True))
        self.assertEqual(by_pk[self.plain.pk].message, 'MSG-academic')

    def test_the_reviewer_can_still_accept_dismiss_and_plan_on_metadata_alone(self):
        fresh = self.alert(by=self.counselor, risk_type='emotional', message='MSG-fresh-emotional')
        other = self.alert(by=self.counselor, risk_type='family', message='MSG-fresh-family')
        for reviewer in (self.admin, self.lead):
            self.client.force_login(reviewer)
            alert = self.alert(by=self.counselor, risk_type='emotional', message='MSG-x')
            self.assertEqual(self.client.post(reverse('dashboard:alert_review', args=[alert.pk]), {'decision': 'accept'}).status_code, 302)
            self.assertEqual(Alert.objects.get(pk=alert.pk).status, 'accepted')
            page = self.client.get(reverse('dashboard:plan_new', args=[self.s7.pk]) + f'?alert={alert.pk}')
            self.assertEqual(page.status_code, 200)
            self.assertNotIn('MSG-x', page.content.decode())
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:alert_review', args=[fresh.pk]), {'decision': 'dismiss', 'reason': 'other', 'note': NOTE})
        self.assertEqual(Alert.objects.get(pk=fresh.pk).status, 'dismissed')       # `other` with a note works unread
        self.client.post(reverse('dashboard:alert_review', args=[other.pk]), {'decision': 'dismiss', 'reason': 'other'})
        self.assertEqual(Alert.objects.get(pk=other.pk).status, 'new')              # the note rule still applies
        self.client.post(reverse('dashboard:alert_reopen', args=[fresh.pk]))
        self.assertEqual(Alert.objects.get(pk=fresh.pk).status, 'new')

    def test_counselor_loses_the_text_when_the_referral_closes(self):
        self.assertIn(self.emo_c.pk, self.texts(self.counselor))
        Referral.objects.update(status='closed')
        self.assertEqual(self.texts(self.counselor), set())
        self.assertEqual(self.notes(self.counselor), set())
        self.assertNotIn('MSG-emotional-by-counselor', self.rendered(self.counselor))

    def test_two_school_isolation(self):
        self.refer(self.sb, self.counselor_b, by=self.admin_b)
        alert = self.alert(self.sb, by=self.admin_b, risk_type='emotional', message='MSG-school-b')
        self.assertEqual(self.texts(self.counselor_b), {alert.pk})
        for user in (self.counselor, self.admin, self.lead, self.teacher):
            self.assertNotIn(alert.pk, self.texts(user))
            self.assertNotIn('MSG-school-b', self.rendered(user))
        self.assertNotIn('MSG-school-b', self.rendered(self.admin_b))      # metadata only for the other school's admin too

    def test_reads_of_sensitive_text_are_audited_with_codes_only(self):
        AuditEvent.objects.all().delete()
        self.rendered(self.admin)
        self.assertFalse(AuditEvent.objects.filter(action='alert_text_view').exists())    # nothing readable, nothing logged
        self.rendered(self.counselor)
        rows = sorted(AuditEvent.objects.filter(action='alert_text_view').values_list('username', 'detail', 'object_type'))
        self.assertEqual(rows, [('counselor', 'emotional', 'Alert'), ('counselor', 'emotional', 'Alert'), ('counselor', 'family', 'Alert')])
        every = ' '.join(f'{a} {b} {c}' for a, b, c in AuditEvent.objects.values_list('action', 'detail', 'object_id'))
        self.assertNotIn('MSG', every)
        self.assertNotIn(NOTE, every)
