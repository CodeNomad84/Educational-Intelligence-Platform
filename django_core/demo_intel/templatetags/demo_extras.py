# DEMO SCOPE — whole file.
from django import template

from demo_intel.fa import digits

register = template.Library()


@register.filter
def fa(value):
    """Render digits (and decimal points) as Persian."""
    return digits(value)


@register.filter
def pct(value):
    return digits(f"{value:.0f}٪") if value is not None else "—"


@register.filter
def one(value):
    return digits(f"{value:.1f}") if value is not None else "—"
