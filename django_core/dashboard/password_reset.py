"""Password reset by a Grade Lead (only when the school allows it) or by the SchoolAdmin.

* The reset sets a RANDOM temporary password (``bulk_accounts.new_password``; nobody chooses it), flags the account
  ``must_change_password`` and clears its failed-login counter. The password is shown once in the response of the POST and
  is never stored, logged, audited or put in a message. Existing sessions of the account end (the session hash changes).
* Grade Lead: only Student / Parent accounts linked to students of the Grade Lead's OWN grade and school
  (``access.grade_lead_students``), in a school whose ``grade_leads_may_reset_passwords`` is on. A parent is reset only if ALL
  of the parent's children are in that scope. Never the actor, never an inactive, staff, superuser, school-staff,
  membership or dual-role account (the account must hold exactly the group Student or exactly the group Parent, which also excludes every SchoolAdmin). Targets
  outside the scope are 404 (nothing about them is revealed); in-scope but ineligible targets are 403. At most
  ``HOURLY_CAP`` resets per Grade Lead per hour; the refusal is audit-logged (``password_reset_capped``) for the SchoolAdmin.
* SchoolAdmin: any Student / Parent / staff account of the own school except itself, inactive, staff/superuser and
  SchoolAdmin / PlatformAdmin accounts; a parent with children in another school is a 404.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from schools import audit
from schools.models import AccountProfile, AuditEvent, School, SchoolStaff
from students.access import ADMIN, GRADE_LEAD, PARENT, PLATFORM_ADMIN, STUDENT, grade_lead_students
from students.models import Student

from . import throttle
from .bulk_accounts import new_password
from .decorators import role_required
from .school_views import _render, school_page

User = get_user_model()
HOURLY_CAP = 20


def _groups(user):
    return set(user.groups.values_list('name', flat=True))


def _ineligible_for_gradelead(actor, target):
    """Reason string if an in-scope target may not be reset by a Grade Lead, else ''."""
    if target.pk == actor.pk:
        return 'self'
    if not target.is_active:
        return 'inactive'
    if target.is_staff or target.is_superuser:
        return 'staff'
    if SchoolStaff.objects.filter(user=target).exists():
        return 'staff'
    if _groups(target) not in ({STUDENT}, {PARENT}):
        return 'dual-role'
    return ''


def _ineligible_for_admin(actor, target):
    if target.pk == actor.pk:
        return 'self'
    if not target.is_active:
        return 'inactive'
    if target.is_staff or target.is_superuser or _groups(target) & {ADMIN, PLATFORM_ADMIN}:
        return 'staff'
    return ''


def _result(request, target, password, kind):
    response = render(request, 'dashboard/reset_result.html', {
        'target': target, 'password': password, 'is_parent': kind == 'parent', 'back': request.POST.get('back', '')})
    response['Cache-Control'] = 'no-store'
    return response


def _do_reset(actor, target, school, who):
    password = new_password()
    with transaction.atomic():
        target.set_password(password)
        target.save(update_fields=['password'])
        profile, _created = AccountProfile.objects.get_or_create(user=target)
        AccountProfile.objects.filter(pk=profile.pk).update(must_change_password=True)
        throttle.clear(target.username)
        audit.record(actor, audit.PASSWORD_RESET, target, school=school, detail=who)
    return password


# --- Grade Lead -----------------------------------------------------------------------------------------------------
def _gradelead_scope(request):
    """Students the Grade Lead may reset the accounts of: own grade, in schools where the SchoolAdmin allowed it. 403 if none."""
    on = School.objects.filter(pk__in=grade_lead_students(request.user).values('school_id'),
                               grade_leads_may_reset_passwords=True)
    if not on.exists():
        raise PermissionDenied
    return grade_lead_students(request.user).filter(school__in=on)


@role_required(GRADE_LEAD)
def grade_resets(request):
    scope = _gradelead_scope(request)
    rows = []
    for student in scope.select_related('student_user', 'parent_user', 'school_class').order_by(
            'class_name', 'last_name', 'first_name'):
        rows.append({'student': student,
                     'student_ok': student.student_user_id and not _ineligible_for_gradelead(request.user, student.student_user),
                     'parent_ok': student.parent_user_id and not _ineligible_for_gradelead(request.user, student.parent_user)})
    return render(request, 'dashboard/reset_grade.html', {'rows': rows})


@role_required(GRADE_LEAD)
@require_POST
def grade_reset(request, pk):
    scope = _gradelead_scope(request)
    linked = scope.filter(Q(student_user_id=pk) | Q(parent_user_id=pk))
    first = linked.select_related('student_user', 'parent_user').first()
    if first is None:
        raise Http404
    if Student.objects.filter(parent_user_id=pk).exclude(pk__in=scope.values('pk')).exists():
        raise Http404   # a parent with a child outside the own grade / school: not resettable here, and nothing is revealed
    target = first.student_user if first.student_user_id == pk else first.parent_user
    reason = _ineligible_for_gradelead(request.user, target)
    if reason:
        raise PermissionDenied
    since = timezone.now() - timedelta(hours=1)
    if AuditEvent.objects.filter(user=request.user, action=audit.PASSWORD_RESET, created_at__gte=since).count() >= HOURLY_CAP:
        audit.record(request.user, audit.PASSWORD_RESET_CAPPED, target, school=first.school_id)
        response = HttpResponse('Too many resets this hour; the SchoolAdmin has been notified.', status=429,
                                content_type='text/plain; charset=utf-8')
        return response
    password = _do_reset(request.user, target, first.school_id, 'gradelead')
    return _result(request, target, password, 'student' if first.student_user_id == pk else 'parent')


# --- SchoolAdmin ----------------------------------------------------------------------------------------------------
def _admin_candidates(school):
    return User.objects.filter(Q(student_profile__school=school) | Q(children__school=school)
                               | Q(school_staff__school=school)).distinct()


@school_page
def admin_resets(request, school):
    q = (request.GET.get('q') or '').strip()
    people = _admin_candidates(school).exclude(pk=request.user.pk).filter(is_active=True, is_staff=False, is_superuser=False) \
        .exclude(groups__name__in=(ADMIN, PLATFORM_ADMIN))
    if q:
        people = people.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return _render(request, school, 'resets.html', people=people.order_by('last_name', 'username')[:200], q=q,
                   setting=school.grade_leads_may_reset_passwords)


@school_page
@require_POST
def admin_reset(request, school, pk):
    target = _admin_candidates(school).filter(pk=pk).first()
    if target is None or Student.objects.filter(parent_user=target).exclude(school=school).exists():
        raise Http404
    if _ineligible_for_admin(request.user, target):
        raise PermissionDenied
    password = _do_reset(request.user, target, school, 'admin')
    return _result(request, target, password, 'parent' if PARENT in _groups(target) else 'other')


@school_page
@require_POST
def admin_reset_setting(request, school):
    enabled = request.POST.get('enabled') == 'on'
    if enabled != school.grade_leads_may_reset_passwords:
        School.objects.filter(pk=school.pk).update(grade_leads_may_reset_passwords=enabled)
        audit.record(request.user, audit.RESET_SETTING_CHANGE, school, school=school, detail='on' if enabled else 'off')
    messages.success(request, 'تنظیم ذخیره شد.')
    return redirect('dashboard:school_resets')
