"""Deterministic rule evaluation (0025, stage 4): clause validation, evaluation of a rule over a school and the simulation.

Student data is read ONLY through the system read path in ``students/access.py`` (``system_scope_*``), which takes one explicit
school id. This module is its only importer. Rules are data (``Rule.clauses``): every clause names a metric of the closed catalog
in ``risk/signals.py``; nothing is ever evaluated from text. The result of a rule is "fired" or not, with the numbers that led to
it; there is no score and no level.
"""
import hashlib
import json
import math
from collections import defaultdict
from datetime import timedelta
from numbers import Real

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from students.access import system_scope_attendance, system_scope_enrollments, system_scope_grades, system_scope_students

from schools import audit

from . import signals
from .models import Alert, Rule, RuleHit, RuleRun, RuleSettings
from .services import raise_alert

MAX_CLAUSES = 4
MAX_SPAN_DAYS = 730
MIN_GROUP = 5                      # counts below this are withheld in every aggregate shown
CLAUSE_KEYS = {'metric', 'op', 'threshold', 'window_days', 'baseline_days', 'min_records'}

# Starter proposals ported from the demo (unvalidated). baseline_days = length of the window before the recent one.
STARTERS = {
    'attendance_shift': dict(title='افزایش غیبت نسبت به دورهٔ قبل', risk_type='attendance', severity='yellow', connective='all',
                             clauses=[{'metric': 'absence_shift_pp', 'op': '>=', 'threshold': 10, 'window_days': 30,
                                       'baseline_days': 60, 'min_records': 5}]),
    'repeated_absence': dict(title='غیبت مکرر در دو هفتهٔ اخیر', risk_type='attendance', severity='yellow', connective='any',
                             clauses=[{'metric': 'absent_days', 'op': '>=', 'threshold': 3, 'window_days': 14, 'min_records': 5},
                                      {'metric': 'max_consecutive_absences', 'op': '>=', 'threshold': 2, 'window_days': 14,
                                       'min_records': 5}]),
    'low_average': dict(title='میانگین پایین نمرات اخیر', risk_type='academic', severity='yellow', connective='all',
                        clauses=[{'metric': 'avg_score', 'op': '<', 'threshold': 12, 'window_days': 45, 'min_records': 3}]),
    'grade_drop': dict(title='افت نمرهٔ یک درس', risk_type='academic', severity='orange', connective='all',
                       clauses=[{'metric': 'subject_drop', 'op': '>=', 'threshold': 3, 'window_days': 45, 'baseline_days': 75,
                                 'min_records': 2}]),
}


def _int(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValidationError(f'{name}: عدد صحیح بین {lo} و {hi}.')
    return value


def validate_clauses(clauses, connective, *, school_id=None, settings=None):
    """Return the normalized clause list or raise ``ValidationError``. Scale-based clauses need ``grade_scale_max`` (fail closed)."""
    if connective not in ('all', 'any'):
        raise ValidationError('connective: all یا any.')
    if not isinstance(clauses, list) or not 1 <= len(clauses) <= MAX_CLAUSES:
        raise ValidationError(f'تعداد شرط‌ها باید بین ۱ و {MAX_CLAUSES} باشد.')
    if settings is None and school_id is not None:
        settings = RuleSettings.objects.filter(school_id=school_id).first()
    out = []
    for raw in clauses:
        if not isinstance(raw, dict) or set(raw) - CLAUSE_KEYS or not {'metric', 'op', 'threshold', 'window_days'} <= set(raw):
            raise ValidationError('ساختار شرط نامعتبر است.')
        metric = raw['metric']
        if metric not in signals.METRICS:
            raise ValidationError('معیار ناشناخته.')
        if raw['op'] not in signals.OPS:
            raise ValidationError('عملگر نامعتبر.')
        threshold = raw['threshold']
        if isinstance(threshold, bool) or not isinstance(threshold, Real) or not math.isfinite(threshold):
            raise ValidationError('آستانه باید عدد باشد.')
        clause = {'metric': metric, 'op': raw['op'], 'threshold': threshold,
                  'window_days': _int(raw['window_days'], 1, 365, 'window_days')}
        takes_baseline = signals.METRICS[metric][2]
        if takes_baseline:
            clause['baseline_days'] = _int(raw.get('baseline_days'), 1, 365, 'baseline_days')
        elif raw.get('baseline_days') is not None:
            raise ValidationError('این معیار دورهٔ مبنا ندارد.')
        if raw.get('min_records') is not None:
            clause['min_records'] = _int(raw['min_records'], 0, 100, 'min_records')
        if metric == 'avg_score':
            scale = getattr(settings, 'grade_scale_max', None)
            if not scale:
                raise ValidationError('سقف مقیاس نمره برای مدرسه تنظیم نشده است؛ قاعدهٔ مبتنی بر نمره فعال نمی‌شود.')
            if not 0 <= threshold <= scale:
                raise ValidationError(f'آستانهٔ نمره باید بین ۰ و {scale} باشد.')
        out.append(clause)
    return out


def validate_rule_fields(*, kind, risk_type, severity, cooldown_days):
    if kind not in Rule.KINDS:
        raise ValidationError('نوع قاعده نامعتبر است.')
    if risk_type not in Rule.RULE_RISK_TYPES:
        raise ValidationError('نوع ریسک قاعده فقط آموزشی، غیبت یا رفتاری است.')
    if severity not in ('yellow', 'orange'):
        raise ValidationError('شدت نامعتبر.')
    _int(cooldown_days, 1, 365, 'cooldown_days')


def params_hash(rule):
    """Hash of everything that changes what the rule does (not the title)."""
    payload = json.dumps([rule.kind, rule.risk_type, rule.severity, rule.connective, rule.clauses, rule.cooldown_days],
                         sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


# ---- data loading (system read path) ----
def load_school(school_id, first_as_of, last_as_of):
    """``({student_id: grade}, attendance_by_student, grades_by_student)`` of the students with a current enrollment in ONE school."""
    since = first_as_of - timedelta(days=MAX_SPAN_DAYS)
    grade_of = dict(system_scope_enrollments(school_id).values_list('student_id', 'grade'))
    attendance, grades = defaultdict(list), defaultdict(list)
    for row in system_scope_attendance(school_id).filter(date__gt=since, date__lte=last_as_of).only('student_id', 'date', 'status'):
        attendance[row.student_id].append(row)
    for row in system_scope_grades(school_id).filter(date__gt=since, date__lte=last_as_of).only('student_id', 'date', 'score', 'subject'):
        grades[row.student_id].append(row)
    return grade_of, attendance, grades


def _evidence(clause, signal):
    item = {'metric': clause['metric'], 'op': clause['op'], 'threshold': clause['threshold'],
            'window_days': clause['window_days'], 'value': round(signal.value, 2), 'records': signal.records}
    if 'baseline_days' in clause:
        item['baseline_days'] = clause['baseline_days']
    if signal.detail:
        item['detail'] = {k: ([[x if isinstance(x, str) else round(x, 2) for x in row] for row in v] if k == 'subjects'
                              else round(v, 2)) for k, v in signal.detail.items()}
    return item


def evaluate_student(rule, attendances, grades, as_of):
    """``('fired', evidence)`` | ``('insufficient', None)`` | ``('no', None)``. Insufficient data is never a hit."""
    fired, insufficient, evidence = 0, 0, []
    for clause in rule.clauses:
        signal = signals.evaluate_metric(
            clause['metric'], attendances, grades, as_of, window_days=clause['window_days'],
            baseline_days=clause.get('baseline_days'), min_records=clause.get('min_records'))
        if signal is None:
            insufficient += 1
        elif signals.OPS[clause['op']](signal.value, clause['threshold']):
            fired += 1
            evidence.append(_evidence(clause, signal))
    total = len(rule.clauses)
    if rule.connective == 'all':
        if fired == total:
            return 'fired', evidence
        return ('insufficient', None) if fired + insufficient == total else ('no', None)
    if fired:
        return 'fired', evidence
    return ('insufficient', None) if insufficient else ('no', None)


def evaluate_rule(rule, students, attendance, grades, as_of):
    """Results for every student of ``students`` ({id: grade}): ``{student_id: (verdict, evidence)}``."""
    return {sid: evaluate_student(rule, attendance.get(sid, []), grades.get(sid, []), as_of) for sid in students}


# ---- simulation: aggregate counts only, nothing stored but the caller's RuleRun ----
def simulate(rule, *, as_of, weeks=8):
    """Replay ``rule`` at weekly dates ending ``as_of`` over the school's own history. Returns counts per week and per grade;
    a count under MIN_GROUP is ``None`` (withheld). No student id leaves this function and nothing is written."""
    dates = [as_of - timedelta(days=7 * n) for n in range(weeks - 1, -1, -1)]
    students, attendance, grades = load_school(rule.school_id, dates[0], dates[-1])
    result = []
    for day in dates:
        verdicts = evaluate_rule(rule, students, attendance, grades, day)
        by_grade = defaultdict(int)
        for sid, (verdict, _evidence_) in verdicts.items():
            if verdict == 'fired':
                by_grade[students[sid]] += 1
        fired = sum(by_grade.values())
        result.append({'as_of': day, 'evaluated': len(students),
                       'insufficient': sum(1 for v, _e in verdicts.values() if v == 'insufficient'),
                       'fired': fired if fired >= MIN_GROUP else None,
                       'by_grade': {g: (n if n >= MIN_GROUP else None) for g, n in sorted(by_grade.items())}})
    return result


# ---- the runner (live): the only code that turns rule hits into alerts ----
METRIC_FA = {'absence_rate': 'نرخ غیبت', 'absence_shift_pp': 'افزایش نرخ غیبت (واحد درصد)', 'late_count': 'تعداد تأخیر',
             'absent_days': 'تعداد روزهای غیبت', 'max_consecutive_absences': 'بیشترین غیبت پیاپی', 'avg_score': 'میانگین نمرات',
             'grades_count': 'تعداد نمرات', 'subject_drop': 'بیشترین افت نمرهٔ یک درس'}
OPEN_PLAN_STATUSES = ('planned', 'active')
DEFAULT_BREAKER_PERCENT = 15


def message_for(rule, evidence):
    """Deterministic text from the evidence (numbers only, no diagnosis, no free text)."""
    parts = [f"{METRIC_FA[e['metric']]}: {e['value']:g} ({e['op']} {e['threshold']:g}) در {e['window_days']} روز اخیر، {e['records']} رکورد"
             for e in evidence]
    text = f"طبق قاعدهٔ «{rule.title}» ({rule.code} نسخهٔ {rule.version}): " + "؛ ".join(parts)
    return text[:300], text[:500]


def _blocked_by_cooldown(rule, hits, as_of):
    """``hits``: this student's earlier RuleHits of the same rule code. An earlier alert blocks a new one while it is new, or
    accepted with a planned/active plan; otherwise only until ``cooldown_days`` have passed since the last hit (``evaluated_on``, the run's own date)."""
    for hit in hits:
        alert = hit.alert
        if alert.status == Alert.NEW:
            return True
        if alert.status == Alert.ACCEPTED and alert.plans.filter(status__in=OPEN_PLAN_STATUSES).exists():
            return True
    last = max((h.evaluated_on for h in hits), default=None)
    return last is not None and (as_of - last).days < rule.cooldown_days


def _run_rule(rule, students, attendance, grades, as_of, school_id, scale_ok, breaker_percent, actor, triggered_by):
    run = RuleRun(school_id=school_id, rule=rule, mode='live', as_of=as_of, triggered_by=triggered_by, evaluated=len(students))
    uses_scale = any(c['metric'] == 'avg_score' for c in rule.clauses)
    if uses_scale and not scale_ok:
        run.status = RuleRun.Status.NO_SCALE
        run.save()
        return run
    verdicts = evaluate_rule(rule, students, attendance, grades, as_of)
    fired = {sid: ev for sid, (v, ev) in verdicts.items() if v == 'fired'}
    run.hits = len(fired)
    run.skipped_insufficient = sum(1 for v, _e in verdicts.values() if v == 'insufficient')
    if students and len(fired) * 100 > breaker_percent * len(students):      # circuit breaker: more than N% would fire
        run.status = RuleRun.Status.BREAKER
        run.save()
        return run
    earlier = defaultdict(list)
    for hit in RuleHit.objects.filter(school_id=school_id, rule__code=rule.code, student_id__in=fired).select_related('alert'):
        earlier[hit.student_id].append(hit)
    for student in system_scope_students(school_id).filter(pk__in=fired):
        if _blocked_by_cooldown(rule, earlier[student.pk], as_of):
            run.skipped_cooldown += 1
            continue
        message, explanation = message_for(rule, fired[student.pk])
        try:
            with transaction.atomic():           # one transaction per student: a failed hit insert rolls its alert back
                alert = raise_alert(student, risk_type=rule.risk_type, severity=rule.severity, message=message,
                                    explanation=explanation, detected_by='rule_engine', raised_by=None)
                RuleHit.objects.create(school_id=school_id, rule=rule, student=student, alert=alert, evaluated_on=as_of,
                                       evidence={'items': fired[student.pk]})
        except IntegrityError:                   # the same rule+student+day already has a hit (a simultaneous run won)
            run.skipped_cooldown += 1
            continue
        run.alerts_raised += 1
        audit.record(actor, audit.ALERT_RAISE, alert, school=school_id, detail=rule.code[:40])
    run.save()
    return run


def run_school(school_id, *, as_of=None, triggered_by=None):
    """Evaluate every ACTIVE rule of ONE school and raise alerts. ``school_id`` is explicit; ``triggered_by`` is a user (the button)
    or None (command / scheduler, audited as the ``system`` actor). Writes alerts, events, hits and run rows only."""
    if isinstance(school_id, bool) or not isinstance(school_id, int):
        raise ValueError('run_school needs one explicit school id')
    as_of = as_of or timezone.localdate()
    actor = triggered_by or audit.SYSTEM
    settings = RuleSettings.objects.filter(school_id=school_id).first()
    breaker = settings.breaker_percent if settings else DEFAULT_BREAKER_PERCENT
    scale_ok = bool(settings and settings.grade_scale_max)
    active = list(Rule.objects.filter(school_id=school_id, status=Rule.Status.ACTIVE).order_by('code'))
    runs = []
    if active:
        students, attendance, grades = load_school(school_id, as_of, as_of)
        for rule in active:
            run = _run_rule(rule, students, attendance, grades, as_of, school_id, scale_ok, breaker, actor, triggered_by)
            audit.record(actor, audit.RULE_RUN, rule, school=school_id,
                         detail=f"e{run.evaluated}h{run.hits}a{run.alerts_raised}c{run.skipped_cooldown}i{run.skipped_insufficient}"
                                + ('B' if run.status == RuleRun.Status.BREAKER else 'S' if run.status == RuleRun.Status.NO_SCALE else ''))
            runs.append(run)
    return runs
