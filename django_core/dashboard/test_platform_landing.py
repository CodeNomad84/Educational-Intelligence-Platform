"""Where the platform roles land after login: a superuser on the Django admin, a PlatformAdmin (staff) on the operator page."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from dashboard.home import home_url_for
from students.access import PLATFORM_ADMIN

User = get_user_model()


class LandingTests(TestCase):
    def operator(self, staff=True):
        user = User.objects.create_user('pa', password='x', is_staff=staff)
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        return user

    def test_platform_admin_lands_on_the_operator_page(self):
        self.operator()
        response = self.client.post(reverse('dashboard:login'), {'username': 'pa', 'password': 'x'})
        self.assertRedirects(response, reverse('dashboard:operator_overview'), fetch_redirect_response=False)
        self.client.force_login(User.objects.get(username='pa'))
        self.assertEqual(self.client.get(reverse('dashboard:operator_overview')).status_code, 200)
        self.assertEqual(self.client.get('/dashboard/', follow=False).status_code, 403)    # not a school role: no school pages

    def test_superuser_still_lands_on_the_admin(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertEqual(home_url_for(root), '/admin/')

    def test_group_member_without_staff_gets_no_operator_page(self):
        user = self.operator(staff=False)
        self.assertEqual(home_url_for(user), reverse('dashboard:login'))     # misconfigured account: nothing is granted
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('dashboard:operator_overview')).status_code, 403)

    def test_school_roles_are_unchanged(self):
        user = User.objects.create_user('t', password='x')
        user.groups.add(Group.objects.get_or_create(name='Teacher')[0])
        self.assertEqual(home_url_for(user), reverse('dashboard:teacher_home'))
