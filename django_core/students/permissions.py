# students/permissions.py
from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    اجازه دسترسی فقط به کاربرانی که در گروه Admin هستند یا Superuser هستند.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (
                request.user.is_superuser or  # ✅ اضافه کردن این خط
                request.user.groups.filter(name='Admin').exists()
            )
        )

    def has_permission(self, request, view):
        
        return request.user and request.user.is_authenticated and request.user.groups.filter(name='Admin').exists()

class IsTeacherUser(permissions.BasePermission):
    """فقط کاربرانی که در گروه Teacher هستند"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.groups.filter(name='Teacher').exists()

class IsParentUser(permissions.BasePermission):
    """فقط کاربرانی که در گروه Parent هستند"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.groups.filter(name='Parent').exists()

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    دسترسی کامل برای Admin، بقیه فقط خواندنی (مخصوص معلم و والدین)
    """
    def has_permission(self, request, view):
        # درخواست‌های امن (GET, HEAD, OPTIONS) همیشه مجاز هستند
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        # متدهای غیرامن (POST, PUT, DELETE) فقط برای Admin
        return request.user and request.user.is_authenticated and request.user.groups.filter(name='Admin').exists()