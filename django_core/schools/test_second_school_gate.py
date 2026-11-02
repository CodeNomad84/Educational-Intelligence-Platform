"""S10-style gate (P9): with TWO schools holding distinctly named students, alerts, plans, documents and notifications, no page an admin or
staff member of school A can open shows anything of school B (and the reverse). Names are unique markers so a leak is a plain substring."""
import re
from django.urls import reverse

from risk.loop_testing import LoopBase

PAGES = ['dashboard:dashboard', 'dashboard:student_list', 'dashboard:alert_list', 'dashboard:plan_list', 'dashboard:school_home',
         'dashboard:school_strategies', 'dashboard:notifications', 'rules:index', 'rules:catalog', 'docqa:home', 'docqa:documents']


class SecondSchoolGateTests(LoopBase):
    def setUp(self):
        super().setUp()
        from docqa.models import DocumentChunk, SchoolDocument
        from schools import entitlements
        from datetime import date, timedelta
        from students.models import Student
        for school, tag in ((self.a, 'ZQALPHA'), (self.b, 'ZQBRAVO')):
            for n, s in enumerate(Student.objects.filter(school=school)):
                Student.objects.filter(pk=s.pk).update(first_name=f'{tag}{n}', last_name=f'{tag}FAMILY{n}')
        for school, title in ((self.a, 'ZQDOCALPHA'), (self.b, 'ZQDOCBRAVO')):
            entitlements.set_module(school, 'advisor_ai', date.today(), date.today() + timedelta(days=30), kind=entitlements.TRIAL)
            doc = SchoolDocument.objects.create(school=school, title=title, char_count=10)
            DocumentChunk.objects.create(document=doc, school=school, ordinal=0, text=f'{title} text about timetable')
        self.alert(self.s7)                                    # an alert and a plan in school A
        self.plan(by=self.lead, student=self.s7)
        from students.models import Student as S
        sb = S.objects.get(pk=self.sb.pk)
        from risk.services import raise_alert
        raise_alert(sb, risk_type='academic', severity='yellow', message='bravo alert', explanation='bravo', detected_by='admin')

    def seen(self, user, school_tag):
        self.client.force_login(user)
        found = []
        for name in PAGES:
            page = self.client.get(reverse(name))
            if page.status_code != 200:
                continue
            text = re.sub(r'[A-Za-z0-9]{32,}', '', page.content.decode())
            if school_tag in text:
                found.append(name)
        return found

    def test_school_a_staff_never_see_school_b_and_the_reverse(self):
        for user in (self.admin, self.lead):
            self.assertEqual(self.seen(user, 'ZQBRAVO'), [], user.username)
            self.assertEqual(self.seen(user, 'ZQDOCBRAVO'), [], user.username)
        self.assertEqual(self.seen(self.admin_b, 'ZQALPHA'), [])
        self.assertEqual(self.seen(self.admin_b, 'ZQDOCALPHA'), [])
        self.assertEqual(self.seen(self.lead_b, 'ZQALPHA'), [])

    def test_the_gate_does_see_its_own_school(self):
        self.assertIn('dashboard:student_list', self.seen(self.admin, 'ZQALPHA'))          # a vacuous gate would pass the test above
        self.assertIn('docqa:documents', self.seen(self.admin, 'ZQDOCALPHA'))
