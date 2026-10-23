"""Where a user lands after login (and from the dashboard root): by role, deny-by-default for unknown roles."""
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from students.access import ADMIN, COUNSELOR, GRADE_LEAD, PARENT, STUDENT, TEACHER, roles_for


def home_url_for(user):
    """SchoolAdmin -> /school/, Teacher -> /teacher/, Grade Lead and Parent -> their student list; the platform superuser
    -> /admin/. Counselor -> /counselor/."""
    if user.is_superuser and user.is_active:
        return '/admin/'
    roles = roles_for(user)
    if ADMIN in roles:
        return reverse('dashboard:school_home')
    if COUNSELOR in roles:
        return reverse('dashboard:counselor_home')
    if TEACHER in roles:
        return reverse('dashboard:teacher_home')
    if GRADE_LEAD in roles:   # the list of the own grade (first active assignment); without one the plain list
        from schools.models import GradeLeadAssignment
        grade = GradeLeadAssignment.objects.filter(user=user, is_active=True).order_by('grade').values_list(
            'grade', flat=True).first()
        return reverse('dashboard:student_list') + (f'?grade={grade}' if grade else '')
    if PARENT in roles:
        return reverse('dashboard:student_list')
    if STUDENT in roles:
        return reverse('dashboard:me_home')
    return reverse('dashboard:login')


def safe_next(request):
    """The ``next`` target (POST or GET) when it is a same-host URL, else ``None``."""
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return None
