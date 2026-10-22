"""School structure for teacher object-level access (ADR-0003, ADR-0004; proposal 0002, Phase 2.1 / C1).

School -> SchoolClass -> TeacherAssignment. Integer (BigAutoField) primary keys, no dependency on the
scaffold ``accounts``/``core`` apps (preserved on branch ``archive/scaffold-apps-2026-10-13``).

C1 only defines the structure. Nothing here changes who can see which student: ``Student`` has no link
to a class yet (C2) and ``students/access.py`` is untouched (C5).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .academic_years import CODE_RE, RESOLVED, normalize_academic_year
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


class SchoolMembership(models.Model):
    """A user administers a school (ADR-0012, proposal changes/0010, stage S1).

    Many-to-many between users and schools through this model. The row grants nothing unless the user also
    holds the ``SchoolAdmin`` group, is active and is not a superuser; ``students.access.school_ids_for_admin``
    re-checks all of that at query time. **Since S3 the SchoolAdmin branch of ``visible_*`` reads it**: a SchoolAdmin
    sees exactly the schools of its active memberships (none without a row); a superuser keeps a temporary global read
    until S8.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_memberships",
        verbose_name="کاربر",
    )
    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="memberships", verbose_name="مدرسه")
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
        verbose_name = "عضویت در مدرسه"
        verbose_name_plural = "عضویت‌ها در مدرسه"
        ordering = ["school", "user"]
        constraints = [
            models.UniqueConstraint(fields=["user", "school"], name="uniq_schoolmembership_user_school"),
        ]

    def __str__(self):
        return f"{self.user} → {self.school}"

    def clean(self):
        """Only an active, non-superuser account in group ``SchoolAdmin`` and NOT in ``PlatformAdmin`` may be a
        member (the group and account state are re-checked at query time by ``school_ids_for_admin``). ``is_staff`` is allowed until the Django admin is restricted (S9)."""
        from django.core.exceptions import NON_FIELD_ERRORS

        from students.access import ADMIN, PLATFORM_ADMIN  # lazy: keeps role names in one place, avoids an import cycle

        errors = {}
        # An existing INACTIVE row is not re-validated: it grants nothing and must stay deactivatable (review
        # finding G3). On an existing row the user cannot be edited (read-only in the admin), so the error is a
        # non-field error there instead of a field error the form does not have.
        if self.user_id and (self._state.adding or self.is_active):
            key = "user" if self._state.adding else NON_FIELD_ERRORS
            user = self.user
            if not user.is_active:
                errors[key] = "کاربر غیرفعال است."
            elif user.is_superuser:
                errors[key] = "حساب superuser نمی‌تواند عضو مدرسه باشد."
            elif not user.groups.filter(name=ADMIN).exists():
                errors[key] = f"کاربر باید عضو گروه «{ADMIN}» باشد."
            elif user.groups.filter(name=PLATFORM_ADMIN).exists():
                # separation of duties (review finding F1): who manages memberships must not hold one
                errors[key] = f"کاربر عضو گروه «{PLATFORM_ADMIN}» است و نمی‌تواند عضو مدرسه باشد."
        if errors:
            raise ValidationError(errors)


class AcademicYear(models.Model):
    """One school year of one school (ADR-0011). Dates are entered by a SchoolAdmin, never computed.

    Stage 2.2a-1 only stores the entity: ``SchoolClass.academic_year`` and ``GradeLeadAssignment.academic_year``
    are still free text and nothing reads this table for access decisions.
    """

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="academic_years", verbose_name="مدرسه")
    code = models.CharField(max_length=9, verbose_name="کد سال تحصیلی", help_text="مثال: 1404-1405")
    label = models.CharField(max_length=50, blank=True, verbose_name="عنوان")
    start_date = models.DateField(verbose_name="شروع (میلادی)")
    end_date = models.DateField(verbose_name="پایان (میلادی)")
    is_current = models.BooleanField(default=False, verbose_name="سال جاری")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سال تحصیلی"
        verbose_name_plural = "سال‌های تحصیلی"
        ordering = ["school", "-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="uniq_academicyear_school_code"),
            models.UniqueConstraint(
                fields=["school"], condition=models.Q(is_current=True), name="uniq_academicyear_one_current_per_school"),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")), name="academicyear_end_after_start"),
        ]

    def __str__(self):
        return self.label or self.code

    def clean(self):
        errors = {}
        status, canonical = normalize_academic_year(self.code)
        if not CODE_RE.match(self.code or "") or status != RESOLVED or canonical != self.code:
            errors["code"] = "کد باید به شکل 1404-1405 (سال بعد = سال اول + ۱) باشد."
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                errors["end_date"] = "پایان باید بعد از شروع باشد."
            elif self.school_id:
                overlap = AcademicYear.objects.filter(
                    school_id=self.school_id, start_date__lte=self.end_date, end_date__gte=self.start_date,
                ).exclude(pk=self.pk)
                if overlap.exists():
                    errors["start_date"] = "بازه با یک سال تحصیلی دیگر همین مدرسه همپوشانی دارد."
        if self.is_current and self.school_id:
            if AcademicYear.objects.filter(school_id=self.school_id, is_current=True).exclude(pk=self.pk).exists():
                errors["is_current"] = "برای هر مدرسه فقط یک سال جاری می‌تواند وجود داشته باشد."
        if errors:
            raise ValidationError(errors)


class SchoolStaff(models.Model):
    """The school a staff account (Teacher, Grade Lead) belongs to; created by that school's SchoolAdmin in the dashboard.

    Slice 1. It only says WHICH SchoolAdmin may manage the account; it grants no data access by itself (access
    comes from the assignments, re-checked at query time in ``students.access``). One school per account.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="school_staff", verbose_name="کاربر")
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="staff", verbose_name="مدرسه")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "کارکنان مدرسه"
        verbose_name_plural = "کارکنان مدرسه"
        ordering = ["school", "user"]

    def __str__(self):
        return f"{self.user} @ {self.school}"
