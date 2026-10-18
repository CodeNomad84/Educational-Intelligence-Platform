# CHANGE REPORT — Multi-school hosting, stage S1: SchoolMembership, empty PlatformAdmin group, `school_ids_for_admin`
Proposal: `0010-multi-school-hosting-PROPOSAL.md` §9 (S1) · ADR-0012 · Level: L3 · Date: 2026-10-19 · Commits: `ee8cfd6` (S1) and `8918434` (review finding F1) · Status: **S1 accepted by the owner; not pushed**. S2 and later, 2.2-0, 2.2 and 2.4 are NOT started.
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
- Security review: see the section below.

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

## SECURITY REVIEW (`/security-review`, run after the commit; read-only static review, all findings listed regardless of confidence)
Result: **no High or Medium issue newly introduced by `ee8cfd6`**; "S1 changes no access" confirmed by reading `access.py`, `permissions.py`, `decorators.py`, `service_auth.py`, `setup_staff_roles.py`, `admin.py`.
| # | Finding (confidence /10) | Severity | Handling (owner decision 2026-10-19) |
|---|---|---|---|
| F1 | A user in both `PlatformAdmin` and `SchoolAdmin` could grant themselves memberships (4) | Low (latent until S3) | **Fixed** in `8918434`: `clean()` and the admin picker reject/exclude dual-role accounts; 3 negative tests, mutation-checked |
| F2 | `clean()` is creation-time; the admin picker hides rows whose user no longer qualifies, so they cannot be edited, only deleted (3) | Low | **S2** (membership tooling: orphan report, `--deactivate`, `user` read-only on change; recorded in 0010 §9) |
| F3 | Empty school set must never be read as "no filter" by callers (2) | Info | **S3 test list** (empty set yields `.none()`; mutation check; recorded in 0010 §9) |
| F4 | Membership rows survive group removal; a re-added user regains the old scope (3) | Low | **S2** (as F2) |
| F5 | `created_by` is set only by the admin (2) | Info | No action |

**Review of the follow-up `8918434`** (also static, all findings): F1 is closed for the two paths the commit targets (admin form and `full_clean()`); no new vulnerability was introduced. It reports residual items that are **not** closed by `8918434` and are **OPEN, decision requested** (nothing has been changed for them):
| # | Residual item (confidence /10) | Severity | Proposed handling (not decided) |
|---|---|---|---|
| G1 | Group added after the membership exists: `clean()` is not re-run, and `school_ids_for_admin` would still return the schools of a user who later joins `PlatformAdmin` (8) | Medium now as latent; High once S3 reads memberships | Make `school_ids_for_admin` return the empty set for a user in `PlatformAdmin` (one cheap query; changes no S1 access because nothing calls the helper), and/or reject the second role on `User.groups` changes (`m2m_changed`); before S3 |
| G2 | Direct ORM/shell/`bulk_create`/`loaddata`/`update` skip `clean()` (9) | Low | Covered by the query-time check of G1; same limit as the other three `clean()` rules |
| G3 | A dual-role row cannot be deactivated in the admin ("invalid choice"), only deleted (7) | Low | Same as F2 (S2) |
| G4 | The group is matched by name; a renamed group silently stops the rule (5) | Info | Existing pattern across the code base; `setup_platform_role` could assert the name |
| G5 | Whether `SchoolAdmin` holds `auth.change_user`/`auth.change_group` and could add itself to `PlatformAdmin` (3) | Info | By design `setup_staff_roles` never grants `auth.*` (docstring; test P2-REQ-17 in `schools/tests.py`), and the stock Django user admin is the one in use (the `accounts` app is not installed); the permissions of the real Admin group are NOT VERIFIED |
Checked and safe: `.exclude(groups__name=...)` on the M2M join, the `elif` ordering, superuser-also-in-groups, every `has_*_permission` override.

Evidence for `8918434`: `students dashboard schools` **487** tests OK on SQLite (plus 34 `demo_intel`) and on PostgreSQL 16 (disposable container, test database only, removed afterwards); `schools/test_school_membership.py` 49 tests. Mutation checks: removing the `clean()` rule fails `test_user_holding_both_school_admin_and_platform_admin_cannot_be_a_member` and `test_joining_platform_admin_later_does_not_make_clean_pass_again`; removing the picker exclusion fails `test_user_choices_exclude_a_user_who_also_holds_platform_admin`; files restored and hash-verified.

## OWNER ACCEPTANCE
S1 (`ee8cfd6`) accepted 2026-10-19. Not pushed; the push awaits the owner's approval. S2 and later need their own explicit approval.
