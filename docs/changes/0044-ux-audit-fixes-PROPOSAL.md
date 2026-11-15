# 0044 — UX audit fixes F01 (percent) and F02 (do not present a fabricated prediction) — CHANGE PROPOSAL

Written 2026-11-15. **Level: L2** (user-visible behaviour of an AI-labelled block on the school admin's student page;
F02 is listed in the audit as an owner decision, `E2E_AUDIT_REPORT.md:501`). Per `docs/CHANGE_PROCESS.md`:
proposal → owner approval → implement → tests → report.
**Status: PROPOSED — nothing implemented yet.** Scope agreed in chat on 2026-11-15: F01 is a real fix; F02 keeps the
existing hard-coded vector and stops presenting it as a prediction.
Truth labels: `CURRENT` (verified in this working tree, evidence as `file:line`) · `TARGET` · `PROPOSED` · `DECISION
REQUIRED` · `DEFERRED` · `NOT VERIFIED`.

Read with: `E2E_AUDIT_REPORT.md` §4 F01/F02 (§8 roadmap, §10 governance notes) · `django_core/dashboard/views.py`
`student_detail_view` · `django_core/dashboard/templates/dashboard/student_detail.html` ·
`django_core/dashboard/test_e2e_user_flow.py` `PredictionJourneyTests` · `django_core/dashboard/templatetags/eip_ui.py` ·
`fastapi_core/main.py` `/predict/`.

Branch: `work/0044-ux-audit-fixes`, created from `work/e2e-audit` (= `main` + `3103fba`, the audit commit; the base was
chosen with the owner because `main` alone does not contain the audit tests or the report - `git cat-file -e
main:django_core/dashboard/test_e2e_user_flow.py` -> *fatal: Not a valid object name*).

---

## 1. Requirement

> Fix F01: display `risk_probability` as a percentage (×100, no decimals, Persian digits). Fix F02: stop presenting the
> hard-coded numbers as a real prediction; label the block «نمایشی / دادههای تکمیلی موجود نیست» (demo / supplemental
> data not available), keep the hard-coded logic, make sure the UI does not lie to the principal.

Both findings are **P1** ("fix before any pilot use", `E2E_AUDIT_REPORT.md:148`).

## 2. Current behaviour (`CURRENT`, with evidence)

### 2.1 F01 — the probability is 100× too small

| Fact | Evidence |
|---|---|
| The service returns a probability in 0..1. | `fastapi_core/main.py:167` `"risk_probability": round(risk_prob, 4)` |
| The page prints it with a `%` sign and no multiplication. | `student_detail.html:42` `{{ prediction.risk_probability\|floatformat:2 }}%` |
| Measured: 0.70 is rendered as `0.7%`; 0.04 as `0.04%`. | `E2E_AUDIT_REPORT.md:152-156` |

### 2.2 F02 — a fabricated vector presented as a prediction

| Fact | Evidence |
|---|---|
| Three features are constants in the view, with comments that say so. | `views.py:139` `avg_completion_rate = 0.8`; `views.py:145` `total_communications = 3`; `views.py:151` `completed_homework = 12` |
| `attendance_rate = 1 - absences/(days+1)` is `1.0` (perfect) for a student with no attendance rows. | `views.py:134-135` |
| The whole dict is sent to FastAPI and then **printed to the admin**. | `views.py:154-172`; `student_detail.html:51` `(دادههای ارسالشده به هوش مصنوعی: {{ input_data }})` |
| The block calls itself a prediction and colour-codes the risk. | `student_detail.html:40` «نتیجهی پیشبینی»; `:43-49` badges پرریسک/کمریسک |
| Two students with different histories produce the same vector; a second copy exists for the DRF API. | `E2E_AUDIT_REPORT.md:163-176`; `students/views.py:461-480` (F21, out of scope here) |
| The real-data target is what `test_29` asserts today. | `test_e2e_user_flow.py:479-491` |

### 2.3 Constraints found while inspecting (they shape §4)

1. **No Persian-digit output helper exists.** `eip_ui.py` has `jdate`, `mask_nid`, `status_badge`, `nav_link`,
   `empty_state` only (`templatetags/eip_ui.py:1,67-90`). The `_DIGITS`/`_DIGIT_MAP` tables elsewhere (`students/views.py:63`,
   `students/history_import.py:31`, `missions/rubric.py:8`, `schools/academic_years.py:15`) convert Persian→ASCII for
   **input**; nothing converts digits for **display**.
2. **The existing F01 test cannot pass unmodified.** `rendered_risk_percent` returns `float(match.group(1))`
   (`test_e2e_user_flow.py:136-139`). `\d` matches Persian digits, but `float('۷۰')` raises `ValueError`
   (verified on this machine). The helper must normalise Persian/Arabic-Indic digits before parsing. Also
   `0.7 * 100 == 70.00000000000001`, so `round()` is required to get "no decimals".
3. **`test_29` asserts the real-data TARGET, not a label.** It asserts the three constants are *not* sent
   (`test_e2e_user_flow.py:489-491`). Under the owner's decision (label it, keep the logic) it must stay an
   `expectedFailure`; the passing test must be a new/repurposed one that asserts the label.
4. **Three existing tests pin the dishonest strings** and must move with the change: `test_27` (`:461,463`), `test_32`
   (`:516,518`). `test_33` (error text, F19) is unaffected. `demo_intel/tests.py:392` asserts the AI button is absent in
   the demo — still true.
5. **The block is Admin-only and the demo hides it** (`student_detail.html:27-31`), so no parent/teacher/student view
   changes.

## 3. Desired behaviour (`TARGET`)

**F01.** 0.7 → `۷۰%`; 1.0 → `۱۰۰%`; 0 → `۰%`. Persian digits, whole numbers, no decimals. The conversion is a
presentation helper, not a business rule: the database and the FastAPI contract keep 0..1.

**F02.** The hard-coded vector, the `?predict=true` trigger, the 5 s timeout, the Admin gate and the error sentences stay
exactly as they are. What changes is the claim the page makes:

| Element | CURRENT | TARGET |
|---|---|---|
| Button (`:29`) | «🤖 پیشبینی وضعیت با هوش مصنوعی» | «🤖 نمایش آزمایشی وضعیت (دادههای تکمیلی موجود نیست)» |
| Heading (`:40`) | «🤖 نتیجهی پیشبینی» | «🤖 نتیجهی نمایشی» |
| Notice | — | «نمایشی / دادههای تکمیلی موجود نیست» + one sentence naming the three placeholder features and «این خروجی مبنای تصمیم نیست» |
| Probability (`:42`) | «احتمال ریسک: 0.70%» | «احتمال ریسک (نمایشی): ۷۰%» |
| Risk badge (`:43-49`) | «پرریسک» / «کمریسک» | «پرریسک (نمایشی)» / «کمریسک (نمایشی)» |
| Sent data (`:51`) | raw Python dict of 8 features | **removed**; replaced by the Persian sentence above |

The alert colour (`alert-warning`/`alert-success`) is kept: it reflects the model's own classification, and the text now
says what it is. The model's `message` is still shown, prefixed «وضعیت (خروجی مدل آزمایشی):».

## 4. Affected modules (`MODULE_MAP`)

| Module | File | Change |
|---|---|---|
| Design system / presentation | `dashboard/templatetags/eip_ui.py` | + `fa_digits`, + `fa_percent` (no data access; the module docstring already limits it to presentation) |
| Dashboard | `dashboard/templates/dashboard/student_detail.html` | F01 + F02 markup and copy |
| Dashboard | `dashboard/views.py` | only the now-unused `'input_data'` context key (`:191`) is dropped; the vector and the call are untouched |
| Tests | `dashboard/test_e2e_user_flow.py` | helper + `test_27`, `test_28`, `test_29`, new `test_29b`, `test_32` |

## 5. Data impact

None. No model, no migration, no data migration. The hard-coded features stay hard-coded (owner decision). `Homework` and
`TeacherParentCommunication` are **not** read (they exist and are migrated — `dashboard/models.py:7-22`,
`dashboard/migrations/0001_initial.py` — but nothing writes them yet; see §14 F02b).

## 6. API impact

None. `fastapi_core/main.py` `/predict/` keeps returning `risk_probability` in 0..1. The DRF copy at
`students/views.py:461-520` is untouched (F21, `DEFERRED`).

## 7. Frontend impact

One template, using a filter from the module it already loads (`{% load eip_ui %}` at `:2`). No JS, no new dependency, no
Bootstrap change, RTL layout unchanged. Persian digits are the product's normal display convention.

## 8. AI impact

No model, prompt, provider or RAG change. The risk model remains `EXPERIMENTAL/PROTOTYPE` (`docs/AI_GOVERNANCE.md:25`).
The change makes the page agree with that status instead of contradicting it. Documentation of the outbound feature vector
(audit §10) is added to `AI_GOVERNANCE.md` — text only.

## 9. Security impact

No change to RBAC, object/school scope, PII handling or audit rows: `role_required(...)`, `visible_students`,
`audit.record(VIEW_DETAIL)` and the `ADMIN in roles_for(...)` prediction gate (`views.py:167`) are untouched. Removing
the rendered dict **reduces** what is shown to the admin (no internal payload on screen). No real student data involved.

## 10. Testing strategy

1. `fa_percent`/`fa_digits` are exercised end-to-end by `test_28` (0.7 → ۷۰) — no separate unit test file is added; the
   rendered page is the contract.
2. `rendered_risk_percent` normalises Persian/Arabic-Indic digits before `float()` (see §2.3.2).
3. `test_28` loses `@expectedFailure` and additionally asserts `۷۰` is present and `0.70%` is not.
4. `test_29` is repurposed: the block says «نمایشی / دادههای تکمیلی موجود نیست», does not say «نتیجهی پیشبینی»,
   does not print «دادههای ارسالشده به هوش مصنوعی» or `avg_completion_rate`, and **still calls FastAPI once**.
5. `test_29b` keeps the original three assertions (the constants must not be sent) as `@unittest.expectedFailure` — the
   TARGET is unmet and must stay visible, not be deleted.
6. `test_27` and `test_32` move to the new strings; the rest of the module must stay green.

Run: targeted module, then `scripts/run_tests.sh sqlite` (full, output to a file), then `pg` per the standing rule.
Expected: 1674 → 1675 tests, 6 → 5 expected failures (`test_29b` keeps one; `test_28` flips).

## 11. Documentation impact

- `docs/manuals/school-admin.md` — Persian «پروندهٔ ۳۶۰» section: what the demo block is, what it is **not**, who to ask.
- `docs/AI_GOVERNANCE.md` §Risk model — the feature vector sent to FastAPI, and that the page labels it a demo.
- `docs/CHANGE_GUIDE.md` — `Verified-at` note for 0044.
- `docs/MODULE_MAP.md` — the Dashboard row (`:13`) says "`tests.py` empty" and the model note says "no migrations"; both
  are stale and are corrected while the row is being touched.
- `docs/changes/0044-ux-audit-fixes-REPORT.md` — after the tests run.
- `E2E_AUDIT_REPORT.md` is left as the snapshot it is; the report records the closure.

## 12. Customization impact

None. No threshold, school name, model id or branding is introduced. The wording is generic Persian UI copy.

## 13. Risks

| Risk | Mitigation |
|---|---|
| A principal still reads the number as a verdict | Banner + «(نمایشی)» on the number and on the badge + «مبنای تصمیم نیست» |
| Someone "fixes" F02 by deleting the block | The owner chose to keep the logic; `test_29` asserts the call still happens |
| The real-data requirement silently disappears | `test_29b` stays as `expectedFailure` |
| Rounding surprise (0.995 → 100 vs 99) | Whole-number rounding, stated; 0.995 is outside the realistic band |
| `fa_percent` receives a non-number | It returns `''` instead of raising, so a provider surprise cannot 500 the page |

## 14. Recommendation and decisions

**Recommendation: implement F01 + the F02 demo label as described; defer F02b, F04 and F21.**

| # | Item | State |
|---|---|---|
| **D1** | F02: real data vs demo label | **DECIDED by the owner (2026-11-15): demo label, keep the logic** |
| **D2** | Persian digits via a presentation filter in `eip_ui.py` (not a view-side string) | `PROPOSED` — one place, no data access, reusable |
| **D3** | `test_29` becomes the label test; the real-data target moves to `test_29b` (`expectedFailure`) | `PROPOSED` — it cannot be "passed" without inventing data |
| **D4** | Button label also changes (the lie starts at the button) | `PROPOSED` |
| **F02b** | Read real `Homework`/`TeacherParentCommunication` rows; fall back when a student has none | `DEFERRED` — nothing writes those tables yet, so every student would show the fallback |
| **F04** | `?predict=true` is a GET side effect | `DEFERRED` (P2, `E2E_AUDIT_REPORT.md:492`) |
| **F21** | Second unmetered copy in `students/views.py`, no `ai_guard.consume()` | `DEFERRED` (P2, `:490`) |
| **F19** | «کد 500» in the admin's page | `DEFERRED` |
| **Gap** | The outbound vector has no audit row beyond `view_detail` | `DEFERRED` to F21; documented in `AI_GOVERNANCE` now |

**Gate:** implementation starts only after the owner signs this record off. `NOT VERIFIED` until the tests are run.

---

# Tranche 2 — F11 (no way into the assistant), F12 (the legacy library dead end), F06 (no wait state)

Added 2026-11-15 on the same branch. **Level: L2** (navigation visible to four roles, removal of three routes and their
templates, a new user-visible form behaviour). The owner gave the instruction and the decisions in chat on 2026-11-15, so
this section records scope and decisions rather than asking for them:

> "Fix F11 … GradeLead, Teacher, and Counselor can also see and click the link to `/assistant/`. Fix F12: Remove or hide
> the legacy `/library/`, `/upload-document/`, and `/chat/` links and their templates. Route users strictly to
> `/assistant/documents/` as the single source of truth for documents. Fix F06 … disable the submit button upon click,
> show a simple loading spinner … Do NOT implement async polling or streaming; just UI feedback."

Truth labels as in the header of this document. Evidence below is `CURRENT` in this working tree.

## 17. Current behaviour (`CURRENT`)

| # | Fact | Evidence |
|---|---|---|
| F11 | `/assistant/` is open to Admin, GradeLead, Teacher and Counselor | `docqa/views.py:44` `role_required(*STAFF, module='advisor_ai')`; `test_10` passes for all four |
| F11 | the only menu entry is the SchoolAdmin's module loop | `dashboard/templates/dashboard/base.html:58` `{% if IS_SCHOOL_ADMIN %}{% for m in VISIBLE_MODULES %}` |
| F11 | measured: no link for the other three roles | `E2E_AUDIT_REPORT.md:262` `{'GradeLead': False, 'Teacher': False, 'Counselor': False}` |
| F12 | `/library/` is live for the admin and forwards to a route that is off for every role | `dashboard/urls.py:16-17`; `dashboard/views.py:234-304`; `test_37` |
| F12 | `/chat/` is 403 for every role but still ships a view and a template | `dashboard/views.py:200` `role_required()` with an empty role set; `templates/dashboard/chat.html` |
| F12 | the admin's menu advertises both as «به‌زودی» (coming soon) while the real assistant is elsewhere | `base.html:70-73`; `test_trials.py:81` counts exactly 2 such stubs |
| F06 | the ask form is a bare POST with no feedback | `docqa/templates/docqa/home.html:7-11`; worst case 3 s + 65 s (`E2E_AUDIT_REPORT.md:207-215`) |


## 18. What this tranche changes (`PROPOSED` → implemented below)

1. **F11** — `base.html` renders one entry, `دستیار اسناد مدرسه` → `docqa:home`, for GradeLead / Teacher / Counselor, when
   `AI_FEATURES_ON` **and** `'advisor_ai' in ENABLED_MODULES`. `AI_FEATURES_ON` is added to `dashboard/context_processors.py`
   from `settings.ENABLE_AI_FEATURES`, because the view also has `require_pilot_flag('ENABLE_AI_FEATURES')`
   (`docqa/views.py:48`): a link that opens a 403 is the same class of defect as F12. The SchoolAdmin keeps the existing
   `VISIBLE_MODULES` entry; it is not duplicated (that would break the one-link-per-page rule in `dashboard/test_menu.py`).
2. **F12** — `dashboard/urls.py` loses `chat/`, `library/`, `upload-document/`, `delete-document/`; `dashboard/views.py`
   loses `chat_view`, `library_view`, `upload_document_view`, `delete_document_view`, `AI_UPLOAD_TIMEOUT` and the now
   unused `AI_TIMED_OUT`; `templates/dashboard/chat.html` and `templates/dashboard/library.html` are deleted; the two
   «به‌زودی» stubs are replaced by the real entry above. **No redirect**: the single library `/assistant/documents/` is
   SchoolAdmin-only (`docqa/views.py:69`), so redirecting `/library/` there would turn a teacher's bookmark into a 403 —
   a plain 404 states the page no longer exists. `delete-document` is removed with its only caller (the library template).
3. **F06** — `docqa/home.html`: `id="ask-form"`, `id="ask-submit"`, `id="ask-wait"`; a vanilla script in
   `{% block scripts %}` disables the button on submit, shows a Bootstrap spinner and the sentence
   «در حال ارسال… ممکن است تا ۳۰ ثانیه طول بکشد.»; a second submit event is cancelled. No polling, no streaming, no
   fetch: the response is still the plain POST render. The 3 s / 65 s timeouts are **not** changed.
4. **Tests** — `test_12` loses `@expectedFailure` and gains the flag-off case; `test_37` moves from *characterising the
   dead end* to *asserting the dead end is gone* (404 for all four paths, `/assistant/documents/` 200 for the admin, no
   «به‌زودی» stub); `dashboard/tests.py` drops the four URL names from its permission matrices and deletes the classes
   that only exercised the removed route (`LegacyUploadTimeoutTests`, the library-token test, and the upload leg of
   `AIErrorLeakTests` — M-3 stays covered by the two prediction tests); `test_trials.py` expects 0 stubs instead of 2; a
   new test in `docqa/tests.py` asserts the wait state (ids, the sentence, `disabled = true`).
5. **Docs** — `docs/SYSTEM_MAP.md` (routes), `docs/MODULE_MAP.md` (dashboard row), `docs/CHANGE_GUIDE.md` (`Verified-at`),
   `docs/AI_GOVERNANCE.md` (the wait sentence is a hint, not a guarantee), and the four role manuals that gain or lose a
   menu entry.

## 19. Decisions recorded

| # | Item | State |
|---|---|---|
| **D5** | F12 = **remove** the routes, views and templates (not hide behind a flag) | **DECIDED by the owner (2026-11-15)**; what the removal gives up is written below |
| **D6** | `/delete-document/` goes with them | **DECIDED** — its only caller is the deleted template |
| **D7** | The F11 entry is gated on role + module + `ENABLE_AI_FEATURES` | `PROPOSED` — no dead links, no duplicate for the admin |
| **D8** | F06 is UI feedback only; the sentence says ~30 s while the true worst case is 68 s | **DECIDED** («Do NOT implement async polling or streaming») — recorded as a known limitation |
| **F13** | `library_view` swallows every exception | **CLOSED by removal** — the bare `except` went with the view |

**What the removal gives up:** the legacy route was the only place that accepted PDF/DOC (`views.py:270`) and the only
caller of FastAPI's `/upload-document/` and `/documents/parent/<id>`. Both are `disabled_in_phase1` for every role
(`E2E_AUDIT_REPORT.md:271`), so nothing that worked is being removed; a PDF path would have to come back through
`docqa.extract`, which accepts txt/md/docx only.
