# Overnight report — branch `overnight/2026-10-25` (2026-10-25)

Base: `phase-1/boot-security` @ `4651c9a`. Pushed only the overnight branch; nothing merged; no access rule, entitlement semantics, migration or Tier C item touched. Synthetic data only. No gate failed twice.

## Test counts
| Gate | Result |
|---|---|
| `run_tests.sh sqlite` after Task 1 / 3 / 4 | 1116 / 1121 / 1122 tests OK (8 skipped = PostgreSQL-only) + 51 / 55 / 55 `demo_intel` OK |
| Timed full SQLite run (Task 6) | 1122 OK in 1189 s |
| `run_tests.sh pg` after the last task | **1122 OK**, image rebuilt without the 403, no stale-image warning; FastAPI not covered |

## Per task
**1. `/upload/` (commit `b48a0e4`).** The stub view and route are removed; the SchoolAdmin entry now reads "ثبت گروهی از اکسل" and opens `/school/accounts/` (it already has the dry-run preview, confirm and login sheet, and it creates Student records). Four existing tests were pointed at the new route. New tests: no sidebar link of any role ends in a 5xx; the admin entry returns 200; `/upload/` is 404. RUNBOOK risk line removed.

**2. Operator page.** Skipped as instructed (not approved).

**3. Mission polish (commit `dd4c03c`).** (a) `/mission/weights/`: SchoolAdmin, read only, gated by `mission`, audit-logged; active table, column sums, `params_version`, thresholds, all versions with lifecycle state. (b) The grade lead/counselor report already listed the exact missing indicators per unscored branch (tested); the teacher status page lacked a branch view, so it now lists missing indicators per branch, no scores. (c) Grid help in Persian on "not observed" vs score 1 and the minimum, with the numbers read from the school's active weight set. 5 new tests; a mutation (Grade Lead allowed on the weights page) made the role test fail, then restored.

**4. Demo and UX (commit `acf2bd8`).** RUNBOOK §3a "Demo walkthrough per role" with the exact URLs and the `set_school_module` / `seed_mission` commands. New static page `/school/quickstart/` ("راهنمای شروع سریع": bulk accounts, roles, password resets, modules), linked from the SchoolAdmin menu, no module gate, no data; test covers admin 200, content, other roles 403, anonymous 302.

**5. Exam design (commit `010a60a`).** `docs/EXAM_DESIGN_V2.md`, about 1.5 pages, no code: gate `module='exams'`, topics as `VocabularyTerm` (flat; tree is a decision), AI call cap through `ai_guard.consume`, four-slice plan with gates. `docs/EXAM_AND_SURVEY_DESIGN.md` is your untracked file and was not edited or committed.

**6. Quality sweep (this commit).** No flaky test seen: no intermittent failure across 8 full runs on this branch, apart from the harness failure described in the RUNBOOK. Slow tests: the slowest is `test_login_throttle.test_address_locks_across_usernames` (12.5 s); 79 tests take more than 5 s and 265 more than 2 s; the heaviest modules are `missions.test_reports` (165 s), `missions.test_engine` (136 s), `missions.tests` (104 s), `students.test_migration_0015` (85 s), `students.test_migration_0009` (84 s). The mission tests spend about 5 s each in `setUp` creating users with the production password hasher. Doc drift fixed: `DEMO_STATUS.md` upload row, RUNBOOK admin-gating wording, ARCHITECTURE weights page, TESTING counts. RUNBOOK open risks re-read against the code: all still current.

## Skipped and why
* Operator page: not approved.
* Speeding up the mission tests with a fast password hasher in test settings: a settings change, not a doc fix, so only proposed below.
* Fixing the migration-order fragility itself: touches applied migrations (Tier C); still a RUNBOOK open risk.
* Mission slice 2b UI, exams code, anything with an LLM: excluded by the brief.

## Decisions for you
1. Merge `overnight/2026-10-25` into `phase-1/boot-security` (5 commits + this one)?
2. Add `PASSWORD_HASHERS = [MD5PasswordHasher]` to the test settings only? Estimated saving: several minutes per full run, no behavior change in production. Needs your OK because it touches settings.
3. Exams: flat topics or a tree (needs a `parent` link on `VocabularyTerm`, Tier C), and separate AI caps for `exams`? (EXAM_DESIGN_V2.md §7.)
4. Operator page: approve to build after exams, as queued?
