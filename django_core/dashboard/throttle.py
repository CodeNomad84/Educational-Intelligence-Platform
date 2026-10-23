"""Login throttle (brute force): usernames are national ids, i.e. guessable, so failed sign-ins are counted per username AND
per client address in Django's cache (Redis in production, so the count is shared by all workers; in development the
per-process memory cache, which is enough for a single process). No extra dependency.

* ``LOGIN_MAX_FAILURES_USER`` (5) failures for one username inside ``LOGIN_WINDOW_SECONDS`` (900) lock that username for the
  rest of the window; ``LOGIN_MAX_FAILURES_IP`` (20) failures from one address lock the address.
* A locked username or address is refused WITHOUT checking the password, with the same answer whether or not the account exists
  (no enumeration). A success clears the username counter (not the address counter).
* The address is ``REMOTE_ADDR``. Behind a reverse proxy that is the proxy's address, so every user would share one counter:
  configure the proxy to pass the real address and use a trusted-proxy middleware before relying on the IP limit (RUNBOOK).
* Locking a username also locks the real owner for the window: the price of protecting guessable usernames. A SchoolAdmin
  cannot unlock; waiting out the window or a platform administrator clearing the cache are the ways out.
"""
import hashlib

from django.conf import settings
from django.core.cache import cache

LOCKED_MESSAGE = 'تلاش‌های ناموفق بیش از حد مجاز بود؛ چند دقیقه بعد دوباره تلاش کنید.'


def _limits():
    return (getattr(settings, 'LOGIN_MAX_FAILURES_USER', 5), getattr(settings, 'LOGIN_MAX_FAILURES_IP', 20),
            getattr(settings, 'LOGIN_WINDOW_SECONDS', 900))


def _key(kind, value):
    return 'login-throttle:%s:%s' % (kind, hashlib.sha256((value or '').strip().lower().encode()).hexdigest()[:32])


def client_ip(request):
    return request.META.get('REMOTE_ADDR', '')


def is_locked(request, username):
    max_user, max_ip, _window = _limits()
    return (cache.get(_key('user', username), 0) >= max_user) or (cache.get(_key('ip', client_ip(request)), 0) >= max_ip)


def record_failure(request, username):
    _max_user, _max_ip, window = _limits()
    for kind, value in (('user', username), ('ip', client_ip(request))):
        key = _key(kind, value)
        cache.add(key, 0, window)    # the window starts at the first failure
        try:
            cache.incr(key)
        except ValueError:           # expired between add and incr
            cache.add(key, 1, window)


def record_success(username):
    cache.delete(_key('user', username))


from rest_framework import status as _status  # noqa: E402
from rest_framework.exceptions import APIException  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework_simplejwt.views import TokenObtainPairView  # noqa: E402


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """``/api/token/`` under the same limits as the login page (it is the same password check)."""

    def post(self, request, *args, **kwargs):
        username = str(request.data.get('username', ''))[:150] if hasattr(request.data, 'get') else ''
        if is_locked(request, username):
            return Response({'detail': LOCKED_MESSAGE}, status=_status.HTTP_429_TOO_MANY_REQUESTS)
        try:
            response = super().post(request, *args, **kwargs)
        except APIException as exc:   # simplejwt raises AuthenticationFailed for a wrong password
            if exc.status_code in (400, 401):
                record_failure(request, username)
            raise
        if response.status_code == 200:
            record_success(username)
            from schools.models import AccountProfile   # lazy: keeps this module importable by config.urls early
            if AccountProfile.objects.filter(user__username=username, must_change_password=True).exists():
                # a generated initial password may not mint tokens: change it on the web page first
                return Response({'detail': 'password change required'}, status=_status.HTTP_403_FORBIDDEN)
        elif response.status_code in (400, 401):
            record_failure(request, username)
        return response
