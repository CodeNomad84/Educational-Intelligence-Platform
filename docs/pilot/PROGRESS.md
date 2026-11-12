# PILOT PROGRESS (Cline appends; owner reads)

## Baseline (owner-merged before this run)
- T1 `pg-harness fix` — already merged into `phase-1/boot-security` (`9e3763e`).

## T2 — L1 docs-fix (prerequisite, committed while branching T3)
- Branch: `work/docs-fix` · Commit `bca8851`
- Scope: 0037 owner corrections — F8 into 0037a scope (12 findings), F16 is a 2.1 AA failure,
  severity counts (8 High/10 Medium/8 Low), effort (2.5 days, ~5 days), added §10a owner answers.

## T3 — L2 0037a "Names and structure" (incl. F8) — DONE
- Branch: `work/T3-0037a-names-and-structure` · Commit `c683beb`
- Scope (12 findings): F1 (label `for`/aria-label on unnamed controls), F2/F3 (shared
  `_form_errors.html` with `role="alert"` + real ids), F4 (`<title>` via `{% block title %}` +
  new `{% block page_title %}` for the h1), F6 (thead on 360 alerts/plans), F8 (aria-hidden on
  decorative icons; icon-only controls already named), F9/F10 (`scope=col/row` on every `<th>`
  + visually-hidden action headers), F11 (`aria-current` on active alert filter), F12 (section
  titles h5→h2.h5), F18 (grade-sheet row error under its input + aria-describedby). Also fixed a
  broken `{% block title %}` + duplicate content in `risk/rules_index.html`.
- New rendered a11y test `dashboard/test_a11y_render.py` walks all 6 demo roles (bounded BFS,
  `seed_demo_school`) asserting 0 unnamed controls and 0 `<th>` without `scope`.
- `git diff --stat`: `74 files changed, 315 insertions(+), 178 deletions(-)`.

### Test log tail
- sqlite: `Ran 1567 tests in 826.976s` / `OK (skipped=11)` / demo_intel `OK` →
  `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`
- pg: `Ran 1567 tests in 1560.797s` / `OK (skipped=1)` →
  `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)`

## T4 — L2 0037b "Guard rails" — DONE
- Branch: `work/T4-0037b-guard-rails` · Commit `83a63ff`
- Scope: four markup lint rules in `dashboard/test_template_guards.py` (th scope, icon
  aria-hidden, canvas name, extends-base-has-title), scoped to dashboard+risk; completed F8
  (aria-hidden on the remaining Bootstrap icons) and F5-minimal (role+aria-label on the
  grade-dashboard canvases); scoped remaining risk `<th>`s and h4/h5 section/modal/card titles.
- `test_a11y_render.py` now also asserts distinct titles, heading-order and no duplicate ids.
- New `test_contrast_tokens.py` parses `eip.css` `:root` and asserts 4.5/3.0, with the explicit
  `EXPECTED_FAILURES` list (6 pairs, regression marker until 0037c) + decorative card-border exemption.
- New `docs/A11Y_UI_CHECKLIST.md`. Browser pass (`page_audit.mjs` + axe-core) is dev-only/manual — not wired.
- `git diff --stat`: `22 files changed, 286 insertions(+), 60 deletions(-)`.

### Test log tail
- sqlite: `Ran 1577 tests in 1033.034s` / `OK (skipped=11)` / demo_intel `OK` →
  `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`

## T5 — L2 0037c "Colour and the two charts" — DONE
- Branch: `work/T5-0037c-colour-and-charts` · Commit `c4ad3fb`
- Scope: `--eip-muted` #6b7686→#5f6b7a (F7); `--eip-border-strong`→#8a94a6 and warning meter
  fill→#b8791f to ≥3:1 (F14); `.eip-soon` uses `ink-2` on the border tint (F15); focus ring solid
  2px `#2457b8` (F16); `.eip-stack thead` kept in the DOM (visually hidden) on mobile (F13);
  visually-hidden fallback tables for the two Grade-Lead charts (F5, view exposes zipped `rows`).
- `test_contrast_tokens.py` drops `EXPECTED_FAILURES`; all pairs assert natively (text ≥4.5, graphic ≥3.0).
- `git diff --stat`: `4 files changed, 54 insertions(+), 37 deletions(-)`.

### Test log tail
- sqlite: `Ran 1577 tests in 1119.259s` / `OK (skipped=11)` / demo_intel `OK` →
  `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`
- pg: `Ran 1577 tests in 1719.222s` / `OK (skipped=1)` →
  `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)`

## T6 — L1 wrap-up "Documentation & integration" — DONE
- Branch: `work/T6-0037-wrap-up` (from `work/T5-0037c-colour-and-charts` @ `76f718c`) · Commit `a41767d`
- Scope: `docs/changes/0037-ux-audit-REPORT.md` — catalogues F1–F16 + F18 resolved and F17/F19 deferred
  (with rationale); `docs/A11Y_UI_CHECKLIST.md` re-synced to the three active guards
  (`test_template_guards.py`, `test_a11y_render.py`, `test_contrast_tokens.py`; `EXPECTED_FAILURES` cleared
  in 0037c); `docs/CHANGE_GUIDE.md` Verified-at note + look-and-feel a11y-guard pointers.
- `git diff --stat`: `3 files changed, 83 insertions(+), 5 deletions(-)`.

### Test log tail (T6 final sanity check)
- sqlite: `Ran 1577 tests in 1533.473s` / `OK (skipped=11)`; demo_intel `Ran 62 tests in 231.760s` / `OK` →
  `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`

## T6 — L1 pilot-config (PILOT QUEUE) — DONE
- Branch: `work/T6-pilot-config` (from `phase-1/boot-security` @ `c9e1fdf`) · Commit `45e9cb4`
- Scope: flags `PILOT_MODE` / `ENABLE_AI_FEATURES` (False) / `ENABLE_COUNSELOR_ROLE` (False) / `FEEDBACK_URL`
  in `config/settings/base.py` (fail-closed; `development.py` re-enables them for dev/demo/tests);
  `dashboard.decorators.require_pilot_flag` gates the Counselor/referral routes (`counselor_views.py`) and the
  assistant routes (`student_views.py` `tutor_ai`, `docqa/views.py` `advisor_ai`) to 403 when off;
  `fastapi_core/auth.py::disabled_in_phase1` is now config-driven (403 while `ENABLE_AI_FEATURES` is off);
  footer feedback link from `FEEDBACK_URL` (`base.html` + context processor); `docs/pilot/PILOT_CONFIG.md`
  (flags + "one server, two isolated instances" answer); `test_pilot_config.py` (Django + FastAPI).
- `git diff --stat phase-1/boot-security`: `12 files changed, 277 insertions(+), 10 deletions(-)`.

### Test log tail (module tests only, per task)
- Django: `Ran 44 tests in 4.591s` / `OK`  (test_pilot_config + test_counselor + test_student_me + test_modules)
- Django docqa: `Ran 24 tests in 6.001s` / `OK`
- FastAPI: `Ran 40 tests in 1.460s` / `OK`  (tests.test_pilot_config + tests.test_security)

## T7 — L1 whole-branch security review (read-only) — DONE (report only, no code)
- Branch: `work/T7-security-review` (from `phase-1/boot-security` @ `4a516c2`) · Commit `e2a7342`
- Scope: `docs/pilot/T7-SECURITY-REVIEW-REPORT.md` — static review of `config/settings/*`, both URL maps,
  `students/access.py` + `student_school`, the access decorators, DRF (`views`/`serializers`/`permissions`),
  every upload path, the Django→FastAPI service-token bridge (`config/service_auth.py`,
  `fastapi_core/auth.py`), `llm_adapter`, `docqa/`, the legacy library routes, throttling / forced-password
  middleware / password reset / bulk views, `docker-compose.yml` + `fastapi_core/Dockerfile` +
  `deploy/postgres/*.sql`, and every template that renders server data. IDOR sweep was exhaustive: all 41
  `get_object_or_404` hits in `dashboard/ risk/ missions/ exams/ docqa/` were read.
- Result: **no CRITICAL.** 1 HIGH — `students/views.py:248-272` reads an unbounded import upload (no byte cap;
  OOM/disk exhaustion for all tenants). 5 MEDIUM — 3000 s timeout on the legacy library upload
  (`dashboard/views.py:263`); AI service logs at DEBUG incl. document text (`fastapi_core/main.py:37,292-295`);
  raw exception text / upstream bodies returned to clients; an unauthenticated second FastAPI app shipped in
  the image (`main_HuggingFace.py`, = deferral item 7, reachable only if adopted); no audit event on the bulk
  PII import. 11 LOW (§2 table). §4 lists 17 areas checked and clean; §5.1 lists what is **NOT VERIFIED**;
  §5.2 lists 4 **DECISION REQUIRED** owner questions; §6 gives the T8 fix order.
- **No application code, setting, migration or test was changed** — every fix is DEFERRED to T8.
  Tests deliberately **not** run (nothing to test; constraint of the task).
- `git diff --stat phase-1/boot-security`: `2 files changed, 509 insertions(+)` — this report + this entry, nothing else.

## T8 — L2 security fixes after T7 — READY FOR REVIEW: 7 findings fixed, all three suites green, not merged
- Branch: `work/T8-security-fixes` (from `phase-1/boot-security` @ `af41c59`)
- Deliverable this task: `docs/changes/0039-t8-security-fixes-PROPOSAL.md` (L2 proposal, status
  **BLOCKED — DECISION REQUIRED** — history, superseded by the owner answers below) + this entry. **No application code,
  setting, migration or test was changed, and no
  test was run** (nothing to test yet).
- Why BLOCKED: `QUEUE.md` T8 row — "fix ONLY Critical/High findings of T7 … If a fix needs a design decision …:
  BLOCKED". T7 §2 has **no CRITICAL** and exactly one HIGH (H-1), and T7 §5.2 item 4 leaves H-1's ceiling to the owner
  ("so T8 does not invent the policy"). The session brief names H-1 **and** M-1…M-5 (MEDIUM) and L-5 (LOW), which the
  queue does not put in T8 → the scope must be decided before any commit (D0).
- Verified CURRENT while writing the proposal (commands quoted in §2 of it): `POST /api/students/import/` has **no**
  byte cap and **no** row cap (`students/views.py:250-277`, `len(df)` only in the response at `:409`) and
  `FileUploadSerializer.file` has no validator (`serializers.py:87-90`); `config/settings/` has **no**
  `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE`; `dashboard/views.py:263 timeout=3000`;
  `fastapi_core/main.py:37` DEBUG + `:295` logs the first document chunk; `main_HuggingFace.py` and
  `rag_service_HuggingFace_Models.py` are **untracked** (`.git/info/exclude:19-20`) yet copied into the image by
  `fastapi_core/Dockerfile`'s `COPY . .`; `dashboard/bulk_views.py:48` puts the parsed rows in the session;
  `AuditEvent.action` is `max_length=40`, so a new action needs no migration.
- Correction recorded in the proposal: `FILE_UPLOAD_MAX_MEMORY_SIZE` is not a byte cap and
  `DATA_UPLOAD_MAX_MEMORY_SIZE` does not cover file fields — T7 §3 H-1 item 4 needs that caveat.
- Decisions to answer (each with a recommended option in §13 of the proposal): **D0** scope, **D1** H-1 ceiling,
  **D2** M-4 keep vs delete the untracked files, **D3** L-5 storage, **D4** M-5 audit vocabulary.
- `git diff --stat phase-1/boot-security`: documentation only — `docs/changes/0039-t8-security-fixes-PROPOSAL.md` (192
  lines) + this entry, in commit `d50f0ac` (`2 files changed, 216 insertions(+)`), plus the small edits in the commits
  that record this sentence. No code, setting, migration or test in any of them.

### Owner answers (2026-11-11): `D0=b D1=a D2=a D3=b D4=yes`
- Scope = H-1, M-1…M-5, L-5. The `QUEUE.md` T8 row still says "Critical/High only"; that file is owner-owned, so the
  amendment note is yours, not mine.
- Implementation: one commit per finding on `work/T8-security-fixes`, each behind a test that fails without it.
  - **C1 `547ca2d` H-1** — `IMPORT_MAX_BYTES = 2 MB` + a bounded read in `students/views.py`; the extension/format check now
    runs *before* the bytes are read. A module constant, not a setting (`D1=a`).
  - **C2 `cb003da` M-5** — `audit.STUDENT_IMPORT = 'student_import'`, detail `s<n>u<n>e<n>` (counts only), object = the
    target School, one event per accepted import and none for a refused upload (`D4=yes`; no migration: `action` is 40 chars).
  - **C3 `26c774c` M-3** — no exception text or upstream body reaches a client: Django (`students/views.py` fixed row/file
    messages + `logger.warning/exception`), `dashboard/views.py` (all five AI call sites), FastAPI (`_internal_error()`
    returns a fixed sentence and an `X-Correlation-Id`).
  - **C4 `9d13241` M-2** — FastAPI level comes from `LOG_LEVEL` (default `WARNING`); document text and filename are gone
    from every log line.
  - **C5 `5131c53` M-1** — the legacy library upload's `timeout=3000` is now `AI_UPLOAD_TIMEOUT = 30`, and a timeout shows
    one fixed sentence (`dashboard.tests.LegacyUploadTimeoutTests`).
  - **C6 `f524ab2` M-4** — `fastapi_core/.dockerignore` excludes `main_HuggingFace.py` and
    `rag_service_HuggingFace_Models.py`; the local files stay on disk (`D2=a`). `test_exposure.SingleApplicationTests`
    fails if a second `FastAPI(` application is in the build context (it reads `.dockerignore` to decide what "the build
    context" means). `docs/PHASE1_DEFERRED_ITEMS.md` item 7 is closed.
  - **C7 `6ab08c8` L-5** — `bulk_views.py` keeps the parsed rows in the cache (30-minute TTL; Redis in production, LocMem in
    a dev/demo run) and the session row holds only a 43-character random token (`D3=b`). The school id stored *inside* the
    cache entry is what authorises a token, so another school's admin cannot replay one.
- `docs/pilot/T7-SECURITY-REVIEW-REPORT.md` §2 now carries the `Status` column (per-finding commit), and its header says
  which findings are fixed and which are still open.
- Test evidence per module, before the full gate (CURRENT, real runs read from a file, not assumed): `dashboard.tests` 34 OK,
  `dashboard.test_bulk_accounts` 30 OK, `fastapi_core/tests/test_exposure.py` 7 OK (native run; the class skips inside the
  image where the repository root is not mounted).
- **The closing gate has now been run (CURRENT, output redirected to a file and read back):**
  - `scripts/run_tests.sh sqlite` → `Ran 1607 tests in 1423.000s` / `OK (skipped=11)` and `demo_intel`
    `Ran 62 tests in 204.430s` / `OK` — last line `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not
    covered)`.
  - `DJANGO_IMAGE=eip-test-django:local scripts/run_tests.sh pg` → `Ran 1607 tests in 1335.585s` / `OK (skipped=1)` — last
    line `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)`; the
    throw-away container and its internal network were removed by the script (`docker ps -a` has no `eip-test-*` left).
  - FastAPI in the image, `--network none`: `Ran 74 tests` / `OK (skipped=7)` (`test_exposure.SingleApplicationTests`
    skips there, it needs the repository root; it is green natively).
- Merged? **No.** Pushed? **No.** `main` untouched. `/tmp/t8_full_sqlite.txt`, `/tmp/t8_full_pg.txt` and
  `/tmp/t8_fastapi_full.txt` hold the raw output of the three runs above. `git log --oneline
  phase-1/boot-security..HEAD` has 14 commits: the 7 fixes above plus 7 proposal/status commits whose last one is the one that
  records these results.



## T9 — L1 multi-school readiness audit (read-only) — DONE (report only, no code)
- Branch: `work/T9-multi-school-readiness` from `phase-1/boot-security` @ `dd9ed5b`.
- Deliverable: `docs/pilot/T9-MULTI-SCHOOL-READINESS-REPORT.md` (inventory by surface, the isolation model with
  `path:line`, findings, onboarding checklist, verdict). **Docs only**: no application code, settings, migration,
  template or test touched.
- Evidence, not fixtures: a throw-away two-school SQLite DB in `/tmp` built with `create_school alpha|bravo`
  (`EIP_DEMO_DB`, synthetic data only). `create_school` + `seed_rules` created **per school**: 30 vocabulary terms and
  5 starter rules each. A real `POST /login/` as alpha's SchoolAdmin (`302 /school/`) then walked 30 URLs: 200 on every
  page alpha may see (`/dashboard/`, `/students/`, `/alerts/`, `/interventions/`, `/school/*`, `/rules/*`), `403` on
  `/grade/`, `/platform/modules/`, `/exams/*`, `/mission/*`, `/assistant/*` (role/module gates), and **zero traces of
  bravo's students on any page**. Bravo's students: `detail`/`360`/`report-card` → 404; five write POSTs
  (`behavior/new`, `alert`, `plan/new`, `refer`, `account`) → 404 with `behavior/plan/alert` row counts unchanged
  `(0,0,0) → (0,0,0)`; `?search=BRAVO` → no match; own three students still visible (probe not vacuous).
- Read-only checks on that DB, all exit 0, `writes: none`: `check_student_school_ready` `ready:true`,
  `check_access_switch_ready --multi-school` `verdict:READY` / `multi_school_passed:true` / `blockers_nonzero {}` /
  `info_school_admins_per_school {"2":1,"3":1}`, `compare_access_parity --multi-school` `verdict:PASS` /
  `students_leaked 0` / `info_other_school_students_hidden 6`, `check_school_memberships` `orphan_active_total 0`,
  `check_class_links` `6 linked / 0 candidates`, `check_academic_years` `overlapping_ranges 0`,
  `check_assignment_subjects` `assignments 0`, `check_enrollment_backfill` `6 already with enrollment`.
- Findings (no HIGH): T9-F1 LOW new school gets no modules → 403 until enabled; T9-F2 LOW fresh install has an empty
  `default` school and no `SchoolAdmin` group (`setup_staff_roles` creates only Teacher/GradeLead/Counselor); T9-F3
  MEDIUM `national_id` globally unique (S7 `DECISION REQUIRED`, `changes/0020`); T9-F4 LOW DRF writes keep
  `IsAdminUser` so a SchoolAdmin reads but cannot write through the API; T9-F5 MEDIUM superusers see all schools until
  S8 (`DEFERRED`); T9-F6 LOW legacy library isolates only in the FastAPI service (signed `schools` claim) and the
  unscoped `main_HuggingFace.py` / `rag_service_HuggingFace_Models.py` must stay out of the image.
- Gate (CURRENT, read from the file): `scripts/run_tests.sh sqlite` → `Ran 1607 tests in 2265.340s` / `OK (skipped=11)`,
  `demo_intel` `Ran 62 tests` / `OK`, last line `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not
  covered)`; `DJANGO_IMAGE=eip-test-django:local scripts/run_tests.sh pg` → `Ran 1607 tests in 1424.983s` /
  `OK (skipped=1)`, last line `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not
  covered)`.
- Merged? **No.** Pushed? **No.** `main` untouched.

## FOUND (not fixed, out of scope)
- F17 (`role="status"` for non-error messages + `aria-live` on the alert count) not done — not in the
  T5 scope list. F19 (table `<caption>`) still deferred. `risk/rules_index.html` title/duplicate was
  fixed in T3.




