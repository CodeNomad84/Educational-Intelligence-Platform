"""P6-2 (decision 51): in-app notifications. Rows are made only for users who can already review the alert / see the plan, hold no
text, are shown only while still in scope, and only to their owner. Mutation checks (see the commit message): removing the
reviewable_alerts check in ``notify_alert``, the ``user=user`` filter or the scope join in ``visible_notifications`` fails a test."""
import re
from datetime import timedelta

from django.core.management import call_command
from django.urls import reverse

from risk.loop_testing import LoopBase
from risk.models import Notification
from risk.notifications import notify_due_plans, unread_count, visible_notifications
from students.models import Referral


class AlertNotificationTests(LoopBase):
    def users(self, kind=Notification.ALERT_NEW):
        return set(Notification.objects.filter(kind=kind).values_list('user__username', flat=True))

    def test_only_users_who_can_review_the_alert_get_a_row(self):
        self.alert(self.s7)                                     # grade 7, school A
        got = self.users()
        self.assertIn(self.admin.username, got)
        self.assertIn(self.lead.username, got)                  # grade lead of grade 7
        for other in (self.lead8, self.lead_b, self.teacher, self.parent, self.student_user, self.counselor):
            self.assertNotIn(other.username, got, other.username)   # other grade, other school, teacher, parent, student, no referral
        self.assertNotIn(self.admin_b.username, got)            # another school's admin

    def test_the_access_check_is_the_authority_not_the_candidate_list(self):
        """A candidate that can NOT review the alert (a counselor whose referral is open but for a different student) gets nothing:
        guards ``reviewable_alerts`` in ``notify_alert`` even if ``_candidates`` ever returns too many users."""
        from unittest import mock
        with mock.patch('risk.notifications._candidates', return_value=type(self.admin).objects.filter(
                pk__in=[self.lead8.pk, self.teacher.pk, self.parent.pk, self.lead_b.pk, self.admin_b.pk, self.counselor.pk])):
            self.alert(self.s7)
        self.assertEqual(Notification.objects.count(), 0)

    def test_a_counselor_with_an_open_referral_is_notified_and_loses_it_when_the_referral_closes(self):
        self.refer(self.s7, self.counselor)
        self.alert(self.s7)
        self.assertIn(self.counselor.username, self.users())
        self.assertEqual(unread_count(self.counselor), 1)
        Referral.objects.filter(student=self.s7).update(status='closed')
        self.assertEqual(unread_count(self.counselor), 0)       # scope re-checked at read time: no stale row
        self.assertFalse(visible_notifications(self.counselor).exists())

    def test_rows_hold_no_text_and_the_page_has_no_student_name(self):
        self.alert(self.s7, message='SECRET-MESSAGE-xyz')
        row = Notification.objects.filter(user=self.admin).get()
        self.assertEqual(sorted(f.name for f in Notification._meta.concrete_fields if f.get_internal_type() in ('TextField',)), [])
        self.client.force_login(self.admin)
        page = self.client.get(reverse('dashboard:notifications')).content.decode()
        self.assertIn('هشدار جدیدی برای بررسی دارید', page)
        page = re.sub(r'[A-Za-z0-9]{32,}', '', page)         # random CSRF tokens can contain a short name by chance
        for secret in ('SECRET-MESSAGE-xyz', self.s7.first_name + ' ' + self.s7.last_name, self.s7.national_id):
            self.assertNotIn(secret, page)
        self.assertIsNone(row.read_at)

    def test_each_user_sees_and_marks_only_their_own_rows(self):
        self.alert(self.s7)
        self.client.force_login(self.lead)
        self.assertEqual(unread_count(self.admin), 1)
        self.assertEqual(self.client.post(reverse('dashboard:notifications_read')).status_code, 302)
        self.assertEqual(unread_count(self.lead), 0)
        self.assertEqual(unread_count(self.admin), 1)           # the admin's row is untouched by the lead's click
        self.assertEqual(self.client.get(reverse('dashboard:notifications')).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard:notifications')).status_code, 302)    # login required
        self.client.force_login(self.teacher)
        self.assertNotContains(self.client.get(reverse('dashboard:notifications')), 'هشدار جدیدی برای بررسی دارید.')

    def test_the_bell_counts_unread_in_scope_rows_only(self):
        self.alert(self.s7)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:notifications')).context['NOTIF_COUNT'], 1)
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse('dashboard:student_list')).context['NOTIF_COUNT'], 0)


class DueNotificationTests(LoopBase):
    def test_owner_gets_one_row_per_due_date_and_it_is_idempotent(self):
        plan = self.plan(by=self.lead, due_date=self.today + timedelta(days=3))
        self.assertEqual(notify_due_plans(self.a.pk, self.today), 1)
        self.assertEqual(notify_due_plans(self.a.pk, self.today), 0)
        self.assertEqual(Notification.objects.get(plan=plan).user, self.lead)
        far = self.plan(by=self.lead, due_date=self.today + timedelta(days=60))
        self.assertEqual(notify_due_plans(self.a.pk, self.today), 0)
        self.assertFalse(Notification.objects.filter(plan=far).exists())

    def test_nothing_for_another_school_or_a_closed_plan(self):
        plan = self.plan(by=self.lead, due_date=self.today + timedelta(days=1))
        self.assertEqual(notify_due_plans(self.b.pk, self.today), 0)
        from interventions.models import InterventionPlan
        InterventionPlan.objects.filter(pk=plan.pk).update(status='cancelled')
        self.assertEqual(notify_due_plans(self.a.pk, self.today), 0)

    def test_owner_who_lost_scope_gets_nothing(self):
        self.plan(by=self.lead, due_date=self.today + timedelta(days=1))
        from schools.models import GradeLeadAssignment
        GradeLeadAssignment.objects.filter(user=self.lead).delete()
        self.assertEqual(notify_due_plans(self.a.pk, self.today), 0)

    def test_command_runs_for_one_school(self):
        self.plan(by=self.lead, due_date=self.today + timedelta(days=1))
        from io import StringIO
        out = StringIO()
        call_command('notify_due', '--school', self.a.code, stdout=out)
        self.assertIn('created 1', out.getvalue())


class UniquenessTests(LoopBase):
    def test_a_duplicate_row_is_refused_by_the_database(self):
        """Review L-2 (decision 52): get_or_create alone is not race-safe; the constraints are."""
        from django.db import IntegrityError, transaction
        alert = self.alert(self.s7)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.create(user=self.admin, school_id=alert.school_id, kind=Notification.ALERT_NEW, alert=alert)
