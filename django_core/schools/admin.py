"""Admin for School, SchoolClass and TeacherAssignment (proposal 0002, C1).

No permissions are granted here (C4 does that explicitly). The code only narrows what the admin offers:
the school record is superuser-only to add/delete and its key is read-only for everyone else, and only
eligible users can be picked as teacher.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import School, SchoolClass, TeacherAssignment


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
        return fields


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("title", "academic_year", "school", "is_active")
    list_filter = ("school", "is_active", "academic_year")
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
