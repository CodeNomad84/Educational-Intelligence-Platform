# 0035 — Phase 9 exit report (production and multi-school readiness, PREPARED not deployed), 2026-11-02

**Built (repository files only; no server touched, no real data, no real key).**
- **R-04** least-privilege PostgreSQL roles: `deploy/postgres/10-roles.sh` (fresh install), `deploy/postgres-maintenance/r04-convert-existing.sql` (existing database), compose with a one-shot `migrate` service and `school_app` at runtime, production settings default, rehearsal `scripts/test_db_roles.sh` (CI job `dbroles`). Decision 65. The rehearsal found one real defect in my first draft (`REASSIGN OWNED` cannot move objects of the bootstrap superuser) which is fixed.
- **Profiles and preflight:** `deploy/profiles/*.env.example`, `scripts/preflight.py`, `DEPLOYMENT.md` sections 4a and 11. Decision 66.
- **Multi-school:** `schools/test_second_school_gate.py`, `MULTI_SCHOOL_READINESS.md`. Decision 67.
- Earlier in this run: FastAPI exposure proof (no published port), P7 adapter and P7-5 document assistant (reports 0032, 0034), P8 audit (0033).

**Tests:** Django SQLite/PostgreSQL full suite + demo + FastAPI (64) before the push; the `dbroles` rehearsal passes locally including the Django step (migrate as owner, DML as app, DDL refused); mutation check on the second-school gate (an unscoped document list fails it).

**Owner tasks (not done and not decided here):** a real server and domain; real certificates and secrets; the off-site backup target and offline private key; a restore rehearsal and an external port scan on the real server; running `r04-convert-existing.sql` if any database already holds data; the real LLM provider/key and the legal/consent decisions before any student data reaches any AI class; pricing, trial length, legal text, consent, retention; the S7 decision (per-school national id); S8 remainder; Redis authentication if the network is shared.

**Independent review:** NOT VERIFIED — this report refers to an addendum that was never written (no such section exists in the file); a fresh-agent review of the P9 batch is not recorded here. The P7/P7-5/P8 batches were reviewed separately (reports 0032, 0034, 0033).
