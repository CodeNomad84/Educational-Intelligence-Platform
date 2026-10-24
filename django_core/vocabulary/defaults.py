"""Default terms per domain, used by ``seed_vocabulary``. They mirror the enums that exist in the code today (labels
unchanged) so a school starts with what it already sees; a school changes them by replacing terms, never by editing code.
``recommendation_tag`` has no enum yet: its defaults are placeholders taken from the demo intervention kinds (DECISION
REQUIRED: the owner / each school chooses the real set)."""
from .models import INTERVENTION_TYPE, OBSERVATION_CATEGORY, OBSERVATION_SENTIMENT, RECOMMENDATION_TAG

DEFAULTS = {
    OBSERVATION_CATEGORY: [("emotional", "عاطفی"), ("behavioral", "رفتاری"), ("academic", "آموزشی"), ("social", "اجتماعی"),
                           ("spiritual", "معنوی"), ("motivation", "انگیزشی")],
    OBSERVATION_SENTIMENT: [("positive", "مثبت"), ("neutral", "خنثی"), ("negative", "منفی")],
    INTERVENTION_TYPE: [("academic", "آموزشی"), ("behavioral", "رفتاری"), ("emotional", "عاطفی"), ("social", "اجتماعی")],
    RECOMMENDATION_TAG: [("counselor_meeting", "جلسهٔ مشاوره"), ("parent_contact", "تماس/جلسه با والدین"),
                         ("tutoring", "پشتیبانی درسی"), ("attendance_plan", "برنامهٔ پیگیری حضور")],
}
