"""Role gate for dashboard views (server-side, deny by default).

Anonymous users are redirected to login; authenticated users without one of the allowed
roles get HTTP 403. Roles come from students/access.py.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from students.access import has_any_role


def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not has_any_role(request.user, *roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator
