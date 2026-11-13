# 0024 — Platform admin: what exists today, and the smallest way to create a school without Claude Code (NOTE, 2026-10-26)

Evidence only. No code was changed. Labels as in `CLAUDE.md` §2. Method: code read, plus a throw-away test run on an in-memory database (the probe was deleted afterwards, nothing was committed or written to a real database). Existing tests that pin the same facts are cited.

## 1. Is there a platform account in the demo seed?
**No.** `seed_demo` creates `demo_admin` (SchoolAdmin), `demo_gradelead`, `demo_teacher`, `demo_counselor`, `demo_parent`, `demo_student` and nothing else (`students/management/commands/seed_demo.py`; `scripts/start_demo.sh` creates no superuser). Neither a superuser nor a `PlatformAdmin` user exists in the demo.
How to get one, as today:
- **Superuser (the platform account that can do everything described below):** from `django_core`, `python manage.py createsuperuser` (RUNBOOK §2 says: use the normal settings, not the demo settings). Log in at `/login/`; `dashboard_view` / `home_url_for` send a superuser to `/admin/` (`dashboard/views.py:58`, `dashboard/home.py:11`).
- **PlatformAdmin (the narrower role):** `python manage.py setup_platform_role` creates the group with zero permissions; then create a user in `/admin/` (superuser needed) with **is_staff ticked** and the group `PlatformAdmin`. Where such a user landed after login: the login page (a gap: `home_url_for` had no branch for it). **Fixed 2026-10-26**: a staff PlatformAdmin now lands on `/platform/modules/` (`dashboard/home.py`, `dashboard/test_platform_landing.py`).
**Decided 2026-10-26:** the demo seed now creates `demo_platform` (PlatformAdmin, demo database only). **Onboarding decision:** option A now, option B (`create_school` command with an audit event) before the second pilot school; PlatformAdmin gets no extra powers; school creation stays with the superuser; S9 must be closed before real data.

## 2. What can each platform role do today?
Probe results (HTTP status when requesting the page as that user; 200 = allowed, 403 = refused, 302 = sent to the admin login):

| Task | Superuser | PlatformAdmin (staff) | Where |
|---|---|---|---|
| Create / define a School (name, code) | **yes** | **no** (403) | Django admin `/admin/schools/school/add/`; `has_add_permission` is superuser-only (`schools/admin.py`, `SchoolAdmin`). Command: none |
| Create the first SchoolAdmin account | **yes** (3 steps) | **no** | Django admin: Users → Add (`/admin/auth/user/add/`), then put the user in group `SchoolAdmin` (not staff, not superuser), then School memberships → Add (user + school). The membership picker lists only eligible users, so the order matters. Command: none |
| Set the academic year | yes, but not its job | no | The SchoolAdmin does it in the dashboard (`/school/`, RUNBOOK §2 step 5; tests `dashboard/test_school_pages.py`). The superuser can also edit `AcademicYear` in the Django admin (200) |
| Set module state (trial / licensed, dates) | **yes** | **yes** | Django admin `SchoolModule` (`/admin/schools/schoolmodule/add/`, 200 for both; audit-logged), or command `set_school_module <code> <module> --kind trial|licensed [--ends ...]` |
| Seed what a module needs (`mission` weights and rubric, vocabulary terms) | command only | command only | `seed_mission --school <code>`, `seed_vocabulary --school <code>` (RUNBOOK §3a). NOT POSSIBLE from any page |
| Open the operator page | **yes** | **yes** | `/platform/modules/` (read only; tests `dashboard/test_operator_page.py`: allowed, denied for SchoolAdmin even when staff, no student data in the HTML, one audit event per school) |
| Set AI call caps | yes | **no** (the fields are read-only without change permission) | Django admin, School change page |
| Edit the school's name | yes | no | Django admin, School change page |
| Edit branding / school profile | **NOT POSSIBLE** | NOT POSSIBLE | `School` has only name, code, the password-reset switch and the AI caps (`schools/models.py`). No logo, colors, address or profile fields exist |

Reading: **`PlatformAdmin` today can only manage module rows and open the operator page.** The group holds zero model permissions on purpose (`setup_platform_role`; ADR-0012), so it cannot create a school, a user or a membership. Everything needed to onboard a school needs the **superuser**.

## 3. What the platform roles cannot see; do school accounts reach `/admin/`?
- **Student records:** no. A superuser sees 0 rows from `/api/students/` and gets 403 on `/students/`, `/school/`, `/alerts/`, `/school/audit/`; the operator page contains school names, module keys and counters only (tests: `students/test_school_admin_scope.py::test_superuser_sees_no_school_data` and `::test_the_superuser_is_redirected_to_the_django_admin_and_denied_the_api_data`; `demo_intel/tests.py::test_the_platform_superuser_sees_no_students_on_the_demo_pages`; `dashboard/test_operator_page.py`). `Student` is not registered in the Django admin (403).
- **Caveat (not "no data"):** the superuser can list **every user account** in `/admin/auth/user/` (probe: student, parent and teacher accounts all shown) and the school-staff and teacher-assignment rows. Student and parent usernames are national ids (`dashboard/bulk_accounts.py`), so account names are visible to the platform account. This is the known open item "Django admin not school-scoped" (S9, `RUNBOOK` open risks). A PlatformAdmin sees none of it (only the module rows).
- **School-level accounts and `/admin/`:** no. SchoolAdmin, Grade Lead, Teacher, Counselor, Parent and Student all get a redirect to the admin login on every `/admin/...` page (probe). Reason: the Django admin needs `is_staff`, and every account-creation path in the product creates non-staff accounts (staff forms "never staff, never superuser"); a staff account also loses its scoped grants (`_may_hold_scoped_grants`). Conversely a SchoolAdmin who is made staff by hand is still refused the operator page (`test_a_school_admin_who_is_staff_is_still_denied`). The remaining risk is a human ticking `is_staff` on a school account; no automatic guard exists beyond the above (NOT VERIFIED further).

## 4. Smallest way to create a school end to end without Claude Code (works today)
All steps need the platform **superuser**. Nothing is built for this note.
1. (Once, terminal) `cd django_core && python manage.py createsuperuser`. Log in at `/login/`; you land on `/admin/`.
2. Admin → **Schools → Add**: name and a unique code (the code is read-only afterwards for non-superusers).
3. Admin → **Users → Add**: username and password for the first SchoolAdmin; save, then on the change page tick group **SchoolAdmin**; leave staff and superuser unticked. (Admin-created users are not flagged "must change password" — the flag is set only by bulk accounts and resets — so ask them to change it at `/account/` — from the middleware code, not exercised.)
4. Admin → **School memberships → Add**: that user and the school. Without it the SchoolAdmin sees nothing.
5. Modules: Admin → **School modules → Add** (module, kind trial or licensed, dates), or `python manage.py set_school_module <code> <module> --kind licensed`. Then, in a terminal, once per module that needs it: `python manage.py seed_vocabulary --school <code>` and, for mission, `python manage.py seed_mission --school <code>`. (These two are the only steps with no page.)
6. Give the SchoolAdmin the username and password. They log in at `/login/`, land on `/school/`, and follow the Persian quick-start (`/school/quickstart/`): academic year, classes, staff, students, bulk accounts.
7. Check on `/platform/modules/` (module state, days left) and ask the SchoolAdmin to look at `/school/audit/`.
Pain points: three admin forms in a fixed order, two terminal commands, the superuser also sees account lists of all schools, and nothing records "school created" in an audit trail (module changes and views are audited; school creation is not). Per the RUNBOOK, do not create a second real school before the open risks are accepted.

## 5. If you want less friction (proposal only; DECISION REQUIRED, nothing built)
| Option | What it is | Effort | Risks |
|---|---|---|---|
| A. Keep §4 and a one-page checklist | no code | none | human error; account lists visible to the superuser |
| B. Command `create_school --code --name --admin-username [--modules ...]` | one transaction: School + SchoolAdmin (random temporary password printed once, flagged "must change") + membership + optional module rows and seeds; audit event | about one commit, ~15 tests | still a terminal; creates a privileged account (Tier C) |
| C. Platform page **"New school"** (`/platform/schools/new/`) | the same transaction behind a form, with a one-time credentials sheet (like the bulk-accounts login sheet), superuser-only (or a new explicit permission for PlatformAdmin) | about 1-2 commits, ~25 tests, `/security-review` | Tier C: it creates a SchoolAdmin and a membership, so authN/authZ and tenancy are touched; separation of duties (a PlatformAdmin account must never also be a SchoolAdmin) must hold; the password is shown once and never stored; school creation must be audit-logged (no audit rows exist for it today); double submit and duplicate codes must fail cleanly; branding fields would be a separate model change |
Recommendation: A now (it works, is documented), B before the second pilot school, C only if you will onboard many schools or hand this to a non-technical operator. Decide whether `PlatformAdmin` should get these powers (today it has none) or stay a module-and-overview role.
