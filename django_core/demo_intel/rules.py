# DEMO SCOPE — whole file.
# Configuration for the rule-based risk analysis prototype. No school-specific logic: change values here.
# Every threshold below is a DEMO ASSUMPTION, not a validated educational standard.

GRADE_SCALE_MAX = 20            # Iranian 0-20 scale (assumption — confirm with the school)

RECENT_DAYS = 30                # "last month" window for attendance / behaviour
BASELINE_DAYS = 60              # comparison window immediately before the recent one
GRADE_RECENT_DAYS = 45          # grades newer than this are "recent"
GRADE_EARLIER_DAYS = 120        # grades between GRADE_RECENT_DAYS and this are "earlier"

MIN_ATTENDANCE_RECORDS = 5      # per window, needed before comparing attendance
MIN_GRADES_FOR_AVERAGE = 3

# (threshold in percentage points, points) — first match wins, list from strictest
ABSENCE_SHIFT = [(20, 30), (10, 15)]
ABSENCE_HIGH_RATE = (15, 10)    # (rate %, points)
LATE_COUNT = (5, 5)             # (count in recent window, points)
SUBJECT_DROP = (3.0, 10)        # (score drop, points per subject)
SUBJECT_DROP_MAX_SUBJECTS = 2
LOW_AVERAGE = (12.0, 15)        # (average below, points)
NEGATIVE_OBSERVATIONS = [(4, 25), (2, 15)]  # (count in recent window, points)

PROTECTIVE_INTERVENTION = -10
PROTECTIVE_POSITIVE_OBSERVATIONS = (2, -5)  # (count, points)
INTERVENTION_LOOKBACK_DAYS = 120
IMPROVEMENT_ABSENCE_PP = 5
IMPROVEMENT_AVERAGE = 1.5

STRENGTH_HIGH_AVERAGE = 16.0
STRENGTH_LOW_ABSENCE = 3.0
STRENGTH_GROWTH = 2.0

LEVELS = [("HIGH", 60), ("MEDIUM", 30), ("LOW", 0)]  # (level, minimum score)
LEVEL_FA = {"HIGH": "پرخطر", "MEDIUM": "نیازمند توجه", "LOW": "کم‌خطر"}

# Persian names shown to users instead of internal rule ids.
RULE_FA = {
    "attendance_shift": "کاهش حضور و غیاب",
    "attendance_high": "غیبت زیاد",
    "late_count": "تأخیرهای مکرر",
    "subject_drop": "افت نمرهٔ درسی",
    "low_average": "میانگین پایین نمرات",
    "negative_observations": "مشاهدات رفتاری منفی",
    "intervention_improving": "بهبود پس از مداخله",
    "positive_observations": "مشاهدات مثبت",
}
