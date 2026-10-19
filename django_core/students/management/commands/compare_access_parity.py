"""Compare the legacy (pre-switch) access rule with the enrollment-based rule (ADR-0011, stages 2.2a-4b/4c). Read-only.

    manage.py compare_access_parity [--json]

For every user who holds GradeLead, Teacher or Parent it computes the visible student set and tier with the
legacy rule (``access_legacy``) and with the production rule (``access.visible_students``, enrollment-based since
the 4c switch) and prints COUNTS only
(no names, no ids). Every difference is classified by a documented explanation (each one is a bug fixed by
the switch, not a regression); a difference that fits none is UNEXPLAINED. Exit code 1 on any unexplained
difference (owner D-4-6). Nothing here changes access.

Without `--multi-school` the output ends with "multi-school checks: NOT RUN". The multi-school gate (changes/0010, S3) is
a separate opt-in run: it requires THIS command and `check_access_switch_ready` to be run WITH `--multi-school` and to
pass. With the flag the enrollment comparison is skipped and each SchoolAdmin's scope is compared instead; it also fails
when students exist but no SchoolAdmin does (D1), when a school has students but no valid SchoolAdmin covers it (E1)
and while active memberships of non-qualifying users exist (D3).
"""
import json
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import AcademicYear, GradeLeadAssignment
from students import access, access_legacy
from students.access import GRADE_LEAD, PARENT, TEACHER
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, Student

EXPLANATIONS = (
    'school_has_no_current_year',
    'mirror_class_year_differs_from_current_year',   # promoted/stale mirror (a)
    'assignment_year_spelling_variant',              # (b)
    'enrollment_without_class_mirror',               # (c)
    'mirror_grade_differs_from_enrollment',          # (d)
    'mirror_class_differs_from_enrollment_class',    # (d, teacher)
    'mirror_class_inactive',
)


def signature(student, side, ctx):
    """Counts-only fingerprint of an UNEXPLAINED difference (facts, never names or ids), to guide a data/tool fix."""
    klass = student.school_class
    e = ctx['enrollment'].get(student.pk)
    year = ctx['current_year'].get(student.school_id)
    class_year = None
    if klass is not None:
        status, code = normalize_academic_year(klass.academic_year)
        class_year = 'unresolved' if status != RESOLVED else ('current' if code == year else 'other_year')
    return (f"{side}: mirror_class={'none' if klass is None else class_year}"
            f"{'' if klass is None else (',class_active=' + str(klass.is_active).lower())}"
            f"{'' if klass is None or klass.grade is None else (',class_grade_eq_student=' + str(klass.grade == student.grade).lower())}"
            f"; current_enrollment={'none' if e is None else ('grade_eq=' + str(e['grade'] == student.grade).lower() + ',class_eq=' + str(klass is not None and e['school_class_id'] == klass.pk).lower())}")


def explain(student, side, ctx):
    """Return the first matching explanation, or None. ``student`` is a Student; ``ctx`` has precomputed facts."""
    year = ctx['current_year'].get(student.school_id)
    if year is None:
        return 'school_has_no_current_year'
    enrollment = ctx['enrollment'].get(student.pk)
    klass = student.school_class
    if klass is None:
        return 'enrollment_without_class_mirror' if side == 'only_new' else None
    status, code = normalize_academic_year(klass.academic_year)
    if status != RESOLVED or code != year:
        return 'mirror_class_year_differs_from_current_year'
    if side == 'only_new' and any(
            raw != klass.academic_year and normalize_academic_year(raw) == (RESOLVED, year)
            for raw in ctx['lead_years'].get(student.school_id, ())):
        return 'assignment_year_spelling_variant'
    if enrollment is not None:
        if enrollment['grade'] != student.grade:
            return 'mirror_grade_differs_from_enrollment'
        if enrollment['school_class_id'] != klass.pk:
            return 'mirror_class_differs_from_enrollment_class'
    if not klass.is_active:
        return 'mirror_class_inactive'
    return None


class Command(BaseCommand):
    help = "Compare legacy and enrollment-based student visibility (read-only; exit 1 on unexplained differences)."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')
        parser.add_argument('--detail', action='store_true', help='also print a counts-only breakdown of unexplained differences')
        parser.add_argument(
            '--multi-school', action='store_true',
            help='instead of the enrollment comparison, compare what each SchoolAdmin sees today (everything) with '
                 'the membership scope of changes/0010 S3 (counts only; exit 1 if any SchoolAdmin would lose rows)')

    def handle(self, *args, **opts):
        if opts['multi_school']:
            return self._multi_school(opts)
        User = get_user_model()
        users = list(User.objects.filter(groups__name__in=[GRADE_LEAD, TEACHER, PARENT]).distinct())
        current_year = dict(AcademicYear.objects.filter(is_current=True).values_list('school_id', 'code'))
        enrollment = {}
        for e in Enrollment.objects.filter(ended_on__isnull=True, status__in=CURRENT_STATUSES,
                                           academic_year__is_current=True).values('student_id', 'school_class_id', 'grade'):
            enrollment[e['student_id']] = e

        totals = Counter()
        explained = Counter()
        unexplained_signatures = Counter()
        users_with_diff = 0
        for user in users:
            legacy = {s.pk: s.full_tier for s in access_legacy.visible_students(user)}
            new = {s.pk: s.full_tier for s in access.visible_students(user)}
            totals['users_compared'] += 1
            totals['students_in_both'] += len(legacy.keys() & new.keys())
            only_legacy = legacy.keys() - new.keys()
            only_new = new.keys() - legacy.keys()
            tier_diff = [pk for pk in legacy.keys() & new.keys() if legacy[pk] != new[pk]]
            totals['students_only_legacy'] += len(only_legacy)
            totals['students_only_new'] += len(only_new)
            totals['tier_differences'] += len(tier_diff)
            if only_legacy or only_new or tier_diff:
                users_with_diff += 1
            lead_years = {}
            for school_id, raw in GradeLeadAssignment.objects.filter(user=user, is_active=True).values_list(
                    'school_id', 'academic_year'):
                lead_years.setdefault(school_id, set()).add(raw)
            ctx = {'current_year': current_year, 'enrollment': enrollment, 'lead_years': lead_years}
            students = {s.pk: s for s in Student.objects.filter(
                pk__in=only_legacy | only_new | set(tier_diff)).select_related('school_class')}
            checks = [(pk, 'only_legacy') for pk in only_legacy] + [(pk, 'only_new') for pk in only_new] + [
                # the side that gained full detail decides which explanation can apply
                (pk, 'only_new' if new[pk] and not legacy[pk] else 'only_legacy') for pk in tier_diff]
            for pk, side in checks:
                reason = explain(students[pk], side, ctx)
                explained[reason or 'UNEXPLAINED'] += 1
                if reason is None:
                    unexplained_signatures[signature(students[pk], side, ctx)] += 1

        report = {
            **{k: totals.get(k, 0) for k in ('users_compared', 'students_in_both', 'students_only_legacy',
                                             'students_only_new', 'tier_differences')},
            'users_with_differences': users_with_diff,
            'explained_by': {k: explained[k] for k in EXPLANATIONS if explained[k]},
            'unexplained': explained['UNEXPLAINED'],
            'writes': 'none',
        }
        if opts['detail']:
            report['unexplained_signatures'] = dict(unexplained_signatures)
        report['multi_school_checks'] = 'NOT RUN'
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                if key != 'multi_school_checks':
                    self.stdout.write(f'{key}: {value}')
            self.stdout.write('multi-school checks: NOT RUN')
        if report['unexplained']:
            raise CommandError(f"{report['unexplained']} unexplained difference(s).")

    def _multi_school(self, opts):
        from schools.multischool_checks import school_admin_parity

        report = {'users_compared': 0, 'users_with_differences': 0, 'students_lost': 0, 'grades_lost': 0,
                  'attendances_lost': 0, **school_admin_parity()}
        report['writes'] = 'none'
        report['multi_school_checks'] = 'RUN'
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key, value in sorted(report.items()):
                if key != 'multi_school_checks':
                    self.stdout.write(f'{key}: {value}')
            self.stdout.write('multi-school checks: RUN')
        problems = []
        if report['students_lost'] or report['grades_lost'] or report['attendances_lost']:
            problems.append(f"{report['users_with_differences']} SchoolAdmin(s) would lose rows with the membership scope")
        if report.get('no_school_admin_while_students_exist'):
            problems.append('students exist but no SchoolAdmin account exists (the comparison would pass vacuously)')
        if report.get('schools_with_students_but_no_school_admin'):
            problems.append(f"{report['schools_with_students_but_no_school_admin']} school(s) have students but no "
                            'SchoolAdmin who would still see them')
        if report.get('memberships_invalid'):
            problems.append(f"{report['memberships_invalid']} active membership(s) of users who no longer qualify")
        if problems:
            raise CommandError('; '.join(problems) + '.')
