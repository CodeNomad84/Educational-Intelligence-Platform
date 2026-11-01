"""Django admin = platform operators only (C-A, S9; decision pack 0028 P3-10).

Only an active staff account that is a superuser or a PlatformAdmin opens the admin, and it shows platform tables only:
schools, school modules, memberships, groups and user accounts that are not school accounts. School data (students, classes,
teacher and grade-lead assignments, academic years, staff links) is managed on the SchoolAdmin pages under ``/school/``, which
apply the school scopes; it is not registered here. No permissions are granted here. The school record is superuser-only to
add/delete and its key is read-only for everyone else.
"""
from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm

from .models import AuditEvent, School, SchoolMembership, SchoolModule


def _is_platform_operator(user):
    """Superuser or PlatformAdmin (active staff). A SchoolAdmin is never one: module rows and AI caps are theirs to see, not to set."""
    from students.access import PLATFORM_ADMIN

    return bool(user.is_active and user.is_staff and (user.is_superuser or user.groups.filter(name=PLATFORM_ADMIN).exists()))


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_at")
    search_fields = ("name", "code")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        from . import audit

        super().save_model(request, obj, form, change)
        if not change:
            audit.record(request.user, audit.SCHOOL_CREATE, obj, school=obj, detail='admin')

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and not request.user.is_superuser:
            fields = tuple(fields) + ("code",)
        if not _is_platform_operator(request.user):
            fields = tuple(fields) + ("ai_daily_cap", "ai_monthly_cap")   # call caps: platform admin only
        return fields


def _platform_level(request):
    """Superuser or a member of the ``PlatformAdmin`` group (ADR-0012). A SchoolAdmin never qualifies."""
    from students.access import PLATFORM_ADMIN

    user = request.user
    return bool(user.is_active and (user.is_superuser or user.groups.filter(name=PLATFORM_ADMIN).exists()))


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    """Memberships are managed at platform level only (superuser or PlatformAdmin), and only when the account also
    holds the normal Django model permission. Stage S1: the row changes no access."""

    list_display = ("user", "school", "is_active", "created_by", "created_at")
    list_filter = ("school", "is_active")
    search_fields = ("user__username", "school__name", "school__code")
    readonly_fields = ("created_by", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        # The user of an existing row is fixed (review finding G3): a row whose user no longer qualifies must stay
        # deactivatable, and the picker (eligible users only) cannot show it.
        fields = tuple(super().get_readonly_fields(request, obj))
        return fields + ("user",) if obj is not None else fields

    def has_module_permission(self, request):
        return _platform_level(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return _platform_level(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return _platform_level(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return _platform_level(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return _platform_level(request) and super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from students.access import ADMIN, PLATFORM_ADMIN

        if db_field.name == "user":
            kwargs["queryset"] = (
                get_user_model().objects
                .filter(is_active=True, is_superuser=False, groups__name=ADMIN)
                .exclude(groups__name=PLATFORM_ADMIN)  # separation of duties (F1)
                .order_by("username")
                .distinct()
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only for everyone (the platform account too); the school's SchoolAdmin reads it in the dashboard."""
    list_display = ("created_at", "username", "school", "action", "object_type", "object_id")
    list_filter = ("school", "action")

    def has_module_permission(self, request):
        return False   # not offered in the admin index; the content is school data, read in the dashboard

    def has_view_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SchoolModule)
class SchoolModuleAdmin(admin.ModelAdmin):
    """Module entitlements. Only a platform admin (superuser / PlatformAdmin) may see, create or extend rows; never a
    SchoolAdmin. No deletes (end a row with ends_on instead). Every save is audit-logged. A trial is unique per
    (school, module): extending it means editing its ends_on."""

    list_display = ("school", "module_key", "kind", "starts_on", "ends_on")
    list_filter = ("kind", "module_key", "school")

    def has_module_permission(self, request):
        return _is_platform_operator(request.user)

    has_view_permission = has_add_permission = has_change_permission = lambda self, request, obj=None: _is_platform_operator(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        from .entitlements import MODULES

        if db_field.name == "module_key":
            return forms.ChoiceField(choices=[(k, k) for k in MODULES], label=db_field.verbose_name)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        return ("school", "module_key", "kind", "starts_on") if obj is not None else ()

    def save_model(self, request, obj, form, change):
        from . import audit
        from .entitlements import module_change_detail

        super().save_model(request, obj, form, change)
        audit.record(request.user, audit.MODULE_CHANGE, obj, school=obj.school, detail=module_change_detail(obj))


# --- C-A: the admin site itself is closed to everyone but platform operators ----------------------------------------------
def _admin_site_permission(request):
    """Only an active staff superuser or PlatformAdmin opens the admin; a plain staff account or a school account does not."""
    return _is_platform_operator(request.user)


admin.site.has_permission = _admin_site_permission


def _school_role_names():
    from students.access import COUNSELOR, GRADE_LEAD, PARENT, STUDENT, TEACHER

    return (TEACHER, GRADE_LEAD, COUNSELOR, PARENT, STUDENT)


class PlatformUserChangeForm(UserChangeForm):
    """A staff or superuser account can not hold a school role, and a school account can not become staff (P3-10)."""

    def clean(self):
        from students.access import ADMIN

        cleaned = super().clean()
        privileged = cleaned.get('is_staff') or cleaned.get('is_superuser')
        groups = {g.name for g in cleaned.get('groups') or []}
        if privileged and groups & {ADMIN, *_school_role_names()}:
            raise forms.ValidationError('حساب کارکنِ پلتفرم (staff یا superuser) نمی‌تواند نقش مدرسه داشته باشد؛ '
                                        'حساب‌های مدرسه هرگز staff نیستند.')
        return cleaned


class PlatformUserAdmin(DjangoUserAdmin):
    """User accounts: platform accounts, SchoolAdmins and accounts without a role yet. Accounts that only hold a school role
    (Teacher, GradeLead, Counselor, Parent, Student; usernames are often national ids) are never listed, searched or opened
    here; the SchoolAdmin manages them on the school pages."""

    form = PlatformUserChangeForm

    def get_queryset(self, request):
        from students.access import ADMIN, PLATFORM_ADMIN

        User = get_user_model()
        school_only = (User.objects.filter(groups__name__in=_school_role_names(), is_staff=False, is_superuser=False)
                       .exclude(groups__name__in=(ADMIN, PLATFORM_ADMIN)))
        return super().get_queryset(request).exclude(pk__in=school_only.values('pk'))


admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), PlatformUserAdmin)
