"""Single place that maps a Django user to roles and to the students they may see.

Since stage 2.2a-4c (ADR-0011) Grade Lead and Subject Teacher scopes are decided by the student's CURRENT
ENROLLMENT, not by the mirror fields on ``Student``; the pre-switch rule is kept verbatim in ``access_legacy`` for
the parity tooling and for revert.

Roles are the existing Django groups: ``SchoolAdmin`` (was ``Admin``), ``Teacher``, ``Parent``. A superuser is
treated as ``SchoolAdmin``. Anything else (no group, anonymous, unknown group) gets NO role and
therefore no access. This is an interim containment policy for Phase 1 (docs/SECURITY.md,
ADR-0003 is still DECISION REQUIRED); it is not the final authorization model.
"""
from functools import reduce
from operator import or_

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Q, Value

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.vocabulary import SUBJECT_KEYS

from .enrollment_sync import CURRENT_STATUSES
from .models import Attendance, CounselorNote, Enrollment, Grade, Recommendation, Referral, Student

ADMIN = 'SchoolAdmin'  # ADR-0010 (renamed by students/0010); FastAPI auth.ADMIN must match
TEACHER = 'Teacher'  # Subject Teacher (ADR-0005)
GRADE_LEAD = 'GradeLead'  # ADR-0005; group created by setup_staff_roles; read since C5a
COUNSELOR = 'Counselor'  # ADR-0005; access via referrals (Slice 4a)
STUDENT = 'Student'  # Slice 4b: own grades and feedback only (account linked through Student.student_user)
PARENT = 'Parent'
ALL_ROLES = (ADMIN, TEACHER, GRADE_LEAD, PARENT, COUNSELOR, STUDENT)
# ADR-0012 / changes/0010: platform role (stage S1 creates the empty group only). Deliberately NOT in ALL_ROLES:
# ``roles_for`` and the FastAPI token do not recognise it yet, so adding it changes nobody's access.
PLATFORM_ADMIN = 'PlatformAdmin'


def roles_for(user):
    """Return the set of recognised roles held by ``user`` (empty for anonymous/unknown)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()
    if not user.is_active:   # an inactive account holds no role at all (owner decision 2026-10-23); the user object is the unit of trust (H4)
        return set()
    # Slice 0: a superuser is the PLATFORM account (schools, subscriptions, school-admin accounts in the Django admin). It
    # holds no school role by itself and therefore sees no student, grade or attendance data in the application.
    return set(user.groups.filter(name__in=ALL_ROLES).values_list('name', flat=True))


def has_any_role(user, *roles):
    return bool(roles_for(user) & set(roles))


def school_ids_for_admin(user):
    """Ids of the schools a SchoolAdmin administers (ADR-0012; stage S1: defined and tested, NOT used by any
    visibility rule yet; the SchoolAdmin branch of ``visible_*`` still returns everything until S3).

    Empty set for anonymous, inactive and superuser accounts, for users outside the ``SchoolAdmin`` group
    (checked on the group itself, never through ``roles_for``, which maps a superuser to SchoolAdmin), for ANY
    user who also holds ``PlatformAdmin`` (separation of duties; review findings G1/G2: the model check in
    ``SchoolMembership.clean`` runs only at creation, so the group is re-checked here) and for inactive
    memberships. Account state, groups and membership are all re-checked here, at query time. Callers must treat
    an empty set as "no school", never as "no filter" (review finding F3).
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()
    if not user.is_active or user.is_superuser:
        return set()
    held = set(user.groups.filter(name__in=(ADMIN, PLATFORM_ADMIN)).values_list('name', flat=True))
    if ADMIN not in held or PLATFORM_ADMIN in held:
        return set()
    from schools.models import SchoolMembership  # lazy: keeps the import graph acyclic

    return set(SchoolMembership.objects.filter(user=user, is_active=True).values_list('school_id', flat=True))


def _any(parts):
    """OR the non-empty parts; None when there is no part (callers treat None as 'grants nothing')."""
    parts = [p for p in parts if p is not None]
    return reduce(or_, parts) if parts else None


def _may_hold_scoped_grants(user):
    """Grade Lead / Subject Teacher grants apply only to an active, non-staff, non-superuser account, checked at
    query time (owner decision 2026-10-16); the assignment forms enforce the same rule only at creation."""
    return bool(user.is_active and not user.is_staff and not user.is_superuser)


def _current_enrollment(school_id, *extra, **conditions):
    """Q on ``Student``: the student has a CURRENT enrollment (open, status in ``CURRENT_STATUSES``) in the current
    academic year of ``school_id``, and ``school_id`` is also the student's own school (owner D-4-1, D-4-4).
    ``extra`` / ``conditions`` further filter the enrollment. An ``Exists`` subquery: no join duplicates, index-backed."""
    return Q(school_id=school_id) & Q(Exists(Enrollment.objects.filter(
        *extra, student_id=OuterRef('pk'), ended_on__isnull=True, status__in=CURRENT_STATUSES,
        academic_year__is_current=True, academic_year__school_id=school_id, **conditions)))


def _grade_lead_q(user, roles):
    """Students of (school, grade) for each ACTIVE assignment of the user (ADR-0005 §2; owner D-C5a-1).

    Matched through the CURRENT ENROLLMENT (ADR-0011, owner D-4-2): the enrollment's grade equals the assignment's
    grade and the current year's code equals the assignment's NORMALISED academic year; an enrollment class, when
    present, must be active. An unresolved or blank assignment year grants nothing (fail closed), and so does a
    student without a current enrollment. The group is re-checked here, so a row of a user who left the group
    grants nothing.
    """
    if GRADE_LEAD not in roles or not _may_hold_scoped_grants(user):
        return None
    from schools.models import GradeLeadAssignment  # lazy: keeps the import graph acyclic

    parts = []
    for school_id, grade, year in GradeLeadAssignment.objects.filter(user=user, is_active=True).values_list(
            'school_id', 'grade', 'academic_year'):
        status, code = normalize_academic_year(year)
        if status != RESOLVED:
            continue
        parts.append(_current_enrollment(
            school_id, Q(school_class__isnull=True) | Q(school_class__is_active=True),
            academic_year__code=code, grade=grade))
    return _any(parts)


def _teacher_assignments(user, roles):
    """Active assignments of a Subject Teacher: (school_id, class_id, subject). Blank/unknown subject = none."""
    if TEACHER not in roles or not _may_hold_scoped_grants(user):
        return []
    from schools.models import TeacherAssignment

    return list(TeacherAssignment.objects.filter(
        teacher=user, school_class__is_active=True, subject__in=SUBJECT_KEYS,
    ).values_list('school_class__school_id', 'school_class_id', 'subject'))


def _school_admin_q(user, roles):
    """Q on ``Student``: the students of the schools this SchoolAdmin administers (``school_ids_for_admin``: active
    membership, re-checked at query time). An EMPTY school set grants NOTHING (None), never "no filter" (S1 review F3).
    A superuser holds no school role (Slice 0)."""
    if ADMIN not in roles:
        return None
    school_ids = school_ids_for_admin(user)
    return Q(school_id__in=school_ids) if school_ids else None


def _counselor_q(user, roles):
    """Q on ``Student``: students with an OPEN referral to this counselor, in the counselor's own school (Slice 4a)."""
    if COUNSELOR not in roles or not _may_hold_scoped_grants(user):
        return None
    cases = Referral.objects.filter(counselor=user, status='open', school__staff__user=user)
    return Q(pk__in=cases.values('student_id'))


def _own_student_q(user, roles):
    """Q on ``Student``: the student's OWN record (role Student). NOT a full-detail grant: no identity fields, no attendance."""
    if STUDENT not in roles or not _may_hold_scoped_grants(user):
        return None
    return Q(student_user=user)


def _full_tier_q(user, roles):
    """Rows where the user holds a full-detail grant: SchoolAdmin (own schools), Parent (own child) or Grade Lead
    (own grade)."""
    return _any([_school_admin_q(user, roles), Q(parent_user=user) if PARENT in roles and user.is_active else None,
                 _grade_lead_q(user, roles), _counselor_q(user, roles)])


def grade_lead_students(user):
    """Students covered by the user's GRADE LEAD assignments ONLY (own school, own grade, current enrollment), never by any other
    grant the account may also hold (Parent, Teacher, SchoolAdmin...). Used by the password-reset page, which must not widen
    through a second role. Empty for a user who is not an active, non-staff Grade Lead."""
    scope = _grade_lead_q(user, roles_for(user))
    return Student.objects.filter(scope) if scope is not None else Student.objects.none()


def visible_students(user):
    """Students the user may read: the union of the user's grants. Deny by default.

    SchoolAdmin: the students of the schools of the user's active memberships (S3; none without a membership);
    a superuser: all (explicit temporary branch until S8). Parent: own children. Grade Lead: students of the assigned school whose current enrollment
    has the assigned grade, in the current year the assignment names. Subject Teacher: students whose current
    enrollment is in a class with an active assignment. Each row is annotated ``full_tier``: True where a full-detail grant covers it
    (SchoolAdmin, Parent, Grade Lead), False where only a Subject Teacher grant does. Field policy, search
    and attendance follow ``full_tier``, never the user's role names (non-widening, ADR-0005 §5).
    """
    roles = roles_for(user)
    full = _full_tier_q(user, roles)
    teacher = _any(
        _current_enrollment(school_id, school_class_id=class_id)
        for school_id, class_id, _subject in _teacher_assignments(user, roles)
    )
    scope = _any([full, teacher, _own_student_q(user, roles)])
    if scope is None:
        return Student.objects.none().annotate(full_tier=Value(False, output_field=BooleanField()))
    if full is None:
        tier = Value(False, output_field=BooleanField())
    else:
        tier = ExpressionWrapper(full, output_field=BooleanField())
    return Student.objects.filter(scope).annotate(full_tier=tier)


def visible_grades(user):
    """Grade rows the user may read: through a full-detail grant (all subjects) or through a Subject Teacher
    assignment (own subject, assigned class only)."""
    roles = roles_for(user)
    full = _full_tier_q(user, roles)
    parts = [Q(student__in=Student.objects.filter(full)) if full is not None else None]
    parts += [
        Q(student__in=Student.objects.filter(_current_enrollment(school_id, school_class_id=class_id)), subject=subject)
        for school_id, class_id, subject in _teacher_assignments(user, roles)
    ]
    own = _own_student_q(user, roles)
    if own is not None:
        parts.append(Q(student__in=Student.objects.filter(own)))
    scope = _any(parts)
    return Grade.objects.none() if scope is None else Grade.objects.filter(scope)


def visible_attendances(user):
    """Attendance rows: SchoolAdmin the own schools (superuser: all, until S8); Parent and Grade Lead for their full-detail students; a Subject
    Teacher sees none (owner D7)."""
    roles = roles_for(user)
    full = _full_tier_q(user, roles)
    if full is None:
        return Attendance.objects.none()
    return Attendance.objects.filter(student__in=Student.objects.filter(full))


def visible_recommendations(user):
    """Recommendations the user may read. Owner correction A4: a recommendation is STAFF-ONLY unless the teacher marked it
    ``visible_to_student``. SchoolAdmin, Grade Lead and Counselor (referred students) read all of their students'; a Subject
    Teacher reads the own; the student and the parents read only the student-visible ones. Deny by default."""
    roles = roles_for(user)
    staff = _any([_school_admin_q(user, roles), _grade_lead_q(user, roles), _counselor_q(user, roles)])
    parts = [Q(student__in=Student.objects.filter(staff)) if staff is not None else None]
    if PARENT in roles and user.is_active:
        parts.append(Q(student__parent_user=user, visible_to_student=True))
    own = _own_student_q(user, roles)
    if own is not None:
        parts.append(Q(student__in=Student.objects.filter(own), visible_to_student=True))
    if TEACHER in roles and _may_hold_scoped_grants(user):
        parts.append(Q(author=user, student__in=visible_students(user)))
    scope = _any(parts)
    return Recommendation.objects.none() if scope is None else Recommendation.objects.filter(scope)


def visible_referrals(user):
    """Referrals the user may read: SchoolAdmin those of the own schools, a Grade Lead the ones they made (for students still in
    their grade), a counselor their own open cases. Parents and teachers none."""
    roles = roles_for(user)
    admin = _school_admin_q(user, roles)
    parts = [Q(student__in=Student.objects.filter(admin)) if admin is not None else None]
    lead = _grade_lead_q(user, roles)
    if lead is not None:
        parts.append(Q(referred_by=user, student__in=Student.objects.filter(lead)))
    counselor = _counselor_q(user, roles)
    if counselor is not None:
        parts.append(Q(counselor=user, status='open', student__in=Student.objects.filter(counselor)))
    scope = _any(parts)
    return Referral.objects.none() if scope is None else Referral.objects.filter(scope)


def visible_counselor_notes(user):
    """Counselor notes (TEXT): the counselor of the (open) case, the Grade Lead of the student's grade (read-only, also after the
    referral is closed: owner decision 2026-10-26) and the school's SchoolAdmin ONLY while the referral is open (owner decision
    2026-10-28: after it is closed the SchoolAdmin gets metadata only, see ``counselor_note_metadata``). Teachers, parents and students never."""
    roles = roles_for(user)
    admin = _school_admin_q(user, roles)
    parts = [Q(referral__student__in=Student.objects.filter(admin), referral__status='open') if admin is not None else None]
    counselor = _counselor_q(user, roles)
    if counselor is not None:
        parts.append(Q(referral__counselor=user, referral__student__in=Student.objects.filter(counselor)))
    lead = _grade_lead_q(user, roles)   # read-only: there is no write path for a Grade Lead
    if lead is not None:
        parts.append(Q(referral__student__in=Student.objects.filter(lead)))
    scope = _any(parts)
    return CounselorNote.objects.none() if scope is None else CounselorNote.objects.filter(scope)


def counselor_note_metadata(user):
    """Notes of CLOSED referrals that the SchoolAdmin may know exist (existence and date only). Callers must read only ``created_at``
    from this queryset, never ``text``. Empty for every other role (the Grade Lead and the Counselor use ``visible_counselor_notes``)."""
    roles = roles_for(user)
    admin = _school_admin_q(user, roles)
    if admin is None:
        return CounselorNote.objects.none()
    return CounselorNote.objects.filter(referral__student__in=Student.objects.filter(admin), referral__status='closed')


def search_students(queryset, term):
    """Name search for every role; ``national_id`` is matched ONLY on full-tier rows, so a limited row can
    never be probed by identity (TEACHER_ACCESS_REVIEW R6). ``queryset`` comes from ``visible_students``."""
    for word in (term or '').split():
        queryset = queryset.filter(
            Q(first_name__icontains=word) | Q(last_name__icontains=word)
            | (Q(full_tier=True) & Q(national_id__icontains=word))
        )
    return queryset


# --- Intervention loop (change 0022): alerts, plans, follow-ups --------------------------------------------------------
# Reviewers/owners: SchoolAdmin (own schools), Grade Lead (own grade), Counselor (OPEN referral only). A Subject Teacher may
# only RAISE an alert and sees the alerts they raised. Parents and students see nothing. The text of an ``emotional`` plan and
# of its follow-ups is readable ONLY by the plan owner (who must still see the student through a Grade Lead or Counselor
# grant) and by a Counselor with an open referral; SchoolAdmin and Grade Lead otherwise get metadata only.

def _teacher_q(user, roles):
    """Q on ``Student``: students of the classes the Subject Teacher is assigned to (any subject)."""
    return _any(_current_enrollment(school_id, school_class_id=class_id)
                for school_id, class_id, _subject in _teacher_assignments(user, roles))


def _review_q(user, roles):
    """Q on ``Student``: students for whom the user may review alerts and create/own plans (never Teacher, Parent, Student)."""
    return _any([_school_admin_q(user, roles), _grade_lead_q(user, roles), _counselor_q(user, roles)])


def visible_behavior_notes(user):
    """Behavior log (0028 P5-3). SchoolAdmin and Grade Lead: every entry of their students. Subject Teacher: the entries they
    recorded, for students still in their classes. Parent: POSITIVE entries of own children only (owner decision 2026-11-01).
    Counselor and Student: nothing. Fail closed."""
    from .models import BehaviorNote

    roles = roles_for(user)
    parts = []
    staff = _any([_school_admin_q(user, roles), _grade_lead_q(user, roles)])
    if staff is not None:
        parts.append(Q(student__in=Student.objects.filter(staff)))
    teacher = _teacher_q(user, roles)
    if teacher is not None:
        parts.append(Q(recorded_by=user, student__in=Student.objects.filter(teacher)))
    if PARENT in roles and user.is_active:
        parts.append(Q(kind=BehaviorNote.POSITIVE, student__parent_user=user))
    scope = _any(parts)
    return BehaviorNote.objects.none() if scope is None else BehaviorNote.objects.filter(scope)


def behavior_writable_students(user):
    """Students an entry may be recorded for: SchoolAdmin and Grade Lead scope, and a Subject Teacher's classes."""
    roles = roles_for(user)
    scope = _any([_school_admin_q(user, roles), _grade_lead_q(user, roles), _teacher_q(user, roles)])
    return Student.objects.none() if scope is None else Student.objects.filter(scope)


def raisable_students(user):
    """Students an alert may be raised about: the review scope plus a Subject Teacher's own classes."""
    roles = roles_for(user)
    scope = _any([_review_q(user, roles), _teacher_q(user, roles)])
    return Student.objects.none() if scope is None else Student.objects.filter(scope)


def plan_students(user):
    """Students a plan may be created for (SchoolAdmin, Grade Lead, Counselor with an open referral)."""
    scope = _review_q(user, roles_for(user))
    return Student.objects.none() if scope is None else Student.objects.filter(scope)


def visible_alerts(user):
    """Alerts: reviewers see those of their students; a Subject Teacher only the ones they raised (for a student still in
    their classes). Fail closed: no grant, no rows."""
    from risk.models import Alert

    roles = roles_for(user)
    parts = []
    review = _review_q(user, roles)
    if review is not None:
        parts.append(Q(student__in=Student.objects.filter(review)))
    teacher = _teacher_q(user, roles)
    if teacher is not None:
        parts.append(Q(raised_by=user, student__in=Student.objects.filter(teacher)))
    scope = _any(parts)
    return Alert.objects.none() if scope is None else Alert.objects.filter(scope)


def reviewable_alerts(user):
    """Alerts the user may accept or dismiss: the review scope only (a teacher only raises)."""
    from risk.models import Alert

    review = _review_q(user, roles_for(user))
    return Alert.objects.none() if review is None else Alert.objects.filter(student__in=Student.objects.filter(review))


def visible_plans(user):
    """Plans (METADATA level: existence, type, status, dates, owner, outcome code) for the review scope. The text is gated
    separately: see ``visible_plan_texts`` / ``may_read_plan_text``."""
    from interventions.models import InterventionPlan

    review = _review_q(user, roles_for(user))
    if review is None:
        return InterventionPlan.objects.none()
    return InterventionPlan.objects.filter(student__in=Student.objects.filter(review))


def _text_scope(user, roles):
    """Q on ``InterventionPlan`` for plans whose text the user may read."""
    from interventions.models import InterventionPlan

    review = _review_q(user, roles)
    if review is None:
        return None
    students = Student.objects.filter(review)
    owner_grants = _any([_grade_lead_q(user, roles), _counselor_q(user, roles)])   # never the SchoolAdmin grant
    counselor = _counselor_q(user, roles)
    emotional = InterventionPlan.EMOTIONAL
    parts = [~Q(intervention_type=emotional) & Q(student__in=students)]
    if owner_grants is not None:
        parts.append(Q(intervention_type=emotional, owner=user, student__in=Student.objects.filter(owner_grants)))
    if counselor is not None:
        parts.append(Q(intervention_type=emotional, student__in=Student.objects.filter(counselor)))
    return _any(parts)


def visible_plan_texts(user):
    """Plans whose goal/action text the user may read (``emotional`` plans: owner or open-referral Counselor only)."""
    from interventions.models import InterventionPlan

    scope = _text_scope(user, roles_for(user))
    return InterventionPlan.objects.none() if scope is None else InterventionPlan.objects.filter(scope)


def may_read_plan_text(user, plan):
    return visible_plan_texts(user).filter(pk=plan.pk).exists()


def visible_followups(user):
    """Follow-ups whose text the user may read (same gate as the plan text)."""
    from interventions.models import InterventionFollowUp

    return InterventionFollowUp.objects.filter(plan__in=visible_plan_texts(user))


def may_edit_plan(user, plan):
    """Status changes and follow-ups: the plan owner (who can read it), or a SchoolAdmin on a non-emotional plan."""
    from interventions.models import InterventionPlan

    if not visible_plan_texts(user).filter(pk=plan.pk).exists():
        return False
    if plan.owner_id == user.pk:
        return True
    roles = roles_for(user)
    admin = _school_admin_q(user, roles)
    return (admin is not None and plan.intervention_type != InterventionPlan.EMOTIONAL
            and Student.objects.filter(admin, pk=plan.student_id).exists())


def may_cancel_or_reassign_plan(user, plan):
    """Metadata operations: the plan owner or the SchoolAdmin of the plan's school (emotional plans included; no text needed)."""
    if not visible_plans(user).filter(pk=plan.pk).exists():
        return False
    admin = _school_admin_q(user, roles_for(user))
    return plan.owner_id == user.pk or (admin is not None and Student.objects.filter(admin, pk=plan.student_id).exists())


def valid_plan_owner(owner, student, intervention_type):
    """Whether ``owner`` may own a plan of ``intervention_type`` for ``student``. The owner must see the student through a
    Grade Lead or Counselor grant; for an ``emotional`` plan a SchoolAdmin grant never counts, and a user who is also a
    SchoolAdmin is refused (the admin sees metadata only)."""
    from interventions.models import InterventionPlan

    roles = roles_for(owner)
    if intervention_type == InterventionPlan.EMOTIONAL:
        grants = _any([_grade_lead_q(owner, roles), _counselor_q(owner, roles)])
        if grants is None or _school_admin_q(owner, roles) is not None:
            return False
    else:
        grants = _review_q(owner, roles)
    return grants is not None and Student.objects.filter(grants, pk=student.pk).exists()


# --- Alert text policy (change 0022, F3, owner decision 2026-10-26) ------------------------------------------------------------
# For alerts of a sensitive type the MESSAGE and the reviewer's NOTE are readable only by the person who raised the alert and by a
# Counselor with an OPEN referral to the student. SchoolAdmin and Grade Lead see metadata only (type, severity, status, dates,
# dismiss reason code, who raised and reviewed) and can still accept or dismiss on that alone. The review NOTE of any alert is
# additionally never shown to a user who cannot review (a teacher sees status and reason code only).
SENSITIVE_ALERT_TYPES = ('emotional', 'family')


def visible_alert_texts(user):
    """Alerts whose message the user may read."""
    roles = roles_for(user)
    parts = [~Q(risk_event__risk_type__in=SENSITIVE_ALERT_TYPES), Q(raised_by=user)]
    counselor = _counselor_q(user, roles)
    if counselor is not None:
        parts.append(Q(student__in=Student.objects.filter(counselor)))
    return visible_alerts(user).filter(_any(parts))


def visible_alert_notes(user):
    """Alerts whose review note the user may read: the message gate AND the right to review."""
    return visible_alert_texts(user).filter(pk__in=reviewable_alerts(user).values('pk'))


def apply_alert_text_policy(user, alerts):
    """Blank the message / note of every alert the user may not read, in memory (never save these objects), and set
    ``text_hidden``. Views call this once on whatever they are about to render, so no template decides access."""
    alerts = list(alerts)
    ids = [a.pk for a in alerts]
    texts = set(visible_alert_texts(user).filter(pk__in=ids).values_list('pk', flat=True))
    notes = set(visible_alert_notes(user).filter(pk__in=ids).values_list('pk', flat=True))
    for alert in alerts:
        alert.text_hidden = alert.pk not in texts
        if alert.text_hidden:
            alert.message = ''
        if alert.pk not in notes:
            alert.review_note = ''
    return alerts


# ---- System read path (change 0025). The ONLY place that reads student data without a user. ----
# Rules: ONE explicit school id (never "all", never defaulted); only students with a CURRENT enrollment in that school (the
# same condition the role scopes use); read-only querysets; imported only by ``risk/rules.py`` (guard test in
# ``risk/test_system_scope.py``). A new caller needs a new review.
def system_scope_students(school):
    school_id = getattr(school, 'pk', school)
    if isinstance(school_id, bool) or not isinstance(school_id, int) or school_id <= 0:
        raise ValueError('system_scope_students needs one explicit school id')
    return Student.objects.filter(_current_enrollment(school_id))


def system_scope_attendance(school):
    return Attendance.objects.filter(student__in=system_scope_students(school))


def system_scope_grades(school):
    return Grade.objects.filter(student__in=system_scope_students(school))


def system_scope_enrollments(school):
    """The CURRENT enrollments (grade per student) of the system-scope students of one school."""
    school_id = getattr(school, 'pk', school)
    return Enrollment.objects.filter(
        student__in=system_scope_students(school_id), ended_on__isnull=True, status__in=CURRENT_STATUSES,
        academic_year__is_current=True, academic_year__school_id=school_id)
