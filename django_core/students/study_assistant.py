"""DEMO STUB of the student study assistant (Slice 4b). NOT an AI model.

This module builds a short, rule-based study suggestion from the student's OWN grades, entirely inside Django and in memory:
it imports no HTTP/network client, calls no external service, stores nothing and logs nothing (the question is used only to
pick a subject and is thrown away). It exists so the student-facing UI can be shown on synthetic data. A real assistant
needs the approved AI policy and the audit log (2.4) first; until then this stub is the only thing behind the page.
"""
from collections import defaultdict

DEMO_STUB = True
STUB_NOTICE = ('نسخهٔ نمایشی (Stub): این پاسخ را یک قاعدهٔ ساده و محلی از روی نمرات خود شما می‌سازد، نه یک مدل هوش مصنوعی. '
               'هیچ داده‌ای از سیستم خارج نمی‌شود. برای تصمیم‌های مهم با معلم خود صحبت کنید.')
MAX_QUESTION = 300


def subject_summary(grades):
    """``{subject_key: (label, average, count, trend)}`` from ``Grade`` rows; trend = last score minus first (by date)."""
    by_subject = defaultdict(list)
    labels = {}
    for grade in sorted(grades, key=lambda g: (g.date, g.pk)):
        by_subject[grade.subject].append(grade.score)
        labels[grade.subject] = grade.get_subject_display()
    return {key: (labels[key], round(sum(v) / len(v), 2), len(v), round(v[-1] - v[0], 2)) for key, v in by_subject.items()}


def answer(question, summary):
    """Return a short suggestion. ``question`` only selects a subject if it names one; ``summary`` is ``subject_summary``."""
    if not summary:
        return 'هنوز نمره‌ای برای شما ثبت نشده است؛ پس از ثبت نمرات می‌توانم پیشنهاد مطالعه بدهم.'
    text = (question or '')[:MAX_QUESTION]
    chosen = next((key for key, (label, *_rest) in summary.items() if label in text or key in text.lower()), None)
    if chosen is None:
        chosen = min(summary, key=lambda key: summary[key][1])
        intro = 'ضعیف‌ترین درس شما در نمرات فعلی'
    else:
        intro = 'دربارهٔ درسی که نام بردید'
    label, average, count, trend = summary[chosen]
    if average >= 17:
        advice = 'عملکرد شما عالی است؛ با حل مسئله‌های چالشی سطح خود را حفظ کنید.'
    elif average >= 14:
        advice = 'وضعیت خوب است؛ مرور هفتگی و حل چند نمونه‌سؤال از مباحث اشتباه‌شده کمک می‌کند.'
    elif average >= 10:
        advice = 'مباحث پایه را دوباره مرور کنید و هر روز ۲۰ تا ۳۰ دقیقه تمرین کوتاه داشته باشید.'
    else:
        advice = 'بهتر است زودتر با معلم همین درس صحبت کنید و یک برنامهٔ مرور مرحله‌ای بنویسید.'
    direction = 'روند نمرات رو به بهبود است.' if trend > 0.5 else ('روند نمرات کاهشی است.' if trend < -0.5 else 'روند نمرات تقریباً ثابت است.')
    return f'{intro}: «{label}» با میانگین {average} (از {count} نمره). {direction} {advice}'
