"""School structure for teacher object-level access (ADR-0003, ADR-0004; proposal 0002, Phase 2.1 / C1).

School -> SchoolClass -> TeacherAssignment. Integer (BigAutoField) primary keys, no dependency on the
scaffold ``accounts``/``core`` apps (preserved on branch ``archive/scaffold-apps-2026-10-13``).

C1 only defines the structure. Nothing here changes who can see which student: ``Student`` has no link
to a class yet (C2) and ``students/access.py`` is untouched (C5).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class School(models.Model):
    """The school key (ADR-0004). Phase 2 runs with a single default row."""

    name = models.CharField(max_length=200, verbose_name="نام مدرسه")
    code = models.SlugField(max_length=50, unique=True, verbose_name="کد مدرسه")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "مدرسه"
        verbose_name_plural = "مدارس"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    """A class of students inside one school. An inactive class grants no teacher access (ADR-0004 §5)."""

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="classes", verbose_name="مدرسه")
    title = models.CharField(max_length=50, verbose_name="عنوان کلاس")
    academic_year = models.CharField(max_length=20, blank=True, verbose_name="سال تحصیلی")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "کلاس"
        verbose_name_plural = "کلاس‌ها"
        ordering = ["academic_year", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "title"],
                name="uniq_schoolclass_school_year_title",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.academic_year})" if self.academic_year else self.title


class TeacherAssignment(models.Model):
    """Links a teacher to a class. Scoping is class-level; ``subject`` is informational only."""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_assignments",
        verbose_name="معلم",
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        verbose_name="کلاس",
    )
    subject = models.CharField(max_length=50, blank=True, verbose_name="درس")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
        verbose_name="ثبت‌کننده",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تخصیص معلم به کلاس"
        verbose_name_plural = "تخصیص‌های معلم به کلاس"
        ordering = ["school_class", "teacher"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "school_class", "subject"],
                name="uniq_teacherassignment_teacher_class_subject",
            ),
        ]

    def __str__(self):
        return f"{self.teacher} → {self.school_class}"

    def clean(self):
        """Only an active, non-staff user in group ``Teacher`` may be assigned, and only to an active class.

        Enforced for every ModelForm (admin) and ``full_clean()``. The access layer (C5) re-checks the
        role at query time, so a row created by other means still grants nothing to a non-teacher.
        """
        from students.access import TEACHER  # lazy: keeps role names in one place, avoids an import cycle

        errors = {}
        if self.teacher_id:
            user = self.teacher
            if not user.is_active:
                errors["teacher"] = "کاربر غیرفعال است."
            elif user.is_staff or user.is_superuser:
                errors["teacher"] = "حساب مدیریتی (staff/superuser) را نمی‌توان به‌عنوان معلم تخصیص داد."
            elif not user.groups.filter(name=TEACHER).exists():
                errors["teacher"] = f"کاربر باید عضو گروه «{TEACHER}» باشد."
        if self.school_class_id and not self.school_class.is_active:
            errors["school_class"] = "کلاس غیرفعال است."
        if errors:
            raise ValidationError(errors)
