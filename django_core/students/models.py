from django.db import models
from django.contrib.auth import get_user_model  # برای ارجاع به مدل User

from schools.vocabulary import GRADE_CHOICES, SUBJECT_CHOICES

User = get_user_model()

class SchoolAssignmentRefused(Exception):
    """``Student.save()`` was asked to give an existing school-less student a school (S6 requirement 1)."""


class Student(models.Model):
    GRADE_CHOICES = GRADE_CHOICES  # shared vocabulary, defined in schools/vocabulary.py
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    national_id = models.CharField(max_length=10, unique=True)
    grade = models.IntegerField(choices=GRADE_CHOICES)
    phone_number = models.CharField(max_length=15)

# فیلدهای جدید (بر اساس دیتاکلاس قبلی)
    class_name = models.CharField(max_length=50, blank=True, verbose_name="کلاس")
    father_job = models.CharField(max_length=100, blank=True, verbose_name="شغل پدر")
    mother_job = models.CharField(max_length=100, blank=True, verbose_name="شغل مادر")
    
    # ارتباط به مدل User (برای والدین)
    parent_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='children',
        verbose_name="والدین (کاربر)"
    )

    # School structure (ADR-0004). ``school_class`` is the source of truth for class membership;
    # ``school`` is derived from it in save() and ``class_name`` is its deprecated, read-only mirror.
    # Both are nullable: existing rows stay unlinked until the C3 data migration.
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name='students',
        verbose_name="مدرسه",
    )
    school_class = models.ForeignKey(
        'schools.SchoolClass',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='students',
        verbose_name="کلاس (ساختار مدرسه)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "دانش‌آموز"
        verbose_name_plural = "دانش‌آموزان"
        ordering = ['grade', 'last_name', 'first_name']
        constraints = [
            # A class link without a school is never valid. (Equality of school and class.school
            # is a cross-table rule: enforced in save() and re-checked by the access layer.)
            models.CheckConstraint(
                condition=models.Q(school_class__isnull=True) | models.Q(school__isnull=False),
                name='student_class_requires_school',
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.get_grade_display()}"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._remember_loaded_school()
        return instance

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self._remember_loaded_school()

    def _remember_loaded_school(self):
        # S6: the school this row had when it was read; absent (deferred field) = unknown = not guarded.
        if 'school_id' in self.__dict__:
            self._loaded_school_id = self.__dict__['school_id']
        else:
            self.__dict__.pop('_loaded_school_id', None)

    def save(self, *args, **kwargs):
        """Keep ``school`` and the ``class_name`` mirror consistent with ``school_class``.

        S6: an EXISTING student that was read without a school is never given one here, neither by a class link nor by
        assigning ``school``: only ``backfill_student_school`` (queryset update) may populate a legacy row.

        With a class: ``school`` = class.school and ``class_name`` = class.title, always overwritten.
        Without a class: nothing is derived; ``class_name`` keeps its legacy free text.
        ``update_fields`` is extended so a partial save of ``school_class`` still persists both.
        Bulk operations (``bulk_create``/``bulk_update``/``update``) bypass this method.
        """
        if (not self._state.adding and self.__dict__.get('_loaded_school_id', 0) is None
                and (self.school_id is not None or self.school_class_id is not None)):
            raise SchoolAssignmentRefused(
                'An existing student without a school cannot be given one by save(); use backfill_student_school.')
        if self.school_class_id is not None:
            klass = self.school_class
            self.school_id = klass.school_id
            self.class_name = klass.title
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and {'school_class', 'school_class_id'} & set(update_fields):
                kwargs['update_fields'] = set(update_fields) | {'school', 'class_name'}
        super().save(*args, **kwargs)

class Grade(models.Model):
    SUBJECT_CHOICES = SUBJECT_CHOICES  # shared vocabulary, defined in schools/vocabulary.py
    EXAM_TYPE_CHOICES = [
        ('midterm', 'میان‌ترم'),
        ('final', 'پایان‌ترم'),
        ('quiz', 'آزمون'),
        ('project', 'پروژه'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='grades')
    # ADR-0011 stage 2.2a-1: nullable, unused by any read path yet; attribution to year/class/grade-in-year.
    enrollment = models.ForeignKey(
        'students.Enrollment', on_delete=models.PROTECT, null=True, blank=True, related_name='grades',
        verbose_name="ثبت‌نام (سال تحصیلی)")
    # '' = linked by a person/import, 'backfill' = linked by backfill_enrollments (so it can be reverted exactly).
    enrollment_link_source = models.CharField(max_length=10, blank=True, default='', editable=False)
    import_batch = models.ForeignKey(
        'students.ImportBatch', on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name='%(class)ss')
    subject = models.CharField(max_length=20, choices=SUBJECT_CHOICES, verbose_name="درس")
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES, verbose_name="نوع آزمون")
    score = models.FloatField(verbose_name="نمره")
    date = models.DateField(verbose_name="تاریخ آزمون")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "نمره"
        verbose_name_plural = "نمرات"
        ordering = ['-date']
        indexes = [models.Index(fields=['enrollment', 'subject', 'date'], name='grade_enr_subject_date_idx')]

    def __str__(self):
        return f"{self.student} - {self.get_subject_display()} - {self.score}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'حاضر'),
        ('absent', 'غائب'),
        ('late', 'تأخیر'),
        ('sick', 'مریضی'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    enrollment = models.ForeignKey(
        'students.Enrollment', on_delete=models.PROTECT, null=True, blank=True, related_name='attendances',
        verbose_name="ثبت‌نام (سال تحصیلی)")
    enrollment_link_source = models.CharField(max_length=10, blank=True, default='', editable=False)
    import_batch = models.ForeignKey(
        'students.ImportBatch', on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name='%(class)ss')
    date = models.DateField(verbose_name="تاریخ")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, verbose_name="وضعیت")
    note = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حضور و غیاب"
        verbose_name_plural = "حضور و غیاب"
        ordering = ['-date']
        unique_together = [['student', 'date']]
        indexes = [models.Index(fields=['enrollment', 'date'], name='att_enr_date_idx')]

    def __str__(self):
        return f"{self.student} - {self.date} - {self.get_status_display()}"
    
class Document(models.Model):
    title = models.CharField(max_length=255, verbose_name="عنوان سند")
    content = models.TextField(verbose_name="محتوا")
    file = models.FileField(upload_to='documents/', blank=True, null=True, verbose_name="فایل")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سند"
        verbose_name_plural = "اسناد"
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class ImportBatch(models.Model):
    """One year-aware import run (ADR-0011 §5). Stage 2.2a-1: the entity only; no import writes it yet."""

    KIND_CHOICES = [('roster', 'فهرست'), ('grades', 'نمرات'), ('attendance', 'حضور و غیاب'), ('rollover', 'انتقال سال تحصیلی')]

    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    academic_year = models.ForeignKey('schools.AcademicYear', on_delete=models.PROTECT, related_name='import_batches')
    file_sha256 = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name='+')
    dry_run = models.BooleanField(default=True)
    counts = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "دسته ورود داده"
        verbose_name_plural = "دسته‌های ورود داده"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.kind} {self.academic_year} #{self.pk}"


class Enrollment(models.Model):
    """One student in one academic year: class and grade IN THAT YEAR (ADR-0011 §3.2).

    Stage 2.2a-1: storage only. ``Student.grade/school_class`` remain the source of truth and nothing in the
    access layer reads this table (the switch is stage 2.2a-4, behind a parity test).
    """

    STATUS_CHOICES = [
        ('active', 'فعال'), ('promoted', 'ارتقا یافته'), ('retained', 'مردود'),
        ('transferred_out', 'انتقال به مدرسه دیگر'), ('transferred_in', 'انتقال از مدرسه دیگر'),
        ('graduated', 'فارغ‌التحصیل'), ('withdrawn', 'ترک تحصیل'),
    ]
    SOURCE_CHOICES = [('manual', 'دستی'), ('import', 'ورود داده'), ('backfill', 'استنتاج از داده موجود'),
                      ('rollover', 'انتقال سال تحصیلی')]

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='enrollments')
    academic_year = models.ForeignKey(
        'schools.AcademicYear', on_delete=models.PROTECT, related_name='enrollments')
    school_class = models.ForeignKey(
        'schools.SchoolClass', on_delete=models.PROTECT, null=True, blank=True, related_name='enrollments')
    grade = models.PositiveSmallIntegerField(choices=Student.GRADE_CHOICES, verbose_name="پایه در این سال")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active')
    started_on = models.DateField(null=True, blank=True)
    ended_on = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual')
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, null=True, blank=True, related_name='enrollments')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ثبت‌نام سالانه"
        verbose_name_plural = "ثبت‌نام‌های سالانه"
        ordering = ['student', '-academic_year__start_date']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year'], condition=models.Q(ended_on__isnull=True),
                name='uniq_enrollment_one_open_per_student_year'),
            models.CheckConstraint(
                condition=models.Q(ended_on__isnull=True) | models.Q(started_on__isnull=True)
                | models.Q(ended_on__gte=models.F('started_on')),
                name='enrollment_end_not_before_start'),
        ]
        indexes = [
            models.Index(fields=['student', 'academic_year'], name='enr_student_year_idx'),
            models.Index(fields=['academic_year', 'school_class'], name='enr_year_class_idx'),
            models.Index(fields=['academic_year', 'grade', 'status'], name='enr_year_grade_status_idx'),
        ]

    def __str__(self):
        return f"{self.student} {self.academic_year} grade {self.grade} ({self.status})"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.school_class_id and self.academic_year_id:
            if self.school_class.school_id != self.academic_year.school_id:
                errors['school_class'] = "کلاس و سال تحصیلی باید از یک مدرسه باشند."
        if self.student_id and self.academic_year_id and self.student.school_id not in (None, self.academic_year.school_id):
            errors['academic_year'] = "سال تحصیلی با مدرسهٔ دانش‌آموز هم‌خوان نیست."
        if errors:
            raise ValidationError(errors)
