"""0031: activate a catalog template and import rules / strategies from an Excel workbook. Everything goes through the SAME validators
as the forms (``lifecycle.create`` -> ``rules.validate_*``; ``StrategyForm``). Rules land as DRAFT, strategies INACTIVE; nothing runs
until a human simulates and approves. The school is always the caller's (never read from the file). Reports hold fixed reason codes."""
import io
import re
import zipfile

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from openpyxl import Workbook, load_workbook

from interventions.models import Strategy
from schools import audit

from . import catalog, lifecycle, rules, signals
from .models import Rule, RuleSettings

MAX_BYTES, MAX_ROWS = 1_000_000, 200
MAX_UNCOMPRESSED, MAX_MEMBERS, MAX_SCANNED, MAX_COLUMNS, MAX_CELL = 10_000_000, 20, 2000, 40, 500
UPLOADS_PER_WINDOW, WINDOW_SECONDS = 10, 600
RULE_COLUMNS = ['code', 'kind', 'title', 'risk_type', 'severity', 'connective', 'cooldown_days']
CLAUSE_COLUMNS = ['metric', 'op', 'threshold', 'window_days', 'baseline_days', 'min_records']
SLOTS = rules.MAX_CLAUSES
STRATEGY_COLUMNS = ['title', 'intervention_type', 'tier', 'typical_days', 'description']
FORMULA_START = ('=', '+', '-', '@')
DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


class _DryRun(Exception):
    pass


class ImportRefused(Exception):
    """The file as a whole is refused (``code`` is a fixed token)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def upload_allowed(user_id):
    """At most ``UPLOADS_PER_WINDOW`` import uploads per user per window (cache-based, shared by workers in production)."""
    from django.core.cache import cache
    key = f'rules-import:{user_id}'
    cache.add(key, 0, WINDOW_SECONDS)
    try:
        return cache.incr(key) <= UPLOADS_PER_WINDOW
    except ValueError:
        return True


def activate_template(actor, school_id, code):
    """Create a DRAFT rule of this school from template ``code``. Refuses an unknown code, a missing grade scale (score templates)
    and a code the school already has."""
    if code not in catalog.TEMPLATES:
        raise ValidationError('قالب ناشناخته.')
    template = catalog.TEMPLATES[code]
    settings = RuleSettings.objects.filter(school_id=school_id).first()
    clauses = catalog.instantiate(code, getattr(settings, 'grade_scale_max', None))
    if clauses is None:
        raise ValidationError('سقف مقیاس نمره برای مدرسه تنظیم نشده است؛ ابتدا آن را در تنظیمات قاعده‌ها ثبت کنید.')
    rule = lifecycle.create(actor, school_id, code=code, kind=code, title=template['title'], risk_type=template['risk_type'],
                            severity=template['severity'], connective=template['connective'], clauses=clauses,
                            template=(code, catalog.CATALOG_VERSION))
    audit.record(actor, audit.RULE_FROM_TEMPLATE, rule, school=school_id, detail=f'{code} v{catalog.CATALOG_VERSION}')
    return rule


# ---- workbook ----
def template_workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = 'Rules'
    ws.append(RULE_COLUMNS + [f'{name}{n}' for n in range(1, SLOTS + 1) for name in CLAUSE_COLUMNS])
    example = catalog.TEMPLATES['repeated_absence']
    row = ['my_rule', 'repeated_absence', 'قاعدهٔ نمونه', example['risk_type'], example['severity'], example['connective'], 14]
    for clause in example['clauses'][:SLOTS]:
        row += [clause['metric'], clause['op'], clause['threshold'], clause['window_days'], clause.get('baseline_days', ''),
                clause.get('min_records', '')]
    ws.append(row)
    st = wb.create_sheet('Strategies')
    st.append(STRATEGY_COLUMNS)
    st.append(['مرور هفتگی نمونه', 'academic', 1, 30, 'شرح کوتاه راهبرد'])
    notes = wb.create_sheet('Notes')
    for line in ('Rules land as DRAFT (they need simulation and approval); strategies land INACTIVE until you enable them.',
                 f'kind: one of {", ".join(Rule.KINDS)}', 'risk_type: academic | attendance | behavioral (emotional and family are refused)',
                 'severity: yellow | orange; connective: all | any; cooldown_days 1-365',
                 f'metric: one of {", ".join(sorted(signals.METRICS))}; op: >= > <= <', 'Score thresholds are in score units of your school scale.',
                 'intervention_type: academic | behavioral | emotional | social; tier 1-3; typical_days 1-365',
                 f'At most {MAX_ROWS} rows per sheet; .xlsx only; text starting with = + - @ is refused; formulas are not evaluated.'):
        notes.append([line])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _text(value):
    return '' if value is None else str(value).strip()


def _num(value):
    text = _text(value).translate(DIGITS).replace('٫', '.')
    return text


KEEP = set(RULE_COLUMNS) | {f'{n}{i}' for i in range(1, SLOTS + 1) for n in CLAUSE_COLUMNS} | set(STRATEGY_COLUMNS) | {'line'}


def trim(rows):
    """Whitelisted columns only, cells cut to ``MAX_CELL`` characters (the session stores this, review L3)."""
    return [{k: (v[:MAX_CELL] if isinstance(v, str) else v) for k, v in row.items() if k in KEEP} for row in rows]


def read_workbook(data):
    """``(rule_rows, strategy_rows)`` as lists of dicts with the 1-based sheet line; raises ``ImportRefused`` for the file."""
    if len(data) > MAX_BYTES:
        raise ImportRefused('file_too_large')
    if not data.startswith(b'PK'):
        raise ImportRefused('not_xlsx')
    try:       # the compressed size is not the cost: refuse a decompression bomb BEFORE openpyxl loads shared strings (review M1)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
                raise ImportRefused('file_too_large')
    except zipfile.BadZipFile:
        raise ImportRefused('not_xlsx') from None
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False)   # formulas stay '=...' text and are refused
    except Exception:       # noqa: BLE001 - any parse failure is one fixed refusal
        raise ImportRefused('not_xlsx') from None
    out = {}
    for name in ('Rules', 'Strategies'):
        rows = []
        if name in wb.sheetnames:
            for index, raw in enumerate(wb[name].iter_rows(values_only=True, max_col=MAX_COLUMNS), start=1):
                if index > MAX_SCANNED:                                   # blank rows count too (review M1)
                    raise ImportRefused('too_many_rows')
                if index == 1:
                    header = [_text(h) for h in raw]
                    continue
                if not any(_text(v) for v in raw):
                    continue
                if len(rows) >= MAX_ROWS:
                    raise ImportRefused('too_many_rows')
                rows.append({'line': index, **{h: raw[i] if i < len(raw) else None for i, h in enumerate(header) if h}})
        out[name] = rows
    return out['Rules'], out['Strategies']


def _guard_text(row, columns):
    for column in columns:
        if _text(row.get(column)).startswith(FORMULA_START):
            raise ValidationError('formula_like_text')


def _rule_args(row):
    _guard_text(row, ['code', 'title', 'kind', 'risk_type', 'severity', 'connective'])
    clauses = []
    for n in range(1, SLOTS + 1):
        metric = _text(row.get(f'metric{n}'))
        if not metric:
            continue
        _guard_text(row, [f'metric{n}', f'op{n}'])
        clause = {'metric': metric, 'op': _text(row.get(f'op{n}'))}
        for key, col, integer in (('threshold', f'threshold{n}', False), ('window_days', f'window_days{n}', True),
                                  ('baseline_days', f'baseline_days{n}', True), ('min_records', f'min_records{n}', True)):
            text = _num(row.get(col))
            if text == '':
                continue
            try:
                clause[key] = int(float(text)) if integer else float(text)
            except (ValueError, OverflowError):
                raise ValidationError('bad_number') from None
        clauses.append(clause)
    try:
        cooldown = int(float(_num(row.get('cooldown_days')) or 14))
    except (ValueError, OverflowError):
        raise ValidationError('bad_number') from None
    return dict(code=_text(row.get('code')), kind=_text(row.get('kind')), title=_text(row.get('title')), risk_type=_text(row.get('risk_type')),
                severity=_text(row.get('severity')), connective=_text(row.get('connective')) or 'all', clauses=clauses, cooldown_days=cooldown)


def import_rules(actor, school_id, rows, *, apply):
    """Per-row report ``[(line, 'ok'|'refused', code)]``. With ``apply`` the valid rows are created as drafts."""
    report = []
    seen = set()
    for row in rows:
        try:
            args = _rule_args(row)
            if args['code'] in seen:
                raise ValidationError('duplicate_in_file')
            seen.add(args['code'])
            try:
                with transaction.atomic():
                    lifecycle.create(actor, school_id, **args)         # the real path, so the dry run can never disagree with it
                    if not apply:
                        raise _DryRun
            except _DryRun:
                pass
            except IntegrityError:
                raise ValidationError('code_exists') from None
            report.append((row['line'], 'ok', args['code']))
        except ValidationError as exc:
            report.append((row['line'], 'refused', ' '.join(exc.messages)[:80]))
    return report


def import_strategies(school, rows, *, apply):
    from dashboard.strategy_views import StrategyForm

    report = []
    seen = set()
    for row in rows:
        try:
            _guard_text(row, ['title', 'intervention_type', 'description'])
            data = {'title': _text(row.get('title')), 'intervention_type': _text(row.get('intervention_type')),
                    'tier': _num(row.get('tier')), 'typical_days': _num(row.get('typical_days')) or '30',
                    'description': _text(row.get('description'))}
            data['tier'] = str(int(float(data['tier']))) if data['tier'] else ''
            data['typical_days'] = str(int(float(data['typical_days'])))
            form = StrategyForm(data, school=school)
            if not form.is_valid():
                raise ValidationError('invalid_row')
            title = form.cleaned_data['title']
            if title in seen:
                raise ValidationError('duplicate_in_file')
            seen.add(title)
            if apply:
                obj = form.save(commit=False)
                obj.school, obj.is_active = school, False        # lands inactive (owner decision 2026-11-02)
                obj.save()
            report.append((row['line'], 'ok', title))
        except (ValidationError, ValueError, OverflowError) as exc:      # fixed tokens only: never echo a cell value (review I2)
            report.append((row['line'], 'refused', ' '.join(exc.messages)[:80] if isinstance(exc, ValidationError) else 'invalid_row'))
    return report
