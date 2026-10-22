# students/serializers.py
from rest_framework import serializers

from schools.models import SchoolClass

from .models import Student
from .student_school import StudentSchoolError, resolve_student_school


class StudentSerializer(serializers.ModelSerializer):
    # school_class is the source of truth for class membership (ADR-0004): only active classes can be
    # chosen, ``school`` is derived server-side and ``class_name`` is a read-only mirror.
    school_class = serializers.PrimaryKeyRelatedField(
        queryset=SchoolClass.objects.filter(is_active=True), allow_null=True, required=False,
    )
    # S2b: stateless target school for a student without a class (ignored when a class decides). Never stored as
    # such: ``validate`` turns it into ``school_id`` through the single rule in ``student_school``.
    target_school = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Student
        # Explicit list (no '__all__'): a new model field is never exposed or writable by accident.
        fields = [
            'id', 'first_name', 'last_name', 'national_id', 'grade', 'phone_number',
            'class_name', 'father_job', 'mother_job', 'parent_user',
            'school', 'school_class', 'target_school', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'class_name', 'school', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        instance = self.instance
        target = attrs.pop('target_school', None)
        # An update that does not touch the class keeps the class's school (the existing school) as it is.
        school_class = attrs['school_class'] if 'school_class' in attrs else None
        try:
            attrs['school_id'] = resolve_student_school(
                user, school_class=school_class, target_school_id=target,
                existing_school_id=instance.school_id if instance is not None else None,
                is_existing=instance is not None)
        except StudentSchoolError as exc:
            field = 'school_class' if exc.code == 'class_target_mismatch' else 'target_school'
            raise serializers.ValidationError({field: [exc.message]})
        return attrs

    # Field policy (ADR-0005 §6, TEACHER_ACCESS_REVIEW R5): chosen server-side from the row's ``full_tier``
    # annotation set by ``visible_students``. A row without the annotation is treated as limited (fail closed).
    LIMITED_OMIT = ('national_id', 'phone_number', 'father_job', 'mother_job', 'parent_user')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not getattr(instance, 'full_tier', False):
            for name in self.LIMITED_OMIT:
                data.pop(name, None)
        return data

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    # S2b: stateless target school for the whole import (required for several memberships / a superuser).
    target_school = serializers.IntegerField(required=False, allow_null=True)
