# DEMO STATUS — 48-hour school demo (audit only)

> **Update 2026-10-13 (DEMO SCOPE):** the plan in §7 was implemented as the Django-only slice described in
> `DEMO_IMPLEMENTATION_PLAN.md` (deviation: models live in a new self-contained `demo_intel` app because the
> `behavior/risk/interventions` skeletons turned out to hold TARGET models tied to `accounts.User`).
> Run/guide: `DEMO_GUIDE.md`; script: `DEMO_SCRIPT.md`; separation list: `DEMO_SCOPE_MANIFEST.md`.
> The findings below describe the state **before** that work.

Audited: 2026-10-13, branch `phase-1/boot-security`, working tree. No code was changed and no Git command that mutates state was run.
Labels per CLAUDE.md §2. Evidence = commands actually run in this session.

## 1. Verdict

**CURRENT:** the Django side boots and passes its tests; the product screens a school would care about (risk distribution, student risk reasons, AI explanation) **do not exist yet**. The shortest path to a convincing demo is a **Django-only demo slice with synthetic data and a deterministic "demo mode" explainer**; FastAPI/Ollama/RAG should not be on the demo's critical path.

## 2. Current working modules (CURRENT — verified)

| Module | Evidence |
|---|---|
| Django project boots (dev settings, SQLite) | `manage.py check` → 0 issues |
| Django test suite | `manage.py test` → 38 tests, OK |
| Login / logout, role gate (Admin, Parent), object-level scoping | `dashboard/views.py`, `students/access.py`, covered by tests |
| Student list (search) + student detail (grades table, attendance table, avg score, absences) | `dashboard/templates/dashboard/student_list.html`, `student_detail.html` |
| Basic dashboard: 4 counters (students, grades, attendance rows, school average) | `dashboard.html` |
| Student add form (Admin) | `student_create_view` |
| Bootstrap 5 RTL-ish Persian templates, Persian field labels | `base.html`; **loads Bootstrap from jsDelivr CDN** |
| Risk model artifacts exist (`student_risk_model.pth`, `scaler.joblib`) | files present in `fastapi_core/models/` |

## 3. Broken / blocked modules

| Item | State | Evidence |
|---|---|---|
| Dev DB schema | **2 pending migrations** (`students.0006_document`, `0007_rag_documents_table`) + `dashboard.0001`; any query touching `Document` fails | `showmigrations`; `OperationalError: no such table: students_document`. Not migrated: that mutates the owner's `db.sqlite3` — needs your OK. |
| FastAPI service | Does not start in its venv: `ModuleNotFoundError: No module named 'jwt'` | `fastapi_core/.venv`, `auth.py` import |
| FastAPI tests | Fail for the same reason | `unittest discover` → 1 error |
| RAG chat / document search / ingestion | **Disabled by design in Phase 1** (`disabled_in_phase1` → 403 for every role) | `fastapi_core/auth.py:91`, `main.py:141-184` |
| Ollama | Daemon is running but has **zero models pulled** | `curl :11434/api/tags` → `{"models":[]}` |
| Risk "prediction" button | Needs FastAPI (broken above); Admin only; the model is a PROTOTYPE trained on a synthetic label (A-01) and the 8 inputs include **hard-coded constants** (`avg_completion_rate=0.8`, `completed_homework=12`, `total_communications=3`) | `dashboard/views.py:~95-110` |
| Docker stack | Not run (8 services, needs Postgres/Redis/MinIO). Not needed for the demo. | NOT VERIFIED |
| Upload students page | Template `dashboard/upload.html` does not exist; view only flashes a fake success | `dashboard/views.py` upload_students_view |
| `Homework`, `TeacherParentCommunication` models | Defined, now have a migration, but unused by any view | `dashboard/models.py` |

## 4. Data state

`db.sqlite3` holds **2 students, 3 grades, 3 attendance rows**, 3 users (`aispace` superuser, `admin` [Admin], `teacher1` [Teacher, but flagged superuser]). The two student names look like real/personal names — **do not demo from this DB**; use a separate synthetic DB (see plan).

## 5. Demo-ready vs. gap against the requested scope

| Requested | Status | Gap |
|---|---|---|
| Student dashboard: count, class overview, risk distribution, growth, recent alerts | **Partial** — count only | No class breakdown, no risk, no growth, **no Alert/Risk/Observation models at all** (`risk/`, `behavior/`, `interventions/`, `academics/` apps have empty `models.py`) |
| Student profile: info, attendance, grades, behavior, risk + reasons | **Partial** — info, grades, attendance only | No behavior data, no risk level, no human-readable reasons, no trend (drop %) |
| AI assistant (why at risk / intervention / summary) | **Missing for demo** | RAG disabled + no LLM model; needs a demo-mode explainer |
| Teacher/counselor dashboard | **Blocked by policy** | `visible_students()` returns **no students for Teacher** (S-04, DECISION REQUIRED). No Counselor role exists. |
| Persian/RTL, professional look | **Partial** | Bootstrap LTR bundle with `dir="rtl"`? (verify in browser); CDN needs internet in the meeting room |
| Synthetic data labelled as demo | **Missing** | no seed command |

## 6. Conflicts with project rules you should decide before I code

1. **Change level.** New risk logic, new models (Observation, Alert) and an AI demo mode are **L2** in `CLAUDE.md` §6 (proposal + owner approval). Your prompt asks me to present the plan first, so this document is that proposal; I will treat your approval of the plan as the L2 approval for the items in §7 only.
2. **Teacher access (S-04).** A Teacher dashboard requires either (a) a demo-only teacher→class assignment, or (b) showing the staff dashboard under the `Admin` role. I recommend (b) for 48 h: log in as a clearly-named demo user holding **Admin** (or a new `Counselor` group with the same read scope limited to the demo school). No RBAC bypass is added.
3. **"Demo mode" AI.** Fixed-template answers must be visibly labelled "DEMO — rule-based explanation, not a live model" to comply with AI_GOVERNANCE (advisory, labelled, uncertainty shown). It must not be presented as a real LLM.
4. **Do not enable the Phase 1-disabled RAG routes** for the demo; keep `disabled_in_phase1` intact.
5. Risk scoring in the demo will be **deterministic rules** (consistent with "rules before ML"), not the prototype neural net.

## 7. Recommended 48-hour plan (smallest path)

**Day 1 (≈8 h) — data + logic**
1. (30 min) Create a **separate demo SQLite DB** via an env-selected settings override (no change to dev DB), run migrations on it. *Needs your OK for running `migrate` on that new file only.*
2. (2 h) `seed_demo` management command: ~40 synthetic students across 3–4 classes, 15 subjects → 2 terms of grades, 90 days attendance, with 4–5 planted storylines (e.g. "علی احمدی": attendance −20 %, math down, participation down). Names flagged `DEMO`. New small `Observation` model (participation/behaviour) — 1 migration.
3. (2 h) `risk/services.py`: deterministic rule engine → level (Low/Medium/High) + list of reasons with the numbers (attendance Δ, subject score Δ, participation Δ). Unit tests.
4. (1 h) Fix the hard-coded constants issue by simply not using the NN in the demo path.
5. (1 h) Demo users: `demo_admin`, `demo_counselor` (Admin scope), `demo_parent`.

**Day 2 (≈8 h) — screens + AI + docs**
6. (2.5 h) Dashboard v2 in the existing `dashboard.html`: KPI cards, class table, risk-distribution doughnut + growth bar (Chart.js **vendored locally** so it works offline), recent-alerts list (computed from rules, no new Alert table).
7. (2 h) Student profile v2: header card, risk badge + reasons, attendance & score trend charts, observations.
8. (1.5 h) "AI assistant (demo mode)" panel on the profile: three buttons (why at risk / recommended intervention / summary) → server-side templates fed by the real computed numbers, with "DEMO — rule-based" label, uncertainty note and "requires human review".
9. (1 h) Persian/RTL polish + vendor Bootstrap RTL CSS locally.
10. (1 h) `DEMO_GUIDE.md`, `DEMO_SCRIPT.md` (10-min flow), rehearsal run, fix blockers only.

**Explicitly out of scope:** Docker/Postgres, FastAPI, Ollama/RAG, React, real data, CI, git operations.

## 8. Risks to the demo

- Meeting-room internet → mitigated by vendoring Bootstrap/Chart.js.
- Someone asks "is the AI real?" → be honest: it is a rule-based explainer; the roadmap (P7) adds RAG. Do not claim otherwise.
- The synthetic storylines are scripted; say so.
- Repository has no commits and the branch is not clean (all files untracked) — nothing in this plan touches Git; commit hygiene remains your task.

## 9. Decisions I need from you (DECISION REQUIRED)

1. Approve the Django-only demo slice (§7) as the L2 change?
2. Create the separate demo DB and run migrations **only on it**? (Yes/No)
3. Teacher/counselor view: demo user with Admin scope (recommended) or something else?
