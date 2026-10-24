"""Sidebar hygiene: each role has ONE home entry. No sidebar has two links to the same URL, or to URLs that end on the same
page (a link that redirects counts as the page it redirects to). Synthetic data only."""
import re

from django.urls import resolve

from schools.module_grants import grant
from schools.models import TeacherAssignment

from .test_counselor import Base, make_user

LINK = re.compile(r'<nav[^>]*class="[^"]*sidebar[^"]*"[^>]*>(.*?)</nav>', re.S)
HREF = re.compile(r'<a href="([^"]+)"')


class SidebarTests(Base):
    def setUp(self):
        super().setUp()
        grant(self.a)                                              # every sellable module on, so every optional link shows
        self.teacher = make_user('t', 'Teacher', self.a)
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.c7, subject='math')
        self.stu = make_user('stu', 'Student')
        self.s7.student_user = self.stu
        self.s7.save(update_fields=['student_user'])
        self.s7.parent_user = self.parent
        self.s7.save(update_fields=['parent_user'])

    def sidebar_links(self, user):
        self.client.force_login(user)
        page = self.client.get('/account/')                         # any page that extends the base layout
        self.assertEqual(page.status_code, 200)
        match = LINK.search(page.content.decode())
        self.assertIsNotNone(match)
        return [h for h in HREF.findall(match.group(1)) if not h.startswith('#')]

    def landing(self, path):
        """The path a link finally shows: follows redirects (a link to /dashboard/ ends on the role's own home)."""
        self.client.raise_request_exception = False             # a broken target (500) still has a path to compare
        response = self.client.get(path, follow=True)
        return response.redirect_chain[-1][0] if response.redirect_chain else path

    def test_no_role_has_two_links_to_the_same_page(self):
        for user in (self.admin, self.lead, self.counselor, self.teacher, self.parent, self.stu):
            with self.subTest(user=user.username):
                links = self.sidebar_links(user)
                self.assertEqual(len(links), len(set(links)), f'duplicate href in {links}')
                landings = [self.landing(link) for link in links]
                self.assertEqual(len(landings), len(set(landings)), f'links ending on the same page: {list(zip(links, landings))}')
                views = [(m.func, tuple(m.args), tuple(sorted(m.kwargs.items()))) for m in (resolve(p.split('?')[0]) for p in landings)]
                self.assertEqual(len(views), len(set(views)), f'links rendering the same view: {list(zip(links, landings))}')

    def test_only_the_school_admin_has_the_generic_dashboard_entry(self):
        for user, has in ((self.admin, True), (self.lead, False), (self.counselor, False), (self.teacher, False),
                          (self.parent, False), (self.stu, False)):
            with self.subTest(user=user.username):
                self.assertEqual('/dashboard/' in self.sidebar_links(user), has)

    def test_each_role_still_has_its_home_entry(self):
        homes = {self.admin: '/school/', self.lead: '/grade/', self.counselor: '/counselor/', self.teacher: '/teacher/',
                 self.parent: '/students/', self.stu: '/me/'}
        for user, home in homes.items():
            with self.subTest(user=user.username):
                self.assertIn(home, self.sidebar_links(user))

    def test_no_sidebar_link_ends_in_a_server_error(self):
        """Guards the class of bug where a menu entry points at a broken page (the old /upload/ stub)."""
        self.client.raise_request_exception = False
        for user in (self.admin, self.lead, self.counselor, self.teacher, self.parent, self.stu):
            self.client.force_login(user)
            for link in self.sidebar_links(user):
                if link.endswith('/logout/'):
                    continue
                with self.subTest(user=user.username, link=link):
                    self.assertLess(self.client.get(link, follow=True).status_code, 500)

    def test_the_school_admin_upload_entry_opens_the_bulk_accounts_page(self):
        from django.urls import reverse
        self.client.force_login(self.admin)
        links = self.sidebar_links(self.admin)
        self.assertIn(reverse('dashboard:school_accounts'), links)
        self.assertEqual(self.client.get(reverse('dashboard:school_accounts')).status_code, 200)
        self.assertEqual(self.client.get('/upload/').status_code, 404)             # the dead stub route is gone
