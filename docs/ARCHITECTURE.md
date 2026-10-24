# ARCHITECTURE

Labels: CURRENT = verified at commit `3404a1a` (resolvable in this repository's history) and re-verified in Docker on 2026-10-12; TARGET = intended. Defect details: `audit/STAGE0_BASELINE.md`.

## Established decisions (owner-approved; not reopened without an L3 proposal)
1. Django = operational core (auth, RBAC, school entities, workflows, admin).
2. FastAPI = AI/RAG/analytics layer (LLM, RAG, prediction, extraction).
3. PostgreSQL (+ pgvector for vectors, JSONB where justified).
4. React + Bootstrap 5, RTL-first, role-specific dashboards — TARGET; migrated incrementally from Django templates.
5. Modular monolith + AI service; no microservices without documented reason.
6. AI is advisory; humans decide. Deterministic rules before ML.
7. Zero rewrite: preserve and evolve the existing codebase.
8. School-ready design, no premature enterprise multi-tenancy (ADR-0004).
9. Student 360 is the central domain concept.

## CURRENT (verified)
- `django_core/`: apps `students` (Student, Grade, Attendance; DRF at `/api/students/`) and `dashboard` (server-rendered templates); `config/`.
- `fastapi_core/`: `main.py` (chat, documents/RAG endpoints), `rag_service.py`, `auth.py` (JWT), `data_pipeline.py`, training scripts, committed model files.
- `docker-compose.yml`: django, celery, celery_beat, fastapi, postgres (pgvector pg16), redis, minio, ollama.
- **Phase 1 (branch `phase-1/boot-security`, VERIFIED 2026-10-12 in Docker Compose on PostgreSQL 16 + pgvector with real Django 5.2.15 / DRF 3.15.2 / FastAPI 0.111.0 / torch 2.0.1+cu117; test results in `TESTING.md`):** the stack boots, migrations apply, Celery executes a task, authorization and disabled-RAG policy verified live. **NOT VERIFIED:** an embedding model (none pulled), RAG retrieval, GPU execution, a second-device LAN test. Frontend is Django templates, not React (DOC-01).
- **DB ownership (CURRENT after Phase 1):** Django migrations own the `documents` table (`students/0007_rag_documents_table`, PostgreSQL only, idempotent; applied and re-run safely on PostgreSQL 16, verified 2026-10-12). FastAPI performs no DDL, connects as least-privilege `fastapi_user` (SELECT, DELETE; `FASTAPI_DB_ROLE.md`), and startup only checks the table exists.
- **Service trust (CURRENT after Phase 1, interim, ADR-0002 PROPOSED):** Django sends FastAPI a 60-second HS256 token (`iss school-django`, `aud school-fastapi`, `sub`, `roles`) signed with env `SERVICE_JWT_SECRET` (no default; ≥32 chars; unset ⇒ fail closed). FastAPI authorizes by role. Symmetric shared secret; owner ratification DECISION REQUIRED.
- Django and FastAPI share one database (S-08 unchanged: FastAPI still connects with a read/write role). The old FastAPI-managed schema (D-03, D-04) was removed in Phase 1; D-01 (`students.Document` migration state vs. missing model): the model was enabled in `c51ead2` and `makemigrations --check --dry-run` reports no changes (2026-10-13) — RESOLVED.

## TARGET
- Single clear data-ownership model: Django owns operational data and migrations (ADR-0001 PROPOSED).
- Authenticated service-to-service calls (ADR-0002 PROPOSED); FastAPI not publicly exposed.
- Authorization model with object/school scope (ADR-0003 DECISION REQUIRED); school key (ADR-0004 PROPOSED).
- Data layers Raw → Extracted → Validated → Canonical → Derived → Predictions with provenance — future decision, to be proposed in Phase 4 (ADR-0009 reserved, no file yet; renumbered from 0005 on 2026-10-16).
- Rules/Risk/Alert/Intervention pipeline; RAG with ACL before retrieval; Study vs School assistants (`AI_GOVERNANCE.md`).

## Modules & licensing (CURRENT, Django side only)

- **Sellable keys (exactly four):** `advisor_ai` (staff-facing School Assistant, LLM/RAG), `tutor_ai` (student-facing study assistant), `exams`, `mission`. `exams` and `mission` are declared but not built.
- **Always on (base, no rows):** auth/roles, school structure, bulk accounts, grades, attendance, teacher recommendations, the simple student views, **Student 360 and counseling** (referrals, counselor notes, refer form, counselor pages), rule-based risk / early warning and ML `/predict` without an LLM, audit. Any future analytic section is base unless it calls an LLM or is one of the four sellable modules.
- **Table:** `schools.SchoolModule(school, module_key, starts_on, ends_on null)`; no row, expired or not-yet-started = OFF. One check only: `schools/entitlements.module_enabled(school, key, on=today)`. Changes are audit-logged (`module_change`, via `set_school_module`).
- **Disabled** = data retained, reads and writes blocked at the route (403). Gates: `role_required(..., module=)` (user has it in one of their schools), `require_module(school, key)` (object's school), `ModuleRequired` on DRF viewsets, `ENABLED_MODULES` for menu hiding only.
- **Rule:** every new route or AI call is either gated by one of the four keys or explicitly base. AI features check entitlement for **each data source** (e.g. `mission`, `exams`) before retrieval/generation; data from a non-licensed module is never passed to a model. Django-side only; the FastAPI token carries no module claim yet.
- **Known ungated surface:** the Django admin. Superusers/PlatformAdmin have no school, so module-gated routes refuse them.

## Constraints
No new service/dependency without L3 proposal. No real student data until security baseline exit (`SECURITY.md`). Configuration over custom code (`CUSTOMIZATION.md`).

## Open architectural decisions
ADR-0001..0004 (see `adr/`). Future/deferred (numbers reserved, no files yet): data layering & provenance (0005, Phase 4), React mechanics (0006), RAG (0007), LLM provider/egress (0008).
