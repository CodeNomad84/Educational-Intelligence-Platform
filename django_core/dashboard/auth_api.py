"""JSON session authentication for the two presentation frontends (ADR-0014, docs/changes/0040).

Four endpoints under ``/api/auth/``: ``csrf/``, ``login/``, ``logout/``, ``me/``.

* Credentials are checked with ``authenticate()`` under the **existing** login throttle (``dashboard/throttle.py``), so a
  guess against this endpoint costs exactly as much as a guess against the HTML page or ``/api/token/``.
* A successful login creates an ordinary Django session (the cookie the HTML pages already use); a client therefore sends
  ``credentials: 'include'`` and no token storage exists in the browser.
* ``POST`` is CSRF-protected. ``APIView`` is ``csrf_exempt`` inside Django's middleware chain, so ``login/`` restores the
  check explicitly; ``logout/`` and ``me/`` get it from DRF's ``SessionAuthentication`` (a JWT client is not forced to
  carry a CSRF cookie).
* Error bodies keep DRF's ``{"detail": "…"}`` shape so a client can share one handler with ``/api/token/``.
* No national id, mobile number or note is ever part of a response (proposal §4.3).
"""
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from schools.models import AccountProfile

from . import throttle

BAD_CREDENTIALS = 'نام کاربری یا رمز عبور اشتباه است.'      # one sentence for unknown user, wrong password and inactive
MISSING_FIELDS = 'نام کاربری و رمز عبور الزامی است.'
PASSWORD_CHANGE_REQUIRED = {'detail': 'password change required', 'code': 'password_change_required'}


class SchoolSelectionError(Exception):
    """``?school=`` named a school the user does not belong to (proposal §4.3, D6)."""


def _display_name(user):
    return user.get_full_name().strip() or user.username


def _chosen_school(request, school_ids):
    """``(schools, school)`` for the response. ``school`` is only set when the choice is unambiguous: one membership, or an
    explicit validated ``?school=<id>``. A multi-school user without a choice gets ``null`` rather than ``first()``,
    which would silently show the wrong school's data."""
    from schools.models import School

    schools = [{'id': row.id, 'name': row.name}
               for row in School.objects.filter(id__in=school_ids).order_by('name')]
    raw = (request.query_params.get('school') or '').strip()
    if raw:
        if not raw.isdigit() or int(raw) not in school_ids:
            raise SchoolSelectionError('این مدرسه در دسترسی شما نیست.')
        return schools, next(row for row in schools if row['id'] == int(raw))
    return schools, (schools[0] if len(schools) == 1 else None)


def profile_payload(request, user):
    """The ``/api/auth/me/`` contract (proposal §4.3). Every value is derived from an existing accessor; no new rule."""
    from dashboard.context_processors import ROLE_LABELS
    from dashboard.operator_page import is_platform_operator
    from schools.entitlements import enabled_modules_for_user, user_school_ids
    from students.access import roles_for

    roles = roles_for(user)
    operator = is_platform_operator(user)
    schools, school = _chosen_school(request, user_school_ids(user))
    return {
        'id': user.pk,
        'username': user.get_username(),
        'display_name': _display_name(user),
        'roles': sorted(roles),
        'role': next((name for name, _label in ROLE_LABELS if name in roles),
                     'PlatformAdmin' if operator else None),
        'schools': schools,
        'school': school,
        'modules': sorted(enabled_modules_for_user(user)),
        'is_platform_operator': operator,
        'must_change_password': AccountProfile.objects.filter(user_id=user.pk, must_change_password=True).exists(),
        # D5: neither exists in the schema and neither is inferred from a school name or the students in it.
        'gender_scope': None,
        'theme': None,
    }


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    """Hands the browser the ``csrftoken`` cookie it must echo in ``X-CSRFToken`` on login/logout."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        response = Response({'csrfToken': get_token(request)})
        response['Cache-Control'] = 'no-store'
        return response


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    authentication_classes = ()          # no BasicAuthentication: no password on every request, no bypass of the throttle
    permission_classes = (AllowAny,)

    def post(self, request):
        payload = request.data if hasattr(request.data, 'get') else {}   # a JSON array/string is a 400, never a 500
        username = str(payload.get('username') or '').strip()[:150]      # same truncation as the throttle and the JWT view
        password = payload.get('password')
        if not username or not isinstance(password, str) or not password:
            return Response({'detail': MISSING_FIELDS}, status=status.HTTP_400_BAD_REQUEST)
        if throttle.is_locked(request, username):
            return Response({'detail': throttle.LOCKED_MESSAGE}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = authenticate(request, username=username, password=password)
        if user is None:
            throttle.record_failure(request, username)
            return Response({'detail': BAD_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED)
        throttle.record_success(username)
        if AccountProfile.objects.filter(user_id=user.pk, must_change_password=True).exists():
            # a generated initial password may not open a session (same rule as /api/token/, dashboard/throttle.py)
            return Response(PASSWORD_CHANGE_REQUIRED, status=status.HTTP_403_FORBIDDEN)
        login(request, user)             # rotates the session key; never set _auth_user_id by hand
        return Response(profile_payload(request, user))


class LogoutView(APIView):
    authentication_classes = (JWTAuthentication, SessionAuthentication)   # SessionAuthentication enforces CSRF here
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    # JWT first on purpose: DRF answers 401 only when the first authenticator advertises a challenge, and the contract
    # (proposal §7) is 401 for an anonymous caller, not the 403 SessionAuthentication alone would produce.
    authentication_classes = (JWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            return Response(profile_payload(request, request.user))
        except SchoolSelectionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


urlpatterns = [
    path('csrf/', CsrfView.as_view(), name='auth_csrf'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('me/', MeView.as_view(), name='auth_me'),
]
