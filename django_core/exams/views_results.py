"""Exam results (Slice 2), read only, all derived on read (``analytics.py``). Teacher: own subject, students of the own classes.
Grade Lead: students of the own grade (names, fixed name order, never ranked). SchoolAdmin: aggregates of the own schools, no
names, groups under 5 withheld. A module gate on every route; out-of-scope objects are 404."""
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from dashboard.decorators import require_module, role_required
from schools import audit
from schools.models import School
from students.access import ADMIN, GRADE_LEAD, TEACHER, grade_lead_students, school_ids_for_admin
from students.models import Enrollment, Student
from students.enrollment_sync import CURRENT_STATUSES

from . import analytics
from .access import MODULE, enabled_school_ids, teacher_class_ids, teacher_scopes
from .models import Exam, QuestionAttempt

NOTE = 'تمرین است، نه امتحان: اعداد فقط شواهدی برای مرور و گفت‌وگو هستند، نمره یا رتبه نیستند.'


def _current_class_students(class_ids):
    ids = Enrollment.objects.filter(school_class_id__in=class_ids, ended_on__isnull=True, status__in=CURRENT_STATUSES,
                                    academic_year__is_current=True).values_list('student_id', flat=True)
    return Student.objects.filter(pk__in=ids)


@role_required(TEACHER, module=MODULE)
@never_cache
def exam_results(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if (exam.school_id, exam.subject) not in teacher_scopes(request.user):
        raise Http404
    require_module(exam.school_id, MODULE)
    mine = set(exam.classes.values_list('pk', flat=True)) & teacher_class_ids(request.user, exam.school_id, exam.subject)
    students = list(_current_class_students(mine).order_by('last_name', 'first_name', 'pk'))
    ids = [s.pk for s in students]
    attempts = {}
    for a in QuestionAttempt.objects.filter(session__exam=exam, session__student_id__in=ids):
        attempts.setdefault(a.session.student_id, []).append(a)
    total = exam.items.count()
    rows = [{'student': s, 'total': total, **analytics.student_summary(attempts.get(s.pk, [])),
             'started': s.pk in attempts} for s in students]
    audit.record(request.user, audit.EXAM_RESULTS_VIEW, exam, school=exam.school_id, detail=f's{len(students)}')
    return render(request, 'exams/results.html', {
        'exam': exam, 'rows': rows, 'questions': analytics.question_stats(exam, ids), 'floor': analytics.MIN_QUESTIONS,
        'group_floor': analytics.MIN_STUDENTS, 'note': NOTE})


@role_required(GRADE_LEAD, module=MODULE)
@never_cache
def lead_overview(request):
    students = [s for s in grade_lead_students(request.user).order_by('last_name', 'first_name', 'pk') if s.school_id in enabled_school_ids(request.user)]
    attempts = {}
    for a in QuestionAttempt.objects.filter(session__student__in=students).select_related('session__exam'):
        attempts.setdefault((a.session.student_id, a.session.exam.subject), []).append(a)
    subjects = sorted({subject for _sid, subject in attempts})
    rows = [{'student': s, 'cells': [analytics.student_summary(attempts.get((s.pk, subject), [])) for subject in subjects]} for s in students]
    for school_id in {s.school_id for s in students}:
        audit.record(request.user, audit.EXAM_GRADELEAD_VIEW, school=school_id, detail=f's{len(students)}')
    return render(request, 'exams/lead_overview.html', {'rows': rows, 'subjects': subjects, 'floor': analytics.MIN_QUESTIONS, 'note': NOTE})


@role_required(ADMIN, module=MODULE)
@never_cache
def admin_overview(request):
    blocks = []
    for school_id in sorted(school_ids_for_admin(request.user) & enabled_school_ids(request.user)):
        exams = []
        for exam in Exam.objects.filter(school_id=school_id).order_by('-created_at'):
            sessions = exam.sessions.count()
            finished = exam.sessions.filter(finished_at__isnull=False).count()
            by_student = {}
            for a in QuestionAttempt.objects.filter(session__exam=exam).select_related('question__topic', 'session'):
                by_student.setdefault(a.session.student_id, []).append(a)
            shown = sessions >= analytics.MIN_STUDENTS
            exams.append({'exam': exam, 'subject': exam.get_subject_display(), 'shown': shown,
                          'started': sessions if shown else None, 'finished': finished if shown else None,
                          'topics': analytics.topic_rates(by_student) if shown else []})
        blocks.append({'school': School.objects.get(pk=school_id), 'exams': exams})
        audit.record(request.user, audit.EXAM_ADMIN_VIEW, school=school_id, detail=str(len(exams)))
    return render(request, 'exams/admin_overview.html', {'blocks': blocks, 'group_floor': analytics.MIN_STUDENTS, 'note': NOTE})
