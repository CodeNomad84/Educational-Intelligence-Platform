# PROJECT CHECKLIST — start to finish

Written for the owner, 2026-10-25, from the repository at `8435a0e`. Docs only; it changes no behavior and is **derived**: code, migrations and tests win over it (see `ROADMAP.md` and `RUNBOOK.md` for detail).
Legend: `[x]` done and verified in the repo (commit or file cited) · `[~]` partial (what is missing is stated) · `[ ]` not started · `[!]` blocked or needs an owner decision. A line marked "unverified" was not checked against code or tests for this list.
Test status at `8435a0e`: 1150 tests on SQLite and on PostgreSQL 16, 57 `demo_intel`, all OK; FastAPI 28 OK (`docs/TESTING.md`). ROADMAP.md now points here for status.

## 1. Foundation
- [x] Phase 1 boot and critical security containment closed (`docs/PHASE1_FINAL_STATUS.md`, `4c096de` per `ROADMAP.md`).
- [x] Authorization model and school scoping decided in ADRs 0003, 0004, 0005, 0010, 0011, 0012 (`docs/adr/`).
- [x] Roles Teacher, Grade Lead, Counselor, Student, Parent, SchoolAdmin enforced through one access layer (`students/access.py`; commits `cdfeef5`, `ca0ea93`, `bbc0190`).
- [x] Superuser is the platform account with no school data (`416c64e`).
- [x] Cross-school write hole closed (`e530877`).
- [x] Multi-school S1 `SchoolMembership` and platform-admin group (report `docs/changes/0011-multi-school-S1-membership-REPORT.md`; model in `schools/models.py`).
- [x] Multi-school S2 tooling and S2b school assignment on every student-creation path (reports `0012`, `0013`; `a29b44b`..`45f541f`).
- [x] Multi-school S6 `Student.school` NOT NULL (`4b40532`, report `0015`).
- [x] Multi-school S3 SchoolAdmin read scope by membership, with leak checks (`e22f140`, `492e8f2`, report `0017`).
- [x] Multi-school S4 writes, imports and commands: every write path refused across schools (`students/test_cross_school_writes.py`), real PostgreSQL import-race test (`students/test_import_race_postgres.py`), maintenance commands classified and scoped (`schools/test_command_scope.py`); see `docs/changes/0019-s4-completion-REPORT.md`.
- [x] Multi-school S5 FastAPI document library scoped by school (`2c5dc7a`).
- [x] Multi-school S7 decided 2026-10-26: **S7 = C (keep global `national_id` uniqueness) until a second real school or first transfer case is planned; then A with a username rule** (`docs/changes/0020-s7-national-id-PROPOSAL.md`). Nothing to build now.
- [ ] Multi-school S8 platform split, S9 Django admin restricted to platform operators, S10 second-school go-live gate: **DEFERRED until after P3** (owner, 2026-10-26; only needed once a second school exists; admin is still ungated, see `0021`).
- [x] Audit log: who viewed or changed what, no content stored (`ac7be60`, `schools/audit.py`).
- [~] Backup and restore: rehearsal script for the demo DB and a documented path (`501f2d1`, `RUNBOOK.md` §3), but no scheduled backups and no encrypted off-site copy.
- [x] Test tooling: `scripts/run_tests.sh sqlite|pg|all`, disposable PostgreSQL container, isolation traps (`fde42b0`, `cb2b44f`; fast test-only hasher `0c0430e`).
- [~] CI (T-01): `.github/workflows/ci.yml` runs Django check, migrations check, SQLite and PostgreSQL tests and `demo_intel`, green on GitHub since 2026-10-25; the FastAPI suite is a separate job (`fastapi_core/requirements-test.txt`).

## 2. Core school features
- [x] Slice 1 SchoolAdmin manages years, classes, teachers, grade leads in the dashboard (`e9b3ee4`).
- [x] Slice 2 Subject Teacher enters grades and recommendations (`cdfeef5`).
- [x] Slice 3 Student 360 page for SchoolAdmin, Grade Lead and Parent (`e5e4cfe`).
- [x] Slice 4a Counselor role and referrals (`ca0ea93`); owner corrections A1-A4 (`52e82eb`).
- [~] Referral workflow states and parental consent (declined, awaiting consent, parent declined) from roadmap 2.6: not in code (`grep awaiting_parent_consent` finds nothing); satisfaction feedback 2.7 not started.
- [x] Slice 4b Student role with a demo-stub study assistant (`bbc0190`).
- [x] Bulk accounts from Excel with dry run, confirm and a one-time login sheet (`983c07a`); dead `/upload/` stub replaced (`b48a0e4`).
- [x] Forced first-login password change and profile password change (`983c07a`).
- [x] Password reset by SchoolAdmin and by Grade Lead (school setting, default off) (`a52b81b`); a lost login sheet is reissued from the same list (test 2026-10-25, linked from the accounts page).
- [x] Login throttle per username and address on `/login/` and `/api/token/` (`201c94d`).
- [x] One home entry per role in the sidebar with a duplicate-link test (`4651c9a`, `dashboard/test_menu.py`).
- [x] Persian quick-start page for the SchoolAdmin (`acf2bd8`).
- [x] Demo seed with all modules licensed and synthetic mission and exam data (`4651c9a`, `8435a0e`).
- [~] Grade entry (own class and subject) is done for teachers, but roadmap item 2.2b "grade needs academic year and class" is recorded as open (`SECURITY.md` C5a-R1).
- [ ] Deterministic risk rules and alerts in the real core DB (roadmap 2.3/2.4; `risk/` has `RiskEvent`/`Alert` models only; the demo has its own rules).
- [x] Intervention loop built 2026-10-26 (change 0022; commits `9063a1c`, `e8e367e`, `63c0715` and the Student 360/re-evaluation commit): manual alerts, human review (accept/dismiss with a coded reason), intervention plans, follow-ups, outcome, re-evaluation list and Student 360 tile; base module, no AI; emotional-plan text only for the owner and an open-referral Counselor. `NOT YET IMPLEMENTED`: the rule engine that calls `risk.services.raise_alert` (2.3), notifications, parent view, effectiveness scoring.
- [!] Retention period for alerts, plans, follow-ups and risk events waits for the legal policy; risk events 3 years per doc 12, not enforced; nothing is deleted automatically.
- [ ] Open item: `Referral` and `CounselorNote` still use `CASCADE` on the student, the new loop tables use `PROTECT` (students are deactivated, never deleted); decide whether to align (changes applied models, Tier C).
- [ ] Open item: the local `.git/info/exclude` hides `django_core/{risk,interventions,behavior,governance,accounts,core}`; `risk/` and `interventions/` were force-added (new files there need `git add -f`).
- [ ] Open item (info, from 0023 F4): list pages and the Student 360 tile are not audit-logged (plan pages and sensitive alert text are); part of the audit completeness review.
- [ ] Open item (info, from 0023 F5): no rate limit on raising alerts.
- [ ] Open item (info, from 0023 F6): the loop's test fixture `risk/loop_testing.py` lives inside the app package and imports `dashboard.test_counselor`; move it to a test-only location when convenient.
- [x] Alert text rule (0023 F3): message and review note of `emotional`/`family` alerts readable only by the raiser and an open-referral Counselor; SchoolAdmin and Grade Lead see metadata and can still review.
- [x] Demo PlatformAdmin `demo_platform` in the demo seed (staff, zero permissions, demo database only); a PlatformAdmin lands on `/platform/modules/` (2026-10-26).
- [ ] `create_school` command with an audit event (school creation is not audit-logged): **before the second pilot school**. Decision 2026-10-26: onboarding option A (manual checklist, `docs/manuals/platform-admin.md`) now; PlatformAdmin gets NO extra powers; school creation stays with the superuser.
- [ ] S9 Django admin closure: the superuser sees every user account, including student and parent accounts whose usernames are national ids. **Must be closed before real data.**
- [x] Owner decision 2026-10-26: the Grade Lead MAY read counselor notes of students in the own grade (read only, enrollment-based grade scope, tied to a referral; pinned by `dashboard/test_lead_counselor_notes.py`). Known gap: no note-specific audit event. Open question for the owner: align this with the metadata-only rule for emotional/family alerts and emotional plan text?
- [ ] Future idea (not now): the counselor marks each note "counselor only" or "shared with the grade lead".
- [ ] Proposal `docs/changes/0025-rules-and-alerts-PROPOSAL.md` (deterministic rules and derived analytics feeding the alerts): awaiting owner decision.
- [ ] P3 exit plan `docs/changes/0026-p3-exit-plan-NOTE.md`: owner/legal/ops tasks (O1-O9) can start now; code tasks (C-*) in order.
- [ ] Parent notifications, parent-teacher messaging, printable report card, behavior log UI (backlog items 3-6).
- [!] Parent individual-record access (Parent sees `parent_user`; recorded as C5a-R3/C6 in `SECURITY.md`).

## 3. Commercial layer
- [x] Per-school module entitlement for `advisor_ai`, `tutor_ai`, `exams`, `mission`; Student 360 and counseling stay base (`ef7a0d1`, `schools/entitlements.py`).
- [x] Trial versus licensed rows, expiry banner, locked-but-visible menu with a static info page, per-school AI call caps (`06e9dcb`).
- [x] Platform operator grants modules by command or Django admin, audit-logged (`set_school_module`, `schools/admin.py`).
- [x] Operator page `/platform/modules/` (`dashboard/operator_page.py`): superuser or PlatformAdmin only, per-school module state, end date, days left, AI usage vs caps, expiring filter, audit-logged, no student data; base/platform, not a sellable module.
- [ ] Billing, plans, prices, invoices, license keys, renewal and usage reports: deliberately not built.
- [!] Pricing and trial-length policy (owner decision, not yet made).
- [~] FastAPI carries no module claim, so module gating is Django-side only (`entitlements.py` docstring).

## 4. Modules
### Mission / Qalamestan
- [x] Slice 1 models, versioned default weights, fast observation grid (`f681093`).
- [x] Slice 2 rule engine plus evaluation hook for a later ML comparison (`8001002`).
- [x] Slice 3 per-student report, 2-3 suggested paths with `params_version`, activity-choice and parent-meeting forms, admin aggregate with groups under 5 hidden (`3390f08`).
- [x] Read-only weights page for SchoolAdmin and grid help text (`dd4c03c`).
- [x] Slice 2b weights lifecycle UI for the SchoolAdmin: draft > simulated > pending approval > active, aggregate simulation, clone, immutable active/retired, `params_version` kept (`missions/lifecycle.py`, `views_weights.py`).
- [x] Mission weights approval decided 2026-10-25: single approver for now; creator, approver and approval time are shown on the weight-set page and the approval is audit-logged. Optional per-school "require second approver" switch (default OFF) to revisit before the first real multi-admin school.
- [ ] Real-teacher pilot of the rubric and weights; the weights are an unvalidated first proposal.
- [!] Whether subject teachers may enter the two forms (owner said Grade Lead only; revisit after the pilot).
### Exams
- [x] Slice 1 question bank with an explanation per option, flat topics, exams for classes, practice player, module gate (`8435a0e`).
- [~] Slice 2 built 2026-10-25 (CSV import with dry run, exam editing, teacher/Grade Lead/SchoolAdmin results with group floors); still missing: repeated-error rule, weekly trend, per-student baseline-relative time.
- [ ] Slice 3 study recommendations, Student 360 tile, retention cleanup command.
- [ ] Slice 4 AI question suggestions behind a separate exams AI cap and the external-LLM switch.
- [!] Exam retention period, SchoolAdmin and parent access to individual analytics, question ownership when a teacher leaves (`docs/EXAM_DESIGN_V2.md` §7).
### Questionnaires
- [ ] In-platform family and student questionnaires (`docs/EXAM_AND_SURVEY_DESIGN.md` §2; design only).
- [!] Consent text, retention rules and anonymity group size need an approved policy first.
### Vocabulary
- [x] School-scoped, dated, never-edited-in-place vocabulary terms with `seed_vocabulary` (`0c1b246`).
- [!] A tree (`parent` link) is a later Tier C decision; flat dotted codes are used now.

## 5. AI
- [x] Governance rules written (`docs/AI_GOVERNANCE.md`) and the Socratic tutor designed (`docs/ASSISTANT_DESIGN.md`, design only).
- [x] Demo-stub study assistant and demo School Assistant run without any LLM (`bbc0190`, `demo_intel/`).
- [ ] LLM integration for the tutor: pseudonymisation, safety escalation to adults, transparency to the student (all in the design, none built).
- [!] External-LLM switch: whether any external provider is allowed at all, which provider and which country.
- [ ] `advisor_ai` real implementation (RAG over school data with ACL before retrieval; FastAPI RAG is disabled, HTTP 403).
- [ ] Adaptive learning feedback from exam analytics (after exams Slice 2).
- [ ] Prompt-injection and unauthorized-retrieval tests for the AI layer (`SECURITY.md` review topics).

## 6. Hardening before real data
- [x] `/admin/` login throttled with the same limits and counters as `/login/` (`dashboard/throttle.py` `throttled_admin_login`, tests in `dashboard/test_login_throttle.py`).
- [~] Throttle behind a proxy: client address source is configurable (`THROTTLE_TRUSTED_PROXIES`, default OFF, tests for both modes); still no HTTPS or reverse-proxy configuration shipped (RUNBOOK).
- [ ] Password strength beyond length 8, 2FA for SchoolAdmin, email/SMS self-service reset (RUNBOOK).
- [~] Migration-order fragility between `schools.0010` and `students.0009`: guarded by `schools/test_fresh_migrate.py` (fresh-DB module rows and plan order; `docs/changes/0018-migration-order-guard.md`); an explicit dependency is unsafe for databases behind on migrations, so the order is protected, not enforced.
- [x] Concurrent import race on PostgreSQL has a real two-connection test that runs in `pg` mode and the CI postgres job (`EIP_REQUIRE_PG=1`).
- [~] R-a batch-file provenance: signed batch files exist (`067571b`), no per-row provenance (RUNBOOK).
- [ ] FastAPI module claim in the service token (RUNBOOK).
- [ ] Django admin not school-scoped and not module-gated (RUNBOOK; S9).
- [ ] Audit log completeness review (list pages, exports, admin actions) (RUNBOOK).
- [ ] Test-container overlay misses files replaced mid-run (RUNBOOK; avoid reseeding the demo while tests run).
- [x] FastAPI suite re-run 2026-10-25: 28 tests OK in the fastapi image (`docs/TESTING.md`); still not part of CI.
- [ ] Dependency audit and the tracked pickle/joblib model files (S-11 in `SECURITY.md`).
- [ ] Full `/security-review` of the whole branch, not only of single changes.
- [!] Legal, consent and retention policy for children's data (owner and legal; gates questionnaires, surveys, referral consent, real data).
- [ ] Real-data readiness gate (P3 exit criteria in `SECURITY.md`): authorization matrix tested, scoping everywhere, secrets rotated, upload validation, hardened production settings, dependency audit, permission tests green in CI.
- [!] Rotation of any secret that was ever committed (hard rule in `CLAUDE.md`; status unverified).

## 7. Deployment and operations
- [ ] Production deployment from `docs/DEPLOYMENT.md` (Docker compose exists; production never run; unverified).
- [ ] Scheduled, encrypted, off-site backups with a rehearsed restore on real infrastructure.
- [ ] Monitoring, logging and alerting.
- [ ] Onboarding runbook for a first pilot school: create school, admin, year, classes, staff, bulk accounts (steps 2 and 6 of `RUNBOOK.md` exist; pilot not done).
- [ ] Pilot feedback loop with teachers (mission observations and exam use) feeding weights and rubric changes.
- [!] Hosting location and who operates the platform day to day.

## 8. Later
- [ ] Rules versus ML evaluation on held-out anonymised data (hook exists: `missions/evaluation.py`).
- [!] Framework tree (principle > component > indicator) for vocabulary (Tier C schema decision).
- [ ] Family questionnaires in production use (see §4).
- [ ] React frontend (target in `ARCHITECTURE.md`; not started).
- [!] Google sign-in for staff, LTI or other integrations: only if the owner wants them (decision 8 in `EXAM_AND_SURVEY_DESIGN.md`).
- [ ] Multi-language support, only if non-Persian-speaking families appear.

## Next 5 recommended steps
1. Exams Slice 2: CSV import first, then analytics (your order).
2. The operator page (read-only module and AI usage view; approved in principle).
3. Mission slice 2b: weights lifecycle UI so the weights can be tuned after a teacher pilot.
4. Hardening: the migration-order fix as its own commit once CI has run green on GitHub.
5. Run a closed pilot with synthetic data and 2-3 real teachers on mission observations, before any real student data.

## Decisions waiting for the owner
1. Migration-order fix: make `schools.0010` / `students.0009` order explicit (touches applied migrations).
2. Exams: retention period, SchoolAdmin and parent access to individual analytics, question ownership, separate exams AI cap values, whether AI suggestions are allowed at all.
3. External LLM: allowed or not, provider and country.
4. Legal, consent and retention policy for questionnaires, referral consent and real data.
5. Subject teachers on the mission forms; and when the weights may leave "unvalidated".
6. Pricing, plans and trial length (before any billing work).
7. Hosting and operator model for production.
8. Vocabulary tree (Tier C) versus flat codes.

## User manuals (source for the final manuals)
- [x] Skeleton and backfill 2026-10-26: `docs/manuals/` has one file per role (platform admin, school admin, grade lead, teacher, counselor, parent, student) and a README with the convention and the markers TO VERIFY / PENDING POLICY / NOT BUILT. Written in plain English first; Persian translation at the end of the project.
- [ ] Every item marked TO VERIFY in the manuals is checked in the running product before publishing.
- [ ] Manual material marked PENDING POLICY (consent, retention, external LLM, parent access) is finished only after the owner decides.

## Template for a new slice's checklist entry
```
- [ ] <slice name> (proposal NNNN): code + tests green on SQLite and PostgreSQL + mutation checks for access rules + security review + docs (maps, SECURITY matrix if access changed) + **manual lines for each affected role (docs/manuals/<role>.md)** + CI green
```
