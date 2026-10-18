# CHANGE GUIDE — "If I want to change X, where do I look?"

Verified-at: `3404a1a` + Phase 1 branch `phase-1/boot-security`; the commit `3404a1a` is resolvable in this repository's history (verified 2026-10-13); Phase 1 closed at `4c096de`. Paths re-checked against the working tree on 2026-10-12. Schools/vocabulary rows re-verified 2026-10-16 (C4b). Access-rule rows re-verified 2026-10-16 (2.2a-4c switch: `students/access.py` decides Grade Lead / Subject Teacher scope by current enrollment). Rows marked NOT YET IMPLEMENTED have no location yet; classify via `CHANGE_PROCESS.md`. Any change touching auth/data is at least L2.

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
| Who may see which student / grade / attendance row; field tiers; identity search | `django_core/students/access.py` (single choke point; since 4c Grade Lead / Subject Teacher scope = CURRENT ENROLLMENT via `_current_enrollment`; `students/access_legacy.py` keeps the pre-switch rule verbatim for `compare_access_parity` and revert; negative tests `students/test_access_switch.py`), `students/serializers.py` (`LIMITED_OMIT`), `students/views.py` (`TierAwareSearchFilter`), `dashboard/views.py`, `student_*.html`; guard test `students/test_access_c5a.py` (`QuerysetChokePointTests`) | L3 |
| Canonical year texts on classes and Grade Lead assignments | `manage.py normalize_year_texts [--apply --log FILE | --revert-from FILE]` (dry-run default, unambiguous conversions only) | L2 (data) |
| Academic years / enrollments (temporal model; read by the access rule since 2.2a-4c) | `django_core/schools/models.py` (`AcademicYear`), `schools/academic_years.py`, `students/models.py` (`Enrollment`, `ImportBatch`, `Grade.enrollment`, `Attendance.enrollment`); reports `check_academic_years`, `check_enrollment_backfill` (read-only); ADR-0011; `manage.py backfill_enrollments [--apply|--revert-backfill]` (dry-run default, evidence-only); `seed_temporal_synthetic` (synthetic, empty DB only); `manage.py import_history --kind roster|grades|attendance --year … --file … [--apply]` / `--revert-batch ID` (year-aware, `students/history_import.py`); `manage.py check_access_switch_ready` (pre-flight, exit 1 if NOT READY), `manage.py compare_access_parity` (legacy vs enrollment rule, exit 1 on unexplained differences); `manage.py rollover_academic_year --to CODE --class-map FILE [--outcomes FILE] [--default promote] [--flip-current] [--deactivate-old-classes] [--deactivate-old-grade-lead-assignments] [--apply]` / `--revert-batch ID` (year rollover, batch-logged); `seed_temporal_realistic` (synthetic, empty DB only); access switch 4c CURRENT since 2026-10-16 (`students/access.py`; report `changes/0006-phase2-2a-4c-access-switch-REPORT.md`) | L3 |
| Role group names (`SchoolAdmin`/`Teacher`/`GradeLead`/`Counselor`/`Parent`) | `django_core/students/access.py` constants; FastAPI `fastapi_core/auth.py` `ADMIN` must match; rename = reversible data migration like `students/0010` (L3) | L3 |
| Create the staff role groups / grant Admin school-structure permissions | `django_core/schools/management/commands/setup_staff_roles.py` (`manage.py setup_staff_roles [--fix] [--grant-admin-assignments]`); constants in `students/access.py` | L2 |
| Subject / grade vocabulary; report assignment subjects not in it | `django_core/schools/vocabulary.py` (re-exported by `students/models.py`); `manage.py check_assignment_subjects [--json]` (read-only) | L3 if a value changes (data migration) |
| Grade Lead assignments (model, admin, year picker) | `django_core/schools/models.py` (`GradeLeadAssignment`), `schools/admin.py`; access reading it is C5a, NOT YET IMPLEMENTED | L3 |
| Settings / secrets / ports | `config/settings/`, `docker-compose.yml`, FastAPI `auth.py` | never print secrets (S-03) |
| Tests | `django_core/{students,dashboard}/tests.py`, `fastapi_core/tests/test_security.py`; commands in `docs/TESTING.md` | |
| Reports | NOT YET IMPLEMENTED | |

Answer format for new questions: Feature / Primary module / Backend / Frontend / Database / Configuration / Tests / Related docs / Recommended starting point.
