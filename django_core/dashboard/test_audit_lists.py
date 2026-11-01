"""C-L (P3): pages and API reads that show student records are audit-logged: one ``list_view`` event per school with the
number of rows shown (no row ids, no content), and the API's single-record read as ``view_student_detail``. Aggregate-only
pages (dashboard counts, school home) write nothing. Synthetic data only."""
from django.urls import reverse

from risk.loop_testing import LoopBase
from schools import audit
from schools.models import AuditEvent, SchoolMembership


def events(user, action=audit.LIST_VIEW):
    return sorted(AuditEvent.objects.filter(user=user, action=action).values_list('school__code', 'detail', 'object_type'))


class ListAuditTests(LoopBase):
    def test_student_list(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:student_list')).status_code, 200)
        self.assertEqual(events(self.admin), [('a', 'students:n2', '')])

    def test_student_list_counts_what_is_shown(self):
        self.client.force_login(self.lead)                  # grade 7 of school a only
        self.client.get(reverse('dashboard:student_list'))
        self.assertEqual(events(self.lead), [('a', 'students:n1', '')])

    def test_one_event_per_school_for_a_multi_school_admin(self):
        SchoolMembership.objects.create(user=self.admin, school=self.b)
        self.client.force_login(self.admin)
        self.client.get(reverse('dashboard:student_list'))
        self.assertEqual(events(self.admin), [('a', 'students:n2', ''), ('b', 'students:n1', '')])

    def test_empty_list_writes_nothing(self):
        self.client.force_login(self.admin)
        self.client.get(reverse('dashboard:student_list'), {'search': 'nobody-has-this-name'})
        self.assertEqual(events(self.admin), [])

    def test_referral_list(self):
        self.refer(self.s7, self.counselor)
        self.client.force_login(self.counselor)
        self.assertEqual(self.client.get(reverse('dashboard:counselor_home')).status_code, 200)
        self.assertEqual(events(self.counselor), [('a', 'referrals:n1', '')])

    def test_alert_and_plan_lists(self):
        self.alert(); self.alert(student=self.s8)
        self.plan()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:alert_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard:plan_list')).status_code, 200)
        self.assertEqual(events(self.admin), [('a', 'alerts:n2', ''), ('a', 'plans:n1', '')])

    def test_aggregate_pages_write_no_list_event(self):
        self.client.force_login(self.admin)
        self.client.get('/dashboard/')
        self.assertEqual(events(self.admin), [])

    def test_unknown_page_code_is_refused(self):
        with self.assertRaises(ValueError):
            audit.record_list(self.admin, 'free text', [])


class ApiAuditTests(LoopBase):
    def test_api_list_and_detail(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/students/').status_code, 200)
        self.assertEqual(events(self.admin), [('a', 'api_students:n2', '')])
        response = self.client.get(f'/api/students/{self.s7.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], self.s7.pk)
        self.assertEqual(sorted(AuditEvent.objects.filter(user=self.admin, action=audit.VIEW_DETAIL)
                                .values_list('school__code', 'object_type', 'object_id', 'detail')),
                         [('a', 'Student', str(self.s7.pk), 'api')])

    def test_api_detail_outside_scope_is_404_and_not_logged(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f'/api/students/{self.sb.pk}/').status_code, 404)
        self.assertFalse(AuditEvent.objects.filter(action=audit.VIEW_DETAIL).exists())
