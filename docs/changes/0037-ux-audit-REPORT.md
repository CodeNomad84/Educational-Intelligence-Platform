# 0037 — UX / accessibility audit delivery (report), 2026-11-09

**Level L2 — approved proposal `0037-ux-audit-PROPOSAL.md` (owner decisions 10.1–10.8, 2026-11-09).**
Delivered in three batches on a linear branch chain from `phase-1/boot-security`; this T6 wraps up with the report, checklist/guide sync and a final sanity run. Wrap-up branch `work/T6-0037-wrap-up` (from `work/T5-0037c-colour-and-charts` @ `76f718c`).

No `students/access.py`, entitlement, audit-rule, schema, URL or permission change in any batch; no migration, no new endpoint, no new runtime dependency.

## 1. Delivery by phase

| Phase | Batch | Branch | Feature commit | Record commit | Scope (summary) | `git diff --stat` |
|---|---|---|---|---|---|---|
| T3 | 0037a "Names & structure" | `work/T3-0037a-names-and-structure` | `c683beb` | `0dfd82c` | 12 A-level findings: labels, shared error include, `<title>`, `<thead>`, `scope`, icon `aria-hidden`, `aria-current`, heading levels, grade-sheet error | 74 files, +315/−178 |
| T4 | 0037b "Guard rails" | `work/T4-0037b-guard-rails` | `83a63ff` | `deb0fdf` | 4 markup lint rules + rendered-name test + token-contrast test + checklist | 22 files, +286/−60 |
| T5 | 0037c "Colour & charts" | `work/T5-0037c-colour-and-charts` | `c4ad3fb` | `049362a`, `76f718c` | colour tokens, focus ring, responsive `<thead>`, chart fallback tables | 4 files, +54/−37 |

## 2. Resolved findings (F1–F16 and F18)

| ID | SC | Sev | Fix | Phase |
|---|---|---|---|---|
| F1 | 3.3.2, 1.3.1 (A) | High | `label for` / `aria-label` on the unnamed controls | T3 |
| F2 | 3.3.1, 4.1.2 (A) | High | shared `_form_errors.html` with real error `id`s | T3 |
| F3 | 3.3.1, 4.1.3 (AA) | High | `_form_errors.html` announces via `role="alert"` | T3 |
| F4 | 2.4.2 (A) | High | `{% block title %}` reaches `<head>` + `{% block page_title %}` for the h1 | T3 |
| F5 | 1.1.1, 4.1.2 (A) | High | `role="img"`+`aria-label` on the Grade-Lead canvases (T4) + `visually-hidden` fallback tables from the `json_script` (T5) | T4 + T5 |
| F6 | 1.3.1 (A) | High | `<thead>` on the 360 alerts/plans table | T3 |
| F7 | 1.4.3 (AA) | High | `--eip-muted` `#6b7686` → `#5f6b7a` (≥4.5:1) | T5 |
| F8 | 4.1.2 (A) | High | `aria-hidden` on decorative Bootstrap icons (T3, then the remaining ones in T4) | T3 + T4 |
| F9 | 1.3.1 (A) | Medium | `scope="col"/"row"` on every `<th>` | T3 (+ remaining `risk` `<th>`s in T4) |
| F10 | 1.3.1 (A) | Medium | `visually-hidden` label in the empty action `<th>` | T3 |
| F11 | 1.4.1, 4.1.2 (A) | Medium | `aria-current="page"` on the active alert filter | T3 |
| F12 | 1.3.1 (A), 2.4.6 (AA) | Medium | section titles `h5` → `h2 class="h5"` | T3 (+ remaining h4/h5 section titles in T4) |
| F13 | 1.3.1 (A) | Medium | `.eip-stack thead` kept in the DOM (`visually-hidden`, not `display:none`) on mobile | T5 |
| F14 | 1.4.11 (AA) | Medium | warning-meter fill → `#b8791f`, `--eip-border-strong` → `#8a94a6` (≥3:1) | T5 |
| F15 | 1.4.3 (AA) | Medium | `.eip-soon` uses `ink-2` on the border tint | T5 |
| F16 | 2.4.7 (2.1 AA) | Medium | focus ring solid 2 px `#2457b8` (≥3:1 indicator) | T5 |
| F18 | 3.3.1 (A) | Low | grade-sheet row error under its input + `aria-describedby` | T3 |

## 3. Automated guardrails — the zero-contrast-failure baseline

Three guards now fail `scripts/run_tests.sh sqlite` on regression (full rule list in `docs/A11Y_UI_CHECKLIST.md`, kept in sync):

- `dashboard/test_template_guards.py` — static markup lint: `<th>` needs `scope`; decorative `bi-*` icons need `aria-hidden`; `extends base.html` needs a `title` block; `<canvas>` needs `role`+`aria-label`.
- `dashboard/test_a11y_render.py` — rendered walk of all 6 demo roles: every control has an accessible name, every title is distinct, heading levels never skip, no duplicate `id`.
- `dashboard/test_contrast_tokens.py` — parses `eip.css :root`, asserts text ≥4.5:1 and graphic ≥3:1 with the WCAG formula. The `EXPECTED_FAILURES` list shipped in T4 was **removed in T5**; every pair now asserts natively → **zero contrast failures**.

The browser pass (`scripts/dev/page_audit.mjs` + axe-core) is dev-only and manual (owner decision 10.3); it is **not** wired into the suite.

## 4. Deferred items (with rationale)

| ID | SC | Sev | Why deferred | Tracking |
|---|---|---|---|---|
| F17 | 4.1.3 (AA) | Low | `role="status"` for non-error messages + `aria-live` on the alert count. Listed in the proposal's 0037c scope but the executed T5 batch covered colour tokens + the two charts only; the message-role change in `base.html`/`base_public.html` was not included. | `docs/pilot/PROGRESS.md` "FOUND"; not blocking the pilot |
| F19 | 1.3.1 (A) | Low | No `<caption>` on any table. Listed in the proposal's 0037a scope but consciously deferred: per-table orientation is polish across the heaviest tables (360 ×5, `/rules/` ×5, grade dashboard ×2) and is not needed for the zero-contrast-failure baseline or the guardrails. | `docs/pilot/PROGRESS.md` "FOUND"; not blocking the pilot |

## 5. Test evidence

- T3 sqlite: `Ran 1567 tests in 826.976s` / `OK (skipped=11)` / demo_intel `OK` → `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`.
- T3 pg: `Ran 1567 tests in 1560.797s` / `OK (skipped=1)` → `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)`.
- T4 sqlite: `Ran 1577 tests in 1033.034s` / `OK (skipped=11)` / demo_intel `OK` → `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`.
- T5 sqlite: `Ran 1577 tests in 1119.259s` / `OK (skipped=11)` / demo_intel `OK` → `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`.
- T5 pg: `Ran 1577 tests in 1719.222s` / `OK (skipped=1)` → `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)`.
- T6 final sanity check (this session): `scripts/run_tests.sh sqlite` → main `Ran 1577 tests in 1533.473s` / `OK (skipped=11)`; demo_intel `Ran 62 tests in 231.760s` / `OK`; `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`.

## 6. Truth labels

- `CURRENT`: F1–F16 and F18 resolved; the three guards active; zero contrast failures; sqlite + pg green (T3 and T5).
- `DEFERRED`: F17, F19.
- `NOT VERIFIED`: behaviour with a real screen reader; the dev-only browser/axe-core pass (manual, not run this session).

No real student data; no secret read; nothing pushed.

