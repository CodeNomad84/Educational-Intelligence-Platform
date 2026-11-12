# T9 — Multi-school readiness audit (Phase 1 pilot)

**Status: REPORT ONLY — no application code, settings, migration, template or test was modified by this task.** Every
statement below is either a `path:line` I read on this branch or the output of a command I ran; labels are used
throughout (`CURRENT` = verified here, `TARGET` = agreed but not built, `NOT VERIFIED`, `DECISION REQUIRED`,
`DEFERRED`). Nothing is merged or pushed.

| Item | Value |
|---|---|
| Branch | `work/T9-multi-school-readiness` (created from `phase-1/boot-security` @ `dd9ed5b`) |
| Review type | Static audit of every school-bearing view/query/form/export/command **plus** a live two-school probe and the read-only readiness commands |
| Code changes | **None.** `git diff --stat` at the end shows only this report and `PROGRESS.md` |
| Evidence DB | Throw-away SQLite file in `/tmp` (`EIP_DEMO_DB=/tmp/t9_ms.sqlite3`), synthetic schools only. **No real student data was created, read or copied.** |
| Regression gate | `scripts/run_tests.sh sqlite` and `scripts/run_tests.sh pg` run once at the end (§7) |
| Question answered | "Can a second school be onboarded into this deployment without one school seeing another?" |

## 0. How to read this report

* A green statement is always followed by the file/line or the command output it came from. Where I could not verify
  something, it is in §8 rather than guessed.
* The live probe (§4) is the part a reader should trust most: it logs in as the SchoolAdmin of school **alpha** against a
  database that really contains school **bravo**, and looks for bravo's students on every page alpha can reach.
* Severity: **HIGH** = cross-tenant read or write; **MEDIUM** = blocks onboarding or is a documented deferral with
  tenant consequences; **LOW** = onboarding friction / hygiene. There is **no HIGH finding** in this audit (§5).


## 1. Scope and method

Read on this branch (not from memory): `students/access.py`, `students/student_school.py`, `students/serializers.py`,
`students/views.py`, `dashboard/decorators.py`, `dashboard/school_views.py`, `dashboard/school_forms.py`,
`dashboard/views.py`, `dashboard/{student,teacher,counselor,grade_dashboard,notification,password_reset,bulk,strategy,account}_views.py`,
`dashboard/{module_info,operator_page,quickstart,home}.py`, `schools/entitlements.py`, `schools/models.py`,
`schools/command_scope.py`, `schools/multischool_checks.py`, `exams/access.py`, `exams/views.py`,
`exams/views_results.py`, `exams/views_import.py`, `missions/access.py`, `missions/views_reports.py`,
`risk/urls.py` + `risk/views.py` (through its templates), `docqa/views.py`, `config/service_auth.py`,
`fastapi_core/{main,auth,rag_service}.py`, every `*/management/commands/{create_school,seed_*,check_*,compare_*,run_rules,rollover_academic_year}.py`,
and the four download/export endpoints (§3.4).

Method: four passes.

1. **Inventory** — list every URL that can return school data and every command that reads or writes it.
2. **Model** — confirm each of them resolves its school from the *user's memberships*, never from a request parameter.
3. **Live probe** — build a two-school database with `create_school`, log in over HTTP as alpha's admin, walk 30 pages,
   request bravo's student objects, POST to bravo's write endpoints, and diff row counts (§4.3).
4. **Contracts** — run the readiness commands that exist for exactly this question (§4.2).

## 2. The isolation model, as it actually is (`CURRENT`)

| Layer | Mechanism | Where |
|---|---|---|
| Identity → schools | `school_ids_for_admin(user)` = active `SchoolMembership` rows of an active, non-superuser account holding the `SchoolAdmin` group; **empty set instead of "all"** for anyone else | `students/access.py:50` |
| "Which school am I acting in" | `allowed_school_ids` → never `None`; `_current_school` accepts `?school=` **only if it is in that set**, else falls back to the smallest allowed id; the choice is kept in the session | `students/student_school.py:72`, `dashboard/school_views.py:29-39` |
| Read scopes | 18 `visible_*` querysets (`visible_students`, `visible_grades`, `visible_attendances`, `visible_alerts`, `visible_plans`, `visible_behavior_notes`, …). A view that lists school data uses one of these and nothing else | `students/access.py:170-530` |
| Object reads | `get_object_or_404(<visible_* or school=school>, pk=…)` — another school's id is a **404**, not a redirect | `dashboard/views.py:111`, `dashboard/strategy_views.py:44,80`, `dashboard/school_views.py:139` |
| Writes | the school is derived server-side: `resolve_student_school(user, school_class=…, target_school_id=…, existing_school_id=…)` refuses a school outside the set, a class/target mismatch, and any school *change* | `students/student_school.py:80-106` |
| Per-school configuration | `risk.{RiskEvent,Alert,RuleSettings,Rule,RuleHit,RuleRun,Notification}`, `interventions.{Strategy,…}`, `docqa.{SchoolDocument,…}`, `schools.{SchoolClass,AcademicYear,StaffProfile,SchoolModule}`, `vocabulary.VocabularyTerm` — each carries a `school` FK with `on_delete=PROTECT` | `risk/models.py:35,59,91,118,169,188,215`, `interventions/models.py:17,42`, `docqa/models.py:8,26`, `vocabulary/models.py:28`, `schools/models.py:43,285,339,417` |
| AI service boundary | the token's `schools` claim is minted **from the database** (`school_ids_for_admin`) and cannot be set by the client; FastAPI rejects a missing/malformed claim with 401 and filters every query with `school_id = ANY(%s)` | `config/service_auth.py:31-49`, `fastapi_core/auth.py:127-141`, `fastapi_core/rag_service.py:177,249,263` |
| Management commands | one explicit `--school` (or `--all-schools`) when more than one school exists; a test fails if a new command is unclassified | `schools/command_scope.py`, `schools/test_command_scope.py` |
| New school | `create_school <code> <name>` in one transaction, audited, seeds vocabulary and the starter rule set **for that school only** | `schools/management/commands/create_school.py`, live output in §4.1 |

## 3. Inventory — every school-bearing surface and its verdict

Verdicts are `CURRENT` (verified in code **and** on the probe where reachable) or `N/A` (no school data at all).

### 3.1 Dashboard (`ADMIN`, `GRADE_LEAD`, `TEACHER`, `PARENT`, `STUDENT`, `COUNSELOR`)

| Surface | Scoped by | Verdict |
|---|---|---|
| `student_list_view`, `student_detail_view` (`dashboard/views.py:86-111`) | `visible_students(request.user)`; detail is `get_object_or_404(visible_students)` | `CURRENT` |
| `student_360`, `reveal_national_id` (`dashboard/student360.py`) | `visible_students` + `apply_alert_text_policy`; the national id is a POST-only reveal, audited | `CURRENT` |
| behaviour note / alert / plan create (`behavior_views`, `loop_views`, `plan_views`) | `behavior_writable_students`, `raisable_students`, `plan_students` — the target must be in the writer's scope | `CURRENT` |
| alert review / reopen, plan start/cancel/complete/reassign/followup | `reviewable_alerts`, `may_edit_plan`, `may_cancel_or_reassign_plan`, `may_read_plan_text` | `CURRENT` |
| counselor home / case / close, referral | `visible_referrals`, `visible_counselor_notes`, `counselor_note_metadata`; the referral target is `get_object_or_404(visible_students(...).filter(full_tier=True))` (`dashboard/counselor_views.py:49`); pilot flag gate | `CURRENT` |
| teacher home / grade sheet / grade delete / student page | `_my_assignments` + `_class_students` (assignment → class → students of that class) | `CURRENT` |
| grade dashboard (`dashboard/grade_dashboard.py`) | `visible_students`, aggregate only above `MIN_GROUP` | `CURRENT` |
| school pages: home, years, classes, staff list/detail, assignments, audit log (`dashboard/school_views.py`) | `@school_page` → `_current_school` + `school=` on every lookup; `staff_queryset` is per school | `CURRENT` |
| strategies (`dashboard/strategy_views.py`) | `@school_page`, `get_object_or_404(Strategy, pk=pk, school=school)`, effect rows from `visible_plans(user).filter(school_id=school.pk)` | `CURRENT` |
| bulk accounts (import → preview → confirm → login sheet) | `@school_page`; the cached batch entry stores the school id and `_stored(request, school)` rejects another school's token; sheet is `no-store` | `CURRENT` |
| password resets (school + grade) | `@school_page` / grade-lead scope; reset target looked up inside the school | `CURRENT` |
| notifications (`dashboard/notification_views.py`) | own rows **re-checked** on every view: `risk/notifications.py:61 visible_notifications(user)` unions the user's own rows whose alert/plan is still in scope; mark-read updates that queryset only | `CURRENT` |
| `account_views` (profile, password change), `quickstart`, `module_info` | own account / static text only | `N/A` |
| operator overview (`dashboard/operator_page.py`) | platform operator only (`403` for a SchoolAdmin — observed), no student data, audited once per school shown | `CURRENT` |
| legacy library `library/upload-document/delete-document` (`dashboard/views.py:231-340`) | Django gate is role-only, but the service refuses by the signed `schools` claim: list/delete/search are `school_id = ANY(%s)`; upload+ingest are `disabled_in_phase1` (403) | `CURRENT` (see T9-F6) |

### 3.2 Modules

| App | Verdict | Note |
|---|---|---|
| `risk` (`/rules/…`) | `CURRENT` | rules/runs/alerts/notifications all carry a school FK; `RuleSettings` is one row per school; the rule catalogue is versioned per school (`rule_version_unique`, `risk/models.py:141-144`) |
| `exams` (`/exams/…`) | `CURRENT` | `exams/access.py` (`enabled_school_ids`, `teacher_scopes`, `teacher_class_ids`, `own_student`, `student_exams`); results pages iterate the caller's scopes |
| `missions` (`/mission/…`) | `CURRENT` | `missions/access.py` entry scopes; `aggregate`/`weights` are per school; small groups withheld |
| `docqa` (`/assistant/…`) | `CURRENT` | `SchoolDocument` + per-request `_school`; the AI routes are 403 unless `ENABLE_AI_FEATURES` is on |
| DRF API (`/api/…`, `students/views.py` + `serializers.py`) | `CURRENT` with one note | querysets come from `visible_students`; `IsAdminUser` on write endpoints is *stricter* than the role, so a SchoolAdmin cannot write through the API at all (T9-F4) |

### 3.3 Management commands

`create_school` (one transaction, audited, per-school seeds), `seed_vocabulary`, `seed_rules`, `seed_strategies`,
`seed_mission`, `run_rules`, `rollover_academic_year`, `backfill_enrollments`, `backfill_school_memberships`,
`backfill_student_school`, `normalize_year_texts`, `notify_due`, `import_history`, `load_mission_rubric`,
`set_school_module`, `setup_platform_role`, `setup_staff_roles`, and the read-only `check_*`/`compare_*` reports.

The rule is one function, `resolve_scope` (`schools/command_scope.py:13-23`), used by every command classified
**needs-school**: with **more than one** school, a command that **writes** must be told which school (`--school-code`) or be
given `--all-schools` where it allows that, otherwise it stops *before reading or writing* with
`more than one school exists: pass --school-code <school code> …; nothing was changed.` Platform-wide
(`setup_staff_roles`, `setup_platform_role`) and read-only (`check_*`, `compare_*`, `demo_check`) commands are classified
separately and may cover every school. `schools/test_command_scope.py:34-42` discovers the first-party commands with
`get_commands()` and fails if a new one is not classified exactly once, so a new command cannot silently escape the rule.
`CURRENT`.

### 3.4 Downloads and exports

There is **no export of student data** anywhere in the codebase (`grep "text/csv|spreadsheetml|attachment;"` — 4
non-test hits): `accounts-template.xlsx` (empty template), `login-sheet.xlsx` (only the accounts just created for the
calling admin's school, `Cache-Control: no-store`), `rules_strategies_template.xlsx` (empty template),
`exam-questions-template.csv` (empty template). `CURRENT`.


## 4. Evidence on a real two-school database (`CURRENT`)

Nothing in this section came from fixtures: it is a migrated SQLite database in `/tmp` (`/tmp/t9_ms.sqlite3`, settings
`config.settings.demo` + `EIP_DEMO_DB`), seeded only with synthetic data.

### 4.1 Building the tenant

Built with the real commands — `create_school alpha "School Alpha"` and `create_school bravo "School Bravo"`
(30 vocabulary terms each) followed by `seed_rules --school alpha` / `--school bravo` (5 starter rules each) and a seed
script that adds one `SchoolAdmin` + `SchoolMembership`, one class and three students per school. The state of the
database afterwards, read back with `manage.py shell` on the same file:

```
school 1 default | terms  0 | rules 0 | students 0 | memberships 0
school 2 alpha   | terms 30 | rules 5 | students 3 | memberships 1
school 3 bravo   | terms 30 | rules 5 | students 3 | memberships 1
groups ['Counselor', 'GradeLead', 'SchoolAdmin', 'Teacher']
```

Three observations, all `CURRENT`:

* The vocabulary and the rule catalogue were created **per school** (30 terms and 5 rules each), not shared — the second
  `create_school` did not reuse the first school's rows.
* A fresh install also contains an **empty `default` school row** (0 of everything above). That row is why
  `check_academic_years` reports `schools_without_current_year: 1`.
* The `SchoolAdmin` group is **not** created by `setup_staff_roles`, which creates only
  `STAFF_ROLE_GROUPS = (Teacher, GradeLead, Counselor)` (`schools/management/commands/setup_staff_roles.py:17`) and
  refuses with `Group "SchoolAdmin" does not exist; create it first` (`:71`). Here it exists because the seed script
  created it — i.e. the group is a documented onboarding step, not something the code does for you (T9-F2).

### 4.2 Read-only readiness commands against that database (all exit 0; every `writes:` line says `none`)

| Command | Verdict line | Numbers that matter |
|---|---|---|
| `check_student_school_ready --json` | `"ready": true` | `schools 3`, `students 6`, `students_without_school 0`, `students_whose_school_differs_from_their_class_school 0`, `backfill_would_assign 0` |
| `check_access_switch_ready --multi-school --json` | `"verdict": "READY"`, `"multi_school_passed": true` | `blockers_nonzero {}`, `students_missing_current_enrollment 0`, `school_admins_without_membership 0`, `info_school_admins_per_school {"2":1,"3":1}`, `active_memberships_of_platform_admin_users 0` |
| `compare_access_parity --multi-school --json` | `"verdict": "PASS"`, `"multi_school_passed": true` | `users_compared 2`, `students_leaked 0`, `students_locked_out 0`, `grades_leaked 0`, `grades_locked_out 0`, `info_other_school_students_hidden 6` |
| `check_school_memberships` | — | `memberships_total 2`, `memberships_active 2`, `orphan_active_total 0` |
| `check_class_links` | — | `Students: 6  already linked: 6  candidates: 0`, `Linkable class titles (2): ALPHA-7A, BRAVO-7A` |
| `check_academic_years` | — | `schools 3`, `academic_year_rows 2`, `class_rows 2`, `schools_with_several_current_years 0`, `overlapping_ranges 0`, `codes_with_spelling_variants 0` |
| `check_assignment_subjects` | — | `assignments 0` (none created) |
| `check_enrollment_backfill` | — | `students 6`, `students_already_with_enrollment 6` |

`schools_without_current_year: 1` in `check_academic_years` is the empty `default` school, not a data problem:
`check_access_switch_ready` reports `schools_with_students_but_no_current_year: 0`.

### 4.3 HTTP probe as alpha's SchoolAdmin (real login, 30 pages)

`POST /login/ {admin_alpha, …}` → `302 /school/`. Then, for every page alpha can reach, the response body was searched
for the three bravo students' names (`BRAVOS0/1/2`):

```
/dashboard/ 200  /students/ 200  /alerts/ 200  /interventions/ 200  /notifications/ 200
/account/ 200    /school/ 200    /school/strategies/ 200  /school/accounts/ 200
/school/resets/ 200  /school/staff-roles/ 200  /school/quickstart/ 200
/rules/ 200  /rules/catalog/ 200  /rules/import/ 200
/grade/ 403  /platform/modules/ 403   (role/module gates, as designed)
/exams/ 403  /exams/teacher/ 403  /exams/lead/ 403  /exams/admin/ 403
/exams/teacher/topics/ 403  /exams/teacher/import/ 403
/mission/ 403  /mission/students/ 403  /mission/aggregate/ 403  /mission/weights/ 403
/assistant/ 403  /assistant/documents/ 403  /assistant/setting/ 403
bravo_traces = [] on every line
```

Object level, the same session against bravo's three students: `detail` 404, `360` 404, `report-card` 404,
`behavior/new` 405 — `@require_POST` (`dashboard/behavior_views.py:38`) runs *before* the lookup, so that 405 is the same
answer alpha's own students get, i.e. not an oracle; the POST below is the real test.

Search, re-run on its own to show exactly what the page contains:

```
GET /students/?search=BRAVO -> 200  hrefs=['/students/', '/students/add/']      names_on_page=[]
GET /students/              -> 200  hrefs=['/students/','/students/1/','/students/1/360/','/students/2/', …,
                                          '/students/3/360/','/students/add/']  names=['ALPHAS0','ALPHAS1','ALPHAS2']
```

No student row and no bravo name in the filtered page; the unfiltered page still lists alpha's three students, so the
probe is not vacuous.

Write paths aimed at bravo's student — all refused, nothing created:

```
POST /students/4/behavior/new/ -> 404     POST /students/4/alert/  -> 404
POST /students/4/plan/new/     -> 404     POST /students/4/refer/  -> 404
POST /students/4/account/      -> 404
BRAVO ROWS behavior/plan/alert before= (0, 0, 0) after= (0, 0, 0)
PROBLEMS= none
```

The `403`s are themselves part of the answer: `create_school` grants **no modules**, so a brand-new school's admin cannot
even reach `exams` or `mission` until an operator enables them (T9-F1), and `/assistant/…` sits behind the
`ENABLE_AI_FEATURES` pilot flag as well (`docqa/views.py:47`). Per-school module gating is fail-closed, which is why
`T9-F1` is a LOW onboarding finding and not a security one.


## 5. Findings

No **HIGH** finding: I found no page, object lookup, export, command or service call that returns another school's data
to a school account, and the probe could not make one. What is left is onboarding friction and two owner-level
decisions that already existed before this task.

| ID | Severity | Finding | Status |
|---|---|---|---|
| **T9-F1** | LOW | A school created with `create_school` has **no modules**: its admin gets `403` on `/exams/…` and `/mission/…` until an operator enables each module (`/assistant/…` additionally needs the `ENABLE_AI_FEATURES` pilot flag; `/grade/` is a grade-lead page, 403 by role). Fail-closed and documented (`create_school` prints the next step, `docs/manuals/platform-admin.md`), but a second school will look "broken" on day one. | `CURRENT` — expected. Action: add "enable the school's modules" to the onboarding checklist (§6). |
| **T9-F2** | LOW | A **fresh install** has an empty `default` school row and **no `SchoolAdmin` group**: `setup_staff_roles` creates only `Teacher`, `GradeLead`, `Counselor`. Adding a user to a non-existent group silently grants no role, and `check_academic_years` then reports `schools_without_current_year: 1` for that empty row. | `CURRENT` — documentation-only (`DEFERRED`): either the manual step or the check output should say this out loud. |
| **T9-F3** | MEDIUM | `national_id` is **globally unique**, not unique per school (`students/student_school.py:134`, S7). Two schools cannot both hold the same national id; the refusal is one fixed message, so it is a blocker, **not** a disclosure. Owner decision pending in `docs/changes/0020`. | `DECISION REQUIRED` (owner). |
| **T9-F4** | LOW | The DRF write endpoints keep `IsAdminUser`, so a **SchoolAdmin** (non-staff) can read the API but gets `403` on every write, while the same operation is allowed on the HTML page. Stricter than the role, so not a leak — but it is a silent behaviour difference for the second school's staff. | `CURRENT`; `TARGET` = align with `SchoolAdmin` + membership or document the API as operator-only. |
| **T9-F5** | MEDIUM | **Superusers see every school** until S8 splits platform operators from school data. `operator_page` is already operator-only and audited per school, and the Django admin pages are closed for school data (`schools/admin.py:25-215` registers only School, SchoolMembership, AuditEvent, SchoolModule and User; `dashboard/admin.py` registers nothing), but any superuser account remains a cross-tenant read path. The switch-over check counts `active_memberships_of_platform_admin_users` and currently reports `0` — that number is the guardrail to keep at 0. | `DEFERRED` (owner, S8). |
| **T9-F6** | LOW | The **legacy library** pages (`dashboard:library`, `upload_document`, `delete_document`) have no school logic on the Django side: isolation comes only from the FastAPI service's signed `schools` claim. That is `CURRENT` and correct today, but the Django view has no fallback if the service is misconfigured. The unused legacy pair still contains an **unscoped** `get_all_documents()` (`fastapi_core/rag_service_HuggingFace_Models.py:92`, called at `main_HuggingFace.py:260`) and stays out of the image because `fastapi_core/.dockerignore` excludes both files (T8 C6). | `CURRENT`; keep both out of the image. |

Checked and clean (no finding): cross-school search, student 360, national-id reveal (POST + audit), behaviour/alert/plan
create, plan transitions, counselor cases, teacher grade sheets, bulk accounts preview/confirm/login sheet, password
resets, notifications, strategies, rules/catalogue/import, exams results, missions aggregate/weights, docqa documents,
the four download endpoints, all management commands.

## 6. Onboarding checklist for the second school (owner/ops)

1. `manage.py create_school <code> "<name>"` (one transaction, audited).
2. Create the `SchoolAdmin` group if the install is fresh (T9-F2), the admin account, and its `SchoolMembership`.
3. Enable the modules the school bought (`schools` module rows / trial dates) — otherwise every module page is `403` (T9-F1).
4. Set the current `AcademicYear` and the classes (a school with students and no current year is a blocker in
   `check_access_switch_ready`).
5. Decide **S7** (national id per school) before importing a second school's real roster (T9-F3).
6. Run the read-only checks on the **real** database, in this order: `check_student_school_ready`,
   `check_access_switch_ready --multi-school`, `compare_access_parity --multi-school`, `check_school_memberships`,
   `check_class_links`, `check_academic_years`, `check_assignment_subjects`, `check_enrollment_backfill`.
7. Keep one `school_app` database role for the installation (a school never gets its own role), confirm per-school
   backups restore (`RUNBOOK.md`), and agree the platform operator per school (`0028 P3-1`).
8. Re-run the probe of §4.3 against the new school's admin before handing over credentials (it is a scripted client
   login + page walk, no fixtures needed).


## 7. Regression gate (run once at the end, output redirected to a file and read back)

* `scripts/run_tests.sh sqlite` → `Ran 1607 tests in 2265.340s` / `OK (skipped=11)`, then `demo_intel`
  `Ran 62 tests in 213.770s` / `OK`, last line `ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not
  covered)` (`/tmp/t9_full_sqlite.txt`).
* `DJANGO_IMAGE=eip-test-django:local scripts/run_tests.sh pg` → `Ran 1607 tests in 1424.983s` / `OK (skipped=1)`,
  last line `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)`
  (`/tmp/t9_full_pg.txt`; the log is verbosity 1, so it does not name the single skip).

The suite is unchanged by this task (docs only); it is quoted because a readiness claim is worth nothing without the
regression gate on the same commit.

## 8. Not verified / deferred

* **PostgreSQL with two schools** — the regression gate (§7) passed on PostgreSQL 16, so the schema and the school-scoped
  code paths are engine-clean; but the *two-school probe* of §4 ran on SQLite only. No tenant logic in this report is
  engine-dependent (`school_id` filters and `PROTECT` FKs behave the same), yet a second school has not been created on a
  real PG deployment. `NOT VERIFIED` there.
* **Real data** — none exists and none was used. Every number in §4 comes from synthetic schools.
* **The running FastAPI service** — not started for this task; the service-boundary statements come from reading
  `main.py`/`auth.py`/`rag_service.py` plus the existing FastAPI tests. In the pilot default the AI routes are `403`
  anyway (`ENABLE_AI_FEATURES=False`).
* **Two schools on one server as one process** — unchanged product stance: two isolated instances mean two deployments
  (separate processes, databases, secrets, storage), not two schools inside one shared process (`docs/pilot/PILOT_CONFIG.md`
  §"Can one server run two isolated instances?"). This report does not change that decision; it only says that the
  *application layer* is membership-scoped and fails closed if the owner chooses one deployment with two schools.
* **Browser rendering** — not redone here; `scripts/dev/page_audit.mjs` covers the visual pass and is dev-only.
* **Scale** — the probe used 2 schools / 6 students. `students/access.py` builds querysets, not per-row loops, so there is
  no known N+1 school lookup, but no load test was run.

## 9. Verdict

**A second school can be added to this deployment without seeing the first one's data** — on the evidence of §2 (code),
§4 (a two-school database, a real login, 30 pages, object reads, write attempts, eight read-only checks) and §7 (the
regression gate). The isolation lives in one place (`students/access.py` + `student_school.py`) and every surface I
audited goes through it.

It is **conditional** on the owner's onboarding steps in §6: modules must be enabled per school (T9-F1), the S7 national-id
decision must be taken before real rosters are imported (T9-F3), superuser accounts must stay in operator hands until S8
(T9-F5), and the read-only checks must be run against the real database — not the throw-away one used here.

No code change is proposed by this report. `docs/MULTI_SCHOOL_READINESS.md` (P9) remains the short table; this document is
the audit that backs it for a second school.

