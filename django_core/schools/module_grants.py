"""Grant optional modules to a school (no audit event): used by the demo seed and by tests. Operators use set_school_module."""
from datetime import date

from .entitlements import MODULES
from .models import SchoolModule


def grant(school, *keys, starts_on=date(2020, 1, 1), ends_on=None):
    for key in keys or MODULES:
        SchoolModule.objects.update_or_create(school=school, module_key=key, starts_on=starts_on, defaults={'ends_on': ends_on})
