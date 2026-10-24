"""Who may enter and who may read mission observations. Deny by default; the module gate is applied on top of every scope.

ENTRY (grid): only Subject Teachers (students of their active class assignments) and Grade Leads (students of their grade),
both through the CURRENT ENROLLMENT, reusing the building blocks of ``students.access`` (read only; no access rule is changed
there). A SchoolAdmin, Counselor, Parent or Student never enters observations.
READ (``visible_observations``): Teacher = own observations only; Grade Lead = all observers' rows for the students of the
own grade; Counselor = only students with an OPEN referral to them; SchoolAdmin = none (aggregates only, Slice 3).
"""
from django.db.models import Q

from schools.entitlements import module_enabled, user_school_ids
from students.access import (
    COUNSELOR, GRADE_LEAD, TEACHER, _any, _counselor_q, _current_enrollment, _grade_lead_q, _teacher_assignments, roles_for)
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, Student

from .models import Activity, Observation

MODULE = 'mission'
ENTRY_ROLES = (TEACHER, GRADE_LEAD)


def enabled_school_ids(user):
    """Schools of the user where the mission module is on today (trial or licensed)."""
    return {sid for sid in user_school_ids(user) if module_enabled(sid, MODULE)}


def entry_students(user):
    roles = roles_for(user)
    scope = _any([_grade_lead_q(user, roles),
                  _any(_current_enrollment(school_id, school_class_id=class_id)
                       for school_id, class_id, _subject in _teacher_assignments(user, roles))])
    return Student.objects.filter(scope) if scope is not None else Student.objects.none()


def entry_scopes(user):
    """{(school_id, grade)} of the user's entry students in their current enrollment, restricted to schools with the module on."""
    allowed = enabled_school_ids(user)
    rows = Enrollment.objects.filter(
        student__in=entry_students(user).values('pk'), ended_on__isnull=True, status__in=CURRENT_STATUSES,
        academic_year__is_current=True, student__school_id__in=allowed).values_list('student__school_id', 'grade').distinct()
    return set(rows)


def usable_activities(user):
    scopes = entry_scopes(user)
    q = _any(Q(school_id=school_id, grade=grade) for school_id, grade in scopes)
    return Activity.objects.filter(q) if q is not None else Activity.objects.none()


def grid_students(user, activity):
    """The students this user may score in this activity: entry scope, same school, enrolled in the activity's grade and
    academic year. Empty when the module is off for the school."""
    if not module_enabled(activity.school_id, MODULE):
        return Student.objects.none()
    enrolled = Enrollment.objects.filter(
        academic_year=activity.period.academic_year, grade=activity.grade, ended_on__isnull=True,
        status__in=CURRENT_STATUSES).values('student_id')
    return entry_students(user).filter(school_id=activity.school_id, pk__in=enrolled).order_by('last_name', 'first_name', 'pk')


def visible_observations(user):
    roles = roles_for(user)
    schools = enabled_school_ids(user)
    base = Observation.objects.filter(session__activity__school_id__in=schools)
    parts = []
    if TEACHER in roles:
        parts.append(Q(session__observer=user))
    lead = _grade_lead_q(user, roles)
    if lead is not None:
        parts.append(Q(student__in=Student.objects.filter(lead).values('pk')))
    counselor = _counselor_q(user, roles) if COUNSELOR in roles else None
    if counselor is not None:
        parts.append(Q(student__in=Student.objects.filter(counselor).values('pk')))
    q = _any(parts)
    return base.filter(q) if q is not None and schools else Observation.objects.none()
