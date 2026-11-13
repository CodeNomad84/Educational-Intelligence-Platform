"""P5-1 principal dashboard and P5-2 support levels (decision pack 0028). Synthetic data only.

The page is SchoolAdmin only, shows one school among the user's memberships, reads no alert or plan text, withholds rates of
groups under 5, and audit-logs the attention list. Support levels are derived, review scope only."""
from datetime import timedelta

from django.utils import timezone

from interventions.models import InterventionPlan
from interventions.support import INTENSIVE, TARGETED, UNIVERSAL, level_for
from risk.services import raise_alert
from schools.models import AuditEvent, TeacherAssignment
from students.models import Attendance

from .test_counselor import Base, make_user

SECRET = 'PRIVATE-ALERT-TEXT'


class LevelRuleTests(Base):
    def test_rule(self):
        self.assertEqual(level_for(0, 0, 0), UNIVERSAL)
        self.assertEqual(level_for(0, 1, 0), UNIVERSAL)
        self.assertEqual(level_for(0, 2, 0), TARGETED)
        self.assertEqual(level_for(0, 1, 1), TARGETED)
        self.assertEqual(level_for(1, 0, 0), TARGETED)
        self.assertEqual(level_for(1, 1, 1), INTENSIVE)
        self.assertEqual(level_for(2, 0, 0), INTENSIVE)


class PrincipalTests(Base):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        raise_alert(self.s7, risk_type='attendance', severity='orange', message=SECRET, explanation=SECRET, detected_by='admin')
        self.plan(self.s7)
        raise_alert(self.sb, risk_type='academic', severity='orange', message='b', explanation='b', detected_by='admin')
        self.plan(self.sb, owner=self.admin_b)

    def plan(self, student, owner=None):
        return InterventionPlan.objects.create(
            school=student.school, student=student, owner=owner or self.admin, created_by=owner or self.admin,
            intervention_type='academic', goal=SECRET, action_plan=SECRET, status=InterventionPlan.ACTIVE,
            start_date=self.today - timedelta(days=20), due_date=self.today - timedelta(days=1))

    def page(self, user, **params):
        self.client.force_login(user)
        return self.client.get('/dashboard/', params)

    def test_admin_sees_own_school_only_and_no_text(self):
        page = self.page(self.admin)
        o = page.context['overview']
        self.assertEqual((o['total'], o['alerts']['new'], o['plans']['open'], o['plans']['overdue']), (2, 1, 1, 1))
        self.assertEqual([a['student'] for a in o['attention']], [self.s7])
        self.assertEqual(o['attention'][0]['level'], INTENSIVE)
        self.assertNotContains(page, SECRET)
        self.assertNotContains(page, self.sb.first_name)
        self.assertEqual(self.page(self.admin, school=self.b.pk).context['overview']['total'], 2)   # foreign id: own school

    def test_small_groups_are_withheld(self):
        for day in range(1, 8):
            for s in (self.s7, self.s8):
                Attendance.objects.create(student=s, date=self.today - timedelta(days=day), status='present')
        o = self.page(self.admin).context['overview']
        self.assertIsNone(o['attendance'])                          # 2 students < 5
        self.assertTrue(all(c['attendance'] is None and c['average'] is None for c in o['classes']))
        self.assertTrue(all(v is None for v in o['weekly_attendance']['values']))

    def test_other_roles_do_not_get_the_page(self):
        teacher = make_user('t', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=teacher, school_class=self.c7, subject='math')
        for user in (self.lead, self.counselor, teacher, self.parent):
            with self.subTest(user=user.username):
                response = self.page(user)
                self.assertEqual(response.status_code, 302)
                self.assertNotIn('overview', response.context or {})

    def test_attention_list_is_audit_logged(self):
        self.page(self.admin)
        event = AuditEvent.objects.get(action='list_view', username='admin')
        self.assertEqual((event.school_id, event.detail), (self.a.pk, 'attention:n1'))

    def test_admin_without_membership_sees_empty_page(self):
        page = self.page(make_user('lonely', 'SchoolAdmin'))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context['no_school'])


class SupportLevelVisibilityTests(PrincipalTests):
    def test_student_list_shows_levels_to_reviewers_only(self):
        self.assertContains(self.page_list(self.admin), 'tier-3')
        self.assertContains(self.page_list(self.lead), 'tier-3')
        teacher = make_user('t2', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=teacher, school_class=self.c7, subject='math')
        self.assertNotContains(self.page_list(teacher), 'eip-tier')
        self.assertNotContains(self.page_list(self.parent), 'eip-tier')

    def page_list(self, user):
        self.client.force_login(user)
        return self.client.get('/students/')

    def test_student_360_badge(self):
        self.client.force_login(self.admin)
        page = self.client.get(f'/students/{self.s7.pk}/360/')
        self.assertContains(page, 'tier-3')
        self.assertEqual(page.context['support']['open_plans'], 1)
        self.assertIsNone(self.client.get(f'/students/{self.s8.pk}/360/').context['support'])

    test_admin_sees_own_school_only_and_no_text = test_small_groups_are_withheld = None
    test_other_roles_do_not_get_the_page = test_attention_list_is_audit_logged = None
    test_admin_without_membership_sees_empty_page = None
