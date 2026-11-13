# DEMO SCOPE — whole file.
"""Preflight for the live demo. Exits non-zero (CommandError) on a wrong configuration or stale data."""
from django.core.management.base import BaseCommand, CommandError
from django.db.utils import OperationalError

from demo_intel import preflight


class Command(BaseCommand):
    help = "Verify the demo configuration and print mode, database and seed date (DEMO SCOPE)."

    def add_arguments(self, parser):
        parser.add_argument("--max-age", type=int, default=1,
                            help="Maximum age of the seed in days before the check fails (default 1).")
        parser.add_argument("--allow-stale", action="store_true", help="Warn instead of failing on an old seed.")

    def handle(self, *args, **opts):
        problems = preflight.configuration_problems()
        if problems:
            raise CommandError("WRONG CONFIGURATION — refusing to run the demo: " + " ".join(problems))
        try:
            pending = preflight.pending_migrations()
        except OperationalError:
            raise CommandError("Demo database is not initialised. Run: scripts/start_demo.sh --reseed")
        if pending:
            shown = ", ".join(pending[:5]) + (f" (+{len(pending) - 5} more)" if len(pending) > 5 else "")
            raise CommandError(
                f"DATABASE SCHEMA IS BEHIND THE CODE — {len(pending)} unapplied migration(s): {shown}. "
                "Nothing was changed and nothing will be run for you. Options (you choose): "
                "(1) keep the data and only apply the schema: "
                "DJANGO_SETTINGS_MODULE=config.settings.demo python manage.py migrate ; "
                "(2) WARNING — DESTRUCTIVE: scripts/start_demo.sh --reseed migrates AND DELETES every student, "
                "grade, attendance row, observation, counseling note, intervention and demo_* user in "
                "demo_db.sqlite3, then rebuilds the synthetic demo data.")
        try:
            st = preflight.status()
        except OperationalError:
            raise CommandError("Demo database is not initialised. Run: scripts/start_demo.sh --reseed")
        self.stdout.write("DEMO MODE ACTIVE")
        self.stdout.write(f"Database:  {st['database']}")
        self.stdout.write(f"Students:  {st['students']}")
        self.stdout.write(f"Seed date: {st['seed_date']} (age {st['age_days']} day(s))")
        if not st["students"]:
            raise CommandError("Demo database is empty. Run: scripts/start_demo.sh --reseed")
        if st["age_days"] is not None and st["age_days"] > opts["max_age"]:
            msg = (f"Seed is {st['age_days']} day(s) old; storylines drift as time passes. "
                   "Run: scripts/start_demo.sh --reseed")
            if opts["allow_stale"]:
                self.stderr.write(self.style.WARNING("WARNING: " + msg))
            else:
                raise CommandError(msg + "  (or set DEMO_ALLOW_STALE=1 to override)")
