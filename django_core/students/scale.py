"""P4-2: the grading scale of a school. ``RuleSettings.grade_scale_max`` (per school, set by the SchoolAdmin side) or the Iranian
default 20. Each ``Grade`` stores the scale it was entered under (``Grade.scale_max``), so a later change of the school's scale
never reinterprets old rows."""
DEFAULT_SCALE = 20


def school_scale(school_id):
    from risk.models import RuleSettings

    value = RuleSettings.objects.filter(school_id=school_id).values_list('grade_scale_max', flat=True).first()
    return value or DEFAULT_SCALE
