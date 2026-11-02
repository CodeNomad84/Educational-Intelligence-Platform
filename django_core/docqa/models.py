"""P7-5 staff document assistant (decisions 61-63). Non-personal school documents only: the SchoolAdmin uploads, staff ask, answers cite
the document. Stores EXTRACTED TEXT chunks (no original file). Every read filters by school BEFORE retrieval."""
from django.conf import settings
from django.db import models


class SchoolDocument(models.Model):
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='+')
    title = models.CharField(max_length=120)
    source_name = models.CharField(max_length=200, blank=True)
    char_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']
        constraints = [models.UniqueConstraint(fields=['school', 'title'], name='doc_unique_title_per_school')]

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    document = models.ForeignKey(SchoolDocument, on_delete=models.CASCADE, related_name='chunks')
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='+')   # copied from the document: the ACL filter
    ordinal = models.PositiveIntegerField()
    text = models.TextField(max_length=1500)

    class Meta:
        ordering = ['document_id', 'ordinal']
        indexes = [models.Index(fields=['school', 'document'], name='chunk_school_doc_idx')]


class AssistantSettings(models.Model):
    """Per-school switch for the AI answer layer. OFF by default; without it the page is a plain document search."""
    school = models.OneToOneField('schools.School', on_delete=models.PROTECT, related_name='+')
    ai_enabled = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)
