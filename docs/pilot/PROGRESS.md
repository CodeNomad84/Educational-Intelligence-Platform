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

## FOUND (not fixed, out of scope)
- F17 (`role="status"` for non-error messages + `aria-live` on the alert count) not done — not in the
  T5 scope list. F19 (table `<caption>`) still deferred. `risk/rules_index.html` title/duplicate was
  fixed in T3.




