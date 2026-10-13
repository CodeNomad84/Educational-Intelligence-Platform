# CHANGE PROPOSAL — Phase 2.1: School, classes, teacher assignment, teacher object-level scoping
Level: **L3** (authorization, schema, tenancy key) · Status: **DRAFT — not approved; nothing implemented** · Date: 2026-10-13
Depends on: ADR-0003 and ADR-0004 marked ACCEPTED by the owner. Traceability: P2-REQ-02, 03, 04, 05 (`TRACEABILITY.md`).

## 1. Requirement
A teacher must see only the students of classes assigned to them (list, detail, API), assignments are maintained by an administrator in the admin UI, and a School key exists so a second school can be added without a retrofit. Source: owner approval 2026-10-13; `SECURITY.md` matrix and S-04; ADR-0003/0004 drafts.

## 2. Current behavior (CURRENT, evidence)
- `students/access.py`: Admin all, Parent `parent_user=user`, Teacher `Student.objects.none()`; no recognised role gives none.
- `students/views.py:38` (DRF `StudentViewSet.get_queryset`) and the dashboard views use `visible_students()`; 38 `students`/`dashboard` tests pass (`scripts/run_tests.sh`, 2026-10-13).
- No School/class/assignment model. `Student.class_name` is a free-text CharField (used by forms, `students/views.py` upload and filterset, admin, seed, `demo_intel`).
- Untracked scaffolds (`schools`, `risk`, `academics`, `accounts`, `core`) are not in `INSTALLED_APPS`. Inspected 2026-10-13: `schools.TeacherAssignment.teacher` → `accounts.User`; `academics.Attendance` uses `related_name="attendances"`, which collides with `students.Attendance`.

## 3. Desired behavior
- `School` (one default row), `SchoolClass` (school, title, academic year, optional grade level), `TeacherAssignment` (teacher user, class, optional subject).
- `Student.school_class` (nullable FK) and `Student.school` (nullable FK). `class_name` kept, deprecated.
- `visible_students()` Teacher branch: students whose class has an assignment for this user; union with Parent logic if the user holds both roles.
- Assignments managed in Django admin by authorized staff only; the assigned user must be in the `Teacher` group (validated).

## 4. Affected modules (`MODULE_MAP`)
`students` (models, migrations, admin, `access.py`, tests); `dashboard` (read paths only, no logic change expected). New app for School/class/assignment: **DECISION REQUIRED** whether it is a new tracked app `schools` (rewritten minimal; recommended, matches ADR-0004) or models inside `students`. Not touched: `demo_intel`, FastAPI, `accounts`, `academics`, `core`, `behavior`, `governance`, `interventions`.

## 5. Data impact
- New tables: School, SchoolClass, TeacherAssignment. New nullable columns on `students_student`.
- Migrations: (a) schema, (b) data migration creating the default School (name from a setting, not hard-coded) and one class per distinct non-empty `class_name`, assigning students; blank `class_name` stays unassigned (visible to Admin only), (c) later and separate: make `Student.school` required (not in 2.1).
- Reversible; no existing column dropped; `national_id` uniqueness unchanged (D-06 deferred).
- Provenance: assignment rows carry created/updated timestamps; who assigned is captured by the admin log.
- **PK type DECISION REQUIRED** (ADR-0004 §6; recommendation integer).
- The demo database (`demo_db.sqlite3`) needs `migrate` or a reseed afterwards; `demo_intel` keeps working through `class_name`.

## 6. API impact
`/api/students/` visibility changes for Teachers only (from empty to scoped). No schema or route change. `class_name` filter remains and cannot widen the scoped queryset.

## 7. Frontend impact
None required. Teachers reach the existing student list/detail templates; navigation gating in `base.html` is NOT VERIFIED and is checked in 2.1c. Student 360 is Phase 2.2.

## 8. AI impact
None. No RAG/LLM/FastAPI change; the FastAPI service-token `roles` claim and its Admin-only prediction route are unchanged.

## 9. Security impact
- AuthZ change (ADR-0003). Deny by default, 404 for non-visible objects, no existence leak.
- Review checklist: IDOR by pk, query-string filters/search/ordering, DRF detail routes, mutations (create/upload stay Admin only), parent+teacher dual role, assignment removal taking effect immediately, who may edit assignments (**DECISION REQUIRED**: superuser only vs Admin-group staff with explicit model permissions).
- PII: no new personal data. Audit logging (S-05) remains NOT FIXED; the minimal audit entry arrives in 2.4.
- Dashboard aggregates, library and AI prediction stay denied for Teachers (they would reveal other classes).

## 10. Testing strategy (each test docstring carries `REQ: P2-REQ-nn`)
Permission tests: assigned teacher sees only own classes in list/detail/API; other class → 404; unassigned teacher → none; two classes → union; assignment removed → access gone; teacher+parent union; filters/search cannot widen; anonymous/no-role unchanged; create/upload/predict/library/dashboard still denied for teacher; Admin and Parent unchanged. Migration tests: forward, idempotent, reverse, blank `class_name`. Admin tests: only authorized staff can add assignments; non-Teacher user rejected. A two-school fixture proves the school filter. Gate: `scripts/run_tests.sh` plus `makemigrations --check`.

## 11. Documentation impact
`SECURITY.md` matrix and S-04 (on acceptance), `MODULE_MAP`, `CHANGE_GUIDE` (bump `Verified-at`), `TRACEABILITY`, `TESTING`, ADR statuses.

## 12. Customization impact
Default school name and class naming come from settings/admin data; nothing school-specific in code.

## 13. Risks
Data migration on messy `class_name` text (spelling variants create duplicate classes; mitigated by an admin-reviewable report before enabling teacher access); breaking `demo_intel` (mitigated: `class_name` kept, demo tests run in the gate); `AUTH_USER_MODEL` swap must **not** happen (scaffold `accounts` is out of scope); future second school needs the `national_id` constraint change.

## 14. Recommendation
Approve after ADR-0003/0004 acceptance, in four small commits: 2.1a models + admin + migration (no behavior change); 2.1b data migration + report; 2.1c teacher scoping in `access.py` with tests; 2.1d docs. Alternatives: models inside `students` (smaller diff, weaker domain boundary); UUID keys (ERD alignment, higher cost).
**DECISION REQUIRED:** (1) ADR-0003/0004 acceptance and the two open cells; (2) PK type; (3) new `schools` app vs `students`; (4) who may edit assignments; (5) subject-level assignment now or later (proposal: optional field, class-level scoping only).
