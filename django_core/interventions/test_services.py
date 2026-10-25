"""Plans and follow-ups: transitions, the owner rules, the emotional-text gate (owner and open-referral Counselor only),
append-only follow-ups, school isolation, PROTECT."""
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from interventions.models import InterventionFollowUp, InterventionPlan
from interventions.services import (add_followup, cancel_plan, complete_plan, create_plan, reassign_plan, start_plan)
from risk.loop_testing import LoopBase
from risk.services import LoopError
from schools.models import AuditEvent
from students.access import (may_edit_plan, may_read_plan_text, valid_plan_owner, visible_followups, visible_plan_texts,
                             visible_plans)
from students.models import Referral


class CreateTests(LoopBase):
    def test_admin_lead_counselor_may_create_others_may_not(self):
        self.refer(self.s7, self.counselor)
        for user in (self.admin, self.lead, self.counselor):
            plan = self.plan(by=user)
            self.assertEqual((plan.owner_id, plan.school_id, plan.status), (user.pk, self.a.pk, 'planned'))
        for user in (self.teacher, self.parent, self.student_user, self.admin_b, self.lead8, self.lead_b):
            with self.subTest(user=user.username), self.assertRaises(PermissionDenied):
                self.plan(by=user)

    def test_counselor_needs_the_open_referral(self):
        with self.assertRaises(PermissionDenied):
            self.plan(by=self.counselor)

    def test_from_an_accepted_alert_only(self):
        pending = self.alert()
        with self.assertRaises(LoopError):
            self.plan(alert=pending)
        done = self.accepted()
        self.assertEqual(self.plan(alert=done).alert_id, done.pk)
        other = self.accepted(self.s8)
        with self.assertRaises(LoopError):
            self.plan(alert=other)                       # alert belongs to another student

    def test_a_plan_may_start_without_an_alert(self):
        self.assertIsNone(self.plan().alert_id)

    def test_validation(self):
        for extra in ({'goal': ' '}, {'action_plan': ''}, {'due_date': self.today - timedelta(days=1)},
                      {'intervention_type': 'bogus'}):
            with self.subTest(extra=extra), self.assertRaises(LoopError):
                self.plan(**extra)

    def test_owner_rules(self):
        self.refer(self.s7, self.counselor)
        self.assertEqual(self.plan(by=self.admin, owner=self.lead).owner_id, self.lead.pk)
        with self.assertRaises(PermissionDenied):
            self.plan(by=self.lead, owner=self.counselor)        # only the admin assigns another owner
        with self.assertRaises(LoopError):
            self.plan(by=self.admin, owner=self.lead8)           # does not see the student
        with self.assertRaises(LoopError):
            self.plan(by=self.admin, owner=self.teacher)

    def test_emotional_plan_is_written_by_its_owner_never_by_the_admin(self):
        self.refer(self.s7, self.counselor)
        with self.assertRaises(PermissionDenied):
            self.plan(by=self.admin, kind='emotional', owner=self.counselor)
        with self.assertRaises(LoopError):
            self.plan(by=self.admin, kind='emotional')           # the admin cannot own one either
        self.assertEqual(self.plan(by=self.lead, kind='emotional').owner_id, self.lead.pk)
        self.assertEqual(self.plan(by=self.counselor, kind='emotional').owner_id, self.counselor.pk)

    def test_audit_has_codes_only(self):
        self.plan(goal='private goal')
        event = AuditEvent.objects.get(action='intervention_create')
        self.assertEqual((event.detail, event.object_type), ('academic', 'InterventionPlan'))


class EmotionalTextTests(LoopBase):
    """Owner decision 2026-10-26: text of emotional plans and follow-ups only for the owner and a Counselor with an open
    referral; SchoolAdmin and Grade Lead otherwise see metadata only."""

    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)
        self.lead_plan = self.plan(by=self.lead, kind='emotional')
        start_plan(self.lead, self.lead_plan)
        add_followup(self.lead, self.lead_plan, self.today, 'talked', 'on_track')
        self.counselor_plan = self.plan(by=self.counselor, kind='emotional')
        self.open_plan = self.plan(by=self.lead, kind='academic')

    def texts(self, user):
        return set(visible_plan_texts(user).values_list('pk', flat=True))

    def metas(self, user):
        return set(visible_plans(user).values_list('pk', flat=True))

    def test_school_admin_sees_metadata_but_never_emotional_text(self):
        every = {self.lead_plan.pk, self.counselor_plan.pk, self.open_plan.pk}
        self.assertEqual(self.metas(self.admin), every)
        self.assertEqual(self.texts(self.admin), {self.open_plan.pk})
        self.assertFalse(may_read_plan_text(self.admin, self.lead_plan))
        self.assertEqual(set(visible_followups(self.admin)), set())

    def test_grade_lead_reads_only_own_emotional_plans(self):
        other_lead = self.plan(by=self.admin, owner=self.lead)           # owner is the lead
        self.assertEqual(self.texts(self.lead), {self.lead_plan.pk, self.open_plan.pk, other_lead.pk,
                                                 self.counselor_plan.pk} - {self.counselor_plan.pk})
        self.assertEqual(self.metas(self.lead), {self.lead_plan.pk, self.counselor_plan.pk, self.open_plan.pk, other_lead.pk})
        self.assertFalse(may_read_plan_text(self.lead, self.counselor_plan))

    def test_counselor_with_an_open_referral_reads_every_emotional_plan_of_that_student(self):
        self.assertTrue(may_read_plan_text(self.counselor, self.lead_plan))
        self.assertEqual({f.plan_id for f in visible_followups(self.counselor)}, {self.lead_plan.pk})

    def test_counselor_without_a_referral_sees_nothing(self):
        Referral.objects.update(status='closed')
        self.assertEqual(self.metas(self.counselor), set())
        self.assertEqual(self.texts(self.counselor), set())
        self.assertEqual(set(visible_followups(self.counselor)), set())

    def test_owner_who_loses_sight_of_the_student_loses_the_text(self):
        from schools.models import GradeLeadAssignment
        GradeLeadAssignment.objects.filter(user=self.lead).update(is_active=False)
        self.assertEqual(self.texts(self.lead), set())

    def test_other_schools_and_roles_see_nothing(self):
        for user in (self.admin_b, self.lead_b, self.counselor_b, self.teacher, self.parent, self.student_user, self.lead8):
            with self.subTest(user=user.username):
                self.assertEqual(self.metas(user), set())
                self.assertEqual(self.texts(user), set())
                self.assertEqual(set(visible_followups(user)), set())

    def test_the_admin_can_cancel_and_reassign_but_not_write_follow_ups(self):
        with self.assertRaises(PermissionDenied):
            add_followup(self.admin, self.lead_plan, self.today, 'x', 'on_track')
        with self.assertRaises(PermissionDenied):
            start_plan(self.admin, self.counselor_plan)
        reassign_plan(self.admin, self.lead_plan, self.counselor)
        self.lead_plan.refresh_from_db()
        self.assertEqual(self.lead_plan.owner_id, self.counselor.pk)
        self.assertFalse(may_read_plan_text(self.lead, self.lead_plan))    # the old owner lost the text
        cancel_plan(self.admin, self.counselor_plan)
        self.counselor_plan.refresh_from_db()
        self.assertEqual(self.counselor_plan.status, 'cancelled')

    def test_emotional_reassign_only_to_a_counselor_or_lead_who_sees_the_student(self):
        for new_owner in (self.admin, self.teacher, self.lead8, self.counselor_b):
            with self.subTest(owner=new_owner.username), self.assertRaises(LoopError):
                reassign_plan(self.admin, self.lead_plan, new_owner)
        self.assertFalse(valid_plan_owner(self.admin, self.s7, 'emotional'))


class LifecycleTests(LoopBase):
    def test_happy_path(self):
        plan = self.plan()
        start_plan(self.admin, plan)
        add_followup(self.admin, plan, self.today, 'went well', 'on_track')
        complete_plan(self.admin, plan, 'improved', 'good')
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.outcome), ('completed', 'improved'))
        self.assertIsNotNone(plan.closed_at)
        self.assertEqual(plan.reevaluate_on, plan.closed_at.date() + timedelta(days=30))
        self.assertEqual(list(AuditEvent.objects.filter(action__in=['intervention_status', 'intervention_outcome',
                                                                    'followup_add']).values_list('action', 'detail').order_by('pk')),
                         [('intervention_status', 'active'), ('followup_add', 'on_track'),
                          ('intervention_status', 'completed'), ('intervention_outcome', 'improved')])

    def test_every_illegal_transition_is_refused(self):
        plan = self.plan()
        with self.assertRaises(LoopError):
            complete_plan(self.admin, plan, 'improved')              # planned -> completed
        start_plan(self.admin, plan)
        with self.assertRaises(LoopError):
            start_plan(self.admin, plan)                             # active -> active
        with self.assertRaises(LoopError):
            complete_plan(self.admin, plan, 'bogus')
        with self.assertRaises(LoopError):
            complete_plan(self.admin, plan, '')
        complete_plan(self.admin, plan, 'no_change')
        for call in (lambda: start_plan(self.admin, plan), lambda: cancel_plan(self.admin, plan),
                     lambda: complete_plan(self.admin, plan, 'improved'),
                     lambda: reassign_plan(self.admin, plan, self.lead)):
            with self.assertRaises(LoopError):
                call()
        cancelled = self.plan()
        cancel_plan(self.admin, cancelled)
        with self.assertRaises(LoopError):
            start_plan(self.admin, cancelled)

    def test_followups_only_while_active_and_append_only(self):
        plan = self.plan()
        with self.assertRaises(LoopError):
            add_followup(self.admin, plan, self.today, 'too early', 'on_track')
        start_plan(self.admin, plan)
        for args in ((self.today, '', 'on_track'), (self.today, 'x', 'bogus'), (self.today + timedelta(days=2), 'x', 'on_track')):
            with self.assertRaises(LoopError):
                add_followup(self.admin, plan, *args)
        follow = add_followup(self.admin, plan, self.today, 'ok', 'blocked')
        with self.assertRaises(ValueError):
            follow.progress_note = 'changed'
            follow.save()
        with self.assertRaises(ValueError):
            follow.delete()
        complete_plan(self.admin, plan, 'worse')
        with self.assertRaises(LoopError):
            add_followup(self.admin, plan, self.today, 'late', 'on_track')

    def test_only_the_owner_or_the_admin_acts(self):
        plan = self.plan(by=self.lead)
        other = self.plan(by=self.admin, owner=self.lead)
        start_plan(self.lead, plan)
        # a second Grade Lead of the same grade is not the owner
        from dashboard.test_counselor import make_user
        from schools.models import GradeLeadAssignment
        twin = make_user('twin', 'GradeLead', self.a)
        GradeLeadAssignment.objects.create(user=twin, school=self.a, grade=7, academic_year='1404-1405')
        for call in (lambda: start_plan(twin, other), lambda: cancel_plan(twin, other),
                     lambda: add_followup(twin, plan, self.today, 'x', 'on_track')):
            with self.assertRaises(PermissionDenied):
                call()
        self.assertTrue(may_edit_plan(self.admin, plan))      # admin acts on a non-emotional plan

    def test_other_school_cannot_touch_a_plan(self):
        plan = self.plan()
        start_plan(self.admin, plan)
        for user in (self.admin_b, self.lead_b, self.counselor_b):
            for call in (lambda u=user: start_plan(u, plan), lambda u=user: cancel_plan(u, plan),
                         lambda u=user: reassign_plan(u, plan, u),
                         lambda u=user: add_followup(u, plan, self.today, 'x', 'on_track'),
                         lambda u=user: complete_plan(u, plan, 'improved')):
                with self.assertRaises(PermissionDenied):
                    call()
        plan.refresh_from_db()
        self.assertEqual((plan.status, plan.owner_id), ('active', self.admin.pk))
        self.assertEqual(InterventionFollowUp.objects.count(), 0)

    def test_constraints_and_protect(self):
        plan = self.plan()
        with self.assertRaises(IntegrityError), transaction.atomic():
            InterventionPlan.objects.filter(pk=plan.pk).update(status='completed')     # no outcome
        with self.assertRaises(IntegrityError), transaction.atomic():
            InterventionPlan.objects.filter(pk=plan.pk).update(due_date=self.today - timedelta(days=1))
        with self.assertRaises(ProtectedError):
            self.s7.delete()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.delete(f'/api/students/{self.s7.pk}/').status_code, 409)
