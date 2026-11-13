"""Independent review 0027 finding 1 (owner decision 2026-10-28): the SchoolAdmin has no DIRECT read of emotional/family alert text or
emotional plan text, but can reach it through a Counselor account (create or reset it) plus a referral. This is an ACCEPTED
insider-trust risk compensated by audit. These tests (1) demonstrate the path so the SECURITY.md wording rests on evidence,
(2) pin that every step is audit-logged with ids and codes only, and (3) pin that a Grade Lead can never reset a Counselor or a SchoolAdmin."""
from django.contrib.auth import get_user_model
from django.urls import reverse

from dashboard.test_counselor import make_user
from interventions.services import start_plan
from risk.loop_testing import LoopBase
from risk.models import Alert
from risk.services import review_alert
from schools.models import AuditEvent
from students.access import visible_alert_texts, visible_plan_texts
from students.models import Referral

User = get_user_model()
EMO = 'EMOTIONAL-MSG-abc'
GOAL = 'EMOTIONAL-GOAL-abc'
PW = 'Chosen-by-admin-1'


class AdminToCounselorPathTests(LoopBase):
    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)
        self.alert_emo = self.alert(by=self.counselor, risk_type='emotional', message=EMO)
        review_alert(self.lead, self.alert_emo, Alert.DISMISSED, reason='other', note='n')
        self.plan_emo = self.plan(by=self.lead, kind='emotional', goal=GOAL)
        start_plan(self.lead, self.plan_emo)
        Referral.objects.filter(student=self.s7).update(status='closed')      # the original counselor's case is closed

    def get(self, user, name, *args, query=''):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args) + query).content.decode()

    def test_the_admin_has_no_direct_read(self):
        self.assertNotIn(self.alert_emo.pk, visible_alert_texts(self.admin).values_list('pk', flat=True))
        self.assertNotIn(self.plan_emo.pk, visible_plan_texts(self.admin).values_list('pk', flat=True))
        self.assertNotIn(EMO, self.get(self.admin, 'dashboard:alert_list', query='?status=dismissed'))
        self.assertNotIn(GOAL, self.get(self.admin, 'dashboard:plan_detail', self.plan_emo.pk))

    def test_path_a_admin_creates_a_counselor_refers_and_reads_the_text_as_that_counselor(self):
        AuditEvent.objects.all().delete()
        self.client.force_login(self.admin)
        response = self.client.post(reverse('dashboard:school_staff', args=['counselors']), {
            'username': 'c-new', 'first_name': 'C', 'last_name': 'New', 'password1': PW, 'password2': PW})
        self.assertEqual(response.status_code, 302)
        counselor = User.objects.get(username='c-new')
        self.client.post(reverse('dashboard:student_refer', args=[self.s7.pk]),
                         {'counselor': counselor.pk, 'reason': 'Needs support'})
        self.assertTrue(Referral.objects.filter(student=self.s7, counselor=counselor, status='open').exists())
        self.assertIn(EMO, self.get(counselor, 'dashboard:alert_list', query='?status=dismissed'))      # the path works
        self.assertIn(GOAL, self.get(counselor, 'dashboard:plan_detail', self.plan_emo.pk))
        # ... and every step left an audit row (ids and codes only)
        events = {(e.username, e.action) for e in AuditEvent.objects.all()}
        for want in (('admin', 'staff_account_create'), ('admin', 'referral_create'), ('c-new', 'alert_text_view'),
                     ('c-new', 'intervention_view')):
            self.assertIn(want, events)
        every = ' '.join(f'{e.detail} {e.object_type} {e.object_id}' for e in AuditEvent.objects.all())
        self.assertNotIn(EMO, every)
        self.assertNotIn(GOAL, every)
        self.assertEqual(AuditEvent.objects.get(action='staff_account_create').detail, 'counselors')

    def test_path_b_admin_resets_an_existing_counselor_and_uses_it(self):
        other = make_user('c-other', 'Counselor', self.a)
        self.refer(self.s7, other)
        AuditEvent.objects.all().delete()
        self.client.force_login(self.admin)
        response = self.client.post(reverse('dashboard:school_reset', args=[other.pk]))
        self.assertEqual(response.status_code, 200)
        reset = AuditEvent.objects.get(action='password_reset')
        self.assertEqual((reset.username, reset.detail, reset.object_id, reset.school_id), ('admin', 'admin', str(other.pk), self.a.pk))
        from schools.models import AccountProfile
        self.assertTrue(AccountProfile.objects.get(user=other).must_change_password)      # the admin knows the generated password ...
        AccountProfile.objects.filter(user=other).update(must_change_password=False)      # ... and sets a new one at the forced change page
        other.refresh_from_db()      # the stored hash changed: a stale instance would log the session out
        self.assertIn(EMO, self.get(other, 'dashboard:alert_list', query='?status=dismissed'))
        self.assertNotIn('Chosen', str(list(AuditEvent.objects.values_list('detail', flat=True))))

    def test_role_grant_through_the_staff_roles_page_is_audited(self):
        person = make_user('plain-staff', 'Teacher', self.a)
        AuditEvent.objects.all().delete()
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:school_staff_roles_save', args=[person.pk]), {'teacher': 'on', 'counselor': 'on'})
        event = AuditEvent.objects.filter(action='staff_roles_change').first()
        self.assertIsNotNone(event)
        self.assertEqual((event.username, event.object_id), ('admin', str(person.pk)))
        self.assertIn('C', event.detail)

    def test_a_grade_lead_can_never_reset_a_counselor_or_a_school_admin(self):
        from schools.models import School
        School.objects.filter(pk=self.a.pk).update(grade_leads_may_reset_passwords=True)
        from students.models import Student
        for index, target in enumerate((self.counselor, self.admin, make_user('c-x', 'Counselor', self.a))):
            # link the target to a grade-7 student so it is "in scope" by every other measure
            kid = Student.objects.create(first_name='K', last_name='x', national_id=f'91000000{index:02d}', grade=7, phone_number='',
                                         school=self.a, school_class=self.c7)
            from students.enrollment_sync import ensure_current_enrollment
            ensure_current_enrollment(kid, source='import')
            Student.objects.filter(pk=kid.pk).update(parent_user=target)
            self.client.force_login(self.lead)
            response = self.client.post(reverse('dashboard:grade_reset', args=[target.pk]))
            self.assertIn(response.status_code, (403, 404), target.username)
            target.refresh_from_db()
            self.assertTrue(target.check_password('x'), target.username)          # password unchanged
        self.assertFalse(AuditEvent.objects.filter(action='password_reset').exists())
