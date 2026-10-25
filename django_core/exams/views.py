"""Exams Slice 1 pages: the teacher's question bank, topics, exam creation, and the student practice player.

Gate on every view: ``role_required(<role>, module='exams')`` (request level) plus ``require_module`` on the object's school.
Teachers author for the (school, subject) pairs of their assignments and edit only their OWN questions (and only while nobody
has attempted them); students play only published, open exams that target their current class. Out-of-scope objects are 404,
a wrong role is 403. Audit stores ids and counts, never text. Practice only: this module never writes a ``Grade``.
"""
import re
from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.decorators import require_module, role_required
from schools import audit
from schools.models import School, SchoolClass
from schools.vocabulary import SUBJECT_CHOICES
from students.access import STUDENT, TEACHER
from vocabulary.models import EXAM_TOPIC, VocabularyTerm
from vocabulary.terms import terms_on

from .access import MODULE, bank_questions, own_student, student_exams, teacher_class_ids, teacher_scopes
from .models import Exam, ExamQuestion, ExamSession, Option, Question, QuestionAttempt

MAX_OPTIONS = 5
IDLE_CLAMP_SECONDS = 300      # a tab left open counts as at most this per step, so it cannot poison the baseline
SUBJECT_LABELS = dict(SUBJECT_CHOICES)
CONCEPT = re.compile(r'^[a-z][a-z0-9_]{1,30}$')


def _scope_choices(user):
    names = dict(School.objects.filter(pk__in={s for s, _sub in teacher_scopes(user)}).values_list('pk', 'name'))
    return [(f'{s}:{sub}', f'{names[s]} — {SUBJECT_LABELS.get(sub, sub)}') for s, sub in sorted(teacher_scopes(user))]


def _split(key):
    school_id, subject = key.split(':', 1)
    return int(school_id), subject


def _parse_scope(user, raw):
    try:
        school_id, subject = raw.split(':', 1)
        pair = (int(school_id), subject)
    except (ValueError, AttributeError):
        return None
    return pair if pair in teacher_scopes(user) else None


def _topics(school_id, subject):
    return terms_on(school_id, EXAM_TOPIC).filter(code__startswith=f'{subject}.').order_by('code')


# --- teacher: bank ---------------------------------------------------------------------------------------------------
@role_required(TEACHER, module=MODULE)
def teacher_home(request):
    scopes = teacher_scopes(request.user)
    questions = bank_questions(request.user).select_related('topic', 'author')
    exams = Exam.objects.none()
    for school_id, subject in scopes:
        exams = exams | Exam.objects.filter(school_id=school_id, subject=subject)
    return render(request, 'exams/teacher_home.html', {
        'questions': questions, 'exams': exams.distinct().prefetch_related('classes'), 'has_scope': bool(scopes),
        'labels': SUBJECT_LABELS})


@role_required(TEACHER, module=MODULE)
@require_http_methods(['GET', 'POST'])
def topics(request):
    """Add a flat topic ``<subject>.ch<N>.<concept>`` to the own subjects. Existing codes are never edited."""
    errors = []
    if request.method == 'POST':
        pair = _parse_scope(request.user, request.POST.get('scope', ''))
        chapter, concept = (request.POST.get('chapter') or '').strip(), (request.POST.get('concept') or '').strip().lower()
        label = (request.POST.get('label_fa') or '').strip()
        if pair is None:
            errors.append('درس نامعتبر است.')
        elif not (chapter.isdigit() and 1 <= int(chapter) <= 99) or not CONCEPT.match(concept) or not label or len(label) > 100:
            errors.append('فصل (۱ تا ۹۹)، کد مفهوم (حروف لاتین کوچک، عدد و _) و عنوان لازم است.')
        else:
            school_id, subject = pair
            code = f'{subject}.ch{int(chapter)}.{concept}'
            if len(code) > 50 or VocabularyTerm.objects.filter(school_id=school_id, domain=EXAM_TOPIC, code=code).exists():
                errors.append('این کد بیش از حد بلند است یا از قبل وجود دارد.')
            else:
                term = VocabularyTerm.objects.create(school_id=school_id, domain=EXAM_TOPIC, code=code, label_fa=label,
                                                     effective_from=timezone.localdate())
                audit.record(request.user, audit.EXAM_TOPIC_ADD, term, school=school_id)
                messages.success(request, 'مبحث افزوده شد.')
                return redirect('exams:topics')
    rows = [(label, list(_topics(*_split(key)))) for key, label in _scope_choices(request.user)]
    return render(request, 'exams/topics.html', {'scopes': _scope_choices(request.user), 'rows': rows, 'errors': errors})


def _read_question(request, post, editing=None):
    """Parse the editor. Returns (data, errors, form_state)."""
    errors = []
    pair = _parse_scope(request.user, post.get('scope', ''))
    stem = (post.get('stem') or '').strip()
    options = []
    for i in range(1, MAX_OPTIONS + 1):
        text, expl = (post.get(f'o{i}_text') or '').strip(), (post.get(f'o{i}_expl') or '').strip()
        if text or expl:
            options.append({'i': i, 'text': text, 'explanation': expl})
    correct = (post.get('correct') or '').strip()
    topic = None
    if pair is None:
        errors.append('درس نامعتبر است.')
    else:
        topic = _topics(*pair).filter(pk=post.get('topic') or 0).first() if str(post.get('topic') or '').isdigit() else None
        if topic is None:
            errors.append('مبحث را از فهرست مبحث‌های همین درس انتخاب کنید.')
    if not stem or len(stem) > 2000:
        errors.append('متن پرسش لازم است (حداکثر ۲۰۰۰ نویسه).')
    if len(options) < 2:
        errors.append('دست‌کم دو گزینه لازم است.')
    for o in options:
        if not o['text'] or len(o['text']) > 300:
            errors.append(f'گزینهٔ {o["i"]}: متن لازم است (حداکثر ۳۰۰ نویسه).')
        if not o['explanation'] or len(o['explanation']) > 1000:
            errors.append(f'گزینهٔ {o["i"]}: توضیح لازم است؛ برای هر گزینه، چه درست چه غلط (حداکثر ۱۰۰۰ نویسه).')
    if correct not in {str(o['i']) for o in options}:
        errors.append('یکی از گزینه‌های پرشده را به‌عنوان پاسخ درست انتخاب کنید.')
    return ({'pair': pair, 'topic': topic, 'stem': stem, 'options': options, 'correct': correct}, errors)


def _question_context(request, question, data=None, errors=(), read_only=False):
    scope_choices = _scope_choices(request.user)
    topics_by_scope = {key: list(_topics(*_split(key))) for key, _l in scope_choices}
    if data is not None:
        scope = f'{data["pair"][0]}:{data["pair"][1]}' if data['pair'] else ''
        state = {'scope': scope, 'topic': data['topic'].pk if data['topic'] else '', 'stem': data['stem'], 'correct': data['correct'],
                 'options': {o['i']: o for o in data['options']}}
    elif question is not None:
        opts = list(question.options.all())
        state = {'scope': f'{question.school_id}:{question.subject}', 'topic': question.topic_id, 'stem': question.stem,
                 'correct': str(next((o.order for o in opts if o.is_correct), '')),
                 'options': {o.order: {'text': o.text, 'explanation': o.explanation} for o in opts}}
    else:
        state = {'scope': '', 'topic': '', 'stem': '', 'correct': '', 'options': {}}
    slots = [{'i': i, **state['options'].get(i, {'text': '', 'explanation': ''})} for i in range(1, MAX_OPTIONS + 1)]
    return {'question': question, 'scopes': scope_choices, 'topics_by_scope': topics_by_scope, 'state': state, 'slots': slots,
            'errors': list(errors), 'read_only': read_only}


@role_required(TEACHER, module=MODULE)
@require_http_methods(['GET', 'POST'])
def question_edit(request, pk=None):
    question = None
    if pk is not None:
        question = get_object_or_404(bank_questions(request.user), pk=pk)
        require_module(question.school_id, MODULE)
    if question is not None and (question.author_id != request.user.pk or question.has_attempts):
        if request.method == 'POST':
            raise PermissionDenied                       # only the author edits, and never after students have attempted it
        return render(request, 'exams/question_form.html', _question_context(request, question, read_only=True))
    if request.method == 'POST':
        data, errors = _read_question(request, request.POST)
        if not errors:
            school_id, subject = data['pair']
            with transaction.atomic():
                if question is None:
                    question = Question(school_id=school_id, subject=subject, author=request.user)
                elif (question.school_id, question.subject) != data['pair']:
                    raise PermissionDenied               # the school and subject of a saved question do not move
                question.topic, question.stem = data['topic'], data['stem']
                question.status = Question.DRAFT                  # any edit needs a fresh approval
                question.approved_by, question.approved_at = None, None
                question.save()
                question.options.all().delete()
                for order, o in enumerate(data['options'], start=1):
                    Option.objects.create(question=question, order=order, text=o['text'], explanation=o['explanation'],
                                          is_correct=str(o['i']) == data['correct'])
            audit.record(request.user, audit.EXAM_QUESTION_SAVE, question, school=question.school_id, detail=f'o{len(data["options"])}')
            messages.success(request, 'پرسش ذخیره شد (پیش‌نویس؛ برای استفاده در آزمون باید تأیید شود).')
            return redirect('exams:teacher_home')
        return render(request, 'exams/question_form.html', _question_context(request, question, data, errors))
    return render(request, 'exams/question_form.html', _question_context(request, question))


@role_required(TEACHER, module=MODULE)
@require_POST
def question_status(request, pk):
    question = get_object_or_404(bank_questions(request.user), pk=pk)
    require_module(question.school_id, MODULE)
    if question.author_id != request.user.pk:
        raise PermissionDenied
    action = request.POST.get('action')
    if action == 'approve' and question.status == Question.DRAFT:
        question.status, question.approved_by, question.approved_at = Question.APPROVED, request.user, timezone.now()
    elif action == 'retire' and question.status in (Question.DRAFT, Question.APPROVED):
        question.status = Question.RETIRED
    else:
        messages.error(request, 'این تغییر وضعیت مجاز نیست.')
        return redirect('exams:teacher_home')
    question.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    audit.record(request.user, audit.EXAM_QUESTION_STATUS, question, school=question.school_id, detail=question.status)
    return redirect('exams:teacher_home')


# --- teacher: exams -----------------------------------------------------------------------------------------------------
def _parse_date(raw):
    try:
        return date.fromisoformat((raw or '').strip()) if (raw or '').strip() else None
    except ValueError:
        return False


def _exam_form(request, exam=None):
    """Create (exam is None) or edit an exam. Only the creator edits; once students have a session the question set is locked
    (title, window, classes and publication stay editable)."""
    scopes = _scope_choices(request.user)
    locked = exam is not None and exam.sessions.exists()
    approved = bank_questions(request.user).filter(status=Question.APPROVED).select_related('topic')
    class_rows = []
    for key, label in scopes:
        school_id, subject = _split(key)
        for c in SchoolClass.objects.filter(pk__in=teacher_class_ids(request.user, school_id, subject)).order_by('title'):
            class_rows.append((key, c))
    errors = []
    if request.method == 'POST':
        pair = (exam.school_id, exam.subject) if exam is not None else _parse_scope(request.user, request.POST.get('scope', ''))
        title = (request.POST.get('title') or '').strip()
        opens, closes = _parse_date(request.POST.get('opens_on')), _parse_date(request.POST.get('closes_on'))
        picked_q = [int(x) for x in request.POST.getlist('questions') if x.isdigit()]
        picked_c = [int(x) for x in request.POST.getlist('classes') if x.isdigit()]
        if pair is None:
            errors.append('درس نامعتبر است.')
        if not title or len(title) > 120:
            errors.append('عنوان لازم است.')
        if opens is False or closes is False or (opens and closes and closes < opens):
            errors.append('بازهٔ تاریخ نامعتبر است.')
        questions = classes = []
        if pair is not None:
            classes = list(SchoolClass.objects.filter(pk__in=set(picked_c) & teacher_class_ids(request.user, *pair)))
            if not classes or len(classes) != len(set(picked_c)):
                errors.append('دست‌کم یک کلاس از کلاس‌های خودتان (همین درس) انتخاب کنید.')
            if not locked:
                questions = list(approved.filter(school_id=pair[0], subject=pair[1], pk__in=picked_q))
                if not questions or len(questions) != len(set(picked_q)):
                    errors.append('دست‌کم یک پرسش تأییدشدهٔ همین درس انتخاب کنید.')
        if not errors:
            with transaction.atomic():
                if exam is None:
                    exam = Exam.objects.create(school_id=pair[0], subject=pair[1], title=title, opens_on=opens or None,
                                               closes_on=closes or None, published=bool(request.POST.get('published')),
                                               created_by=request.user)
                    action = audit.EXAM_CREATE
                else:
                    exam.title, exam.opens_on, exam.closes_on = title, opens or None, closes or None
                    exam.published = bool(request.POST.get('published'))
                    exam.save(update_fields=['title', 'opens_on', 'closes_on', 'published'])
                    action = audit.EXAM_EDIT
                exam.classes.set(classes)
                if not locked:
                    exam.items.all().delete()
                    by_pk = {q.pk: q for q in questions}
                    for order, qpk in enumerate(dict.fromkeys(picked_q), start=1):
                        ExamQuestion.objects.create(exam=exam, question=by_pk[qpk], order=order)
            audit.record(request.user, action, exam, school=exam.school_id, detail=f'q{exam.items.count()}c{len(classes)}')
            messages.success(request, 'آزمون ذخیره شد.')
            return redirect('exams:teacher_home')
    state = None
    if exam is not None:
        state = {'title': exam.title, 'opens_on': exam.opens_on or '', 'closes_on': exam.closes_on or '', 'published': exam.published,
                 'classes': set(exam.classes.values_list('pk', flat=True)), 'questions': set(exam.items.values_list('question_id', flat=True))}
    return render(request, 'exams/exam_form.html', {'scopes': scopes, 'questions': approved, 'class_rows': class_rows, 'errors': errors,
                                                    'exam': exam, 'state': state, 'locked': locked,
                                                    'scope_key': f'{exam.school_id}:{exam.subject}' if exam else ''})


@role_required(TEACHER, module=MODULE)
@require_http_methods(['GET', 'POST'])
def exam_new(request):
    return _exam_form(request)


@role_required(TEACHER, module=MODULE)
@require_http_methods(['GET', 'POST'])
def exam_edit(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if (exam.school_id, exam.subject) not in teacher_scopes(request.user):
        raise Http404
    require_module(exam.school_id, MODULE)
    if exam.created_by_id != request.user.pk:
        raise PermissionDenied
    return _exam_form(request, exam)


@role_required(TEACHER, module=MODULE)
@require_POST
def exam_unpublish(request, pk):
    scopes = teacher_scopes(request.user)
    exam = get_object_or_404(Exam, pk=pk)
    if (exam.school_id, exam.subject) not in scopes:
        raise Http404
    require_module(exam.school_id, MODULE)
    if exam.created_by_id != request.user.pk:
        raise PermissionDenied
    exam.published = False
    exam.save(update_fields=['published'])
    audit.record(request.user, audit.EXAM_UNPUBLISH, exam, school=exam.school_id)
    return redirect('exams:teacher_home')


# --- student: practice player ----------------------------------------------------------------------------------------
@role_required(STUDENT, module=MODULE)
@never_cache
def student_home(request):
    student = own_student(request.user)
    if student is None:
        raise Http404
    rows = []
    for exam in student_exams(student).order_by('-created_at'):
        total = exam.items.count()
        solved = QuestionAttempt.objects.filter(session__exam=exam, session__student=student, solved_at__isnull=False).count()
        rows.append({'exam': exam, 'total': total, 'solved': solved})
    return render(request, 'exams/student_home.html', {'rows': rows, 'labels': SUBJECT_LABELS})


def _reveal(option, state):
    """What the student may see of an option: nothing about correctness until they chose it."""
    return {'pk': option.pk, 'text': option.text, 'state': state, 'explanation': option.explanation if state else ''}


@role_required(STUDENT, module=MODULE)
@never_cache
@require_http_methods(['GET', 'POST'])
def play(request, pk):
    student = own_student(request.user)
    if student is None:
        raise Http404
    exam = get_object_or_404(student_exams(student), pk=pk)
    require_module(exam.school_id, MODULE)
    now = timezone.now()
    with transaction.atomic():
        session, _ = ExamSession.objects.get_or_create(exam=exam, student=student)
        items = list(exam.items.select_related('question').order_by('order'))
        solved = set(QuestionAttempt.objects.filter(session=session, solved_at__isnull=False).values_list('question_id', flat=True))
        current = next((i for i in items if i.question_id not in solved), None)
        if current is None:
            if session.finished_at is None:
                session.finished_at = now
                session.save(update_fields=['finished_at'])
            return render(request, 'exams/done.html', {'exam': exam, 'total': len(items)})
        question = current.question
        attempt, _ = QuestionAttempt.objects.get_or_create(session=session, question=question)
        options = list(question.options.all())
        feedback = None
        if request.method == 'POST':
            chosen = next((o for o in options if str(o.pk) == (request.POST.get('option') or '')), None)
            if chosen is None:
                raise Http404
            if chosen.pk not in attempt.wrong_option_ids:           # a repeated click on a red option changes nothing
                if attempt.last_shown_at:
                    attempt.seconds_spent += min(max(0, int((now - attempt.last_shown_at).total_seconds())), IDLE_CLAMP_SECONDS)
                attempt.attempt_count += 1
                if chosen.is_correct:
                    attempt.solved_at, attempt.last_shown_at = now, None
                    feedback = 'correct'
                else:
                    attempt.wrong_option_ids = [*attempt.wrong_option_ids, chosen.pk]
                    attempt.last_shown_at = now
                    feedback = 'wrong'
                attempt.save()
        elif attempt.solved_at is None:
            attempt.last_shown_at = now                              # the clock starts when the question is shown
            attempt.save(update_fields=['last_shown_at'])
        shown = [_reveal(o, 'wrong' if o.pk in attempt.wrong_option_ids else
                         'correct' if (attempt.solved_at is not None and o.is_correct) else '') for o in options]
    return render(request, 'exams/play.html', {
        'exam': exam, 'question': question, 'options': shown, 'index': items.index(current) + 1, 'total': len(items),
        'solved_now': attempt.solved_at is not None, 'feedback': feedback})
