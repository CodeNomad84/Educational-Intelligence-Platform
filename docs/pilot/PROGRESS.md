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

## FOUND (not fixed, out of T3 scope)
- `risk/templates/risk/rules_index.html` had a broken `{% block title %}` block plus a full
  duplicated "اجرای قواعد"/"کیفیت قواعد" section — fixed as part of F4/F12 (same file was in scope).
- F19 (table `<caption>`) not yet added (Low; deferred to 0037b follow-up).

