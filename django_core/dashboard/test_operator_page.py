"""Platform operator page: allowed for a superuser and a PlatformAdmin (active staff), denied for everyone else, school names and
counters only (no student data, no personal names), expiring filter, caps, audit. Synthetic data only."""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from schools.models import AICallUsage, AuditEvent, School, SchoolModule
from schools.module_grants import grant
from students.access import PLATFORM_ADMIN

from .test_counselor import Base, make_user

TODAY = timezone.localdate
URL = '/platform/modules/'


class OperatorBase(Base):
    def setUp(self):
        super().setUp()
        SchoolModule.objects.all().delete()
        self.root = make_user('root', is_staff=True, is_superuser=True)
        self.platform = make_user('platform', PLATFORM_ADMIN, is_staff=True)
        self.t = make_user('teach', 'Teacher', self.a)
        self.s7.student_user = make_user('stu', 'Student')
        self.s7.save(update_fields=['student_user'])

    def get(self, user, url=URL):
        self.client.force_login(user)
        return self.client.get(url)


class AccessTests(OperatorBase):
    def test_allowed(self):
        for user in (self.root, self.platform):
            self.assertEqual(self.get(user).status_code, 200, user.username)

    def test_denied(self):
        no_staff = make_user('platform-nostaff', PLATFORM_ADMIN)                      # group without is_staff: not an operator
        inactive = make_user('root2', is_staff=True, is_superuser=True)
        inactive.is_active = False
        inactive.save()
        for user in (self.admin, self.lead, self.counselor, self.t, self.parent, self.s7.student_user, no_staff):
            self.assertEqual(self.get(user).status_code, 403, user.username)
        self.client.force_login(inactive)
        self.assertIn(self.client.get(URL).status_code, (302, 403))                   # an inactive account cannot even log in
        self.client.logout()
        self.assertEqual(self.client.get(URL).status_code, 302)                        # anonymous: to the login page
        self.assertEqual(self.client.post(URL).status_code, 302)

    def test_a_school_admin_who_is_staff_is_still_denied(self):
        self.admin.is_staff = True
        self.admin.save()
        self.assertEqual(self.get(self.admin).status_code, 403)

    def test_menu_link_only_for_operators(self):
        link = f'href="{URL}"'
        self.assertIn(link, self.get(self.platform, reverse('dashboard:profile')).content.decode())
        for user in (self.admin, self.t, self.lead):
            self.assertNotIn(link, self.get(user, reverse('dashboard:profile')).content.decode())


class ContentTests(OperatorBase):
    def test_states_end_dates_and_days_left(self):
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() - timedelta(days=1),
                                    ends_on=TODAY() + timedelta(days=5))
        grant(self.a, 'mission', ends_on=TODAY() + timedelta(days=100))
        grant(self.a, 'tutor_ai')                                                      # licensed, open ended
        page = self.get(self.platform)
        entry = next(e for e in page.context['schools'] if e['school'] == self.a)
        by = {m['key']: m for m in entry['modules']}
        self.assertEqual((by['exams']['state'], by['exams']['days'], by['exams']['expiring']), ('active_trial', 5, True))
        self.assertEqual((by['mission']['state'], by['mission']['days'], by['mission']['expiring']), ('active_licensed', 100, False))
        self.assertEqual((by['tutor_ai']['state'], by['tutor_ai']['end'], by['tutor_ai']['days']), ('active_licensed', None, None))
        self.assertEqual((by['advisor_ai']['state'], by['advisor_ai']['end']), ('locked', None))
        other = next(e for e in page.context['schools'] if e['school'] == self.b)
        self.assertEqual({m['state'] for m in other['modules']}, {'locked'})

    def test_expiring_filter(self):
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() - timedelta(days=1),
                                    ends_on=TODAY() + timedelta(days=14))
        grant(self.b, 'mission', ends_on=TODAY() + timedelta(days=15))
        names = lambda page: [e['school'].code for e in page.context['schools'] if e['school'].code in ('a', 'b')]       # noqa: E731
        self.assertEqual(names(self.get(self.root, URL + '?expiring=1')), ['a'])        # 14 days counts, 15 does not
        self.assertEqual(sorted(names(self.get(self.root))), ['a', 'b'])
        SchoolModule.objects.all().delete()
        self.assertEqual(names(self.get(self.root, URL + '?expiring=1')), [])

    def test_ai_usage_against_caps(self):
        self.a.ai_daily_cap, self.a.ai_monthly_cap = 7, 70
        self.a.save()
        AICallUsage.objects.create(school=self.a, module_key='tutor_ai', day=TODAY(), count=3)
        AICallUsage.objects.create(school=self.a, module_key='tutor_ai', day=TODAY() - timedelta(days=10), count=4)
        AICallUsage.objects.create(school=self.a, module_key='tutor_ai', day=TODAY() - timedelta(days=45), count=99)   # outside 30 days
        entry = next(e for e in self.get(self.root).context['schools'] if e['school'] == self.a)
        usage = entry['usage']
        self.assertEqual((usage['daily_cap'], usage['monthly_cap']), (7, 70))
        self.assertEqual((usage['modules']['tutor_ai']['last30'], usage['modules']['tutor_ai']['today']), (7, 3))
        self.assertEqual(usage['modules']['advisor_ai']['last30'], 0)

    def test_no_student_data_or_personal_names_in_the_html(self):
        grant(self.a, 'mission')
        html = self.get(self.platform).content.decode()
        for secret in ('Seven', 'Eight', 'Bee', self.s7.national_id, 'teach', 'lead', 'counselor', 'parent', 'stu'):
            self.assertNotIn(secret, html.replace(URL, '').replace('platform', '').replace('root', ''), secret)
        self.assertIn('<strong>A</strong>', html)                                          # school names are shown

    def test_audit_one_event_per_school_without_content(self):
        self.get(self.platform)
        self.get(self.platform, URL + '?expiring=1')
        events = AuditEvent.objects.filter(action='platform_overview_view')
        schools = School.objects.count()                                                 # includes the default school of the migrations
        self.assertEqual(sorted(events.values_list('school__code', 'detail', 'username'))[:2], [('a', 'a', 'platform'), ('b', 'a', 'platform')])
        self.assertEqual(events.count(), schools)                                        # the filtered view showed no school: no event
        self.get(self.root)
        self.assertEqual(AuditEvent.objects.filter(action='platform_overview_view').count(), 2 * schools)
