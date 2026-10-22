"""Year rollover: close the current year's enrollments and open the next year's (ADR-0011, stage 2.2a-4d).

    manage.py rollover_academic_year --to 1405-1406 [--school-code CODE] --class-map FILE
                                     [--outcomes FILE] [--default promote]
                                     [--flip-current] [--deactivate-old-classes]
                                     [--deactivate-old-grade-lead-assignments] [--apply] [--json]
    manage.py rollover_academic_year --revert-batch ID [--apply]

DRY-RUN by default; ``--apply`` writes everything in one transaction and one ``ImportBatch`` (kind
``rollover``) that stores the undo information, so ``--revert-batch`` restores the previous state exactly.

Evidence only, nothing guessed:
  * only students with an OPEN enrollment in the school's CURRENT year are considered;
  * the outcome of each student comes from ``--outcomes`` (CSV ``national_id,status`` with status in promoted,
    retained, graduated, transferred_out, withdrawn) or, only if the admin passes ``--default promote``, from the
    stated rule "grade below 12 is promoted, grade 12 graduates". A student with neither is skipped and counted;
  * promoted/retained students need an explicit class mapping (``--class-map`` CSV ``from_class,to_class``, titles)
    that resolves to exactly one class of the target year whose grade (if set) fits; otherwise they are skipped
    whole (no half promotion);
  * the target year must already exist with its dates; classes are never created.
Idempotent: a student already enrolled in the target year, or without an open enrollment, is skipped. The
command changes no access rule; it changes DATA (enrollments, and the Student grade/class mirror of promoted
students). ``--flip-current`` makes the target year current; the two ``--deactivate-old-*`` flags retire the old
year's classes and Grade Lead assignments (ADR-0004: year rollover is an explicit admin action).
"""
import csv
import hashlib
import json
from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schools.academic_years import RESOLVED, normalize_academic_year
from schools.models import AcademicYear, GradeLeadAssignment, School, SchoolClass
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment, ImportBatch, Student
from students.views import _clean_national_id

OUTCOMES = ('promoted', 'retained', 'graduated', 'transferred_out', 'withdrawn')
MOVING = ('promoted', 'retained')


def _read_csv(path, required):
    with open(path, 'rb') as fh:
        raw = fh.read()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    if rows and not set(required) <= set(rows[0]):
        raise CommandError(f'{path}: columns required: {", ".join(required)}')
    return [{k.strip(): (v or '').strip() for k, v in r.items()} for r in rows], raw


class Command(BaseCommand):
    help = "Roll the school over to the next academic year (dry-run by default; batch-logged and reversible)."

    def add_arguments(self, parser):
        parser.add_argument('--to')
        parser.add_argument('--school-code')
        parser.add_argument('--class-map')
        parser.add_argument('--outcomes')
        parser.add_argument('--default', choices=['promote'])
        parser.add_argument('--flip-current', action='store_true')
        parser.add_argument('--deactivate-old-classes', action='store_true')
        parser.add_argument('--deactivate-old-grade-lead-assignments', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revert-batch', type=int)
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **opts):
        if opts['revert_batch'] is not None:
            report = self._revert(opts['revert_batch'], opts['apply'])
        else:
            report = self._rollover(opts)
        report['mode'] = 'APPLIED' if opts['apply'] else 'DRY-RUN'
        if opts['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        else:
            for key, value in sorted(report.items()):
                self.stdout.write(f'{key}: {value}')

    # ------------------------------------------------------------------------------------------
    def _years(self, opts):
        status, code = normalize_academic_year(opts['to'])
        if status != RESOLVED:
            raise CommandError(f"سال مقصد «{opts['to']}» قابل تشخیص نیست.")
        current = AcademicYear.objects.filter(is_current=True).select_related('school')
        if opts['school_code']:
            current = current.filter(school__code=opts['school_code'])
        current = list(current)
        if len(current) != 1:
            raise CommandError('Exactly one school with a current year is required (use --school-code); found %d.' % len(current))
        source = current[0]
        target = AcademicYear.objects.filter(school=source.school, code=code).first()
        if target is None:
            raise CommandError(f'AcademicYear {code} does not exist for school {source.school.code}; create it (with dates) first.')
        if target.pk == source.pk or target.start_date <= source.start_date:
            raise CommandError('The target year must be later than the current year.')
        return source, target

    def _classes_of_year(self, school, year):
        out = {}
        for pk, title, text, grade in SchoolClass.objects.filter(school=school).values_list(
                'pk', 'title', 'academic_year', 'grade'):
            status, code = normalize_academic_year(text)
            if status == RESOLVED and code == year.code:
                out.setdefault(title.strip(), []).append((pk, grade))
        return out

    def _rollover(self, opts):
        if not (opts['to'] and opts['class_map']):
            raise CommandError('--to and --class-map are required (or use --revert-batch).')
        source, target = self._years(opts)
        school = source.school
        class_rows, raw_map = _read_csv(opts['class_map'], ('from_class', 'to_class'))
        class_map = {r['from_class']: r['to_class'] for r in class_rows}
        outcomes, raw_out = {}, b''
        if opts['outcomes']:
            out_rows, raw_out = _read_csv(opts['outcomes'], ('national_id', 'status'))
            for r in out_rows:
                nid, err = _clean_national_id(r['national_id'])
                if err or r['status'] not in OUTCOMES:
                    raise CommandError(f"outcomes file: invalid row ({'national_id' if err else 'status'}): {r}")
                outcomes[nid] = r['status']
        target_classes = self._classes_of_year(school, target)
        already = set(Enrollment.objects.filter(academic_year=target).values_list('student_id', flat=True))

        skipped = Counter()
        outcome_counts = Counter()
        closes, creates, mirrors = [], [], []
        open_rows = Enrollment.objects.filter(
            academic_year=source, ended_on__isnull=True, status__in=CURRENT_STATUSES,
        ).select_related('student', 'school_class')
        considered = 0
        for e in open_rows:
            considered += 1
            if e.student_id in already:
                skipped['already_in_target_year'] += 1
                continue
            outcome = outcomes.get(e.student.national_id)
            if outcome is None and opts['default'] == 'promote':
                outcome = 'promoted' if e.grade < 12 else 'graduated'
            if outcome is None:
                skipped['no_outcome_given'] += 1
                continue
            if outcome == 'graduated' and e.grade != 12:
                skipped['graduated_before_grade_12'] += 1
                continue
            if outcome == 'promoted' and e.grade >= 12:
                skipped['promoted_beyond_grade_12'] += 1
                continue
            if outcome in MOVING:
                new_grade = e.grade + 1 if outcome == 'promoted' else e.grade
                if e.school_class is None:
                    skipped['enrollment_without_class'] += 1
                    continue
                to_title = class_map.get(e.school_class.title)
                if to_title is None:
                    skipped['no_class_mapping'] += 1
                    continue
                options = target_classes.get(to_title, [])
                if len(options) != 1:
                    skipped['target_class_not_found' if not options else 'target_class_ambiguous'] += 1
                    continue
                class_pk, class_grade = options[0]
                if class_grade is not None and class_grade != new_grade:
                    skipped['target_class_grade_conflict'] += 1
                    continue
                creates.append((e.student_id, class_pk, new_grade))
                mirrors.append((e.student_id, new_grade, class_pk))
            outcome_counts[outcome] += 1
            closes.append((e.pk, outcome))

        old_classes = [pk for pk, text in SchoolClass.objects.filter(school=school, is_active=True).values_list(
            'pk', 'academic_year') if self._year_code(text) == source.code]
        old_assignments = [a.pk for a in GradeLeadAssignment.objects.filter(school=school, is_active=True)
                           if self._year_code(a.academic_year) == source.code]
        report = {
            'school': school.code, 'from_year': source.code, 'to_year': target.code,
            'students_considered': considered, 'outcomes': dict(outcome_counts),
            'skipped': dict(skipped),
            'enrollments_to_close': len(closes), 'enrollments_to_open': len(creates),
            'student_mirrors_to_update': len(mirrors),
            'flip_current': bool(opts['flip_current']),
            'old_classes_to_deactivate': len(old_classes) if opts['deactivate_old_classes'] else 0,
            'old_grade_lead_assignments_to_deactivate': len(old_assignments) if opts['deactivate_old_grade_lead_assignments'] else 0,
        }
        if not opts['apply']:
            return report

        with transaction.atomic():
            digest = hashlib.sha256(raw_map + b'\x00' + raw_out).hexdigest()
            batch = ImportBatch.objects.create(kind='rollover', academic_year=target, file_sha256=digest, dry_run=False)
            undo = {'closed': [], 'created': [], 'mirrors': [], 'flip': None, 'classes': [], 'assignments': []}
            prior = {e.pk: e for e in Enrollment.objects.filter(pk__in=[pk for pk, _s in closes])}
            for pk, outcome in closes:
                undo['closed'].append({'id': pk, 'status': prior[pk].status, 'ended_on': prior[pk].ended_on})
                Enrollment.objects.filter(pk=pk).update(status=outcome, ended_on=source.end_date)
            for student_id, class_pk, grade in creates:
                e = Enrollment.objects.create(
                    student_id=student_id, academic_year=target, school_class_id=class_pk, grade=grade,
                    status='active', source='rollover', import_batch=batch, started_on=target.start_date)
                undo['created'].append(e.pk)
            for student_id, grade, class_pk in mirrors:
                st = Student.objects.get(pk=student_id)
                undo['mirrors'].append({'student_id': student_id, 'grade': st.grade, 'school_class_id': st.school_class_id})
                st.grade, st.school_class_id = grade, class_pk
                st.save()
            if opts['flip_current']:
                AcademicYear.objects.filter(pk=source.pk).update(is_current=False)
                AcademicYear.objects.filter(pk=target.pk).update(is_current=True)
                undo['flip'] = {'from': source.pk, 'to': target.pk}
            if opts['deactivate_old_classes']:
                SchoolClass.objects.filter(pk__in=old_classes).update(is_active=False)
                undo['classes'] = old_classes
            if opts['deactivate_old_grade_lead_assignments']:
                GradeLeadAssignment.objects.filter(pk__in=old_assignments).update(is_active=False)
                undo['assignments'] = old_assignments
            batch.counts = {'report': report, 'undo': json.loads(json.dumps(undo, default=str))}
            batch.save(update_fields=['counts'])
        report['import_batch'] = batch.pk
        return report

    @staticmethod
    def _year_code(text):
        status, code = normalize_academic_year(text)
        return code if status == RESOLVED else None

    # ------------------------------------------------------------------------------------------
    def _revert(self, batch_id, apply):
        try:
            batch = ImportBatch.objects.get(pk=batch_id, kind='rollover')
        except ImportBatch.DoesNotExist:
            raise CommandError(f'Rollover batch {batch_id} does not exist.')
        if batch.counts.get('reverted'):
            raise CommandError(f'Batch {batch_id} was already reverted.')
        undo = batch.counts['undo']
        created = Enrollment.objects.filter(pk__in=undo['created'])
        in_use = [e.pk for e in created if e.grades.exists() or e.attendances.exists()]
        if in_use:
            raise CommandError(f'Cannot revert: {len(in_use)} new enrollment(s) are already used by grades/attendance.')
        report = {'import_batch': batch.pk, 'to_year': batch.academic_year.code,
                  'enrollments_to_delete' if not apply else 'enrollments_deleted': created.count(),
                  'enrollments_to_reopen' if not apply else 'enrollments_reopened': len(undo['closed']),
                  'student_mirrors_to_restore' if not apply else 'student_mirrors_restored': len(undo['mirrors']),
                  'flip_to_undo': bool(undo['flip']),
                  'classes_to_reactivate': len(undo['classes']), 'assignments_to_reactivate': len(undo['assignments'])}
        if not apply:
            return report
        with transaction.atomic():
            created.delete()
            for c in undo['closed']:
                ended = date.fromisoformat(c['ended_on']) if c['ended_on'] not in (None, 'None') else None
                Enrollment.objects.filter(pk=c['id']).update(status=c['status'], ended_on=ended)
            for m in undo['mirrors']:
                st = Student.objects.get(pk=m['student_id'])
                st.grade, st.school_class_id = m['grade'], m['school_class_id']
                st.save()
            if undo['flip']:
                AcademicYear.objects.filter(pk=undo['flip']['to']).update(is_current=False)
                AcademicYear.objects.filter(pk=undo['flip']['from']).update(is_current=True)
            SchoolClass.objects.filter(pk__in=undo['classes']).update(is_active=True)
            GradeLeadAssignment.objects.filter(pk__in=undo['assignments']).update(is_active=True)
            batch.counts = {**batch.counts, 'reverted': True}
            batch.save(update_fields=['counts'])
        return report
