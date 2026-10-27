"""Risk events and alerts (intervention loop, change 0022).

``RiskEvent`` is an append-only record of one determination with its explanation. ``Alert`` is the item a person reviews:
one row per event, not one per recipient; the first review (accept or dismiss) wins. Both are school-scoped; the school is
always copied from the student. Nothing here is a label of the student, only a record of what staff noticed and decided.
Manual only for now: ``raise_alert`` (``risk/services.py``) is the single entry point a rule engine will call later.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
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


class RuleSettings(models.Model):
    """Per-school knobs of the rule engine (0025). A new table instead of columns on School (no change to existing tables).
    ``grade_scale_max`` empty = not set: a score-based rule (``low_average``) cannot be activated (fail closed)."""
    school = models.OneToOneField("schools.School", on_delete=models.PROTECT, related_name="+")
    grade_scale_max = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="سقف مقیاس نمره")
    breaker_percent = models.PositiveSmallIntegerField(default=15, verbose_name="آستانهٔ قطع‌کن (درصد دانش‌آموزان)")
    require_second_approver = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(breaker_percent__gte=1, breaker_percent__lte=100),
                                              name="rulesettings_breaker_1_100")]


class Rule(models.Model):
    """One row = one VERSION of a deterministic rule. Clauses are data validated against the metric catalog
    (``risk/signals.py``); nothing is ever executed from them. Only non-sensitive risk types are allowed, enforced by the
    database as well as by validation."""
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        SIMULATED = "simulated", "شبیه‌سازی‌شده"
        PENDING = "pending_approval", "در انتظار تأیید"
        ACTIVE = "active", "فعال"
        PAUSED = "paused", "متوقف"
        ARCHIVED = "archived", "بایگانی"

    RULE_RISK_TYPES = ("academic", "attendance", "behavioral")   # never emotional / family / social / motivation
    KINDS = ("attendance_shift", "repeated_absence", "low_average", "grade_drop")

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+")
    code = models.SlugField(max_length=40)
    version = models.PositiveIntegerField(default=1)
    kind = models.CharField(max_length=30, choices=[(k, k) for k in KINDS])
    title = models.CharField(max_length=120)
    risk_type = models.CharField(max_length=20, choices=[(t, t) for t in RULE_RISK_TYPES])
    severity = models.CharField(max_length=10, choices=[("yellow", "yellow"), ("orange", "orange")])
    connective = models.CharField(max_length=3, choices=[("all", "all"), ("any", "any")], default="all")
    clauses = models.JSONField(default=list)
    cooldown_days = models.PositiveSmallIntegerField(default=14)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    params_hash = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["school_id", "code", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code", "version"], name="rule_version_unique"),
            models.UniqueConstraint(fields=["school", "code"], condition=models.Q(status__in=["active", "paused"]),
                                    name="rule_one_live_version_per_code"),
            models.CheckConstraint(condition=models.Q(risk_type__in=["academic", "attendance", "behavioral"]),
                                   name="rule_risk_type_not_sensitive"),
        ]

    PARAM_FIELDS = ("kind", "risk_type", "severity", "connective", "clauses", "cooldown_days", "code", "version", "school_id")

    def save(self, *args, **kwargs):
        # Parameters are frozen once a version is live or finished (clone to change): active, paused and archived rows only
        # change status / approval fields. Draft, simulated and pending rows are edited through risk.lifecycle.
        if self.pk:
            old = Rule.objects.filter(pk=self.pk).first()
            if old is not None and old.status in ("active", "paused", "archived"):
                for name in self.PARAM_FIELDS:
                    if getattr(old, name) != getattr(self, name):
                        raise ValidationError("A live or archived rule version cannot be edited; clone it.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} v{self.version} ({self.status})"


class RuleHit(models.Model):
    """Why one alert exists: the evidence (metric values and record counts) of a rule firing for a student on a date.
    Unique per (rule, student, day): two simultaneous runs cannot both raise an alert. Read only through the alert."""
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+")
    rule = models.ForeignKey(Rule, on_delete=models.PROTECT, related_name="hits")
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="+")
    alert = models.ForeignKey(Alert, on_delete=models.PROTECT, related_name="rule_hits")
    evaluated_on = models.DateField()
    evidence = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["rule", "student", "evaluated_on"], name="rulehit_once_per_day")]
        indexes = [models.Index(fields=["rule", "student", "-evaluated_on"])]


class RuleRun(models.Model):
    """Counts of one evaluation of one rule (simulation or live). No student ids, no names."""
    class Status(models.TextChoices):
        OK = "ok", "انجام شد"
        BREAKER = "breaker_tripped", "قطع‌کن فعال شد؛ هشداری ثبت نشد"
        NO_SCALE = "no_scale", "مقیاس نمره تنظیم نشده"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="+")
    rule = models.ForeignKey(Rule, on_delete=models.PROTECT, related_name="runs")
    mode = models.CharField(max_length=10, choices=[("simulation", "simulation"), ("live", "live")])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OK)
    as_of = models.DateField()
    started_at = models.DateTimeField(auto_now_add=True)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    evaluated = models.PositiveIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0)
    alerts_raised = models.PositiveIntegerField(default=0)
    skipped_cooldown = models.PositiveIntegerField(default=0)
    skipped_insufficient = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at", "-pk"]
