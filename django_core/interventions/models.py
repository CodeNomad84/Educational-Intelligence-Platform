"""Intervention plans and follow-ups (intervention loop, change 0022).

Records of what staff decided and did, never a label of the student. School-scoped (copied from the student). Students are
deactivated or archived, never deleted, so the student FK is PROTECT. The text of an ``emotional`` plan and of its
follow-ups is readable only by the plan owner and a Counselor with an open referral (``students.access``); everybody else
who can see the plan sees metadata only. Nothing is deleted automatically (retention waits for the legal policy).
"""
from django.conf import settings
from django.db import models


class Strategy(models.Model):
    """P6-1: a school-editable library entry (generic intervention idea) that a plan can be started from. Configuration, not
    student data; deactivated rather than deleted so past plans keep their reference."""
    TIER_CHOICES = [(1, "سطح ۱ — پیشگیری عمومی"), (2, "سطح ۲ — حمایت هدفمند"), (3, "سطح ۳ — حمایت فشرده")]

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=120, verbose_name="عنوان")
    intervention_type = models.CharField(max_length=20, choices=[("academic", "آموزشی"), ("behavioral", "رفتاری"),
                                                                 ("emotional", "عاطفی"), ("social", "اجتماعی")], verbose_name="نوع")
    tier = models.PositiveSmallIntegerField(choices=TIER_CHOICES, default=1, verbose_name="سطح")
    description = models.TextField(max_length=1000, verbose_name="شرح")
    typical_days = models.PositiveSmallIntegerField(default=30, verbose_name="مدت معمول (روز)")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ["tier", "intervention_type", "title"]
        constraints = [models.UniqueConstraint(fields=["school", "title"], name="strategy_unique_title_per_school")]

    def __str__(self):
        return self.title


class InterventionPlan(models.Model):
    ACADEMIC, BEHAVIORAL, EMOTIONAL, SOCIAL = "academic", "behavioral", "emotional", "social"
    TYPE_CHOICES = [(ACADEMIC, "آموزشی"), (BEHAVIORAL, "رفتاری"), (EMOTIONAL, "عاطفی"), (SOCIAL, "اجتماعی")]
    PLANNED, ACTIVE, COMPLETED, CANCELLED = "planned", "active", "completed", "cancelled"
    STATUS_CHOICES = [(PLANNED, "برنامه‌ریزی‌شده"), (ACTIVE, "فعال"), (COMPLETED, "تکمیل‌شده"), (CANCELLED, "لغوشده")]
    OUTCOME_CHOICES = [("improved", "بهبود"), ("no_change", "بدون تغییر"), ("worse", "بدتر شد"),
                       ("not_assessable", "قابل ارزیابی نیست")]

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+", editable=False)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="intervention_plans")
    alert = models.ForeignKey("risk.Alert", on_delete=models.PROTECT, null=True, blank=True, related_name="plans")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="مسئول")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", editable=False)
    intervention_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="نوع مداخله")
    goal = models.TextField(max_length=300, verbose_name="هدف")
    action_plan = models.TextField(max_length=1000, verbose_name="برنامه اقدام")
    start_date = models.DateField(verbose_name="شروع")
    due_date = models.DateField(verbose_name="سررسید")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PLANNED, db_index=True)
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    outcome_note = models.TextField(max_length=500, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reevaluate_on = models.DateField(null=True, blank=True)
    strategy = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True, related_name="plans", editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(due_date__gte=models.F("start_date")), name="plan_due_after_start"),
            models.CheckConstraint(condition=~models.Q(status="completed") | models.Q(outcome__gt=""),
                                   name="plan_completed_has_outcome"),
        ]

    def __str__(self):
        return f"{self.student} {self.intervention_type} {self.status}"


class InterventionFollowUp(models.Model):
    ASSESSMENT_CHOICES = [("on_track", "در مسیر"), ("needs_change", "نیازمند تغییر"), ("blocked", "متوقف")]

    plan = models.ForeignKey(InterventionPlan, on_delete=models.PROTECT, related_name="followups")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="+", editable=False)
    followup_date = models.DateField()
    progress_note = models.TextField(max_length=1000, verbose_name="یادداشت پیشرفت")
    assessment = models.CharField(max_length=15, choices=ASSESSMENT_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-followup_date", "-pk"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Follow-ups are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Follow-ups are append-only.")
