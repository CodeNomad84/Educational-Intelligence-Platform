"""Fixed subject vocabulary shared by ``Grade.subject`` and ``TeacherAssignment.subject`` (ADR-0005 §3, D12).

One definition, owned by ``schools`` so that ``students`` (which already depends on ``schools``) re-exports it
without an import cycle. Changing a value here is a data migration, not a code edit: stored rows hold the key.
"""
SUBJECT_CHOICES = [
    ('math', 'ریاضی'), ('physics', 'فیزیک'), ('chemistry', 'شیمی'),
    ('biology', 'زیست‌شناسی'), ('literature', 'ادبیات فارسی'),
    ('arabic', 'عربی'), ('english', 'انگلیسی'), ('quran', 'قرآن'),
    ('religious', 'دینی'), ('history', 'تاریخ'), ('geography', 'جغرافیا'),
    ('social', 'اجتماعی'), ('sports', 'ورزش'), ('art', 'هنر'),
    ('computer', 'کامپیوتر'),
]
SUBJECT_KEYS = tuple(key for key, _label in SUBJECT_CHOICES)
