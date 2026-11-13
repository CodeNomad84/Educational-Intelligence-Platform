# CHANGE PROPOSAL — Phase 1: Bootable Baseline + Critical Security Containment
Level: **L3** · Status: DRAFT (scope pre-authorized by the owner's Phase 1 prompt; ADR-0001/0002 remain PROPOSED) · Base: `d2a3201` (Phase 0) on `3404a1a` (both from the owner's previous repository history; neither is present in this repository, which has 0 commits)

## 1. Requirement
Make Django and FastAPI start, make Django own the operational schema, contain S-01 and S-02, add the minimum tests. No features.

## 2. Current behavior (re-verified at `3404a1a`; runtime checks used real Django 5.2.15 / DRF 3.15.2 / FastAPI 0.111.0 sources, with only heavy ML/DB packages stubbed — see "Verification limits")
| ID | Status | Evidence |
|---|---|---|
| B-01 | CONFIRMED (run) | `import main` → `NameError: Depends` (main.py:108) |
| B-02 | CONFIRMED (run) | `manage.py check` → `NameError: Student` (dashboard/models.py:5) |
| B-03 | CONFIRMED (read) | 3 `predict_status` defs; the undecorated one at views.py:236 overrides the `@action` at :180; module-level copy at :274 uses undefined `models` |
| B-04 | CONFIRMED (run) | `manage.py check` with default `config.settings` loads the empty package and "passes" vacuously (no apps configured) |
| B-05 | CONFIRMED (read) | `redirect('login')`, `redirect('dashboard')`, `redirect('upload_students')` lack the `dashboard:` namespace; `LOGIN_URL` unset (login_required → `/accounts/login/`); `upload.html` missing (not fixed: stub, not a boot blocker) |
| B-06 | CONFIRMED (read) | `POST /documents/` passes `metadata` into `parent_id` |
| B-07 | CONFIRMED (read) | stray `@router_v1.get("/chat/")` registered after `include_router` (dead route) |
| B-09 | CONFIRMED (read) | `IsAdminUser.has_permission` defined twice; superuser branch dead |
| S-01 | CONFIRMED (read) | All dashboard views are `@login_required` only: any logged-in user (incl. parents with no group) lists/reads every student, sees school-wide aggregates, creates students, uploads/deletes RAG documents, chats. The DRF API already scopes parents via `Student.parent_user` and is NOT affected for list/retrieve. |
| S-02 | CONFIRMED (read) | Anonymous: `POST /chat/`, `POST /documents/`, `GET /documents/search/`, `POST /upload-document/`, `DELETE /documents/parent/{id}`. `/predict/`, `/documents/list/`, `DELETE /documents/{id}` use `verify_jwt`, whose secret has a hard-coded default, and Django sends no token (so they are currently unreachable from Django). |
| D-03/D-04 | CONFIRMED (read) | FastAPI startup runs `create_documents_table()` (DDL; `DROP TABLE documents CASCADE` on dimension mismatch); `get_db_connection` runs `CREATE EXTENSION` on every connection |

## 3. Desired behavior
Django + FastAPI import and start; Django migrations create the `documents` table; FastAPI performs no DDL; dashboard enforces role + object scope server-side; every FastAPI data route requires a Django-issued, short-lived, role-bearing token; mutations are Admin-only.

## 4. Affected modules
`django_core/{config,dashboard,students}`, `fastapi_core/{main,auth,rag_service}`, `docker-compose.yml` (port only), new `.env.example` (names only).

## 5. Design (minimal; no new dependency)
- **Roles** = existing Django groups `Admin`, `Teacher`, `Parent` (+ superuser ⇒ Admin). New `students/access.py` is the single place that maps user → roles and user → visible students (Parent ⇒ `parent_user=user`). Unknown/no group ⇒ no access.
- **Dashboard policy (interim, deny-by-default)**: dashboard/student list/detail/chat/library: Admin+Teacher; Parent: own children only (list/detail), no dashboard aggregates, no AI/library; create student, document upload/delete, student upload: Admin only. Unauthorized authenticated ⇒ 403; anonymous ⇒ redirect to login; other parent's child ⇒ 404.
- **Service trust (interim, implements ADR-0002 as proposed)**: Django mints an HS256 JWT per call (iss `school-django`, aud `school-fastapi`, `sub`, `roles`, `exp` ≤ 60 s) signed with env `SERVICE_JWT_SECRET`; FastAPI verifies signature/iss/aud/exp and role. No secret ⇒ fail closed (503). Uses PyJWT (already a dependency of both services).
- **FastAPI role map**: Admin+Teacher: `/predict/`, `/api/v1/predict/`, `/chat/`, `/documents/search/`, `/documents/list/`. Admin only: `POST /documents/`, `POST /upload-document/`, `DELETE /documents/{id}`, `DELETE /documents/parent/{id}`. `/` health stays public.
- **DB ownership**: new `students/0007` migration (PostgreSQL-only, idempotent, non-destructive: `CREATE EXTENSION IF NOT EXISTS vector`; `CREATE TABLE IF NOT EXISTS documents … vector(1024)`; index) — DDL copied from the existing FastAPI function. FastAPI: remove `create_documents_table` (incl. DROP) and per-connection `CREATE EXTENSION`; startup only *checks* that the table exists and logs. Existing migrations are not touched.
- **Boot fixes**: add `Depends`; import `Student`/`AUTH_USER_MODEL` in `dashboard/models.py` + additive `dashboard/0001` migration; keep one `predict_status` (the latest, 8-feature version) inside the class with `Avg`; `IsAdminUser` single definition; namespaced redirects; `LOGIN_URL`; `DJANGO_SETTINGS_MODULE` defaults (`manage.py`→development, wsgi/asgi/celery→production); fix `add_document` call; drop dead chat route.
- **Port**: publish FastAPI as `127.0.0.1:8001:8001` (Django reaches it over the compose network by service name, so the host mapping is only for local dev/docs).
- **Not done (out of scope, documented)**: S-03..S-11 except as touched above; teacher scoping (S-04); the other published ports (S-06) — `DECISION REQUIRED` to bind 5432/6379/9000/9001/11434 to loopback too.

## 6. Data impact
Two additive migrations (`students/0007` raw SQL on PostgreSQL only; `dashboard/0001` creates two empty tables). No data migration, no destructive operation. Existing deployments whose `documents` table was created by FastAPI: `IF NOT EXISTS` ⇒ no change.

## 7. API impact
FastAPI routes now require a Bearer service token (breaking for any direct caller — none known). Django API unchanged except `predict` route now actually registered and `IsAdminUser` now admits superusers.

## 8. Frontend impact
Role-based access errors (403/redirect) on dashboard pages; no template changes.

## 9. AI impact
None beyond access control. Risk model, prompts, RAG logic untouched.

## 10. Security impact
Improves S-01, S-02, D-04, part of S-03 (removes FastAPI default JWT secret). Adds a new secret (`SERVICE_JWT_SECRET`) — must be set in `.env` by the owner (not committed). New risk: shared symmetric secret between services (rotation, blast radius) — see Risks.

## 11. Testing strategy
`manage.py test` (Django `TestCase`, sqlite, deterministic) for boot/auth/authz/migration; `python -m unittest` in `fastapi_core/tests` using FastAPI `TestClient` with heavy ML/DB modules replaced by test doubles (declared in the test). No new test dependency.

## 12. Documentation impact
`SECURITY.md` (CURRENT table, interim role policy), `ARCHITECTURE.md` + `SYSTEM_MAP.md` + `MODULE_MAP.md` (CURRENT sections), `TESTING.md` (commands + gates), ADR-0001/0002 status note, `ROADMAP.md`.

## 13. Risks
Unverifiable here: PostgreSQL migration, real ML stack import, Docker bring-up, Celery. Parent redirect/403 behavior is a product-level interim choice. Teachers still see all students (S-04). Symmetric secret. Role names are string-matched group names.

## 14. Recommendation
Proceed as designed. Items needing owner ratification: ADR-0002 interim approach; matrix cells for dashboard roles; vector dimension 1024 (ADR-0001).

### Verification limits (sandbox)
PyPI/Docker/PostgreSQL are unavailable. Django, DRF, simplejwt, django-filter, requests, FastAPI 0.111.0, starlette, pydantic **1.10.17** (project may resolve v2), httpx and PyJWT run from GitHub source checkouts; pandas, celery, torch, numpy, joblib, psycopg2, ollama, fitz, langchain are stubbed. Results are labelled accordingly.
