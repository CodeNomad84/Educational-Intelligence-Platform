# CHANGE REPORT — Multi-school hosting, stage S1: SchoolMembership, empty PlatformAdmin group, `school_ids_for_admin`
Proposal: `0010-multi-school-hosting-PROPOSAL.md` §9 (S1) · ADR-0012 · Level: L3 · Date: 2026-10-19 · Commit: one local commit (hash in the owner message; **not pushed**) · Status: **implemented locally, pending owner review**. S2 and later, 2.2-0, 2.2 and 2.4 are NOT started.
Rule that still applies: NO REAL STUDENT DATA until the P3 exit criteria and the 2.4 audit log. All data below is synthetic or empty.

## WHY
Multi-school hosting needs SchoolAdmin to be bound to schools (ADR-0012 decision 2) and a separate platform role (decision 4). S1 is the additive foundation: it stores the membership entity, creates the empty platform group and defines the single helper that later stages will use. It is built first, with **no access change**, so that every later switch (S3) can be gated by parity.

## WHAT
- `SchoolMembership(user, school, is_active, created_by, created_at, updated_at)`, unique `(user, school)`, many-to-many through the model. `clean()` at creation: user active, **not superuser**, in group `SchoolAdmin` (`is_staff` allowed until S9).
- `school_ids_for_admin(user)` returns the set of school ids; it re-checks at query time that the user is authenticated, active, not superuser, in group `SchoolAdmin` (checked on the group, never through `roles_for`) and that the membership row is active. Anything else gives the empty set (fail closed).
- `setup_platform_role` creates the group `PlatformAdmin` with zero permissions and no members, reports, and `--fix` removes any permission found. It creates no user and sets no `is_staff`/`is_superuser`.
- `SchoolMembershipAdmin` for superuser or `PlatformAdmin` group members only (and only with the normal model permission); a SchoolAdmin holding the permissions is still refused. The user picker offers only active, non-superuser SchoolAdmins; `created_by` is set automatically.
- `PLATFORM_ADMIN` constant; deliberately **not** in `ALL_ROLES`, so `roles_for` and the FastAPI token do not know the role yet.
- **Nothing reads the new entity**: no `visible_*`, view, serializer, permission class or token code uses it (guard tests assert this by inspecting source).

## WHERE
`django_core/schools/models.py` (`SchoolMembership`), `schools/migrations/0004_schoolmembership.py`, `schools/admin.py` (`SchoolMembershipAdmin`, `_platform_level`), `schools/management/commands/setup_platform_role.py`, `students/access.py` (`PLATFORM_ADMIN`, `school_ids_for_admin`), `schools/test_school_membership.py`. Docs: `MODULE_MAP.md`, `CHANGE_GUIDE.md` (row + Verified-at note), `ROADMAP.md` (row 2.1m), `TESTING.md` (update paragraph), this report.

## HOW
Additive migration (one `CreateModel`, no data migration). The helper lives in `access.py` (the single place for role/scope rules) with a lazy import of the model, the same pattern as `_grade_lead_q`. Hygiene mirrors `GradeLeadAssignment`: creation-time checks in `clean()` plus query-time re-checks, because rows created around `clean()` (bulk, shell, fixtures) must grant nothing. Rollback: `migrate schools 0003` (drops the empty table) and revert the commit.

## RISKS
- **None to current access** (verified below). The new table is empty on every existing database.
- **Privilege-adjacent surface:** `SchoolMembershipAdmin` lets a platform-level account create memberships. Until S3 they have no effect; from S3 they will grant school scope. Mitigated by `_platform_level` (a SchoolAdmin is refused even with the permissions) and by the PlatformAdmin group holding **zero** permissions in S1, so in practice only a superuser can use it.
- `is_staff` SchoolAdmins may hold memberships until S9 (report/blocker planned there).
- Test-only note: the unique-constraint mutation fails only the `full_clean` test, because the database constraint comes from the migration; the migration is the authority and the IntegrityError test guards it.
- Security review: see the owner message (the review was run on the commit, after it was made).

## EVIDENCE (real command results, 2026-10-19)
**Baseline before the change (SQLite, development settings):** `students dashboard schools` 438 tests OK; `demo_intel` (demo settings) 34 tests OK.

**After the change:**
| Run | Result |
|---|---|
| `manage.py check` (SQLite) | no issues |
| `makemigrations --check --dry-run` (SQLite and PostgreSQL) | No changes detected |
| `test students dashboard schools` SQLite | Ran **484** tests, OK (438 + 46 new) |
| `test demo_intel` SQLite, demo settings | Ran 34 tests, OK |
| `test students dashboard schools` PostgreSQL 16.14 (disposable `pgvector/pgvector:pg16`, tmpfs, private network; test DB only; the container and network were removed afterwards) | Ran **484** tests, OK |
| Migration `schools/0004` on scratch PostgreSQL: forward, `migrate schools 0003`, forward again | table created, dropped, recreated; unique constraint `uniq_schoolmembership_user_school` present |
| Same on scratch SQLite | unapplied and re-applied OK |
| `setup_platform_role` twice on scratch PostgreSQL | `created` then `exists`; permissions 0; members 0 |

**No access change (stage condition 1):**
- A scratch SQLite database was seeded by `seed_temporal_realistic` (234 synthetic students, 39 classes, 330 enrollments, 4419 grades, 12766 attendance rows) using the code of the previous commit (`git archive` copy), a SchoolAdmin and a superuser were added, then the file was copied and migrated with the S1 code (only `0004` applied).
- `compare_access_parity`: output byte-identical before/after (39 users, 168 in both, 9 only-legacy, 124 only-new, tier differences 0). It exits 1 on both sides with "9 unexplained difference(s)": this is the documented baseline of the deliberately dirty synthetic seed (`TESTING.md`, 2026-10-16 loaded-database gate), not an effect of S1.
- `check_access_switch_ready`: output byte-identical (NOT READY, 6 blocker rows, the same seeded class-grade conflicts).
- Per-user dump of `roles_for`, `visible_students` (with tier), `visible_grades`, `visible_attendances` for all 41 users (760 student rows): sha256 identical before and after (`7827fee3…a3c410`).
- Guard tests in `StageS1ChangesNoAccessTests` (memberships created for a SchoolAdmin and a Parent change nobody's sets; a SchoolAdmin without membership still sees every school; a `PlatformAdmin` group member has no role and sees nothing; `PLATFORM_ADMIN` not in `ALL_ROLES`; no visibility, view, serializer, permission or token source mentions the new entity).
- The real databases `django_core/db.sqlite3` and `demo_db.sqlite3` were never opened by these commands (size and modification time unchanged); `data/postgres` was not touched.

**Non-vacuity (mutation checks, each restored from a scratchpad copy, sha256 of `access.py`/`models.py` verified equal afterwards, tree contains only the intended changes):**
| Mutation | Failing tests |
|---|---|
| helper: drop the active/superuser check | `test_deactivated_account_grants_nothing`, `test_superuser_row_created_around_clean_still_grants_nothing`, `test_user_who_became_superuser_grants_nothing` |
| helper: drop the group check | `test_membership_of_a_user_outside_the_group_grants_nothing` (5 sub-cases), `test_user_who_left_the_group_grants_nothing` |
| helper: drop the membership `is_active` filter | `test_inactive_membership_grants_nothing`, `test_only_inactive_memberships_grant_nothing` |
| model: drop the unique constraint | `test_pair_uniqueness_is_also_a_validation_error_in_forms` |
| model `clean()`: drop the superuser rule | `test_superuser_cannot_be_a_member` |

**Deviation, reported as required:** the first run of the new test file had one failure, in my own test `test_pair_uniqueness_is_also_a_validation_error_in_forms`, which called `validate_unique()`; Django validates constraints in `full_clean()`, so the test was wrong, not the product code. I corrected the test and re-ran; no existing test failed at any point.

## OWNER ACCEPTANCE
Pending. Not pushed. Next stage (S2) needs its own explicit approval.
