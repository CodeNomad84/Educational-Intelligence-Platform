"""SchoolAdmin pages for deterministic rules (0025). BASE module (no ``module=`` gate), SchoolAdmin only, one school at a time.

The school comes from the admin's own memberships (``school_page``: validated selection among ``school_ids_for_admin``);
every rule is looked up inside that school, so another school's id is a 404. Audit rows hold codes and counts only.
Grade Lead, Teacher, Counselor, Parent, Student, superuser and PlatformAdmin are refused (403) by ``role_required(ADMIN)``.
"""
import math

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.school_views import school_page
from schools import audit

from . import lifecycle, quality, rules, signals
from .models import Rule, RuleRun, RuleSettings

UNVALIDATED = ('آستانه‌ها پیشنهاد اولیه و اعتبارسنجی‌نشده‌اند؛ پیش از فعال‌سازی، معلمان همین مدرسه باید آن‌ها را بازبینی کنند.')
ACTIONS = {'submit': lifecycle.submit, 'approve': lifecycle.approve, 'reopen': lifecycle.reopen, 'pause': lifecycle.pause,
           'resume': lifecycle.resume, 'archive': lifecycle.archive}
SLOTS = 4


def _settings(school):
    return RuleSettings.objects.get_or_create(school=school)[0]


def _number(raw, name, integer=False):
    raw = (raw or '').strip()
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise ValidationError(f'{name}: عدد نامعتبر.') from None
    if not integer and not math.isfinite(value):
        raise ValidationError(f'{name}: عدد نامعتبر.')
    return value


def _parse_clauses(post):
    clauses = []
    for n in range(SLOTS):
        metric = (post.get(f'c{n}_metric') or '').strip()
        if not metric:
            continue
        clause = {'metric': metric, 'op': (post.get(f'c{n}_op') or '').strip(),
                  'threshold': _number(post.get(f'c{n}_threshold'), 'آستانه'),
                  'window_days': _number(post.get(f'c{n}_window'), 'بازه', integer=True)}
        if (post.get(f'c{n}_baseline') or '').strip():
            clause['baseline_days'] = _number(post.get(f'c{n}_baseline'), 'دورهٔ مبنا', integer=True)
        if (post.get(f'c{n}_min') or '').strip():
            clause['min_records'] = _number(post.get(f'c{n}_min'), 'حداقل رکورد', integer=True)
        clauses.append(clause)
    return clauses


def _fields(post):
    return dict(title=post.get('title') or '', risk_type=post.get('risk_type') or '', severity=post.get('severity') or '',
                connective=post.get('connective') or 'all', clauses=_parse_clauses(post),
                cooldown_days=_number(post.get('cooldown_days'), 'مهلت', integer=True))


def _slots(clauses):
    rows = [dict(c) for c in clauses][:SLOTS]
    return rows + [{} for _ in range(SLOTS - len(rows))]


def _context(school, request, **extra):
    from schools.models import School
    from students.student_school import allowed_school_ids
    return {'school': school, 'my_schools': School.objects.filter(pk__in=allowed_school_ids(request.user)).order_by('name'),
            'unvalidated': UNVALIDATED, 'metrics': sorted(signals.METRICS), 'ops': list(signals.OPS),
            'risk_types': Rule.RULE_RISK_TYPES, **extra}


@school_page
@never_cache
def index(request, school):
    rows = list(Rule.objects.filter(school=school).select_related('created_by', 'approved_by'))
    return render(request, 'risk/rules_index.html', _context(
        school, request, rules=rows, settings=_settings(school), kinds=Rule.KINDS, starters=sorted(rules.STARTERS),
        runs=RuleRun.objects.filter(school=school, mode='live').select_related('rule')[:12], quality=quality.rule_quality(school.pk),
        has_active=any(r.status == Rule.Status.ACTIVE for r in rows)))


@school_page
@require_POST
def run_now(request, school):
    """The school is the page's own (membership-derived) school; nothing in the request names a school."""
    runs = rules.run_school(school.pk, triggered_by=request.user)
    if not runs:
        messages.info(request, 'قاعدهٔ فعالی برای اجرا وجود ندارد.')
    for run in runs:
        text = f'{run.rule.code}: ارزیابی {run.evaluated}، هشدار جدید {run.alerts_raised}، تکراری/مهلت {run.skipped_cooldown}'
        if run.status == RuleRun.Status.OK:
            messages.success(request, text)
        else:
            messages.warning(request, f'{text} — {run.get_status_display()}')
    return redirect('rules:index')


@school_page
@require_POST
def save_settings(request, school):
    current = _settings(school)
    try:
        scale = (request.POST.get('grade_scale_max') or '').strip()
        scale = _number(scale, 'سقف مقیاس', integer=True) if scale else None
        if scale is not None and not 1 <= scale <= 1000:
            raise ValidationError('سقف مقیاس نمره بین ۱ و ۱۰۰۰ باشد.')
        breaker = _number(request.POST.get('breaker_percent'), 'آستانهٔ قطع‌کن', integer=True)
        if not 1 <= breaker <= 100:
            raise ValidationError('آستانهٔ قطع‌کن بین ۱ و ۱۰۰ درصد باشد.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        return redirect('rules:index')
    changed = [k for k, new in (('scale', scale), ('breaker', breaker), ('second', bool(request.POST.get('second'))))
               if new != {'scale': current.grade_scale_max, 'breaker': current.breaker_percent, 'second': current.require_second_approver}[k]]
    current.grade_scale_max, current.breaker_percent = scale, breaker
    current.require_second_approver = bool(request.POST.get('second'))
    current.save()
    audit.record(request.user, audit.RULE_SETTINGS, current, school=school, detail=','.join(changed) or 'none')
    messages.success(request, 'تنظیمات ذخیره شد.')
    return redirect('rules:index')


@school_page
@require_http_methods(['GET', 'POST'])
@never_cache
def create(request, school):
    errors, starter = [], rules.STARTERS.get(request.GET.get('from') or '')
    form = {'code': request.GET.get('from') if starter else '', 'kind': request.GET.get('from') if starter else '',
            'cooldown_days': 14, **(starter or {})}
    slots = _slots((starter or {}).get('clauses', []))
    if request.method == 'POST':
        try:
            rule = lifecycle.create(request.user, school.pk, code=(request.POST.get('code') or '').strip(),
                                    kind=request.POST.get('kind') or '', **_fields(request.POST))
        except ValidationError as exc:
            errors, form, slots = exc.messages, request.POST, _slots(_parse_safe(request.POST))
        else:
            messages.success(request, 'پیش‌نویس ساخته شد.')
            return redirect('rules:detail', pk=rule.pk)
    return render(request, 'risk/rules_form.html', _context(
        school, request, rule=None, errors=errors, form=form, slots=slots, kinds=Rule.KINDS, editable=True))


def _parse_safe(post):
    try:
        return _parse_clauses(post)
    except ValidationError:
        return []


@school_page
@require_http_methods(['GET', 'POST'])
@never_cache
def detail(request, school, pk):
    rule = get_object_or_404(Rule.objects.filter(school=school), pk=pk)
    errors, form = [], None
    if request.method == 'POST':
        try:
            lifecycle.edit(rule, request.user, **_fields(request.POST))
        except ValidationError as exc:
            errors, form = exc.messages, request.POST
        else:
            messages.success(request, 'ذخیره شد؛ قاعده به پیش‌نویس برگشت و باید دوباره شبیه‌سازی شود.')
            return redirect('rules:detail', pk=rule.pk)
    editable = rule.status in lifecycle.EDITABLE
    return render(request, 'risk/rules_form.html', _context(
        school, request, rule=rule, errors=errors, editable=editable, kinds=Rule.KINDS,
        form=form or {'code': rule.code, 'kind': rule.kind, 'title': rule.title, 'risk_type': rule.risk_type, 'severity': rule.severity,
                      'connective': rule.connective, 'cooldown_days': rule.cooldown_days},
        slots=_slots(rule.clauses if form is None else _parse_safe(form)),
        can={'simulate': rule.status in lifecycle.EDITABLE, 'submit': rule.status == Rule.Status.SIMULATED,
             'approve': rule.status == Rule.Status.PENDING, 'reopen': rule.status in (Rule.Status.SIMULATED, Rule.Status.PENDING),
             'pause': rule.status == Rule.Status.ACTIVE, 'resume': rule.status == Rule.Status.PAUSED,
             'archive': rule.status in (Rule.Status.DRAFT, Rule.Status.SIMULATED, Rule.Status.PENDING, Rule.Status.PAUSED),
             'clone': True}))


@school_page
@require_POST
def action(request, school, pk):
    rule = get_object_or_404(Rule.objects.filter(school=school), pk=pk)
    name = request.POST.get('do') or ''
    try:
        if name == 'simulate':
            rule, result = lifecycle.simulate(rule, request.user)
            return render(request, 'risk/rules_simulation.html', _context(school, request, rule=rule, result=result))
        if name == 'clone':
            return redirect('rules:detail', pk=lifecycle.clone(rule, request.user).pk)
        if name not in ACTIONS:
            raise ValidationError('عملیات نامعتبر.')
        ACTIONS[name](rule, request.user)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    else:
        messages.success(request, 'انجام شد.')
    return redirect('rules:detail', pk=rule.pk)
