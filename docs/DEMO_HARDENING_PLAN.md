# DEMO HARDENING PLAN (DEMO SCOPE)

Status: approved by owner 2026-10-13; implemented in the same session (results recorded in `DEMO_GUIDE.md` / final report).
Scope: reliability and polish only. No FastAPI/RAG/LLM/ML, no Git, no change to `db.sqlite3`, no engine-logic or threshold change.

## Files

| # | Change | Files | Type | Expected impact | Risk |
|---|---|---|---|---|---|
| 1 | Safe launcher: sets `config.settings.demo`, fixed demo `SECRET_KEY` (generated once into gitignored `django_core/.env.demo`), `--noreload`, preflight, prints mode / DB / seed date, optional `--reseed`, refuses wrong settings, refuses stale seed | `scripts/start_demo.sh` (new), `demo_intel/management/commands/demo_check.py` (new) | new | Impossible to start the demo against `db.sqlite3`; sessions survive; stale data caught | Low. Script only calls existing commands |
| 2 | Seed stability: heroes' first **and** last names reserved; fillers deterministic (exactly 3 "emerging concern" fillers, all others bounded to Low); exact 2 / 7 / 31 | `students/management/commands/seed_demo.py` | edit | Same story on every seeding day | Medium: filler random stream changes → re-verified over 14 consecutive days |
| 3 | Demo login (standalone, vendored assets, DEMO banner) | `demo_intel/templates/demo_intel/login.html` (new), 1 DEMO SCOPE hook in `dashboard/views.py::login_view` | new + hook | First screen looks like a product, works offline | Low. Old login untouched outside DEMO_MODE |
| 4 | Assistant: ambiguous / unknown / improvement answers, whole-word name matching, "Rule-Based Prototype Assistant" label | `demo_intel/assistant.py`, `assistant.html` | edit | No silent wrong-student answers; story C explainable | Low; uses engine output + intervention kind/status/date only (no counseling text) |
| 5 | Persian digits & decimal separator in reasons, answers, chart labels; Persian rule names (no internal ids on screen); score legend; unsigned points | `demo_intel/{rules,engine,analytics,fa}.py`, `templatetags/demo_extras.py`, 5 templates | edit | Consistent Persian UI | Low |
| 6 | Parent view: skip in live demo; hide misleading AI button and dead Chat/Library links in DEMO_MODE only | `dashboard/templates/dashboard/student_detail.html`, `base.html` (2 DEMO SCOPE blocks) | edit | No fake-AI button on any demo screen | Low (`not DEMO_MODE` → unchanged outside demo) |
| 7 | Script and checklist | `docs/DEMO_SCRIPT.md` (rewrite), `docs/DEMO_PRESENTATION_CHECKLIST.md` (new), `docs/DEMO_GUIDE.md`, `docs/DEMO_SCOPE_MANIFEST.md` (updates) | docs | Business story for CEO / planning / counseling | None |
| 8 | Tests: start configuration, seed stability, assistant edge cases, permission preservation | `demo_intel/tests.py` | edit | Regression safety | Low |

## Risk assessment

* **Seed change (2)** is the only change that can alter what the room sees. Mitigation: verification loop over 14 consecutive "today" values asserting 2/7/31 and hero levels; documented hero list in the guide.
* **Hooks into existing files** stay inert unless `settings.DEMO_MODE`; the original 38 tests are re-run under the default settings.
* **Launcher** never writes to `db.sqlite3`; the preflight reads only the demo DB; `--reseed` runs `migrate` + `seed_demo --reset`, both guarded to `demo_db.sqlite3`.
* **NOT VERIFIED** after this work: visual rendering in a real browser (none available in the build environment).
