"""Risk events and alerts (intervention loop, change 0022).

``RiskEvent`` is an append-only record of one determination with its explanation. ``Alert`` is the item a person reviews:
one row per event, not one per recipient; the first review (accept or dismiss) wins. Both are school-scoped; the school is
always copied from the student. Nothing here is a label of the student, only a record of what staff noticed and decided.
Manual only for now: ``raise_alert`` (``risk/services.py``) is the single entry point a rule engine will call later.
"""
from django.conf import settings
from django.db import models


class RiskEvent(models.Model):
    class RiskType(models.TextChoices):
        ACADEMIC = "academic", "آموزشی"
        EMOTIONAL = "emotional", "هیجانی"
        BEHAVIORAL = "behavioral", "رفتاری"
        SOCIAL = "social", "اجتماعی"
        ATTENDANCE = "attendance", "غیبت"
        MOTIVATION = "motivation", "انگیزشی"
        FAMILY = "family", "خانوادگی"

    class Severity(models.TextChoices):
        GREEN = "green", "عادی"
        YELLOW = "yellow", "نیازمند توجه"
        ORANGE = "orange", "نیازمند مداخله"
        RED = "red", "مداخله فوری"

    class DetectedBy(models.TextChoices):
        RULE_ENGINE = "rule_engine", "موتور قاعده‌محور"
        COUNSELOR = "counselor", "مشاور"
        TEACHER = "teacher", "معلم"
        ADMIN = "admin", "مدیر یا ناظم"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+", editable=False)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="risk_events")
    risk_type = models.CharField(max_length=20, choices=RiskType.choices, verbose_name="نوع")
    risk_score = models.FloatField(null=True, blank=True, verbose_name="امتیاز")
    severity = models.CharField(max_length=10, choices=Severity.choices, verbose_name="شدت")
    detected_by = models.CharField(max_length=20, choices=DetectedBy.choices)
    explanation = models.TextField(max_length=500, verbose_name="توضیح")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["student", "risk_type", "-created_at"])]

    def __str__(self):
        return f"{self.student} {self.risk_type} {self.severity}"


class Alert(models.Model):
    NEW, ACCEPTED, DISMISSED = "new", "accepted", "dismissed"
    STATUS_CHOICES = [(NEW, "جدید"), (ACCEPTED, "پذیرفته‌شده"), (DISMISSED, "ردشده")]
    # Dismiss reasons are fixed codes (configuration, not school logic); "other" needs a note.
    DISMISS_REASONS = [("not_relevant", "نامرتبط"), ("already_handled", "قبلاً رسیدگی شده"), ("duplicate", "تکراری"),
                       ("data_error", "خطای داده"), ("other", "سایر")]

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+", editable=False)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="alerts")
    risk_event = models.ForeignKey(RiskEvent, on_delete=models.PROTECT, related_name="alerts")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="+", editable=False)
    message = models.TextField(max_length=300, verbose_name="پیام")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=NEW, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", editable=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    dismiss_reason = models.CharField(max_length=20, choices=DISMISS_REASONS, blank=True)
    review_note = models.TextField(max_length=300, blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status="dismissed", dismiss_reason__gt="") | ~models.Q(status="dismissed"),
                name="alert_dismissed_has_reason"),
            models.CheckConstraint(
                condition=~models.Q(dismiss_reason="other") | models.Q(review_note__gt=""),
                name="alert_other_reason_has_note"),
        ]

    def __str__(self):
        return f"{self.student} {self.status}"
