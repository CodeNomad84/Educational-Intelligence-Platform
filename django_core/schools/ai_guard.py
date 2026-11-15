"""AI trial guard: a per-school daily / monthly call cap for the AI assistants (advisor_ai, tutor_ai).

A config value, not billing: ``School.ai_daily_cap`` / ``ai_monthly_cap`` (platform admin, Django admin), falling back to
``settings.AI_DEFAULT_DAILY_CAP`` / ``AI_DEFAULT_MONTHLY_CAP``. Call ``consume`` in the Django caller BEFORE any LLM or
FastAPI request; it takes a slot and raises ``AICapReached`` (nothing is sent) when a cap is hit. A call that produced no
answer must be given back with ``refund`` (change 0044 / E2E F05): the cap counts delivered answers, not attempts, so a
provider outage cannot exhaust a school's day. Counts only, no content.
"""
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import AICallUsage, School


class AICapReached(Exception):
    def __init__(self, period):
        self.period = period      # 'daily' | 'monthly'
        super().__init__(period)

    @property
    def message_fa(self):
        return ('سقف روزانهٔ استفاده از دستیار هوشمند برای مدرسهٔ شما پر شده است؛ فردا دوباره امتحان کنید.' if self.period == 'daily'
                else 'سقف ماهانهٔ استفاده از دستیار هوشمند برای مدرسهٔ شما پر شده است؛ برای افزایش سقف با پشتیبانی تماس بگیرید.')


def caps_for(school):
    return (school.ai_daily_cap if school.ai_daily_cap is not None else getattr(settings, 'AI_DEFAULT_DAILY_CAP', 100),
            school.ai_monthly_cap if school.ai_monthly_cap is not None else getattr(settings, 'AI_DEFAULT_MONTHLY_CAP', 1000))


def consume(school, module_key, on=None):
    on = on or timezone.localdate()
    with transaction.atomic():
        school = School.objects.select_for_update().get(pk=getattr(school, 'pk', school))   # serialises concurrent calls
        daily, monthly = caps_for(school)
        row, _ = AICallUsage.objects.get_or_create(school=school, module_key=module_key, day=on)
        if row.count >= daily:
            raise AICapReached('daily')
        used = AICallUsage.objects.filter(school=school, module_key=module_key, day__year=on.year,
                                          day__month=on.month).aggregate(n=Sum('count'))['n'] or 0
        if used >= monthly:
            raise AICapReached('monthly')
        AICallUsage.objects.filter(pk=row.pk).update(count=F('count') + 1)


def refund(school, module_key, on=None):
    """Give back one unit taken by ``consume`` when the call delivered no answer (E2E F05).

    A provider 5xx, a timeout or a refused request used to keep the slot, so one outage could exhaust the school's whole
    daily cap with zero answers delivered. Never below zero: a duplicated refund, or a refund after the day rolled over,
    is a no-op instead of a negative count.
    """
    on = on or timezone.localdate()
    school_id = getattr(school, 'pk', school)
    with transaction.atomic():
        row = (AICallUsage.objects.select_for_update()
               .filter(school_id=school_id, module_key=module_key, day=on, count__gt=0).first())
        if row is not None:
            AICallUsage.objects.filter(pk=row.pk).update(count=F('count') - 1)
