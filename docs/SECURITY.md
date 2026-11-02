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
| S-11 | Pickle model files committed | MEDIUM | PARTIAL: since 2026-11-01 (`changes/0029`) the `.pth` is loaded with `torch.load(..., weights_only=True)` (tensors only, verified on the real file); `scaler.joblib` is still a pickle (repository-controlled file; JSON replacement proposed for P7). NOTE 2026-10-13: three artifacts are still tracked in the index (`fastapi_core/models/scaler.joblib`, `fastapi_core/models/student_risk_model.pth`, `fastapi_core/student_model.joblib`); see the deferred decision below |

## Critical Security Containment (Phase 1)
Minimal changes, ahead of everything else: (A) authenticate + role-gate Django views and FastAPI routes, (B) block public exposure of FastAPI and data-store ports, (C) remove default secrets / require env config, (D) rotate any exposed secret (never rewrite history). Each is an L3 change needing approval.

## Security Baseline Exit Criteria (Phase 3)
Authorization matrix implemented and tested · object/school scoping on every student-data endpoint · service-to-service auth · secrets from env only, rotated · audit log for student-data access and exports · upload validation (size, type, scan policy) · production settings hardened · dependency audit · permission tests green in CI.
Dependency audit status: done 2026-11-01 (`changes/0029-dependency-audit-REPORT.md`): Django-side and FastAPI web-stack advisories fixed by upgrades; **CURRENT RISK — NOT YET FIXED:** the FastAPI ML/RAG stack (torch, transformers, langchain, chromadb) keeps known advisories until its P7 replacement; the FastAPI service stays on loopback only.
Django admin status: closed 2026-11-01 (C-A, S9): `admin.site.has_permission` = superuser or PlatformAdmin; school-data models unregistered; user list excludes school-only accounts; staff + school role refused (`schools/test_admin_closure.py`, mutation-checked).
Production settings status: hardened 2026-11-01 (C-H; `DEPLOYMENT.md` §3/§3a): secure cookies, HTTPS redirect behind a TLS proxy, staged HSTS, nosniff/DENY/same-origin, console-only logging, `check --deploy --fail-level WARNING` as release gate with project checks eip.E001-E005 (hosts, https origins, proxy header, no external assets, DB password). Real host/certificate values: at deployment.

## Required review topics for every significant change
AuthN · AuthZ · object-level access · school isolation · SQL injection · XSS · CSRF · SSRF · file upload · secret leakage · PII exposure · prompt injection · unauthorized RAG retrieval · unsafe exports · audit logging · dependency vulnerabilities.

## Counseling data
Separate, strictest tier: strict ACL, audit, retention rules, consent where applicable, no AI exposure without approved policy (`AI_GOVERNANCE.md`).


### Counselor notes (owner decision 2026-10-26)
The **Grade Lead MAY read the counselor's notes of students in the own grade** (the Grade Lead is the main implementer of the counselor's advice at school). Decided by the owner on 2026-10-26 (earlier correction A3); do not restrict. What the code does, pinned by `dashboard/test_lead_counselor_notes.py`: **read only** (the only write route is the counselor-only case page); scope is the Grade Lead's enrollment-based grade in the own school (another grade or another school: 404); notes exist only through a referral (no referral, no note); **a closed referral keeps its notes readable for the Grade Lead** (the Counselor loses access; since 2026-10-28 the SchoolAdmin keeps **metadata only** - that notes exist and their dates - and no text, `counselor_note_metadata`); a read is audit-logged at page level (`view_student_360` / `view_counselor_case`) AND, only when note text is actually displayed, by `counselor_note_view` (detail `n<count>`, ids and counts only, never text; written for the Counselor case page, the Grade Lead and the SchoolAdmin; 2026-10-27, closes the former audit gap). Readers of the TEXT: Counselor (open referral), Grade Lead (own grade, read only, also after close), SchoolAdmin (own school, only while the referral is open). Not: Teacher, Parent, Student.
**Deliberate asymmetry:** the Grade Lead reads counselor *notes*, but sees only metadata for `emotional` / `family` alert messages and review notes and for the text of `emotional` intervention plans (decided earlier, change 0022/0023). Whether to align the two is an open question for the owner. Future idea (not now): the counselor marks each note "counselor only" or "shared with the grade lead".

## Authorization Matrix
Normative once approved. Legend: **CURRENT** = verified behavior; **TARGET** = intended; `DECISION REQUIRED` = owner must decide. Scope values: own / own children / own classes / school / none.

| Capability | Admin | Manager | Teacher | Mentor | Counselor | Parent | Student |
|---|---|---|---|---|---|---|---|
| View student profile | DECISION REQUIRED | DECISION REQUIRED | own classes (TARGET); **CURRENT: all students** | DECISION REQUIRED | DECISION REQUIRED | own children (TARGET); **CURRENT: all students** | own (TARGET) |
| Create/edit student | DECISION REQUIRED | DECISION REQUIRED | none (TARGET); **CURRENT: any authenticated user can create** | none (TARGET) | none (TARGET) | none | none |
| Attendance entry | DECISION REQUIRED | DECISION REQUIRED | own classes (TARGET) | DECISION REQUIRED | DECISION REQUIRED | none | none |
| Grades entry/view | DECISION REQUIRED | DECISION REQUIRED | own classes (TARGET) | DECISION REQUIRED | DECISION REQUIRED | own children view (TARGET) | own view (TARGET) |
| Student 360 view | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED |
| Risk/alert view | see the intervention-loop table below (CURRENT) | — | see below | — | see below | none (CURRENT) | none (CURRENT) |
| Intervention manage | see the intervention-loop table below (CURRENT) | — | none (CURRENT) | — | see below | none (CURRENT) | none (CURRENT) |
| Counseling records | none (TARGET) | DECISION REQUIRED | none (TARGET) | none (TARGET) | owner of record (TARGET) | none | none |
| Upload/delete RAG documents | DECISION REQUIRED | DECISION REQUIRED | none (TARGET); **CURRENT: any authenticated** | none | none | none | none |
| Staff AI assistant | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | DECISION REQUIRED | none | none |
| Study assistant | none | none | none | none | none | none | restricted (TARGET) |
| Data export | DECISION REQUIRED | DECISION REQUIRED | none (TARGET) | none | none | none | none |
| User/role admin | DECISION REQUIRED | none (TARGET) | none | none | none | none | none |

CURRENT role mechanism: `NOT VERIFIED` beyond Django groups/permissions (S-04); roles Mentor/Counselor/Manager do not exist in code as far as verified (`NOT VERIFIED`). ADR-0003 decides the model.

### Intervention loop — alerts, plans, follow-ups (CURRENT since change 0022, owner decisions 2026-10-26)
Roles use the real groups (the generic matrix above predates them). Base module: no entitlement is required, school scope always applies. Out of scope = 404, wrong role = 403, no role (Parent, Student, superuser) = nothing. Synthetic data only until the P3 exit.

| Capability | SchoolAdmin (own schools) | Grade Lead (own grade, enrollment-based) | Counselor (OPEN referral only) | Subject Teacher |
|---|---|---|---|---|
| Raise an alert | yes | yes | yes | yes, own classes only |
| Alert metadata (type, severity, status, dates, dismiss reason code, who raised / reviewed) | yes | yes | yes | own alerts |
| **Message of an `emotional` or `family` alert** | **no direct read** (unless they raised it); reachable only through a Counselor account, see "Accepted insider-trust risk" below | **only if they raised it** | **yes (open referral)** | own alerts |
| Message of other alerts | yes | yes | yes | own alerts |
| Reviewer's note (any alert; for those two types the message gate applies first) | yes | yes | yes | **never** |
| See alerts | all of the school | own grade | referred students | only the ones they raised |
| Accept / dismiss (`other` needs a note) | yes | yes | yes | no |
| Reopen a dismissed alert | yes | no | no | no |
| Create a plan | yes (cannot create or own an `emotional` plan) | yes | yes | no |
| See plan metadata (existence, type, status, dates, owner, outcome code) | all | own grade | referred students | no |
| **Text of an `emotional` plan and its follow-ups** | **no direct read**; same accepted insider path | **only as the plan owner** | **yes (open referral)**; as owner | no |
| Text of other plan types | yes | yes | yes | no |
| Follow-up, start, complete with outcome | non-emotional plans | own plans | own plans | no |
| Cancel / reassign (reassign an `emotional` plan only to a Counselor or Grade Lead who sees the student) | yes | own plans | own plans | no |

**Accepted insider-trust risk (owner decision 2026-10-28, from the independent review 0027 finding 1; evidence: `dashboard/test_sensitive_role_path.py`).** The SchoolAdmin has no direct read of that text, but the SchoolAdmin creates and resets Counselor accounts (`/school/counselors/`, `/school/resets/`), grants the Counselor role (`/school/staff-roles/`) and refers students to a Counselor. A SchoolAdmin can therefore log in as a Counselor they control and read the text. This is accepted and compensated by audit, not prevented: each step is logged with ids and codes only (`staff_account_create`, `staff_roles_change`, `password_reset`, `referral_create`, and every display of the text as `alert_text_view` / `intervention_view` by the Counselor account). A Grade Lead can NEVER reset the password of a Counselor or a SchoolAdmin (test). Residual risk and a possible later hardening (a second school-level actor for sensitive role changes and Counselor resets) are recorded in `PROJECT_CHECKLIST.md`.

**API tokens and password changes (2026-10-28, review 0027 finding 2).** JWTs are bound to a hash of the account's password (`SIMPLE_JWT['CHECK_REVOKE_TOKEN']`, `config/settings/base.py`): after an admin or Grade Lead reset, a forced change or a user change, tokens issued earlier (access and refresh) no longer authenticate. Tested in `students/test_token_revocation.py`. A removed role or a deactivated account is already checked per request (`is_active`, role lookups); tokens carry no role claim.

**National id masking (2026-11-02, decisions 39 and 44).** Pages and the REST list (`/api/students/`) show `******` plus the last four digits; the full value leaves only through the audited reveal (`POST students/<pk>/national-id/`) or the API detail read (`GET /api/students/<id>/`), both writing `national_id_reveal` (API: detail `api`). Writes by the SchoolAdmin return the full id of the row just written. Search by id still matches inside the user's own scope (no audit). Review L-1 closed.

**National id refusal (2026-10-28, finding 3).** A taken national id is refused with one fixed message in the form, the API and the import report, identical for the same school and another school and naming no school. The refusal itself still shows that the id exists somewhere (global uniqueness until S7).

Rules: SchoolAdmin and Grade Lead can accept or dismiss a sensitive alert on its metadata alone (`other` still needs a note, which the reviewer writes without reading the message). Every display of a sensitive alert's message is audit-logged (`alert_text_view`, detail = risk type; no text). Every read of a plan page is audit-logged (`intervention_view`, detail `text` or `meta`); audit rows hold ids and codes only. Closing a referral ends the Counselor's access at once. No export, no parent or student view, no AI. Alerts and plans protect their student (`PROTECT`): students are deactivated, never deleted (the API answers 409). Retention: no period decided, no automatic deletion; risk events 3 years per doc 12 is not enforced. `Referral` and `CounselorNote` still use `CASCADE` (open item).

### Demo track P5 (CURRENT since 2026-11-02; decision pack 0028 P5-1..P5-4, owner approval 2026-11-01)
| Feature | SchoolAdmin | Grade Lead | Subject Teacher | Counselor | Parent | Student |
|---|---|---|---|---|---|---|
| Principal dashboard `/dashboard/` (aggregates of ONE school among the memberships; rates of groups under 5 withheld; attention list audit-logged as `list_view attention`) | yes | redirected home | redirected home | redirected home | redirected home | redirected home |
| Support level (derived from `reviewable_alerts` + `visible_plans`, never stored) on the student list and Student 360 | yes | yes (own grade) | no | — (no list/360) | no | no |
| Behavior log: record (`behavior_writable_students`, audit `behavior_note_create`) | own schools | own grade | own classes | no | no | no |
| Behavior log: read (`visible_behavior_notes`) | all entries | all entries | own entries only | no | **positive entries of own children only** | no |
| Report card `/students/<pk>/report-card/` (full tier, audit `report_card_view`) | yes | own grade | no | no | own children | no |
Tests: `dashboard/test_principal.py`, `test_behavior.py`, `test_report_card.py`; mutation-checked: support-level gate, parent positive-only filter, teacher own-entries filter.

## Deterministic rules and the system read path (CURRENT since change 0025, owner approval 2026-10-27)
* **Who:** rules are authored, simulated, approved, paused, archived and run by the **SchoolAdmin of the school only** (`risk/lifecycle.py` re-checks `school_ids_for_admin` on every move; the pages `/rules/` use `role_required(ADMIN)` and the membership-derived school). Grade Lead, Teacher, Counselor, Parent, Student, superuser and PlatformAdmin have no rules page (403). They see only the **alerts** a rule raised (normal `visible_alerts`; evidence numbers are in the alert text for the review scope: SchoolAdmin, Grade Lead, Counselor via an open referral; a Teacher never sees rule alerts because `raised_by` is empty).
* **Rule content:** a rule is data (clauses over a closed metric catalog, `risk/signals.py`); nothing is evaluated from text. Risk types: academic, attendance, behavioral only, refused in validation AND by a database CHECK (`rule_risk_type_not_sensitive`). No composite score or level. Seeded rules are drafts, labelled "first proposal, not validated"; activation is a human step; `low_average` cannot be saved or activated while the school has no grade scale (fail closed).
* **System read path** (`students/access.py`: `system_scope_students/attendance/grades/enrollments`): the only code that reads student data without a user. One explicit integer school id (never "all", `ValueError` otherwise); only students with a current enrollment in that school; read-only querysets; imported only by `risk/rules.py` (guard test `risk/test_rules_core.py::test_only_the_rules_module_imports_the_system_path`). The runner writes only alerts, risk events, rule hits, run rows and audit rows (tested).
* **Triggering:** command `run_rules --school CODE` (refuses without `--school` once several schools exist) and the SchoolAdmin "run now" button (school from membership, request parameters ignored). No scheduler. Audit: `rule_run` (counts only; actor `system` for the command, the user for the button), `alert_raise` (rule code), `rule_create|edit|status|simulate|settings`.
* **Safety valves:** circuit breaker (default 15% of evaluated students per rule per run, per-school setting): above it NO alert is raised for that rule, the `RuleRun` row says `breaker_tripped` and the SchoolAdmin sees it; cooldown 14 days and no re-fire while an earlier alert is new or accepted with a planned/active plan; one transaction per student; unique hit per (rule, student, day) so two simultaneous runs cannot duplicate an alert (real PostgreSQL race test).
* **Aggregates:** simulation and rule-quality pages show counts only; any group under 5 is withheld; no per-student lists.
* **Retention** of hits and runs: PENDING POLICY (same as alerts).

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


## FastAPI and `/llm/complete/` exposure (owner decision 2026-11-02)
FastAPI (including the AI route `/llm/complete/`) is reachable ONLY over the internal Docker network (`http://fastapi:8001`, called by Django with the signed service token). **No port is published** for it in `docker-compose.yml` (the earlier loopback mapping `127.0.0.1:8001` was removed), the nginx example has no rule to it, and every route requires the token (`verify_jwt`; the AI route additionally needs the SchoolAdmin role and one school in the token). Checks that fail the build: `fastapi_core/tests/test_exposure.py` (a published port, host networking, or any reference to 8001/fastapi/`/llm` under `deploy/`), `test_every_non_public_route_requires_authentication` and `LLMRouteTests` (token removed or role relaxed). `CURRENT` for the repository files; `NOT VERIFIED` on a running server (check with `ss -ltnp` and an external port scan after deployment; owner/ops task). For local debugging use `docker compose exec fastapi ...`, not a published port.

## R-04 status (P9, 2026-11-02)
The application no longer needs a PostgreSQL superuser: `school_app` (DML only) at runtime, `school_owner` for migrations, `school_admin` for maintenance (`DEPLOYMENT.md` 4a, decision 65). `CURRENT` in the repository and rehearsed in throw-away containers (`scripts/test_db_roles.sh`, CI job `dbroles`); `NOT VERIFIED` on a real server (nothing is deployed). Residual: Redis without authentication (internal network only); the bootstrap superuser exists and must have its own strong password; `school_app` can read every table of the installation (school isolation is enforced in the application, not by row-level security).
