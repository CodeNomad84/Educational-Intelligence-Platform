"""Login throttle (brute force on guessable national-id usernames): per username and per address, login page and JWT endpoint."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from schools.models import AccountProfile

User = get_user_model()


class ThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user('9000000001', password='Right-pass-1')
        self.other = User.objects.create_user('9000000002', password='Right-pass-2')

    def login(self, username, password, client=None, **extra):
        return (client or self.client).post(reverse('dashboard:login'), {'username': username, 'password': password}, **extra)

    def test_username_locks_after_five_failures_even_for_the_right_password(self):
        for _ in range(5):
            self.assertEqual(self.login('9000000001', 'wrong').status_code, 200)
        locked = self.login('9000000001', 'Right-pass-1')
        self.assertEqual(locked.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)          # the right password did not sign in
        self.assertEqual(self.login('9000000002', 'Right-pass-2').status_code, 302)   # another username is unaffected

    def test_unknown_username_behaves_like_a_known_one(self):
        for _ in range(5):
            self.login('9999999999', 'wrong')
        self.assertEqual(self.login('9999999999', 'wrong').status_code, 429)   # no way to tell the account does not exist
        for _ in range(5):
            self.login('9000000001', 'wrong')
        self.assertEqual(self.login('9000000001', 'wrong').status_code, 429)

    def test_success_clears_the_username_counter(self):
        for _ in range(4):
            self.login('9000000001', 'wrong')
        self.assertEqual(self.login('9000000001', 'Right-pass-1').status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.login('9000000001', 'wrong')
        self.assertEqual(self.login('9000000001', 'Right-pass-1').status_code, 302)   # still under the limit

    def test_address_locks_across_usernames(self):
        for i in range(20):
            self.login(f'80000000{i:02d}', 'wrong')
        self.assertEqual(self.login('9000000002', 'Right-pass-2').status_code, 429)
        other_ip = Client(REMOTE_ADDR='10.1.2.3')
        self.assertEqual(self.login('9000000002', 'Right-pass-2', client=other_ip).status_code, 302)

    @override_settings(LOGIN_MAX_FAILURES_USER=2)
    def test_limits_are_settings(self):
        self.login('9000000001', 'wrong'); self.login('9000000001', 'wrong')
        self.assertEqual(self.login('9000000001', 'Right-pass-1').status_code, 429)

    def test_token_endpoint_has_the_same_limit(self):
        url = reverse('token_obtain_pair')
        for _ in range(5):
            self.assertEqual(self.client.post(url, {'username': '9000000001', 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post(url, {'username': '9000000001', 'password': 'Right-pass-1'}).status_code, 429)
        self.assertEqual(self.client.post(url, {'username': '9000000002', 'password': 'Right-pass-2'}).status_code, 200)

    def test_flagged_account_gets_no_token_until_it_changes_the_password(self):
        AccountProfile.objects.create(user=self.user, must_change_password=True)
        url = reverse('token_obtain_pair')
        response = self.client.post(url, {'username': '9000000001', 'password': 'Right-pass-1'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('access', response.json())
        AccountProfile.objects.filter(user=self.user).update(must_change_password=False)
        self.assertEqual(self.client.post(url, {'username': '9000000001', 'password': 'Right-pass-1'}).status_code, 200)


class AdminLoginThrottleTests(TestCase):
    """/admin/login/ shares the limits and the counters of /login/."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.staff = User.objects.create_user('9000000011', password='Right-pass-1', is_staff=True, is_superuser=True)
        self.url = '/admin/login/'

    def attempt(self, username, password, **extra):
        return self.client.post(self.url, {'username': username, 'password': password, 'next': '/admin/'}, **extra)

    def test_username_locks_after_five_failures_even_for_the_right_password(self):
        for _ in range(5):
            self.assertEqual(self.attempt('9000000011', 'wrong').status_code, 200)
        self.assertEqual(self.attempt('9000000011', 'Right-pass-1').status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_success_signs_in_and_clears_the_counter(self):
        for _ in range(4):
            self.attempt('9000000011', 'wrong')
        self.assertEqual(self.attempt('9000000011', 'Right-pass-1').status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.assertEqual(self.attempt('9000000011', 'wrong').status_code, 200)      # the counter restarted

    def test_unknown_username_and_address_limits(self):
        for _ in range(5):
            self.attempt('9999999999', 'wrong')
        self.assertEqual(self.attempt('9999999999', 'wrong').status_code, 429)
        cache.clear()
        for n in range(20):
            self.attempt(f'u{n}', 'wrong')
        self.assertEqual(self.attempt('9000000011', 'Right-pass-1').status_code, 429)   # the address is locked

    def test_counters_are_shared_with_the_normal_login_and_get_is_untouched(self):
        for _ in range(5):
            self.client.post(reverse('dashboard:login'), {'username': '9000000011', 'password': 'wrong'})
        self.assertEqual(self.attempt('9000000011', 'Right-pass-1').status_code, 429)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class ClientAddressTests(TestCase):
    """Which address the limits count: REMOTE_ADDR by default, X-Forwarded-For only behind a configured trusted proxy."""

    def request(self, remote, forwarded=None):
        from django.test import RequestFactory
        extra = {'REMOTE_ADDR': remote}
        if forwarded is not None:
            extra['HTTP_X_FORWARDED_FOR'] = forwarded
        return RequestFactory().post('/login/', **extra)

    def test_default_ignores_x_forwarded_for(self):
        from dashboard.throttle import client_ip
        self.assertEqual(client_ip(self.request('10.0.0.5', '203.0.113.9')), '10.0.0.5')
        self.assertEqual(client_ip(self.request('198.51.100.7', '1.2.3.4, 5.6.7.8')), '198.51.100.7')

    @override_settings(THROTTLE_TRUSTED_PROXIES=['10.0.0.5', '172.18.0.0/16'])
    def test_trusted_proxy_mode(self):
        from dashboard.throttle import client_ip
        self.assertEqual(client_ip(self.request('10.0.0.5', '203.0.113.9')), '203.0.113.9')
        self.assertEqual(client_ip(self.request('10.0.0.5', '1.1.1.1, 203.0.113.9, 172.18.0.3')), '203.0.113.9')   # right-most non-proxy; the 1.1.1.1 is client-controlled
        self.assertEqual(client_ip(self.request('172.18.4.4', '203.0.113.9')), '203.0.113.9')                    # a network entry
        self.assertEqual(client_ip(self.request('10.0.0.5')), '10.0.0.5')                                        # no header: fall back
        self.assertEqual(client_ip(self.request('10.0.0.5', 'not-an-ip')), '10.0.0.5')                           # malformed: fall back
        self.assertEqual(client_ip(self.request('10.0.0.5', '203.0.113.9, junk')), '10.0.0.5')
        self.assertEqual(client_ip(self.request('10.0.0.5', '10.0.0.5, 172.18.0.3')), '10.0.0.5')                # only proxies in the chain

    @override_settings(THROTTLE_TRUSTED_PROXIES=['10.0.0.5'])
    def test_a_header_from_an_untrusted_peer_is_ignored(self):
        from dashboard.throttle import client_ip
        self.assertEqual(client_ip(self.request('198.51.100.7', '203.0.113.9')), '198.51.100.7')                 # spoofing attempt

    @override_settings(THROTTLE_TRUSTED_PROXIES=['not-a-network', ''])
    def test_a_bad_setting_means_off(self):
        from dashboard.throttle import client_ip
        self.assertEqual(client_ip(self.request('10.0.0.5', '203.0.113.9')), '10.0.0.5')

    def test_the_limits_follow_the_configured_address_end_to_end(self):
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_user('9000000021', password='Right-pass-1')
        def attempt(n, **extra):
            return self.client.post(reverse('dashboard:login'), {'username': f'nobody{n}', 'password': 'x'}, **extra)
        with override_settings(THROTTLE_TRUSTED_PROXIES=['10.0.0.5']):
            for n in range(20):                                                   # 20 failures from client A behind the proxy
                attempt(n, REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR='203.0.113.9')
            self.assertEqual(attempt(99, REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR='203.0.113.9').status_code, 429)
            self.assertEqual(attempt(100, REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR='203.0.113.77').status_code, 200)   # client B is not locked
        cache.clear()
        for n in range(20):                                                       # default mode: everyone behind the proxy is one address
            attempt(n, REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR=f'203.0.113.{n}')
        self.assertEqual(attempt(101, REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR='203.0.113.200').status_code, 429)
