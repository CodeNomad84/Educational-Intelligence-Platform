"""Presentation helpers of the design system (P8-3). No data access: links, labels, CSS classes and date display only."""
from django import template
from django.urls import reverse
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_link(context, name, icon, label, *args, also='', prefix=False, css=''):
    """One sidebar entry. Active when the current view is ``name`` or one of the space-separated view names in ``also``,
    or, with ``prefix``, when the current path starts with the link's path."""
    url = reverse(name, args=args)
    request = context.get('request')
    match = getattr(request, 'resolver_match', None)
    current = match.view_name if match else ''
    active = current == name or current in also.split() or bool(prefix and request and request.path.startswith(url))
    return format_html('<a href="{}" class="eip-nav-link{}{}"{}><i class="bi bi-{}" aria-hidden="true"></i><span>{}</span></a>',
                       url, ' active' if active else '', f' {css}' if css else '',
                       format_html(' aria-current="page"') if active else '', icon, label)


@register.inclusion_tag('dashboard/_empty.html')
def empty_state(title, text='', icon='inbox', action_url='', action_label=''):
    """The shared empty state: icon, title, one sentence, optional action."""
    return {'title': title, 'text': text, 'icon': icon, 'action_url': action_url, 'action_label': action_label}


_STATUS = {   # CSS per status code; the label normally comes from the model's get_*_display
    'new': 'is-warning', 'accepted': 'is-info', 'dismissed': '',
    'planned': 'is-primary', 'active': 'is-primary', 'completed': 'is-success', 'cancelled': '',
    'improved': 'is-success', 'no_change': '', 'worse': 'is-danger', 'not_assessable': '',
    'on_track': 'is-success', 'needs_change': 'is-warning', 'blocked': 'is-danger',
    'open': 'is-primary', 'closed': '',
    'green': 'is-success', 'yellow': 'is-warning', 'orange': 'is-danger', 'red': 'is-danger',
}


@register.simple_tag
def status_badge(code, label=''):
    """A soft badge for a status or severity code with its display label."""
    return format_html('<span class="eip-badge {}"><span class="eip-dot" aria-hidden="true"></span>{}</span>',
                       _STATUS.get(code, ''), label or code)


# --- Persian (Jalali) dates: display only; the database keeps Gregorian dates ----------------------------------------------
MONTHS_FA = ('فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند')


def to_jalali(gy, gm, gd):
    """Gregorian -> Jalali (year, month, day), the standard arithmetic conversion."""
    g_days = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_days[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


@register.filter
def jdate(value, style='short'):
    """``{{ d|jdate }}`` -> 1405/08/10, ``|jdate:'long'`` -> 10 آبان 1405, ``|jdate:'month'`` -> آبان 1405. Datetimes are
    shown in the local time zone; empty input gives ''."""
    if not value:
        return ''
    if hasattr(value, 'hour'):
        from django.utils import timezone
        value = timezone.localtime(value) if timezone.is_aware(value) else value
    jy, jm, jd = to_jalali(value.year, value.month, value.day)
    if style == 'long':
        return f'{jd} {MONTHS_FA[jm - 1]} {jy}'
    if style == 'month':
        return f'{MONTHS_FA[jm - 1]} {jy}'
    return f'{jy}/{jm:02d}/{jd:02d}'
