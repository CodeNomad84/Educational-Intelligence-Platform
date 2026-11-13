# DEMO READINESS REVIEW (DEMO SCOPE)

Reviewed: 2026-10-13. Scope: hardening only — no new features, no engine redesign, no Git, no touch of `db.sqlite3`.
Status: **review only; no code or seed changes made.** Recommended changes are in §7 and wait for approval.

## 0. How this was checked (evidence)

| Method | What |
|---|---|
| Rendered pages via Django test client against the demo DB | login template, parent pages, admin pages, assistant answers |
| Scratch-DB simulation (`scratchpad/drift.py`; real DBs untouched) | re-seed on 7 consecutive days; show a DB N days after seeding |
| Template/code reading | layout, labels, RTL, navigation |
| **NOT VERIFIED** | actual visual rendering in a browser (none available here) — layout, RTL alignment, chart look, projector legibility |

## 1. Current demo flow and where it can break

| Step | Page | State |
|---|---|---|
| 1 Login | `/` (old template + old base, **CDN Bootstrap**, old sidebar) | works; first impression is the *old* UI (see I-3) |
| 2 Management dashboard | `/dashboard/` | works; KPIs, 3 charts, attention list, class table |
| 3 Risk overview | same page + `/demo/students/` | works; filter by level/class/name |
| 4 Counselor workflow | `/demo/counselor/` | works; 9 cases with reasons + actions |
| 5 Student profile | `/students/<id>/` | works for staff |
| 6 Assistant | `/demo/assistant/` | works for supported phrasings; see I-5 |
| Optional: parent view | `/students/` → old UI | works but exposes old-UI problems (I-4) |

## 2. Findings

### CRITICAL — can embarrass or derail a live presentation

**C-1 Wrong settings module shows the dev database, not the demo.**
`manage.py` defaults to `config.settings.development`. If the presenter forgets `export DJANGO_SETTINGS_MODULE=config.settings.demo`, the app starts normally and shows `db.sqlite3` (2 students whose names look like real people, no risk data, old dashboard). Nothing on screen says "wrong database".
*Fix:* one start script that sets the module itself (+ prints which DB it uses); checklist item "banner must read DEMO".

**C-2 Seed data goes stale: the storylines decay within days.**
Seeding is relative to the seeding date, the engine to *today*. Evidence (scratch DB, same seed shown N days later):

| Shown | High / Med / Low | Ali (story B) | Reza | Sina |
|---|---|---|---|---|
| day 0 | 2 / 7 / 31 | Medium 50 | High 90 | High 90 |
| +3 d | 2 / 7 / 31 | Medium 35 | High 80 | High 90 |
| +7 d | 2 / 4 / 34 | **Low 10** | High 80 | High 75 |
| +14 d | 1 / 4 / 35 | Low 10 | **Medium 50** | High 60 |
| +30 d | 0 / 2 / 38 | Low | Low 15 | Medium 35 |

Re-seeding on any single day is stable (7 consecutive days all gave 2/7/31, Ali Medium, Reza & Sina High, Mahsa/Arian Low).
*Fix:* re-seed on the day of the meeting (checklist), and add a "data freshness" line to the start script output.

### IMPORTANT — would be noticed by the audience or force improvisation

**I-1 Two "Ahmadi" students in the same class as the hero case.**
Random filler produced **مریم احمدی, ۱۰-الف, Medium 55**, next to **علی احمدی, ۱۰-الف, Medium 50**. In the attention list both appear adjacent; the assistant question "چرا احمدی…" silently answers for Ali.
*Fix:* exclude scripted last names from filler generation (seed tweak; changes the random stream → re-verify distribution).

**I-2 Mixed Latin/Persian digits and decimal separators.**
Reason texts come from the engine with Latin digits (`27٪`, `15.4`, `25 واحد درصد`) while KPIs use Persian digits (`۴۰`). Same in assistant answers and chart axis/labels. Verified in rendered HTML.
*Fix:* pass reason/answer text through the existing `fa` filter in templates (and `Chart.js` tick callback); no engine change.

**I-3 Login page is the old UI.**
`login.html` extends the old `base.html`: CDN Bootstrap (unstyled if the room has no internet), the old dark sidebar with links that bounce back to login, no DEMO banner or product name. It is the first thing the CEO sees.
*Fix:* give login a small standalone demo template (same vendored assets) shown only in DEMO_MODE.

**I-4 Parent view exposes old-UI problems (verified).**
Parent detail page: CDN-dependent, shows the "🤖 پیش‌بینی وضعیت با هوش مصنوعی" button (contradicts "no fake AI"; click does nothing for parents), sidebar links to Chat and Library that return 403, no demo banner.
*Fix options:* (a) zero-code: drop the parent segment from the live script, keep it for Q&A only; (b) small: in DEMO_MODE render parents through a demo template with no risk card, no AI button, no dead links.

**I-5 Assistant: edge handling that can surprise a live questioner** (all run):
* "چرا احمدی…" → answers for one of two students without saying so.
* "چرا علی در معرض خطر است؟" (first name only) and "why is Ali Ahmadi at risk" (English) → silently returns the generic attention list.
* "بهترین دانش‌آموز کیست؟" → declined (fine, but a natural executive question).
* "مهسا فرهادی چطور بهتر شد؟" → generic info, not the improvement explanation — **the improvement story (C) is the weakest on screen**.
*Fix:* keyword-config only: ask "which student?" when a name is ambiguous; say "student not recognised" instead of falling through; add improvement keywords (بهتر، بهبود، improve) to the existing "why" intent.

**I-6 Technical wording on executive pages.**
Profile shows rule ids (`قاعده: attendance_shift`); level thresholds (30/60) and the meaning of "امتیاز" appear nowhere on screen; the CEO's first question will be "این عدد از کجا آمده؟".
*Fix:* map rule ids to short Persian names; add one static line "امتیاز = جمع قواعد؛ ۳۰–۵۹ نیازمند توجه، ۶۰+ پرخطر".

**I-7 Sessions die on restart.**
Demo settings inherit the dev behaviour: a random `SECRET_KEY` per process, and `runserver` auto-reloads on file changes. A restart (or editing a file) logs everybody out mid-demo.
*Fix:* start script uses `--noreload` and a fixed `SECRET_KEY` for the process (value generated once by the script, not committed).

**I-8 Script numbers are fragile.**
`DEMO_SCRIPT.md` quotes exact values ("۷٪ → ۱۸٪", "۱۵٫۳ → ۱۰٫۶"). They depend on seeding day and on any seed change (I-1 changes them).
*Fix:* script says "read the two numbers on screen"; or freeze them after the final seed.

### NICE TO HAVE

* **N-1** `DEBUG=True`: any error shows the Django debug page; e.g. typing `/upload/` → `TemplateDoesNotExist` (verified; old bug, not linked from the demo nav). Rehearse; do not type URLs; or later set `DEBUG=False` with `--insecure`.
* **N-2** 4th KPI card label is overloaded ("میانگین نمرات اخیر … · غیبت …"): split into two cards.
* **N-3** Doughnut legend without counts; add counts to legend labels.
* **N-4** Reason points shown as "۳۰+ امتیاز" (sign placement can flip in RTL): show "۳۰ امتیاز".
* **N-5** Terminology varies: «نیازمند توجه» (level), «نیازمند بازبینی» (counselor/assistant). Pick one.
* **N-6** Counselor cards: add one line explaining "پیشنهاد، نه تصمیم" (exists in footer; move under the title).
* **N-7** Improvement story has no entry point on the management dashboard (Mahsa is Low, so not in the attention list). Open from the student list (`?q=مهسا`) — script-only.
* **N-8** Port 8000 clash if the Docker stack (`docker-compose`) is up; checklist item.
* **N-9** Counseling summaries are shown on profiles with a "confidential" header; fine for synthetic data, but say "synthetic" aloud.

## 3. Presentation scenario (Step 2) — proposed, not yet rewritten

Audience: School CEO · Planning manager · Counseling-center manager. No technical terms (no "rule engine", RBAC, RAG, API).

| Min | Beat | On screen | Line for the room |
|---|---|---|---|
| 0–1.5 | **Problem** | login → dashboard (don't scroll) | "Thousands of data points — attendance, grades, observations — and no early-warning view." |
| 1.5–4 | **1. School overview** | KPIs + risk doughnut + trends | CEO: "one-glance status". Planning: "trend by week and class". |
| 4–6 | **2. Who needs attention** | attention list → counselor dashboard | Counselor: "prioritised list instead of searching files". |
| 6–8 | **3. Why + 4. Intervention** | **Student A** (Reza): reasons, numbers, actions; quick contrast **Student C** (Mahsa): "after the intervention it improved" | "Every score is explained; the counselor decides." |
| 8–9 | **Assistant** | one question, answered with a list | "Ask in plain words; answers only from your data." |
| 9–10 | **5. Roadmap + ask** | roadmap slide/table | "Now: transparent early-warning on synthetic data. Next: your real data under your data policy. Later: document search and AI summaries — always advisory." Close with 3 questions to the room. |

Role hooks (one question each): CEO — "which decisions would you want this to support weekly?"; Planning — "which indicators/periods do you report on?"; Counseling — "which actions do you actually take, and what is missing from the suggestions?"

## 4. Synthetic data story review (Step 3)

| Story | Student | Now | Verdict |
|---|---|---|---|
| A — High, clear reasons, intervention | رضا کاظمی (۹-ب) | High 90: 5 reasons, planned parent contact + 1 referral note | **Good.** Alternate: سینا باقری (High 90). |
| B — Medium, early warning | علی احمدی (۱۰-الف) | Medium 50: absence ↑, maths ↓, 2 participation observations | **Good**, but confused by مریم احمدی (I-1) |
| C — Improvement after intervention | مهسا فرهادی (۱۰-ب) | Low 0; "improving after counselor meeting" + 2 positive observations | Data fine; **presentation weak** (I-5, N-7): not on attention list, assistant doesn't explain improvement |
| D — Excellent | آرین جعفری (۱۱-الف) | Low 0; 3 positive observations; avg ≈ 18 | **Good** |

Seed adjustments proposed: only the filler-name exclusion (I-1). No scenario numbers need to change. Engine logic: **no serious bug found**; the observed drift (C-2) is inherent to a "last 30 days" design, not a defect.

## 5. Visual quality (Step 4) — from template review, NOT visually verified

Good: vendored Bootstrap RTL + Vazirmatn (works offline), consistent card/badge system, one colour per level, banner and prototype label on every demo page, `dir="rtl"`.
Small fixes only: I-2, I-3, I-6, N-2, N-3, N-4, N-5. Legibility on a projector (font sizes, contrast of the muted text, 1366×768 layout) must be checked once on the presentation machine.

## 6. Presentation checklist (Step 5) — outline; file created after approval

* **Before:** `start_demo` script (settings + fixed secret + noreload) · `migrate` + `seed_demo --reset` **on the meeting day** · confirm DEMO banner, 40 students, 2/7/31 · log in once per role · browser: full screen, zoom 100–110 %, bookmarks for 6 URLs, extra tab on the student profile of Reza and Mahsa · offline test (Wi-Fi off) · port 8000 free · backup: screenshots/PDF of the 6 screens + a recorded run.
* **During:** exact navigation list with the expected result per page (counts: 40 / 2 / 7 / 31; Reza High; Ali Medium; Mahsa Low with "improving").
* **After:** feedback questions (3 per role), what they asked that the demo could not answer, next-step owner/date.

## 7. High-risk threshold decision (Step 6)

Current: **2 High / 7 Medium / 31 Low** (5 % / 17.5 % / 77.5 %).

**Recommendation: A — keep the distribution; do not inflate.**
* It is already on the generous side for a school (22 % flagged); more High cases would look alarmist and invite "is this realistic?".
* The story needs *clarity*, not volume: two urgent cases with five reasons each, seven early-warning cases, one visible success, one excellent student already cover A–D.
* Lowering the High threshold would be tuning to the demo, not to the data — the opposite of the explainability promise.
* What *does* strengthen the story is robustness and presentation (C-2, I-1, I-5 for story C), not different numbers.
Revisit only if rehearsal shows the room cannot see the contrast between Reza (High) and Ali (Medium) — then add one more scripted High with a different pattern, not a threshold change.

## 8. Recommended small changes (awaiting approval)

| # | Change | Files | Size | Fixes |
|---|---|---|---|---|
| 1 | `scripts/start_demo.sh`: sets settings module, fixed secret, `--noreload`, prints DB path & seed date | new, `django_core/` | S | C-1, I-7, N-8 |
| 2 | Seed: exclude scripted last names from filler; re-verify distribution & storylines | `seed_demo.py` | S | I-1 |
| 3 | Persian digits for reason/assistant text and chart ticks | templates, `demo_extras.py` | S | I-2 |
| 4 | Demo login template (vendored assets, banner, product name) | new template + 1 hook line | S | I-3 |
| 5 | Rule-id → Persian names; add "score legend" line | `rules.py`, 2 templates | S | I-6 |
| 6 | Assistant: ambiguity prompt, "not recognised", improvement keywords | `assistant.py` | S | I-5 |
| 7 | Parent view via demo template (or script-only workaround) | 1 template + hook | S | I-4 |
| 8 | Split KPI card, legend counts, remove "+" from points, unify term | templates | S | N-2..N-5 |
| 9 | Rewrite `DEMO_SCRIPT.md` per §3; add `DEMO_PRESENTATION_CHECKLIST.md`; make guide say "re-seed on meeting day" | docs | S | C-2, I-8 |
| 10 | Tests for 2, 6, 7 (+ re-run all 50) | `demo_intel/tests.py` | S | regression |

Not proposed: engine/threshold changes, new pages, FastAPI/RAG, Git actions, any change to `db.sqlite3`.
