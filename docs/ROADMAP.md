# ROADMAP

Current phase: **Phase 2 — MVP productization (compressed roadmap approved by the owner 2026-10-13); sub-phase 2.1 (School / class / teacher scoping) in progress: C0–C3 done, C4–C6 and the access review gate open (status reconciled with git 2026-10-15).** Phase 1 is closed on branch `phase-1/boot-security` at `4c096de` (see `PHASE1_FINAL_STATUS.md`, `PHASE1_DEFERRED_ITEMS.md`). Baseline `3404a1a` is resolvable in this repository's history. Operational model validation remains blocked (`PHASE1_FINAL_VERIFICATION.md`). Each phase starts only on owner approval.

**Phase 2 is Django-first**: no RAG/LLM, no React, no FastAPI changes. PostgreSQL/FastAPI verification was completed 2026-10-15 (`PHASE1_DEFERRED_ITEMS.md` #2, #3; evidence in `TESTING.md`); CI (T-01) stays deferred (#8). Phase 2 absorbs the MVP slice of P2, P4, P5 and P6 below; their full scope remains in the table.

| Sub-phase | Content | Level | Status |
|---|---|---|---|
| 2.0 | Preparation: file-mode normalization, single Django test command, dead settings removal, doc reconciliation, lightweight traceability (`TRACEABILITY.md`), ADR-0003/0004 drafts, Phase 2.1 proposal | L1 + docs | DONE except the file-mode normalization of tracked model binaries, deferred by owner (S-11). Commits: `88c5cdd` test command, `48e8e1f` dead settings, `9f0b461`/`36075a8` doc reconciliation, `ff1b158` traceability, `c8add0e` ADR drafts + proposal, `1181c6b` script mode |
| 2.1 | `School`, `SchoolClass`, `TeacherAssignment` (assigned in admin UI), Student→class relation, teacher object-level scoping | L3 | DESIGN APPROVED 2026-10-13 (ADR-0003/0004 ACCEPTED); C-1 archived (`45218a7`); C0 `e581bed`; **C1 DONE** `2125c9f` (schools app incl. `TeacherAssignment`); **C2 DONE** `85556da` (nullable FKs, `save()` mirror, explicit serializer `fields` at `students/serializers.py:18-23`, form/admin selector); **C3 DONE** `d874168` (`check_class_links`), `f12eb9f` (data migration 0009), `2d41a4e` + `ccd06ac` + `03e72fa` (import class resolution); **C4 NOT STARTED** (permission-grant command only); **gate** `TEACHER_ACCESS_REVIEW.md` NOT STARTED, required before C5; **C5 NOT STARTED** (teacher scoping); **C6 PARTIAL** (`997c8d0` TESTING counts only; SECURITY matrix/S-04, MODULE_MAP, CHANGE_GUIDE, TRACEABILITY pending C5). Related hardening: `72379b1` national_id import validation, `3bf3b8c` backend-neutral tests, `50b3b67` Django bound to loopback (R-03) |
| 2.2 | Teacher-scoped Student 360 read view | L2 | NOT STARTED |
| 2.3 | Deterministic, config-driven rules in a separate `risk` domain | L2 | NOT STARTED |
| 2.4 | Alert + human review (acknowledge/dismiss with note) + minimal audit entry | L2 | NOT STARTED |
| 2.5 | Synthetic seed for the core DB + school walk-through | L1 | NOT STARTED |

| Phase | Name | Status |
|---|---|---|
| P0 | CCOS installation (docs/config only) | committed on `ccos/phase-0` in the owner's previous repository history (that branch is not present here); owner accepted |
| P1 | Bootable Baseline + Critical Security Containment | CLOSED 2026-10-13 at `4c096de`; PostgreSQL/FastAPI re-verification deferred (`PHASE1_DEFERRED_ITEMS.md`) |
| P2 | Test harness + Authorization Matrix decisions | IN PROGRESS as Phase 2.0 (Django test command done; matrix decisions pending ADR-0003) |
| P3 | Security baseline (exit criteria in SECURITY.md) | NOT STARTED |
| P4 | Core domain architecture (data layers; React foundation slice at end) | NOT STARTED |
| P5 | Student 360 + analytics | NOT STARTED |
| P6 | Rules / Risk / Alerts / Interventions | NOT STARTED |
| P7 | RAG + AI assistants | NOT STARTED |
| P8 | React completion | NOT STARTED |
| P9 | Production + multi-school readiness | NOT STARTED |

Interim rule: NO REAL STUDENT DATA until P3 exit (Phase 1 does not lift it). Deferred docs created at their phase: DATA_MODEL (P4), API_MAP (P2/P4), RULE_ENGINE (P6), DEPLOYMENT (P9/P1 if needed).
