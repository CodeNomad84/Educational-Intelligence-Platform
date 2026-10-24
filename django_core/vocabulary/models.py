"""School-scoped, dated vocabularies (observation categories, recommendation tags, ...). Slice B.

A ``VocabularyTerm`` is never edited or deleted in place: a rename creates a NEW term whose ``replaces`` points at the old
one (see ``vocabulary.terms.rename_term``); the old term only gets its ``effective_to`` / ``active`` closed. Stored data
that refers to a term therefore keeps its meaning across years. New modules (exams, questionnaires, observations) must
use this table from day one; no existing model reads it yet. A ``node`` link to a framework (principle > component >
indicator) is deliberately NOT here: it is added when the framework tables exist.

Guards are model-level (``save`` / ``delete``); queryset ``update()`` / ``delete()`` bypass them, as everywhere in Django.
"""
from django.core.exceptions import ValidationError
from django.db import models

OBSERVATION_CATEGORY = 'observation_category'
OBSERVATION_SENTIMENT = 'observation_sentiment'
RECOMMENDATION_TAG = 'recommendation_tag'
INTERVENTION_TYPE = 'intervention_type'
DOMAINS = (OBSERVATION_CATEGORY, OBSERVATION_SENTIMENT, RECOMMENDATION_TAG, INTERVENTION_TYPE)
DOMAIN_CHOICES = [(d, d) for d in DOMAINS]

_RETIRE_FIELDS = {'effective_to', 'active'}      # the only fields that may change after creation


class VocabularyTerm(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="vocabulary_terms", verbose_name="مدرسه")
    domain = models.CharField(max_length=30, choices=DOMAIN_CHOICES, verbose_name="حوزه")
    code = models.SlugField(max_length=50, verbose_name="کد")
    label_fa = models.CharField(max_length=100, verbose_name="برچسب")
    active = models.BooleanField(default=True, verbose_name="فعال")
    effective_from = models.DateField(verbose_name="از تاریخ")
    effective_to = models.DateField(null=True, blank=True, verbose_name="تا تاریخ (شامل)")
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replaced_by",
                                 verbose_name="جایگزین")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "واژه"
        verbose_name_plural = "واژگان"
        ordering = ["school", "domain", "code", "effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["school", "domain", "code", "effective_from"], name="uniq_vocabularyterm_version"),
            models.CheckConstraint(condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                                   name="vocabularyterm_to_not_before_from"),
        ]
        indexes = [models.Index(fields=["school", "domain", "effective_from"])]

    def __str__(self):
        return f"{self.school_id}/{self.domain}/{self.code}"

    def clean(self):
        if self.domain not in DOMAINS:
            raise ValidationError({"domain": "unknown domain"})
        if self.replaces_id and (self.replaces.school_id != self.school_id or self.replaces.domain != self.domain):
            raise ValidationError({"replaces": "a replacement must be in the same school and domain"})

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.clean()
        else:
            old = type(self).objects.get(pk=self.pk)
            changed = {f.name for f in self._meta.concrete_fields
                       if f.name != 'created_at' and getattr(old, f.attname) != getattr(self, f.attname)}
            if changed - _RETIRE_FIELDS:
                raise ValidationError("A vocabulary term is never edited in place; create a replacement term instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("A vocabulary term is never deleted; close it with effective_to / active=False.")
