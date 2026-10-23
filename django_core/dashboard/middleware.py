"""Forced password change: an authenticated account flagged ``must_change_password`` (generated initial password) can
reach only the password-change page, logout and static files until it has chosen its own password."""
from django.shortcuts import redirect
from django.urls import reverse

from schools.models import AccountProfile


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not request.path.startswith('/static/'):
            allowed = {reverse('dashboard:password_change'), reverse('dashboard:logout')}
            if request.path not in allowed and AccountProfile.objects.filter(
                    user_id=user.pk, must_change_password=True).exists():
                return redirect('dashboard:password_change')
        return self.get_response(request)
