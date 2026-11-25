"""JSON platform summary for the Platform Admin (Ministry) view in the presentation frontends.

``GET /api/platform/global-stats/`` returns aggregate, platform-wide figures only — total schools,
active users by role and the number of schools with each sellable module active. It never returns a
school name, a personal name, a national id or any student record; the calling user's scope is the
whole platform, so this endpoint is gated to platform operators exactly like the Django admin
(superuser or an active staff account in ``PlatformAdmin``; ``dashboard/operator_page.py``).

Unlike ``operator_page.overview`` (which shows one row per school and is therefore audit-logged per
school), this view shows only totals, so there is no school-scoped event to write.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from schools.entitlements import MODULES, module_enabled
from schools.models import School
from students.access import (
    ADMIN,
    COUNSELOR,
    GRADE_LEAD,
    PARENT,
    PLATFORM_ADMIN,
    STUDENT,
    TEACHER,
)

from .module_info import label as module_label
from .operator_page import is_platform_operator

User = get_user_model()

# Display order and labels for the role breakdown shown to the ministry.
ROLE_LABELS = (
    (ADMIN, "مدیر مدرسه"),
    (TEACHER, "معلم"),
    (GRADE_LEAD, "مربی پایه"),
    (COUNSELOR, "مشاور"),
    (PARENT, "والدین"),
    (STUDENT, "دانش‌آموز"),
    (PLATFORM_ADMIN, "مدیر سامانه"),
)

FORBIDDEN = {"detail": "دسترسی به این گزارش برای شما مجاز نیست."}


def build_global_stats():
    """Aggregate counters only; no names, no ids, no student data."""
    schools = School.objects.order_by("pk")
    schools_total = schools.count()

    users_by_role = []
    for role, label in ROLE_LABELS:
        count = User.objects.filter(is_active=True, groups__name=role).distinct().count()
        users_by_role.append({"role": role, "label": label, "count": count})

    modules = []
    for key in MODULES:
        active_schools = sum(1 for school in schools if module_enabled(school, key))
        modules.append({"key": key, "label": module_label(key), "active_schools": active_schools})

    return {
        "generated_at": timezone.now().isoformat(),
        "schools_total": schools_total,
        "users_total": User.objects.filter(is_active=True).count(),
        "users_by_role": users_by_role,
        "modules": modules,
    }


class PlatformGlobalStatsView(APIView):
    authentication_classes = (JWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not is_platform_operator(request.user):
            return Response(FORBIDDEN, status=status.HTTP_403_FORBIDDEN)
        return Response(build_global_stats())
