"""0025 commit 2: every legal and illegal lifecycle move, edit resets, hash binding, approver rules, immutability, audit."""
from django.core.exceptions import PermissionDenied, ValidationError

from dashboard.test_counselor import make_user
from risk import lifecycle, rules
from risk.models import Rule, RuleSettings
from risk.rules_testing import TODAY, RulesBase
from schools.models import AuditEvent, SchoolMembership


class LifecycleTests(RulesBase):
    def fields(self, rule):
        return dict(title=rule.title, risk_type=rule.risk_type, severity=rule.severity, connective=rule.connective,
                    clauses=[dict(c) for c in rule.clauses], cooldown_days=rule.cooldown_days)

    def refused(self, func, *args, **kw):
        with self.assertRaises(ValidationError):
            func(*args, **kw)

    def test_happy_path_and_previous_version_is_archived(self):
        v1 = self.live()
        self.assertEqual((v1.status, v1.approved_by_id), ('active', self.admin.pk))
        v2 = lifecycle.clone(v1, self.admin)
        self.assertEqual((v2.version, v2.status), (2, 'draft'))
        lifecycle.simulate(v2, self.admin, as_of=TODAY)
        lifecycle.submit(v2, self.admin)
        lifecycle.approve(v2, self.admin)
        self.assertEqual([Rule.objects.get(pk=v1.pk).status, Rule.objects.get(pk=v2.pk).status], ['archived', 'active'])

    def test_illegal_moves_are_refused(self):
        rule = self.starter(code='repeated_absence')
        self.refused(lifecycle.submit, rule, self.admin)                 # draft cannot be submitted
        self.refused(lifecycle.approve, rule, self.admin)
        self.refused(lifecycle.pause, rule, self.admin)
        self.refused(lifecycle.resume, rule, self.admin)
        self.refused(lifecycle.reopen, rule, self.admin)
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        self.refused(lifecycle.approve, rule, self.admin)                # simulated is not yet pending
        lifecycle.submit(rule, self.admin)
        self.refused(lifecycle.submit, rule, self.admin)
        live = lifecycle.approve(rule, self.admin)
        self.refused(lifecycle.approve, live, self.admin)
        self.refused(lifecycle.archive, live, self.admin)                # active must be paused first
        self.refused(lifecycle.simulate, live, self.admin)
        self.refused(lifecycle.edit, live, self.admin, **self.fields(live))
        paused = lifecycle.pause(live, self.admin)
        self.refused(lifecycle.pause, paused, self.admin)
        self.assertEqual(lifecycle.resume(paused, self.admin).status, 'active')
        lifecycle.pause(live, self.admin)
        archived = lifecycle.archive(live, self.admin)
        self.refused(lifecycle.archive, archived, self.admin)
        self.refused(lifecycle.resume, archived, self.admin)

    def test_editing_after_simulation_resets_to_draft_and_clears_the_hash(self):
        rule = self.starter(code='repeated_absence')
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        fields = self.fields(rule)
        fields['clauses'][0]['threshold'] = 4
        edited = lifecycle.edit(rule, self.admin, **fields)
        self.assertEqual((edited.status, edited.params_hash), ('draft', ''))
        self.refused(lifecycle.submit, edited, self.admin)

    def test_activation_requires_a_hash_matching_the_current_parameters(self):
        rule = self.starter(code='repeated_absence')
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        Rule.objects.filter(pk=rule.pk).update(clauses=[{**rule.clauses[0], 'threshold': 9}])     # changed behind the lifecycle's back
        self.refused(lifecycle.approve, rule, self.admin)
        self.assertEqual(Rule.objects.get(pk=rule.pk).status, 'pending_approval')

    def test_active_paused_and_archived_parameters_cannot_be_saved(self):
        live = self.live()
        for status in ('active', 'paused', 'archived'):
            Rule.objects.filter(pk=live.pk).update(status=status)
            fresh = Rule.objects.get(pk=live.pk)
            for name, value in (('clauses', []), ('cooldown_days', 1), ('risk_type', 'academic'), ('severity', 'orange')):
                setattr(fresh, name, value)
                with self.assertRaises(ValidationError, msg=f'{status}/{name}'):
                    fresh.save()
                fresh = Rule.objects.get(pk=live.pk)
        fresh.status = 'paused'
        fresh.save()                                                     # a status change alone is fine

    def test_single_approver_by_default_second_approver_when_switched_on(self):
        rule = self.starter(code='repeated_absence')
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        other = make_user('admin2', 'SchoolAdmin')
        SchoolMembership.objects.create(user=other, school=self.a)
        RuleSettings.objects.filter(school=self.a).update(require_second_approver=True)
        self.refused(lifecycle.approve, rule, self.admin)                # author may not approve with the switch on
        self.assertEqual(lifecycle.approve(rule, other).approved_by_id, other.pk)
        RuleSettings.objects.filter(school=self.a).update(require_second_approver=False)
        solo = self.live(code='attendance_shift')
        self.assertEqual(solo.approved_by_id, self.admin.pk)

    def test_only_a_schooladmin_of_the_rules_school_may_move_a_rule(self):
        rule = self.starter(code='repeated_absence')
        for user in (self.admin_b, self.lead, self.teacher, self.counselor, self.parent):
            with self.subTest(user=user.username):
                for func in (lifecycle.simulate, lifecycle.submit, lifecycle.approve, lifecycle.pause, lifecycle.archive,
                             lifecycle.clone, lifecycle.reopen):
                    with self.assertRaises(PermissionDenied):
                        func(rule, user)
                with self.assertRaises(PermissionDenied):
                    lifecycle.edit(rule, user, **self.fields(rule))
        with self.assertRaises(PermissionDenied):
            self.starter(code='low_average', by=self.admin_b)             # creating in a school one does not administer

    def test_a_deactivated_admin_cannot_approve(self):
        rule = self.starter(code='repeated_absence')
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(PermissionDenied):
            lifecycle.approve(rule, self.admin)

    def test_scale_removed_after_drafting_blocks_activation(self):
        rule = self.starter(code='low_average')
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        RuleSettings.objects.filter(school=self.a).update(grade_scale_max=None)
        self.refused(lifecycle.approve, rule, self.admin)

    def test_one_unfinished_version_per_code_and_code_reuse_refused(self):
        live = self.live()
        lifecycle.clone(live, self.admin)
        self.refused(lifecycle.clone, live, self.admin)
        self.refused(self.starter, code='repeated_absence')

    def test_audit_has_codes_and_counts_only(self):
        AuditEvent.objects.all().delete()
        self.live()
        actions = set(AuditEvent.objects.values_list('action', flat=True))
        self.assertTrue({'rule_create', 'rule_simulate', 'rule_status'} <= actions)
        every = ' '.join(AuditEvent.objects.values_list('detail', flat=True))
        self.assertNotIn('Kid', every)
        self.assertTrue(all(len(d) <= 40 for d in AuditEvent.objects.values_list('detail', flat=True)))


class SecondApproverLastEditorTests(RulesBase):
    """Independent review 0027 finding 4: with the switch on, the approver differs from the creator AND the last editor."""
    def setUp(self):
        super().setUp()
        self.b_admin = make_user('admin-b2', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.b_admin, school=self.a)
        self.c_admin = make_user('admin-c2', 'SchoolAdmin')
        SchoolMembership.objects.create(user=self.c_admin, school=self.a)
        RuleSettings.objects.filter(school=self.a).update(require_second_approver=True)

    def pending_after_edit_by_b(self):
        rule = self.starter(code='repeated_absence')                        # created by self.admin (A)
        fields = dict(title=rule.title, risk_type=rule.risk_type, severity=rule.severity, connective=rule.connective,
                      clauses=[dict(c) for c in rule.clauses], cooldown_days=rule.cooldown_days)
        fields['clauses'][0]['threshold'] = 4
        rule = lifecycle.edit(rule, self.b_admin, **fields)                 # B rewrites A's draft
        lifecycle.simulate(rule, self.b_admin, as_of=TODAY)
        lifecycle.submit(rule, self.b_admin)
        return Rule.objects.get(pk=rule.pk)

    def test_the_last_editor_cannot_approve_what_they_wrote(self):
        rule = self.pending_after_edit_by_b()
        self.assertEqual((rule.created_by_id, rule.last_edited_by_id), (self.admin.pk, self.b_admin.pk))
        for actor in (self.b_admin, self.admin):                            # the editor and the creator are both refused
            with self.assertRaises(ValidationError):
                lifecycle.approve(rule, actor)
        self.assertEqual(Rule.objects.get(pk=rule.pk).status, 'pending_approval')
        self.assertEqual(lifecycle.approve(rule, self.c_admin).approved_by_id, self.c_admin.pk)

    def test_switch_off_keeps_the_single_approver(self):
        RuleSettings.objects.filter(school=self.a).update(require_second_approver=False)
        rule = self.pending_after_edit_by_b()
        self.assertEqual(lifecycle.approve(rule, self.b_admin).status, 'active')

    def test_a_clone_is_authored_by_the_cloner(self):
        RuleSettings.objects.filter(school=self.a).update(require_second_approver=False)
        live = self.live()
        RuleSettings.objects.filter(school=self.a).update(require_second_approver=True)
        copy = lifecycle.clone(live, self.b_admin)
        self.assertEqual((copy.created_by_id, copy.last_edited_by_id), (self.b_admin.pk, self.b_admin.pk))
