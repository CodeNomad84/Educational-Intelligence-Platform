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
| P2-REQ-01 | Admin sees all students; a parent sees only own children; no recognised role means no access | `SECURITY.md` interim access policy; `students/access.py` | CURRENT | built (P1) | existing `students`/`dashboard` tests; per-test mapping due in 2.1 | |
| P2-REQ-02 | A teacher sees only students of classes assigned to them, on every list, detail and API path | `SECURITY.md` matrix ("own classes"); ADR-0003 option (c) | TARGET — ADR-0003 DECISION REQUIRED | 2.1 | | |
| P2-REQ-03 | A teacher cannot create or edit students | `SECURITY.md` matrix and interim policy | CURRENT (deny) | built (P1); re-proved in 2.1 | existing tests | |
| P2-REQ-04 | Teacher-to-class assignments are maintained by an administrator in the admin UI | Owner approval 2026-10-13 | PROPOSED (L3 proposal 2.1) | 2.1 | | |
| P2-REQ-05 | A `School` entity exists and school-owned data can be scoped to it; no school name, threshold or branding hard-coded in core | ADR-0004 (PROPOSED); `CLAUDE.md` §3, §7; owner approval 2026-10-13 | PROPOSED | 2.1 | | |
| P2-REQ-06 | A teacher can view a Student 360 page (attendance, grades, trends) for students in own classes | `SECURITY.md` matrix (grades "own classes"; Student 360 cell DECISION REQUIRED) | TARGET — cell DECISION REQUIRED | 2.2 | | |
| P2-REQ-07 | Risk detection is deterministic and rule-based before any ML; thresholds and weights are configuration, not code constants tied to one school | `ARCHITECTURE.md` decision 6; `CLAUDE.md` §3; `CUSTOMIZATION.md` | TARGET | 2.3 | | |
| P2-REQ-08 | Risk lives in its own domain (separate app), not inside `students` | Owner approval 2026-10-13 | PROPOSED | 2.3 | | |
| P2-REQ-09 | Every risk result is explainable and carries provenance (rules fired, rule/config version, input window) | `CLAUDE.md` §8 (derived data carries provenance); `REQUIREMENTS.md` flow | TARGET | 2.3 | | |
| P2-REQ-10 | An alert never triggers an action by itself; a human reviews it (acknowledge/dismiss with note) | `CLAUDE.md` §1, §8; `REQUIREMENTS.md` flow | TARGET | 2.4 | | |
| P2-REQ-11 | Who may see or review risk/alerts (teacher cell) is explicit; parents and students see none | `SECURITY.md` matrix (parent/student "none (TARGET)"; teacher DECISION REQUIRED) | DECISION REQUIRED | 2.4 | | |
| P2-REQ-12 | Review actions and student-data access are recorded in an audit trail (minimal in Phase 2) | `SECURITY.md` S-05 (NOT FIXED) and baseline exit criteria | TARGET | 2.4 | | |
| P2-REQ-13 | Only synthetic data is used in any environment | `SECURITY.md` interim rule; `CLAUDE.md` §7 | CURRENT rule | all; seed guard in 2.5 | | |
| P2-REQ-14 | Phase 2 has no RAG, LLM or FastAPI dependency; Django-first | Owner approval 2026-10-13; `AI_GOVERNANCE.md` | CONSTRAINT | all | review per change | |
| P2-REQ-15 | User-facing pages are Persian/RTL on the existing Django templates | `CLAUDE.md` §1; `ARCHITECTURE.md` decision 4 (React is TARGET, incremental) | CURRENT (partial) | 2.2 – 2.4 | | |

## Open decisions that gate rows
| Decision | Gates | Source |
|---|---|---|
| ADR-0003 accepted with Teacher/Admin matrix cells filled | P2-REQ-02, 06, 11 | `adr/0003-authorization-model.md` |
| ADR-0004 accepted (School key now) | P2-REQ-05 | `adr/0004-school-scoping-tenant-key.md` |
| Grading scale (0–20 vs 0–100) and attendance vocabulary | P2-REQ-07 thresholds | Stage 0 D-07, D-08; `REQUIREMENTS.md` checklist |
| Calibration of rule thresholds with the school (current values are demo assumptions) | P2-REQ-07 for non-demo use | `django_core/demo_intel/rules.py` |
| Whether a Counselor role exists in Phase 2 | P2-REQ-11 | `SECURITY.md` matrix |
| Import of owner requirements and REQ IDs | `Owner REQ-ID` column | `REQUIREMENTS.md` |
