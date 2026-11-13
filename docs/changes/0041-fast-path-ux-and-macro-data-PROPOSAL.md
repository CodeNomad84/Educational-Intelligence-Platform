# 0041 — Fast-Path UX & Low-Friction Data Entry + Macro-Analytics Strategy (CHANGE PROPOSAL / ROADMAP — nothing is implemented)

Written 2026-11-13 for the owner. **Level: L2 as a document** (it records and sequences future work; it changes no code).
The work packages it contains carry their own levels: **WP-1 L2 · WP-2 L2 · WP-3 L3 · WP-4 L3 · WP-5 L3**.
**Status: PROPOSED.** Nothing below is approved for implementation *by this file*; each work package needs its own proposal, and the
three L3 ones need their own ADR, before the first line of code. Synthetic data only.
**This change touches documentation only**: no production code, model, migration, route, template, setting, static file or test is
changed, and no existing behaviour is altered.

Read with: `docs/CHANGE_PROCESS.md` (levels and the 11 steps), `docs/templates/CHANGE_PROPOSAL.md` (section order — the mapping is
given at the end of §1), `docs/ARCHITECTURE.md`, `docs/adr/0013-mvp-frontend-server-rendered.md`,
`docs/adr/0014-two-json-frontends.md`, `docs/AI_GOVERNANCE.md`, `docs/SECURITY.md`.
Truth labels in this document: `CURRENT` (verified in the repo, with a file:line) · `TARGET` (intended, not built) ·
`PROPOSED` (awaiting the owner) · `DECISION REQUIRED` (owner must choose) · `DEFERRED` · `NOT VERIFIED`.

---

## 1. Requirement and scope boundary

The owner asked for five modules to be recorded as **Phase-3 / post-integration work packages** — "Fast-Path UX & Low-Friction Data
Entry" and "Macro-Analytics Strategy" — so that they are not lost after the dual-frontend integration (`docs/changes/0040-…`):

| WP | Title | Level |
|---|---|---|
| WP-1 | Negative attendance (bulk-exception flow) | L2 |
| WP-2 | Ladder-style grade grid (keyboard-driven UX) | L2 |
| WP-3 | Zero-hardware OMR answer-sheet scanner | L3 |
| WP-4 | Voice-to-incident logging (Whisper + structured extraction) | L3 |
| WP-5 | Macro-analytics & regional governance (B2G module) | L3 |

**What this document is.** A roadmap of five work packages with, for each: goal, backend, frontend, data, API, security, tests, level,
gate and what is deliberately excluded. It exists so the owner can prioritise and so a later proposal starts from an agreed shape
instead of a blank page.

**What this document is not.** It is **not an approval to build**, not a design frozen in code, and not a claim that anything works.
No endpoint, table, dependency or screen described below exists today; §2 states exactly what exists.

**Why one document and not five proposals.** The five WPs share one premise (a Persian-language school where data entry is the
bottleneck and where the same data must later be aggregated for authorities). Recording them together makes the shared constraints
(§3) and the ordering (§5) visible. **Each WP still gets its own proposal** at implementation time; for WP-3, WP-4 and WP-5 that
proposal is L3 and is followed by an ADR, per `CHANGE_PROCESS.md`.

**Template mapping** (so a reviewer can check compliance with `docs/templates/CHANGE_PROPOSAL.md`):
requirement = §1 · current behaviour = §2 · desired behaviour = §4 (per WP) · affected modules = §4.0 · data impact = §6 ·
API impact = §7 · frontend impact = §8 · AI impact = §9 · security impact = §10 · testing = §11 · documentation impact = §12 ·
customization impact = §13 · risks and alternatives = §14 · recommendation and decisions = §14.4–§14.6.
§3 (the binding constraints), §5 (sequencing and gates) and §15 (verification and process notes) are additions for a multi-WP roadmap;
they replace nothing.

---

## 2. Current behaviour (`CURRENT`, with evidence)

Everything in this section was read from the working tree on 2026-11-13 on branch `work/dual-frontend-integration` (the branch this
one was cut from). Nothing here is taken from documentation alone where code could be read.

### 2.1 What exists

| Subject | `CURRENT` state | Evidence |
|---|---|---|
| Attendance storage | `students.Attendance`: `student` (CASCADE), `enrollment` (PROTECT, nullable), `date`, `status` ∈ `present/absent/late/sick`, `note`, `created_at`; `unique_together [student, date]`; index `att_enr_date_idx (enrollment, date)` | `django_core/students/models.py:133-160` |
| Attendance **entry** | **No attendance write view, form, template or API exists.** Rows are created only by import/seed code | `django_core/config/urls.py` (no attendance route); `students/history_import.py:323`; `students/management/commands/seed_demo.py:262`, `seed_demo_school.py:137`, `seed_temporal_realistic.py`, `seed_temporal_synthetic.py` |
| Attendance **reading** | Scoped reads through `visible_attendances` (plus the reviewed system path `system_scope_attendance`, `:514-515`); used by Student 360, principal dashboard and report card | `django_core/students/access.py:213`, `:514`; `dashboard/principal.py:44`; `dashboard/student360.py:68`; `dashboard/report_card.py:44` |
| Grade entry | One **whole-form** POST per class and exam type: every field posts at once, the server re-renders the page, row errors appear after reload. No keyboard flow, no autosave, no per-cell endpoint | `django_core/dashboard/teacher_views.py:75-112`, template `dashboard/templates/dashboard/teacher/grades.html` |
| Grade model | One row per grade; **no uniqueness on (student, subject, exam_type, date)**; `scale_max` from the per-school grade scale (decision 47) | `django_core/students/models.py` (`Grade`), `school_scale` at `teacher_views.py:78` |
| Behavioural record | `students.BehaviorNote`: `kind` ∈ `positive/concern`, `category` ∈ 6 closed codes, `note` ≤300 chars, `occurred_on` (never future), `recorded_by`; school copied from the student; student PROTECT | `django_core/students/models.py:331-356`, form with the same four fields at `dashboard/behavior_views.py:19-25` |
| Existing API surface | `/api/token/`, `/api/token/refresh/`, `/api/auth/` (csrf, login, logout, me — ADR-0014), DRF router `students` only | `django_core/config/urls.py:18-29` |
| Minimum-group floors | `MIN_GROUP = 5` withholds aggregates; already applied on the principal dashboard, mission simulations and exam result views | `django_core/risk/rules.py` (`MIN_GROUP`), `dashboard/principal.py:35-36`, `missions/lifecycle.py:28` |
| Module entitlement | Exactly **four** sellable keys, documented as "the only sellable keys": `advisor_ai`, `tutor_ai`, `exams`, `mission`; everything else is base | `django_core/schools/entitlements.py:13-17` |
| School key | `School`: `name`, `code`, password-reset flag, AI caps, timestamps. **No province/city/district/region column** | `django_core/schools/models.py:17-37` |
| Frontends | `frontend-men/`, `frontend-women/` are presentation-only TanStack/React apps (`index.tsx`, `__root.tsx`, constant data); ADR-0014 §1 forbids real student data there without a new L2 naming the endpoint and its ACL | `frontend-*/src/routes/`, `docs/adr/0014-two-json-frontends.md:27-29` |
| OMR / scanning | No OpenCV, no image pipeline, no sheet template, no scan record anywhere in code or in any earlier document | `grep -rniE "omr\|opencv"` over `django_core`, `docs`, `frontend-*/src` → no match outside `.venv` and this proposal |
| Speech / voice | No audio capture, no ASR, no transcription code anywhere in code or in any earlier document | `grep -rniE "whisper\|voice"` → no match outside `.venv` and this proposal |
| B2G / regional view | No authority role, no region model, no aggregate export, no cross-school reporting surface. `PlatformAdmin` is a **technical** role explicitly denied school data | `docs/adr/0010-platform-role-map.md:82`; `docs/PRODUCT_SCOPE.md:40` ("Reports & exports for authorities — LATER (needs export policy)") |

### 2.2 Recorded `DOCUMENTATION / CODE CONFLICT` (recorded, not fixed here)

`docs/PRODUCT_BACKLOG.md` §2 lists **"Grades, attendance entry and import — Have — `dashboard/teacher_views.py`, `students/views.py`
import"**. Grades entry is `CURRENT` (`teacher_views.py:75`) and import is `CURRENT` (`students/history_import.py`), but
**attendance entry is not implemented**: there is no write path outside import/seed code (§2.1). Per CLAUDE.md §4 and
`/report-conflict` the conflict is recorded rather than silently resolved — that backlog row bundles three capabilities of which the
middle one is missing. 0041 does not edit the row; WP-1 would close it. The backlog edit made by this change only *references* it
(§12).

### 2.3 Consequence for this roadmap

Every WP below is an **additive** build on a stable base, not a rewrite: the attendance, grade and behaviour models already exist and
are in use; `students/access.py` is the single access layer; the audit log stores ids and codes only; the SPA question is settled by
ADR-0013 with the narrow exception in ADR-0014. **No WP requires touching authentication or frontend routing.**

---

## 3. Constraint that binds every WP (read this before §4)

These are not preferences; each is an accepted decision or a hard rule in `CLAUDE.md`. A work package that cannot satisfy them cannot
be approved as written.

| # | Constraint | Source | What it means here |
|---|---|---|---|
| C-1 | Server-rendered Django templates + Bootstrap 5 RTL; **small JavaScript only where it adds real value; no build step** | `docs/adr/0013-…` §2 | WP-1 and WP-2 ship as Django pages with vanilla JS. No new frontend framework, no npm toolchain, no bundler |
| C-2 | **React only as islands**, each with its own L2 and the first one writing ADR-0006 | `docs/adr/0013-…` §3 | A React screen for WP-1/WP-2 is allowed only after ADR-0006 exists. The default plan does not need it |
| C-3 | A full SPA stays **DEFERRED**; the two React apps are presentation/pilot only, and **wiring real student data into them is a new L2 naming endpoint + ACL** | ADR-0013 §4, ADR-0014 §1 | None of WP-1..WP-5 may be delivered by pushing student data into `frontend-men`/`frontend-women`. ADR-0014's auth surface is unchanged by this roadmap |
| C-4 | All data access goes through `students/access.py`, fail-closed, school-scoped; no raw `Student.objects` in a view | CLAUDE.md §7, ADR-0003/0004/0005 | WP-1 adds one *write* helper there; WP-5 adds one *aggregate* helper there. A guard test enforces it |
| C-5 | Every new route is gated by `schools/entitlements.py` or is explicitly base; there are exactly **four** sellable keys | CLAUDE.md §3, `schools/entitlements.py:13-17` | WP-1/2/3 are base (attendance and grades are base today). WP-4 is proposed base. **WP-5 wants a fifth key → L3 + ADR** |
| C-6 | AI is advisory only; nothing AI-generated becomes trusted data without human validation; **no student PII to an external LLM**; counselling data never goes to AI | CLAUDE.md §8, `AI_GOVERNANCE.md` | WP-4 writes nothing until a human confirms, and runs on the local provider class only; ADR-0014:49 keeps AI features off until ADR-0008 (provider/egress policy, not yet written) is decided |
| C-7 | Audit stores **ids and codes, never content** | `schools/audit.py`, SECURITY matrix | Every WP adds audit codes and counts; no note text, no audio, no image, no score in the audit row |
| C-8 | **No new dependency without an L3 proposal** | `CHANGE_PROCESS.md` levels table | WP-3 (OpenCV/numpy) and WP-4 (ASR runtime) are L3 for this reason alone, before any data argument |
| C-9 | No real student data until the P3 exit criteria are met | `docs/SECURITY.md`, CLAUDE.md §7 | All five WPs are built and demonstrated on synthetic data; the real-data gate is the owner's, not a code switch |
| C-10 | No hard-coded school-specific logic, names or thresholds | CLAUDE.md §7, `CUSTOMIZATION.md` | k, the time-granularity floor, sheet geometry, max audio seconds and prompt ids are configuration/constants with documented defaults |
| C-11 | `PlatformAdmin` is a technical role **denied** school data; a superuser is break-glass, not a reader | `docs/adr/0010-platform-role-map.md:82` | WP-5 may **not** reuse `PlatformAdmin` as the authority role; it needs its own grant (see WP-5) |

---

## 4. Work packages

### 4.0 Affected modules (`MODULE_MAP`)

| WP | Django app(s) | Files that a later implementation would touch |
|---|---|---|
| WP-1 | `students` (model untouched), `dashboard` (pages), `schools` (audit constant) | `students/access.py`, `dashboard/urls.py` + a new view module, `dashboard/templates/dashboard/…`, `config/urls.py` (one `path()`), `schools/audit.py`, tests |
| WP-2 | `dashboard`, `students` (read only) | `dashboard/teacher_views.py` and/or a new view module, one template, one static JS file, `students/access.py` (read helper if needed), tests |
| WP-3 | new module or `exams` (answer keys) | a new `omr` package/command + sheet-template data + tests; **no change to `exams` models in slice 1** |
| WP-4 | `dashboard` (UI), optional `docqa`-style adapter use, `students` (reuse `BehaviorNote`) | one view module, one template + small JS, one adapter call, `AI_GOVERNANCE.md`, tests |
| WP-5 | new `governance` app (proposed), `schools` (region), `students/access.py` (aggregate path), `schools/entitlements.py` (key) | new models + migration, an aggregate query builder, a read-only view/API, tests, one ADR |

No WP modifies `django_core/config/settings/base.py` except to add an app to `INSTALLED_APPS` (WP-5) or a configuration constant —
and only if its own L3 proposal says so.

**Landmine found while writing this (recorded so WP-5 does not trip on it):** `.git/info/exclude` lists `/django_core/governance/` as
local-only (alongside `behavior/`, `core/`, `interventions/`, `risk/`). A new app in that directory would be **invisible to `git
status`**. WP-5's proposal must therefore either pick a different app directory or use `git add -f` for every file it creates and list
them in its report — the exclude list is a local-only convenience, not a safety net against a silent omission.

### 4.1 WP-1 — Negative attendance (bulk-exception flow) · **L2**

**Premise.** A teacher does not "mark 32 students present"; they mark the two who are not. The screen opens with the whole roster
already **present**, so the work is proportional to the exceptions, not to the class size. `TARGET`: a full day for a class in under
15 seconds on a phone.

**Backend.**
- `POST /api/attendance/bulk-exception/` with body `{ "date": "YYYY-MM-DD", "absent_ids": [int, …], "late_ids": [int, …] }`.
- Authentication: **session** (the browser already holds `sessionid`; ADR-0014 §3 stays the model) plus the existing
  `SessionAuthentication`/`JWTAuthentication` for machine clients. **No `BasicAuthentication`** (ADR-0014 §5). CSRF stays on: the
  client sends `X-CSRFToken`, exactly as `/api/auth/login/` already requires.
- Password-change gate: `dashboard/middleware.py` already answers an `/api/` path with `403 {"detail","code"}` instead of a 302
  (ADR-0014 §6) — the new endpoint inherits this, and a test must prove it.
- Throttling: reuse `dashboard/throttle.py`; a per-user rate is enough (no new dependency).
- **Scope resolution (the security core).** A new helper in `students/access.py`, e.g.
  `attendance_writable_students(user, on_date)`, returns only students the caller may mark: SchoolAdmin → own membership schools;
  Grade Lead → own grade; Subject Teacher → students of the classes they are assigned to (`TeacherAssignment`), honouring the rule
  that an inactive class grants nothing; everyone else → `.none()`. It is built from the same primitives as the existing `visible_*`
  functions and must not widen them.
- **All-or-nothing.** If any id is outside the caller's scope the whole request is rejected (`400`) and **nothing is written**. The
  response must not reveal whether an out-of-scope id exists (no enumeration oracle).
- **Write.** Match the existing `unique_together (student, date)`: one row per student per day. `absent_ids` → `absent`,
  `late_ids` → `late`, every other student of the roster → `present`. `enrollment` is resolved from the current academic-year
  enrollment (ADR-0011) and `enrollment_link_source` set accordingly; `import_batch` is **never** touched (an entry is not an
  import). Re-posting the same date is the correction path: it `update_or_create`s, so a student can move `absent → late → present`
  without duplicating rows (`DECISION REQUIRED` D-1.2).
- **Audit.** One `attendance_bulk` row per request: date, counts per status, result (`ok`/`rejected`), actor. **No student ids and no
  names** in the audit detail — counts only (C-7).
- Response: `{ "date", "counts": {"present", "absent", "late", "sick"}, "created", "updated", "unchanged" }`.

**Frontend.**
- A Django page (C-1) rendering the roster server-side for one class and one date, e.g. `/teacher/attendance/` reached from the
  teacher home, with a class/date header and a grade-lead variant.
- **Everyone starts as «حاضر».** Each row has one primary exception control (tap = غایب, second tap = تأخیر, third = مریضی, fourth
  = بازگشت به حاضر) plus an explicit «واگرد» for the last action. A sticky footer shows "۳ غایب · ۱ تأخیر" and one «ثبت» button.
- Progressive enhancement: with JavaScript the taps accumulate and post once (one request to the endpoint above); **without
  JavaScript the page is an ordinary form POST** that still works. The default-present behaviour must not depend on JS.
- «همه حاضر» is a single explicit action for a day without exceptions, so the positive case also writes rows (`DECISION REQUIRED`
  D-1.2).
- RTL, 44 px touch targets, visible focus, `docs/A11Y_UI_CHECKLIST.md`; no client-side validation that the server does not repeat.

**Explicitly out of scope for WP-1.** Parent notifications (channel undecided, `PRODUCT_BACKLOG.md` §2), SMS/e-mail, per-period or
per-subject attendance, sick-note upload, a history editor, exports, and **any screen inside `frontend-men`/`frontend-women`**
(C-3).

**Why L2.** New API surface + a new write helper over student data + an audit code. Not L3: no model change, no new dependency, no
change to authN/authZ, no service boundary.

### 4.2 WP-2 — Ladder-style grade grid (keyboard-driven UX) · **L2**

**Premise.** Entering a column of 32 scores in a form that reloads the page costs minutes per class and is the highest-frequency staff
action in the product. `TARGET`: type, Enter, type, Enter — the column fills without the page moving, each cell persists on its own,
and closing the laptop mid-column loses nothing.

**Current gap** (`CURRENT`): `dashboard/teacher_views.py:75` accepts **one whole-form POST**, validates every row, then either writes
all rows or re-renders with per-row errors. There is no per-cell endpoint and no keyboard model.

**Backend.**
- One small JSON write path for a single cell: `POST /teacher/<assignment_pk>/grades/cell/` (session + CSRF) is recommended, because
  ADR-0013 keeps the page server-rendered and the same view can fall back to HTML. `POST /api/grades/cell/` is the alternative if the
  owner wants machine symmetry — `DECISION REQUIRED` D-2.1.
- Server-side validation is authoritative and unchanged in substance: numeric, `0 ≤ value ≤ school_scale(school)`, student inside the
  caller's class through the existing teacher scope, **subject from the `TeacherAssignment`, never from the request body**, `date` not
  in the future.
- **Identity of a cell.** `Grade` has no uniqueness constraint, so a naive autosave duplicates rows on retry. Slice 1 does an
  update-or-create keyed on `(student, enrollment, subject, exam_type, date)`; adding a real `UniqueConstraint` is `DECISION REQUIRED`
  D-2.2 — it is a data decision with a migration and a duplicate-cleanup step, so it belongs in the WP-2 proposal, not here.
- Response per cell: `{ "ok": true, "student", "value", "grade_id", "created": bool }` or `{ "ok": false, "error": "<Persian>" }`.
  Idempotent: the same value twice is a no-op.
- Audit: the existing `GRADE_ADD` code covers a create; a change needs `GRADE_EDIT`. One row per keystroke is too noisy at class scale,
  so the WP-2 proposal must choose per-cell audit (best for an investigation, higher volume) or a per-batch summary — `DECISION
  REQUIRED` D-2.3.

**Frontend.**
- A `<table>` of real `<input>` elements in a Django page with a vanilla-JS controller (C-1, no build step): **Enter = next row in the
  same column**, Shift+Enter = previous, ArrowUp/Down = same, ArrowLeft/Right = previous/next student **in visual RTL order** (this
  needs an explicit test, not an assumption), Tab = next field, Escape = revert the cell to its server value.
- **Background autosave with debounce** (~600–800 ms after typing stops, plus an immediate flush on blur/Enter so the next cell never
  waits). Cell state is visible: idle · `⟳` saving · `✓` saved · `✗` error with the server's Persian message. A failed cell keeps the
  typed value so nothing is lost.
- A header form for `exam_type` and `date` (per-column decisions, not per-cell) with an explicit «ایجاد ستون»; the grid refuses to save
  a cell before a column exists.
- The existing whole-form POST remains as the no-JS path and for "submit everything".
- Accessibility: a label per input, `aria-live` for the save state, visible focus, 44 px rows on touch (`docs/A11Y_UI_CHECKLIST.md`).

**Explicitly out of scope.** Pasting blocks from Excel (own proposal), offline queueing, undo history beyond the session, a
multi-subject grid, colour-coded thresholds (a grade sheet must not become a judgement of the child), and any React island before
ADR-0006 (C-2).

**Why L2.** New endpoint + a new interaction model over student data; no schema change in slice 1, no dependency, no auth change.

### 4.3 WP-3 — Zero-hardware OMR answer-sheet scanner · **L3**

**Premise.** The school already prints 4-choice answer sheets. A teacher photographs a stack with an ordinary phone; the platform
crops, perspective-corrects, reads the bubbles and proposes scores. "Zero hardware" is the point: no scanner, no dedicated device, no
app install.

**Pipeline (`TARGET`, deterministic — not AI).**
1. Grayscale → adaptive threshold / Otsu.
2. Locate the four corner fiducials printed on the sheet (fallback: the largest quadrilateral contour).
3. Perspective transform to a canonical rectangle (`cv2.getPerspectiveTransform` + `cv2.warpPerspective`).
4. Sample each bubble cell from the **versioned sheet template** (question count, choice count, cell geometry, fiducial layout) — a
   data file, never coordinates hard-coded per exam (`C-10`).
5. Fill ratio per bubble → per-question decision = highest ratio above a threshold and at least a margin above the runner-up.
6. **Ambiguity is a first-class outcome**: two filled or none filled → `needs_review`, never a guess.
7. Score against the exam's answer key (the `exams` module already stores per-option explanations and keys — reuse, do not duplicate).

**Why L3.**
- **New dependency** (OpenCV + numpy): L3 by `CHANGE_PROCESS.md` before any data argument is made (`C-8`).
- **Service boundary** is genuinely open. `docs/ARCHITECTURE.md:7` defines "FastAPI = AI/RAG/analytics layer (LLM, RAG, prediction,
  extraction)"; OMR is deterministic geometry over an image, and whether it belongs to that service, to the Django core, or to neither
  is a new decision rather than an application of an existing one.
- A photographed sheet is a **potentially identifying artifact** (handwriting, a name box, a classroom in the background).

**Service boundary — `DECISION REQUIRED` D-3.1.**
| Option | Shape | Cost | Risk |
|---|---|---|---|
| (a) CLI / management command | `manage.py scan_sheets --template … --file …` on the school's machine | none new in the web app; heavy deps isolated behind an optional extra | no in-browser UX; operator must run a command |
| (b) FastAPI endpoint | `POST /omr/score/` on the AI service, called with the service token (ADR-0002 interim) | real-time UX; heavy deps out of the web image | stretches the `ARCHITECTURE.md:7` definition of that service; needs the service-token path and a new egress question |
| (c) Django view in-process | upload → score synchronously | simplest UX | adds a binary dependency to the core app and to the whole test gate; blocks a worker while processing |

**Recommendation: (a) first** — deterministic, offline, no new HTTP surface, no image leaves the school's machine, and it can be
demonstrated without touching the web tier. Revisit (b) only if the pilot asks for a real-time flow; that would be its own L3 with
ADR-0001/0002 implications.

**Data and PII.**
- Sheets carry a **printed anonymous sheet code**, not a name or national id. The teacher (or an import step) maps code → student at
  confirmation time; the mapping lives for the duration of the scoring session.
- Raw images are **deleted after scoring by default**; no `ImageField`, no `MEDIA_ROOT` copy served by the app, no external upload
  (`DECISION REQUIRED` D-3.2 on any retention for dispute resolution).
- Nothing is written to `Grade` by the scanner. Output is a **proposal table** (per student, per question) that a human confirms —
  the same rule as WP-4 and as AI output (`C-6`), applied here even though the pipeline is deterministic.
- Answer-key mismatch (template version ≠ exam) is a hard refusal, not a best effort.

**Frontend.** Slice 1 is a CLI plus a page that displays the proposal table for confirmation; a camera capture screen is a later
slice and would live in a Django template (C-1) or a React island after ADR-0006 (C-2).

**Explicitly out of scope.** Handwriting OCR, essay or short-answer grading, multi-page booklets, a mobile app, browser camera
integration, bubble-sheet *printing* (the school already prints them), and any automatic write into `Grade`.

**Effort estimate.** Roughly 2 sessions for the pipeline + fixtures, 1 for the proposal/confirm page, 1 for tests; the sheet template
and the synthetic-sheet generator are the real work.

### 4.4 WP-4 — Voice-to-incident logging (Whisper + structured extraction) · **L3**

**Premise.** A teacher who just handled an incident will not type three paragraphs. They will speak 20 seconds into their phone. The
platform transcribes locally, extracts **only** the fields the existing `BehaviorNote` already has, and shows a draft with one
«ثبت» button. Nothing is stored before that tap.

**Chain (`TARGET`).** browser `MediaRecorder` → audio blob (≤ 60 s, `audio/webm` or `audio/wav`) → **local** ASR (Whisper-class
runtime, e.g. `faster-whisper`) → structured extraction (local LLM class) → draft JSON → server-side validation → teacher confirms →
`BehaviorNote` written through the existing `dashboard/behavior_views.py` path.

**Structured target = the existing schema, unchanged** (`CURRENT`, `students/models.py:331-356`):

| Field | Allowed values | Rule |
|---|---|---|
| `kind` | `positive` \| `concern` | closed list; the extractor may suggest, the human decides |
| `category` | `participation`, `effort`, `kindness`, `responsibility`, `conduct`, `other` | closed list; `other` is never invented as a new code |
| `occurred_on` | date | never in the future (the existing form validator already refuses it) |
| `note` | free text, **≤ 300 chars** | truncated by a human edit, never silently by the model |
| `recorded_by` | the confirming user | set by the server, never by the extractor |

No new model, no new free-text field, no severity score, no "risk level", no diagnosis, no automatic alert. **The extractor must not be
able to create a note the human did not confirm** — the draft and the confirm are separate requests and only the second writes.

**Provider and egress (`C-6`).**
- ADR-0008 (LLM provider & data-egress policy) **has not been written**, and ADR-0014 line 49 states that AI features stay off until
  it is decided. Therefore no external provider may receive a child's voice or an incident description: both ASR and extraction run in
  the **local provider class** (`AI_GOVERNANCE.md` "Provider adapter": `class: local`).
- A voice recording is biometric-adjacent and the transcript is sensitive: even after ADR-0008 is decided, this WP should stay
  local-only. That is a recommendation, and `DECISION REQUIRED` D-4.1 if the owner wants external ASR.
- The pipeline has **no access to counseling data**: it never reads `CounselorNote` or `Referral` (ACL before retrieval, not
  retrieve-then-redact). The note the teacher speaks is their own; the produced record is a `BehaviorNote`, not counseling text.
- Prompt ids, model ids and versions are constants recorded in the proposal/report (`AI_GOVERNANCE.md` "Versioning").
- The output is labelled in the UI as a machine draft with per-field confidence; low-confidence fields are left empty for the human.

**Audio handling.**
- Recording is explicit (a visible indicator, a stated purpose, a max duration); no background capture, no auto-upload on blur.
- **Recommended default: delete the audio immediately after transcription**, keep only the text and a hash of the audio for
  traceability. Any retention for dispute resolution is `DECISION REQUIRED` D-4.2 (retention period, encryption, who may play it back).
- Audio bytes never enter the audit log (`C-7`) and never appear in an error message or log line.

**Gating and degradation.**
- Base feature: the underlying `BehaviorNote` is base today, so adding a dictation shortcut to it stays base (`C-5`). Making it a
  sellable key would be an L3 change to the key list.
- If the local model is unavailable, the microphone button is hidden and the existing manual form works exactly as today. **The
  feature must degrade to nothing**, never to a half-written note.
- A per-school daily call cap already exists in `School.ai_daily_cap`/`ai_monthly_cap`; the WP-4 proposal should reuse it.

**Naming caution.** The owner's brief says "Qalamestaan behavioral schema". In this repository `docs/marketing/capabilities.md:101`
records that the product UI says «انتخاب مأموریت‌محور» and that "Qalamestaan" appears **only in `docs/qalamestaan/`**, which holds
Word/PDF/PNG sources (`فرم ثبت مشاهده.docx`, `راهنمای مشاهدات-نسخه2.docx`, …) and no transcribed field table. WP-4 therefore maps to
the **implemented** `BehaviorNote` schema above; if the owner wants extra fields from the observation form, that is a separate schema
proposal with its own migration, and the `.docx` sources must first be transcribed into a text specification (no `.docx` parsing in
the build path).

**Explicitly out of scope.** Real-time streaming transcription, speaker diarization, multilingual output, auto-created alerts or
referrals, parent-visible dictation, and any use of voice for identification.

### 4.5 WP-5 — Macro-analytics & regional governance (B2G) · **L3**

**Premise.** A district, province or ministry wants trends — attendance, outcomes, module usage — without ever seeing a child. The value
is aggregate insight; the risk is that an "aggregate" view becomes a per-student one through a filter, an export, or arithmetic.

**Hard boundary (architectural, not negotiable in the slice).**

| Allowed | Forbidden |
|---|---|
| Counts, rates, distributions, trend indices, cohort sizes | Any student row, name, national id, code |
| Aggregates over groups with **n ≥ k** (default k = 5, reusing `risk.rules.MIN_GROUP`) | `BehaviorNote`/`CounselorNote` text, referral status, alert text, free-text recommendations |
| Term / semester granularity by default | Daily series that can be differenced back to one child |
| School-level totals and region roll-ups | Per-teacher or per-student drill-down, class-level lists |
| Published, versioned metric definitions | Raw scans, audio, exports (export is a separate L3 + policy) |

**Anti-re-identification rules (the part that is usually skipped).**
1. **Primary suppression:** any cell with `n < k` is withheld, not shown as `*` with a real number behind it.
2. **Secondary suppression:** if a published total minus published parts would expose a small cell, suppress the *second-smallest*
   cell too — the differencing attack. The existing `MIN_GROUP` floors do **not** cover this; the aggregate builder must.
3. **Combination floors:** the floor applies to every *combination* used (school × grade × term), not only to marginals, otherwise a
   20-cell table leaks even when each marginal is legal.
4. **Small-population refusal:** a region whose total cohort is below `k` publishes nothing at all.
5. **Time floor:** default term; a shorter granularity is configuration, and lowering it below the documented floor must be a
   decision, not a query parameter.
6. **No query freedom.** A fixed catalogue of named aggregates with server-side definitions. No ad-hoc slicing UI, no "group by
   anything" — that is the difference between a report and a re-identification tool.

**Access model.**
- **New, explicitly granted authority role** (`AuthorityViewer`), `DECISION REQUIRED` D-5.1. It must **not** reuse `PlatformAdmin`:
  ADR-0010 line 82 states that `PlatformAdmin` is a technical role that cannot see school data (`C-11`), and reusing it would silently
  overturn an accepted decision. A superuser stays break-glass.
- The role carries a **named jurisdiction scope** (one region node or a set) and nothing else: no school-data pages, no student
  search, no Django-admin student permissions.
- **Jurisdiction data does not exist yet.** `School` has `name`, `code`, the password-reset flag, AI caps and timestamps — no
  province/city/district (`schools/models.py:17-37`). WP-5 needs a `Region` table (self-referencing or fixed three levels) and a
  `School.region` FK (PROTECT) with a migration and backfill: an **L3 data change**. Hierarchy depth is `DECISION REQUIRED` D-5.2.

**Module key.** `schools/entitlements.py:13-17` documents four sellable keys and calls them "the only sellable keys". A fifth key
(`governance`) is an L3 change plus an ADR (`C-5`); shipping it as a base feature contradicts the commercial intent — it is the one
capability a ministry buys. `DECISION REQUIRED` D-5.3 (fifth key vs base).

**Read path.**
- A **new explicit aggregate function** in `students/access.py` (e.g. `aggregate_scope(user, region_ids, term)`), never a user's
  `visible_*` set and never a student queryset handed to a view. The aggregate builder is its only consumer, and a guard test asserts
  that no governance view imports `Student` directly.
- Cross-school aggregation respects the school key (ADR-0004/0012): compute **per school, then sum**; never join student rows across
  schools into one queryset that the requester can filter.
- Every aggregate query is **audited** (`schools/audit.py`): actor, metric id, region id, term, result size. The authority's own reads
  are auditable — that is the point.

**Legal and honesty.**
- "Zero PII" is a **design target, not a certificate**. k-anonymity reduces but does not eliminate re-identification, and under many
  privacy regimes aggregated-but-small data can still be personal data. The proposal must say so, and a data-sharing agreement plus
  the owner's legal sign-off is a **precondition** for any real deployment (the same shape as the outstanding legal items in
  `docs/SECURITY.md`). No claim of "anonymous" or "compliant" may appear in UI or marketing copy until that sign-off exists.
- No school rankings by name (naming and shaming), no "best/worst region" label, no predictions about regions, no inference of
  individual students, no labelling of children at all.

**Frontend.** A read-only Django page: pick a published metric, a term, a jurisdiction; see one table and one chart from a fixed
catalogue. No filters beyond those three, no export button in slice 1, no React (C-1/C-2).

**Tests.** The differencing test (construct a table where a small cell is derivable → assert refusal/secondary suppression); boundary
tests at n = k−1, k, k+1; a schema-leak suite asserting the response contains no `id`, `name`, `student`, `note` or free-text field;
a cross-jurisdiction test (authority A cannot query B's schools); a "no ad-hoc grouping" test; an audit test; a k-floor test on
combinations, not just marginals.

**Why L3.** New models + migration + new role + new entitlement key + a new read path over cross-school data + legal exposure. This is
the highest-risk package in this document by a wide margin.

---

## 5. Sequencing, dependencies and gates

### 5.1 Order

| Order | WP | Why it comes here |
|---|---|---|
| 1 | **WP-1** attendance | It is a *correctness* gap, not a convenience one: the backlog claims attendance entry and there is none (§2.2). It is also the cheapest of the five and the input for WP-5 |
| 2 | **WP-2** grade grid | Highest frequency of use; independent of WP-1; can be developed in parallel if the owner wants |
| 3 | **WP-4** voice-to-incident | Independent, but only worth building if the pilot's teachers actually write behaviour notes; needs a local runtime decision first (D-4.1) |
| 4 | **WP-3** OMR | Needs answer keys in `exams` (already present) but is a separate skill set and a new dependency; only justified if the pilot prints bubble sheets at scale |
| 5 | **WP-5** B2G | Last. It consumes aggregates produced by WP-1/WP-2, needs a new role, a region schema, a fifth entitlement key and legal sign-off. Building it before the data exists produces empty charts and a domain model nobody validated |

### 5.2 Dependency graph

```
P3 exit (real data) ──► any WP in production
WP-1 ──► attendance aggregates ──► WP-5
WP-2 ──► grade aggregates     ──► WP-5
WP-3 ──► (independent; reuses exams answer keys; writes nothing without confirmation)
WP-4 ──► (independent of data; needs local ASR/LLM runtime + ADR-0008 for anything external)
WP-5 ──► needs: Region schema + new role + entitlement decision + legal sign-off
```

### 5.3 Gates (a WP cannot start before its gate is green)

| Gate | Applies to | Condition |
|---|---|---|
| G-P3 | all, for real data | P3 exit criteria met on the real data (`docs/SECURITY.md`), not on synthetic data |
| G-DEP | WP-3, WP-4 | the dependency is named in an approved L3 proposal with a pinned version, a licence note and an offline-install story |
| G-BOUND | WP-3 | service boundary chosen (D-3.1) and, if FastAPI, the service-token path defined (ADR-0002 interim) |
| G-AI | WP-4 | local provider class in use; prompt/model versions recorded; no counseling access; a "no write without confirm" test green |
| G-ADR-0006 | any React island | ADR-0006 written (it is reserved, not written — ADR-0013:6) |
| G-ADR-0008 | anything external | ADR-0008 written; AI stays off until then (ADR-0014:49) |
| G-REGION | WP-5 | `Region` model + migration + `School.region` backfill approved as L3 |
| G-ROLE | WP-5 | the authority role is a **new** grant, not `PlatformAdmin` (D-5.1) |
| G-KEY | WP-5 | the fifth entitlement key approved as L3 + ADR (D-5.3) |
| G-LEGAL | WP-5 | data-sharing agreement and owner/legal sign-off on publication rules |

### 5.4 What the owner gets after this document is approved

Nothing runs. The deliverable is a decision list (§14.6) and an order. The next artefact is one proposal per WP, in the order of §5.1,
each starting with the open decisions that block it.

---

## 6. Data impact

No WP in this document changes a model today; this table is what a later proposal would have to declare.

| WP | New/changed models | Migration | Volume | Retention / deletion | Notes |
|---|---|---|---|---|---|
| WP-1 | **none** (`Attendance` untouched) | none | +1 row per student per school day where attendance is taken (≈ 30–40 rows per class-day) | existing retention rules apply; rows are correction-friendly (`update_or_create`) | `import_batch` stays NULL; `enrollment` linked from the current year. D-1.2 decides materialised vs sparse |
| WP-2 | none in slice 1; **possible** `UniqueConstraint (student, enrollment, subject, exam_type, date)` later | none / one | no change (same rows, written more often) | n/a | D-2.2 governs the constraint; a cleanup migration for pre-existing duplicates would be required first |
| WP-3 | none in slice 1 (stateless scoring, no image storage); sheet templates are **files**, not rows | none | none | raw images deleted after scoring by default (D-3.2) | if scan history is ever wanted, that is its own proposal |
| WP-4 | **none** — reuses `BehaviorNote` exactly | none | +0 (a note today is typed; after WP-4 it is dictated) | audio deleted after transcription by default (D-4.2); the note itself follows the existing retention rule ("nothing deleted automatically") | no new text column |
| WP-5 | `Region` (new), `School.region` (FK, PROTECT), optional aggregate cache table | **yes, L3** | region rows = number of jurisdictions (tens); cache rows = metrics × regions × terms | cache is derivable and disposable; the audit log is append-only | no student-level table is created, ever |

**Data-minimisation check.** WP-1 and WP-2 add *rows about existing students that the school already collects*; they do not add a new
category of personal data. WP-3 and WP-4 are the two that could add an artefact (image, audio) — both are designed to delete it
immediately. WP-5 must not add student-level data at all: it reads what exists and emits aggregates.

---

## 7. API impact

All additions are **new paths**; no existing route, serializer, permission or response shape changes. `/api/token/`,
`/api/token/refresh/`, `/api/auth/csrf|login|logout|me/` and the DRF `students` router stay as they are (`CURRENT`,
`config/urls.py:18-29`).

| WP | Path (proposed) | Method | Auth | Writes | Notes |
|---|---|---|---|---|---|
| WP-1 | `/api/attendance/bulk-exception/` | POST | session + CSRF, or JWT | `Attendance` rows for one date | all-or-nothing; 400 on out-of-scope id; throttled; the password-change gate inherits `dashboard/middleware.py`'s `{"detail","code"}` 403 |
| WP-2 | `/teacher/<assignment_pk>/grades/cell/` (recommended) or `/api/grades/cell/` (D-2.1) | POST | session + CSRF | one `Grade` row | JSON in/out; HTML fallback possible; server-side scale and scope validation |
| WP-3 | none in slice 1 (CLI); if option (b), `POST /omr/score/` on the FastAPI service | POST | service token (ADR-0002 interim) | **none** (returns a proposal) | D-3.1 decides whether this exists at all |
| WP-4 | `POST /api/incidents/draft/` (audio or transcript → draft) and `POST /api/incidents/confirm/` (draft → `BehaviorNote`) | POST | session + CSRF | draft: **none**; confirm: one `BehaviorNote` | two endpoints on purpose: only the second writes. D-4.3 if a single endpoint with a `confirm` flag is preferred (not recommended) |
| WP-5 | `GET /api/governance/aggregates/<metric_id>/?region=&term=` | GET | session; authority role | **none** | read-only, fixed metric catalogue, audited; no export endpoint |

**Compatibility.** Every path above is additive, so the API stays at its current unversioned shape; the two React frontends are
unaffected and nothing in ADR-0014's contract changes. If WP-5 later needs an export, that is a new L3 with a policy, not a query
parameter.

**Anti-abuse.** WP-1 and WP-2 are write endpoints over student data: both need throttling, both must reject unknown or foreign ids
without distinguishing "does not exist" from "not yours", and neither may echo back a roster the caller could not already see.

---

## 8. Frontend impact

| WP | Surface | Stack | New files |
|---|---|---|---|
| WP-1 | teacher attendance page + grade-lead variant | Django template + Bootstrap RTL + small vanilla JS; no-JS form fallback | one template, one JS file, one view module |
| WP-2 | grade grid, replacing the column-entry part of the existing page | Django template + one vanilla-JS controller (keyboard + debounce) | one template change, one JS file, one view module |
| WP-3 | proposal/confirm table (slice 1) | Django template; optional camera capture later | one template |
| WP-4 | microphone button on the existing behaviour-note form | Django template + `MediaRecorder` + `fetch` | one template change, one JS file |
| WP-5 | read-only aggregate page | Django template + one chart (server-rendered SVG, or a chart lib only if one is already present) | one template |

**Rules that hold for all five** (existing policy, not new): no SPA; no build step; no new npm dependency; Bootstrap 5 RTL and the
existing base template; Persian labels and numbers as the interface already does; `docs/A11Y_UI_CHECKLIST.md` applies (focus, labels,
touch targets, `aria-live` for async state); mobile-first for the teacher screens, because that is where the data is entered; **no
screen inside the two React apps** (C-3) and no React island before ADR-0006 (C-2).

**Deliberately not proposed.** Onboarding tours, teacher dashboards, gamification, dark mode, an offline PWA, a native app, or any
redesign of the existing navigation. Each would be its own proposal and none is on the critical path of data entry.

---

## 9. AI impact

| WP | AI involved? | Rule |
|---|---|---|
| WP-1 | **No** | Deterministic writes. Must not be described as AI |
| WP-2 | **No** | Deterministic validation. No "smart" suggestion of a score — that would be a judgement about a child |
| WP-3 | **No**, explicitly | OMR is classical computer vision. It must not be marketed as AI, and it must not be built on a model that could "learn" a wrong answer |
| WP-4 | **Yes**, the only one | Local ASR + local extraction; advisory output; per-field confidence; human confirmation mandatory; closed schema; no counselling access; no severity or risk score; prompt/model versions recorded |
| WP-5 | **No** | No prediction, no ranking, no clustering presented as insight. Aggregates are arithmetic over the school's own data |

**WP-4 governance checklist** (to be answered in its L3 proposal, per `AI_GOVERNANCE.md`): provider class, and whether the model runs on
the school's hardware or the operator's; exactly what is sent to the model (audio and nothing else — no student record); how the output
is labelled; how a wrong extraction is corrected; how a prompt change is versioned and reviewed; what is logged (ids and counts only);
how the feature is switched off per school, degrading to the manual form; and who owns the transcript.

**What must never happen (applies to every WP).** An AI output becoming a stored fact without a human; a child being labelled,
scored, ranked or predicted by a model; counselling text reaching a model; a student's data leaving the deployment; a marketing claim
of AI capability that does not exist (`docs/marketing/capabilities.md` is the reference for what may be said).

---

## 10. Security impact

### 10.1 Authorisation per WP

| WP | Who may act | Scope source | Fail-closed behaviour |
|---|---|---|---|
| WP-1 | SchoolAdmin, Grade Lead, Subject Teacher | new `attendance_writable_students()` in `students/access.py`, built on the existing scopes | no role → empty set → every id rejected; out-of-scope id → whole request 400, nothing written |
| WP-2 | Subject Teacher / Grade Lead holding the assignment | existing teacher scope + `TeacherAssignment` | subject and student come from the assignment, never from the body; unknown assignment → 404 |
| WP-3 | the operator running the CLI (no HTTP principal in slice 1) | filesystem access only | no web principal can trigger scoring; a proposal is never applied automatically |
| WP-4 | any staff role that may already create a `BehaviorNote` | unchanged `dashboard/behavior_views.py` scope; the confirm step goes through it | the draft endpoint returns no student data; confirm refuses a student outside the existing write scope |
| WP-5 | new `AuthorityViewer` with a named jurisdiction | new `aggregate_scope()` in `students/access.py` | no grant → no aggregates; a region outside the grant → 403/empty; `PlatformAdmin` gains nothing |

### 10.2 Threats specific to this roadmap

| Threat | WP | Mitigation in the design |
|---|---|---|
| Bulk endpoint used as an enumeration oracle ("does student 1234 exist?") | WP-1 | validate the **whole** list against scope first; reject without naming which id failed; identical response for "not yours" and "does not exist" |
| Autosave flooding, accidental duplicate grades | WP-2 | debounce + idempotent update-or-create + throttle; D-2.2 for a real constraint |
| Silent misread producing a wrong official grade | WP-3 | ambiguity → `needs_review`; human confirmation; template/answer-key mismatch refuses; nothing auto-written |
| Wrong extraction producing a stigmatising note about a child | WP-4 | closed schema, human confirm, low-confidence fields left empty, no severity, no auto-alert, audit records the human actor only |
| Voice clip retained and replayed out of context | WP-4 | deleted after transcription by default; explicit recording indicator; no audio in logs; D-4.2 if retention is ever wanted |
| Re-identification by differencing across published aggregates | WP-5 | secondary suppression + combination floors + time floor + fixed catalogue (§4.5) |
| The authority role becoming a back door to student data | WP-5 | new role only, no school-data pages, guard test on imports, audited reads |
| Cross-school join leaking past the tenant key | WP-1, WP-5 | compute per school then sum; school key enforced in the access layer (ADR-0004/0012) |
| The audit log becoming a copy of the data | all | counts and codes only (C-7); no names, text, scores, audio or images |

### 10.3 PII and retention

- No real student data in any WP until G-P3; every demo and test uses synthetic data (`CLAUDE.md §7`).
- Two new artefact types: an answer-sheet image (WP-3) and a voice clip (WP-4). Both are **deleted by default after their single use**,
  and neither may be stored in a publicly served media path.
- Retention periods are `DECISION REQUIRED` (D-3.2, D-4.2) because that is a policy question, not an engineering one.
- WP-5 publishes aggregates only, with the explicit statement that k-anonymity is a mitigation and not a guarantee (§4.5).

### 10.4 Not a security boundary

WP-1..WP-5 do **not** make the deployment production-ready. `docs/SECURITY.md` S-03 is still `PARTIAL`, and the P3 exit — including the
access-parity gate re-run on real data — is a precondition for real data, not something these features can substitute for.

---

## 11. Testing strategy

**Where.** Tests live in the owning app, following the existing convention `django_core/<app>/test_<topic>.py` (e.g.
`django_core/dashboard/test_attendance_bulk.py`, `students/test_access_attendance_write.py`). They run under the single command
`scripts/run_tests.sh sqlite` and, at the end of a change, `scripts/run_tests.sh pg`. The suite list in that script
(`students dashboard schools vocabulary missions exams risk interventions docqa` + `demo_intel`) already covers every app these WPs
touch; a new app (WP-5) must be **added to the script's suite list**, which is itself a reviewed change.

**Shape per WP.** Every WP needs the same five kinds of test, and it is not `done` until all five exist and pass on both databases.

| Test kind | WP-1 | WP-2 | WP-3 | WP-4 | WP-5 |
|---|---|---|---|---|---|
| Happy path (actor, scope, write) | teacher marks 2 absent of 30 → 30 rows, correct statuses | one cell saved, page state returns to idle | synthetic sheet → 20/20 questions read | mocked ASR + extraction → draft → confirm → one note | authority reads a region aggregate |
| Authorisation / two-school leak | another teacher's student id → whole request 400, table unchanged | cell for a student outside the class → refused | CLI only; no HTTP principal to test | confirm for a student outside the write scope → refused | authority A → B's region 403/empty; `PlatformAdmin` → no access at all |
| Boundary / adversarial input | duplicate ids, empty lists, future date, closed year | value above `school_scale`, negative, non-numeric, missing column | rotated/skewed/blurred sheet, two bubbles, no bubble, wrong template | bad JSON, unknown category, note > 300 chars, future date, missing field | n = k−1, n = k, n = k+1; **differencing table**; combination floor; response-schema leak |
| No-write assertion | rejected request leaves the table identical | failed cell leaves the row unchanged | scoring never creates a `Grade` | draft endpoint writes nothing | aggregate endpoint writes nothing but an audit row |
| Audit | one row, counts only, no student ids | code and actor as decided in D-2.3 | n/a (CLI) | actor = confirming human, no audio/text in the row | actor + metric + region + term, no result values |

**Additional requirements.**

- **WP-1/WP-2:** a test that the `/api/` password-change gate returns the JSON 403 rather than a redirect (ADR-0014 §6), because the
  new endpoints are reached by `fetch` and a redirect would be followed silently into HTML.
- **WP-2:** a keyboard flow cannot be tested with Django's test client. The next-cell logic (including the RTL order) is extracted as a
  pure function and unit-tested, and the manual steps are recorded in the change report. Do not claim a browser test that was not run.
- **WP-3:** fixtures are **generated synthetic sheets** (a script renders the bubbles deterministically), never photographs of real
  children. The dependency stays out of the default test run until G-DEP; tests skip loudly when it is absent, and **a skipped test is
  never reported as a pass**.
- **WP-4:** ASR and extraction are **mocked**; no model runs in CI. The prompt text and model id are asserted against expected
  constants so a silent prompt change fails the test.
- **WP-5:** a "no ad-hoc grouping" test asserts unknown query parameters are rejected; a guard test asserts no governance view imports
  `Student` directly; an audit test asserts the read was logged.
- **Regression:** each WP adds at least one assertion that the *existing* behaviour is unchanged — the whole-form grade POST still works
  after WP-2, the manual behaviour-note form still works after WP-4, the existing attendance readers see the new rows after WP-1.

**What tests cannot establish.** Performance on a real phone, OCR accuracy on a real school's printer, ASR accuracy on Persian school
vocabulary, and re-identification resistance in an adversarial sense. Those need a pilot under real (consented) conditions and stay
`NOT VERIFIED` until measured.

---

## 12. Documentation impact

| Document | Change | When |
|---|---|---|
| `docs/changes/0041-…-PROPOSAL.md` (this file) | created | now |
| `docs/PRODUCT_BACKLOG.md` | new §4 listing the five WPs as upcoming, the old §4 renumbered to §5, one pointer line (§12.1) | now |
| `docs/SECURITY.md` | authorisation-matrix rows for the new endpoints and the new authority role; PII/retention rows | with each WP |
| `docs/ARCHITECTURE.md` | the new routes and, for WP-5, the aggregate read path | with each WP |
| `docs/MODULE_MAP.md` | which module owns each screen, and whether it is base or a key | with each WP |
| `docs/AI_GOVERNANCE.md` | WP-4's provider class, prompt ids, model ids, confirmation rule | with WP-4 |
| `docs/DATA_MODEL.md` | `Region`, `School.region`, any constraint from D-2.2 | with the WP that migrates |
| `docs/CUSTOMIZATION.md` | k, time granularity, sheet-template version, max audio seconds, prompt ids | with each WP |
| `docs/manuals/teacher.md`, `…/grade-lead.md`, `…/school-admin.md` | the new screens in Persian, in the existing manual style | with each WP |
| `docs/TESTING.md` | new modules; WP-3/WP-4 need a "how to run without the optional dependency" note | with each WP |
| `docs/PROJECT_CHECKLIST.md`, `docs/ROADMAP.md` | status flips only **after** a WP ships with a report | after, never in advance |

### 12.1 The backlog edit made by this change (exact scope)

`docs/PRODUCT_BACKLOG.md` gains a new `## 4. Upcoming Fast-Path Enhancements (Post Proposal 0040)` section with a five-row table
(WP / title / level / gate / one-line outcome), the previous `## 4. Method and limits` becomes `## 5.`, and one line under the document
header points to this proposal. **No existing row is reworded**, including the row that §2.2 records as conflicting — closing that gap
is WP-1's job, with evidence, not a documentation edit that would hide it.

---

## 13. Customization impact

| Setting | Default | Why configurable | Where it would live |
|---|---|---|---|
| Minimum group size `k` (WP-5) | 5 (reuses `MIN_GROUP`) | a small rural district legitimately has cohorts of 8; a large one may want 10 | `risk/rules.py` constant + documented in `CUSTOMIZATION.md` |
| Published time-granularity floor (WP-5) | term | policy, not code | the aggregate catalogue definition |
| Sheet template version (WP-3) | one template per exam layout | a school may use 100- or 150-question sheets | the versioned template file, not a setting |
| Bubble fill threshold + ambiguity margin (WP-3) | tuned on synthetic sheets | printers and paper differ | constants in the OMR module, printed in the run report |
| Max recording length (WP-4) | 60 s | a long incident narrative vs a quick note | a school-level setting or constant |
| ASR/extraction provider + model id (WP-4) | `class: local` | the operator's hardware differs | the existing provider adapter config |
| Daily AI cap | existing `School.ai_daily_cap` / `AI_DEFAULT_DAILY_CAP` | already a per-school config value | unchanged |

**No hard-coded school names, no per-school `if` statements, no region names in code.** A new school is configured, never coded
(`CLAUDE.md §7`, `CUSTOMIZATION.md`). The `Region` hierarchy (WP-5) is **data**: a new province is a row, not a release.

---

## 14. Risks, alternatives and the decision list

### 14.1 Risk register

| ID | Risk | WP | Likelihood | Impact | Mitigation |
|---|---|---|---|---|---|
| R-1 | Attendance written on the wrong date (a copied URL, a stale tab) and nobody notices | WP-1 | Medium | Medium | the date is shown loudly in the header and in the confirmation; one audit row per request; correction is a re-post, not a delete |
| R-2 | "All present" becomes a rubber stamp, so absence data loses signal | WP-1 | Medium | Medium | the positive case is an explicit action, not a silent default write; the footer always shows the exception count; no auto-submit |
| R-3 | Autosave creates duplicate grade rows | WP-2 | Medium | High (data quality) | update-or-create on the natural key + D-2.2 constraint + a duplicate-detection query in the report |
| R-4 | A misread sheet silently changes an official grade | WP-3 | Low (with `needs_review`) | **High** | never auto-write; ambiguity → review; per-question proposal table confirmed by a human; template/key mismatch refuses |
| R-5 | Extraction produces a stigmatising note about a child | WP-4 | Medium | **High** | closed schema, human confirm, no severity field, low-confidence left empty, audit names the human |
| R-6 | A voice clip or an image is retained indefinitely | WP-3, WP-4 | Medium | High | delete-after-use default; retention only by explicit decision, written into `SECURITY.md` |
| R-7 | The B2G module becomes a surveillance tool through small-cell differencing | WP-5 | **High if not designed for it** | **Severe** | secondary suppression + combination floors + time floor + fixed catalogue + audit + legal sign-off as a precondition |
| R-8 | A new dependency cannot be installed offline at a school | WP-3, WP-4 | Medium | Medium | G-DEP requires a pinned version and an offline wheel/model story; CI skips the tests, the report states it |
| R-9 | Scope creep: "fast path" grows into a redesign | all | **High** | Medium | each WP's out-of-scope list is part of its contract; anything not listed needs its own proposal |
| R-10 | The roadmap is read as an approval and work starts without a proposal | all | Medium | Medium | `Status: PROPOSED` in the header; §1 and §5.4 state it twice; each WP names its own gate |

### 14.2 Alternatives considered (and why they are not the plan)

| Alternative | Why not |
|---|---|
| Skip WP-1 and keep using Excel import | Import is a batch tool; it cannot record today's two absences before the second period. The backlog already claims this capability, so the gap is also a credibility problem (§2.2) |
| Skip WP-2 and keep the whole-form POST | It is the highest-frequency action in the product; the current flow reloads the page per class-exam. But WP-2 is the least risky of the five, so "do nothing" is a real option if the owner wants to ship only WP-1 |
| Skip WP-3 and use a spreadsheet import | Legitimate: if the school already types answers from paper, OMR only helps at scale. Recommend deferring WP-3 until the pilot demonstrates the volume |
| Skip WP-4 because typing takes 20 seconds | Also legitimate, and the cheapest to defer: the manual form already works. WP-4 is a convenience feature with the highest data-quality risk of the five |
| WP-5 as a static annual report instead of a live module | **The strongest alternative.** A one-off report generated by the operator from an anonymised extract satisfies most ministry asks without a new role, a region schema, a fifth key, or a live surface. Recommend evaluating this before approving the module |
| Build everything on the React frontends | Forbidden by ADR-0013 §4 and ADR-0014 §1 without a new L2 naming endpoint + ACL each time (C-3) |

### 14.3 Effort estimate (rough, in sessions)

| WP | Build | Tests | Docs | Total | Confidence |
|---|---|---|---|---|---|
| WP-1 | 1.5 | 1 | 0.5 | ≈ 3 | High — smallest surface, no new model |
| WP-2 | 2.5 | 1.5 | 0.5 | ≈ 4.5 | Medium — the keyboard/RTL JS is where the time goes |
| WP-3 | 3 | 1.5 | 0.5 | ≈ 5 | Low — depends on sheet quality and the fixture generator |
| WP-4 | 2 | 1.5 | 1 | ≈ 4.5 | Low — depends on local model availability and Persian ASR quality |
| WP-5 | 4 | 2 | 1.5 | ≈ 7.5 | Very low — new role, new schema, entitlement, legal |

These are estimates, not commitments, and none of them includes the pilot feedback loops.

### 14.4 Recommendation

1. **Record this roadmap** (this document) plus the backlog pointer. That is all 0041 asks for.
2. **Approve WP-1 next**, as its own L2 proposal: it closes a documented capability gap rather than adding a convenience.
3. **Approve WP-2 after WP-1**, or in parallel if a second worker is available; it is the biggest daily time saving and the lowest risk.
4. **Defer WP-3 and WP-4** until the pilot shows the volume that justifies them. Both are L3, both add a dependency, and neither is
   needed for a school to run its day.
5. **Treat WP-5 as a decision, not a backlog item.** Before any code: choose between the live module and the static annual report
   (D-5.4), then the region schema, the role, the key and the legal sign-off. Ship it last — or not at all.

### 14.5 ADRs this roadmap implies (none written by this change)

| ADR | Title | Triggered by |
|---|---|---|
| 0006 | React island mechanics (reserved, per ADR-0013:6) | only if a React screen is chosen for WP-1/WP-2/WP-3 |
| 0008 | LLM provider & data-egress policy (not written; ADR-0014:49 keeps AI off) | WP-4, if an external provider is ever wanted |
| new | OMR service boundary (deterministic CV: CLI vs service) | WP-3, options (b) or (c) |
| new | Aggregate publication policy & authority role (B2G) | WP-5 |
| none | WP-1, WP-2 | an L2 change proposal is enough |

### 14.6 Decision list — `DECISION REQUIRED`

| ID | Question | Recommended answer | Blocks |
|---|---|---|---|
| D-0.1 | Is this roadmap accepted as the record of the five WPs, in the order of §5.1? | accept | everything |
| D-1.1 | `/api/attendance/bulk-exception/` as proposed, or a Django form endpoint like WP-2? | the `/api/` path (a bulk write with a JSON body; a form POST would post 30 checkboxes) | WP-1 |
| D-1.2 | Materialised ("all present" writes a row per student) or sparse (only exceptions)? | **materialised** — the existing readers and rates assume rows exist | WP-1 |
| D-1.3 | May a Grade Lead mark the whole grade, or only the classes they are assigned to? | only their assigned classes unless the owner says otherwise | WP-1 |
| D-2.1 | Cell endpoint under `/teacher/…/` or `/api/grades/cell/`? | `/teacher/…/` (keeps the page server-rendered, HTML fallback) | WP-2 |
| D-2.2 | Add a `UniqueConstraint` on the grade natural key (with duplicate cleanup)? | yes, in a second slice, after measuring duplicates | WP-2 |
| D-2.3 | Per-cell audit or per-batch summary? | per cell for creates, per batch for a bulk save, ids only in both | WP-2 |
| D-3.1 | OMR service boundary: CLI (a), FastAPI (b) or Django view (c)? | **(a) CLI first** | WP-3 |
| D-3.2 | Any retention of scanned images (e.g. for disputes)? | no retention by default | WP-3 |
| D-4.1 | Local-only ASR, or an external provider once ADR-0008 exists? | **local-only**, permanently | WP-4 |
| D-4.2 | Any retention of voice clips? | no retention by default (transcript + hash only) | WP-4 |
| D-4.3 | Two endpoints (draft, confirm) or one with a flag? | two endpoints — the split is the safety property | WP-4 |
| D-5.1 | New `AuthorityViewer` role or extend `PlatformAdmin`? | **new role** (`PlatformAdmin` is denied school data by ADR-0010:82) | WP-5 |
| D-5.2 | Region hierarchy depth: 2 levels (province → district) or 3 (+ school)? | 2 levels; a school references the district | WP-5 |
| D-5.3 | Fifth entitlement key `governance`, or base? | **fifth key** (it is the capability a ministry buys) | WP-5 |
| D-5.4 | Live module or static annual report as the first B2G deliverable? | static report first; the module only if a customer asks | WP-5 |
| D-5.5 | Minimum group size `k` for publication | 5, matching `MIN_GROUP` | WP-5 |

---

## 15. Verification of this change and process notes

### 15.1 What was run

| Check | Command | Result |
|---|---|---|
| Only documentation changed | `git diff --stat`, `git status -s` | `docs/changes/0041-…` (new) and `docs/PRODUCT_BACKLOG.md` only; no file under `django_core/`, `fastapi_core/`, `frontend-*/`, `scripts/` or `static/` |
| Cited paths exist | `test -e` over every path named in §2.1 and §4.5 | all exist (§15.2 records the two that were wrong in the brief) |
| Test suite | `scripts/run_tests.sh sqlite` | run once at the end of this change; the result is reported verbatim in the session report. A documentation-only change cannot break a test, but the run is the evidence, not this sentence |

### 15.2 Process notes (deviations, stated rather than hidden)

1. **Branch base.** The standing rule is to branch from `phase-1/boot-security`. This branch was cut from
   `work/dual-frontend-integration` instead, because `main`/`phase-1/boot-security` do not contain `docs/changes/0040-…` or ADR-0014,
   both of which 0041 cites. The deviation is deliberate and reported; no push, no merge, no change to `main`.
2. **Requested path vs convention.** The brief named `docs-EIP/…-ROADMAP.md`. That directory does not exist here; the document lives at
   `docs/changes/0041-fast-path-ux-and-macro-data-PROPOSAL.md` per `docs/changes/README.md`. Recorded so the naming choice is not read
   as an oversight.
3. **Brief vs evidence.** The brief said the behaviour schema was in `students/models.py` and called it "Qalamestaan". The code path is
   `django_core/students/models.py`, and the only "Qalamestaan" material is `.docx`/`.pdf`/`.png` under `docs/qalamestaan/` with no
   transcribed field table — §4.4 states which schema was used instead and why.
4. **One conflict recorded, not fixed** (§2.2): the backlog claims attendance entry; there is no write path.

### 15.3 Truth labels applied in this document

- `CURRENT`: §2.1 (each row cites a file:line read on 2026-11-13), §2.2, §4.4's schema table, §4.5's `School` field list and the
  four-key entitlement statement.
- `TARGET`: every endpoint, screen, pipeline and model in §4 and §6–§8. None exists.
- `PROPOSED`: this document and the backlog pointer.
- `DECISION REQUIRED`: the 17 items in §14.6.
- `NOT VERIFIED`: performance, accuracy, real-device behaviour and adversarial re-identification resistance (§11, last paragraph).
- `DEFERRED`: WP-3 and WP-4 per §14.4, and the whole SPA question (ADR-0013 §4), which this document does not reopen.

### 15.4 Next step

The owner answers §14.6 — at minimum D-0.1 and which WP goes first. Then a new proposal for that WP, in the same folder, following
the same template, with its gates from §5.3.















