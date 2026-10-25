# ROADMAP

> **Current status lives in `docs/PROJECT_CHECKLIST.md`** (start-to-finish list with evidence). This file keeps the phase definitions and history; where the two disagree, the checklist and git win. Since 2026-10-19 the product modules `mission` (slices 1-3) and `exams` (slice 1) were built on top of Phase 2.

Current phase: **Phase 2 — MVP productization (compressed roadmap approved by the owner 2026-10-13), Django-first.** Phase 1 is closed on `phase-1/boot-security` at `4c096de` (`PHASE1_FINAL_STATUS.md`, `PHASE1_DEFERRED_ITEMS.md`); baseline `3404a1a` is resolvable in this repository's history. Sub-phases 2.1, 2.1m (multi-school) and 2.2a are largely built; what is done and what is open is tracked item by item in `PROJECT_CHECKLIST.md`. Each phase starts only on owner approval.

**Phase 2 is Django-first**: no RAG/LLM, no React, no FastAPI changes. PostgreSQL and FastAPI verification: `TESTING.md` (Django 1174 tests on SQLite and PostgreSQL, FastAPI 28; 2026-10-25). CI: `.github/workflows/ci.yml` exists (Django only; not yet run on GitHub). Phase 2 absorbs the MVP slice of P2, P4, P5 and P6 below; their full scope remains in the table.

| Sub-phase | Content | Level | Status |
|---|---|---|---|
| 2.0 | Preparation: file-mode normalization, single Django test command, dead settings removal, doc reconciliation, lightweight traceability (`TRACEABILITY.md`), ADR-0003/0004 drafts, Phase 2.1 proposal | L1 + docs | DONE except the file-mode normalization of tracked model binaries, deferred by owner (S-11). Commits: `88c5cdd` test command, `48e8e1f` dead settings, `9f0b461`/`36075a8` doc reconciliation, `ff1b158` traceability, `c8add0e` ADR drafts + proposal, `1181c6b` script mode |
| 2.1 | `School`, `SchoolClass`, `TeacherAssignment`, Student→class relation, teacher object-level scoping, staff roles (Grade Lead, Subject Teacher, Counselor) | L3 | DONE (ADR-0003/0004/0005/0010; history in `changes/0002-…`, `TEACHER_ACCESS_REVIEW.md`; read access C5a `students/access.py`; open items `SECURITY.md` C5a-R1..R4) |
| 2.2a | Temporal data model (`Enrollment`, current-year access switch, history import, year rollover) | L3 | DONE (ADR-0011; `changes/0003-…`, `0005-…`, `0006-…`) |
| 2.1m | Multi-school hosting (ADR-0012, `changes/0010-…`): S1, S2, S2b, S3, S5, S6 DONE (reports `0011`..`0017`); S4 DONE (report `0019`); S7 (`national_id` per school; options in `0020`, owner decides), S8 (platform split), S9 (Django admin restricted), S10 (second-school gate) NOT STARTED | L3 | see `PROJECT_CHECKLIST.md` §1 |
| 2.2 | Staff Student 360 read view | L2 | Student 360 page built for SchoolAdmin, Grade Lead and Parent (`e5e4cfe`); same-year trend vs past years and provenance: not verified (`changes/0004-…`, `0007-…`); Parent staff-only (D-22-2), SchoolAdmin all sections (D-22-3) |
| 2.2b / 2.2c | Grade entry (own class + subject) / improvement recommendations | L3 / L2 | Teacher grade entry and recommendations built (`cdfeef5`); open: grades need academic year and class (`SECURITY.md` C5a-R1) |
| 2.6 | Counseling referral workflow (states submitted, counselor_declined, awaiting_parent_consent, parent_declined, active, closed), parental consent (no exception path, owner D5), Admin status view, Counselor role, separate sensitive records | L3 | Counselor role and referrals built (`ca0ea93`); the consent states and workflow are NOT STARTED; requires 2.4 audit log first and policy/legal review (D24); crisis/escalation path needs its own policy document first (D18) |
| 2.7 | Satisfaction feedback after closed referrals (family + counselor; Admin sees ratings/aggregates, minimum count 5, no free text) | L3 | NOT STARTED; after 2.6; policy/legal review |
| 2.3 | Deterministic, config-driven rules in a separate `risk` domain | L2 | NOT STARTED |
| 2.4 | Alert + human review (acknowledge/dismiss with note) + minimal audit entry | L2 | Audit log DONE (`ac7be60`); alerts and human review NOT STARTED |
| 2.5 | Synthetic seed for the core DB + school walk-through | L1 | NOT STARTED |

| Phase | Name | Status |
|---|---|---|
| P0 | CCOS installation (docs/config only) | committed on `ccos/phase-0` in the owner's previous repository history (that branch is not present here); owner accepted |
| P1 | Bootable Baseline + Critical Security Containment | CLOSED 2026-10-13 at `4c096de`; PostgreSQL/FastAPI re-verification deferred (`PHASE1_DEFERRED_ITEMS.md`) |
| P2 | Test harness + Authorization Matrix decisions | Test harness DONE (`scripts/run_tests.sh`, CI workflow); matrix decided in ADR-0003/0005/0010, some cells still DECISION REQUIRED (`SECURITY.md`) |
| P3 | Security baseline (exit criteria in SECURITY.md) | NOT STARTED |
| P4 | Core domain architecture (data layers; React foundation slice at end) | NOT STARTED |
| P5 | Student 360 + analytics | NOT STARTED |
| P6 | Rules / Risk / Alerts / Interventions | NOT STARTED |
| P7 | RAG + AI assistants | NOT STARTED |
| P8 | React completion | NOT STARTED |
| P9 | Production + multi-school readiness | NOT STARTED |

Interim rule: NO REAL STUDENT DATA until P3 exit (Phase 1 does not lift it). Deferred docs created at their phase: DATA_MODEL (P4), API_MAP (P2/P4), RULE_ENGINE (P6), DEPLOYMENT (P9/P1 if needed).
