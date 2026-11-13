"""JSON session auth for the two presentation frontends (ADR-0014, docs/changes/0040 §11, cases 1-16).

Synthetic accounts only. The throttle counters are shared with the HTML login and ``/api/token/``, so every test starts
from a clear cache; no test edits an existing one to make a new behaviour pass.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from schools.models import AccountProfile, School, SchoolMembership

from . import throttle

User = get_user_model()
PASSWORD = 'Str0ng-demo-pass-77'
ME_KEYS = {'id', 'username', 'display_name', 'roles', 'role', 'schools', 'school', 'modules',
           'is_platform_operator', 'must_change_password', 'gender_scope', 'theme'}


class AuthApiBase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.school = School.objects.create(name='A', code='a')
        self.other = School.objects.create(name='B', code='b')
        self.user = User.objects.create_user('9000000001', password=PASSWORD,
                                             first_name='سارا', last_name='احمدی')
        self.user.groups.add(Group.objects.get_or_create(name='SchoolAdmin')[0])
        SchoolMembership.objects.create(user=self.user, school=self.school)
        self.url = {'login': reverse('auth_login'), 'me': reverse('auth_me'), 'csrf': reverse('auth_csrf'),
                    'logout': reverse('auth_logout')}

    def login(self, username='9000000001', password=PASSWORD, client=None):
        return (client or self.client).post(self.url['login'], {'username': username, 'password': password},
                                            content_type='application/json')


class LoginTests(AuthApiBase):
    def test_1_correct_credentials_open_a_session(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['username'], '9000000001')
        self.assertEqual(body['roles'], ['SchoolAdmin'])
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))

    def test_2_wrong_password_is_401_and_generic(self):
        response = self.login(password='wrong')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'detail': 'نام کاربری یا رمز عبور اشتباه است.'})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_3_unknown_username_is_byte_identical(self):
        unknown = self.login(username='9999999999', password='wrong')
        known = self.login(password='wrong')
        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.content, known.content)          # no enumeration
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_4_inactive_account_is_refused_like_a_wrong_password(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.login()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'detail': 'نام کاربری یا رمز عبور اشتباه است.'})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_5_flagged_account_gets_no_session(self):
        AccountProfile.objects.create(user=self.user, must_change_password=True)
        response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'password_change_required')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_6_five_failures_then_the_right_password_is_429(self):
        for _ in range(5):
            self.assertEqual(self.login(password='wrong').status_code, 401)
        locked = self.login()
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json(), {'detail': throttle.LOCKED_MESSAGE})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_7_address_locks_across_usernames(self):
        for i in range(20):
            self.login(username=f'80000000{i:02d}', password='wrong')
        self.assertEqual(self.login().status_code, 429)
        other_ip = Client(REMOTE_ADDR='10.1.2.3')
        self.assertEqual(self.login(client=other_ip).status_code, 200)   # another address is unaffected

    def test_8_session_then_me(self):
        self.assertEqual(self.login().status_code, 200)
        response = self.client.get(self.url['me'])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['roles'], ['SchoolAdmin'])
        self.assertEqual(body['schools'], [{'id': self.school.id, 'name': 'A'}])
        self.assertEqual(body['school'], {'id': self.school.id, 'name': 'A'})
        self.assertEqual(body['role'], 'SchoolAdmin')
        self.assertEqual(body['display_name'], 'سارا احمدی')

    def test_9_anonymous_me_is_json_401(self):
        response = self.client.get(self.url['me'])
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['Content-Type'].split(';')[0], 'application/json')

    def test_10_jwt_is_accepted_by_me(self):
        token = self.client.post(reverse('token_obtain_pair'),
                                 {'username': '9000000001', 'password': PASSWORD}).json()['access']
        response = self.client.get(self.url['me'], HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], '9000000001')

    def test_11_both_credential_paths_refuse_a_flagged_account(self):
        AccountProfile.objects.create(user=self.user, must_change_password=True)
        token = self.client.post(reverse('token_obtain_pair'), {'username': '9000000001', 'password': PASSWORD})
        self.assertEqual(token.status_code, 403)
        self.assertEqual(self.login().status_code, 403)           # same rule on both paths (C6)

    def test_13_csrf_is_required(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(self.login(client=strict).status_code, 403)      # no token: refused before the password check
        csrf = strict.get(self.url['csrf'])
        self.assertEqual(csrf.status_code, 200)
        token = csrf.json()['csrfToken']
        self.assertIn('csrftoken', strict.cookies)
        response = strict.post(self.url['login'], {'username': '9000000001', 'password': PASSWORD},
                               content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        # login() rotates the CSRF secret, so the client must read the cookie again before the next POST
        token = strict.get(self.url['csrf']).json()['csrfToken']
        self.assertEqual(strict.post(self.url['logout']).status_code, 403)   # logout is protected too
        self.assertEqual(strict.post(self.url['logout'], HTTP_X_CSRFTOKEN=token).status_code, 204)


class ProfileTests(AuthApiBase):
    def test_12_flagged_account_gets_json_403_not_a_redirect(self):
        AccountProfile.objects.create(user=self.user, must_change_password=True)
        self.client.force_login(self.user)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'].split(';')[0], 'application/json')
        self.assertEqual(response.json()['code'], 'password_change_required')
        # the pages it may use still work, and /api/auth/ stays reachable so it can sign out
        self.assertEqual(self.client.get(reverse('dashboard:password_change')).status_code, 200)
        self.assertEqual(self.client.post(self.url['logout']).status_code, 204)

    def test_14_15_cors_headers_follow_the_allowed_list(self):
        with override_settings(CORS_ALLOWED_ORIGINS=['http://localhost:5173'], CORS_ALLOW_CREDENTIALS=True):
            allowed = self.client.options(self.url['me'], HTTP_ORIGIN='http://localhost:5173',
                                          HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET')
            self.assertEqual(allowed['Access-Control-Allow-Origin'], 'http://localhost:5173')
            self.assertEqual(allowed['Access-Control-Allow-Credentials'], 'true')
            refused = self.client.options(self.url['me'], HTTP_ORIGIN='https://evil.example',
                                          HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET')
            self.assertNotIn('Access-Control-Allow-Origin', refused)

    def test_16_body_keys_and_no_private_fields(self):
        AccountProfile.objects.create(user=self.user, phone='09120000000')
        self.client.force_login(self.user)
        response = self.client.get(self.url['me'])
        self.assertEqual(set(response.json()), ME_KEYS)
        body = response.content.decode()
        for private in ('national_id', 'phone', '09120000000', 'counselor_note', 'pbkdf2_', 'md5$'):
            self.assertNotIn(private, body)
        self.assertEqual(set(response.json()['schools'][0]), {'id', 'name'})

    def test_16b_multi_school_needs_an_explicit_choice(self):
        SchoolMembership.objects.create(user=self.user, school=self.other)
        self.client.force_login(self.user)
        body = self.client.get(self.url['me']).json()
        self.assertIsNone(body['school'])                          # never first()
        self.assertEqual(len(body['schools']), 2)
        chosen = self.client.get(self.url['me'], {'school': self.other.id}).json()
        self.assertEqual(chosen['school'], {'id': self.other.id, 'name': 'B'})
        denied = School.objects.create(name='C', code='c')
        self.assertEqual(self.client.get(self.url['me'], {'school': denied.id}).status_code, 400)

    def test_logout_ends_the_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url['logout']).status_code, 204)
        self.assertEqual(self.client.get(self.url['me']).status_code, 401)

    def test_missing_fields_are_400(self):
        self.assertEqual(self.client.post(self.url['login'], {'username': '9000000001'},
                                          content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(self.url['login'], {'username': '9000000001', 'password': 123},
                                          content_type='application/json').status_code, 400)
