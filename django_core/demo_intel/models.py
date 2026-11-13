# DEMO SCOPE — whole file.
# Minimal tables the demo needs beyond students.Student/Grade/Attendance. Deliberately independent of the
# TARGET-state models in behavior/risk/interventions (those are not installed and reference accounts.User).
# Only loaded when config.settings.demo is used (INSTALLED_APPS is extended there, not in base.py).
from django.db import models


class StudentObservation(models.Model):
    class Category(models.TextChoices):
        PARTICIPATION = "participation", "مشارکت کلاسی"
        DISCIPLINE = "discipline", "انضباط"
        SOCIAL = "social", "اجتماعی"
        ACADEMIC = "academic", "آموزشی"
        POSITIVE = "positive", "نکتهٔ مثبت"

    class Sentiment(models.TextChoices):
        POSITIVE = "positive", "مثبت"
        NEUTRAL = "neutral", "خنثی"
        NEGATIVE = "negative", "منفی"

    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="demo_observations")
    date = models.DateField()
    category = models.CharField(max_length=20, choices=Category.choices)
    sentiment = models.CharField(max_length=10, choices=Sentiment.choices)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} {self.date} {self.sentiment}"


class CounselingNote(models.Model):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="demo_counseling_notes")
    date = models.DateField()
    counselor_name = models.CharField(max_length=100)
    summary = models.TextField()

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} {self.date}"


class InterventionRecord(models.Model):
    class Kind(models.TextChoices):
        COUNSELOR_MEETING = "counselor_meeting", "جلسهٔ مشاوره"
        PARENT_CONTACT = "parent_contact", "تماس/جلسه با والدین"
        TUTORING = "tutoring", "پشتیبانی درسی"
        ATTENDANCE_PLAN = "attendance_plan", "برنامهٔ پیگیری حضور"

    class Status(models.TextChoices):
        PLANNED = "planned", "برنامه‌ریزی‌شده"
        ACTIVE = "active", "در جریان"
        COMPLETED = "completed", "تکمیل‌شده"

    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="demo_interventions")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    start_date = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices)
    description = models.TextField(blank=True)
    outcome = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.student} {self.get_kind_display()}"
