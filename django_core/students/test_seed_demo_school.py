from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from interventions.support import levels_for_user
from students.models import Student


class SeedDemoSchoolTests(TestCase):
    def test_seed_builds_all_support_levels_and_refuses_twice(self):
        out = StringIO()
        call_command('seed_demo_school', '--i-know-this-is-synthetic', '--password=x-demo-pass', '--scale=1.0', stdout=out)
        self.assertGreaterEqual(Student.objects.count(), 190)
        from django.contrib.auth import get_user_model
        admin = get_user_model().objects.get(username='demo_admin')
        levels = {v['level'] for v in levels_for_user(admin).values()}
        self.assertEqual(levels, {2, 3})
        with self.assertRaises(CommandError):
            call_command('seed_demo_school', '--i-know-this-is-synthetic', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('seed_demo_school', stdout=StringIO())

    def test_as_of_fixes_the_dates_and_a_bad_value_is_refused(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo_school', '--i-know-this-is-synthetic', '--as-of=nope', stdout=StringIO())
        call_command('seed_demo_school', '--i-know-this-is-synthetic', '--password=x', '--scale=0.2', '--as-of=2026-11-02', stdout=StringIO())
        from datetime import date
        from students.models import Attendance
        self.assertEqual(Attendance.objects.order_by('-date').first().date, date(2026, 11, 1))
