"""Login throttle (brute force): usernames are national ids, i.e. guessable, so failed sign-ins are counted per username AND
per client address in Django's cache (Redis in production, so the count is shared by all workers; in development the
per-process memory cache, which is enough for a single process). No extra dependency.

* ``LOGIN_MAX_FAILURES_USER`` (5) failures for one username inside ``LOGIN_WINDOW_SECONDS`` (900) lock that username for the
  rest of the window; ``LOGIN_MAX_FAILURES_IP`` (20) failures from one address lock the address.
* A locked username or address is refused WITHOUT checking the password, with the same answer whether or not the account exists
  (no enumeration). A success clears the username counter (not the address counter).
* The address is ``REMOTE_ADDR`` unless ``THROTTLE_TRUSTED_PROXIES`` is set (see ``client_ip``); ``X-Forwarded-For`` is never trusted by
  default. Behind a reverse proxy without that setting every user would share the proxy's counter (RUNBOOK).
* Locking a username also locks the real owner for the window: the price of protecting guessable usernames. A SchoolAdmin
  cannot unlock; waiting out the window or a platform administrator clearing the cache are the ways out.
"""
import hashlib
import ipaddress

from django.conf import settings
from django.core.cache import cache

LOCKED_MESSAGE = 'تلاش‌های ناموفق بیش از حد مجاز بود؛ چند دقیقه بعد دوباره تلاش کنید.'


def _limits():
    return (getattr(settings, 'LOGIN_MAX_FAILURES_USER', 5), getattr(settings, 'LOGIN_MAX_FAILURES_IP', 20),
            getattr(settings, 'LOGIN_WINDOW_SECONDS', 900))


def _key(kind, value):
    return 'login-throttle:%s:%s' % (kind, hashlib.sha256((value or '').strip().lower().encode()).hexdigest()[:32])


def _network(text):
    try:
        return ipaddress.ip_network(str(text).strip(), strict=False)
    except ValueError:
        return None


def _trusted_networks():
    return [n for n in map(_network, getattr(settings, 'THROTTLE_TRUSTED_PROXIES', ()) or ()) if n is not None]


def client_ip(request):
    """The address the limits are counted for. Default: ``REMOTE_ADDR`` and nothing else. With ``THROTTLE_TRUSTED_PROXIES`` set AND
    ``REMOTE_ADDR`` inside one of those networks, the client is the right-most ``X-Forwarded-For`` entry that is not itself a trusted
    proxy (entries to its left are client-controlled and ignored). A missing or malformed header, or a request that does not come
    from a trusted proxy, falls back to ``REMOTE_ADDR``."""
    remote = request.META.get('REMOTE_ADDR', '')
    trusted = _trusted_networks()
    if not trusted:
        return remote
    try:
        peer = ipaddress.ip_address(remote)
    except ValueError:
        return remote
    if not any(peer in net for net in trusted):
        return remote
    for raw in reversed([p.strip() for p in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if p.strip()]):
        try:
            hop = ipaddress.ip_address(raw)
        except ValueError:
            return remote                                  # malformed chain: do not guess
        if not any(hop in net for net in trusted):
            return str(hop)
    return remote


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


def clear(username):
    """Forget the failed attempts of a username (after a password reset); the address counters are not touched."""
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


def throttled_admin_login(original):
    """Wrap ``admin.site.login`` with the same limits (shared counters with ``/login/``): a locked username or address is
    refused before the password is looked at; a re-rendered form (HTTP 200 after a POST) counts as a failure, a redirect as a
    success. Installed in ``config/urls.py``."""
    from functools import wraps

    from django.http import HttpResponse

    @wraps(original)
    def login(request, *args, **kwargs):
        if request.method != 'POST':
            return original(request, *args, **kwargs)
        username = str(request.POST.get('username', ''))[:150]
        if is_locked(request, username):
            return HttpResponse(LOCKED_MESSAGE, status=429, content_type='text/plain; charset=utf-8')
        response = original(request, *args, **kwargs)
        if response.status_code == 200:
            record_failure(request, username)
        elif response.status_code in (301, 302):
            record_success(username)
        return response
    return login
