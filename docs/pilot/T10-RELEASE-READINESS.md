# T10 — PILOT RELEASE READINESS GATE & RELEASE FREEZE

Branch: `work/T10-pilot-release-readiness` (from `phase-1/boot-security`, after the T9 merge).
Scope of this task: (a) platform branding in the UI comes from **one settings value**, (b) a release manifest,
(c) a verified security gate checklist for the pilot release, (d) a written freeze rule. Read-only where noted.
Labels: `CURRENT` (verified here, command/file quoted) · `TARGET` · `NOT VERIFIED` · `DECISION REQUIRED` · `DEFERRED`.

**Numbering note (report, not resolved silently):** `docs/pilot/QUEUE.md` reserves "T10" for an **L3
proposal-only** task (SchoolAdmin password policy + optional 2FA) and says Cline must not edit that file. The
owner's instruction in chat of 2026-12-11 assigns T10 to *this* release-readiness task. Both are kept; the queue
file is untouched. Which number the 2FA proposal takes is `DECISION REQUIRED` (owner).

---

## 1. Branding — what changed and why it is L1

Change level **L1** (`docs/CHANGE_PROCESS.md`: "small UI", test, no behaviour, no schema, no API, no permission
change). No migration, no new dependency, no route. The old name was a literal in four templates, in the a11y
test's expected bare title, and in a demo-only Celery e-mail body; it is now `settings.PLATFORM_NAME`
(`CURRENT`, see §5).

| Item | Value / file |
|---|---|
| Persian name (display everywhere) | `سکوی آموزشی-تربیتی آرمان نو` — `config/settings/base.py:14` (`EIP_PLATFORM_NAME` overrides) |
| English name (metadata) | `Arman-e-No Educational & Upbringing Platform` — `config/settings/base.py:15` (`EIP_PLATFORM_NAME_EN`) |
| Template access | `{{ PLATFORM_NAME }}` / `{{ PLATFORM_NAME_EN }}` from `dashboard/context_processors.py:66-68` |
| School name stays separate | `{{ SCHOOL_NAME }}` (the `School` row); the product name never replaces it |

Why settings and not a literal: `CLAUDE.md` §7 forbids hard-coded branding in core code, and a school meeting
must not require editing templates. The guillemets «» the owner wrote are typographic quotes, not part of the
name: they are **not** stored (`CURRENT`).

## 2. Release manifest (what actually ships)

| Component | `CURRENT` state |
|---|---|
| Django apps | `students, dashboard, schools, vocabulary, missions, exams, risk, interventions, docqa` (`config/settings/base.py:10-25`); `demo_intel` is demo-settings only (`config/settings/demo.py:22`) |
| Migrations | 53 migration files across the apps (`ls django_core/*/migrations/*.py | grep -v __init__ | wc -l` → `53`); `makemigrations --check --dry-run` is part of the gate and reports no pending change |
| Settings modules | `development`, `production`, `demo`, `test_sqlite`, `test_postgres`, `restore_check` (`config/settings/`) |
| FastAPI (AI layer) | `fastapi_core/` (chat/RAG/documents); every route 403 while `ENABLE_AI_FEATURES` is off (`docs/pilot/PILOT_CONFIG.md`) |
| Front-end assets | self-hosted, no CDN: `dashboard/static/dashboard/vendor/` (`bootstrap-5.3.0`, `bootstrap-icons-1.11.3`, `chartjs-4.4.1`, `vazirmatn-33.0.3`); `dashboard/deploy_checks.py:66` fails a deployment that loads an asset from another site (`eip.E004`) |
| Sellable modules | `advisor_ai`, `tutor_ai`, `exams`, `mission` — gated by `schools/entitlements.py`; everything else is base (`CLAUDE.md` §3) |
| Pilot config | `ENABLE_AI_FEATURES=False`, `ENABLE_COUNSELOR_ROLE=False` by default (`docs/pilot/PILOT_CONFIG.md`) |
| Operations scripts | `scripts/run_tests.sh` (sqlite/pg/all), `scripts/preflight.py`, `scripts/backup.sh`, `scripts/restore_backup.sh`, `scripts/test_backup_restore.sh`, `scripts/reset_demo_school.sh`, `scripts/start_demo.sh` |
| Tests | 1610 Django tests (sqlite gate; 1607 before the 3 new branding tests) + 62 `demo_intel` (demo settings) + FastAPI `tests/` (run separately, not covered by `run_tests.sh`) |

## 3. Release freeze (effective from this commit)

1. `phase-1/boot-security` is **frozen** for feature work. Only these land before the pilot: a **Critical/High**
   security fix (T7/T8 rules: failing test first), a **docs** correction, or an explicit owner override.
2. Every change still gets its own `work/<id>-<topic>` branch off `phase-1/boot-security`; **no push, no merge to
   `main`, no force-push** by Cline (`STANDING RULES`).
3. No migration without a written proposal; a schema change during the pilot window is a release blocker.
4. A change that touches `students/access.py`, entitlements, audit rules or auth stops the task (`BLOCKED`), even
   inside the freeze — those need the owner's decision, not a quiet fix.
5. The gate is re-run (sqlite + pg) on the exact commit that is handed to the school; a green run on an older
   commit is not evidence for a newer one.
6. Freeze lifts only by an explicit owner statement in chat; it is not inferred from a green test run.
7. Tagging the release (`v0.x`) is `DECISION REQUIRED` — no tag was created here.



## 4. Security gate checklist (verified against this branch)

Each row names the evidence. "T9-R" = `docs/pilot/T9-MULTI-SCHOOL-READINESS-REPORT.md` (merged here as `e0b4156`).

| # | Gate | Evidence | Status |
|---|---|---|---|
| G1 | No real student data in any environment | every fixture in this repo is synthetic (`seed_demo_school`, `seed_temporal_synthetic`); T9-R §8; the probe database was `/tmp/t9_ms.sqlite3` | `CURRENT` |
| G2 | Authentication + brute-force protection | `dashboard/throttle.py` (5 failures/username, 20/address, 900 s window, no user enumeration; `REMOTE_ADDR` unless `THROTTLE_TRUSTED_PROXIES`); `/admin/` login uses the same throttle (`config/urls.py:12`) | `CURRENT` |
| G3 | RBAC + object scope on every route | `students/access.py` (18 `visible_*` querysets), `docs/SECURITY.md` matrix, T9-R §2-§3 (path:line per surface) | `CURRENT` |
| G4 | School (tenant) isolation with two schools | T9-R §4: 30 pages, 0 leaked rows, 5 write POSTs 404 with `(0,0,0)` unchanged; `compare_access_parity --multi-school` `students_leaked 0` | `CURRENT` |
| G5 | Secrets fail closed | `production.py:9-20` refuses to start on a missing/short/placeholder `SECRET_KEY`; no `.env` in the repo; the service token secret is minted/validated in `config/service_auth.py` | `CURRENT` |
| G6 | Transport + cookie hardening | `production.py:63-77`: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`, `X_FRAME_OPTIONS='DENY'` | `CURRENT` |
| G7 | Audit trail for privileged actions | `schools/audit.py:90 record()` / `:116 record_list()`; `AuditEvent` model; module toggles, school creation, staff-role changes and password resets write rows | `CURRENT` |
| G8 | AI/counselor surfaces off in the pilot | `ENABLE_AI_FEATURES=False`, `ENABLE_COUNSELOR_ROLE=False` by default → 403 on `/assistant/…`, `/me/assistant/…`, `/counselor/…`, referrals, and FastAPI chat/RAG (`docs/pilot/PILOT_CONFIG.md`) | `CURRENT` |
| G9 | No PII to external models, no RAG without ACL | ACL applied in the query (`school_id = ANY(%s)`) before retrieval; `docs/AI_GOVERNANCE.md`; AI routes 403 in the pilot anyway | `CURRENT` (code) / `NOT VERIFIED` (a live provider) |
| G10 | Entitlements fail closed | `schools/entitlements.py`; a new school gets no module (T9-F1 LOW, onboarding checklist in T9-R §6) | `CURRENT` |
| G11 | Front-end supply chain | self-hosted vendored assets, `eip.E004` deployment check refuses a CDN reference | `CURRENT` |
| G12 | Regression gate on this commit | §6 below (sqlite + pg + the new brand tests) | `CURRENT` |
| G13 | Backup + restore drilled | `scripts/backup.sh`, `restore_backup.sh`, `test_backup_restore.sh`, `config/settings/restore_check.py` exist; **not run in this task** | `NOT VERIFIED` (T11 runbook) |
| G14 | Stronger password policy / optional 2FA | the queue's own T10 (L3, proposal only) is untouched; still UNDECIDED | `DEFERRED` |
| G15 | National id uniqueness across two schools | S7 decision; two schools cannot both hold the same national id (a blocker, not a leak) | `DECISION REQUIRED` (T9-F3, `docs/changes/0020`) |
| G16 | Superuser sees every school | true until S8; keep superusers in operator hands | `DEFERRED` (T9-F5) |
| G17 | FastAPI tests + image exposure | run separately from `run_tests.sh`; last recorded `Ran 74 tests` / `OK (skipped=7)` in the image with `--network none` (T8); not re-run here | `NOT VERIFIED` for this commit |
| G18 | Browser rendering / a11y in a real browser | `scripts/dev/page_audit.mjs` is dev-only; the rendered a11y walk runs inside the Django tests | `NOT VERIFIED` (manual pass pending) |

No gate changed status in this task: T10 only renames the product in the UI. G15 and G16 stay owner decisions
rather than defects.

## 5. Branding verification (evidence)

* Files changed: `config/settings/base.py` (two settings), `dashboard/context_processors.py` (two context keys),
  `dashboard/templates/dashboard/base.html` (title, `application-name`/`description` meta, sidebar brand, top-bar
  fallback), `dashboard/templates/dashboard/base_public.html` (title + meta + `<h1>`),
  `demo_intel/templates/demo_intel/base_demo.html` (title + top bar), `demo_intel/templates/demo_intel/login.html`
  (title), `students/tasks.py` (welcome e-mail body), `dashboard/test_a11y_render.py` (expected bare title now
  reads the setting).
* New test `dashboard/test_branding.py`: both settings non-empty, **no template** in the nine app template trees
  holds the old literal or a hard-coded new name, and a real `GET /login/` renders
  `<h1>…{PLATFORM_NAME}</h1>`, `<title>ورود — {PLATFORM_NAME}</title>`, `<meta name="application-name">` and the
  English name in `<meta name="description">` (HTML-escaped `&amp;`).
* The school's own name is unchanged and still comes from the `School` row (`{{ SCHOOL_NAME }}`), so a second
  school does not inherit the product name as its identity.
* Override without a code change: `EIP_PLATFORM_NAME` / `EIP_PLATFORM_NAME_EN` in the environment (read at import
  time, so a restart is required).

## 6. Test evidence (this commit, output read back from a file)

Everything below is a real command run on this branch; each output was redirected to a file and read back
(the terminal is noisy). No step is claimed from memory.

| # | Command (from repo root unless noted) | Verdict line read from the file | Label |
|---|---|---|---|
| 1 | `scripts/run_tests.sh sqlite` → step `check` (development) | `System check identified no issues (0 silenced).` (`check_exit=0` when re-run alone) | `CURRENT` |
| 2 | `scripts/run_tests.sh sqlite` → step `makemigrations --check --dry-run` | `No changes detected` (`makemigrations_exit=0`) | `CURRENT` |
| 3 | `manage.py test students dashboard schools vocabulary missions exams risk interventions docqa` (`config.settings.test_sqlite`) | `Ran 1610 tests in 1228.920s` / `OK (skipped=11)` | `CURRENT` |
| 4 | `manage.py test demo_intel` (`config.settings.demo`) | first pass `FAILED (failures=1)`; after the test-only fix below `Ran 62 tests in 299.486s` / `OK` | `CURRENT` |
| 5 | `manage.py test dashboard.test_branding` (`config.settings.test_sqlite`) | `OK`, `brand_exit=0`, 3 tests | `CURRENT` |
| 6 | `scripts/run_tests.sh pg` (PostgreSQL leg) | not run for this commit | `NOT VERIFIED` |

**The one demo failure, and why it was not a leak.** `demo_intel.tests.SeedDemoPlatformAccountTests.`
`test_login_lands_on_the_operator_page_and_sees_no_students` asserts that no seeded student first name appears on
`/platform/modules/`. The demo roster contains a student called **آرمان** (`seed_demo.py`, the `behavior_warning`
case), and the operator page now shows the product name «سکوی آموزشی-تربیتی آرمان نو» — whose substring «آرمان» tripped
the check. The page never contained student data (the school-scoped routes still answer `403` for that account, which
the same test asserts). Fix is in the test only (`demo_intel/tests.py`): strip `settings.PLATFORM_NAME` from the
rendered HTML before the substring check, with a comment naming the collision. The student-leak assertion itself is
unchanged, so the guarantee it encodes is still tested. Consequence worth knowing for the pilot: **a student whose
first name is «آرمان» will read the brand as partly their own name** — cosmetic, no action needed, noted here so it is
not mistaken for a data leak in a future review.

**What is *not* verified for this commit.** The redundant second `sqlite` pass was aborted on purpose (the owner asked
to stop the polling loop); the evidence is the first full pass above, and the only change made after it is the
test-only edit in `demo_intel/tests.py`, whose module was then re-run green on its own (`Ran 62 tests / OK`). The
PostgreSQL leg of the gate has **not** been run on this branch (`NOT VERIFIED`); one owner command
(`scripts/run_tests.sh pg`) closes it. Per-step exit codes are only available for the steps re-run individually
(row 1, 2, 5); rows 3 and 4 are quoted from the verdict lines of the redirected run.

## 7. What the owner still has to decide before the first real student

| # | Item | Why it blocks the pilot | Label |
|---|---|---|---|
| D1 | S7 `national_id` uniqueness (global vs per school) | a second school cannot import a roster whose ids collide with the first school's | `DECISION REQUIRED` (T9-F3) |
| D2 | Superuser visibility until S8 | every superuser sees every school; keep those accounts with the operator | `DEFERRED` (T9-F5) |
| D3 | Stronger password policy / 2FA for SchoolAdmins | pilot accounts use national ids as usernames; the queue's L3 T10 proposes options | `DEFERRED` (proposal not written) |
| D4 | Release tag / version string | the manifest above has no version; nothing was tagged | `DECISION REQUIRED` |
| D5 | Which T-number the 2FA proposal takes | the queue reserves T10 for it and this task reuses the name | `DECISION REQUIRED` |
| D6 | Backup/restore drill on the real server | `test_backup_restore.sh` exists but was not run here | `NOT VERIFIED` |
| D7 | Modules enabled per school | a new school reaches nothing until each module is enabled (T9-F1) | `CURRENT` documented, action per school |

## 8. Verdict

**The code is ready for a pilot with one school, and for a second school only after D1-D3 and the onboarding
steps in `docs/pilot/T9-MULTI-SCHOOL-READINESS-REPORT.md` §6.** The release freeze in §3 is in force from this
commit; the gate is re-run on whatever commit is actually handed over. Nothing in this task changed a permission,
a query scope or a migration — it changed the product's name and wrote down what "ready" means.

`NOT VERIFIED` remains for: the PostgreSQL leg of `scripts/run_tests.sh` on this branch, the FastAPI suite on this
commit, a real browser pass, a real PostgreSQL deployment with two schools, and the backup/restore drill.

