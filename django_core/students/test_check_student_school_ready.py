"""S6-1: ``check_student_school_ready`` is a read-only pre-flight for the NOT NULL migration (S6-2)."""
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from schools.models import School, SchoolClass

from .models import Student


def run(*args):
    out = StringIO()
    try:
        call_command('check_student_school_ready', '--json', *args, stdout=out)
        failed = False
    except CommandError:
        failed = True
    return json.loads(out.getvalue()), failed


class CheckStudentSchoolReadyTests(TestCase):
    def student(self, n, school=None, klass=None):
        return Student.objects.create(first_name=f'S{n}', last_name='T', national_id=f'93100000{n:02d}', grade=7,
                                      phone_number='0', school=school, school_class=klass)

    def test_ready_when_every_student_has_a_school(self):
        school = School.objects.order_by('pk').first()
        self.student(1, school)
        report, failed = run()
        self.assertEqual((report['ready'], failed, report['students_without_school']), (True, False, 0))
        self.assertEqual(report['students'], 1)


    def test_a_student_whose_school_differs_from_its_class_school_is_not_ready(self):
        a = School.objects.order_by('pk').first()
        b = School.objects.create(name='B', code='b')
        klass = SchoolClass.objects.create(school=a, title='7-A', academic_year='1404', grade=7)
        s = self.student(1, a, klass)
        Student.objects.filter(pk=s.pk).update(school=b)
        report, failed = run()
        self.assertEqual((report['ready'], failed, report['students_whose_school_differs_from_their_class_school']),
                         (False, True, 1))

    def test_the_report_has_counts_only_and_the_command_writes_nothing(self):
        school = School.objects.order_by('pk').first()
        self.student(1, school)
        before = list(Student.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as ctx:
            report, _failed = run()
        self.assertEqual(list(Student.objects.order_by('pk').values()), before)
        self.assertFalse([q for q in ctx.captured_queries if q['sql'].lstrip().upper().startswith(
            ('INSERT', 'UPDATE', 'DELETE', 'ALTER', 'CREATE', 'DROP'))])
        self.assertTrue(all(isinstance(v, (int, bool)) for v in report.values()))
        self.assertNotIn('S1', json.dumps(report))

    def test_text_output_ends_with_the_verdict(self):
        out = StringIO()
        call_command('check_student_school_ready', stdout=out)
        self.assertTrue(out.getvalue().strip().endswith('READY'))
