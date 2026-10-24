# students/permissions.py
from rest_framework import permissions

from schools.entitlements import module_enabled, module_enabled_for_user

from .access import ADMIN, PARENT, TEACHER, has_any_role

class IsAdminUser(permissions.BasePermission):
    """School administrators (group SchoolAdmin, or the temporary superuser mapping) through the role check, so an
    inactive account is refused (``roles_for`` is empty for it)."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and has_any_role(request.user, ADMIN))

class IsTeacherUser(permissions.BasePermission):
    """فقط کاربرانی که در گروه Teacher هستند"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.groups.filter(name=TEACHER).exists()

class IsParentUser(permissions.BasePermission):
    """فقط کاربرانی که در گروه Parent هستند"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.groups.filter(name=PARENT).exists()

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    دسترسی کامل برای Admin، بقیه فقط خواندنی (مخصوص معلم و والدین)
    """
    def has_permission(self, request, view):
        # درخواست‌های امن (GET, HEAD, OPTIONS) همیشه مجاز هستند
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        # متدهای غیرامن (POST, PUT, DELETE) فقط برای Admin
        return request.user and request.user.is_authenticated and request.user.groups.filter(name=ADMIN).exists()

class ModuleRequired(permissions.BasePermission):
    """Entitlement gate. The view declares ``module_by_action = {'action_name': 'module_key'}``; actions not listed are
    not gated. Request level: the module is on for one of the user's schools; object level (``get_object``): on for the
    object's school. Disabled = 403 (data retained)."""

    def has_permission(self, request, view):
        key = getattr(view, 'module_by_action', {}).get(getattr(view, 'action', None))
        return key is None or module_enabled_for_user(request.user, key)

    def has_object_permission(self, request, view, obj):
        key = getattr(view, 'module_by_action', {}).get(getattr(view, 'action', None))
        return key is None or module_enabled(getattr(obj, 'school_id', None), key)
