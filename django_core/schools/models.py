"""School structure for teacher object-level access (ADR-0003, ADR-0004; proposal 0002, Phase 2.1 / C1).

School -> SchoolClass -> TeacherAssignment. Integer (BigAutoField) primary keys, no dependency on the
scaffold ``accounts``/``core`` apps (preserved on branch ``archive/scaffold-apps-2026-10-13``).

C1 only defines the structure. Nothing here changes who can see which student: ``Student`` has no link
to a class yet (C2) and ``students/access.py`` is untouched (C5).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .vocabulary import GRADE_CHOICES, SUBJECT_CHOICES


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
    # Report/class-view attribute only (ADR-0004 amendment, owner D13): never the Grade Lead scope key,
    # and not back-filled from students; legacy classes stay NULL until an admin sets it.
    grade = models.PositiveSmallIntegerField(
        choices=GRADE_CHOICES, null=True, blank=True, verbose_name="پایه")
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
    """Links a Subject Teacher to a class and a subject (vocabulary shared with ``Grade.subject``)."""

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
    # Access-relevant (ADR-0005 §3): same fixed vocabulary as Grade.subject. ``blank`` stays True so that
    # legacy rows remain valid; clean() rejects a blank subject when a row is created.
    subject = models.CharField(max_length=50, blank=True, choices=SUBJECT_CHOICES, verbose_name="درس")
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
        if self._state.adding and not self.subject:
            errors["subject"] = "درس باید انتخاب شود."
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


class GradeLeadAssignment(models.Model):
    """Links a Grade Lead to one grade of one school for one academic year (ADR-0005 §2).

    Scope key is ``Student.grade`` of the assignment's school, not ``SchoolClass.grade``. Nothing reads this
    model yet: ``visible_students`` is unchanged until C5a, so creating a row grants no access.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="grade_lead_assignments",
        verbose_name="مربی پایه",
    )
    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="grade_lead_assignments", verbose_name="مدرسه")
    grade = models.PositiveSmallIntegerField(choices=GRADE_CHOICES, verbose_name="پایه")
    academic_year = models.CharField(max_length=20, verbose_name="سال تحصیلی")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
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
        verbose_name = "تخصیص مربی پایه"
        verbose_name_plural = "تخصیص‌های مربی پایه"
        ordering = ["school", "grade", "user"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "grade", "academic_year"],
                name="uniq_gradeleadassignment_user_school_grade_year",
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.get_grade_display()} ({self.academic_year})"

    def clean(self):
        """Only an active, non-staff user in group ``GradeLead`` may be assigned (re-checked at query time in C5a)."""
        from students.access import GRADE_LEAD  # lazy, same reason as TeacherAssignment.clean

        errors = {}
        if self.user_id:
            user = self.user
            if not user.is_active:
                errors["user"] = "کاربر غیرفعال است."
            elif user.is_staff or user.is_superuser:
                errors["user"] = "حساب مدیریتی (staff/superuser) را نمی‌توان به‌عنوان مربی پایه تخصیص داد."
            elif not user.groups.filter(name=GRADE_LEAD).exists():
                errors["user"] = f"کاربر باید عضو گروه «{GRADE_LEAD}» باشد."
        if self.academic_year is not None and not self.academic_year.strip():
            errors["academic_year"] = "سال تحصیلی الزامی است."
        if errors:
            raise ValidationError(errors)

    def year_warning(self):
        """Non-blocking hint: no class of this school carries this academic year (typo or rollover not done)."""
        if not (self.school_id and self.academic_year):
            return None
        if SchoolClass.objects.filter(school_id=self.school_id, academic_year=self.academic_year).exists():
            return None
        return f"هیچ کلاسی در این مدرسه با سال تحصیلی «{self.academic_year}» وجود ندارد."
