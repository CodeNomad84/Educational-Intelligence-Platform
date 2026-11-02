"""Audit log writer (2.4). ``record`` stores who/what/when only - never content (no names, notes, phone numbers, texts)."""
from .models import AuditEvent

# Action names (fixed vocabulary).
VIEW_360 = 'view_student_360'
NATIONAL_ID_REVEAL = 'national_id_reveal'   # explicit click on the masked id; object = the Student; no value stored
VIEW_DETAIL = 'view_student_detail'
VIEW_CASE = 'view_counselor_case'
COUNSELOR_NOTE_VIEW = 'counselor_note_view'    # detail = n<count of notes shown>; written only when note text is displayed; never the text
SHOW_PARENT_PHONES = 'show_parent_phones'
NOTE_ADD = 'counselor_note_add'
REFERRAL_CREATE = 'referral_create'
REFERRAL_CLOSE = 'referral_close'
GRADE_ADD = 'grade_add'
GRADE_DELETE = 'grade_delete'
RECOMMENDATION_ADD = 'recommendation_add'
STAFF_ACCOUNT_CREATE = 'staff_account_create'
STUDENT_ACCOUNT_CREATE = 'student_account_create'
BULK_ACCOUNTS = 'bulk_accounts'          # detail = counts only, e.g. s12p9t3e1
PASSWORD_RESET = 'password_reset'          # detail = who reset: gradelead | admin; object = the account; no password
PASSWORD_RESET_CAPPED = 'password_reset_capped'   # a grade lead hit the hourly cap (flag for the SchoolAdmin)
RESET_SETTING_CHANGE = 'reset_setting_change'     # detail = on | off
MODULE_CHANGE = 'module_change'              # detail = <module_key>:on|off|<end date>; object = the SchoolModule row
MISSION_ACTIVITY_CREATE = 'mission_activity_create'
MISSION_GRID_VIEW = 'mission_grid_view'
MISSION_GRID_SAVE = 'mission_grid_save'   # detail = counts only, e.g. s12o30d2
MISSION_REPORT_VIEW = 'mission_report_view'
MISSION_PLAN_SAVE = 'mission_plan_save'           # detail = number of paths
MISSION_CHOICES_SAVE = 'mission_choices_save'     # detail = number of rows
MISSION_MEETING_ADD = 'mission_meeting_add'
MISSION_AGGREGATE_VIEW = 'mission_aggregate_view'
MISSION_WEIGHTS_VIEW = 'mission_weights_view'
MISSION_WEIGHTS_SAVE = 'mission_weights_save'          # detail = v<version>
MISSION_WEIGHTS_SIMULATE = 'mission_weights_simulate'  # detail = n<students>
MISSION_WEIGHTS_STATUS = 'mission_weights_status'      # detail = <action>:v<version>
EXAM_TOPIC_ADD = 'exam_topic_add'
EXAM_QUESTION_SAVE = 'exam_question_save'      # detail = number of options
EXAM_QUESTION_STATUS = 'exam_question_status'  # detail = new status
EXAM_CREATE = 'exam_create'                    # detail = counts only, e.g. q5c2
EXAM_UNPUBLISH = 'exam_unpublish'
PLATFORM_OVERVIEW_VIEW = 'platform_overview_view'   # operator page; one event per school shown; detail a (all) | x (expiring filter)
EXAM_EDIT = 'exam_edit'                        # detail = counts only
EXAM_CSV_IMPORT = 'exam_csv_import'            # detail = counts only, e.g. c12e3
EXAM_RESULTS_VIEW = 'exam_results_view'        # teacher results of one exam
EXAM_GRADELEAD_VIEW = 'exam_gradelead_view'
EXAM_ADMIN_VIEW = 'exam_admin_view'
ALERT_RAISE = 'alert_raise'                    # detail = risk type
ALERT_REVIEW = 'alert_review'                  # detail = accepted | dismissed:<reason code>
ALERT_REOPEN = 'alert_reopen'
INTERVENTION_CREATE = 'intervention_create'    # detail = plan type
INTERVENTION_STATUS = 'intervention_status'    # detail = new status
INTERVENTION_OUTCOME = 'intervention_outcome'  # detail = outcome code
INTERVENTION_OWNER = 'intervention_owner'      # reassigned; no detail
FOLLOWUP_ADD = 'followup_add'                  # detail = assessment code
ALERT_TEXT_VIEW = 'alert_text_view'            # detail = risk type; a sensitive alert's message was shown to this user
INTERVENTION_VIEW = 'intervention_view'        # detail = text | meta (whether the text was shown)
RULE_CREATE = 'rule_create'                    # detail = <code> v<version>
RULE_EDIT = 'rule_edit'
RULE_STATUS = 'rule_status'                    # detail = new status
RULE_SIMULATE = 'rule_simulate'                # detail = counts only
RULE_RUN = 'rule_run'                          # detail = counts only; actor 'system' for the runner
RULE_SETTINGS = 'rule_settings'                # detail = changed keys only
STAFF_ROLES_CHANGE = 'staff_roles_change'  # detail = resulting roles, e.g. T,G
BEHAVIOR_NOTE_CREATE = 'behavior_note_create'  # detail = positive | concern; object = the BehaviorNote
REPORT_CARD_VIEW = 'report_card_view'      # detail = term:<code>; object = the Student
LIST_VIEW = 'list_view'                    # detail = <page>:n<rows shown>; one event per school among the rows; no row ids
LIST_PAGES = ('students', 'referrals', 'plans', 'alerts', 'api_students', 'attention')
SCHOOL_CREATE = 'school_create'            # detail = cmd | admin (which path created it); object = the School


SYSTEM = 'system'      # actor of scheduled / command runs (no user): stored as user=None, username 'system', roles 'system'


def record(user, action, obj=None, *, school=None, detail=''):
    """Append one event. ``school`` defaults to ``obj.school_id`` (a Student) or the student's school."""
    from students.access import roles_for

    if user == SYSTEM:
        school_id = getattr(school, 'pk', school)
        if school_id is None:
            raise ValueError('audit event without a school')
        return AuditEvent.objects.create(
            user=None, username=SYSTEM, roles=SYSTEM, school_id=school_id, action=action,
            object_type=type(obj).__name__ if obj is not None else '', object_id=str(getattr(obj, 'pk', '') or ''),
            detail=detail[:40])

    school_id = getattr(school, 'pk', school)
    if school_id is None and obj is not None:
        school_id = getattr(obj, 'school_id', None) or getattr(getattr(obj, 'student', None), 'school_id', None) \
            or getattr(getattr(obj, 'referral', None), 'school_id', None)
    if school_id is None:
        raise ValueError('audit event without a school')
    return AuditEvent.objects.create(
        user=user if getattr(user, 'pk', None) else None, username=getattr(user, 'username', '')[:150],
        roles=','.join(sorted(roles_for(user)))[:120], school_id=school_id, action=action,
        object_type=type(obj).__name__ if obj is not None else '', object_id=str(getattr(obj, 'pk', '') or ''),
        detail=detail[:40])


def record_list(user, page, rows):
    """A list of student records was shown: one ``list_view`` event per school among ``rows`` with the number of rows shown
    for it (C-L). Nothing is written for an empty list. ``rows`` is an unsliced queryset or an iterable of objects with
    ``school_id``."""
    from collections import Counter

    from django.db.models import QuerySet

    if page not in LIST_PAGES:
        raise ValueError(f'unknown list page {page!r}')
    if isinstance(rows, QuerySet) and not rows.query.is_sliced:
        counts = Counter(rows.order_by().values_list('school_id', flat=True))
    else:
        counts = Counter(row.school_id for row in rows)
    for school_id, shown in sorted(counts.items()):
        record(user, LIST_VIEW, school=school_id, detail=f'{page}:n{shown}')
