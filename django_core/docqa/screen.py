"""Keep student data out of documents and prompts (hard rule): refuses text that carries a national id, a mobile number, an e-mail or
the name of a student of the SAME school. A best-effort tripwire like the FastAPI filter (same normalisation); the real protection is
that only non-personal documents are accepted by an attested upload and that prompts are built from those documents alone."""
import re
import unicodedata

DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
LETTERS = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ۀ': 'ه', 'ة': 'ه', 'أ': 'ا', 'إ': 'ا', 'ؤ': 'و'})
PHONE = re.compile(r'(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)')
LONG_RUN = re.compile(r'\d{10,}')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
BETWEEN_DIGITS = re.compile(r'(?<=\d)[\s\-_.،,/()]+(?=\d)')


def normalize(text):
    text = unicodedata.normalize('NFKC', text).translate(DIGITS).translate(LETTERS)
    text = ''.join(ch for ch in text if unicodedata.category(ch) not in ('Cf', 'Mn', 'Cc') or ch in '\n\t ')
    return text.replace('ـ', '').casefold()


def student_names(school_id):
    """Full names (and last names of 3+ letters) of the school's students, normalised; read through the access layer by the caller's
    scope is not needed here: this is a screening list inside one school, never shown."""
    from students.models import Student
    names = set()
    for first, last in Student.objects.filter(school_id=school_id).values_list('first_name', 'last_name'):
        full = normalize(f'{first} {last}').strip()
        if len(full) >= 3:
            names.add(full)
        if len(normalize(last).strip()) >= 3:
            names.add(normalize(last).strip())
    return names


def screen_text(text, school_id, names=None):
    """Fixed reason codes (empty list = clean): national_id, phone, email, student_name."""
    flat = normalize(text)
    squeezed = BETWEEN_DIGITS.sub('', flat)
    reasons = []
    if LONG_RUN.search(squeezed):
        reasons.append('national_id')
    if PHONE.search(squeezed):
        reasons.append('phone')
    if EMAIL.search(flat):
        reasons.append('email')
    names = student_names(school_id) if names is None else names
    if any(name in flat for name in names):
        reasons.append('student_name')
    return reasons
