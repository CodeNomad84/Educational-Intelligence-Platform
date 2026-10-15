"""Read-only report: free-text academic years vs the ``AcademicYear`` table (ADR-0011, stage 2.2a-1).

    python manage.py check_academic_years [--json]

It only SELECTs and prints counts and year strings (no personal data). It tells the admin which spellings
resolve to which canonical code, which cannot be resolved (never guessed), and which canonical years still
need an ``AcademicYear`` row with dates before a backfill can run (stage 2.2a-3).
"""
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from schools.academic_years import BLANK, RESOLVED, normalize_academic_year
from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass


class Command(BaseCommand):
    help = "Report free-text academic years and AcademicYear rows (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Print the report as JSON.')

    def handle(self, *args, **opts):
        sources = {
            'classes': Counter(SchoolClass.objects.values_list('academic_year', flat=True)),
            'grade_lead_assignments': Counter(GradeLeadAssignment.objects.values_list('academic_year', flat=True)),
        }
        spellings = defaultdict(set)   # canonical code -> raw spellings
        unresolved = Counter()
        blank = {name: 0 for name in sources}
        for name, counter in sources.items():
            for raw, n in counter.items():
                status, code = normalize_academic_year(raw)
                if status == BLANK:
                    blank[name] += n
                elif status == RESOLVED:
                    spellings[code].add(raw)
                else:
                    unresolved[raw] += n

        years = list(AcademicYear.objects.values('school_id', 'code', 'start_date', 'end_date', 'is_current'))
        have = {y['code'] for y in years}
        by_school = defaultdict(list)
        for y in years:
            by_school[y['school_id']].append(y)
        overlaps = 0
        for rows in by_school.values():
            rows = sorted(rows, key=lambda r: r['start_date'])
            overlaps += sum(1 for a, b in zip(rows, rows[1:]) if b['start_date'] <= a['end_date'])
        schools = list(School.objects.values_list('pk', flat=True))
        current_count = Counter(y['school_id'] for y in years if y['is_current'])

        report = {
            'schools': len(schools),
            'academic_year_rows': len(years),
            'schools_without_current_year': sum(1 for s in schools if current_count[s] == 0),
            'schools_with_several_current_years': sum(1 for s in schools if current_count[s] > 1),
            'overlapping_ranges': overlaps,
            'class_rows': sum(sources['classes'].values()),
            'class_rows_blank_year': blank['classes'],
            'grade_lead_assignment_rows': sum(sources['grade_lead_assignments'].values()),
            'grade_lead_assignment_rows_blank_year': blank['grade_lead_assignments'],
            'canonical_codes_found': {c: sorted(raws) for c, raws in sorted(spellings.items())},
            'codes_with_spelling_variants': sorted(c for c, raws in spellings.items() if len(raws) > 1),
            'codes_without_academic_year_row': sorted(c for c in spellings if c not in have),
            'unresolved_values': dict(unresolved),
            'writes': 'none',
        }
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        self.stdout.write('Academic years (read-only)')
        for key, value in report.items():
            if isinstance(value, (dict, list)):
                self.stdout.write(f'  {key}: {len(value)}')
                for item in (value.items() if isinstance(value, dict) else value):
                    self.stdout.write(f'    {item}')
            else:
                self.stdout.write(f'  {key}: {value}')
