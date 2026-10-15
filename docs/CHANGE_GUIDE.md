# CHANGE GUIDE — "If I want to change X, where do I look?"

Verified-at: `3404a1a` + Phase 1 branch `phase-1/boot-security`; the commit `3404a1a` is resolvable in this repository's history (verified 2026-10-13); Phase 1 closed at `4c096de`. Paths re-checked against the working tree on 2026-10-12. Schools/vocabulary rows re-verified 2026-10-16 (C4b). Rows marked NOT YET IMPLEMENTED have no location yet; classify via `CHANGE_PROCESS.md`. Any change touching auth/data is at least L2.

| I want to change… | Look at | Notes |
|---|---|---|
| Student fields | `django_core/students/models.py`, `serializers.py`, `dashboard/forms.py`, templates `student_form.html`, new migration | L2; national_id is globally unique (D-06) |
| Grade/attendance logic | `students/models.py`; features in `students/views.py`; FastAPI `data_pipeline.py` (scale/vocab mismatch D-07/D-08) | L2 |
| Who can see/do what | `students/access.py` (roles, student scope), `dashboard/decorators.py` + `dashboard/views.py` (`@role_required`), `students/permissions.py` + `students/views.py` (API), `fastapi_core/main.py` (`require_roles`), `docs/SECURITY.md` | L3 (S-04, ADR-0003) |
| Django→FastAPI trust | `django_core/config/service_auth.py`, `fastapi_core/auth.py`, env `SERVICE_JWT_SECRET` (local file `.env.service`; never in `.env.example` values) | L3 (ADR-0002) |
| FastAPI database role / grants | `FASTAPI_DB_ROLE.md`, `fastapi_core/rag_service.py`, `.env.fastapi` | L3 (authZ/data) |
| Dataset / model artifacts / local secret files | `DATA_AND_ARTIFACTS.md` | L2 |
| RAG documents table | Django migration `students/0007_rag_documents_table.py` (FastAPI must not create schema) | L3 (ADR-0001) |
| Login / tokens | `dashboard/views.py` (login_view), `config/urls.py` (`api/token/`), `config/settings/base.py` | L3 |
| Dashboard/pages | `dashboard/views.py`, `urls.py`, `templates/dashboard/` | React migration TARGET |
| Student import (CSV/XLSX) | `students/views.py` import action | B-10 |
| Risk prediction | `students/views.py` predict/features, `fastapi_core/main.py`, `train_nn_model.py`, `models/` | EXPERIMENTAL |
| Risk thresholds / rules | NOT YET IMPLEMENTED (threshold 0.5 hard-coded in FastAPI) | L2; rule engine Phase 6 |
| Alerts / interventions | NOT YET IMPLEMENTED | Phase 6 |
| Student 360 | NOT YET IMPLEMENTED | Phase 5 |
| RAG chunking / retrieval | `fastapi_core/main.py` (chunking, top_k), `rag_service.py` | L2; ACL needed (A-04) |
| LLM / embedding provider or model | `fastapi_core/rag_service.py`, `docker-compose.yml` (ollama) | L3 (ADR-0008) |
| Add a school / branding / calendar | NOT YET IMPLEMENTED — `docs/CUSTOMIZATION.md`, ADR-0004 | L3 |
| Notifications | `students/tasks.py` (unused), `config/celery.py` | L2 |
| Role group names (`SchoolAdmin`/`Teacher`/`GradeLead`/`Counselor`/`Parent`) | `django_core/students/access.py` constants; FastAPI `fastapi_core/auth.py` `ADMIN` must match; rename = reversible data migration like `students/0010` (L3) | L3 |
| Create the staff role groups / grant Admin school-structure permissions | `django_core/schools/management/commands/setup_staff_roles.py` (`manage.py setup_staff_roles [--fix] [--grant-admin-assignments]`); constants in `students/access.py` | L2 |
| Subject / grade vocabulary; report assignment subjects not in it | `django_core/schools/vocabulary.py` (re-exported by `students/models.py`); `manage.py check_assignment_subjects [--json]` (read-only) | L3 if a value changes (data migration) |
| Grade Lead assignments (model, admin, year picker) | `django_core/schools/models.py` (`GradeLeadAssignment`), `schools/admin.py`; access reading it is C5a, NOT YET IMPLEMENTED | L3 |
| Settings / secrets / ports | `config/settings/`, `docker-compose.yml`, FastAPI `auth.py` | never print secrets (S-03) |
| Tests | `django_core/{students,dashboard}/tests.py`, `fastapi_core/tests/test_security.py`; commands in `docs/TESTING.md` | |
| Reports | NOT YET IMPLEMENTED | |

Answer format for new questions: Feature / Primary module / Backend / Frontend / Database / Configuration / Tests / Related docs / Recommended starting point.
