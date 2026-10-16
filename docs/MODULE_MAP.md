# MODULE MAP

Verified-at: `3404a1a` + Phase 1 branch `phase-1/boot-security`; the commit `3404a1a` is resolvable in this repository's history (verified 2026-10-13); Phase 1 closed at `4c096de`. Paths re-checked against the working tree on 2026-10-12. Status labels: CURRENT / NOT YET IMPLEMENTED. Code wins over this file.

## Django core — `django_core/`
| Module | Path | Purpose / contents | Tests |
|---|---|---|---|
| Service auth (Phase 1) | `config/service_auth.py` | mints the Django→FastAPI service token | `dashboard/tests.py` (ServiceTokenTests) |
| Access policy | `students/access.py` (roles, `visible_students` with `full_tier`, `visible_grades`, `visible_attendances`, `search_students`), `dashboard/decorators.py` (`role_required`) | single source of role + object-scope rules | `students/tests.py`, `dashboard/tests.py` |
| Settings/config | `config/` (`settings/{base,development,production}.py`, `urls.py`, `celery.py`, `wsgi.py`, `asgi.py`, plus `settings/demo.py` for DEMO SCOPE) | Project config. The former flat `config/settings.py` (shadowed, B-04) was removed in `48e8e1f` | none |
| School structure | `schools/` — `models.py` (School, SchoolClass incl. nullable `grade`, TeacherAssignment, GradeLeadAssignment, **AcademicYear**), `academic_years.py` (year normaliser, date lookup), `vocabulary.py` (subject/grade vocabularies shared with `students`), `admin.py`, `management/commands/{setup_staff_roles,check_assignment_subjects,check_academic_years}.py`, `migrations/0001–0003` | School key and assignments (none read by access code before C5a) | `schools/tests.py`, `schools/test_c4b.py`, `schools/test_setup_staff_roles.py` |
| Students | `students/` — `models.py` (Student, Grade, Attendance, **Enrollment, ImportBatch**; enrollment links unused by any read path yet, ADR-0011 2.2a-1), `enrollment_sync.py` (current-year enrollment kept in step; called explicitly), `access_legacy.py` (pre-switch rule, parity reference only), `access_enrollment.py` (enrollment rule, NOT active until 4c), `history_import.py` + `management/commands/{check_enrollment_backfill,backfill_enrollments,seed_temporal_synthetic,import_history,check_access_switch_ready,compare_access_parity}.py`, `views.py` (DRF `StudentViewSet`, import, features, predict), `serializers.py`, `permissions.py`, `tasks.py`, `migrations/0001–0006` | Operational student data & API at `/api/students/` | `tests.py` empty |
| Dashboard | `dashboard/` — `views.py`, `urls.py`, `forms.py`, `models.py` (Homework, TeacherParentCommunication; no migrations, undefined imports — B-02), `templates/dashboard/*.html` | Server-rendered UI (login, student list/detail/form, chat, library) | `tests.py` empty |

## AI layer — `fastapi_core/`
| Module | Path | Purpose |
|---|---|---|
| API | `main.py` | chat, documents CRUD/search, upload, predict; role-protected (Phase 1) |
| RAG | `rag_service.py` | embeddings/generation via Ollama; read-only table check, no DDL (Phase 1) |
| Auth | `auth.py` | service-token verification, `require_roles`, `disabled_in_phase1` (chat/ingestion/search), `validate_service_secret` (startup); tests in `fastapi_core/tests/` |
| Data pipeline / models | `data_pipeline.py`, `train_model.py`, `train_nn_model.py`, `models/`, `student_model.joblib` | prototype risk model (synthetic label — A-01) |
| Config | `config.py` | empty |

## Infrastructure
`docker-compose.yml` (8 services; env files `.env`, `.env.service`, `.env.fastapi`, `.env.minio` — see `DATA_AND_ARTIFACTS.md`; DB role runbook `FASTAPI_DB_ROLE.md`), `django_core/Dockerfile`, `fastapi_core/Dockerfile`.

## NOT YET IMPLEMENTED
Student 360 · Rule engine · Risk events · Alerts · Interventions · Observations/Behavior · Parents/Classes entities · Audit log · Ingestion pipeline · React frontend · tests/CI.

## Per-module template (use when a module is added)
Purpose · Responsibility · Main files · Models · Services · APIs · Frontend · Dependencies · Inputs · Outputs · Tests · Related docs.
