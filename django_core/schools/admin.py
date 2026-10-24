"""Admin for School, SchoolClass, TeacherAssignment (proposal 0002, C1) and GradeLeadAssignment (C4b).

No permissions are granted here (C4 does that explicitly). The code only narrows what the admin offers:
the school record is superuser-only to add/delete and its key is read-only for everyone else, and only
eligible users can be picked as teacher.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model

from .models import (
    AcademicYear, AuditEvent, GradeLeadAssignment, School, SchoolClass, SchoolMembership, SchoolModule, SchoolStaff,
    TeacherAssignment)


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

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and not request.user.is_superuser:
            fields = tuple(fields) + ("code",)
        if not _is_platform_operator(request.user):
            fields = tuple(fields) + ("ai_daily_cap", "ai_monthly_cap")   # call caps: platform admin only
        return fields


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("title", "academic_year", "grade", "school", "is_active")
    list_filter = ("school", "is_active", "academic_year", "grade")
    search_fields = ("title",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ("teacher", "school_class", "subject", "created_by", "created_at")
    list_filter = ("school_class__school", "school_class__is_active")
    search_fields = ("teacher__username", "school_class__title", "subject")
    readonly_fields = ("created_by", "created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from students.access import TEACHER

        if db_field.name == "teacher":
            kwargs["queryset"] = (
                get_user_model().objects
                .filter(is_active=True, is_staff=False, is_superuser=False, groups__name=TEACHER)
                .order_by("username")
                .distinct()
            )
        elif db_field.name == "school_class":
            kwargs["queryset"] = SchoolClass.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class GradeLeadAssignmentForm(forms.ModelForm):
    """Academic year is picked from the years already used by classes (no free-text typos)."""

    academic_year = forms.ChoiceField(label="سال تحصیلی")

    class Meta:
        model = GradeLeadAssignment
        fields = ("user", "school", "grade", "academic_year", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        years = set(
            SchoolClass.objects.exclude(academic_year="").values_list("academic_year", flat=True).distinct())
        if self.instance.pk and self.instance.academic_year:
            years.add(self.instance.academic_year)  # keep an existing value selectable
        self.fields["academic_year"].choices = [("", "---------")] + [(y, y) for y in sorted(years)]


@admin.register(GradeLeadAssignment)
class GradeLeadAssignmentAdmin(admin.ModelAdmin):
    form = GradeLeadAssignmentForm
    list_display = ("user", "school", "grade", "academic_year", "is_active", "created_by", "created_at")
    list_filter = ("school", "grade", "academic_year", "is_active")
    search_fields = ("user__username",)
    readonly_fields = ("created_by", "created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from students.access import GRADE_LEAD

        if db_field.name == "user":
            kwargs["queryset"] = (
                get_user_model().objects
                .filter(is_active=True, is_staff=False, is_superuser=False, groups__name=GRADE_LEAD)
                .order_by("username")
                .distinct()
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        warning = obj.year_warning()
        if warning:
            messages.warning(request, warning)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    """SchoolAdmin enters the year code and its dates (ADR-0011); nothing reads this table for access yet."""

    list_display = ("code", "school", "start_date", "end_date", "is_current")
    list_filter = ("school", "is_current")
    search_fields = ("code", "label")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # enrollments protect the row; deletion is never routine


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


@admin.register(SchoolStaff)
class SchoolStaffAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "created_at")
    list_filter = ("school",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


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
