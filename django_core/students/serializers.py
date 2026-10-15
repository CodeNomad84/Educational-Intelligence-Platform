# students/serializers.py
from rest_framework import serializers

from schools.models import SchoolClass

from .models import Student


class StudentSerializer(serializers.ModelSerializer):
    # school_class is the source of truth for class membership (ADR-0004): only active classes can be
    # chosen, ``school`` is derived server-side and ``class_name`` is a read-only mirror.
    school_class = serializers.PrimaryKeyRelatedField(
        queryset=SchoolClass.objects.filter(is_active=True), allow_null=True, required=False,
    )

    class Meta:
        model = Student
        # Explicit list (no '__all__'): a new model field is never exposed or writable by accident.
        fields = [
            'id', 'first_name', 'last_name', 'national_id', 'grade', 'phone_number',
            'class_name', 'father_job', 'mother_job', 'parent_user',
            'school', 'school_class', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'class_name', 'school', 'created_at', 'updated_at']

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
