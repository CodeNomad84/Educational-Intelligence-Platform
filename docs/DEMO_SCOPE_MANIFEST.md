# DEMO SCOPE MANIFEST

Everything added for the school-meeting demo is tagged **DEMO SCOPE** so it can be separated from the main
codebase. Tagging convention:

* New files: first line comment `DEMO SCOPE — whole file.`
* Edits inside existing files: wrapped in `DEMO SCOPE begin` … `DEMO SCOPE end`.

Find everything: `grep -rn "DEMO SCOPE" django_core docs --include='*' -l` (exclude `.venv`).

## New files (delete to remove the demo)

| Path | Purpose |
|---|---|
| `django_core/demo_intel/` (whole app) | models, rules, engine, analytics, assistant, views, templates, vendored assets, tests, migration |
| `django_core/config/settings/demo.py` | demo settings (separate DB file, adds `demo_intel`, context processor) |
| `django_core/students/management/` (`__init__.py`, `commands/__init__.py`, `commands/seed_demo.py`) | synthetic data command |
| `django_core/demo_db.sqlite3` | generated demo database (gitignored by `*.sqlite3`) |
| `django_core/.env.demo` | generated fixed demo secret key (gitignored by `.env.*`) |
| `scripts/start_demo.sh` | safe launcher (settings guard, fixed secret, `--noreload`, `--reseed`, `--check`) |
| `docs/DEMO_STATUS.md`, `DEMO_IMPLEMENTATION_PLAN.md`, `DEMO_READINESS_REVIEW.md`, `DEMO_HARDENING_PLAN.md`, `DEMO_GUIDE.md`, `DEMO_SCRIPT.md`, `DEMO_PRESENTATION_CHECKLIST.md`, `DEMO_SCOPE_MANIFEST.md` | documentation |

## Edits to existing files (6 blocks, all inert unless `settings.DEMO_MODE` is true)

| File | Marker | What |
|---|---|---|
| `django_core/dashboard/views.py` | `dashboard_view` | after the Admin check: renders the demo school dashboard |
| `django_core/dashboard/views.py` | `student_detail_view` | after object-scoped lookup, for Admin only: renders the demo profile |
| `django_core/dashboard/views.py` | `login_view` | renders the standalone demo login template |
| `django_core/dashboard/urls.py` | end of file | 3 extra routes under `/demo/…` |
| `django_core/dashboard/templates/dashboard/student_detail.html` | AI button | hidden when `DEMO_MODE` |
| `django_core/dashboard/templates/dashboard/base.html` | sidebar | Chat/Library links (403 in Phase 1) hidden when `DEMO_MODE` |

## Not touched

`students/access.py`, `dashboard/decorators.py` (RBAC), `students/models.py`, `base.py`/`development.py`/`production.py`,
`fastapi_core/`, `docker-compose.yml`, `.env*`, `db.sqlite3`, existing migrations, the unused `behavior/risk/interventions` apps.

## To separate the demo later

1. Delete the new files above.
2. Remove the `DEMO SCOPE begin/end` blocks (6 places in 4 files).
3. Nothing else references the demo; `base.py` never listed `demo_intel`.
