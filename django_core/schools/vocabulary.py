"""Fixed vocabularies: grade levels and subjects, shared by ``Grade.subject`` and ``TeacherAssignment.subject`` (ADR-0005 §3, D12).

One definition, owned by ``schools`` so that ``students`` (which already depends on ``schools``) re-exports it
without an import cycle. Changing a value here is a data migration, not a code edit: stored rows hold the key.
"""
GRADE_CHOICES = [
    (7, 'هفتم'), (8, 'هشتم'), (9, 'نهم'),
    (10, 'دهم'), (11, 'یازدهم'), (12, 'دوازدهم'),
]

SUBJECT_CHOICES = [
    ('math', 'ریاضی'), ('physics', 'فیزیک'), ('chemistry', 'شیمی'),
    ('biology', 'زیست‌شناسی'), ('literature', 'ادبیات فارسی'),
    ('arabic', 'عربی'), ('english', 'انگلیسی'), ('quran', 'قرآن'),
    ('religious', 'دینی'), ('history', 'تاریخ'), ('geography', 'جغرافیا'),
    ('social', 'اجتماعی'), ('sports', 'ورزش'), ('art', 'هنر'),
    ('computer', 'کامپیوتر'),
]
SUBJECT_KEYS = tuple(key for key, _label in SUBJECT_CHOICES)

# Classification of a stored ``TeacherAssignment.subject`` against the vocabulary (check command, C4b).
VALID, BLANK, EXACT_LABEL, UNMATCHED = 'valid', 'blank', 'exact_label', 'unmatched'
_BY_LABEL = {label: key for key, label in SUBJECT_CHOICES}


def classify_subject(value):
    """Return ``(status, key)``. Exact match only: no strip, no case folding, no fuzzy matching (decision 2).

    ``valid``: already a key. ``exact_label``: equals a Persian label exactly, ``key`` is its key.
    ``blank``: empty string. ``unmatched``: anything else (``key`` is None).
    """
    if value == '':
        return BLANK, None
    if value in SUBJECT_KEYS:
        return VALID, value
    if value in _BY_LABEL:
        return EXACT_LABEL, _BY_LABEL[value]
    return UNMATCHED, None
