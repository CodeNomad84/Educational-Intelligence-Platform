"""The realistic synthetic seed: guards, determinism, shape, and what the tools say about its dirty data."""
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from schools.models import SchoolClass
from students.models import Enrollment, Student


FINGERPRINT = (58, 'e53dbae2fd4f2e42')  # scale 0.25; identical on two separate runs


def seed(scale=0.25):
    out = StringIO()
    call_command('seed_temporal_realistic', '--i-know-this-is-synthetic', '--scale', str(scale), stdout=out)
    return out.getvalue()


class SeedTests(TestCase):
    def test_guards(self):
        with self.assertRaises(CommandError):
            call_command('seed_temporal_realistic', stdout=StringIO())
        seed()
        with self.assertRaises(CommandError):
            seed()

    def test_shape_and_dirty_data_present(self):
        seed()
        self.assertGreater(Student.objects.count(), 40)
        self.assertTrue(Enrollment.objects.filter(source='import').exists())
        self.assertFalse(Enrollment.objects.filter(academic_year__is_current=True).exists())  # left to the backfill
        spellings = set(SchoolClass.objects.filter(title='7-A').values_list('academic_year', flat=True))
        self.assertGreaterEqual(len(spellings), 2)
        self.assertTrue(SchoolClass.objects.filter(academic_year='404').exists())
        self.assertGreater(Student.objects.filter(school_class__isnull=True).count(), 0)

    def test_deterministic(self):
        """Same inputs, same data: the fingerprint below changes only if the seed itself is changed on purpose."""
        import hashlib
        seed()
        rows = sorted(Student.objects.values_list('national_id', 'grade', 'school_class__title', 'school_class__academic_year'),
                      key=lambda r: r[0])
        digest = hashlib.sha256(repr(rows).encode('utf-8')).hexdigest()[:16]
        self.assertEqual((Student.objects.count(), digest), FINGERPRINT)

    def test_tools_surface_the_dirty_data_without_fixing_it(self):
        seed()
        call_command('backfill_enrollments', '--apply', stdout=StringIO())
        students = list(Student.objects.order_by('pk').values())
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command('check_access_switch_ready', '--json', stdout=out)
        pre = json.loads(out.getvalue())
        self.assertEqual(pre['verdict'], 'NOT READY')
        self.assertGreater(pre['students_class_grade_conflict_would_vanish'], 0)
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command('compare_access_parity', '--json', stdout=out)
        self.assertGreater(json.loads(out.getvalue())['unexplained'], 0)
        self.assertEqual(list(Student.objects.order_by('pk').values()), students)  # no tool changed a student
