from django.db import models
from django.contrib.auth import get_user_model  # برای ارجاع به مدل User

User = get_user_model()

class Student(models.Model):
    GRADE_CHOICES = [
        (7, 'هفتم'), (8, 'هشتم'), (9, 'نهم'),
        (10, 'دهم'), (11, 'یازدهم'), (12, 'دوازدهم'),
    ]
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "دانش‌آموز"
        verbose_name_plural = "دانش‌آموزان"
        ordering = ['grade', 'last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.get_grade_display()}"

class Grade(models.Model):
    SUBJECT_CHOICES = [
        ('math', 'ریاضی'), ('physics', 'فیزیک'), ('chemistry', 'شیمی'),
        ('biology', 'زیست‌شناسی'), ('literature', 'ادبیات فارسی'),
        ('arabic', 'عربی'), ('english', 'انگلیسی'), ('quran', 'قرآن'),
        ('religious', 'دینی'), ('history', 'تاریخ'), ('geography', 'جغرافیا'),
        ('social', 'اجتماعی'), ('sports', 'ورزش'), ('art', 'هنر'),
        ('computer', 'کامپیوتر'),
    ]
    EXAM_TYPE_CHOICES = [
        ('midterm', 'میان‌ترم'),
        ('final', 'پایان‌ترم'),
        ('quiz', 'آزمون'),
        ('project', 'پروژه'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='grades')
    subject = models.CharField(max_length=20, choices=SUBJECT_CHOICES, verbose_name="درس")
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES, verbose_name="نوع آزمون")
    score = models.FloatField(verbose_name="نمره")
    date = models.DateField(verbose_name="تاریخ آزمون")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "نمره"
        verbose_name_plural = "نمرات"
        ordering = ['-date']

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
    date = models.DateField(verbose_name="تاریخ")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, verbose_name="وضعیت")
    note = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حضور و غیاب"
        verbose_name_plural = "حضور و غیاب"
        ordering = ['-date']
        unique_together = [['student', 'date']]

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