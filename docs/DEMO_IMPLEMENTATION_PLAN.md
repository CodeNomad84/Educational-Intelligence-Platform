# DEMO IMPLEMENTATION PLAN — Rule-Based Student Intelligence Prototype

Status: **PROPOSED — awaiting approval. No code has been written for this plan.**
Basis: audit in `docs/DEMO_STATUS.md` (2026-10-13). No Git operations are part of this plan; every change is a new file or a small additive edit, listed below so it can be reverted by deleting/restoring those files.

## 1. Scope in one paragraph

A Django-only demo slice: synthetic data in a **separate SQLite file**, a deterministic explainable risk engine, three screens (school dashboard, counselor dashboard, student intelligence card), and a keyword-driven "Educational Intelligence Assistant (Prototype)" that answers only from demo data. No FastAPI, RAG, Ollama, LLM, or ML model is called. Everything intelligent is labelled "Rule-Based Risk Analysis Prototype".

## 2. Design decisions (and why)

| Decision | Choice | Reason |
|---|---|---|
| Demo database | New settings module `config/settings/demo.py` (imports `development`, overrides `DATABASES.NAME` → `demo_db.sqlite3`, adds a `DEMO_MODE` flag). Run with `DJANGO_SETTINGS_MODULE=config.settings.demo`. | `db.sqlite3` is never opened by demo commands. `*.sqlite3` is already gitignored. |
| Seed safety guard | `seed_demo` aborts unless `settings.DEMO_MODE` is true **and** the DB file name is `demo_db.sqlite3`. `--reset` only flushes that DB. | Makes it impossible to seed/flush the real dev DB by mistake. |
| Where new models live | Existing empty app skeletons: `behavior` (Observation, CounselingNote), `interventions` (Intervention); `risk` holds the engine (no models). They are currently **not** in `INSTALLED_APPS`; I add them. | Fits MODULE_MAP intent ("zero rewrite"); one additive edit to `base.py`. Alternative: put all three models in `students` as migration `0008`. |
| Risk engine | Pure-Python functions in `risk/engine.py`; weights/thresholds in a dict in `risk/rules.py` (no school-specific values in logic). Returns `{level, score, reasons[], strengths[], recommendations[]}`. Each reason carries the rule id and the numbers used. | Explainable, testable, configurable. Grade scale assumed **0–20** (Iranian) — to be confirmed. |
| Counselor view | `/counselor/` restricted to the existing **Admin** role; `demo_counselor` user is placed in the `Admin` group. **No change to `students/access.py`, no new role, no RBAC bypass.** | Teacher→student scope (S-04) and a real Counselor role remain DECISION REQUIRED; documented as such in the guide. |
| Parent view | `demo_parent` keeps the existing scoped list/detail. Risk card is **staff-only**. | Showing risk labels to families is a policy decision not yet made. |
| Counseling notes & AI | Notes are seeded and shown to staff, but the **engine and assistant never read note text** — only that an intervention/meeting exists. | CLAUDE.md §7/§8: counseling data is not exposed to AI without an approved policy. Even though this is rule-based, we keep the boundary from day one. |
| Assistant | `risk/assistant.py`: intent matching by keywords (fa + en) → fixed query functions over the DB → templated answer. Unknown question → lists supported questions. Footer on every answer: "Generated from rule-based analysis. Human review required." | No LLM, no hidden predictions. |
| Front-end assets | Vendor Bootstrap 5 RTL CSS/JS + Chart.js into `dashboard/static/vendor/` (downloaded once). | Demo must not depend on meeting-room Wi-Fi. Fallback: keep CDN links. |
| Dates | Seed dates are relative to "today"; engine windows: last 30 days vs. previous 60 days. | Demo stays "live" whenever it is run. |

## 3. Database changes

All additive; applied **only** to `demo_db.sqlite3` unless you later choose otherwise.

| Model | App | Fields |
|---|---|---|
| `Observation` | behavior | student FK, date, category (participation / discipline / social / academic / positive), sentiment (positive / neutral / negative), note, recorded_by (nullable user FK) |
| `CounselingNote` | behavior | student FK, date, counselor (nullable user FK), summary |
| `Intervention` | interventions | student FK, type (counselor meeting / parent contact / tutoring / attendance plan), start_date, status (planned / active / completed), description, outcome |

New migrations are generated with `makemigrations` (files only; not applied to `db.sqlite3`). Existing tables (`Student`, `Grade`, `Attendance`) are **unchanged**.

## 4. Files

### Create
| File | Purpose |
|---|---|
| `django_core/config/settings/demo.py` | demo DB + `DEMO_MODE` + context processor |
| `django_core/students/management/{__init__,commands/__init__,commands/seed_demo}.py` | synthetic data (path as requested) |
| `django_core/behavior/models.py`, `interventions/models.py` + `migrations/0001_initial.py` (2) | models above (files exist but empty) |
| `django_core/risk/{rules,engine,assistant}.py` | rules, engine, prototype assistant |
| `django_core/dashboard/context_processors.py` | exposes `DEMO_MODE` to templates |
| `django_core/dashboard/templates/dashboard/{counselor,assistant}.html`, `_intel_card.html` | new screens / partial |
| `django_core/dashboard/static/vendor/…` | Bootstrap RTL, Chart.js (local copies) |
| `django_core/risk/tests.py`, additions to `dashboard/tests.py` | engine, permissions, seed guard |
| `docs/DEMO_GUIDE.md`, `docs/DEMO_SCRIPT.md` | as requested |

### Modify (small, additive)
| File | Change |
|---|---|
| `config/settings/base.py` | add `behavior`, `interventions`, `risk` to `INSTALLED_APPS` |
| `dashboard/views.py` | add `school_dashboard` data to `dashboard_view` (keep existing context keys), `counselor_view`, `assistant_view`; add intelligence card data to `student_detail_view` (Admin only) |
| `dashboard/urls.py` | `/counselor/`, `/assistant/` |
| `dashboard/templates/dashboard/base.html` | local assets, demo banner, nav links; chat link relabelled (the old FastAPI chat stays disabled) |
| `dashboard/templates/dashboard/dashboard.html`, `student_detail.html`, `student_list.html` | KPI cards + charts, intelligence card, risk badge in list |
| `behavior/admin.py`, `interventions/admin.py` | register models |
| `docs/DEMO_STATUS.md`, `docs/MODULE_MAP.md` | status update (MODULE_MAP only if you want it kept in sync) |

### Deliberately untouched
`students/access.py`, `dashboard/decorators.py`, all of `fastapi_core/`, `docker-compose.yml`, `.env*`, `db.sqlite3`, `students/models.py`.

## 5. Synthetic data (seed_demo)

- ~40 students, grades 9–11, 3–4 classes, fictional Persian names, national IDs from an obviously fake range (`9000000001…`), flagged by a **DEMO** banner and class labels.
- ~90 days of attendance, 6–8 subjects × 2 periods of grades, observations, counseling notes, interventions.
- Scripted storylines (named students, fixed seed so the demo is repeatable): high performer · attendance decline · grade deterioration · behavioural warning signs · improvement after intervention · stable low-risk (+ filler students with random but bounded noise).
- Demo users (password printed by the command; never stored in repo): `demo_admin` (Admin), `demo_counselor` (Admin group), `demo_parent` (Parent, linked to one child).

## 6. Risk rules (first draft, weights adjustable)

| Area | Rule | Points |
|---|---|---|
| Attendance | absence rate last 30 d exceeds the prior 60 d rate by ≥10 / ≥20 percentage points | +15 / +30 |
| Attendance | absence rate last 30 d > 15 % | +10 |
| Attendance | ≥5 late arrivals in 30 d | +5 |
| Academic | a subject's recent average fell ≥3 points vs. earlier (max 2 subjects counted) | +10 each |
| Academic | overall recent average < 12 / 20 | +15 |
| Behavior | negative observations in 30 d: ≥2 / ≥4 | +15 / +25 |
| Protective | active/completed intervention with improving trend; positive observations | −10 / −5 |

Level: `score < 30` LOW · `30–59` MEDIUM · `≥ 60` HIGH (clamped 0–100). Recommendations map from triggered rules (counselor meeting, parent communication, attendance plan, tutoring). Every output states: "Prototype — requires human review."

## 7. Implementation order & estimates

| # | Step | Est. |
|---|---|---|
| 1 | `demo.py` settings, models, migrations, admin | 1.5 h |
| 2 | `seed_demo` + guard + users | 2.5 h |
| 3 | Risk engine + rules + unit tests | 2.5 h |
| 4 | School dashboard + counselor dashboard (charts) | 3 h |
| 5 | Student intelligence card | 1.5 h |
| 6 | Prototype assistant + page + tests | 2 h |
| 7 | Vendor assets, RTL/Persian polish, demo banner | 1.5 h |
| 8 | Permission tests, full test run (existing 38 must still pass) | 1 h |
| 9 | DEMO_GUIDE, DEMO_SCRIPT, rehearsal, bug fixes | 2 h |
| | **Total** | **≈ 17–18 h** |

Cut line if time runs short: drop step 6's free-text matching to 3 fixed buttons; drop the counselor page (use a "needs attention" panel on the main dashboard).

## 8. Risks

| Risk | Mitigation |
|---|---|
| Looks like fake AI | Permanent labels: "Rule-Based Risk Analysis Prototype", "Human review required"; every reason shows the rule and numbers; guide scripts the honest answer to "is this AI?" |
| Seeding/flushing the real DB | Demo settings + guard in command; `db.sqlite3` never opened |
| Grade scale / thresholds wrong for this school | Config dict; confirm scale (0–20?) with you |
| Counselor = Admin role may be questioned | Stated openly in guide; real role is DECISION REQUIRED (S-04, ADR-0003) |
| Counseling-note sensitivity | Synthetic only; engine/assistant do not read note text |
| `INSTALLED_APPS` change affects non-demo runs | Additive, migrations unapplied there; revert = remove 3 lines |
| Persian dates | Shown as Gregorian ISO by default; optional ~30-line Jalali template filter (no dependency) if you want it |
| Existing tests regress | Existing dashboard context keys preserved; full suite re-run |
| CDN assets blocked | Vendored locally; download is a one-time step (needs internet once) |
| Repo has no commits / untracked tree | Out of scope by your instruction; nothing here touches Git |

## 9. Approvals requested

1. Approve this plan (L2 change) and the file list above.
2. Models in `behavior`/`interventions` apps (recommended) **or** all in `students` (0008)?
3. Counselor view under the Admin role for the demo — OK?
4. Allow downloading Bootstrap RTL / Chart.js once into `dashboard/static/vendor/` — OK?
5. Grade scale 0–20 — confirm.
6. Jalali date filter — yes / no?
