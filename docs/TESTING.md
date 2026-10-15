# TESTING

**CURRENT (verified 2026-10-15, Docker Compose, rebuilt images):** **232 Django tests (PostgreSQL 16, `students dashboard`) + 24 FastAPI tests** pass; `manage.py check` clean; `makemigrations --check --dry-run` reports no changes; `students` migrations 0001-0009 applied on a fresh database. Stdlib `unittest` / Django `TestCase` only (no new dependency). No CI yet (T-01). pytest remains DECISION REQUIRED (Phase 2).
Environment of that run: Django 5.2.15, DRF 3.15.2, PyJWT 2.15.1 (Django image), FastAPI 0.111.0, pydantic 2.14.0, PyJWT 2.9.0, torch 2.0.1+cpu (CPU-only wheel, `cuda.is_available()` False; fastapi image 2.5 GB, was 8.26 GB with `+cu117`), Python 3.10.22, PostgreSQL 16 + pgvector 0.8.5.
**Single Django command (host virtualenv, SQLite, no Docker):** `scripts/run_tests.sh` runs `check`, `makemigrations --check --dry-run`, `test students dashboard schools` (development settings) and `test demo_intel` (demo settings), stopping at the first failure. Result 2026-10-15: check clean, no migration changes, **256** + **32** tests OK. It does **not** cover FastAPI, PostgreSQL or Docker; CI (T-01) stays deferred.
**Why the counts differ:** the SQLite command also runs the `schools` app (24 tests), the PostgreSQL command lists `students dashboard` only: 232 + 24 = 256. Both exercise the same `students`/`dashboard` tests. Tests must be backend-neutral: `varchar` limits (`national_id` 10, `class_name` 50) are enforced only on PostgreSQL, so no test may depend on SQLite storing an over-limit value (see commit `3bf3b8c`).

**Update 2026-10-16 (C4b):** `students dashboard schools` = **284 tests** on SQLite (`scripts/run_tests.sh`, plus 32 `demo_intel`) and on PostgreSQL 16 (one-off container, all OK; test DB only, real data untouched). New: `schools/test_c4b.py` (17) and one extended grant assertion (8 -> 12 Admin permissions). Migration `schools/0002` reversibility on PostgreSQL: NOT VERIFIED (no backward run). FastAPI not re-run (no change).

**Update 2026-10-16 (after `/test-fastapi/` removal and C4 `setup_staff_roles`):** `students dashboard schools` = **267 tests** on both SQLite (`scripts/run_tests.sh`, plus 32 `demo_intel`) and PostgreSQL 16 (container, all OK). The PostgreSQL command now lists `schools` too. New tests: `dashboard` `RemovedDebugRouteTests` (1) and `schools/test_setup_staff_roles.py` (10). FastAPI suite not re-run in this step (no FastAPI change).

Docker commands (run from the repository root):
- `docker compose exec -T django python manage.py check`
- `docker compose exec -T django python manage.py makemigrations --check --dry-run`
- `docker compose exec -T django python manage.py test students dashboard`
- `docker compose exec -T fastapi python -m unittest discover -s tests -t .` (fakes torch and the RAG module, except `EmbeddingFailureTests`, which loads the real `rag_service.py` with only `ollama`/`psycopg2`/`pgvector` faked: it verifies routing, authentication, authorization and validation, not model loading)
Live probes (not part of the suite, run 2026-10-12): role x route matrix against the running FastAPI, token-validation and cross-token probes, startup validation of `SERVICE_JWT_SECRET` with the real `main.py`, a Celery `debug_task` round trip, and the runbook verification SQL of `FASTAPI_DB_ROLE.md`.
Superseded (historical, do not cite as current): the 2026-10-11 results of 31 Django and 14 FastAPI tests (owner's machine, stubbed sandbox), and the 2026-10-12 results of 38 Django tests on PostgreSQL / `torch 2.0.1+cu117`, before the import, class-linking and school-scoping tests.

**KNOWN ISSUE (CURRENT RISK - NOT YET FIXED): `national_id` is normalised on the import path only.** The import maps Persian/Arabic-Indic digits to ASCII (commit `72379b1`); the dashboard form, the admin and the API serializer store what was typed. Matching is exact string equality and `unique=True` (`students/models.py`), so a Persian-digit id created elsewhere is not matched by an imported ASCII id, the unique constraint does not catch the duplicate, and the dashboard search (`icontains`) does not match across scripts. Future proposal (not approved): option (b), normalise in `Student.save()` or a shared helper plus a data migration (L2).
Not covered: a real Ollama embedding model (none pulled), RAG retrieval and document-level ACL (RAG is disabled in Phase 1), full browser flows, model quality (see `DATA_AND_ARTIFACTS.md`), GPU execution, and any historical comparison of test assertions against `3404a1a` (now possible from `git log`; not performed).

## Pyramid (TARGET)
Unit → integration/API → permission/RBAC → data integrity → AI/RAG evaluation → frontend → E2E → regression. Weight toward permission and API tests first.

## Mandatory regression flows (TARGET)
Login · RBAC · student/parent/teacher access · attendance · assessment · risk detection · alert · intervention · RAG permissions.

## Gates
| Gate | Meaning | Phase |
|---|---|---|
| G0 | Docs/config only; no code touched (git diff shows only docs) | 0 |
| G1 | Stack boots; migrations apply on empty DB; `manage.py check` clean | 1 — VERIFIED 2026-10-12: Docker Compose stack boots, migrations (incl. `students/0007`) applied on PostgreSQL 16 + pgvector, `check` clean. "Empty cluster" bring-up with the role runbook not run. |
| G2 | Containment checks pass (below) | 1 — VERIFIED 2026-10-12 by tests and live probes, including host reachability of 5432/6379/9000/9001 (closed). A second-device LAN test was NOT RUN. |
| G3 | Test harness runs in CI-able command; permission tests exist | 2 |
| G4 | Security baseline exit criteria met (`SECURITY.md`) | 3 |
| G5 | Feature regression suite green for touched flows | each feature |

## Containment checks (Phase 1, TARGET)
Unauthenticated FastAPI calls rejected; parent cannot read other students; non-staff cannot create/delete; DB/Redis/MinIO/Ollama ports not published externally; no secret defaults used at startup.

## Rules
Report real output only. A change touching auth/permissions needs a permission test. Synthetic data only.
