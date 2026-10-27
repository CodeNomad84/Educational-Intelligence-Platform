"""Lifecycle of a rule version (0025): draft > simulated > pending_approval > active > paused > archived.

All writes to a rule go through here. Every function takes the ``actor`` and refuses (``PermissionDenied``) unless the actor is a
SchoolAdmin of the rule's school (``school_ids_for_admin``, re-checked at call time); the views add the same gate on top.
* ``edit`` works on draft/simulated/pending and always sends the rule back to draft (``params_hash`` cleared): a simulation or an
  approval never covers parameters that changed afterwards.
* ``simulate`` (draft or simulated -> simulated) stores the ``params_hash`` it ran for; ``submit`` and ``approve`` require the hash to
  equal the current parameters.
* ``approve``: one approver (any SchoolAdmin of the school); with ``RuleSettings.require_second_approver`` the approver must not be
  the author. Activation archives the previous live version of the same code in the same transaction.
* active/paused/archived parameters never change (model guard); ``clone`` creates the next version as a draft.
"""
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from schools import audit
from students.access import school_ids_for_admin

from . import rules
from .models import Rule, RuleRun, RuleSettings

UNFINISHED = (Rule.Status.DRAFT, Rule.Status.SIMULATED, Rule.Status.PENDING)
EDITABLE = UNFINISHED


def _admin_of(actor, school_id):
    if school_id not in school_ids_for_admin(actor):
        raise PermissionDenied


def _settings(school_id):
    return RuleSettings.objects.filter(school_id=school_id).first()


def _locked(rule, actor):
    locked = Rule.objects.select_for_update().get(pk=rule.pk)
    _admin_of(actor, locked.school_id)
    return locked


def _check(rule):
    rules.validate_rule_fields(kind=rule.kind, risk_type=rule.risk_type, severity=rule.severity, cooldown_days=rule.cooldown_days)
    rule.clauses = rules.validate_clauses(rule.clauses, rule.connective, school_id=rule.school_id)


@transaction.atomic
def create(actor, school_id, *, code, kind, title, risk_type, severity, connective, clauses, cooldown_days=14):
    """New code -> version 1 draft. The code is unique per school (a new version of a code goes through ``clone``)."""
    _admin_of(actor, school_id)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}', code or ''):
        raise ValidationError('کد: حروف کوچک انگلیسی، رقم، خط تیره یا زیرخط (حداکثر ۴۰).')
    if Rule.objects.filter(school_id=school_id, code=code).exists():
        raise ValidationError('این کد قبلاً استفاده شده است؛ برای نسخهٔ جدید از «کپی» استفاده کنید.')
    rule = Rule(school_id=school_id, code=code, version=1, kind=kind, title=title.strip()[:120], risk_type=risk_type,
                severity=severity, connective=connective, clauses=clauses, cooldown_days=cooldown_days, created_by=actor)
    if not rule.title:
        raise ValidationError('عنوان لازم است.')
    _check(rule)
    rule.save()
    audit.record(actor, audit.RULE_CREATE, rule, school=school_id, detail=f'{code} v1')
    return rule


@transaction.atomic
def edit(rule, actor, *, title, risk_type, severity, connective, clauses, cooldown_days):
    locked = _locked(rule, actor)
    if locked.status not in EDITABLE:
        raise ValidationError('فقط پیش‌نویس، شبیه‌سازی‌شده یا منتظر تأیید قابل ویرایش است؛ از نسخه کپی بگیرید.')
    locked.title, locked.risk_type, locked.severity = title.strip()[:120], risk_type, severity
    locked.connective, locked.clauses, locked.cooldown_days = connective, clauses, cooldown_days
    if not locked.title:
        raise ValidationError('عنوان لازم است.')
    _check(locked)
    locked.status, locked.params_hash = Rule.Status.DRAFT, ''
    locked.save()
    audit.record(actor, audit.RULE_EDIT, locked, school=locked.school_id, detail=f'{locked.code} v{locked.version}')
    return locked


@transaction.atomic
def clone(source, actor):
    _admin_of(actor, source.school_id)
    if Rule.objects.filter(school_id=source.school_id, code=source.code, status__in=UNFINISHED).exists():
        raise ValidationError('یک نسخهٔ در حال کار از این قاعده وجود دارد؛ ابتدا آن را تمام کنید.')
    version = (Rule.objects.filter(school_id=source.school_id, code=source.code).aggregate(m=Max('version'))['m'] or 0) + 1
    copy = Rule.objects.create(
        school_id=source.school_id, code=source.code, version=version, kind=source.kind, title=source.title,
        risk_type=source.risk_type, severity=source.severity, connective=source.connective, clauses=source.clauses,
        cooldown_days=source.cooldown_days, created_by=actor)
    audit.record(actor, audit.RULE_CREATE, copy, school=copy.school_id, detail=f'{copy.code} v{version}')
    return copy


def _status(rule, actor, status):
    audit.record(actor, audit.RULE_STATUS, rule, school=rule.school_id, detail=status)


@transaction.atomic
def simulate(rule, actor, *, as_of=None, weeks=8):
    """draft/simulated -> simulated (stores the hash) and the aggregate weekly counts. Writes one RuleRun of counts, no alert/hit."""
    locked = _locked(rule, actor)
    if locked.status not in (Rule.Status.DRAFT, Rule.Status.SIMULATED, Rule.Status.PENDING):
        raise ValidationError('فقط قاعدهٔ در حال کار شبیه‌سازی می‌شود.')
    _check(locked)
    as_of = as_of or timezone.localdate()
    result = rules.simulate(locked, as_of=as_of, weeks=weeks)
    if locked.status == Rule.Status.DRAFT:
        locked.status = Rule.Status.SIMULATED
    locked.params_hash = rules.params_hash(locked)
    locked.save()
    last = result[-1]
    RuleRun.objects.create(school_id=locked.school_id, rule=locked, mode='simulation', as_of=as_of, triggered_by=actor,
                           evaluated=last['evaluated'], hits=last['fired'] or 0, skipped_insufficient=last['insufficient'])
    audit.record(actor, audit.RULE_SIMULATE, locked, school=locked.school_id, detail=f"w{weeks}e{last['evaluated']}")
    return locked, result


def _hash_ok(rule):
    return bool(rule.params_hash) and rule.params_hash == rules.params_hash(rule)


@transaction.atomic
def submit(rule, actor):
    locked = _locked(rule, actor)
    if locked.status != Rule.Status.SIMULATED or not _hash_ok(locked):
        raise ValidationError('ابتدا قاعده را با پارامترهای فعلی شبیه‌سازی کنید.')
    locked.status = Rule.Status.PENDING
    locked.save()
    _status(locked, actor, locked.status)
    return locked


@transaction.atomic
def reopen(rule, actor):
    locked = _locked(rule, actor)
    if locked.status not in (Rule.Status.SIMULATED, Rule.Status.PENDING):
        raise ValidationError('این تغییر وضعیت مجاز نیست.')
    locked.status, locked.params_hash = Rule.Status.DRAFT, ''
    locked.save()
    _status(locked, actor, locked.status)
    return locked


@transaction.atomic
def approve(rule, actor):
    locked = _locked(rule, actor)
    if locked.status != Rule.Status.PENDING or not _hash_ok(locked):
        raise ValidationError('فقط قاعدهٔ منتظر تأیید با پارامترهای شبیه‌سازی‌شده فعال می‌شود.')
    settings = _settings(locked.school_id)
    if settings is not None and settings.require_second_approver and locked.created_by_id == actor.pk:
        raise ValidationError('تأییدکننده باید غیر از سازندهٔ قاعده باشد.')
    locked.clauses = rules.validate_clauses(locked.clauses, locked.connective, school_id=locked.school_id)   # fail closed: scale
    for old in Rule.objects.select_for_update().filter(school_id=locked.school_id, code=locked.code,
                                                       status__in=(Rule.Status.ACTIVE, Rule.Status.PAUSED)):
        old.status = Rule.Status.ARCHIVED
        old.save()
    locked.status, locked.approved_by, locked.approved_at = Rule.Status.ACTIVE, actor, timezone.now()
    locked.save()
    _status(locked, actor, locked.status)
    return locked


@transaction.atomic
def pause(rule, actor):
    locked = _locked(rule, actor)
    if locked.status != Rule.Status.ACTIVE:
        raise ValidationError('فقط قاعدهٔ فعال متوقف می‌شود.')
    locked.status = Rule.Status.PAUSED
    locked.save()
    _status(locked, actor, locked.status)
    return locked


@transaction.atomic
def resume(rule, actor):
    locked = _locked(rule, actor)
    if locked.status != Rule.Status.PAUSED:
        raise ValidationError('فقط قاعدهٔ متوقف ادامه می‌یابد.')
    locked.clauses = rules.validate_clauses(locked.clauses, locked.connective, school_id=locked.school_id)
    locked.status = Rule.Status.ACTIVE
    locked.save()
    _status(locked, actor, locked.status)
    return locked


@transaction.atomic
def archive(rule, actor):
    locked = _locked(rule, actor)
    if locked.status in (Rule.Status.ACTIVE, Rule.Status.ARCHIVED):
        raise ValidationError('قاعدهٔ فعال ابتدا باید متوقف شود.' if locked.status == Rule.Status.ACTIVE else 'قبلاً بایگانی شده است.')
    locked.status = Rule.Status.ARCHIVED
    locked.save()
    _status(locked, actor, locked.status)
    return locked
