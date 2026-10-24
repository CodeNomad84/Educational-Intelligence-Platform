"""Reference data of the mission-based selection model (owner-confirmed 2026-10-24) and its first parameter version.

Indicators and branches are the model's fixed vocabulary (global rows, created by migration 0002). The weight table below is
the owner-confirmed default; a school gets it as its first ACTIVE ``WeightSet`` (``seed_mission``) and changes it only by a
new version through the approval lifecycle. The numbers are PROPOSED weights, not scientifically validated.
"""
INDICATORS = [
    (1, 'کاوشگری و فهم عمیق'), (2, 'تحلیل و استدلال'), (3, 'خلاقیت و ایده‌پردازی'), (4, 'درک و آفرینش هنری'),
    (5, 'فهم فنی و ساختن'), (6, 'بیان و انتقال معنا'), (7, 'درک و همراهی با دیگران'), (8, 'تعامل و جلب همراهی'),
    (9, 'سازمان‌دهی و هماهنگی'), (10, 'تشخیص نیاز و راه‌حل'), (11, 'اقدام و پیگیری'), (12, 'یادگیری و سازگاری'),
]

SCIENCE, ECONOMY, CULTURE = 'science', 'economy', 'culture'
FIELD_CHOICES = [(SCIENCE, 'علمی'), (ECONOMY, 'اقتصادی'), (CULTURE, 'فرهنگی')]
BRANCHES = [   # (code, field, name) in table column order
    ('knowledge_production', SCIENCE, 'تولید دانش'), ('knowledge_application', SCIENCE, 'کاربردی‌سازی دانش'),
    ('knowledge_promotion', SCIENCE, 'ترویج دانش'), ('value_production', ECONOMY, 'تولید ارزش'),
    ('value_circulation', ECONOMY, 'گردش ارزش'), ('nurturing', CULTURE, 'پرورش'),
    ('culture_production', CULTURE, 'تولید'), ('culture_promotion', CULTURE, 'ترویج'),
]

# Rows = indicators 1..12, columns = BRANCHES in order. Every column sums to 100 (validated before a set leaves draft).
WEIGHTS = [
    [25, 10, 15, 5, 5, 5, 5, 5],
    [25, 20, 10, 10, 15, 5, 5, 5],
    [10, 15, 5, 10, 5, 5, 20, 10],
    [0, 0, 5, 5, 0, 0, 20, 5],
    [5, 15, 0, 15, 0, 5, 10, 0],
    [5, 5, 25, 5, 15, 15, 15, 20],
    [0, 0, 10, 5, 5, 20, 5, 10],
    [0, 0, 5, 5, 20, 10, 0, 20],
    [5, 5, 5, 10, 10, 10, 5, 10],
    [5, 15, 5, 15, 15, 10, 5, 5],
    [10, 5, 5, 10, 5, 5, 5, 5],
    [10, 10, 10, 5, 5, 10, 5, 5],
]

# First-version thresholds (owner decisions 2026-10-24: minimum 3 valid observations in 2 activities; notable difference 1.5).
MIN_OBSERVATIONS, MIN_ACTIVITIES, DIFF_THRESHOLD = 3, 2, '1.5'

# Fixed rows of the "activity choices" form (the owner's form); codes are stored, labels are shown.
CHOICE_CATEGORIES = [
    ('research', 'پژوهش علمی'), ('art', 'مهارت هنری'), ('digital', 'مهارت دیجیتال'), ('duty', 'مسئولیت کلاسی'), ('book', 'کتاب'),
    ('hobby', 'سرگرمی'), ('music', 'موسیقی'), ('sport', 'ورزش'), ('role_model', 'الگوی زندگی'),
]
