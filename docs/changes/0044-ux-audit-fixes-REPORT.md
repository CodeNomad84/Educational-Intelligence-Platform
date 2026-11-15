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

`docs/manuals/school-admin.md` (the only role whose view changed in tranche 1 — F01/F02). Tranche 2 (F11/F12/F06) also
changed what teacher, grade-lead and counselor see; see §21.

## 16. Migration required?


---

# Tranche 2 — F11 (nav entry), F12 (legacy pages removed), F06 (wait state)

Implemented 2026-11-15 on the same branch under the owner's instruction (recorded verbatim in the proposal, §18). Code
level: L2. Nothing below was run against PostgreSQL in this tranche; the missing pg leg is the same gap recorded in §8.

## 17. What changed

| File | Change |
|---|---|
| `dashboard/templates/dashboard/base.html` | the two «به‌زودی» stubs are gone; one `دستیار اسناد مدرسه` → `/assistant/` entry for GradeLead/Teacher/Counselor |
| `dashboard/context_processors.py` | new `AI_FEATURES_ON` (from `settings.ENABLE_AI_FEATURES`), so the entry follows the view's own flag |
| `dashboard/urls.py` | `chat/`, `library/`, `upload-document/`, `delete-document/` removed |
| `dashboard/views.py` | `chat_view`, `library_view`, `upload_document_view`, `delete_document_view`, `AI_UPLOAD_TIMEOUT`, `AI_TIMED_OUT` removed (the bare `except` of F13 went with them) |
| `dashboard/templates/dashboard/{chat,library}.html` | deleted (`git rm`) |
| `docqa/templates/docqa/home.html` | `id="ask-form"/"ask-submit"/"ask-wait"`, a Bootstrap spinner, «در حال ارسال… ممکن است تا ۳۰ ثانیه طول بکشد.» and a vanilla script that disables the button and cancels a second submit |
| `docs/pilot/PILOT_CONFIG.md` | the «Django `/chat/` is unchanged» line was false after this change: it now lists the four removed paths as 404 for every role |
| `docs/marketing/capabilities.md` | P4 pointed at the deleted `dashboard/views.py::chat_view`; it now points at `docqa/views.py` and says the chat page was removed. **Local only**: `docs/marketing/` is in `.gitignore`, so this edit is not part of the commit |
| `docs/SYSTEM_MAP.md` | the FastAPI `/chat/` line notes that the Django page which called it is gone |

## 18. Verification (commands actually run, outputs copied)

| Run | Result |
|---|---|
| `manage.py test docqa dashboard.tests dashboard.test_menu dashboard.test_trials dashboard.test_pilot_config` | **first attempt FAILED**: `Ran 86 tests in 30.533s` / `FAILED (failures=1)` — `test_trials` counted **1** «به‌زودی» instead of 0 |
| cause | my own edit: Django's `{# … #}` is single-line only, so a 5-line comment was rendered as literal nav text. Changed to `{% comment %}…{% endcomment %}` |
| same groups after the fix | `Ran 61 tests in 12.004s` / `OK` |
| `manage.py test docqa dashboard.test_trials dashboard.test_e2e_user_flow -v 2` | `Ran 80 tests in 62.175s` / `OK (expected failures=4)`; `[E2E] F11: a nav link to /assistant/ on each role home: {'GradeLead': True, 'Teacher': True, 'Counselor': True}`; `[E2E] F12: removed pages still advertised in the admin menu? []` |
| the F06 guard | `docqa.tests.PageAccessTests.test_the_ask_form_states_the_wait_and_blocks_a_second_submit` ran and passed in the 80-test run — it asserts the three ids, the spinner class, the sentence, `button.disabled = true`, and that the page contains **no** `fetch(` / `XMLHttpRequest` / `EventSource` |
| `manage.py test dashboard.test_menu` | `Ran 7 tests in 11.116s` / `OK` — includes the new dual-role regression `test_an_admin_who_is_also_a_teacher_gets_one_assistant_link` (a SchoolAdmin in the Teacher group sees exactly **one** `/assistant/` link). Its first version FAILED (`0 != 1`) because `test_counselor.make_user(..., 'SchoolAdmin', school)` deliberately does **not** create a `SchoolStaff` row, so the throw-away user had no school and no entitlements; the test now promotes the fixture admin instead |
| `scripts/run_tests.sh sqlite` (final, all edits in place) | `manage.py check`: `System check identified no issues (0 silenced).` · `makemigrations --check --dry-run`: `No changes detected` · `Ran 1675 tests in 1406.237s` / **`OK (skipped=11, expected failures=4)`** · `demo` settings: `Ran 62 tests in 170.398s` / **`OK`** · runner's own last line: `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`. Log: `/tmp/full_0044b_final.log` |

Expected failures 5 → 4 (`test_12` flipped from `@expectedFailure` to a passing test). Test count 1678 → **1675**, measured,
not estimated: six tests went with the legacy URLs (`test_chat_disabled…`, `test_library_admin_sends_token…`,
`test_the_ai_upload_timeout_is_bounded`, `test_a_timeout_gets_a_fixed_sentence`,
`test_a_document_upload_failure_does_not_render_the_exception_text`, and `test_anonymous_cannot_mutate`, whose whole body
POSTed to `/upload-document/` and `/delete-document/`) and three were added (`test_the_legacy_chat_and_library_routes_are_gone`,
`test_the_ask_form_states_the_wait_and_blocks_a_second_submit`,
`test_an_admin_who_is_also_a_teacher_gets_one_assistant_link`); `test_37` and `test_teacher_denied…` were rewritten in place.

## 19. Security & permissions review

- **Authorization is unchanged and server-side.** F11 only adds a link; `docqa/views.py` still gates `/assistant/` with
  `role_required(*STAFF, module='advisor_ai')` + `require_pilot_flag('ENABLE_AI_FEATURES')` (test_10/test_11 unchanged).
- **F12 removes endpoints, so the attack surface shrinks**: `/upload-document/` accepted a 10 MB unvalidated upload and
  forwarded it to FastAPI; it is a 404 now. The only addition is the nav link.
- **The removed views were admin-only or unreachable** (`role_required(ADMIN)` / `role_required()` with an empty set), so
  no role loses a capability it could actually use: every legacy capability ended in `disabled_in_phase1` (E2E F12).
- **No new data access**, no new query, no student data touched; the new context key is one settings boolean.
- **No inline-script risk introduced**: no CSP middleware exists in this repo (checked), the script is a `submit` listener
  with no network call, and the form still submits without JS (progressive enhancement).
- `AI_FEATURES_ON` is a display switch only. It is not, and must not become, an authorization check.

## 20. Known limitations

1. **D8:** the sentence says «تا ۳۰ ثانیه» while the true worst case is 68 s (3 s + 65 s). The timeout was not changed;
   the copy is a hint to stop re-clicking, and `docs/AI_GOVERNANCE.md` now says exactly that.
2. The ask is still one blocking POST (the streaming half of F06 is out of scope by decision); F14 (no answer cache) and
   F05 (cap charged for failed calls) are untouched, so a retry still costs a second unit.
3. **PDF/DOC upload died with the legacy page.** Nothing usable is lost (that route was disabled for every role), but a
   PDF import would need a new path through `docqa.extract`, which accepts txt/md/docx only.
4. Removed with the pages: `test_chat_disabled_for_every_role_and_never_calls_ai` (it asserted the unreachable chat view
   made no AI call) and `LegacyUploadTimeoutTests` (the M-1 bounded-timeout guard for a route that no longer exists). The
   M-3 error-leak guard still covers the prediction path; the docqa upload path keeps its own tests.
5. PostgreSQL: `NOT VERIFIED` for this tranche too — same registry/stale-image gap as §8; nothing here is
   database-engine specific (no model, no migration, no raw SQL).

## 21. User manuals updated (tranche 2)

`docs/manuals/school-admin.md` (the legacy «کتابخانه»/«چت» pages are gone; documents live in «دستیار اسناد» +
«مدیریت اسناد»; the wait sentence), `docs/manuals/teacher.md`, `docs/manuals/grade-lead.md`,
`docs/manuals/counselor.md` (the «دستیار اسناد مدرسه» entry appears only when the module and the AI switch are on, and
the button disables itself). `docs/manuals/parent.md` and `docs/manuals/student.md`: no change (never had access).

## 22. Owner acceptance (tranche 2)

pending — two pieces of copy are the owner's call: the menu label `دستیار اسناد مدرسه`, and the wait sentence
«در حال ارسال… ممکن است تا ۳۰ ثانیه طول بکشد.» (D8 notes the 30 s vs 68 s gap).

## 23. Migration required (tranche 2)

No. No model, no field, no data change; URLs, views and templates only.

---

# Tranche 3 — F05 (a failed call was charged), F17 (a missing secret was a 500), F03 (one AI address), F04 (a GET side effect)

Added 2026-11-15 on the same branch; scope and decisions are in the proposal's tranche-3 section (§20–§22 there).

## 24. What changed

| File | Change |
|---|---|
| `schools/ai_guard.py` | new `refund(school, module_key, on=None)`: gives one unit back, filtered by `count__gt=0` so it can never go negative, a no-op after the day rolled over; the module docstring now says the cap counts answers |
| `docqa/services.py` | `service_headers()` is wrapped: `ImproperlyConfigured` → excerpts + the ordinary offline sentence + audit `search:k{n}:unconfigured` + one log line naming the variable (F17); `ai_guard.refund()` when `_complete()` raises (F05); the `FASTAPI` literal is replaced by `service_url()` reading `settings.FASTAPI_BASE_URL` (F03); the offline sentence became one constant `OFFLINE_NOTICE` |
| `fastapi_core/llm_adapter.py` | `_refund_slot()`; `complete()` refunds in a `finally` unless an answer was returned — covers a 5xx, a timeout, a malformed answer and a `busy` refusal (F05); the module docstring says `LLM_DAILY_CAP` counts answered calls |
| `config/settings/base.py` | `FASTAPI_BASE_URL` (env `FASTAPI_BASE_URL`, default `http://fastapi:8001`, `.rstrip('/')`) |
| `dashboard/views.py` | the model runs only on `POST` with `action=predict` (SchoolAdmin only, as before); the URL comes from the setting |
| `students/views.py` | the DRF predict action builds its URL from the setting (the literal is gone) |
| `dashboard/templates/dashboard/student_detail.html` | `<form method="post">` + `{% csrf_token %}` + hidden `action=predict`; the button text is unchanged |
| tests | see §25 |
| docs | `docs/AI_GOVERNANCE.md` (accounting), `docs/ARCHITECTURE.md` (refund), `docs/CHANGE_GUIDE.md` (`Verified-at`), `docs/manuals/school-admin.md` (the trigger is a form; only delivered answers are counted; the misconfigured-server fallback) |

## 25. Verification (commands actually run, outputs copied)

| Run | Result |
|---|---|
| `manage.py test dashboard.tests dashboard.test_e2e_user_flow docqa students.test_access_c5a --settings=config.settings.test_sqlite` | `Ran 135 tests in 28.510s` / **`OK (expected failures=1)`** (the one left is F02b, DEFERRED). Printed: `[E2E] F05: quota consumed by a failed provider call = 0`, `[E2E] provider 500 -> quota_used=0`, `[E2E] F17: ask without SERVICE_JWT_SECRET -> status=200`, `[E2E] F04: two page views made predict_calls=1`. Log: `/tmp/t3_django.log` |
| `docker run --rm --network none -v "$PWD/fastapi_core:/app:ro" -w /app educational-intelligence-platform-fastapi:latest python -m unittest discover -s tests -t .` | `Ran 124 tests in 10.724s` / **`OK (skipped=32)`** — the suite has no expected failure left. Log: `/tmp/t3_fastapi.log` |
| `scripts/run_tests.sh sqlite` (all edits in place) | `manage.py check`: `System check identified no issues (0 silenced).` · `makemigrations --check --dry-run`: `No changes detected` · `Ran 1676 tests in 989.083s` / **`OK (skipped=11, expected failures=1)`** · demo settings: `Ran 62 tests in 176.731s` / **`OK`** · runner's last line: `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)`. Log: `/tmp/full_0044c_final.log` |

Expected failures 4 → **1**: `test_21` (F05), `test_30` (F04) and `test_39` (F17) now pass; the only one left is `test_29b`,
the DEFERRED F02b. The FastAPI suite's only expected failure (`test_16`) is gone too. Test count 1675 → **1676**, measured:
one test was added (`FastApiBaseUrlTests.test_the_prediction_posts_to_the_configured_base_url`); four others were renamed
and rewritten in place (`test_teacher_predicting…`, `test_parent_cannot_trigger…`, `test_31_…`, `test_39_…` naming).
PostgreSQL: `NOT VERIFIED` (the same carry-over as tranche 1 — the registry is still unreachable); nothing in this tranche
is engine-specific (one setting, no model, no raw SQL).

## 26. Known limitations (tranche 3)

1. **The cap now bounds delivered answers, not attempts.** A provider that keeps failing lets a school retry at zero quota
   cost; the attempt rate stays bounded elsewhere (the adapter's 3 concurrent calls per school, the docqa
   `QUESTIONS_PER_WINDOW` throttle). Recorded in D9 rather than hidden.
2. **D10:** POST-and-render, no redirect-after-post and no result cache. A refresh *after* a submission still asks the
   browser to confirm a resubmission; the alternative (a per-student/day cache) stays the audit's TARGET.
3. **D11:** FastAPI still serves `/predict/` twice (`/predict/` and `/api/v1/predict/`). Removing the second is a breaking
   API change and was not part of the instruction; `DECISION REQUIRED` if the duplicate is to go.
4. **F17 is a fallback, not a deploy check.** Nothing refuses to start without `SERVICE_JWT_SECRET`; the audit's
   "and/or fail at startup" half stays open (the predict page and the ask page now degrade the same way).
5. **The DRF action `GET /api/students/<id>/predict/` is unchanged** (F04 was scoped to the HTML page). It is still a GET
   with an inference side effect, so an API client that polls it pays per call; turning it into a POST is a breaking API
   change — `DECISION REQUIRED`.

## 27. Security & permissions review (tranche 3)

- **F04:** the model is reachable only by a POST that carries a CSRF token (Django's `CsrfViewMiddleware` is on for the
  page), and only for a SchoolAdmin: the role check that was on the GET branch is unchanged. A GET no longer performs any
  outbound request, so a prefetch, a bookmark or the back button cannot spend a call.
- **F05:** `refund()` can never go below zero and is scoped to one school/day/module; the caller cannot ask for a refund,
  only a failed provider call produces one. No new data access, no new query beyond the same `AICallUsage` row.
- **F17:** the fallback carries no exception detail to the page; the audit row holds a fixed code, the log line names the
  variable but never a value.
- **F03:** `FASTAPI_BASE_URL` is operator configuration (environment), not request data; the signed service token still
  goes only to the configured internal address, and `fastapi_core/tests/test_exposure.py` now fails if a caller
  reintroduces a literal host or the setting disappears.
- No student data is sent anywhere new; the two AI prompts are unchanged.

## 28. User manuals updated (tranche 3)

`docs/manuals/school-admin.md` only: the demo button is a form (one submission = one request, a failed call is given
back, a refresh does not re-run the model) and the assistant falls back to the excerpts when the server has no service
key. No other role has the prediction button or the assistant's quota.

## 29. Owner acceptance (tranche 3)

Scope and decisions were given in chat on 2026-11-15 ("Fix F05 … Fix F17 … Fix F03 & F04"), so this tranche introduces no
new user-visible copy to approve: the button label, the demo sentences and the offline sentence are unchanged (D12). Two
items stay with the owner as `DECISION REQUIRED`, not as acceptance blockers: **D11** (drop FastAPI's duplicate
`/api/v1/predict/`) and the DRF `GET …/predict/` action (§26 item 5).

## 30. Migration required (tranche 3)

No. One new setting (`FASTAPI_BASE_URL`, default unchanged), no model, no field, no data change.
