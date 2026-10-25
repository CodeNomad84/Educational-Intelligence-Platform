# 0019 — S4 completion: read-through, PostgreSQL race test, maintenance-command scope (2026-10-26)

Scope: S4 of `0010-multi-school-hosting-PROPOSAL.md` (writes, import, commands). No access rule, migration or schema changed. Synthetic data only.

## Read-through (a): writes across schools
| Item | Evidence | Status |
|---|---|---|
| The only data API is `/api/students/` (list, retrieve, create, update, partial_update, destroy, import, features, predict); no Enrollment/Attendance/Grade/Observation endpoints exist | `config/urls.py`, `students/views.py` | done (facts) |
| PUT/PATCH/DELETE/features/predict of another school's student: 404, nothing changes | `students/test_cross_school_writes.py` `ApiTests` | done |
| Create/move with another school's class, `target_school` or parent: refused, nothing changes | same, `ApiTests` | done |
| Import into a foreign target school refused; import cannot overwrite a foreign student by `national_id` | same | done |
| Dashboard: student detail/360/account/referral of another school, `student_add` with a foreign class, school pages (year, class, staff, assignments, reset, roles) of another school | same, `DashboardAdminTests` (mutations: viewset queryset, `year_set_current`, `class_edit` scope each fail it) | done |
| Subject Teacher: foreign assignment sheet, grade delete through own or foreign sheet, foreign student page | same, `DashboardTeacherTests` | done |
| Mission and exams routes across schools | `missions/tests.py`, `missions/test_reports.py`, `exams/tests.py`, `exams/test_slice2.py` (cross-school cases) | done |
| Gap found | none: every path was already scoped | — |

## (b) PostgreSQL import-race test
The RUNBOOK said "the PostgreSQL thread test is skipped"; there was in fact **no real concurrency test** (only a deterministic simulation with a stale `locked_state`, `test_school_scoped_import.py`). Added `students/test_import_race_postgres.py`: two real connections, deterministic interleaving (the main thread holds an uncommitted insert, the worker's `write_row` blocks on the unique index, the test waits until `pg_stat_activity` shows the lock, commits, and the worker must get `ImportConflict`). Runs in `run_tests.sh pg` and the CI postgres job, both set `EIP_REQUIRE_PG=1` so the test fails instead of skipping. Stable: 5/5 runs, 0.4 s. Mutations: the old unconditional `update_or_create`, and not mapping `IntegrityError`, each fail both tests.

## (c) Maintenance commands (24 first-party commands classified in `schools/test_command_scope.py`)
- **Needs a school once several exist** (new, `schools/command_scope.py`): `seed_mission`, `seed_vocabulary` (`--school` or explicit `--all-schools`), `normalize_year_texts`, `backfill_enrollments` (`--school-code`, required for `--apply` / `--revert-backfill`; dry runs may still read every school). One school: unchanged.
- **Single school by construction** (already refuse when ambiguous): `set_school_module`, `seed_demo`, `rollover_academic_year`, `import_history`, `backfill_school_memberships`, `backfill_student_school`.
- **Platform-wide by design**: `setup_staff_roles`, `setup_platform_role`, `load_mission_rubric`, `check_school_memberships` (batch-logged), `seed_temporal_*` (create their own synthetic school).
- **Read-only**: the `check_*` commands, `compare_access_parity`, `demo_check`.
A new command that is in none of the lists fails the guard test.

## Still open for a second real school (S4 itself is complete)
S7 (`national_id` per school: see `0020-s7-national-id-PROPOSAL.md`), S8, S9, S10, Django admin not school-scoped, FastAPI without a module claim, legal/consent policy, the no-real-data rule until P3.
