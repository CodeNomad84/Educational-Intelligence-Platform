# Additive migration: creates Homework and TeacherParentCommunication (previously had no migration, D-02).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("students", "0006_document"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Homework",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("subject", models.CharField(max_length=50)),
                ("title", models.CharField(max_length=200)),
                ("due_date", models.DateField()),
                ("completion_rate", models.FloatField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "در انتظار"),
                            ("completed", "انجام شده"),
                            ("late", "دیرکرد"),
                        ],
                        max_length=20,
                    ),
                ),
                ("teacher_comment", models.TextField(blank=True)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="homeworks",
                        to="students.student",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TeacherParentCommunication",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField()),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("meeting", "جلسه"),
                            ("message", "پیام"),
                            ("call", "تماس"),
                        ],
                        max_length=20,
                    ),
                ),
                ("content", models.TextField()),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="communications",
                        to="students.student",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teacher_comms",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
