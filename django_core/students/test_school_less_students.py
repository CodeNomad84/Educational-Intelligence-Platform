"""S6 requirement 1 (changes/0010) -- after S6-2 (students.0015, Student.school NOT NULL) a school-less student cannot exist,
so the negative tests that built one (API PATCH, admin edit, live import, dashboard form, ``save()`` guard cases) were
retired with the column change; while the column was nullable (S6-1, commits b4beb90 and 363f484) they proved that nothing
outside ``backfill_student_school`` could give an existing school-less student a school. What remains is the part that
is still observable: ``save()`` keeps working for new students and for students that have a school. The database-level
proof (create, bulk_create, bulk_update, update and raw SQL all fail on NULL) and the backfill tools against school-less
rows are in ``test_migration_0015``.
"""
from django.test import TestCase

from schools.models import School, SchoolClass

from .models import Student


class SaveKeepsWorkingTests(TestCase):
    def test_save_is_unchanged_for_new_students_and_students_that_have_a_school(self):
        school = School.objects.create(name='A', code='a')
        klass = SchoolClass.objects.create(school=school, title='7-A', academic_year='1404', grade=7)
        fresh = Student.objects.create(first_name='N', last_name='S', national_id='9300000002', grade=7,
                                       phone_number='0', school_class=klass)
        self.assertEqual(fresh.school_id, school.pk)
        fresh.school_class = None
        fresh.save()
        fresh.school_class = klass
        fresh.save()
        self.assertEqual(Student.objects.get(pk=fresh.pk).school_id, school.pk)
