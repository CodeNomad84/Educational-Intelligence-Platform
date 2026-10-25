"""Exam results (exams Slice 2): derived on read, never stored, no ranking and no talent labels.

First try = solved with no wrong option chosen. Every figure carries the number of attempts it rests on; below ``MIN_QUESTIONS``
questions per student (``MIN_STUDENTS`` students per group for aggregates) the figure is withheld ("not enough data").
Time is shown only as a class-level median per question: it is never compared between students.
"""
from collections import Counter
from statistics import median

from .models import Option, QuestionAttempt

MIN_QUESTIONS = 5      # a per-student figure needs at least this many solved questions
MIN_STUDENTS = 5       # an aggregate group smaller than this is never shown


def _first_try(attempt):
    return attempt.solved_at is not None and not attempt.wrong_option_ids


def student_summary(attempts):
    """{'solved': n, 'first_try': n, 'rate': float | None} for one student's attempts (rate withheld under the floor)."""
    solved = [a for a in attempts if a.solved_at is not None]
    first = sum(1 for a in solved if _first_try(a))
    return {'solved': len(solved), 'first_try': first,
            'rate': first / len(solved) if len(solved) >= MIN_QUESTIONS else None}


def question_stats(exam, student_ids=None):
    """Per question of ``exam`` (in exam order): attempts, first-try rate, mean tries, median seconds, most chosen wrong option."""
    attempts = QuestionAttempt.objects.filter(session__exam=exam, attempt_count__gt=0)
    if student_ids is not None:
        attempts = attempts.filter(session__student_id__in=student_ids)
    by_q = {}
    for a in attempts:
        by_q.setdefault(a.question_id, []).append(a)
    options = {o.pk: o for o in Option.objects.filter(question__in=exam.questions.all())}
    rows = []
    for item in exam.items.select_related('question', 'question__topic').order_by('order'):
        group = by_q.get(item.question_id, [])
        solved = [a for a in group if a.solved_at is not None]
        wrong = Counter(w for a in group for w in a.wrong_option_ids)
        top = options.get(wrong.most_common(1)[0][0]) if wrong else None
        rows.append({
            'question': item.question, 'attempts': len(group), 'solved': len(solved),
            'first_try_rate': (sum(1 for a in solved if _first_try(a)) / len(solved)) if len(solved) >= MIN_STUDENTS else None,
            'mean_tries': (sum(a.attempt_count for a in group) / len(group)) if len(group) >= MIN_STUDENTS else None,
            'median_seconds': median(a.seconds_spent for a in group) if len(group) >= MIN_STUDENTS else None,
            'top_wrong': top})
    return rows


def topic_rates(attempts_by_student):
    """Aggregate first-try rate per topic over {student_id: [attempts with .question.topic]}; a topic with fewer than
    ``MIN_STUDENTS`` students is withheld. Returns [(topic, n_students, rate | None)] in topic-code order."""
    per_topic = {}
    for sid, attempts in attempts_by_student.items():
        for a in attempts:
            if a.solved_at is not None:
                per_topic.setdefault(a.question.topic, {}).setdefault(sid, []).append(_first_try(a))
    out = []
    for topic in sorted(per_topic, key=lambda t: t.code):
        students = per_topic[topic]
        flat = [x for v in students.values() for x in v]
        out.append((topic, len(students), (sum(flat) / len(flat)) if len(students) >= MIN_STUDENTS else None))
    return out
