# DEMO GUIDE — Rule-Based Student Intelligence Prototype

> **DEMO SCOPE.** Everything here belongs to the school-meeting demo slice (see `DEMO_SCOPE_MANIFEST.md`).
> All students, grades, attendance, observations and counseling notes are **synthetic**. No real student data.
> The "intelligence" is a **rule-based, explainable prototype** — not an LLM, not machine learning.

## 1. Start (one script)

From the repository root:

```bash
DEMO_PASSWORD='<choose one>' scripts/start_demo.sh --reseed    # migrate + synthetic data (do this on meeting day)
scripts/start_demo.sh                                         # start (127.0.0.1:8000, no auto-reload)
scripts/start_demo.sh --check                                 # preflight only
```

The launcher always uses `config.settings.demo` (database `demo_db.sqlite3`), refuses to start if another settings
module is exported, generates a fixed demo secret key once (`django_core/.env.demo`, gitignored) so logins survive a
restart, runs `demo_check`, and prints:

```
DEMO MODE ACTIVE
Database:  demo_db.sqlite3
Students:  40
Seed date: <date> (age 0 day(s))
```

It **refuses** to start when the seed is older than one day (`DEMO_ALLOW_STALE=1` overrides), because the
"last 30 days" storylines drift as time passes (a 7-day-old seed turns Ali Low). Re-seeding on any single day is
stable: 2 High / 7 Medium / 31 Low and the same hero levels on 14 consecutive days (verified).
`DEMO_PORT` changes the port. Open <http://127.0.0.1:8000/>; no Docker, FastAPI, Ollama or internet is needed.

Manual equivalent (advanced): `DJANGO_SETTINGS_MODULE=config.settings.demo` + `manage.py migrate`,
`seed_demo --reset --password …`, `demo_check`, `runserver --noreload` from `django_core/`.

## 3. Demo users

| Username | Group | What it shows |
|---|---|---|
| `demo_admin` | Admin | School dashboard, counselor dashboard, student list/profiles, assistant |
| `demo_counselor` | Admin (see note) | Same pages; used to narrate "the counselor's view" |
| `demo_parent` | Parent | Own child only, no risk card. **Not part of the live demo**: the family portal is a future phase (the old parent page is minimal; its AI button and dead links are hidden in demo mode) |

Password: the one you passed to `--password` (or printed by `seed_demo`).
Note: there is no Counselor role yet and teacher→student scoping is an open decision (S-04). For the demo the
counselor user simply holds the existing **Admin** role. No permission rule was relaxed.

## 4. Pages

| URL | Who | Content |
|---|---|---|
| `/` (login) | everyone | Standalone demo login: banner, local assets, no old sidebar |
| `/dashboard/` | Admin | KPIs, risk distribution, weekly absence trend, score trend, class table, students needing attention |
| `/demo/counselor/` | Admin | Medium/High cases with reasons, suggested actions, existing interventions |
| `/demo/students/` | Admin | Filterable list (class, level, name) with risk badges |
| `/students/<id>/` | Admin → intelligence card; Parent → original page (own child only) | Level, score, strengths, concerns with rule + numbers, actions, trends |
| `/demo/assistant/` | Admin | Prototype Q&A over the analysis results |

## 5. Demo characters (synthetic; verified identical on 14 consecutive seeding days)

Each hero's first **and** last name is reserved, so no filler student shares a name with a hero.

| Story | Student | Class | Level (score on a typical day) | Key reasons |
|---|---|---|---|---|
| A — High, clear reasons | **رضا کاظمی** | ۹-ب | High (75–90) | attendance fall, high absence, maths fall, negative observations |
| A′ — High (alternate) | سینا باقری | ۱۱-الف | High (75–90) | + physics fall, low average |
| B — Medium, early warning | **علی احمدی** | ۱۰-الف | Medium (50) | attendance fall, maths fall, participation observations |
| Medium | پارسا نوری | ۱۱-الف | Medium (50) | grade deterioration |
| Medium | نیلوفر موسوی | ۹-ب | Medium (45) | attendance decline, lateness |
| Medium | آرمان رحیمی | ۹-الف | Medium (30) | behavioural observations, lateness |
| Medium (filler) | نیما یوسفی · الهام مرادی · فاطمه ملکی | ۹-الف · ۱۰-ب · ۱۰-ب | Medium (40) | emerging concern |
| C — improved after intervention | **مهسا فرهادی** | ۱۰-ب | Low (0) | "improving after intervention", positive observations |
| D — excellent | **آرین جعفری** | ۱۱-الف | Low (0) | high average, positive observations |
| Stable | کیان صادقی | ۱۰-ب | Low (0) | — |

The other 31 students are generated from a fixed seed and are bounded to Low. Distribution: **2 High / 7 Medium / 31 Low**.

## 6. How the risk score works (say this out loud)

Points come from named rules (`demo_intel/rules.py`), each returned with the numbers that triggered it:

| Area | Rule | Points |
|---|---|---|
| Attendance | absence rate up ≥ 10 / ≥ 20 percentage points vs. the previous 60 days | +15 / +30 |
| Attendance | absence rate > 15 % in the last 30 days | +10 |
| Attendance | ≥ 5 late arrivals in 30 days | +5 |
| Academic | a subject's recent average fell ≥ 3 points (max 2 subjects) | +10 each |
| Academic | recent average < 12 / 20 | +15 |
| Behaviour | ≥ 2 / ≥ 4 negative observations in 30 days | +15 / +25 |
| Protective | improving trend after an intervention | −10 |
| Protective | ≥ 2 positive observations | −5 |

Levels: score ≥ 60 **High**, 30–59 **Medium**, < 30 **Low**. Thresholds are **demo assumptions**, to be calibrated with the school.

## 7. Boundaries built into the demo

* The engine and the assistant **never read counseling-note text**; they only know that an intervention exists.
* Every intelligence page is labelled *Rule-Based Risk Analysis Prototype — human review required*.
* The assistant ("Rule-Based Prototype Assistant") answers a fixed set of question types from the analysis results; ambiguous names ask for the full name, unknown names/questions are declined, English-written names are not recognised.
* Risk cards are staff-only; parents do not see them (policy for families is undecided).
* The existing FastAPI/RAG chat stays disabled (Phase 1). It is not part of the demo.

## 8. Reset / remove

* Re-seed: `seed_demo --reset` (affects only `demo_db.sqlite3`).
* Throw away the demo data: delete `django_core/demo_db.sqlite3`.
* Remove the demo slice entirely: see `DEMO_SCOPE_MANIFEST.md`.

## 9. Tests

```bash
cd django_core
DJANGO_SETTINGS_MODULE=config.settings.demo .venv/bin/python manage.py test          # 69 tests (original + demo + hardening)
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python manage.py test   # 38 original run, demo tests skipped
```
Hardening tests cover: launcher / configuration guard, seed stability across a week (distribution + hero levels +
unique hero names), assistant edge cases (ambiguous, unknown, improvement), Persian digits / no internal ids,
demo login without CDN, no AI button on the parent page, and preserved permissions.

## 10. Known limitations (be upfront)

* Not visually verified in a real browser during development (no browser available in the build environment);
  rehearse once on the presentation machine. Responses and static assets were verified via HTTP.
* Dates are Gregorian (ISO) shown with Persian digits. No Jalali calendar yet.
* Charts need JavaScript (vendored locally). Grade scale assumed 0–20.
* Not a validated educational instrument; do not present risk labels as diagnoses.
