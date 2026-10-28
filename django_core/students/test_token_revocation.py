"""Independent review 0027 finding 2 (owner decision 2026-10-28): JWTs issued before a password reset or change stop working.
A token pair is bound to a hash of the account's password (SIMPLE_JWT CHECK_REVOKE_TOKEN). Synthetic data only."""
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from dashboard.test_counselor import Base, make_user

JSON = 'application/json'
PW = 'Old-password-1'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TokenRevocationTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.user = make_user('tok-admin', 'SchoolAdmin')
        self.user.set_password(PW)
        self.user.save()
        from schools.models import SchoolMembership
        SchoolMembership.objects.create(user=self.user, school=self.a)

    def pair(self):
        response = self.client.post('/api/token/', {'username': 'tok-admin', 'password': PW}, content_type=JSON)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def list_with(self, access):
        return self.client.get('/api/students/', HTTP_AUTHORIZATION=f'Bearer {access}').status_code

    def refresh(self, refresh):
        return self.client.post('/api/token/refresh/', {'refresh': refresh}, content_type=JSON)

    def test_a_fresh_pair_works(self):
        tokens = self.pair()
        self.assertEqual(self.list_with(tokens['access']), 200)
        again = self.refresh(tokens['refresh'])
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.list_with(again.json()['access']), 200)

    def test_tokens_issued_before_a_reset_are_rejected_after_it(self):
        tokens = self.pair()
        self.user.set_password('A-new-password-2')          # what password_reset._do_reset / a user change does
        self.user.save(update_fields=['password'])
        self.assertEqual(self.list_with(tokens['access']), 401)           # the old access token
        refreshed = self.refresh(tokens['refresh'])                       # the old refresh token may mint a token ...
        if refreshed.status_code == 200:
            self.assertEqual(self.list_with(refreshed.json()['access']), 401)   # ... that is useless
        new = self.client.post('/api/token/', {'username': 'tok-admin', 'password': 'A-new-password-2'}, content_type=JSON)
        self.assertEqual(self.list_with(new.json()['access']), 200)       # the new password works

    def test_an_admin_reset_through_the_page_revokes_the_tokens(self):
        from dashboard.test_counselor import make_user as mk
        target = mk('tok-teacher', 'Teacher', self.a)
        target.set_password(PW)
        target.save()
        tokens = self.client.post('/api/token/', {'username': 'tok-teacher', 'password': PW}, content_type=JSON).json()
        self.assertTrue(self.refresh_status_usable(tokens))                 # usable before the reset
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('dashboard:school_reset', args=[target.pk])).status_code, 200)
        self.assertEqual(self.refresh_status_usable(tokens), False)

    def refresh_status_usable(self, tokens):
        if self.list_with(tokens['access']) == 200:
            return True
        refreshed = self.refresh(tokens['refresh'])
        return refreshed.status_code == 200 and self.list_with(refreshed.json()['access']) == 200
