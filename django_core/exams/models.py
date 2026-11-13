"""Exams (module key ``exams``), Slice 1: a teacher question bank with an explanation for EVERY option, exams assigned to
classes, and a practice player that records time, attempts and the wrong options in order.

Practice only: nothing here ever writes a ``Grade``. Topics are ``VocabularyTerm`` rows of the domain ``exam_topic`` with a flat,
hierarchical code ``<subject>.ch<N>.<concept>`` (e.g. ``math.ch3.fractions``); there is no tree and no parent link. No names,
free text or answers beyond option ids are stored in attempt rows.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from schools.vocabulary import SUBJECT_CHOICES
from vocabulary.models import EXAM_TOPIC

TEACHER_SOURCE = 'teacher'


class Question(models.Model):
    DRAFT, APPROVED, RETIRED = 'draft', 'approved', 'retired'
    STATUS_CHOICES = [(DRAFT, 'پیش‌نویس'), (APPROVED, 'تأییدشده'), (RETIRED, 'بازنشسته')]

    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='exam_questions')
    subject = models.CharField(max_length=50, choices=SUBJECT_CHOICES, verbose_name="درس")
    topic = models.ForeignKey('vocabulary.VocabularyTerm', on_delete=models.PROTECT, related_name='+', verbose_name="مبحث")
    stem = models.TextField(verbose_name="متن پرسش")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    source = models.CharField(max_length=20, default=TEACHER_SOURCE)      # later: csv / ai_suggested
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['school', 'subject', 'status'], name='exam_q_scope_idx')]

    def __str__(self):
        return self.stem[:40]

    def clean(self):
        topic = self.topic
        if topic.school_id != self.school_id or topic.domain != EXAM_TOPIC or not topic.code.startswith(f'{self.subject}.'):
            raise ValidationError('the topic is not an exam topic of this school and subject')

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.clean()
        super().save(*args, **kwargs)

    @property
    def has_attempts(self):
        return self.attempts.exists()


class Option(models.Model):
    """One answer choice. The explanation is REQUIRED for every option, right or wrong (constraint + editor)."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    order = models.PositiveSmallIntegerField()
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)
    explanation = models.TextField()

    class Meta:
        ordering = ['question', 'order']
        constraints = [
            models.UniqueConstraint(fields=['question', 'order'], name='uniq_exam_option_order'),
            models.UniqueConstraint(fields=['question'], condition=models.Q(is_correct=True), name='one_correct_exam_option'),
            models.CheckConstraint(condition=~models.Q(explanation=''), name='exam_option_has_explanation'),
            models.CheckConstraint(condition=~models.Q(text=''), name='exam_option_has_text'),
        ]


class Exam(models.Model):
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT, related_name='exams')
    subject = models.CharField(max_length=50, choices=SUBJECT_CHOICES, verbose_name="درس")
    title = models.CharField(max_length=120, verbose_name="عنوان")
    classes = models.ManyToManyField('schools.SchoolClass', related_name='exams', verbose_name="کلاس‌ها")
    questions = models.ManyToManyField(Question, through='ExamQuestion', related_name='exams')
    opens_on = models.DateField(null=True, blank=True)
    closes_on = models.DateField(null=True, blank=True)
    published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.CheckConstraint(
            condition=models.Q(opens_on__isnull=True) | models.Q(closes_on__isnull=True) | models.Q(closes_on__gte=models.F('opens_on')),
            name='exam_closes_not_before_opens')]

    def __str__(self):
        return self.title


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name='+')
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['exam', 'order']
        constraints = [models.UniqueConstraint(fields=['exam', 'question'], name='uniq_exam_question'),
                       models.UniqueConstraint(fields=['exam', 'order'], name='uniq_exam_question_order')]

    def save(self, *args, **kwargs):
        if self._state.adding and (self.question.school_id != self.exam.school_id or self.question.subject != self.exam.subject
                                   or self.question.status != Question.APPROVED):
            raise ValidationError('an exam holds approved questions of its own school and subject')
        super().save(*args, **kwargs)


class ExamSession(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='sessions')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='exam_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['exam', 'student'], name='uniq_exam_session')]


class QuestionAttempt(models.Model):
    """Everything recorded about one student on one question: seconds (clamped per step), the number of tries, the wrong option
    ids in the order they were chosen, and when it was solved. Nothing else."""
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='attempts')
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name='attempts')
    seconds_spent = models.PositiveIntegerField(default=0)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    wrong_option_ids = models.JSONField(default=list)
    last_shown_at = models.DateTimeField(null=True, blank=True)
    solved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'question'], name='uniq_exam_attempt')]
