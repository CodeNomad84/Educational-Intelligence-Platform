# TRACEABILITY (Phase 2, lightweight)

Created 2026-10-13 (Phase 2.0). Maps Phase 2 intent to its source, the sub-phase that delivers it, and the tests that prove it.

**IDs are provisional.** `P2-REQ-nn` is a working identifier derived by Claude Code from repository documents and the owner's 2026-10-13 approvals. These are **not** the owner's REQ IDs (`REQUIREMENTS.md` is still a skeleton). The `Owner REQ-ID` column stays empty until the owner imports requirements; mapping then is a one-time edit of this file.

Labels per `CLAUDE.md` §2. `Test` is filled when the test exists; a row without a test is not delivered.

## Convention
- A test that proves a requirement carries `REQ: P2-REQ-nn` in its docstring. Coverage check: `grep -rn "P2-REQ-" django_core --include=tests.py`.
- A change that adds, drops or reinterprets a row updates this file in the same commit.
- Sub-phases refer to `ROADMAP.md` (2.1 … 2.5).

## Requirements
| ID | Requirement | Source | Label | Phase | Test | Owner REQ-ID |
|---|---|---|---|---|---|---|
| P2-REQ-01 | SchoolAdmin (group formerly `Admin`) sees all students; a parent sees only own children; no recognised role means no access | `SECURITY.md` interim access policy; `students/access.py` | CURRENT | built (P1) | existing `students`/`dashboard` tests; per-test mapping due in 2.1 | |
| P2-REQ-02 | A teacher sees only students of classes assigned to them, on every list, detail and API path | `SECURITY.md` matrix (“own classes”); ADR-0003 option (c) | CURRENT for read (C5a; Subject Teacher via active class + own subject, Grade Lead via school/grade/linked-class year) | 2.1 (C5a) | `students/test_access_c5a.py` | |
| P2-REQ-03 | A teacher cannot create or edit students | `SECURITY.md` matrix and interim policy | CURRENT (deny) | built (P1); re-proved in 2.1 | existing tests | |
| P2-REQ-04 | Teacher-to-class assignments are maintained by an administrator in the admin UI | Owner approval 2026-10-13; ADR-0003 §6 (admin staff with explicit permissions) | ACCEPTED | 2.1 | | |
| P2-REQ-05 | A `School` entity exists and school-owned data can be scoped to it; no school name, threshold or branding hard-coded in core | ADR-0004 (ACCEPTED); `CLAUDE.md` §3, §7 | ACCEPTED | 2.1 | | |
| P2-REQ-06 | A teacher can view a Student 360 page (attendance, grades, trends) for students in own classes | `SECURITY.md` matrix (grades "own classes"); ADR-0003 matrix | ACCEPTED (ADR-0003) | 2.2 | | |
| P2-REQ-07 | Risk detection is deterministic and rule-based before any ML; thresholds and weights are configuration, not code constants tied to one school | `ARCHITECTURE.md` decision 6; `CLAUDE.md` §3; `CUSTOMIZATION.md` | TARGET | 2.3 | | |
| P2-REQ-08 | Risk lives in its own domain (separate app), not inside `students` | Owner approval 2026-10-13 | ACCEPTED | 2.3 | | |
| P2-REQ-09 | Every risk result is explainable and carries provenance (rules fired, rule/config version, input window) | `CLAUDE.md` §8 (derived data carries provenance); `REQUIREMENTS.md` flow | TARGET | 2.3 | | |
| P2-REQ-10 | An alert never triggers an action by itself; a human reviews it (acknowledge/dismiss with note) | `CLAUDE.md` §1, §8; `REQUIREMENTS.md` flow | TARGET | 2.4 | | |
| P2-REQ-11 | A teacher sees risk indicators for assigned students and may acknowledge alerts and add notes; parents and students see none; final intervention ownership belongs to a future Counselor role | ADR-0003 matrix (owner decision 2026-10-13); `SECURITY.md` (parent/student "none (TARGET)") | ACCEPTED (intervention details DECISION REQUIRED, future) | 2.3 – 2.4 | | |
| P2-REQ-12 | Review actions and student-data access are recorded in an audit trail (minimal in Phase 2) | `SECURITY.md` S-05 (NOT FIXED) and baseline exit criteria | TARGET | 2.4 | | |
| P2-REQ-13 | Only synthetic data is used in any environment | `SECURITY.md` interim rule; `CLAUDE.md` §7 | CURRENT rule | all; seed guard in 2.5 | | |
| P2-REQ-14 | Phase 2 has no RAG, LLM or FastAPI dependency; Django-first | Owner approval 2026-10-13; `AI_GOVERNANCE.md` | CONSTRAINT | all | review per change | |
| P2-REQ-15 | User-facing pages are Persian/RTL on the existing Django templates | `CLAUDE.md` §1; `ARCHITECTURE.md` decision 4 (React is TARGET, incremental) | CURRENT (partial) | 2.2 – 2.4 | | |
| P2-REQ-16 | A teacher never receives `national_id`, phone, parents' jobs or `parent_user` (HTML or API) and cannot search/filter by them | ADR-0003 §5 (owner decision 2026-10-13); `CLAUDE.md` §7 (PII) | CURRENT (limited serializer tier; search/ordering cannot probe; Grade Lead sees `national_id` in own grades, synthetic data only until 2.4) | 2.1 (C5a) | `students/test_access_c5a.py` (API and HTML) | |
| P2-REQ-17 | `auth.*` permissions stay superuser-only; Teacher users are never staff and the Teacher group has no model permissions | ADR-0003 §6 | ACCEPTED | 2.1 (C4) | | |
| P2-REQ-18 | `school_class` is the source of truth; `class_name` is a deprecated mirror; import and forms resolve existing active classes only and never auto-create | ADR-0004 §4–6 | ACCEPTED | 2.1 (C2, C3) | | |
| P2-REQ-19 | The migrated data never grants access by itself: no assignments are created, near-duplicate class names are reported not merged | Design review 2026-10-13 §2; fail-closed principle | ACCEPTED | 2.1 (C3) | | |
| P2-REQ-20 | `TEACHER_ACCESS_REVIEW.md` exists and is reviewed before the teacher access change (C5) ships | Owner instruction 2026-10-13 | ACCEPTED | before C5 | | |
| P2-REQ-21 | `TeacherAssignment.subject` uses the same fixed vocabulary as `Grade.subject`; a blank subject is rejected for new assignments; legacy values are converted only on exact match | ADR-0005 §3; ADR-0004 amendments | CURRENT (model + `check_assignment_subjects`; not yet used for access) | 2.1 (C4b; enforcement C5a) | `schools/test_c4b.py` | |
| P2-REQ-22 | A Grade Lead is assigned to (school, grade, academic year) only by an Admin in the admin site; the assignment grants no access until C5a | ADR-0005 §2 | CURRENT (model + admin + guard test) | 2.1 (C4b; access C5a) | `schools/test_c4b.py` | |
| P2-REQ-23 | Student history is kept across school years: academic years per school, enrollments (class and grade in that year), year-attributed grades/attendance; nothing is guessed in a backfill | ADR-0011; `changes/0003-…` | 2.2a-1 and backfill command CURRENT (schema, reports, evidence-only `backfill_enrollments`, synthetic seed); year-aware historical import (`import_history`, batches, revert) CURRENT; access switch (2.2a-4, parity-gated) PROPOSED (`changes/0005-…`) | 2.2a | `schools/test_academic_years.py`, `students/test_enrollment_schema.py` | |
| P2-REQ-24 | Past-year free-text notes/recommendations are SchoolAdmin only until the 2.4 audit log exists; no Recommendation model and no real data until retention is decided | ADR-0011 owner decisions 2026-10-16 | ACCEPTED (policy); model DEFERRED | 2.2a/2.2c | | |

## Open decisions that gate rows
| Decision | Gates | Source |
|---|---|---|
| ~~ADR-0003 / ADR-0004 acceptance~~ — ACCEPTED 2026-10-13 | P2-REQ-02, 04, 05, 06, 11 | `adr/0003-…`, `adr/0004-…` |
| Intervention ownership details (Counselor role, what a teacher may propose) | future interventions phase | ADR-0003 matrix |
| Grading scale (0–20 vs 0–100) and attendance vocabulary | P2-REQ-07 thresholds | Stage 0 D-07, D-08; `REQUIREMENTS.md` checklist |
| Calibration of rule thresholds with the school (current values are demo assumptions) | P2-REQ-07 for non-demo use | `django_core/demo_intel/rules.py` |
| Import of owner requirements and REQ IDs | `Owner REQ-ID` column | `REQUIREMENTS.md` |
