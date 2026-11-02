from django.db import models
from django.contrib.auth import get_user_model  # برای ارجاع به مدل User

from schools.vocabulary import GRADE_CHOICES, SUBJECT_CHOICES

User = get_user_model()

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
    # Owner correction A2: shown ONLY on the case page of a referred student (counselor), never in lists, the API or details.
    father_phone = models.CharField(max_length=20, blank=True, verbose_name="تلفن پدر")
    mother_phone = models.CharField(max_length=20, blank=True, verbose_name="تلفن مادر")
    
    # ارتباط به مدل User (برای والدین)
    parent_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='children',
        verbose_name="والدین (کاربر)"
    )
    # Slice 4b: the student's own login account (role Student). One account per student; set by the school's SchoolAdmin.
    student_user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name='student_profile',
        verbose_name="حساب دانش‌آموز")

    # School structure (ADR-0004). ``school_class`` is the source of truth for class membership;
    # ``school`` is derived from it in save() and ``class_name`` is its deprecated, read-only mirror.
    # ``school`` is NOT NULL since S6 (students.0015); ``school_class`` stays nullable (a student may have no class).
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.PROTECT,
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

    def save(self, *args, **kwargs):
        """Keep ``school`` and the ``class_name`` mirror consistent with ``school_class``.

        With a class: ``school`` = class.school and ``class_name`` = class.title, always overwritten.
        Without a class: nothing is derived; ``class_name`` keeps its legacy free text.
        ``update_fields`` is extended so a partial save of ``school_class`` still persists both.
        Bulk operations (``bulk_create``/``bulk_update``/``update``) bypass this method.
        """
        if self.school_class_id is not None:
            klass = self.school_class
            if not self._state.adding and self.school_id is not None and self.school_id != klass.school_id:
                # an existing student never moves to a class of another school (generic message, no school name)
                from django.core.exceptions import ValidationError
                raise ValidationError({'school_class': 'کلاس انتخاب‌شده برای این دانش‌آموز مجاز نیست.'})
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
        if self.student_id and self.academic_year_id and self.student.school_id != self.academic_year.school_id:
            errors['academic_year'] = "سال تحصیلی با مدرسهٔ دانش‌آموز هم‌خوان نیست."
        if errors:
            raise ValidationError(errors)


class Recommendation(models.Model):
    """A teacher's written recommendation / feedback about a student (Slice 2). Human-written, never AI-generated.

    Visible to the student's full-tier readers (SchoolAdmin of the school, Grade Lead of the grade, the parent) and to its
    author; see ``students.access.visible_recommendations``.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='recommendations')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', editable=False)
    subject = models.CharField(max_length=20, choices=SUBJECT_CHOICES, blank=True, verbose_name="درس")
    text = models.TextField(max_length=2000, verbose_name="توصیه")
    # Owner correction A4: staff-only by default; True = the student (and the parents) can read this text.
    visible_to_student = models.BooleanField(default=False, verbose_name="قابل نمایش به دانش‌آموز")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = "توصیه"
        verbose_name_plural = "توصیه‌ها"

    def __str__(self):
        return f"{self.student} - {self.created_at:%Y-%m-%d}"


class Referral(models.Model):
    """A SchoolAdmin or Grade Lead refers a student to a school counselor with a short reason (Slice 4a).

    An OPEN referral is what lets the counselor read the student (``students.access._counselor_q``): only referred
    students, only while open, only in the counselor's own school. Closing it ends the counselor's access.
    """
    STATUS_CHOICES = [('open', 'باز'), ('closed', 'بسته')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='referrals')
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='+', editable=False)
    counselor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+', verbose_name="مشاور")
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', editable=False)
    reason = models.TextField(max_length=500, verbose_name="دلیل ارجاع")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['student', 'counselor'], condition=models.Q(status='open'),
                                    name='uniq_open_referral_student_counselor'),
        ]

    def __str__(self):
        return f"{self.student} -> {self.counselor} ({self.status})"


class CounselorNote(models.Model):
    """A counselor's note on a referral. Readable only by the counselor of the case and the school's SchoolAdmin."""
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', editable=False)
    text = models.TextField(max_length=2000, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class BehaviorNote(models.Model):
    """Behavior log (decision pack 0028 P5-3): a short positive or concern entry by school staff. Never a label of the student.
    School copied from the student; PROTECT (students are deactivated, never deleted). Read scope: ``visible_behavior_notes``
    (SchoolAdmin and Grade Lead: all entries of their students; Subject Teacher: own entries; Parent: POSITIVE entries of own
    children only, owner decision 2026-11-01). Nothing is deleted automatically (retention waits for the legal policy)."""
    POSITIVE, CONCERN = 'positive', 'concern'
    KIND_CHOICES = [(POSITIVE, 'مثبت'), (CONCERN, 'نگرانی')]
    CATEGORY_CHOICES = [('participation', 'مشارکت'), ('effort', 'تلاش'), ('kindness', 'همدلی و کمک'),
                        ('responsibility', 'مسئولیت‌پذیری'), ('conduct', 'رفتار کلاسی'), ('other', 'سایر')]

    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='+', editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='behavior_notes')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, verbose_name='نوع')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='موضوع')
    note = models.TextField(max_length=300, verbose_name='شرح کوتاه')
    occurred_on = models.DateField(verbose_name='تاریخ')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_on', '-pk']
        indexes = [models.Index(fields=['student', '-occurred_on'])]

    def save(self, *args, **kwargs):
        self.school_id = self.student.school_id
        super().save(*args, **kwargs)
