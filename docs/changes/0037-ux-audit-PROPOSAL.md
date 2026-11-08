# 0037 — Persian/RTL dashboard: UX, accessibility (WCAG 2.1 AA) and simplicity audit (CHANGE PROPOSAL — read-only audit; nothing is implemented)

Level: L2 · Status: DRAFT (waiting for your approval) · Date: 2026-11-07 · Branch `work/ux-audit` @ `a48c6a1` (from `phase-1/boot-security`)

This file audits the existing dashboard. It changes no code, no data, no permission and no audit rule. Every number is **CURRENT** and came from a command whose output is quoted in the tables and in Appendix A. Proposed work is marked **TARGET**. Nothing is claimed as fixed, and no test is claimed to pass.

---

## 0. Cross-walk to `docs/templates/CHANGE_PROPOSAL.md`

This is an audit, so the template's 14 items map onto it like this — nothing is missing, it is just ordered by evidence rather than by template.

| Template item | Where it is answered here |
|---|---|
| 1 **Requirement** | Audit the existing Persian/RTL dashboard for UX, WCAG 2.1 AA and simplicity, read-only, and propose (not perform) the fixes. Owner's request this session. |
| 2 **Current behavior** | §1 (how it was measured), §2 (per-role task list), §3 (top-10 flows), §4.2 (F1–F19), §5 (S1–S7), §6, Appendix A (raw output). |
| 3 **Desired behavior** | §6 "Proposed fix" column, §7 the three batches, §8 the three checks. |
| 4 **Affected modules** | `dashboard` only (templates, `static/dashboard/css/eip.css`, `static/dashboard/js/eip-jdate.js`, `templatetags/eip_ui.py`, `test_template_guards.py`); `scripts/dev/page_audit.mjs`. `missions` is noted as out of scope in §12. |
| 5 **Data impact** | none — §9. No model, no migration, no provenance change. |
| 6 **API impact** | none — no endpoint, no schema, no FastAPI contract is touched. |
| 7 **Frontend impact** | the substance of §6/§7: markup, tokens, and one 1-line `<title>` change. No SPA, no framework (ADR-0013). |
| 8 **AI impact** | none. Nothing here changes extraction, matching, prompts or rules; the "not a diagnosis / not a decision" copy is explicitly preserved (§2 last paragraph). |
| 9 **Security impact** | neutral-to-positive — §9 row "Security". `students/access.py`, entitlements and audit rules untouched. |
| 10 **Testing strategy** | §8: two static/render guards plus a contrast test, and per-bug tests inside 0037a. Existing suite unaffected. |
| 11 **Documentation impact** | one new `docs/A11Y_UI_CHECKLIST.md` (0037b); this proposal; no README/MODULE_MAP change. |
| 12 **Customization impact** | the five colour values in 0037c become the design tokens; nothing becomes hard-coded that is not already. |
| 13 **Risks** | §11 "Risk" column; the one real risk is the global `--eip-muted` change (0037c). |
| 14 **Recommendation** | §7 (three batches, independent except b-after-a) + §10 (eight DECISION REQUIRED items) + §11 (≈4.5 days). |

---

## 1. How this was measured (and what is NOT verified)

**Read (static):** all 49 templates under `django_core/dashboard/templates/` (base, base_public, the six role homes, `loop/*`, `teacher/*`, `counselor/*`, `school/*`, `student_*`, `_empty`, `_behavior`, `_student_summary`), `dashboard/urls.py`, `templatetags/eip_ui.py`, `static/dashboard/css/eip.css`, `static/dashboard/js/eip-jdate.js`, plus `dashboard/test_template_guards.py` and `scripts/dev/page_audit.mjs`.

**Ran (read-only, against the synthetic demo data):** five probes under `DJANGO_SETTINGS_MODULE=config.settings.demo` (plus one set of static counts). They render pages through Django's own test client (`force_login` per demo role) and parse the HTML with `html.parser`. The only writes were Django session rows in the gitignored `demo_db.sqlite3`; no project file was touched.

| Probe | What it does | Result |
|---|---|---|
| **P1 role walk** | 6 demo roles (`demo_admin`, `demo_gradelead`, `demo_teacher`, `demo_counselor`, `demo_parent`, `demo_student`), breadth-first over same-origin GET links (cap 26 pages/role, depth ≤ 2) | 147 paths requested, **65 pages rendered and analysed**; the rest are 403 (correctly refused) or 302 role redirects |
| **P2 write screens** | the data-entry pages the walk cannot reach: teacher grade sheet ×2, alert-new, plan-new, strategies, class-new, student-add, report card | **9 more pages** (74 in total) |
| **P3 invalid POST** | posts an empty alert form and inspects what Django actually emits | `aria-describedby` points at an id that no element carries |
| **P4 contrast** | WCAG 2.1 relative-luminance formula over the 26 token pairs actually used in `eip.css` | **5 real failures**, 1 decorative exemption, 1 WCAG-2.2-only issue |
| **P5 navigation** | per-role count of sidebar links, sections and labels | 16/5 for the Admin down to 3/2 for the Parent |
| **C1 static counts** | per-pattern counts over the 49 templates | `8/2` labels, `160/0` table headers, `4/2` canvases, `34/5` icons |

**NOT VERIFIED (explicitly):**
- behaviour with a real screen reader (NVDA / VoiceOver / TalkBack) — no assistive technology in this environment. The findings are DOM-level facts plus the WCAG criterion each one breaks; the *user impact* wording is an informed reading of those facts, not an observed session.
- rendered pixels: contrast is computed from the CSS literals (exact for solid tokens, an approximation for the translucent focus ring).
- target sizes: 31 px for `.btn-sm` is Bootstrap 5.3's computed height, not a browser measurement.
- `scripts/dev/page_audit.mjs` was **not** run this session (no server up, no demo password in this environment); its proposed accessibility extension is in §8, not a claim.
- no usability session with a real teacher/counsellor/parent has ever happened for this product; the "top 10 flows" order is derived from screen/click counts and template structure, not from observed users.

**Per-role volume (CURRENT, P1):**

| Role | pages rendered | form controls | controls with no accessible name | icon elements rendered | icons without `aria-hidden` | sidebar links / sections |
|---|---|---|---|---|---|---|
| SchoolAdmin | 21 | 70 | **18** | 497 | 140 | 16 / 5 |
| GradeLead | 12 | 27 | 2 | 199 | 79 | 9 / 5 |
| Teacher | 11 | 7 | 0 | 156 | 57 | 8 / 4 |
| Counselor | 9 | 15 | **8** | 117 | 54 | 6 / 4 |
| Parent | 7 | 7 | 0 | 68 | 40 | 3 / 2 |
| Student | 5 | 7 | 0 | 56 | 26 | 5 / 3 |
| **total** | **65** | **133** | **28** | **1093** | **396 (36 %)** | — |

P2 adds 24 more controls of which **22 have no accessible name**.

---

## 2. What each role actually does today (task list, CURRENT)

**Subject Teacher (daily, ~30 students per class).** `کلاسهای من` → one row per class → `ثبت و مشاهدهٔ نمرات` → grade sheet → type up to 30 marks → `ثبت نمرات`. Two screens, which is *good*. The sheet is one form with `exam_type`, `date` and one unlabeled input per student; the same page also lists today's marks, each with its own `حذف` POST form.

**Grade Lead (daily).** `داشبورد پایه` (four stat cards, two charts, two tables) → `هشدارها` → inline accept/dismiss per row → `ایجاد برنامهٔ مداخله` → plan form → plan detail → follow-up form. The grade dashboard is the only screen that answers "who needs attention in my grade" in one place — a genuine strength.

**Counselor (daily).** `پروندههای ارجاعی` → case → close case; plus the same alert and plan loop as the Grade Lead.

**SchoolAdmin (weekly, setup-heavy).** Five jobs in five different places: (1) student list and 360 file, (2) staff and role assignment (`مدیریت مدرسه → نقشهای کارکنان`, 27 checkboxes on one page), (3) bulk account creation from Excel (4 steps), (4) password reset, (5) the platform-operator module overview. The sidebar has 16 entries in 5 sections; two of them lead to module screens that are locked or empty under the current licence.

**Parent (occasional).** `فرزندان من` → child → `کارنامه`. Three screens for the one thing a parent opens the product for.

**Student (occasional).** `صفحهٔ من` — one screen: own marks by year, teacher feedback, one link to the study assistant. Correctly small.

**Absent everywhere, and should stay absent:** no AI advice about a child, no score, no ranking, no automatic action, no e-mail or SMS. Every screen that shows a tier or an alert carries a sentence saying it is not a diagnosis. That principle is clear in the copy and this audit proposes nothing that weakens it.

---

## 3. The ten flows that cost the most (CURRENT)

"Screens" = full page loads, "clicks" = user activations. Counted from `dashboard/urls.py` (every state change is its own URL with its own confirm form) and from the links actually rendered on P1/P2.

| # | Flow | Role | Screens | Clicks | What is measured wrong |
|---|---|---|---|---|---|
| 1 | Enter marks for one class | Teacher | 3 | ~35 | all 30 score inputs have no label and no `scope` on the `نمره` column (`grades.html:14`); empty `<th></th>` for the delete column; 31 `btn-sm` |
| 2 | Turn a new alert into an intervention | Grade Lead, Counselor | 4 | 3 + reason/note | the dismiss form's `<select name="reason">` and `<input name="note">` are unnamed (`loop/alerts.html:23-24`); the active status filter is colour-only (`alerts.html:8`) |
| 3 | Record a plan follow-up | Grade Lead, Counselor | 3 | 3 | on `/interventions/2/` **6 controls are unnamed**: `followup_date`, `assessment`, `progress_note` have ids but their labels have no `for`; `outcome`, `note`, `owner` have neither (P1) |
| 4 | Find *why* a rule fires | SchoolAdmin | 3 | 3 | `/rules/` is the worst screen in the product: `h1→h5→h4→h6` skipping, 5 tables with 0 `scope`, 23 `btn-sm`, 2 unnamed number inputs |
| 5 | Read the child's report card | Parent | 3 | 2 | the parent's likeliest destination is the deepest page in their space (P1 depth 2: `/students/5/report-card/`) |
| 6 | Bulk-create accounts from Excel | SchoolAdmin | 4 | 4 | the file input has no label (`/school/accounts/`, 1 unnamed control) |
| 7 | Reset one password | SchoolAdmin | 3 | 4 | the search box is placeholder-only (`/school/resets/` `name="q"`) |
| 8 | Assign staff roles | SchoolAdmin | 2 | 27+ | 9 of 27 checkboxes are unnamed (`teacher`/`gradelead`/`counselor` repeated without `id` or wrapping label) |
| 9 | Understand a student | SchoolAdmin, GradeLead, Counselor, Parent | 2 | 2 | Student 360: `h1` then **five bare `h5`s**, 5 tables (one with 12 date columns), one of them (alerts+plans, `student_360.html:15`) has **no `<thead>` at all**, no in-page navigation. The parent's `/students/5/` skips `h1→h4` |
| 10 | Check who is at risk in a grade | Grade Lead | 1 | 1 | the two charts (`grade_dashboard.html:16-17`) have no `role`, no label and no text alternative; the numbers exist only inside `json_script` |

Two flows are already good and should not be touched: the teacher's two-screen route into the grade sheet, and the student's single `صفحهٔ من`.

---

## 4. Accessibility findings against WCAG 2.1 AA

Severity here = **Blocker** (a user group cannot complete the task), **High** (task completes only with repeated guessing / an A-level failure), **Medium** (an A/AA failure with a workaround, or friction), **Low** (polish). "Verified" = produced by a command in this session; nothing here was confirmed with a real screen reader.

### 4.1 What the codebase already gets right (do not regress these)

| Done well | Where |
|---|---|
| `<html dir="rtl" lang="fa">` on every page; `<main id="eip-main">`; a real skip link `پرش به محتوای اصلی` | `base.html:2,100,12` |
| The `eip_ui` template tags emit accessible icons: `nav_link`, `empty_state`, `panel` all render `aria-hidden="true"` on the `<i>` and mark the current page with `aria-current="page"` | `templatetags/eip_ui.py` |
| Search form on the student list: `role="search"`, `aria-label="جست‌وجو"` on the input, `visually-hidden` on the icon button | `student_list.html:9-11` |
| Grade sheet uses `form.exam_type.label_tag` (correct `for`/`id` pairing) | `teacher/grades.html:7-8` |
| Every audited page has `dir`/`lang` and no horizontal scroll (the existing harness already asserts this) | `scripts/dev/page_audit.mjs` |
| Tier/badge colours all pass 4.5:1 (5 of 5 badges), all alert variants pass (7.8–9.3:1), primary button 6.71:1 | P4 |
| Mobile: secondary columns are dropped with `d-none d-md-table-cell` and re-shown as a sub-line under the name instead of forcing horizontal scroll | `student_list.html:21` |

The design tokens are largely sound. The failures below are almost all **hand-written markup escaping the tag system**, plus five colour values.

### 4.2 Findings

| ID | SC | Finding | Evidence | Sev |
|---|---|---|---|---|
| **F1** | 3.3.2, 1.3.1 (A) | Form labels are not associated with their controls. **Root cause is one repeated idiom**: `<label class="form-label">{{ field.label }}</label>{{ field }}` — the label is a *sibling* of its input and has no `for`, so every page built this way is unnamed. | P1: **28 of 133** walked controls have no accessible name; P2: **22 of 24** on write screens. The idiom: `loop/alert_form.html:6`, `loop/plan_form.html:10`, `school/strategies.html:13` (and `missions/grid.html:23`, `missions/choices.html:10` repeat the error-div half of it outside the dashboard). Raw inputs with no label at all: `score_{{ student.pk }}` (`teacher/grades.html:14`), `reason`/`note` (`loop/alerts.html:23-24`), `followup_date`/`assessment`/`progress_note` (labels present, no `for`), `outcome`/`owner`, `q` (`school/resets.html`), `file` (`school/accounts.html`), 9 of 27 role checkboxes (`school/staff_roles.html`), `grade_scale_max`/`breaker_percent` (`rules.html`). | **High** |
| **F2** | 3.3.1, 4.1.2 (A) | On an invalid POST the error text is visually adjacent but programmatically unreachable: `aria-describedby="id_message_error"` points at an id that no element carries — because the error div is hand-written (`{% for e in field.errors %}<div class="text-danger small">`) without that id. | P3: the textarea renders `required aria-invalid="true" aria-describedby="id_message_error"`, while errors render as `<div class="text-danger small">این مقدار لازم است.</div>` with **no id** (`errorlist markup: []`). Same 4 templates as F1. | **High** |
| **F3** | 3.3.1, 4.1.3 (AA) | A failed submit announces nothing and moves focus nowhere: no error summary, no `role="alert"` on the error block, no focus move to the first invalid field — the page simply re-renders. | 0 `aria-live`, 0 `role="status"` in all 49 templates; errors are plain `text-danger` divs; P3 returned 200. | **High** |
| **F4** | 2.4.2 (A) | Every authenticated page has the same document title `پلتفرم هوشمند مدرسه`, although each template defines `{% block title %}` for its `<h1>`. Only the login page (`base_public`) sets a distinct one. | `base.html:6` is static; 49 templates define `{% block title %}` that never reaches `<head>`. | **High** |
| **F5** | 1.1.1 (A), 4.1.2 (A) | The two Grade-Lead charts are `<canvas>` with no `role`, no accessible name and no text alternative; their data exists only inside a `json_script` blob. | 4 canvases / 2 labelled / 0 with `role="img"` across templates; `grade_dashboard.html:16-17`. | **High** |
| **F6** | 1.3.1 (A) | Student 360's alerts+plans table is a 5-column data table with **no header row at all**; the trend table puts its `<th>`s in the body row and transposes axes without `scope`. | `student_360.html:14-19`, `:23-24`. | **High** |
| **F7** | 1.4.3 (AA) | `--eip-muted` fails on the two surfaces it is used on: **4.40:1** on `#f8fafc` and **4.26:1** on the page background `#f4f6fa` (needs 4.5). It is the colour of every caption and timestamp — and of the legal disclaimers ("این ارقام تصمیم نیستند…", "برچسب یا تشخیص نیست"). | P4 rows 5–6; e.g. `student_360.html:22,39`, `student_list.html:35`. | **High** |
| **F8** | 4.1.2 (A) | 396 of 1093 rendered icon elements (36 %) carry no `aria-hidden`, and several are the *only* content of their control, so those controls have no name. | P1 per-role counts; 34 hand-written `<i class="bi …">`, only 5 with `aria-hidden` (C1). Examples: `student_360.html:6` (printer), search buttons, row `×` buttons. | **High** |
| **F9** | 1.3.1 (A) | 160 `<th>` in the templates, **0** with `scope`. | C1; P1 `TH_NO_SCOPE` non-empty for 6 of 6 roles, e.g. `/rules/` five tables `[(8,0),(4,0),(7,0),(8,0),(4,0)]`. | **Medium** |
| **F10** | 1.3.1 (A) | Empty `<th></th>` action headers leave an unnamed column on 3 list screens. | `student_list.html:17`, `teacher/grades.html:10,25`, `teacher/home.html:5`. | **Medium** |
| **F11** | 1.4.1 (A), 4.1.2 (A) | The alert status filter conveys its active state by fill colour only (`btn-primary` vs `btn-outline-primary`, identical text: `جدید / پذیرفته‌شده / رد‌شده / همه`); no `aria-current`, no `aria-pressed`. | `loop/alerts.html:8`; sidebar chips *do* get `aria-current="page"` because they go through the tag — this one does not. | **Medium** |
| **F12** | 1.3.1 (A), 2.4.6 (AA) | Heading levels skip: `h1` → `h5` on most screens; `/rules/` runs `h1,h5,h5,h4,h6,h5`. | P1 `/interventions/2/` `H_SKIP=[(1,5)]`, `/rules/` `H_SKIP=[(1,5),(4,6)]`, and `student_360.html` uses five bare `h5`s as section titles. | **Medium** |
| **F13** | 1.3.1 (A) | At the mobile breakpoint the alerts table hides its header row (`thead{display:none}`) and substitutes CSS-generated labels (`td[data-label]::before{content:attr(data-label)}`), which assistive tech does not reliably expose as headers. | `eip.css:177-181`, `loop/alerts.html:9`. | **Medium** |
| **F14** | 1.4.11 (AA) | The warning meter fill is **1.94:1** against its track and the input border **1.46:1** against white — both under the 3:1 graphic/UI boundary. (Card border 1.14 is decorative and exempt.) | P4 rows 24, 26. | **Medium** |
| **F15** | 1.4.3 (AA) | The `eip-soon` "coming soon / locked" pill is **3.74:1** — the licence-locked module state is the hardest thing on the page to read. | P4 row 16; used on 2 sidebar entries plus module cards. | **Medium** |
| **F16** | 2.4.7 (AA, weakly) / 2.4.13 (2.2 only) | The focus ring is `#2457b8` at 45 % alpha → **2.12:1** on white, 2.07:1 on the page background. Visible, but not a 3:1 indicator. | P4 trailing note; `eip.css` `:focus-visible`. | **Medium** |
| **F17** | 4.1.3 (AA) | Success/info messages use `role="alert"` (assertive), so a "ذخیره شد" interrupts whatever is being read; and 0 elements use `aria-live`, so the in-page swaps (`?status=new` filter, inline accept) are silent. | `base.html:114`, `base_public.html:20`; C1 `aria-live=0`, `role=status` 0. | **Low** |
| **F18** | 3.3.1 (A) | Grade-sheet row validation writes its message into a `text-danger` cell in the *third* column, so the error is neither adjacent to its input nor linked to it. | `teacher/grades.html:14-15`. | **Low** |
| **F19** | 1.3.1 (A) | No table has a `<caption>`, so on a page carrying up to 5 tables there is no per-table orientation. | 0 captions in 49 templates (C1); `/rules/` and `/students/*/360/` each render 5 tables. | **Low** |

**Two claims I want to keep honest.** (a) F16 is *not* a WCAG **2.1** AA failure — 2.1 only requires the indicator to be visible (it is); the 3:1 number comes from 2.2 SC 2.4.13, and from 1.4.11 if you treat the ring as a UI component. (b) F13 is about reliability, not certainty: some browser/screen-reader pairs *do* read `::before` content, so the header row disappearing is the hard part and the pseudo-element label is a gamble.

Nothing in this section is a **Blocker** in the WCAG sense; F1–F8 are the ones that make a keyboard/screen-reader user guess, and they are all A-level.

**The cross-cutting cause.** These are not 19 unrelated bugs, they are one habit: the same widget is written three different ways depending on who wrote the page. The student search is a `role="search"` landmark with an `aria-label` (`student_list.html:9-11`); the staff search on the resets page is the identical widget with no role and no label (`school/resets.html:11`). Table cells carry `data-label` for the mobile card view, but no `scope` for the desktop table. A `label` is emitted by the template tag on some pages and hand-written *without* `for` on others. Fixing the three shapes once — one search partial, one field partial, one table partial — is what makes 0037a cheap and what makes 0037b worth having.

---

## 5. Simplicity and cognitive-load findings

| ID | Finding | Evidence | Effort |
|---|---|---|---|
| **S1** | The Admin sidebar is the product's biggest wall: **16 links in 5 sections**, and two of them (`آمار آزمون‌ها`, `دستیار مشاور هوشمند`) open module screens that are licence-locked or empty. The Teacher, by contrast, sees 8 and the Parent 3. | P5 sidebar counts: 16/5, 9/5, 8/4, 6/4, 3/2, 5/3. | M |
| **S2** | One module, three names: `آمار آزمون‌ها` (Admin), `آزمون‌های پایه` (Grade Lead), `آزمون‌ها (بانک پرسش)` (Teacher). A staff member explaining the product to a colleague cannot name the screen. | P5 label lists. | S |
| **S3** | Button density beats the data: `/students/` renders **83 `btn-sm`** (2 per row × ~40 rows), the grade sheet 31, `/rules/` 23, `/school/resets/` 20, `/school/staff-roles/` 17. On the student list every row has `مشاهده` **and** `پرونده ۳۶۰` although the row's own name is already a link to one of them. | P1 `BTN_SM`, C1. | S |
| **S4** | Destructive actions sit inline with data, one click, no confirm, and in one case directly under a warning that asks the user to be careful: `حذف` per row on the grade sheet, `بازنشانی رمز` per row on the resets page (the warning above it says "verify the requester's identity first"), and a dense row of `پذیرش`/`رد` per alert. A mis-click on a 31 px target in a 30-row table silently deletes a mark or resets a password. | `teacher/grades.html:29`, `school/resets.html:10-15`, `loop/alerts.html:9-26`. | S |
| **S5** | The 360 file is a single scroll with no in-page navigation: `h1` then five bare `h5` sections (`هشدارها و مداخلهها`, `روند`, `ارجاع`, `یادداشتها`, summary), 5 tables — one of them 12 date columns wide — and four top action buttons in four different styles (`btn-link`, `btn-outline-primary` ×2, `btn-outline-warning`, `btn-outline-secondary`). | P1 `/students/1/360/`: `h=[1,5,5,5,5,5]`, `th_no_scope=[(4,0),(3,0),(12,0),(4,0),(4,0)]`; `student_360.html:5-9`. | M |
| **S6** | Every state change is a fresh page load, so the back button becomes ambiguous ("did I save, or did I just go back?"): 6 role homes, 4-step account creation, and a confirm form for every status transition. | `urls.py`; P1 depth ≤ 2. | L (by design; do not "fix" with SPAs — ADR-0013) |
| **S7** | Numbers are mixed-script: `jdate` prints Persian-calendar dates with ASCII digits (`1405/08/17`) next to Persian words, and `floatformat` prints a Latin decimal point (`12.3`) inside RTL text. | `eip-jdate.js`, `student_360.html:24-26`. | S |

Two structural strengths worth keeping: (1) every role home answers its role's main question in **one** screen (nav depth to any task ≤ 2 for all six roles); (2) the disclaimers ("not a diagnosis", "not a decision") are attached to the data itself rather than buried in a help page.

---

## 6. Prioritised fix list (one row per finding, ordered by cost-to-the-user)

Effort: **S** ≤ half a day, **M** ≤ 2 days, **L** > 2 days. "Policy" = needs a product/governance decision from you before code (see §10).

| # | ID | Finding | Roles | Sev | Proposed fix | Effort | Policy |
|---|---|---|---|---|---|---|---|
| 1 | F1 | 50 controls with no accessible name (28 walked + 22 on write screens) | all | High | fix the one shared idiom — `for="{{ field.id_for_label }}"` in `alert_form.html`, `plan_form.html`, `strategies.html` (3 lines, covers most of the count) — then `aria-label`/`for` on the raw grids: grade sheet (`aria-label="نمرهٔ {{ r.student.last_name }}"`), dismiss form, follow-up form, resets search, accounts file, the 9 role checkboxes (a `visually-hidden` label naming person + role, since one `id` cannot serve repeated names), 2 rule numbers | M | no |
| 2 | F2 | `aria-describedby` dangles → errors unreachable | all | High | the error div is already hand-written in the same 3 templates: give it `id="{{ field.id_for_label }}_error"` (the id Django already points at) via one shared include | S | no |
| 3 | F3 | Failed POST is silent, focus stays put | all | High | add an error summary block at the top of the form (`role="alert"`, links to each bad field) and autofocus it; needs one shared include, no per-page work | S | no |
| 4 | F4 | Same `<title>` on all ~60 authenticated pages | all | High | `base.html`: `<title>{% block title %}…{% endblock %} — پلتفرم هوشمند مدرسه</title>`; every template already defines the block, so this is a 1-line change plus trimming long titles | S | no |
| 5 | F8 | 396 icon elements with no `aria-hidden`; icon-only buttons unnamed | all | High | `aria-hidden="true"` on decorative `<i>`, `visually-hidden` text where the icon is the label (the `nav_link` tag already does exactly this — reuse it) | S | no |
| 6 | F7 | `--eip-muted` 4.40 / 4.26 on the two surfaces it is used on | all | High | darken the token one step (`#6b7686` → `#5b6675`, gives ≈5.1 on page bg) or forbid `text-muted` on `--eip-surface-2`; the disclaimers must be the *most* legible text, not the dimmest | S | no |
| 7 | F5 | Two charts are unnamed canvases with no text alternative | GradeLead | High | give each canvas `role="img"` + `aria-label` carrying the summary sentence, and render the same numbers as a `<table class="visually-hidden">` from the existing `json_script` data | M | no |
| 8 | F6 | 360 alerts+plans table has no header row | Admin, GradeLead, Counselor, Parent | High | add `<thead>` + `<th scope="col">` (`نوع / دسته / وضعیت / تاریخ / اقدام`); same for the transposed trend table, or convert it to a real 2-column list | S | no |
| 9 | F9 | 160 `<th>`, 0 `scope` | all | Medium | add `scope="col"` (and `scope="row"` where the first cell is a name); mechanical, scriptable, then enforced by the lint in §8 | S | no |
| 10 | F10 | Empty `<th></th>` action columns | Admin, Teacher | Medium | `<th><span class="visually-hidden">اقدام‌ها</span></th>` | S | no |
| 11 | F12 | `h1→h5` skips; `/rules/` runs `h1,h5,h5,h4,h6,h5` | Admin, GradeLead, Counselor | Medium | demote section titles to `<h2 class="h5">` (identical rendering, no visual change); `report_card.html` already uses `h1→h2` and is the pattern to copy | S | no |
| 12 | F11 | Active alert filter is colour-only | GradeLead, Counselor | Medium | add `aria-current="page"` to the active chip (the sidebar tag already emits it; this one is hand-written) | S | no |
| 13 | F13 | Mobile table drops its header row and fakes labels in CSS | all | Medium | keep the `<thead>` in the DOM (`.visually-hidden` instead of `display:none`) and keep the `data-label` pseudo-elements as a visual aid only | S | no |
| 14 | F14 | Warning meter 1.94:1, input border 1.46:1 | all | Medium | darken the warning fill to `#b8791f`-class and the input border to ≥3:1 (`#8a94a6`); tokens only | S | no |
| 15 | F15 | `eip-soon` pill 3.74:1 | all | Medium | use the `ink-2` colour on the border tint (≈5.9:1), or drop the pill and mark locked items with a `bi-lock` + text | S | no |
| 16 | F16 | Focus ring 2.12:1 | all | Medium | raise the ring to a solid `#2457b8` at 2 px offset (3.9:1) — one token in `eip.css` | S | **decide 2.1 vs 2.2** |
| 17 | F17 | Success toasts are `role="alert"`; in-page swaps are silent | all | Low | `role="status"` for non-error messages; `aria-live="polite"` on the alert-count region | S | no |
| 18 | F18 | Grade-sheet row error sits in the wrong column | Teacher | Low | put the message under the input in the same `<td>` and point `aria-describedby` at it | S | no |
| 19 | F19 | No `<caption>` on any table | all | Low | caption the 5 heaviest tables (360 ×5, `/rules/` ×5, grade dashboard ×2) | S | no |
| 20 | S3 | 83 `btn-sm` on `/students/`; every row has two action buttons plus a link on the name | Admin, GradeLead, Teacher | Medium | one action per row (the name link goes to the same place as `مشاهده`; keep `پرونده ۳۶۰` only for full-tier students) | S | no |
| 21 | S4 | One-click `حذف` inline with 30 rows of marks; no confirm, no undo | Teacher | Medium | add the repo's existing confirm-modal pattern, or an undo banner for 10 s (a delete stays a POST — no JS-only action) | M | **decide** |
| 22 | S2 | One exam module has three different names across roles | Admin, GradeLead, Teacher | Low | one label (`آزمون‌ها`) + a subtitle per role | S | **decide wording** |
| 23 | S5 | 360 has no in-page navigation and 4 button styles | Admin, GradeLead, Counselor, Parent | Low | sticky anchor sub-nav (`بیمهٔ وضعیت / هشدارها / روند / ارجاع / یادداشت‌ها`) and one button style for primary actions | M | no |
| 24 | S1 | Admin sidebar: 16 links / 5 sections, two of them locked modules | Admin | Low | fold setup into the `مدیریت مدرسه` hub (16 → 10) and hide licence-locked entries behind one `ماژول‌ها` entry | M | **decide** |
| 25 | S7 | Mixed-script dates and decimals | all | Low | add a small `persian_digits` filter (or a `jdate` option) for dates, keep Latin digits for scores, and write the rule down once | S | **decide** |
| 26 | S6 | Every state change is a page load | all | Low | leave as is (ADR-0013 forbids an SPA); add a `Saved` marker so "back" is unambiguous | L | no |

---

**Total if all 26 ship: 20 S + 5 M + 1 L.** The six High findings that carry most of the user cost (F1, F2, F3, F4, F7, F8) are all **S** — that is the headline of this audit.

---

## 7. Proposed work, split into three independently shippable batches

All three are template/CSS/test work only. **None** touches `students/access.py`, entitlements, the audit rules, the database schema, or any URL/permission. No migration, no new endpoint, no new runtime dependency (batch B asks for `axe-core` as a *dev* dependency — your call, see §10).

### 0037a — "Names and structure" (the 11 High/Medium A-level findings)

Scope: F1, F2, F3, F4, F6, F9, F10, F11, F12, F18, F19.

| Piece | Where |
|---|---|
| `<title>` from the existing `{% block title %}` | `base.html` (1 line) |
| one shared error include: real `id`s + `role="alert"` + optional form-level summary | new `templates/dashboard/_form_errors.html`, used by every hand-written form |
| `label for` / `aria-label` on the 50 unnamed controls | `teacher/grades.html`, `loop/alerts.html`, `plan_detail.html`, `school/resets.html`, `school/accounts.html`, `school/staff_roles.html`, `rules.html` |
| `scope="col"` / `scope="row"` + the missing `<thead>` | 20 templates (160 `<th>`), heaviest: `student_360.html`, `rules.html`, `grade_dashboard.html` |
| `visually-hidden` label in the empty action `<th>` | `student_list.html`, `teacher/grades.html`, `teacher/home.html` |
| `aria-current` on the active filter chip | `loop/alerts.html` |
| section titles `h5` → `h2 class="h5"` (no visual change) | the pages P1 reports as `h=[1,5,…]`: `student_360.html`, plan detail, `rules.html`, `_student_summary.html`, loop list headers |

**The cheapest win in the whole audit:** F1+F2 on the Django-form pages are 6 lines in 3 templates (`for="{{ field.id_for_label }}"` on the label, `id="{{ field.id_for_label }}_error"` on the error div). `loop/alert_form.html` is the single template behind both `ثبت نگرانی` and a new alert (`loop_views.alert_new`); `loop/plan_form.html` is behind every intervention plan.

**Visible change:** only the new error text/summary and the `title` bar. Headings keep their size via `class="h5"`.
**Risk:** low — template-only; every touched page already has rendering tests (`test_student_360`, `test_teacher_pages`, `test_loop_alerts`, `test_school_pages`, `test_template_guards`).
**Acceptance:** the batch-B rendered test reports **0 unnamed controls** and **0 `<th>` without `scope`** on the 12 audited pages; `scripts/run_tests.sh sqlite` green.

### 0037b — "Guard rails" (so the audit cannot rot) — lands **after** 0037a

| Piece | Where | Runtime |
|---|---|---|
| lint rules: `<th>` needs `scope`; `<i class="bi` needs `aria-hidden`; `extends base.html` needs a `title` block; `<canvas>` needs `role`+`aria-label`; no `role="alert"` on non-error messages | `dashboard/test_template_guards.py` (extend) | < 1 s |
| rendered-name test: walk the 6 roles (bounded BFS), assert every control has an accessible name, every page title is distinct, heading levels never skip, no duplicate `id` | new `dashboard/test_a11y_render.py` | ~15 s on sqlite |
| token-contrast test: parse `eip.css` custom properties + the pair list, assert ≥ 4.5 (text) / ≥ 3.0 (graphics) | new `dashboard/test_contrast_tokens.py` | ~0.1 s, no browser |
| browser pass: `axe-core` per page/role inside the existing harness, plus a tab-order walk that asserts the focus ring is visible on every stop | `scripts/dev/page_audit.mjs` | manual, dev only |
| write the rule down once | new `docs/A11Y_UI_CHECKLIST.md` (there is no UI guide today) | — |

**Deliberately a separate batch:** a guard that fails on today's code would block everyone; 0037a clears the violations first, 0037b keeps them cleared.

### 0037c — "Colour and the two charts" (independent of a/b)

Scope: F5, F7, F13, F14, F15, F16, F17.

| Piece | Where |
|---|---|
| darken `--eip-muted` (4.26 → ≈5.1) | `eip.css:vars` — one value, global |
| warning meter fill, input border, `eip-soon` pill to ≥3:1 / ≥4.5:1 | `eip.css` |
| focus ring to a solid 2 px `#2457b8` | `eip.css` `:focus-visible` |
| keep `<thead>` in the DOM on mobile | `eip.css:177-181` |
| `role="img"` + `aria-label` + a `visually-hidden` numbers table from the existing `json_script` | `grade_dashboard.html`, `_nid_script.html` |
| `role="status"` for non-error messages | `base.html`, `base_public.html` |

**Risk:** the token change is the only place in this audit where every screen changes at once — hence the contrast test in 0037b should ideally land first (it is allowed to fail on the four known pairs until 0037c completes them).

**S2/S4/S5/S1/S7 (the simplicity items) are not in any batch** — each changes what a user sees or how a workflow runs, so they need your decision before they get a proposal of their own (§10).

---

## 8. The automated checks I propose (at least one is required to close this audit)

Today the product has excellent *permission* guards (`test_menu.py`, `test_sensitive_role_path.py`, `test_template_guards.py`) and **no** guard at all for markup. Nothing in CI would notice if every `aria-label` disappeared tomorrow. Three cheap levels, in increasing cost:

**1. Static lint (extend `dashboard/test_template_guards.py`, < 1 s, no DB).** It already parses templates; four new rules, each a line in the violation report:

```python
RULES = {
    "th_without_scope":        r"<th(?![^>]*scope=)",
    "icon_without_aria_hidden": r'<i class="bi [^"]*"(?![^>]*aria-hidden)',
    "canvas_without_name":     r"<canvas(?![^>]*(aria-label|role=))",
    "extends_base_without_title": None,  # structural: extends base.html but defines no {% block title %}
}
```

**2. Rendered test (new `dashboard/test_a11y_render.py`, ~15 s on sqlite).** The probe from §1 rewritten as a `TestCase`: for each of the 6 demo roles, follow that role's own links (capped, same host) and assert — every `<input|select|textarea>` that is not `hidden/submit/button` has a name (`<label for>`, wrapping label, `aria-label`, `aria-labelledby`); every `<canvas>` has `role` + `aria-label`; `<title>` differs from the bare product name; no heading leap of more than one level; no duplicate `id` on a page. This is the check that would have caught F1 and F4 before a pilot.

**3. Token contrast (new `dashboard/test_contrast_tokens.py`, ~0.1 s, no browser).** Parse the `:root` block of `eip.css`, then assert the real foreground/background pairs and the graphic pairs against 4.5 / 3.0 with the WCAG formula. Pure arithmetic, no dependency, and the only way F7/F14/F15 stay fixed.

**Optional, dev only:** add `axe-core` to the existing Playwright `page_audit.mjs` so a human can run a full automated audit per page. This is the **only** item in the whole proposal that adds a dependency (dev-only), so it is a separate decision (§10.3).

**Tests added inside 0037a itself** (not waiting for b): one assertion per bug fixed — `test_grade_sheet_inputs_have_names`, `test_invalid_alert_form_links_its_error`, `test_every_page_title_is_distinct`, `test_student_360_tables_have_header_rows`.

---

## 9. Impact on data, permissions and the audit trail

**None.** For the record, in the form the governance rules ask for:

| Area | Impact |
|---|---|
| Schema / migrations | none — no model field added or changed |
| Data access | none — every template renders data its view already authorised; nothing new is read. `students/access.py` is not touched |
| Entitlements / roles | none — no URL added, no permission changed. S1 would re-order sidebar *links*, not change who may open them |
| Audit rules / audit log | none — no action becomes audited or unaudited; the 0033 rules stay as documented |
| Security | neutral to positive: an `aria-label` repeats a label the page already prints; the new error `id`s expose nothing |
| Privacy | the `visually-hidden` numbers table for the charts repeats percentages already present in the `json_script` on the same page |
| Real student data | none used — every probe ran against the seeded demo school |
| SPA / React | nothing added; ADR-0013 respected |

---

## 10. Questions for you (DECISION REQUIRED)

1. **Target: WCAG 2.1 AA or 2.2 AA?** 2.2 adds two cheap wins (focus appearance, 24 px target size) and would pull F16 and part of S4 into scope. Recommendation: 2.2 AA, since the CSS is open anyway.
2. **May 0037c change the global `--eip-muted` value?** One variable, ~100 elements, every screen: "slightly darker captions everywhere". Widest-reaching change in the proposal.
3. **Is `axe-core` allowed as a dev-only dependency** in `page_audit.mjs`? Nothing ships to production; `requirements.txt` untouched.
4. **`حذف` on the grade sheet (S4):** confirm-modal, undo banner, or leave one-click? The modal is more consistent with the rest of the product; the undo banner is safer for a fast typist. I will not choose this for you.
5. **Sidebar (S1):** is reducing the Admin sidebar from 16 to ~10 in scope now, or is the module map frozen until after the pilot?
6. **Naming (S2):** one label for the exam module — `آزمون‌ها` — acceptable for all three roles?
7. **Digits (S7):** Persian digits in dates (`۱۴۰۵/۰۸/۱۷`) or keep ASCII? A typography/culture call, not an accessibility one, and it touches `jdate` everywhere at once.
8. **Who reads this product?** If a school inspector or ministry reviewer will, then F1–F4 move from "High" to "cannot ship", and 0037a should land before any new feature work.

---

## 11. Effort and risk summary

| Batch | Scope | Files | New files | Effort | Risk | Depends on |
|---|---|---|---|---|---|---|
| 0037a | 11 findings, template-only | ~22 templates | `_form_errors.html` | **2 days** | low (no CSS change) | — |
| 0037b | 4 guards + 1 doc | `test_template_guards.py`, `page_audit.mjs` | `test_a11y_render.py`, `test_contrast_tokens.py`, `docs/A11Y_UI_CHECKLIST.md` | **1.5 days** | none (tests only) | 0037a green; §10.3 |
| 0037c | colour tokens, charts, message roles | `eip.css`, 3 templates | — | **1 day** | medium (global token) | §10.2 |
| **total** | | | | **≈ 4.5 days** | | |

Suite cost: the three new checks add ≈ 16 s to `scripts/run_tests.sh sqlite`. No existing test gets slower; none is deleted.

---

## 12. Deliberately out of scope

- Redesigning any screen, or changing the navigation *structure* (only the S1 question above).
- Dark mode, high-contrast mode, print stylesheets (the report card prints today; its print a11y is unverified).
- Persian typography beyond S7: font, line-height, ZWNJ, bidi isolation of mixed Latin/Persian strings.
- Touch ergonomics on a real device (none here) — 31 px `.btn-sm` is a computed figure, not an observation.
- The FastAPI side, and the PDF/Excel exports (not part of the Django UI).
- Anything that lets an AI score or ranking drive an action — out of scope by policy, not by effort.
- **`missions/` shares F1/F2** (`missions/grid.html:23`, `missions/choices.html:10` write the same unlinked error div). It is outside the dashboard scope of this audit; the same 2-line fix should follow in whichever change next touches that module, and the §8 rendered test can be pointed at it later.

---

## Appendix A — raw probe output (CURRENT)

Per-role totals, P1 (`/tmp/ux_probe_out.txt`):

```
SchoolAdmin  pages=26 ok=21   controls=70 unnamed=18  bi_icons=497 icons_no_aria_hidden=140
GradeLead    pages=26 ok=12   controls=27 unnamed=2   bi_icons=199 icons_no_aria_hidden=79
Teacher      pages=26 ok=11   controls=7  unnamed=0   bi_icons=156 icons_no_aria_hidden=57
Counselor    pages=24 ok=9    controls=15 unnamed=8   bi_icons=117 icons_no_aria_hidden=54
Parent       pages=24 ok=7    controls=7  unnamed=0   bi_icons=68  icons_no_aria_hidden=40
Student      pages=21 ok=5    controls=7  unnamed=0   bi_icons=56  icons_no_aria_hidden=26
```

Worst pages, same run (depth, path, controls, unnamed, heading levels, `(th, scope)` per table, `btn-sm`):

```
d0 /rules/               ctrls=3  UNNAMED=2 h=[1,5,5,4,6,5] H_SKIP=[(1,5),(4,6)] TH=[(8,0),(4,0),(7,0),(8,0),(4,0)] BTN_SM=23
d0 /school/staff-roles/  ctrls=27 UNNAMED=9 h=[1]         TH=[(7,0)]  BTN_SM=17
d0 /school/resets/       ctrls=2  UNNAMED=1 h=[1]         TH=[(3,0)]  BTN_SM=20
d0 /school/accounts/     ctrls=1  UNNAMED=1 h=[1]                     BTN_SM=15
d0 /alerts/              ctrls=2  UNNAMED=2 h=[1]         TH=[(8,0)]  BTN_SM=7
d1 /interventions/2/     ctrls=6  UNNAMED=6 h=[1,5]       H_SKIP=[(1,5)] TH=[(6,0)] BTN_SM=2
d1 /students/1/360/      ctrls=9  UNNAMED=- h=[1,5,5,5,5,5] H_SKIP=[(1,5)] TH=[(4,0),(3,0),(12,0),(4,0),(4,0)] BTN_SM=7
d1 /students/5/                         h=[1,4,5,5,5]     H_SKIP=[(1,4)]
d2 /students/5/report-card/             h=[1,2]           TH=[(5,0)]  BTN_SM=4   <- correct heading order: the pattern to copy
```

Static counts, C1 (49 templates): `label_without_for=8`, `label_with_for=2`, `th_total=160`, `th_with_scope=0`, `canvas=4`, `canvas_labelled=2`, `canvas_with_role=0`, `<i class="bi …">=34` of which `aria-hidden=5`, `aria-live=0`, `role="status"=0`, `<caption>=0`. Sidebar links/sections: 16/5, 9/5, 8/4, 6/4, 3/2, 5/3.

Invalid POST, P3 (`/alerts/new/` submitted empty):

```
status 200
<textarea name="message" … required aria-invalid="true" aria-describedby="id_message_error" id="id_message">
errors rendered as: <div class="text-danger small">این مقدار لازم است.</div>    (no id= anywhere)
errorlist markup: []
```

Contrast, P4 — 26 pairs, 6 outside their threshold:

```
muted #6b7686 on surface-2 #f8fafc     4.40  (needs 4.5)
muted #6b7686 on page bg   #f4f6fa     4.26  (needs 4.5)
eip-soon #6b7686 on #e3e8ef            3.74  (needs 4.5)
meter warning #e0a43a on track #eef1f5 1.94  (needs 3.0)
input border #cfd6e1 on white          1.46  (needs 3.0)
card border  #e3e8ef on #f4f6fa        1.14  (decorative, exempt)
:focus-visible ring #2457b8 @.45       2.12 on white / 2.07 on page bg
PASS: body ink 15.21, ink-2 7.69, primary 6.71, active nav 8.08, all 5 badges 4.68–6.65, all 4 alerts 7.78–9.26
```

**Reproduce** (read-only; all used the demo settings and the gitignored demo DB):

```bash
cd django_core
DJANGO_SETTINGS_MODULE=config.settings.demo .venv/bin/python /tmp/ux_probe.py    # P1 role walk
DJANGO_SETTINGS_MODULE=config.settings.demo .venv/bin/python /tmp/ux_probe2.py   # P2 write screens
DJANGO_SETTINGS_MODULE=config.settings.demo .venv/bin/python /tmp/ux_probe3.py   # P3 invalid POST
DJANGO_SETTINGS_MODULE=config.settings.demo .venv/bin/python /tmp/ux_probe4.py   # P5 sidebar/section counts per role
.venv/bin/python /tmp/ux_contrast.py                                             # P4 colour maths
```

The five probe scripts are throw-away artefacts in `/tmp`; they are **not** proposed for the repo (0037b turns the useful parts into real tests) and they were not committed.

---

**Status: DRAFT. Nothing has been implemented. Waiting for approval of §7's batches and answers to §10 before any code is touched.**
