"""Who may author and who may play (module key ``exams``). Deny by default; the module gate applies on top of every scope.

AUTHORING: a Subject Teacher, for the (school, subject) pairs of their active class assignments, in schools with ``exams`` on.
They read the bank of those pairs and edit or retire only their OWN questions. PLAYING: a Student, through their own student
record, for published, open exams that target their CURRENT class. Nothing here changes an access rule in ``students.access``;
it only reuses its read-only building blocks.
"""
from django.db.models import Q
from django.utils import timezone

from schools.entitlements import module_enabled, user_school_ids
from students.access import STUDENT, TEACHER, _any, _own_student_q, _teacher_assignments, roles_for
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, Student

from .models import Exam, Question

MODULE = 'exams'


def enabled_school_ids(user):
    return {sid for sid in user_school_ids(user) if module_enabled(sid, MODULE)}


def teacher_scopes(user):
    """{(school_id, subject)} the teacher may author for, restricted to schools with the module on."""
    roles = roles_for(user)
    return {(school_id, subject) for school_id, _class, subject in _teacher_assignments(user, roles)
            if module_enabled(school_id, MODULE)}


def teacher_class_ids(user, school_id, subject):
    roles = roles_for(user)
    return {class_id for sid, class_id, subj in _teacher_assignments(user, roles) if (sid, subj) == (school_id, subject)}


def bank_questions(user):
    """The bank the teacher can read: every question of their (school, subject) pairs."""
    q = _any(Q(school_id=school_id, subject=subject) for school_id, subject in teacher_scopes(user))
    return Question.objects.filter(q) if q is not None else Question.objects.none()


def own_student(user):
    """The Student record of a signed-in student (None for anyone else or when the module is off for their school)."""
    roles = roles_for(user)
    q = _own_student_q(user, roles) if STUDENT in roles else None
    student = Student.objects.filter(q).first() if q is not None else None
    return student if student is not None and module_enabled(student.school_id, MODULE) else None


def current_class_id(student):
    return Enrollment.objects.filter(
        student=student, ended_on__isnull=True, status__in=CURRENT_STATUSES, academic_year__is_current=True,
        school_class__isnull=False).values_list('school_class_id', flat=True).first()


def student_exams(student, on=None):
    """Published exams, open today, that target the student's current class (same school)."""
    on = on or timezone.localdate()
    class_id = current_class_id(student)
    if class_id is None:
        return Exam.objects.none()
    return Exam.objects.filter(
        Q(opens_on__isnull=True) | Q(opens_on__lte=on), Q(closes_on__isnull=True) | Q(closes_on__gte=on),
        school_id=student.school_id, published=True, classes__pk=class_id).distinct()
