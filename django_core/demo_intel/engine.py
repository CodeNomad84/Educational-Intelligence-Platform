# DEMO SCOPE — whole file.
"""Explainable rule-based student risk analysis (PROTOTYPE).

Deterministic and transparent: every point of the score comes from a named rule in rules.py and is
returned with the numbers that triggered it. No ML, no LLM, no hidden state.

Boundary (docs/AI_GOVERNANCE.md): counseling-note TEXT is never read here. The engine only sees that an
intervention record exists. Output is advisory and always requires human review.
"""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from students.models import Attendance, Grade, Student

from . import rules as R
from .models import InterventionRecord, StudentObservation

SUBJECT_FA = dict(Grade.SUBJECT_CHOICES)
CATEGORY_FA = dict(StudentObservation.Category.choices)


def _pct(part, whole):
    return (part / whole * 100.0) if whole else None


def _avg(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _level_for(score):
    for level, minimum in R.LEVELS:
        if score >= minimum:
            return level
    return "LOW"


def _analyze(student, attendances, grades, observations, interventions, today):
    recent_start = today - timedelta(days=R.RECENT_DAYS)
    base_start = recent_start - timedelta(days=R.BASELINE_DAYS)
    g_recent_start = today - timedelta(days=R.GRADE_RECENT_DAYS)
    g_earlier_start = today - timedelta(days=R.GRADE_EARLIER_DAYS)

    att_recent = [a for a in attendances if a.date > recent_start]
    att_base = [a for a in attendances if base_start < a.date <= recent_start]
    abs_recent = _pct(sum(a.status == "absent" for a in att_recent), len(att_recent))
    abs_base = _pct(sum(a.status == "absent" for a in att_base), len(att_base))
    lates_recent = sum(a.status == "late" for a in att_recent)

    g_recent = [g for g in grades if g.date > g_recent_start]
    g_earlier = [g for g in grades if g_earlier_start < g.date <= g_recent_start]
    avg_recent = _avg(g.score for g in g_recent)
    avg_earlier = _avg(g.score for g in g_earlier)

    obs_recent = [o for o in observations if o.date > recent_start]
    negative = [o for o in obs_recent if o.sentiment == "negative"]
    positive = [o for o in obs_recent if o.sentiment == "positive"]

    score = 0
    reasons = []      # dicts: rule, kind (risk|protective), points, text
    recs = []
    strengths = []

    def add(rule, points, text, kind="risk"):
        nonlocal score
        score += points
        reasons.append({"rule": rule, "rule_fa": R.RULE_FA.get(rule, rule), "kind": kind,
                        "points": points, "text": text})

    # --- Attendance -------------------------------------------------------------------------------
    attendance_triggered = False
    if (abs_recent is not None and abs_base is not None
            and len(att_recent) >= R.MIN_ATTENDANCE_RECORDS and len(att_base) >= R.MIN_ATTENDANCE_RECORDS):
        shift = abs_recent - abs_base
        for threshold, points in R.ABSENCE_SHIFT:
            if shift >= threshold:
                add("attendance_shift", points,
                    f"افت حضور: نرخ غیبت ۳۰ روز اخیر {abs_recent:.0f}٪ در برابر {abs_base:.0f}٪ در دورهٔ قبل "
                    f"(افزایش {shift:.0f} واحد درصد)")
                attendance_triggered = True
                break
    if abs_recent is not None and len(att_recent) >= R.MIN_ATTENDANCE_RECORDS and abs_recent > R.ABSENCE_HIGH_RATE[0]:
        add("attendance_high", R.ABSENCE_HIGH_RATE[1],
            f"نرخ غیبت ۳۰ روز اخیر بیش از {R.ABSENCE_HIGH_RATE[0]}٪ است ({abs_recent:.0f}٪)")
        attendance_triggered = True
    if lates_recent >= R.LATE_COUNT[0]:
        add("late_count", R.LATE_COUNT[1], f"{lates_recent} بار تأخیر در ۳۰ روز اخیر")
        attendance_triggered = True

    # --- Academic ---------------------------------------------------------------------------------
    academic_triggered = False
    by_subject_recent, by_subject_earlier = defaultdict(list), defaultdict(list)
    for g in g_recent:
        by_subject_recent[g.subject].append(g.score)
    for g in g_earlier:
        by_subject_earlier[g.subject].append(g.score)
    drops = []
    for subject, scores in by_subject_recent.items():
        if subject in by_subject_earlier:
            drop = _avg(by_subject_earlier[subject]) - _avg(scores)
            if drop >= R.SUBJECT_DROP[0]:
                drops.append((drop, subject, _avg(by_subject_earlier[subject]), _avg(scores)))
    drops.sort(reverse=True)
    weak_subjects = []
    for drop, subject, earlier, recent in drops[:R.SUBJECT_DROP_MAX_SUBJECTS]:
        add("subject_drop", R.SUBJECT_DROP[1],
            f"افت نمرهٔ {SUBJECT_FA.get(subject, subject)}: میانگین از {earlier:.1f} به {recent:.1f} "
            f"(کاهش {drop:.1f} نمره)")
        weak_subjects.append(SUBJECT_FA.get(subject, subject))
        academic_triggered = True
    if avg_recent is not None and len(g_recent) >= R.MIN_GRADES_FOR_AVERAGE and avg_recent < R.LOW_AVERAGE[0]:
        add("low_average", R.LOW_AVERAGE[1],
            f"میانگین نمرات اخیر {avg_recent:.1f} از {R.GRADE_SCALE_MAX} است (کمتر از {R.LOW_AVERAGE[0]:.0f})")
        academic_triggered = True

    # --- Behaviour --------------------------------------------------------------------------------
    behavior_triggered = False
    for count, points in R.NEGATIVE_OBSERVATIONS:
        if len(negative) >= count:
            cats = defaultdict(int)
            for o in negative:
                cats[CATEGORY_FA.get(o.category, o.category)] += 1
            detail = "، ".join(f"{k} ({v})" for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))
            add("negative_observations", points,
                f"{len(negative)} مشاهدهٔ منفی در ۳۰ روز اخیر — {detail}")
            behavior_triggered = True
            break

    # --- Protective factors -----------------------------------------------------------------------
    lookback = today - timedelta(days=R.INTERVENTION_LOOKBACK_DAYS)
    relevant = [i for i in interventions
                if i.status in ("active", "completed") and i.start_date >= lookback]
    improving = bool(
        (abs_base is not None and abs_recent is not None and abs_base - abs_recent >= R.IMPROVEMENT_ABSENCE_PP)
        or (avg_recent is not None and avg_earlier is not None and avg_recent - avg_earlier >= R.IMPROVEMENT_AVERAGE)
    )
    intervention_helping = False
    if relevant and improving:
        kind = relevant[0].get_kind_display()
        add("intervention_improving", R.PROTECTIVE_INTERVENTION,
            f"پس از «{kind}» نشانه‌های بهبود دیده می‌شود (کاهش غیبت یا افزایش نمره)", kind="protective")
        strengths.append(f"بهبود پس از مداخله ({kind})")
        intervention_helping = True
    if len(positive) >= R.PROTECTIVE_POSITIVE_OBSERVATIONS[0]:
        add("positive_observations", R.PROTECTIVE_POSITIVE_OBSERVATIONS[1],
            f"{len(positive)} مشاهدهٔ مثبت در ۳۰ روز اخیر", kind="protective")
        strengths.append(f"{len(positive)} مشاهدهٔ مثبت اخیر معلمان")

    # --- Strengths (informational, no points) -----------------------------------------------------
    if avg_recent is not None and avg_recent >= R.STRENGTH_HIGH_AVERAGE:
        strengths.append(f"میانگین نمرات اخیر بالا ({avg_recent:.1f} از {R.GRADE_SCALE_MAX})")
    if avg_recent is not None and avg_earlier is not None and avg_recent - avg_earlier >= R.STRENGTH_GROWTH:
        strengths.append(f"روند صعودی نمرات (+{avg_recent - avg_earlier:.1f})")
    if abs_recent is not None and len(att_recent) >= R.MIN_ATTENDANCE_RECORDS and abs_recent <= R.STRENGTH_LOW_ABSENCE:
        strengths.append("حضور منظم در ۳۰ روز اخیر")

    score = max(0, min(100, score))
    level = _level_for(score)

    # --- Recommendations (derived only from triggered rules) --------------------------------------
    if attendance_triggered:
        recs += ["تعریف برنامهٔ پیگیری حضور و غیاب", "تماس یا جلسه با والدین برای بررسی علت غیبت‌ها"]
    if academic_triggered:
        subj = ("در " + "، ".join(weak_subjects)) if weak_subjects else "در دروس ضعیف"
        recs.append(f"پشتیبانی درسی / کلاس تقویتی {subj}")
    if behavior_triggered:
        recs += ["جلسهٔ مشاوره با دانش‌آموز", "گفت‌وگوی هماهنگ معلمان دربارهٔ مشاهدات رفتاری"]
    if level == "HIGH":
        recs.append("بازبینی پرونده توسط مشاور و معاون در هفتهٔ جاری")
    if intervention_helping:
        recs.append("ادامهٔ مداخلهٔ فعلی و ثبت نتیجه؛ بازارزیابی پس از ۳۰ روز")
    if not recs:
        recs.append("ادامهٔ پایش عادی؛ اقدام ویژه‌ای لازم نیست")
    recs = list(dict.fromkeys(recs))

    confident = len(att_recent) >= 10 and len(g_recent) + len(g_earlier) >= 8
    return {
        "student_id": student.id,
        "level": level,
        "level_fa": R.LEVEL_FA[level],
        "score": score,
        "reasons": reasons,
        "strengths": strengths,
        "recommendations": recs,
        "metrics": {
            "absence_recent": abs_recent,
            "absence_baseline": abs_base,
            "lates_recent": lates_recent,
            "avg_recent": avg_recent,
            "avg_earlier": avg_earlier,
            "negative_obs_recent": len(negative),
            "positive_obs_recent": len(positive),
            "attendance_records_recent": len(att_recent),
            "grades_used": len(g_recent) + len(g_earlier),
        },
        "confidence": "متوسط" if confident else "کم (داده ناکافی)",
        "has_active_intervention": any(i.status == "active" for i in interventions),
    }


def analyze_students(students=None, today=None):
    """Return {student_id: result} using a constant number of queries."""
    today = today or timezone.localdate()
    students = list(students if students is not None else Student.objects.all())
    ids = [s.id for s in students]
    att, grd, obs, itv = (defaultdict(list) for _ in range(4))
    for a in Attendance.objects.filter(student_id__in=ids):
        att[a.student_id].append(a)
    for g in Grade.objects.filter(student_id__in=ids):
        grd[g.student_id].append(g)
    for o in StudentObservation.objects.filter(student_id__in=ids):
        obs[o.student_id].append(o)
    for i in InterventionRecord.objects.filter(student_id__in=ids):
        itv[i.student_id].append(i)
    return {s.id: _analyze(s, att[s.id], grd[s.id], obs[s.id], itv[s.id], today) for s in students}


def analyze_student(student, today=None):
    return analyze_students([student], today)[student.id]
