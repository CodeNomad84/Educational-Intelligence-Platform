"""Role gate for dashboard views (server-side, deny by default).

Anonymous users are redirected to login; authenticated users without one of the allowed
roles get HTTP 403. Roles come from students/access.py.
"""
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from schools.entitlements import module_enabled, module_enabled_for_user
from students.access import has_any_role


def require_module(school, key):
    """Object-level module gate: 403 unless ``school`` (a School or id) has ``key`` on today."""
    if not module_enabled(school, key):
        raise PermissionDenied


def role_required(*roles, module=None):
    """``module``: optional entitlement key (schools/entitlements.py); the user needs it on in at least one of their
    schools. Views that load an object must also call ``require_module(obj.school_id, key)``."""
    def decorator(view):
        @login_required
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not has_any_role(request.user, *roles):
                raise PermissionDenied
            if module is not None and not module_enabled_for_user(request.user, module):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator


def require_pilot_flag(flag):
    """Pilot config gate (T6): raise PermissionDenied (403) unless the Django setting ``flag`` is
    truthy. Read at request time via ``getattr(settings, flag)`` so ``override_settings`` works in
    tests. Stack it *inside* ``role_required`` so anonymous users still get the login redirect and
    role checks run before the flag."""
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not getattr(settings, flag, False):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator
