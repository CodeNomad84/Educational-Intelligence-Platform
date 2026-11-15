# 0044 — E2E audit findings F01 + F02 on the student page (report), 2026-11-15

Proposal: [0044-ux-audit-fixes-PROPOSAL.md](0044-ux-audit-fixes-PROPOSAL.md) · Branch `work/0044-ux-audit-fixes`
(from `work/e2e-audit` = `main` + `3103fba`) · Owner decisions D1–D4 (2026-11-15): demo label, keep the hard-coded
logic, presentation filter in `eip_ui.py`, rename the button too.

**Level L2.** No `students/access.py`, entitlement, audit-rule, schema, URL, permission or provider change; no migration,
no new endpoint, no new dependency, no FastAPI change.

## 1. What changed

| # | Finding | WHY | WHAT / WHERE | HOW |
|---|---|---|---|---|
| F01 | risk probability 100× too small (P1) | the service returns 0..1 and the page added a `%` sign, so a 70 % risk was shown as `0.7%` — the number the principal acts on | `dashboard/templates/dashboard/student_detail.html:45`; new filters in `dashboard/templatetags/eip_ui.py` | `{{ prediction.risk_probability\|fa_percent }}` → `fa_percent` = `round(float(p) * 100)` in Persian digits (`round()` is required: `0.7*100 == 70.00000000000001`); non-numeric input renders `''` instead of raising |
| F02 | a hard-coded vector presented as a real prediction (P1) | three of the eight features are constants (`views.py`: `0.8`, `3`, `12`) and the block called itself «نتیجه‌ی پیش‌بینی» and printed the raw dict | `student_detail.html:29,40-52`; `dashboard/views.py:152-155` (comment only), `:195` (context key removed) | the block is now «🤖 نتیجه‌ی نمایشی» with a bold «نمایشی / داده‌های تکمیلی موجود نیست», a sentence naming the three placeholder features and «این خروجی مبنای تصمیم نیست»; «احتمال ریسک (نمایشی)» و badges «پرریسک/کم‌ریسک (نمایشی)»; the button is «🤖 نمایش آزمایشی وضعیت (داده‌های تکمیلی موجود نیست)»; the raw `(داده‌های ارسال‌شده به هوش مصنوعی: {{ input_data }})` line is deleted. The outbound vector, the URL, the 5 s timeout, the admin gate and the audit call are untouched |

RISKS (as reviewed in proposal §13): a principal can still read the number as a verdict — mitigated by the banner, the
«(نمایشی)» markers and the explicit sentence; someone may "fix" F02 by deleting the block — the passing `test_29` asserts
the call still happens, and `test_29b` keeps the real-data target visible as an expected failure; `fa_percent` on a
non-number gives `''`, so a provider surprise cannot 500 the page.

## 2. Files changed (`git diff --stat`)

```
 django_core/dashboard/templates/dashboard/student_detail.html | 19 ++++---
 django_core/dashboard/templatetags/eip_ui.py                  | 26 ++++++++-
 django_core/dashboard/test_e2e_user_flow.py                   | 65 ++++++++++++++++++-------
 django_core/dashboard/tests.py                                | 31 ++++++++++
 django_core/dashboard/views.py                                |  7 ++-
 django_core/demo_intel/tests.py                               |  2 +-
 docs/AI_GOVERNANCE.md                                         |  1 +
 docs/CHANGE_GUIDE.md                                          |  2 +-
 docs/MODULE_MAP.md                                            |  4 ++--
 docs/manuals/school-admin.md                                  |  1 +
```
(plus this report, `docs/changes/0044-ux-audit-fixes-REPORT.md`, new — `11 files changed, 287 insertions(+), 37 deletions(-)`
from `git show --stat HEAD`.)

## 3. Models / migrations

None. `dashboard/models.py` (`Homework`, `TeacherParentCommunication`) is read by nothing in this change — exactly why
F02's label is still needed (F02b below).

## 4. APIs

None. The DRF copy of the same placeholder vector (`students/views.py:497-518`, F21) is deliberately untouched; FastAPI is
unchanged.

## 5. Frontend

Server-rendered template only (ADR-0013). The AI block stays admin-only (`can_predict`) and stays hidden in the demo
(`DEMO_MODE`); no parent/teacher/student view changes. `demo_intel/tests.py` now asserts the **new** label is absent in
the demo, so that guard is not vacuous after the rename.

## 6. AI

`CURRENT`: still one `POST` to `/predict/` per admin click, still metered by `ai_guard.consume()`, still the same eight
features, same model/version, same 5 s timeout and the same single `view_detail` audit row. Only the *presentation*
changed. `TARGET` / `DEFERRED`: real features (F02b), an audit row for the outbound vector (F21).

## 7. Tests added / changed

| File | Change |
|---|---|
| `dashboard/tests.py` | new `PersianDigitFilterTests` (3 tests): `fa_digits` converts ASCII→Persian only and is idempotent; `fa_percent` maps `0.7→۷۰`, `1.0→۱۰۰`, `0→۰`, `0.04→۴`, absorbs float noise and rounds; a non-number gives `''` |
| `dashboard/test_e2e_user_flow.py` | `rendered_risk_percent` normalises Persian digits before `float()` (it used to raise on `۷۰`) and tolerates the new «(نمایشی)» suffix; `test_28` (F01) is no longer `expectedFailure` and also asserts `۷۰%` is present and `0.70%` is gone; `test_29` became the passing demo-label test (label + no «پیش‌بینی» + no raw dict + still exactly one call); the real-data target moved verbatim to `test_29b` (`expectedFailure`); `test_27` and `test_32` moved to the new label |
| `demo_intel/tests.py` | the demo guard follows the renamed button label |

## 8. Tests executed (real output, not a claim)

Targeted runs first (SQLite, `config.settings.test_sqlite`):

```
manage.py test dashboard.test_e2e_user_flow
Ran 40 tests in 9.329s
OK (expected failures=5)

manage.py test dashboard.tests dashboard.test_e2e_user_flow
Ran 77 tests in 18.365s
OK (expected failures=5)
```

The F01 line from the rendered page inside that run: `[E2E] F01: model probability 0.70 is rendered as 70.0%`
(previously `0.7`); the F02 line: `[E2E] F02: labelled as a demo; features still sent: {... 'total_communications': 3,
'completed_homework': 12}` — the vector is knowingly unchanged, as decided.

Full suite, `scripts/run_tests.sh sqlite > /tmp/0044_sqlite.log 2>&1`:

```
[config.settings.development] manage.py check          → System check identified no issues (0 silenced).
[config.settings.development] manage.py makemigrations --check --dry-run
[config.settings.test_sqlite] manage.py test students dashboard schools vocabulary missions exams risk interventions docqa
Ran 1678 tests in 1031.226s
OK (skipped=11, expected failures=5)
[config.settings.demo] manage.py test demo_intel
Ran 62 tests in 184.961s
OK
ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)
EXIT=0
```

Count: the audit base had 1674 tests; this branch has 1678 (+3 `PersianDigitFilterTests`, +1 `test_29b`) and the expected
failures drop from 6 to 5 — F01 and F02 left the expected-failure list, `test_29b` (F02b) entered it. `(skipped=11)` and
the demo seed warning are pre-existing and unrelated.

PostgreSQL leg — `scripts/run_tests.sh pg`, **NOT VERIFIED (the leg did not finish)**:

```
>> building eip-test-django:local from django_core/Dockerfile and requirements.txt
ERROR: failed to build: ... docker.io/library/python:3.10-slim: 403 Forbidden     (registry unreachable)
>> WARNING: ... ALLOW_STALE_IMAGE=1, so the existing local image is used. Its dependencies may NOT match
   requirements.txt: do not trust this run as a dependency check.
>> [PostgreSQL 16 container] manage.py check                      → System check identified no issues (0 silenced).
>> [PostgreSQL 16 container] manage.py makemigrations --check --dry-run → No changes detected
>> [PostgreSQL 16 container] manage.py test students dashboard schools ... docqa
Found 1678 test(s).   ... 648 tests passed, no FAIL/ERROR line ...
[E2E] student_detail status=200 queries=58 model_calls=58 server_ms=316
.................EXIT=137          (killed by me after ~11 minutes of a stalled test phase)
```

The first attempt exited 3 without starting anything (the image could not be built because the Docker registry answered
403). The second attempt reused the local `eip-test-django:local` through the script's documented `ALLOW_STALE_IMAGE=1`
path: PG `check` and `makemigrations --check` were clean and 648 of 1678 tests passed with no failure, then the run
stalled. Diagnosis, not a guess: the runner container was at 0 % CPU with only its Postgres socket open, blocked in
`poll()`, while the server sat in `idle in transaction … ClientRead` for 183 s and only 8 threads were alive; killing the
container ended the script with `EXIT=137` and its `trap` removed the disposable container and network (no leftovers).
So this is an **infrastructure/prerequisite failure** (unreachable registry ⇒ stale image, whose psycopg may not match
`requirements.txt`) — **not** a failing assertion: zero `FAIL:`/`ERROR:` test lines. The PostgreSQL result for this change
is therefore `NOT VERIFIED`; the SQLite result above is `CURRENT`. To get it: rebuild the image once Docker Hub is
reachable and run `scripts/run_tests.sh pg` again.

## 9. Documentation updated

- `docs/AI_GOVERNANCE.md` §Risk model — F01/F02 `CURRENT`, F02b and F21 still open, the label must stay until both close.
- `docs/manuals/school-admin.md` §"Look at one student" — what the demo block means, that it is not a basis for a
  decision, that `۷۰%` is a 70 % risk, and that each click spends one AI call.
- `docs/CHANGE_GUIDE.md` — Verified-at line for 0044.
- `docs/MODULE_MAP.md` — dashboard row (adds `templatetags/eip_ui.py`, `migration 0001`, the three test modules) and the
  students row (`tests.py` is not empty). Both cells were stale before this change: `dashboard/models.py` already had
  `Homework`/`TeacherParentCommunication` with migration `0001`, `dashboard/tests.py` is 400 lines and `students/tests.py`
  331.
- **Deliberately not updated:** `docs/manuals/{parent,teacher,counselor}.md` (their views did not change),
  `E2E_AUDIT_REPORT.md` (the audit's own record; F01/F02 status is reported here), `docs/ROADMAP.md` (no scope change).

## 10. Security & permissions review

- Access is unchanged: the block is still `can_predict`-gated to `ADMIN`, the demo still hides it, `students/access.py` is
  untouched, no entitlement or audit rule changed.
- The change **removes** data from the page (the raw feature dict); no new personal data is exposed and the new code logs
  no student data.
- `fa_percent`/`fa_digits` are pure presentation: no model access, no `mark_safe`, so Django escaping is intact.

## 11. Self-review

- **Correctness:** 0.7 → `۷۰%` (verified on a real rendered page — `[E2E] F01: model probability 0.70 is rendered as
  70.0%`); 1.0 → `۱۰۰%`; 0 → `۰%`; the digit form matches the rest of the UI.
- **Architecture:** the conversion lives in the design-system filter module, not in the view; the view keeps building the
  same vector and the same context minus the now-unused `input_data` key.
- **Data/performance:** no query added or removed; the student page's query count is unchanged in the E2E timing prints
  (`student_detail queries=58`).
- **Maintainability:** the label text is in one template block with an `{# F02 ... #}` comment; the view carries a comment
  tying the three constants to the label.
- **AI safety:** the page no longer claims a prediction and no longer asserts the features are real; the unmet target is
  kept as a visible expected failure rather than deleted.

## 12. Known limitations

1. The three placeholder features are still sent (D1) — the model output is still meaningless for a real student, now
   honestly labelled.
2. `test_29b` is an expected failure by design, so "tests pass" here means `OK (expected failures=5)`, not zero expected
   failures.
3. `?predict=true` remains a GET side effect (F04) and the DRF copy remains unmetered (F21) — both out of scope.
4. The PostgreSQL leg is `NOT VERIFIED` for this change: the test image could not be rebuilt (registry 403) and the stale
   image ran 648/1678 tests without a failure before hanging (see §8). Nothing in this change is database-engine
   specific — no model, no migration, no raw SQL — but the missing pg run is a real gap, not a formality.

## 13. Remaining TODOs

- F02b: read real `Homework`/`TeacherParentCommunication` rows (both tables exist and are migrated) and fall back only
  when a student has none; then delete the label and flip `test_29`/`test_29b`.
- F04: make the prediction a POST (or a button-driven fetch) so a refresh or prefetch cannot spend quota.
- F21: route the DRF `predict`/`features` endpoints through the same guard and audit as the page.
- F19: replace «خطا در سرویس هوش مصنوعی (کد 500).» with a sentence an admin can act on.

## 14. Owner acceptance

pending — the proposal record was signed off as the basis for implementation; final acceptance of the delivered label
text is the owner's call.

## 15. User manuals updated

`docs/manuals/school-admin.md` (the only role whose view changed). Parent/teacher/counselor manuals: no change needed.

## 16. Migration required?

No.
