# A11y & UI checklist (dashboard)

The rules the 0037 audit turned into automated guards. Anything here is checked by the tests; if a
rule is violated, `scripts/run_tests.sh sqlite` fails. Keep this list and the tests in sync.

## Markup (0037b lint — `dashboard/test_template_guards.py`)

1. Every `<th>` has `scope="col"` or `scope="row"` (F9). An empty action header gets a
   `visually-hidden` label (F10).
2. Every decorative Bootstrap icon `<i class="bi …">` has `aria-hidden="true"` (F8). An icon that is
   the only content of a control needs the control to carry a name (`aria-label`/text).
3. Every `<canvas>` has `role="img"` and an `aria-label` (F5).
4. Every template that `{% extends 'dashboard/base.html' %}` defines `{% block title %}` (F4).

## Rendered (0037b — `dashboard/test_a11y_render.py`)

- Every form control has an accessible name (label `for`, wrapping label, `aria-label`,
  `aria-labelledby`, `title`, or button text) — F1.
- Every `<title>` differs from the bare product name — F4.
- Heading levels never skip more than one level down the page — F12 (section titles are
  `h2 class="h5"`, not `h5`).
- No duplicate `id` on a page.

## Colour / contrast (0037b–0037c — `dashboard/test_contrast_tokens.py`)

- Text pairs are ≥ 4.5:1; non-text (graphic) pairs are ≥ 3:1. The temporary `EXPECTED_FAILURES`
  list shipped in 0037b was removed in 0037c; every pair now asserts natively, so a contrast
  regression fails the suite.

## Forms (0037a)

- Hand-written Django forms use `for="{{ field.id_for_label }}"` and the shared error include
  `dashboard/_form_errors.html` (which gives each error a real `id` + `role="alert"`).

## Deferred (not yet guarded)

- F17 — `role="status"` for non-error messages + `aria-live` on the alert count.
- F19 — table `<caption>`.
Both are Low severity; tracked in `docs/changes/0037-ux-audit-REPORT.md` §4.

## When you add a new page

Run the three checks before you commit; they are the fastest way to keep the pilot pages accessible.
The full automated browser pass (`scripts/dev/page_audit.mjs` + axe-core) is dev-only and manual.
