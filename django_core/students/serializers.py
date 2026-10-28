# students/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers

from schools.models import SchoolClass

from .models import Student
from .student_school import MESSAGES, NATIONAL_ID_REFUSED, SCHOOL_NOT_ALLOWED, national_id_taken, StudentSchoolError, class_choices, parent_choices, resolve_student_school


class OwnSchoolClassField(serializers.PrimaryKeyRelatedField):
    """Only active classes of the requesting user's own schools exist for this field (a foreign class is "does not exist",
    with the same generic message as a school the user may not use)."""
    default_error_messages = {'does_not_exist': MESSAGES[SCHOOL_NOT_ALLOWED], 'incorrect_type': MESSAGES[SCHOOL_NOT_ALLOWED]}

    def get_queryset(self):
        user = getattr(self.context.get('request'), 'user', None)
        instance = self.parent.instance if self.parent is not None else None
        return class_choices(user, keep_pk=getattr(instance, 'school_class_id', None))


class OwnSchoolParentField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        user = getattr(self.context.get('request'), 'user', None)
        instance = self.parent.instance if self.parent is not None else None
        return parent_choices(user, keep_pk=getattr(instance, 'parent_user_id', None))


class StudentSerializer(serializers.ModelSerializer):
    # school_class is the source of truth for class membership (ADR-0004): only active classes can be
    # chosen, ``school`` is derived server-side and ``class_name`` is a read-only mirror.
    school_class = OwnSchoolClassField(queryset=SchoolClass.objects.none(), allow_null=True, required=False)
    parent_user = OwnSchoolParentField(queryset=get_user_model().objects.none(), allow_null=True, required=False)
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
        # the model's unique validator is replaced by ``validate_national_id`` (one fixed message, review 0027 F3)
        extra_kwargs = {'national_id': {'validators': []}}

    def validate_national_id(self, value):
        # one fixed message for a taken national id, whatever school holds it (review 0027 F3)
        if national_id_taken(value, exclude_pk=getattr(self.instance, 'pk', None)):
            raise serializers.ValidationError(NATIONAL_ID_REFUSED)
        return value

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
                existing_school_id=instance.school_id if instance is not None else None)
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
