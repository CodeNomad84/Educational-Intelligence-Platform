"""Where a user lands after login (and from the dashboard root): by role, deny-by-default for unknown roles."""
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PARENT, STUDENT, TEACHER, roles_for


def home_url_for(user):
    """SchoolAdmin -> /school/, Teacher -> /teacher/, Grade Lead -> /grade/, Parent -> /students/; the platform superuser
    -> /admin/, a PlatformAdmin -> /platform/modules/. Counselor -> /counselor/."""
    if user.is_superuser and user.is_active:
        return '/admin/'
    roles = roles_for(user)
    if ADMIN in roles:
        return reverse('dashboard:school_home')
    if COUNSELOR in roles:
        return reverse('dashboard:counselor_home')
    if TEACHER in roles:
        return reverse('dashboard:teacher_home')
    if GRADE_LEAD in roles:   # the dashboard of the own grade(s); the student list stays one click away
        return reverse('dashboard:grade_dashboard')
    if PARENT in roles:
        return reverse('dashboard:student_list')
    if STUDENT in roles:
        return reverse('dashboard:me_home')
    from .operator_page import is_platform_operator   # lazy: operator_page imports the dashboard layer
    if is_platform_operator(user):                    # a PlatformAdmin (staff) has no school home: the overview is its page
        return reverse('dashboard:operator_overview')
    return reverse('dashboard:login')


def safe_next(request):
    """The ``next`` target (POST or GET) when it is a same-host URL, else ``None``."""
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return None
