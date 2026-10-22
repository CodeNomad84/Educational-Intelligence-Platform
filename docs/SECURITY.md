# SECURITY

Platform handles minors' data. Principles: privacy by design, least privilege, RBAC + object-level + school scope, audit logging, controlled exports, safe uploads, controlled counseling/audio data, careful external-LLM use.

## Interim rule
**NO REAL STUDENT DATA in any environment** until the Security Baseline Exit Criteria below are met. Synthetic data only. School policy documents (non-personal) may enter RAG after Critical Security Containment item B (Phase 1). `DECISION REQUIRED`: confirm no real student data is in any deployed/shared environment today.

## Phase 1 containment status (VERIFIED AT branch `phase-1/boot-security`; sandbox limits in `changes/0001-phase1-boot-security-PROPOSAL.md`)
| ID | Status after Phase 1 |
|---|---|
| S-01 | **CONTAINED (interim)**: dashboard views are role-gated and parent access is scoped to `Student.parent_user` server-side; tested (parent→own child allow, other child 404, no-role 403, anonymous redirect). Teacher student access is now DENIED by default until a teacher-to-student assignment model exists (S-04). Final model = ADR-0003 (DECISION REQUIRED). |
| S-02 | **CONTAINED (interim)**: every FastAPI data route requires a Django-issued service token with a role; chat, document ingestion and search are disabled for every role; document list/delete and predict are Admin-only; startup refuses a missing/weak `SERVICE_JWT_SECRET`; FastAPI uses its own least-privilege DB role (`fastapi_user`, SELECT+DELETE on `documents`). Tested (TestClient + live container probes). RAG ACL/injection defense (A-04) is NOT addressed. |
| S-03 | PARTIAL: FastAPI default JWT secret removed (fails closed and refuses to start); Django `SECRET_KEY`, DB password and MinIO credentials rotated/non-default and kept in gitignored files. Pre-baseline pass: `config/settings/base.py` no longer has an insecure `SECRET_KEY` default (empty => Django refuses to start), `production.py` refuses to start on a missing/short/placeholder key (`DEBUG` fixed `False`), `development.py` uses a random per-process key, and the hard-coded dev key was removed from the shadowed `config/settings.py` (that key remains in the previous repository history, G-01: treat as burned). Other defaults/hard-coded values remain. Not production-safe by this change alone (see Phase 3 exit criteria). |
| S-06 | PARTIAL: PostgreSQL, Redis and MinIO are no longer published to the host; FastAPI (8001) and Ollama (11435) are loopback-only. Django 8000 is published on **loopback only** (`127.0.0.1:8000`, 2026-10-15; R-03 closed for the Dev/Demo-on-VM setting). Reachable from the VM itself or via SSH tunnel; any web-server deployment requires a reverse proxy with HTTPS (see `DEPLOYMENT.md`, DRAFT). |
| D-04 | FIXED in code: FastAPI no longer creates/drops schema. PostgreSQL path NOT VERIFIED. |
| all others | unchanged (see table below) |

### Interim access policy (Phase 1; replaces the CURRENT cells in the matrix where they differ)
Roles = Django groups `SchoolAdmin` (renamed from `Admin` by `students/0010`, ADR-0010; the migration is applied to a real database only by the owner after a backup), `Teacher`, `Parent`; superuser ⇒ SchoolAdmin; no recognised group ⇒ no access (`students/access.py`).
| Capability | SchoolAdmin (was Admin) | Teacher | Parent | no role / anonymous |
|---|---|---|---|---|
| Dashboard aggregates, library (view) | allow (**S3: aggregates cover the membership schools only; the library is NOT school-scoped yet, CURRENT RISK, see Report 0017**) | deny | deny (redirect to own children) | deny / login |
| Chat (RAG) | disabled for every role in Phase 1 | disabled | disabled | disabled |
| Student list & detail | **S3 (2026-10-23): the students of the schools of the user's ACTIVE memberships (`school_ids_for_admin`); none without a valid membership; a superuser reads every school until S8** | **C5a:** Subject Teacher = students of own active assigned classes, limited fields (no `national_id`, phone, parents' jobs, `parent_user`), own-subject grades only, no attendance; **Grade Lead** = students of the assigned school/grade whose linked class is active and of the assignment's academic year (unlinked students invisible), full fields incl. `national_id`, all subjects, attendance; multi-role = union with per-row tier (non-widening) | own children only | deny / login |
| Create student, delete RAG documents, student file upload | allow | deny | deny | deny / login |
| RAG document upload / search | disabled for every role in Phase 1 | disabled | disabled | disabled |
| AI prediction (dashboard and FastAPI `/predict/`) | allow | deny (S-04; also for Grade Lead and Subject Teacher) | deny | deny |

Scope: Phase 1 is a **single-school prototype with no multi-tenant isolation** (see `DATA_AND_ARTIFACTS.md`).
Matrix cells above are interim containment, not approved policy: DECISION REQUIRED (ADR-0003).

## CURRENT RISK — NOT YET FIXED (details in `audit/STAGE0_BASELINE.md`; this table keeps the Stage 0 baseline wording; current status per row is in the right-hand column and in the Phase 1 table above)
| ID | Risk (Stage 0 baseline) | Severity | Status after Phase 1 (verified 2026-10-12) |
|---|---|---|---|
| S-01 | Dashboard views only `@login_required`: parents read all students; any user creates students, uploads/deletes docs, chats | CRITICAL | CONTAINED (interim) |
| S-02 | FastAPI routes unauthenticated, port 8001 published | CRITICAL | CONTAINED (interim); 8001 on loopback only |
| S-03 | Hard-coded/default secrets in code; no `.env.example` (values never reproduced) | HIGH | PARTIAL: service, MinIO and DB secrets are random and kept in gitignored files; other hard-coded values remain |
| C5a-R1 | **CURRENT RISK — NOT YET FIXED (owner 2026-10-16):** `Grade` has no academic year and no class, so a Subject Teacher sees own-subject grades of ALL years and of other teachers for students of the assigned class. Add year and class before grade entry or any real data. | MEDIUM | DEFERRED to Phase 2.2b | 
| C5a-R2 | **CURRENT RISK — minor, C6:** a Parent receives `parent_user` (and `national_id`) of their own child in HTML/API. | LOW | DEFERRED to C6 |
| C5a-R3 | **Informational:** the Django-issued FastAPI service token carries every recognised role incl. `GradeLead`/`Teacher`; FastAPI ignores them today (`require_roles(ADMIN)` only). Re-check when FastAPI gains a role-based route. | LOW | OPEN |
| C5a-R4 | **CURRENT RISK — minor:** `student_detail_view` still computes placeholder AI `input_data` (constants, Stage 0 A-02) for every role; only a SchoolAdmin triggers or sees a prediction. Remove or gate the computation when the AI wiring is reworked. | LOW | OPEN |
| 4c-R1 | **CURRENT (2026-10-16, 2.2a-4c):** Grade Lead / Subject Teacher scope now follows the CURRENT ENROLLMENT (`students/access.py`; the mirror fields no longer decide). Fail-closed by design: a student without a current enrollment, a school without a current academic year, or a Grade Lead assignment whose year does not resolve is invisible to non-admin staff, so a forgotten year rollover (`rollover_academic_year`) or a missing post-rollover assignment hides students until an admin acts. **The gate (`check_access_switch_ready` READY, `compare_access_parity` 0 differences) was proven on SYNTHETIC data only (234 and 4,938 students) and MUST be re-run on the real data before any real student data is loaded (P3 exit rule unchanged).** SchoolAdmin and Parent scopes are unchanged; the pre-switch rule remains in `students/access_legacy.py` for revert. | MEDIUM (availability, not disclosure) | MITIGATED by pre-flight/parity tools and rollover command; `--carry-assignments` NOT BUILT |
| S-04 | Teachers see all students; no class/school scoping | HIGH | **C5a (2026-10-16, implemented, tests green, manual security review recorded in ROADMAP/TESTING): teacher and grade-lead read access is scoped server-side by `visible_students`/`visible_grades`/`visible_attendances`; identity-field audit (2.4) still missing, so Grade Lead `national_id` is for synthetic data only.** Earlier text: **Teacher student access is denied by default** (list/detail/predict/dashboard/library); class/school scoping is still NOT IMPLEMENTED — DECISION REQUIRED |
| S-05 | No audit/access logging | HIGH | NOT FIXED |
| S-06 | Published ports: 5432, 6379 (no auth), 9000/9001, 11434, 8000, 8001 | HIGH | PARTIAL: 5432/6379/9000/9001 unpublished; 8001 and Ollama (11435) loopback; **8000 now loopback-only (2026-10-15)**; this is the Dev/Demo-on-VM setting, and a reverse proxy with HTTPS is required for any web-server deployment |
| S-07 | Debug/logging exposure, `str(e)` returned, default `/docs` | MEDIUM | PARTIAL: delete handlers return generic 500; other handlers still return `str(e)`; `/docs` is public |
| S-08 | FastAPI writes shared DB; `readonly` arg ignored | MEDIUM | PARTIAL: FastAPI now connects as least-privilege `fastapi_user` (SELECT, DELETE on `documents`; see `FASTAPI_DB_ROLE.md`); the `readonly` argument is still unused dead code |
| S-09 | Upload validation weak (FastAPI no size cap, extension only) | MEDIUM | MITIGATED: ingestion routes are disabled for every role; validation itself not changed |
| S-10 | No production hardening (SECURE_*, CSRF origins, CORS, static serving) | MEDIUM | NOT FIXED |
| S-11 | Pickle model files committed | MEDIUM | PARTIAL: they are still pickle-based and loaded with `torch.load`. NOTE 2026-10-13: three artifacts are still tracked in the index (`fastapi_core/models/scaler.joblib`, `fastapi_core/models/student_risk_model.pth`, `fastapi_core/student_model.joblib`); see the deferred decision below |

## Critical Security Containment (Phase 1)
Minimal changes, ahead of everything else: (A) authenticate + role-gate Django views and FastAPI routes, (B) block public exposure of FastAPI and data-store ports, (C) remove default secrets / require env config, (D) rotate any exposed secret (never rewrite history). Each is an L3 change needing approval.

## Security Baseline Exit Criteria (Phase 3)
Authorization matrix implemented and tested · object/school scoping on every student-data endpoint · service-to-service auth · secrets from env only, rotated · audit log for student-data access and exports · upload validation (size, type, scan policy) · production settings hardened · dependency audit · permission tests green in CI.

## Required review topics for every significant change
AuthN · AuthZ · object-level access · school isolation · SQL injection · XSS · CSRF · SSRF · file upload · secret leakage · PII exposure · prompt injection · unauthorized RAG retrieval · unsafe exports · audit logging · dependency vulnerabilities.

## Counseling data
Separate, strictest tier: strict ACL, audit, retention rules, consent where applicable, no AI exposure without approved policy (`AI_GOVERNANCE.md`).

## Authorization Matrix
Normative once approved. Legend: **CURRENT** = verified behavior; **TARGET** = intended; `DECISION REQUIRED` = owner must decide. Scope values: own / own children / own classes / school / none.

| Capability | Admin | Manager | Teacher | Mentor | Counselor | Parent | Student |
|---|---|---|---|---|---|---|---|
| View student profile | DECISION REQUIRED | DECISION REQUIRED | own classes (TARGET); **CURRENT: all students** | DECISION REQUIRED | DECISION REQUIRED | own children (TARGET); **CURRENT: all students** | own (TARGET) |
| Create/edit student | DECISION REQUIRED | DECISION REQUIRED | none (TARGET); **CURRENT: any authenticated user can create** | none (TARGET) | none (TARGET) | none | none |
| Attendance entry | DECISION REQUIRED | DECISION REQUIRED | own classes (TARGET) | DECISION REQUIRED | DECISION REQUIRED | none | none |
| Grades entry/view | DECISION REQUIRED | DECISION REQUIRED | own classes (TARGET) | DECISION REQUIRED | DECISION REQUIRED | own children view (TARGET) | own view (TARGET) |
| Student 360 view | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED |
| Risk/alert view | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | none (TARGET) | none (TARGET) |
| Intervention manage | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | none | none |
| Counseling records | none (TARGET) | DECISION REQUIRED | none (TARGET) | none (TARGET) | owner of record (TARGET) | none | none |
| Upload/delete RAG documents | DECISION REQUIRED | DECISION REQUIRED | none (TARGET); **CURRENT: any authenticated** | none | none | none | none |
| Staff AI assistant | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | none | none |
| Study assistant | none | none | none | none | none | none | restricted (TARGET) |
| Data export | DECISION REQUIRED | DECISION REQUIRED | none (TARGET) | none | none | none | none |
| User/role admin | DECISION REQUIRED | none (TARGET) | none | none | none | none | none |

CURRENT role mechanism: `NOT VERIFIED` beyond Django groups/permissions (S-04); roles Mentor/Counselor/Manager do not exist in code as far as verified (`NOT VERIFIED`). ADR-0003 decides the model.

## Deferred hardening and owner decisions (Phase 1, recorded 2026-10-12)
| Item | Status |
|---|---|
| `school_user` (Django, Celery, DB bootstrap) is a PostgreSQL **superuser** | Deferred by owner pending an explicit security decision. Compromise of Django means full database control. |
| Healthchecks and restart policies | None defined (only Ollama has `restart: unless-stopped`). Future hardening; not a security control. |
| Django published port 8000 | **RESOLVED 2026-10-15 (R-03, owner option 1):** `docker-compose.yml` binds `127.0.0.1:8000:8000`. This is the **Dev/Demo-on-VM** setting only; direct access from the host machine or LAN needs an SSH tunnel. Any web-server deployment requires a reverse proxy with HTTPS (see `DEPLOYMENT.md`, to be written). Previously: published on all interfaces, VMware mode not confirmed. |
| Redis has no authentication | Mitigated only by not publishing the port. |
| Torch | Stays `2.0.1+cu117`; CPU-wheel migration not approved. Image 8.26 GB; CUDA libraries unused. |
| Hard-coded school-specific address `noreply@school.com` in `students/tasks.py` (unused task) | Observation; violates the "no hard-coded school-specific values" rule; not changed. |
| S-11 tracked model binaries | **DEFERRED by owner 2026-10-13.** The three files above stay untouched and uncommitted: content identical to the index (hash-verified), working tree differs only by file mode (`100755` vs `100644`), deliberately not normalized. Untracking, replacing the pickle format or purging history is a later owner decision; rotation/untracking only, never a history rewrite without authorization. |
| Baseline commit | RESOLVED 2026-10-13: the Phase 1 work is committed (`3404a1a` … `4c096de`) on `phase-1/boot-security`; the repository history holds the baseline. |
