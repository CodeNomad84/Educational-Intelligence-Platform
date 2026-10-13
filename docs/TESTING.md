# TESTING

**CURRENT (Phase 1, verified 2026-10-12 inside the Docker Compose containers on rebuilt images):** **38 Django tests + 24 FastAPI tests** pass; `manage.py check` clean; `makemigrations --check --dry-run` reports no changes. Stdlib `unittest` / Django `TestCase` only (no new dependency). No CI yet (T-01). pytest remains DECISION REQUIRED (Phase 2).
Environment of that run: Django 5.2.15, DRF 3.15.2, PyJWT 2.15.1 (Django image), FastAPI 0.111.0, pydantic 2.14.0, PyJWT 2.9.0, torch 2.0.1+cu117, Python 3.10.22, PostgreSQL 16 + pgvector 0.8.5 (Django tests run against PostgreSQL under `config.settings.production`).
Commands (run from the repository root):
- `docker compose exec -T django python manage.py check`
- `docker compose exec -T django python manage.py makemigrations --check --dry-run`
- `docker compose exec -T django python manage.py test students dashboard`
- `docker compose exec -T fastapi python -m unittest discover -s tests -t .` (fakes torch and the RAG module, except `EmbeddingFailureTests`, which loads the real `rag_service.py` with only `ollama`/`psycopg2`/`pgvector` faked: it verifies routing, authentication, authorization and validation, not model loading)
Live probes (not part of the suite, run 2026-10-12): role x route matrix against the running FastAPI, token-validation and cross-token probes, startup validation of `SERVICE_JWT_SECRET` with the real `main.py`, a Celery `debug_task` round trip, and the runbook verification SQL of `FASTAPI_DB_ROLE.md`.
Superseded (historical, do not cite as current): the 2026-10-11 results of 31 Django and 14 FastAPI tests, run on the owner's machine and in a stubbed sandbox before the Round 2/3 policy changes.
Not covered: a real Ollama embedding model (none pulled), RAG retrieval and document-level ACL (RAG is disabled in Phase 1), full browser flows, model quality (see `DATA_AND_ARTIFACTS.md`), GPU execution, and any historical comparison of test assertions (no baseline commit exists).

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
