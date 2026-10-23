"""Where a user lands after login (and from the dashboard root): by role, deny-by-default for unknown roles."""
from django.conf import settings
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from students.access import ADMIN, GRADE_LEAD, PARENT, TEACHER, roles_for


def home_url_for(user):
    """SchoolAdmin -> /school/, Teacher -> /teacher/, Grade Lead and Parent -> their student list; the platform superuser
    -> /admin/. (Counselor has no role yet; the demo counselor account is a SchoolAdmin and lands on its demo page.)"""
    if user.is_superuser and user.is_active:
        return '/admin/'
    roles = roles_for(user)
    # DEMO SCOPE begin — the demo counselor account uses the SchoolAdmin role; its existing home is the counselor view
    if getattr(settings, 'DEMO_MODE', False) and ADMIN in roles and user.username == 'demo_counselor':
        return reverse('dashboard:demo_counselor')
    # DEMO SCOPE end
    if ADMIN in roles:
        return reverse('dashboard:school_home')
    if TEACHER in roles:
        return reverse('dashboard:teacher_home')
    if roles & {GRADE_LEAD, PARENT}:
        return reverse('dashboard:student_list')
    return reverse('dashboard:login')


def safe_next(request):
    """The ``next`` target (POST or GET) when it is a same-host URL, else ``None``."""
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return None
