"""Stage 2.2a-1 tests: year normalisation, AcademicYear constraints, check_academic_years (ADR-0011)."""
import json
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from .academic_years import BLANK, RESOLVED, UNRESOLVED, normalize_academic_year, year_for_date
from .models import AcademicYear, GradeLeadAssignment, School, SchoolClass


class NormaliseTests(SimpleTestCase):
    def test_variants_resolve_to_one_code(self):
        for raw in ("1404", "1404-1405", "1404/1405", "1404 - 1405", "1404-05", "1404_1405", "1404–1405",
                    "۱۴۰۴", "۱۴۰۴-۱۴۰۵", "۱۴۰۴/۰۵", "١٤٠٤-١٤٠٥", " 1404 "):
            self.assertEqual(normalize_academic_year(raw), (RESOLVED, "1404-1405"), raw)

    def test_blank(self):
        for raw in ("", "  ", None):
            self.assertEqual(normalize_academic_year(raw), (BLANK, None))

    def test_unresolved_are_never_guessed(self):
        for raw in ("404", "14", "1404-1407", "1404-06", "2025-2026", "2025", "1500", "1299", "year one",
                    "1404-1405-1406", "14041405", "1404x", "ab-cd"):
            self.assertEqual(normalize_academic_year(raw), (UNRESOLVED, None), raw)

    def test_century_wrap(self):
        self.assertEqual(normalize_academic_year("1399-00"), (RESOLVED, "1399-1400"))
        self.assertEqual(normalize_academic_year("1399/1400"), (RESOLVED, "1399-1400"))

    def test_year_for_date(self):
        ranges = [("1403-1404", date(2024, 9, 23), date(2025, 6, 21)), ("1404-1405", date(2025, 9, 23), date(2026, 6, 21))]
        self.assertEqual(year_for_date(ranges, date(2025, 1, 1)), ["1403-1404"])
        self.assertEqual(year_for_date(ranges, date(2025, 7, 1)), [])
        self.assertEqual(year_for_date(ranges + [("x", date(2025, 1, 1), date(2025, 12, 31))], date(2025, 10, 1)),
                         ["1404-1405", "x"])


class AcademicYearModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="A", code="a")
        self.other = School.objects.create(name="B", code="b")

    def make(self, **kw):
        data = dict(school=self.school, code="1404-1405", start_date=date(2025, 9, 23), end_date=date(2026, 6, 21))
        data.update(kw)
        return AcademicYear(**data)

    def test_valid(self):
        self.make().full_clean()

    def test_code_must_be_canonical(self):
        for code in ("1404", "1404-05", "۱۴۰۴-۱۴۰۵", "1404-1406"):
            with self.assertRaises(ValidationError) as ctx:
                self.make(code=code).full_clean()
            self.assertIn("code", ctx.exception.message_dict, code)

    def test_end_after_start_and_overlap(self):
        with self.assertRaises(ValidationError):
            self.make(end_date=date(2025, 9, 23)).full_clean()
        self.make().save()
        with self.assertRaises(ValidationError) as ctx:
            self.make(code="1403-1404", start_date=date(2026, 6, 1), end_date=date(2026, 12, 1)).full_clean()
        self.assertIn("start_date", ctx.exception.message_dict)
        # same dates in ANOTHER school are fine
        self.make(school=self.other).full_clean()

    def test_one_current_year_per_school(self):
        self.make(is_current=True).save()
        nxt = self.make(code="1405-1406", start_date=date(2026, 9, 23), end_date=date(2027, 6, 21), is_current=True)
        with self.assertRaises(ValidationError) as ctx:
            nxt.full_clean()
        self.assertIn("is_current", ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            nxt.save()  # the database constraint holds even without full_clean
        self.make(school=self.other, is_current=True).save()

    def test_unique_code_per_school_and_db_end_check(self):
        self.make().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(start_date=date(2030, 1, 1), end_date=date(2030, 12, 1)).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(code="1500-1501", end_date=date(2025, 9, 1)).save()


class CheckAcademicYearsTests(TestCase):
    def report(self):
        out = StringIO()
        call_command('check_academic_years', '--json', stdout=out)
        return json.loads(out.getvalue())

    def test_empty(self):
        r = self.report()
        self.assertEqual((r['class_rows'], r['academic_year_rows']), (0, 0))

    def test_counts_variants_unresolved_and_missing_rows_without_writing(self):
        school = School.objects.create(name="A", code="a")
        for i, year in enumerate(["1404", "۱۴۰۴-۱۴۰۵", "1404/1405", "1403", "", "404", "2025"]):
            SchoolClass.objects.create(school=school, title=f"c{i}", academic_year=year)
        AcademicYear.objects.create(school=school, code="1404-1405", start_date=date(2025, 9, 23),
                                    end_date=date(2026, 6, 21), is_current=True)
        before = (SchoolClass.objects.count(), AcademicYear.objects.count())
        r = self.report()
        self.assertEqual(r['class_rows'], 7)
        self.assertEqual(r['class_rows_blank_year'], 1)
        self.assertEqual(r['codes_with_spelling_variants'], ["1404-1405"])
        self.assertEqual(r['codes_without_academic_year_row'], ["1403-1404"])
        self.assertEqual(r['unresolved_values'], {"404": 1, "2025": 1})
        self.assertEqual(r['schools_without_current_year'], r['schools'] - 1)  # this school has one
        self.assertEqual(before, (SchoolClass.objects.count(), AcademicYear.objects.count()))

    def test_text_output(self):
        out = StringIO()
        call_command('check_academic_years', stdout=out)
        self.assertIn('writes: none', out.getvalue())
