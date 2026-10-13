# ROADMAP

Current phase: **Phase 1 — implemented on branch `phase-1/boot-security`, awaiting owner review (see `changes/0001-phase1-boot-security-PROPOSAL.md` and the Phase 1 Change Report).** Baseline: commit `3404a1a` (from the owner's original repository history; not present in this repository, which has 0 commits as of 2026-10-12). Phase 1 status: infrastructure verified and ready for independent infrastructure review; operational model validation blocked (see `PHASE1_FINAL_VERIFICATION.md`). Not accepted. Each phase starts only on owner approval.

| Phase | Name | Status |
|---|---|---|
| P0 | CCOS installation (docs/config only) | committed on `ccos/phase-0` in the owner's previous repository history (branch and commit not present in this repository, which has 0 commits); owner accepted |
| P1 | Bootable Baseline + Critical Security Containment | IMPLEMENTED, NOT COMPLETE: Docker/PostgreSQL/real-stack verification pending; see report |
| P2 | Test harness + Authorization Matrix decisions | NOT STARTED |
| P3 | Security baseline (exit criteria in SECURITY.md) | NOT STARTED |
| P4 | Core domain architecture (data layers; React foundation slice at end) | NOT STARTED |
| P5 | Student 360 + analytics | NOT STARTED |
| P6 | Rules / Risk / Alerts / Interventions | NOT STARTED |
| P7 | RAG + AI assistants | NOT STARTED |
| P8 | React completion | NOT STARTED |
| P9 | Production + multi-school readiness | NOT STARTED |

Interim rule: NO REAL STUDENT DATA until P3 exit (Phase 1 does not lift it). Deferred docs created at their phase: DATA_MODEL (P4), API_MAP (P2/P4), RULE_ENGINE (P6), DEPLOYMENT (P9/P1 if needed).
