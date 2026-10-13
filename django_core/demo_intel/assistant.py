# DEMO SCOPE — whole file.
"""Educational Intelligence Assistant — Rule-Based Prototype Assistant (NOT an LLM).

Keyword intent matching over the output of engine.py. It answers only from demo data, never reads
counseling-note text (only that an intervention exists: kind, status, date), and every answer carries the
'rule-based, human review required' label. Names are matched as whole words; ambiguous or unknown names
are declined explicitly instead of guessing.
"""
import re

from django.urls import reverse

from students.models import Student

from . import rules as R
from .analytics import sort_by_attention
from .engine import analyze_students
from .models import InterventionRecord

LABEL = "Rule-Based Prototype Assistant"
DISCLAIMER = "تولیدشده از تحلیل قاعده‌محور (نمونهٔ اولیه) — بازبینی انسانی الزامی است."
AMBIGUOUS_MSG = "لطفاً نام کامل دانش‌آموز را وارد کنید"
UNKNOWN_MSG = "دانش‌آموزی با این نام پیدا نشد"
SUGGESTIONS = [
    "کدام دانش‌آموزان نیاز به توجه دارند؟",
    "چرا علی احمدی در معرض خطر است؟",
    "چه مداخله‌ای برای رضا کاظمی پیشنهاد می‌شود؟",
    "مهسا فرهادی چگونه بهتر شد؟",
    "وضعیت کلی مدرسه چطور است؟",
]

W_WHY = ("چرا", "دلیل", "علت", "why")
W_INTERVENTION = ("مداخله", "پیشنهاد", "توصیه", "اقدام", "intervention", "recommend")
W_SUMMARY = ("خلاصه", "وضعیت", "summar")
W_IMPROVE = ("بهتر", "بهبود", "پیشرفت", "improv")
W_ATTENTION = ("توجه", "ریسک", "خطر", "attention", "risk", "نیازمند", "بررسی")
W_CLASS = ("کلاس", "class")
W_OVERVIEW = ("مدرسه", "آمار", "overview", "چند", "توزیع", "کلی")


def _norm(text):
    text = (text or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return re.sub(r"\s+", " ", text.translate(table)).strip().lower()


def _resolve(query, students):
    """Return (status, candidates) with status in one|ambiguous|none. Whole-word matching only."""
    q = _norm(query)
    tokens = set(re.findall(r"\w+", q))
    full = [s for s in students
            if f"{_norm(s.first_name)} {_norm(s.last_name)}" in q or f"{_norm(s.last_name)} {_norm(s.first_name)}" in q]
    if len(full) == 1:
        return "one", full
    if len(full) > 1:
        return "ambiguous", full
    firsts = [s for s in students if _norm(s.first_name) in tokens]
    lasts = [s for s in students if _norm(s.last_name) in tokens]
    if firsts and lasts:  # both given but they do not form one student (e.g. first of A + last of B)
        return "ambiguous", firsts + [s for s in lasts if s not in firsts]
    pool = firsts or lasts
    if len(pool) == 1:
        return "one", pool
    if pool:
        return "ambiguous", pool
    return "none", []


def _row(student, result):
    return {
        "name": f"{student.first_name} {student.last_name}", "class": student.class_name,
        "level": result["level"], "level_fa": result["level_fa"], "score": result["score"],
        "url": reverse("dashboard:student_detail", args=[student.id]),
        "text": result["reasons"][0]["text"] if result["reasons"] else "",
    }


def _improvement(ans, s, r):
    m = r["metrics"]
    name = f"{s.first_name} {s.last_name}"
    ans["title"] = f"روند بهبود {name}"
    prev, now, evidence = [], [], []
    if m["absence_baseline"] is not None and m["absence_recent"] is not None:
        prev.append(f"نرخ غیبت {m['absence_baseline']:.0f}٪")
        now.append(f"نرخ غیبت {m['absence_recent']:.0f}٪")
        if m["absence_baseline"] - m["absence_recent"] >= R.IMPROVEMENT_ABSENCE_PP:
            evidence.append(f"کاهش غیبت از {m['absence_baseline']:.0f}٪ به {m['absence_recent']:.0f}٪")
    if m["avg_earlier"] is not None and m["avg_recent"] is not None:
        prev.append(f"میانگین نمرات {m['avg_earlier']:.1f}")
        now.append(f"میانگین نمرات {m['avg_recent']:.1f}")
        if m["avg_recent"] - m["avg_earlier"] >= R.IMPROVEMENT_AVERAGE:
            evidence.append(f"افزایش میانگین نمرات از {m['avg_earlier']:.1f} به {m['avg_recent']:.1f}")
    if m["positive_obs_recent"]:
        evidence.append(f"{m['positive_obs_recent']} مشاهدهٔ مثبت اخیر معلمان")
    itv = list(InterventionRecord.objects.filter(student=s).order_by("start_date"))
    bullets = []
    if prev:
        bullets.append("وضعیت قبلی: " + "، ".join(prev))
    if itv:
        bullets.append("مداخله: " + "؛ ".join(
            f"{i.get_kind_display()} ({i.get_status_display()}، از {i.start_date:%Y-%m-%d})" for i in itv))
    else:
        bullets.append("مداخلهٔ ثبت‌شده‌ای وجود ندارد.")
    if now:
        bullets.append("وضعیت فعلی: " + "، ".join(now))
    if evidence:
        bullets.append("شواهد بهبود: " + "؛ ".join(evidence))
        ans["paragraphs"].append(
            "این شواهد همزمانی بهبود با مداخله را نشان می‌دهد؛ اثبات اثر مداخله نیست و نیاز به قضاوت مشاور دارد.")
    else:
        ans["paragraphs"].append("در داده‌های موجود شواهد روشنی از بهبود دیده نمی‌شود.")
    ans["bullets"] = bullets
    ans["rows"] = [_row(s, r)]


def answer(query, today=None):
    students = list(Student.objects.all())
    results = analyze_students(students, today)
    q = _norm(query)
    ans = {"query": query, "title": "", "paragraphs": [], "rows": [], "bullets": [], "label": LABEL,
           "sources": ["نتایج موتور قاعده‌محور بر روی حضور و غیاب، نمرات و مشاهدات (داده‌های نمایشی مصنوعی)"],
           "disclaimer": DISCLAIMER}
    if not q:
        return _unsupported(ans)

    has = lambda *words: any(_norm(w) in q for w in words)  # noqa: E731
    status, found = _resolve(query, students)
    general = has(*W_ATTENTION, *W_CLASS, *W_OVERVIEW)
    asks_student = has(*W_WHY, *W_INTERVENTION, *W_SUMMARY, *W_IMPROVE)

    if status == "one":
        s = found[0]
        r = results[s.id]
        name = f"{s.first_name} {s.last_name}"
        if has(*W_IMPROVE):
            _improvement(ans, s, r)
        elif has(*W_WHY):
            ans["title"] = f"چرا {name} در سطح «{r['level_fa']}» قرار دارد؟"
            if r["reasons"]:
                ans["bullets"] = [f"{x['text']} ({x['points']} امتیاز)" for x in r["reasons"]]
            else:
                ans["paragraphs"].append("هیچ قاعدهٔ ریسکی فعال نشده است؛ داده‌ها نشانهٔ نگرانی خاصی نشان نمی‌دهند.")
            ans["paragraphs"].append(f"امتیاز کل: {r['score']} از ۱۰۰ — اطمینان داده: {r['confidence']}.")
            ans["rows"] = [_row(s, r)]
        elif has(*W_INTERVENTION):
            ans["title"] = f"اقدامات پیشنهادی برای {name}"
            ans["bullets"] = r["recommendations"]
            if r["has_active_intervention"]:
                ans["paragraphs"].append("توجه: برای این دانش‌آموز مداخلهٔ فعال ثبت شده است.")
            ans["rows"] = [_row(s, r)]
        elif has(*W_SUMMARY):
            m = r["metrics"]
            ans["title"] = f"خلاصهٔ وضعیت {name}"
            parts = [f"سطح ریسک: {r['level_fa']} (امتیاز {r['score']})."]
            if m["avg_recent"] is not None:
                parts.append(f"میانگین نمرات اخیر {m['avg_recent']:.1f}.")
            if m["absence_recent"] is not None:
                parts.append(f"نرخ غیبت ۳۰ روز اخیر {m['absence_recent']:.0f}٪.")
            ans["paragraphs"] = [" ".join(parts)]
            ans["bullets"] = [f"نگرانی: {x['text']}" for x in r["reasons"] if x["kind"] == "risk"] + \
                             [f"نقطهٔ قوت: {x}" for x in r["strengths"]]
            ans["rows"] = [_row(s, r)]
        else:
            ans["title"] = f"اطلاعات مربوط به {name}"
            ans["paragraphs"] = [f"سطح ریسک: {r['level_fa']} (امتیاز {r['score']}). برای جزئیات بپرسید: «چرا …؟»، "
                                 "«چه مداخله‌ای …؟» یا «… چگونه بهتر شد؟»."]
            ans["rows"] = [_row(s, r)]
        return ans

    if status == "ambiguous" and (asks_student or not general):
        ans["title"] = AMBIGUOUS_MSG
        ans["paragraphs"] = ["نام واردشده با بیش از یک دانش‌آموز مطابقت دارد یا کامل نیست."]
        ans["bullets"] = [f"{s.first_name} {s.last_name} (کلاس {s.class_name})" for s in found[:6]]
        return ans

    # A question that is about one student ("why…", "how did … improve…") but names nobody we know must be
    # declined explicitly, even when it contains risk words such as "در معرض خطر".
    student_specific = has(*W_WHY, *W_IMPROVE) or (has(*W_INTERVENTION, *W_SUMMARY) and not general)
    if status == "none" and student_specific:
        ans["title"] = UNKNOWN_MSG
        ans["paragraphs"] = ["نام دانش‌آموز را به فارسی و به‌صورت کامل (نام و نام خانوادگی) وارد کنید."]
        ans["bullets"] = SUGGESTIONS[:3]
        return ans

    if general and has(*W_CLASS) and not has(*W_ATTENTION):
        cls = next((c for c in {s.class_name for s in students} if _norm(c) in q), None)
        if cls:
            members = [s for s in students if s.class_name == cls]
            flagged = [s for s in sort_by_attention(members, results) if results[s.id]["level"] != "LOW"]
            ans["title"] = f"وضعیت کلاس {cls}"
            ans["paragraphs"] = [f"{len(members)} دانش‌آموز؛ {len(flagged)} نفر نیازمند توجه."]
            ans["rows"] = [_row(s, results[s.id]) for s in flagged]
            return ans
        return _unsupported(ans)

    if has(*W_ATTENTION):
        flagged = [s for s in sort_by_attention(students, results) if results[s.id]["level"] != "LOW"]
        ans["title"] = "دانش‌آموزانی که نیاز به توجه دارند"
        ans["paragraphs"] = [
            f"بر اساس روند حضور، نمرات و مشاهدات، {len(flagged)} نفر از {len(students)} دانش‌آموز نیازمند بازبینی هستند."]
        ans["rows"] = [_row(s, results[s.id]) for s in flagged]
        return ans

    if has(*W_OVERVIEW):
        dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for r in results.values():
            dist[r["level"]] += 1
        ans["title"] = "وضعیت کلی مدرسه"
        ans["paragraphs"] = [f"از {len(students)} دانش‌آموز: {dist['HIGH']} پرخطر، {dist['MEDIUM']} نیازمند توجه، "
                             f"{dist['LOW']} کم‌خطر."]
        return ans

    return _unsupported(ans)


def _unsupported(ans):
    ans["title"] = "این پرسش در نسخهٔ نمایشی پشتیبانی نمی‌شود"
    ans["paragraphs"] = ["دستیار نمونهٔ اولیه فقط از داده‌های موجود پاسخ می‌دهد. نمونه پرسش‌های پشتیبانی‌شده:"]
    ans["bullets"] = SUGGESTIONS
    return ans
