"""Mission-based selection (module key ``mission``). Slice 1: reference data, versioned weights, periods, activities and
observations. Nothing here is a stored label or rank of a student; scores are computed on demand (Slice 2).

Indicators, branches and rubric levels are global (the model's fixed vocabulary). Weights and thresholds are DATA, one
``WeightSet`` version per school, lifecycle draft > simulated > pending_approval > active (> retired). An active or retired
set and its weights are immutable at model level; a change is a new version (guards are model-level, as in ``vocabulary``).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from schools.vocabulary import GRADE_CHOICES

from .defaults import FIELD_CHOICES


class Indicator(models.Model):
    code = models.PositiveSmallIntegerField(unique=True, verbose_name="شمارهٔ شاخص")
    name_fa = models.CharField(max_length=100, verbose_name="شاخص")

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code}. {self.name_fa}'


class Branch(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    field = models.CharField(max_length=10, choices=FIELD_CHOICES, verbose_name="میدان")
    name_fa = models.CharField(max_length=100, verbose_name="شاخه")
    order = models.PositiveSmallIntegerField(verbose_name="ترتیب")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name_fa


class RubricLevel(models.Model):
    """Criterion text of one score level of one indicator. Loaded from the owner's local guide (``load_mission_rubric``),
    never committed."""
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='levels')
    score = models.PositiveSmallIntegerField()
    text = models.TextField()

    class Meta:
        ordering = ['indicator', 'score']
        constraints = [models.UniqueConstraint(fields=['indicator', 'score'], name='uniq_rubric_level'),
                       models.CheckConstraint(condition=models.Q(score__gte=1, score__lte=5), name='rubric_score_1_5')]


class WeightSet(models.Model):
    """One version of the weights and thresholds of a school. ``id`` is the ``params_version`` stored on reports."""
    DRAFT, SIMULATED, PENDING, ACTIVE, RETIRED = 'draft', 'simulated', 'pending_approval', 'active', 'retired'
    STATUS_CHOICES = [(DRAFT, 'پیش‌نویس'), (SIMULATED, 'شبیه‌سازی‌شده'), (PENDING, 'منتظر تأیید'), (ACTIVE, 'فعال'),
                      (RETIRED, 'بازنشسته')]
    EDITABLE = (DRAFT,)

    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='mission_weight_sets')
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    min_observations = models.PositiveSmallIntegerField(default=3)
    min_activities = models.PositiveSmallIntegerField(default=2)
    diff_threshold = models.DecimalField(max_digits=3, decimal_places=1, default='1.5')
    show_x20 = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['school', '-version']
        constraints = [
            models.UniqueConstraint(fields=['school', 'version'], name='uniq_weightset_version'),
            models.UniqueConstraint(fields=['school'], condition=models.Q(status='active'), name='one_active_weightset_per_school'),
        ]

    def __str__(self):
        return f'{self.school_id}/v{self.version} ({self.status})'

    def save(self, *args, **kwargs):
        if self._state.adding and self.status != self.DRAFT:
            raise ValidationError('A weight set starts as a draft.')
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if old.status == self.DRAFT and self.status != self.DRAFT and not self.sums_ok():
                raise ValidationError('Every branch column must sum to 100 before a set leaves draft.')
            if old.status in (self.ACTIVE, self.RETIRED):
                changed = {f.name for f in self._meta.concrete_fields if getattr(old, f.attname) != getattr(self, f.attname)}
                if changed - {'status'} or self.status not in (old.status, self.RETIRED):
                    raise ValidationError('An active or retired weight set is immutable; create a new version instead.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('A weight set is never deleted; retire it.')

    def sums_ok(self):
        sums = self.column_sums()
        return len(sums) == Branch.objects.count() and set(sums.values()) == {100}

    def column_sums(self):
        """{branch_id: sum of percents}; a set may leave draft only when every branch sums to 100."""
        sums = {}
        for branch_id, percent in self.weights.values_list('branch_id', 'percent'):
            sums[branch_id] = sums.get(branch_id, 0) + percent
        return sums


class Weight(models.Model):
    weight_set = models.ForeignKey(WeightSet, on_delete=models.CASCADE, related_name='weights')
    indicator = models.ForeignKey(Indicator, on_delete=models.PROTECT, related_name='+')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='+')
    percent = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['weight_set', 'indicator', 'branch'], name='uniq_weight_cell'),
                       models.CheckConstraint(condition=models.Q(percent__lte=100), name='weight_percent_0_100')]

    def save(self, *args, **kwargs):
        if self.weight_set.status not in WeightSet.EDITABLE:
            raise ValidationError('Weights of a set that has left draft are immutable; create a new version.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('A weight is never deleted.')


class Period(models.Model):
    """An observation period inside an academic year (free label). Aggregation never crosses periods."""
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='mission_periods')
    academic_year = models.ForeignKey('schools.AcademicYear', on_delete=models.PROTECT, related_name='mission_periods')
    label = models.CharField(max_length=50, verbose_name="عنوان دوره")
    closed = models.BooleanField(default=False, verbose_name="بسته")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['school', '-academic_year__start_date', 'label']
        constraints = [models.UniqueConstraint(fields=['school', 'academic_year', 'label'], name='uniq_mission_period')]

    def __str__(self):
        return f'{self.label} ({self.academic_year.code})'

    def clean(self):
        if self.academic_year_id and self.academic_year.school_id != self.school_id:
            raise ValidationError('the academic year belongs to another school')


class Activity(models.Model):
    """A observed activity (building, poster, presentation...) for one grade of one school in one period."""
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='mission_activities')
    grade = models.PositiveSmallIntegerField(choices=GRADE_CHOICES, verbose_name="پایه")
    period = models.ForeignKey(Period, on_delete=models.PROTECT, related_name='activities', verbose_name="دوره")
    title = models.CharField(max_length=120, verbose_name="عنوان فعالیت")
    held_on = models.DateField(verbose_name="تاریخ")
    activity_type = models.ForeignKey('vocabulary.VocabularyTerm', on_delete=models.PROTECT, related_name='+', verbose_name="نوع فعالیت")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-held_on', '-pk']
        indexes = [models.Index(fields=['school', 'grade', 'period'], name='mission_act_scope_idx')]

    def __str__(self):
        return self.title

    def clean(self):
        if self.period_id and self.period.school_id != self.school_id:
            raise ValidationError('the period belongs to another school')
        if self.activity_type_id and (self.activity_type.school_id != self.school_id or self.activity_type.domain != 'mission_activity_type'):
            raise ValidationError('the activity type is not a term of this school')

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.clean()
        super().save(*args, **kwargs)


class ObservationSession(models.Model):
    """One observer's entries for one activity. A teacher reads and edits only the sessions they own."""
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='sessions')
    observer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['activity', 'observer'], name='uniq_mission_session')]


class Observation(models.Model):
    """One score 1-5 (with a short evidence sentence) or "not observed" for a student on an indicator. "Not observed" is NOT
    a low score: it is excluded from every calculation."""
    session = models.ForeignKey(ObservationSession, on_delete=models.CASCADE, related_name='observations')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='mission_observations')
    indicator = models.ForeignKey(Indicator, on_delete=models.PROTECT, related_name='+')
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    not_observed = models.BooleanField(default=False)
    evidence = models.CharField(max_length=300, blank=True)
    condition = models.ForeignKey('vocabulary.VocabularyTerm', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    dedupe_key = models.CharField(max_length=64, blank=True)   # same non-blank key in one activity = one independent evidence
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'student', 'indicator'], name='uniq_mission_observation'),
            models.CheckConstraint(
                condition=models.Q(score__isnull=True, not_observed=True) | models.Q(score__isnull=False, score__gte=1, score__lte=5, not_observed=False),
                name='observation_score_xor_not_observed'),
            models.CheckConstraint(condition=models.Q(score__isnull=True) | ~models.Q(evidence=''), name='observation_scored_has_evidence'),
        ]
        indexes = [models.Index(fields=['student', 'indicator'], name='mission_obs_student_idx')]

    def save(self, *args, **kwargs):
        if self._state.adding and self.student.school_id != self.session.activity.school_id:
            raise ValidationError('the student belongs to another school')
        super().save(*args, **kwargs)
