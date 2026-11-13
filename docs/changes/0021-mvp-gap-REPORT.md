# 0021 — MVP gap report: how far the intelligence pipeline is built (2026-10-26)

Docs only. Written from the repository at `e08d677`; nothing was changed in code. Synthetic data only. Labels as in `CLAUDE.md` §2.
Pipeline (`docs/REQUIREMENTS.md`): Data > Student 360 > Analytics > Rules > Risk Event > Alert > Human Review > Intervention > Follow-up > Outcome > Re-evaluation.

## 1. Stage by stage

| # | Stage | Status | Evidence |
|---|---|---|---|
| 1 | Data (students, enrollments, grades, attendance, imports) | **built** | `students/models.py`, `students/access.py`, imports with dry run, `students/test_cross_school_writes.py`, 1232 tests green on SQLite and PostgreSQL |
| 2 | Student 360 | **built** (read view for SchoolAdmin, Grade Lead, Parent; counselor case page) | `dashboard/student360.py`, `dashboard/test_student_360.py`, `dashboard/test_counselor.py` |
| 3 | Analytics | **partial** | derived, on-read analytics exist for modules only: mission engine (`missions/engine.py`) and exam results (`exams/analytics.py`). No trend or comparison analytics over grades/attendance in the core DB; the prototype for that lives in `demo_intel/analytics.py` (demo settings only) |
| 4 | Rules | **partial** | deterministic, config-driven rules exist only in the demo (`demo_intel/rules.py`, `engine.py`, own demo tables, 57 tests, `config/settings/demo.py` adds the app). ROADMAP 2.3 is NOT STARTED for the core DB |
| 5 | Risk event | **missing** | `risk/models.py` defines `RiskEvent`, but `risk` is **not in `INSTALLED_APPS`** and has no migration: no table exists |
| 6 | Alert | **missing** | `risk.Alert` is the same shell (not installed, no migration) |
| 7 | Human review | **missing** | no accept/dismiss code anywhere (ROADMAP 2.4: audit log done, alerts and review NOT STARTED) |
| 8 | Intervention | **missing** | `interventions/models.py` (`InterventionPlan`) is a shell: not installed, no migration, no views. The demo has an unrelated `demo_intel.InterventionRecord` |
| 9 | Follow-up | **missing** | `InterventionFollowUp` shell only |
| 10 | Outcome | **missing** | no outcome field in any installed model (the shell computes effectiveness "at the service layer", which does not exist) |
| 11 | Re-evaluation | **missing** | nothing links a closed intervention back to Student 360 or to a new alert |

Related and built, but not part of this chain: counseling referrals and counselor notes (`students.Referral`, `CounselorNote`, access via an OPEN referral, `ca0ea93`); the audit log (`schools/audit.py`).
**Fact that shapes the next slice:** the four shell apps (`risk`, `interventions`, `behavior`, `governance`) were written before school scoping and cannot load as they are: they point to `accounts.User`, which does not exist (the project uses Django's default user), they use UUID primary keys (the audit log's `object_id` column holds 20 characters; a UUID needs 36) and none has a `school` column. See `0022`.

## 2. What remains for the P3 exit (real data allowed)
Exit criteria are in `docs/SECURITY.md` ("Security Baseline Exit Criteria"). "Blocks" means: one real school must not load real children's data until it is closed.

| Item | State | Blocks real use by one school? |
|---|---|---|
| Legal, consent and retention policy for children's data (owner and legal) | `DECISION REQUIRED`, nothing written | **Yes** |
| Hosting, HTTPS/reverse proxy, hardened production settings | `docs/DEPLOYMENT.md` exists, production never run, no proxy config shipped | **Yes** |
| Scheduled, encrypted, off-site backups with a rehearsed restore | rehearsal script only | **Yes** |
| Secrets rotated, none ever committed in use | status NOT VERIFIED (S-03 PARTIAL) | **Yes** |
| Dependency audit; tracked pickle/joblib model files (S-11) | not done | **Yes** |
| Full `/security-review` of the whole branch | only single changes reviewed | **Yes** |
| Authorization matrix in `SECURITY.md` finalised (most cells still `DECISION REQUIRED`) | the code enforces ADR-0003/0005; the normative table is stale | **Yes** (docs gate) |
| Upload validation: size/type exist for CSV/Excel; scan policy not decided | partial | **Yes** (decide a policy; scanning may be "none, documented") |
| Audit log completeness review (list pages, admin actions, exports) | event coverage reviewed per feature, no full pass | **Yes** |
| Django admin is not school-scoped or module-gated (S9) | open; confirm no school role has `is_staff` | **Yes if any school user can reach `/admin/`**, else no |
| Re-run `check_access_switch_ready` / `compare_access_parity` on the real data | rule in `SECURITY.md` 4c-R1 | **Yes** (a step of go-live) |
| 2.6 referral consent states (parent consent, no exception path, owner D5) | not built | **Counseling only**: a school can start with counseling switched off in practice; it blocks real counseling referrals |
| R-a per-row import provenance | signed batch files exist | No |
| Service-to-service auth (ADR-0002), FastAPI module claim | auth done in Phase 1; module claim open; RAG is disabled (HTTP 403) | No (while `advisor_ai` is unused) |
| S7, S8, S9, S10 (second school) | S7 = C decided; S8-S10 deferred until after P3 | No (single school) |
| Pricing, billing, plans | not built | No |
| Exam slices 3-4, questionnaires, LLM tutor, mission pilot, React | later | No |
| The intervention loop (stages 5-11) | missing | **Not a security blocker; it is the missing product value** of the single-school MVP (Tier C, proposal `0022`) |

Not verified in this report: whether any school-level account can have `is_staff`; ADR-0002 status beyond what the checklist says; production settings behavior.

## 3. Reading
A single school can be run for the existing features (people, grades, attendance, Student 360, referrals, mission, exams) once the P3 items marked "Yes" are closed. The pipeline after "Rules" is not built in the core DB, so today the platform reports but does not close the loop. The smallest slice that closes it is proposed in `0022-intervention-loop-PROPOSAL.md`.
