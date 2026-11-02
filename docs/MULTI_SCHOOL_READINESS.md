# MULTI_SCHOOL_READINESS (P9, 2026-11-02; derived from code and tests, code wins)

**What a second school needs, what exists, what is open.** Real data is not involved; everything is verified with synthetic schools.

| Item | State | Evidence |
|---|---|---|
| School row, vocabulary, rule defaults for a new school | `CURRENT` | `manage.py create_school` (audited, one transaction), `docs/manuals/platform-admin.md` |
| SchoolAdmin sees exactly their active memberships' schools; platform operators have no school data (S9) | `CURRENT` | `students/access.py::school_ids_for_admin`, `schools/test_admin_closure.py`, `schools/test_school_membership.py` |
| Every read goes through `visible_*` scopes; system jobs take ONE explicit school | `CURRENT` | `students/access.py` (`system_scope_*`), `schools/test_command_scope.py` (every command classified) |
| Per-school modules, trials and AI caps | `CURRENT` | `schools/entitlements.py`, `schools/ai_guard.py` |
| Per-school rules, strategies, documents, notifications, grade scale | `CURRENT` | `risk`, `interventions`, `docqa`; `students/scale.py` |
| **Second-school gate** (S10): two schools with marker data, no staff page of one shows anything of the other | `CURRENT` (new) | `schools/test_second_school_gate.py` (also asserts it is not vacuous) |
| Page-level check on a seeded demo school (6 roles, 390/1280 px) | `CURRENT` | `scripts/dev/page_audit.mjs` |
| Database privileges for several schools in one database | `CURRENT` in files, `NOT VERIFIED` on a server | R-04, `DEPLOYMENT.md` 4a |
| **S7: `national_id` unique per school instead of globally** | `DECISION REQUIRED` (owner; options in `changes/0020`); today a national id is globally unique and a duplicate is refused with one fixed message | `students/student_school.py` |
| S8: platform operators split from school data | partly `CURRENT` (admin closure S9, operator page); the rest waits for the owner | `dashboard/operator_page.py` |
| Cross-school integrity of existing data (class/school mismatches, memberships) | `CURRENT` as read-only checks | `check_student_school_ready`, `check_school_memberships`, `check_class_links`, `check_academic_years`, `compare_access_parity` |

**Before onboarding a real second school (owner/ops):** run the read-only checks above on the real database; decide S7; keep one `school_app` role for the whole installation (a school never gets its own database role); confirm per-school backups restore (`RUNBOOK.md`); agree the operator per school (`0028 P3-1`).
