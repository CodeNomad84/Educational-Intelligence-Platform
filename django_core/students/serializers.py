# students/serializers.py
from rest_framework import serializers
from .models import Student

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'  # یا لیست دقیق فیلدها: ['id', 'first_name', ...]
        read_only_fields = ['id', 'created_at', 'updated_at']

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
