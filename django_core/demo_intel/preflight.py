# DEMO SCOPE — whole file. Facts about the demo database used by `demo_check` and the launcher.
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from students.management.commands.seed_demo import EXAM_OFFSETS
from students.models import Grade, Student


def db_filename():
    return Path(str(settings.DATABASES["default"]["NAME"])).name


def configuration_problems():
    """Return a list of human-readable problems with the active configuration (empty = OK)."""
    problems = []
    if not getattr(settings, "DEMO_MODE", False):
        problems.append("DEMO_MODE is off (not running with config.settings.demo).")
    expected = getattr(settings, "DEMO_DB_FILENAME", "demo_db.sqlite3")
    if db_filename() != expected:
        problems.append(f"Database is '{db_filename()}', expected '{expected}'.")
    return problems


def seed_date():
    """The day the demo data was seeded (derived from data: newest exam + smallest exam offset)."""
    newest = Grade.objects.order_by("-date").values_list("date", flat=True).first()
    return newest + timedelta(days=min(EXAM_OFFSETS)) if newest else None


def status(today=None):
    today = today or timezone.localdate()
    seeded = seed_date()
    return {
        "database": db_filename(),
        "students": Student.objects.count(),
        "seed_date": seeded,
        "age_days": (today - seeded).days if seeded else None,
    }
