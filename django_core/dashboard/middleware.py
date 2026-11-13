"""Forced password change: an authenticated account flagged ``must_change_password`` (generated initial password) can
reach only the password-change page, logout and static files until it has chosen its own password.

Since ADR-0014 (docs/changes/0040 §4.4) an ``/api/…`` request is answered with a JSON 403 instead of an HTML redirect: a
fetch/XHR client cannot follow a 302 to a page, and a silent redirect looked like success. ``/api/auth/`` login, csrf and
logout stay reachable so a flagged account can still sign in and out.
"""
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from schools.models import AccountProfile

PASSWORD_CHANGE_REQUIRED = {'detail': 'password change required', 'code': 'password_change_required'}
API_REACHABLE_WHEN_FLAGGED = ('/api/auth/login/', '/api/auth/csrf/', '/api/auth/logout/')


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not request.path.startswith('/static/'):
            allowed = {reverse('dashboard:password_change'), reverse('dashboard:logout')}
            if (request.path not in allowed and not request.path.startswith(API_REACHABLE_WHEN_FLAGGED)
                    and AccountProfile.objects.filter(user_id=user.pk, must_change_password=True).exists()):
                if request.path.startswith('/api/'):
                    return JsonResponse(PASSWORD_CHANGE_REQUIRED, status=403)
                return redirect('dashboard:password_change')
        return self.get_response(request)

