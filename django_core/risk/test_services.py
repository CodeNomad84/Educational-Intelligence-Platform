"""Alerts: who may raise and review, the single winning review, reasons, reopen, constraints, school isolation."""
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction

from risk.loop_testing import LoopBase
from risk.models import Alert, RiskEvent
from risk.services import LoopError, raise_alert, reopen_alert, review_alert
from schools.models import AuditEvent
from students.access import reviewable_alerts, visible_alerts


class RaiseTests(LoopBase):
    def test_roles_that_may_raise(self):
        self.refer(self.s7, self.counselor)
        for user in (self.admin, self.lead, self.counselor, self.teacher):
            with self.subTest(user=user.username):
                alert = self.alert(by=user)
                self.assertEqual((alert.school_id, alert.raised_by_id, alert.status), (self.a.pk, user.pk, 'new'))
                self.assertEqual(alert.risk_event.student_id, self.s7.pk)

    def test_detected_by_follows_the_role(self):
        self.refer(self.s7, self.counselor)
        got = {u.username: self.alert(by=u).risk_event.detected_by for u in (self.admin, self.counselor, self.teacher)}
        self.assertEqual(got, {'admin': 'admin', 'counselor': 'counselor', 'teacher': 'teacher'})

    def test_refused_outside_the_scope(self):
        cases = [(self.teacher, self.s8), (self.teacher, self.sb), (self.lead, self.s8), (self.lead, self.sb),
                 (self.counselor, self.s7),          # no open referral
                 (self.admin, self.sb), (self.admin_b, self.s7), (self.parent, self.s7), (self.student_user, self.s7)]
        for user, student in cases:
            with self.subTest(user=user.username, student=student.first_name):
                with self.assertRaises(PermissionDenied):
                    self.alert(student=student, by=user)
        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(RiskEvent.objects.count(), 0)

    def test_raise_alert_is_the_rule_engine_entry_point(self):
        alert = raise_alert(self.s7, risk_type='attendance', severity='orange', message='m', explanation='why',
                            detected_by='rule_engine')
        self.assertIsNone(alert.raised_by)
        self.assertEqual(alert.risk_event.detected_by, 'rule_engine')

    def test_text_and_choices_are_required(self):
        with self.assertRaises(LoopError):
            self.alert(message='')
        with self.assertRaises(LoopError):
            self.alert(risk_type='bogus')

    def test_audit_has_codes_only(self):
        self.alert(message='secret words')
        event = AuditEvent.objects.get(action='alert_raise')
        self.assertEqual((event.detail, event.object_type, event.school_id), ('academic', 'Alert', self.a.pk))
        self.assertNotIn('secret', ' '.join(map(str, AuditEvent.objects.values_list('detail', 'object_id', flat=False))))


class VisibilityTests(LoopBase):
    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)
        self.x7, self.x8, self.xb = self.alert(), self.alert(self.s8), self.alert(self.sb, by=self.admin_b)
        self.t7 = self.alert(by=self.teacher)

    def ids(self, user):
        return set(visible_alerts(user).values_list('pk', flat=True))

    def test_each_role_sees_its_own_scope(self):
        self.assertEqual(self.ids(self.admin), {self.x7.pk, self.x8.pk, self.t7.pk})
        self.assertEqual(self.ids(self.admin_b), {self.xb.pk})
        self.assertEqual(self.ids(self.lead), {self.x7.pk, self.t7.pk})
        self.assertEqual(self.ids(self.lead8), {self.x8.pk})
        self.assertEqual(self.ids(self.lead_b), {self.xb.pk})
        self.assertEqual(self.ids(self.counselor), {self.x7.pk, self.t7.pk})
        self.assertEqual(self.ids(self.counselor_b), set())
        self.assertEqual(self.ids(self.teacher), {self.t7.pk})        # only what the teacher raised

    def test_nobody_else_sees_anything(self):
        for user in (self.parent, self.student_user):
            self.assertEqual(self.ids(user), set())
        from django.contrib.auth import get_user_model
        root = get_user_model().objects.create_superuser('root', password='x')
        self.assertEqual(self.ids(root), set())

    def test_closing_the_referral_ends_the_counselors_view(self):
        from students.models import Referral as R
        R.objects.filter(student=self.s7).update(status='closed')
        self.assertEqual(self.ids(self.counselor), set())

    def test_teacher_loses_the_alert_when_the_class_assignment_ends(self):
        from schools.models import TeacherAssignment
        TeacherAssignment.objects.filter(teacher=self.teacher).delete()
        self.assertEqual(self.ids(self.teacher), set())

    def test_teacher_cannot_review(self):
        self.assertEqual(set(reviewable_alerts(self.teacher)), set())
        with self.assertRaises(PermissionDenied):
            review_alert(self.teacher, self.t7, Alert.ACCEPTED)

    def test_review_of_another_school_is_refused_and_changes_nothing(self):
        for user in (self.admin_b, self.lead_b, self.counselor_b):
            with self.assertRaises(PermissionDenied):
                review_alert(user, self.x7, Alert.ACCEPTED)
        self.x7.refresh_from_db()
        self.assertEqual((self.x7.status, self.x7.reviewed_by_id), ('new', None))
        with self.assertRaises(PermissionDenied):
            review_alert(self.lead, self.x8, Alert.ACCEPTED)       # other grade, same school


class ReviewTests(LoopBase):
    def test_accept(self):
        alert = self.alert()
        review_alert(self.lead, alert, Alert.ACCEPTED, note=' ok ')
        alert.refresh_from_db()
        self.assertEqual((alert.status, alert.reviewed_by_id, alert.review_note), ('accepted', self.lead.pk, 'ok'))
        self.assertIsNotNone(alert.reviewed_at)
        self.assertEqual(AuditEvent.objects.get(action='alert_review').detail, 'accepted')

    def test_dismiss_needs_a_reason_and_other_needs_a_note(self):
        alert = self.alert()
        for kwargs in ({}, {'reason': 'bogus'}, {'reason': 'other'}, {'reason': 'other', 'note': '  '}):
            with self.subTest(kwargs=kwargs), self.assertRaises(LoopError):
                review_alert(self.admin, alert, Alert.DISMISSED, **kwargs)
        review_alert(self.admin, alert, Alert.DISMISSED, reason='duplicate')
        alert.refresh_from_db()
        self.assertEqual((alert.status, alert.dismiss_reason), ('dismissed', 'duplicate'))
        self.assertEqual(AuditEvent.objects.get(action='alert_review').detail, 'dismissed:duplicate')

    def test_only_one_review_wins(self):
        alert = self.alert()
        review_alert(self.admin, alert, Alert.ACCEPTED)
        with self.assertRaises(LoopError) as raised:
            review_alert(self.lead, alert, Alert.DISMISSED, reason='duplicate')    # a stale object still says "new"
        self.assertEqual(raised.exception.code, 'already_reviewed')
        alert.refresh_from_db()
        self.assertEqual((alert.status, alert.reviewed_by_id), ('accepted', self.admin.pk))

    def test_reopen_is_admin_only_and_only_for_dismissed(self):
        alert = self.alert()
        with self.assertRaises(LoopError):
            reopen_alert(self.admin, alert)                       # still new
        review_alert(self.lead, alert, Alert.DISMISSED, reason='not_relevant')
        for user in (self.lead, self.admin_b, self.teacher):
            with self.assertRaises(PermissionDenied):
                reopen_alert(user, alert)
        reopen_alert(self.admin, alert)
        alert.refresh_from_db()
        self.assertEqual((alert.status, alert.dismiss_reason, alert.reviewed_by_id), ('new', '', None))
        self.assertTrue(AuditEvent.objects.filter(action='alert_reopen').exists())

    def test_database_constraints(self):
        alert = self.alert()
        for fields in ({'status': 'dismissed'}, {'dismiss_reason': 'other'}):
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                Alert.objects.filter(pk=alert.pk).update(**fields)


class ProtectTests(LoopBase):
    def test_a_student_with_an_alert_cannot_be_deleted(self):
        from django.db.models import ProtectedError
        self.alert()
        with self.assertRaises(ProtectedError):
            self.s7.delete()

    def test_api_delete_answers_409_and_keeps_the_student(self):
        self.alert()
        self.client.force_login(self.admin)
        response = self.client.delete(f'/api/students/{self.s7.pk}/')
        self.assertEqual(response.status_code, 409)
        self.s7.refresh_from_db()
