"""Default terms per domain, used by ``seed_vocabulary``. They mirror the enums that exist in the code today (labels
unchanged) so a school starts with what it already sees; a school changes them by replacing terms, never by editing code.
``recommendation_tag`` has no enum yet: its defaults are placeholders taken from the demo intervention kinds (DECISION
REQUIRED: the owner / each school chooses the real set)."""
from .models import (
    INTERVENTION_TYPE, MISSION_ACTIVITY_TYPE, MISSION_CONDITION, OBSERVATION_CATEGORY, OBSERVATION_SENTIMENT, RECOMMENDATION_TAG)

DEFAULTS = {
    OBSERVATION_CATEGORY: [("emotional", "عاطفی"), ("behavioral", "رفتاری"), ("academic", "آموزشی"), ("social", "اجتماعی"),
                           ("spiritual", "معنوی"), ("motivation", "انگیزشی")],
    OBSERVATION_SENTIMENT: [("positive", "مثبت"), ("neutral", "خنثی"), ("negative", "منفی")],
    INTERVENTION_TYPE: [("academic", "آموزشی"), ("behavioral", "رفتاری"), ("emotional", "عاطفی"), ("social", "اجتماعی")],
    RECOMMENDATION_TAG: [("counselor_meeting", "جلسهٔ مشاوره"), ("parent_contact", "تماس/جلسه با والدین"),
                         ("tutoring", "پشتیبانی درسی"), ("attendance_plan", "برنامهٔ پیگیری حضور")],
    # Mission module: placeholders a school replaces (DECISION REQUIRED: the real lists belong to the school).
    MISSION_ACTIVITY_TYPE: [("research", "پژوهش علمی"), ("art", "مهارت هنری"), ("digital", "مهارت دیجیتال"),
                            ("build", "ساخت و کارگاه"), ("group_project", "پروژهٔ گروهی"), ("presentation", "ارائه"),
                            ("responsibility", "مسئولیت کلاسی"), ("camp", "اردو")],
    MISSION_CONDITION: [("individual", "فعالیت انفرادی"), ("small_group", "گروه کوچک"), ("before_class", "مقابل کلاس"),
                        ("with_help", "با کمک معلم"), ("first_experience", "نخستین تجربه")],
}
