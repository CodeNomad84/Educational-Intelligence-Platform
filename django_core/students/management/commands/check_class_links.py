"""Read-only report: how legacy ``Student.class_name`` text would map to classes (proposal 0002, C3a).

    python manage.py check_class_links [--json]

It only SELECTs. It never creates a class, links a student, migrates or writes anything, and it prints class
titles and counts only (no student names or other personal data). It is the rehearsal for the C3b data
migration: run it, review the ambiguous groups, then decide.
"""
import json

from django.core.management.base import BaseCommand

from students.class_links import (
    BLANK, LINKABLE, MULTI_GRADE, TOO_LONG, normalize_title, plan_class_links,
)
from students.models import Student


class Command(BaseCommand):
    help = "Report how legacy Student.class_name values would be linked to classes (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Print the report as JSON.')

    def handle(self, *args, **opts):
        # Ambiguity is judged on ALL students (a title already used by linked students of another grade
        # makes it ambiguous too); only UNLINKED students are candidates for linking.
        rows = list(Student.objects.values_list('class_name', 'grade', 'school_class_id'))  # one query
        pairs = [(class_name, grade) for class_name, grade, _link in rows]
        plan = plan_class_links(pairs)

        already_linked = sum(1 for _c, _g, link in rows if link is not None)
        outcome = {BLANK: 0, LINKABLE: 0, MULTI_GRADE: 0, TOO_LONG: 0}
        for class_name, _grade, link in rows:
            if link is None:  # only unlinked students are candidates
                outcome[plan.status_for(class_name)] += 1

        report = {
            'students': plan.total,
            'already_linked': already_linked,
            'candidates': plan.total - already_linked,
            'candidate_outcome': {
                'would_link': outcome[LINKABLE],
                'blank_left_unlinked': outcome[BLANK],
                'multi_grade_left_unlinked': outcome[MULTI_GRADE],
                'too_long_left_unlinked': outcome[TOO_LONG],
            },
            'titles': {
                'linkable': plan.titles(LINKABLE),
                'multi_grade': {t: plan.grades[t] for t in plan.titles(MULTI_GRADE)},
                'too_long': [f'{t[:20]}… ({len(t)} chars)' for t in plan.titles(TOO_LONG)],
            },
            'near_duplicate_groups': plan.near_duplicate_groups(),
            'bare_titles_warning': plan.bare_titles(),
            'raw_values_with_edge_or_extra_whitespace': sorted(
                {v for v, _g in pairs if v and v != normalize_title(v)}),
            'writes': 'none',
        }

        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return
        self.render(report)

    def render(self, r):
        w = self.stdout.write
        o = r['candidate_outcome']
        w('CLASS LINK REPORT (read-only; nothing was written)')
        w(f"Students: {r['students']}  already linked: {r['already_linked']}  candidates: {r['candidates']}")
        w(f"  would link:                  {o['would_link']}")
        w(f"  blank, left unlinked:        {o['blank_left_unlinked']}")
        w(f"  multi-grade, left unlinked:  {o['multi_grade_left_unlinked']}")
        w(f"  too long, left unlinked:     {o['too_long_left_unlinked']}")
        w(f"Linkable class titles ({len(r['titles']['linkable'])}): " + ', '.join(r['titles']['linkable']))
        if r['titles']['multi_grade']:
            w('AMBIGUOUS (title used by more than one grade; no class would be created):')
            for title, spread in r['titles']['multi_grade'].items():
                w(f"  {title!r}: grades {spread}")
        if r['titles']['too_long']:
            w('TOO LONG (> 50 chars; never truncated): ' + '; '.join(r['titles']['too_long']))
        if r['near_duplicate_groups']:
            w('NEAR-DUPLICATES (kept as distinct classes; review, never merged automatically):')
            for group in r['near_duplicate_groups']:
                w('  ' + ' | '.join(repr(t) for t in group))
        if r['bare_titles_warning']:
            w('WARNING bare titles without any digit (the title alone does not state the grade): '
              + ', '.join(r['bare_titles_warning']))
        if r['raw_values_with_edge_or_extra_whitespace']:
            w(f"Values with edge/extra whitespace (identity = trimmed): "
              f"{len(r['raw_values_with_edge_or_extra_whitespace'])}")
