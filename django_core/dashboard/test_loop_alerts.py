"""Alert pages (change 0022): roles, scope, the review forms, the base-module gate, menu, audit."""
from django.urls import reverse

from risk.loop_testing import LoopBase
from risk.models import Alert
from schools.models import AuditEvent, SchoolModule

ADD = {'risk_type': 'academic', 'severity': 'yellow', 'message': 'Grades fell sharply'}


class AlertPageTests(LoopBase):
    def setUp(self):
        super().setUp()
        self.refer(self.s7, self.counselor)

    def test_no_module_rows_are_needed(self):
        self.assertEqual(SchoolModule.objects.filter(school=self.a).count(), 0)
        for user in (self.admin, self.lead, self.counselor, self.teacher):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('dashboard:alert_list')).status_code, 200, user.username)

    def test_anonymous_parent_and_student_are_refused(self):
        self.assertEqual(self.client.get(reverse('dashboard:alert_list')).status_code, 302)
        for user in (self.parent, self.student_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('dashboard:alert_list')).status_code, 403)
            self.assertEqual(self.client.post(reverse('dashboard:alert_new', args=[self.s7.pk]), ADD).status_code, 403)
        self.assertEqual(Alert.objects.count(), 0)

    def test_raise_through_the_page(self):
        for user in (self.teacher, self.lead, self.counselor, self.admin):
            self.client.force_login(user)
            response = self.client.post(reverse('dashboard:alert_new', args=[self.s7.pk]), ADD)
            self.assertRedirects(response, reverse('dashboard:alert_list'), msg_prefix=user.username)
        self.assertEqual(Alert.objects.filter(student=self.s7).count(), 4)
        self.assertEqual(AuditEvent.objects.filter(action='alert_raise').count(), 4)

    def test_raise_outside_scope_is_404_and_changes_nothing(self):
        cases = [(self.teacher, self.s8), (self.teacher, self.sb), (self.lead, self.s8), (self.admin, self.sb),
                 (self.admin_b, self.s7), (self.counselor_b, self.s7), (self.counselor, self.s8)]
        for user, student in cases:
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('dashboard:alert_new', args=[student.pk]), ADD).status_code, 404,
                             (user.username, student.first_name))
        self.assertEqual(Alert.objects.count(), 0)

    def test_invalid_form_shows_errors(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('dashboard:alert_new', args=[self.s7.pk]), {**ADD, 'message': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Alert.objects.count(), 0)

    def test_list_follows_the_scope(self):
        mine = self.alert(by=self.teacher)
        self.alert(self.s8)
        self.alert(self.sb, by=self.admin_b)
        for user, expected in ((self.teacher, 1), (self.lead, 1), (self.lead8, 1), (self.admin, 2), (self.admin_b, 1),
                               (self.counselor, 1)):
            self.client.force_login(user)
            page = self.client.get(reverse('dashboard:alert_list'))
            self.assertEqual(len(page.context['alerts']), expected, user.username)
        self.client.force_login(self.teacher)
        self.assertEqual([a.pk for a in self.client.get(reverse('dashboard:alert_list')).context['alerts']], [mine.pk])

    def test_teacher_has_no_review_buttons_and_cannot_post_a_review(self):
        alert = self.alert(by=self.teacher)
        self.client.force_login(self.teacher)
        page = self.client.get(reverse('dashboard:alert_list')).content.decode()
        self.assertNotIn(reverse('dashboard:alert_review', args=[alert.pk]), page)
        self.assertEqual(self.client.post(reverse('dashboard:alert_review', args=[alert.pk]), {'decision': 'accept'}).status_code, 403)
        alert.refresh_from_db()
        self.assertEqual(alert.status, 'new')

    def test_review_accept_and_dismiss(self):
        a1, a2 = self.alert(), self.alert()
        self.client.force_login(self.lead)
        self.client.post(reverse('dashboard:alert_review', args=[a1.pk]), {'decision': 'accept'})
        self.client.post(reverse('dashboard:alert_review', args=[a2.pk]), {'decision': 'dismiss', 'reason': 'other'})   # note missing
        a1.refresh_from_db(), a2.refresh_from_db()
        self.assertEqual((a1.status, a2.status), ('accepted', 'new'))
        self.client.post(reverse('dashboard:alert_review', args=[a2.pk]),
                         {'decision': 'dismiss', 'reason': 'other', 'note': 'checked with the teacher'})
        a2.refresh_from_db()
        self.assertEqual((a2.status, a2.dismiss_reason), ('dismissed', 'other'))

    def test_review_of_another_school_or_grade_is_404(self):
        foreign, other_grade = self.alert(self.sb, by=self.admin_b), self.alert(self.s8)
        for user, alert in ((self.admin, foreign), (self.lead, other_grade), (self.counselor, other_grade),
                            (self.admin_b, self.alert()), (self.counselor_b, self.alert())):
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('dashboard:alert_review', args=[alert.pk]), {'decision': 'accept'}).status_code, 404)
        self.assertFalse(Alert.objects.exclude(status='new').exists())

    def test_reopen_is_admin_only(self):
        alert = self.alert()
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:alert_review', args=[alert.pk]), {'decision': 'dismiss', 'reason': 'duplicate'})
        self.client.force_login(self.lead)
        self.assertEqual(self.client.post(reverse('dashboard:alert_reopen', args=[alert.pk])).status_code, 403)
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.post(reverse('dashboard:alert_reopen', args=[alert.pk])).status_code, 404)
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:alert_reopen', args=[alert.pk]))
        alert.refresh_from_db()
        self.assertEqual(alert.status, 'new')

    def test_post_only_endpoints_refuse_get(self):
        alert = self.alert()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:alert_review', args=[alert.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('dashboard:alert_reopen', args=[alert.pk])).status_code, 405)

    def test_menu_has_exactly_one_alert_entry_per_role(self):
        url = reverse('dashboard:alert_list')
        for user in (self.admin, self.lead, self.counselor, self.teacher):
            self.client.force_login(user)
            html = self.client.get('/account/').content.decode()
            self.assertEqual(html.count(f'href="{url}"'), 1, user.username)
        for user in (self.parent, self.student_user):
            self.client.force_login(user)
            self.assertNotIn(f'href="{url}"', self.client.get('/account/').content.decode())
