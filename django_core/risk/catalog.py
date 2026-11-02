"""Default catalog of rule templates (0031, decisions 53-55): read-only, versioned, in code. A school never edits a template; it
ACTIVATES one, which creates a DRAFT ``Rule`` for that school (then the normal simulate / submit / approve lifecycle applies).
Thresholds on the grade scale are stored as PERCENT of the scale (``pct``) and converted with the school's ``grade_scale_max``.
Every number is an unvalidated configurable default, not a legal limit. Closed metric catalog only (``risk.signals.METRICS``);
no emotional / family types (``Rule.RULE_RISK_TYPES``). Intro wording for users: «بر پایهٔ شاخص‌های هشدار زودهنگام ABC و رویکرد
پشتیبانی چندسطحی (MTSS)»; no paper names are shown to users."""
from copy import deepcopy

CATALOG_VERSION = 1
BASIS_FA = 'بر پایهٔ شاخص‌های هشدار زودهنگام ABC (حضور، رفتار، نمره) و رویکرد پشتیبانی چندسطحی (MTSS)'
SCALE_METRICS = ('avg_score', 'subject_drop')      # clause thresholds in score units: stored as percent of the scale


def _c(metric, op, threshold, window, baseline=None, min_records=None, pct=False):
    clause = {'metric': metric, 'op': op, 'threshold': threshold, 'window_days': window}
    if baseline:
        clause['baseline_days'] = baseline
    if min_records is not None:
        clause['min_records'] = min_records
    if pct:
        clause['pct'] = True
    return clause


def _t(title, risk_type, severity, connective, clauses, tier, *, family='', starter=False):
    return dict(title=title, risk_type=risk_type, severity=severity, connective=connective, clauses=clauses, tier=tier,
                family=family, starter=starter)


# Families: a stronger hit supersedes a weaker open one for the same student. Order = weakest -> strongest.
FAMILIES = {
    'attendance': ('repeated_absence', 'absence_run', 'chronic_absence_watch', 'chronic_absence_high'),
    'academic': ('low_average', 'failing_average', 'off_track_combo'),
    'behavior': ('repeated_concerns', 'concern_surge', 'concern_with_absence'),
}

TEMPLATES = {
    'attendance_shift': _t('افزایش غیبت نسبت به دورهٔ قبل', 'attendance', 'yellow', 'all',
                           [_c('absence_shift_pp', '>=', 10, 30, baseline=60, min_records=5)], '2', starter=True),
    'repeated_absence': _t('غیبت مکرر در دو هفتهٔ اخیر', 'attendance', 'yellow', 'any',
                           [_c('absent_days', '>=', 3, 14, min_records=5), _c('max_consecutive_absences', '>=', 2, 14, min_records=5)],
                           '2', family='attendance', starter=True),
    'low_average': _t('میانگین پایین نمرات اخیر', 'academic', 'yellow', 'all',
                      [_c('avg_score', '<', 60, 45, min_records=3, pct=True)], '2', family='academic', starter=True),
    'grade_drop': _t('افت نمرهٔ یک درس', 'academic', 'orange', 'all',
                     [_c('subject_drop', '>=', 15, 45, baseline=75, min_records=2, pct=True)], '2', starter=True),
    'repeated_concerns': _t('نگرانی‌های رفتاری مکرر ثبت‌شده توسط کادر', 'behavioral', 'yellow', 'all',
                            [_c('concern_count', '>=', 3, 30, min_records=0)], '2', family='behavior', starter=True),
    'chronic_absence_watch': _t('غیبت مزمن (نظارتی)', 'attendance', 'yellow', 'all',
                                [_c('absence_rate', '>=', 10, 60, min_records=20)], '1', family='attendance', starter=True),
    'chronic_absence_high': _t('غیبت مزمن شدید', 'attendance', 'orange', 'all',
                               [_c('absence_rate', '>=', 20, 60, min_records=20)], '3', family='attendance'),
    'absence_run': _t('غیبت پیاپی طولانی', 'attendance', 'orange', 'all',
                      [_c('max_consecutive_absences', '>=', 5, 14, min_records=5)], '2', family='attendance'),
    'late_pattern': _t('تأخیر مکرر', 'attendance', 'yellow', 'all', [_c('late_count', '>=', 5, 30)], '1'),
    'failing_average': _t('میانگین بسیار پایین', 'academic', 'orange', 'all',
                          [_c('avg_score', '<', 50, 45, min_records=3, pct=True)], '3', family='academic'),
    'off_track_combo': _t('افت هم‌زمان نمره و حضور', 'academic', 'orange', 'all',
                          [_c('avg_score', '<', 60, 45, min_records=3, pct=True), _c('absence_rate', '>=', 10, 45, min_records=15)],
                          '3', family='academic'),
    'concern_surge': _t('افزایش نگرانی‌های رفتاری', 'behavioral', 'orange', 'all',
                        [_c('concern_count', '>=', 5, 30, min_records=0)], '2', family='behavior'),
    'concern_with_absence': _t('نگرانی رفتاری همراه با غیبت', 'behavioral', 'orange', 'all',
                               [_c('concern_count', '>=', 2, 30, min_records=0), _c('absence_rate', '>=', 10, 30, min_records=10)],
                               '2', family='behavior'),
}
STARTER_PACK = tuple(code for code, t in TEMPLATES.items() if t['starter'])
FAMILY_OF = {code: (family, rank) for family, codes in FAMILIES.items() for rank, code in enumerate(codes)}


def uses_scale(template):
    return any(c['metric'] in SCALE_METRICS for c in template['clauses'])


def instantiate(code, scale):
    """Concrete ``clauses`` for a school: percent thresholds converted with ``scale`` (None if the template needs a scale and the
    school has none: the caller refuses, same fail-closed rule as score-based rules)."""
    template = TEMPLATES[code]
    clauses = []
    for raw in deepcopy(template['clauses']):
        if raw.pop('pct', False):
            if not scale:
                return None
            raw['threshold'] = round(raw['threshold'] * scale / 100, 2)
        clauses.append(raw)
    return clauses
