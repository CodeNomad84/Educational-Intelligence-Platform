"""Read and rename helpers for ``VocabularyTerm`` (the only write path besides creating a brand-new term)."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import VocabularyTerm


def terms_on(school, domain, on=None):
    """Terms of ``domain`` in force for ``school`` on ``on`` (default today): active and inside their dates."""
    on = on or timezone.localdate()
    return VocabularyTerm.objects.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on), school=getattr(school, 'pk', school),
                                         domain=domain, active=True, effective_from__lte=on)


@transaction.atomic
def rename_term(term, *, label_fa, code=None, on=None):
    """Replace ``term`` from date ``on`` (default today): creates a new term (same code unless ``code`` is given) with
    ``replaces=term`` and closes the old one the day before. Returns the new term. Old data keeps pointing at the old row."""
    on = on or timezone.localdate()
    if not term.active or (term.effective_to is not None and term.effective_to < on):
        raise ValueError('only a term that is in force can be replaced')
    if on <= term.effective_from:
        raise ValueError('the replacement must start after the term it replaces')
    new = VocabularyTerm.objects.create(school_id=term.school_id, domain=term.domain, code=code or term.code, label_fa=label_fa,
                                        effective_from=on, replaces=term)
    term.effective_to = on - timedelta(days=1)
    term.active = False
    term.save(update_fields=['effective_to', 'active'])
    return new
