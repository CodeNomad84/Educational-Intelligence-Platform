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
## T8 — L2 security fixes after T7 — BLOCKED: owner decisions D0–D4 (proposal written, no code changed)
- Branch: `work/T8-security-fixes` (from `phase-1/boot-security` @ `af41c59`)
- Deliverable this task: `docs/changes/0039-t8-security-fixes-PROPOSAL.md` (L2 proposal, status
  **BLOCKED — DECISION REQUIRED**) + this entry. **No application code, setting, migration or test was changed, and no
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
- `git diff --stat phase-1/boot-security`: documentation only — this entry + `docs/changes/0039-t8-security-fixes-PROPOSAL.md`.



## FOUND (not fixed, out of scope)
- F17 (`role="status"` for non-error messages + `aria-live` on the alert count) not done — not in the
  T5 scope list. F19 (table `<caption>`) still deferred. `risk/rules_index.html` title/duplicate was
  fixed in T3.




