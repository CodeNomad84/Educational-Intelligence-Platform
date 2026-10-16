"""SYNTHETIC-ONLY data fix for the `seed_temporal_realistic` load (NOT a product tool, never run on real data).

Run inside a SCRATCH database through `manage.py shell`:
    python manage.py shell -c "exec(open('/app/_fix_large_tmp.py').read())"
It plays the role of the school admin who corrects the deliberate dirt of the seed, one category at a time, and
prints COUNTS only. The guards below make it refuse anything that is not the synthetic school and synthetic ids.
The real fixes are made by people in the admin site; the product tools never fix data on their own.
"""
from collections import Counter

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import School, SchoolClass
from students.enrollment_sync import ensure_current_enrollment
from students.models import Enrollment, Student

school = School.objects.get(code='synthetic-large')
assert not Student.objects.exclude(national_id__startswith='98').exists(), 'not a synthetic database'
current_code = school.academic_years.get(is_current=True).code


def year_code(text):
    status, code = normalize_academic_year(text)
    return code if status == RESOLVED else None


current_classes = {}
for klass in SchoolClass.objects.filter(school=school):
    if year_code(klass.academic_year) == current_code and klass.grade is not None:
        current_classes[(klass.grade, klass.title.split('-')[1])] = klass

# "continuing" = the student's LATEST earlier enrollment says promoted/retained (a student who was promoted once and
# later withdrew or transferred out is NOT continuing and must stay as is).
latest = {}
for student_id, status in Enrollment.objects.filter(academic_year__is_current=False).order_by(
        'academic_year__start_date').values_list('student_id', 'status'):
    latest[student_id] = status
continuing = {sid for sid, status in latest.items() if status in ('promoted', 'retained')}
fixed = Counter()
for s in Student.objects.select_related('school_class'):
    klass = s.school_class
    section = klass.title.split('-')[-1] if klass is not None and '-' in klass.title else 'A'
    target = current_classes.get((s.grade, section if (s.grade, section) in current_classes else 'A'))
    if klass is None:
        category = 'no_class'
    elif year_code(klass.academic_year) is None:
        category = 'unresolved_class_year'
    elif year_code(klass.academic_year) != current_code:
        if s.pk not in continuing:
            continue   # graduated / withdrawn / transferred out: the old link is just history
        category = 'past_year_mirror_of_a_continuing_student'
    elif klass.grade is not None and klass.grade != s.grade:
        category = 'class_grade_conflict'
    else:
        continue
    s.school_class = target
    s.save()
    ensure_current_enrollment(s, source='manual')
    fixed[category] += 1
print('SYNTHETIC FIX', dict(fixed))
