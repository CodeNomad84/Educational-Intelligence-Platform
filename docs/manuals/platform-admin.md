# Platform admin manual (superuser and PlatformAdmin)

Who this is: the people who run the platform, not a school. Two kinds exist today:
- **Superuser**: can do everything below. Created in a terminal (`createsuperuser`).
- **PlatformAdmin** (a staff account in the group `PlatformAdmin`): today can only manage module rows and open the operator page. It has no permission to create schools or users on purpose.
Neither role sees student records. Details and evidence: `docs/changes/0024-platform-onboarding-NOTE.md`.

## Log in
**Steps:** open `/login/`, enter username and password. A superuser lands on `/admin/`; a PlatformAdmin lands on the operator page `/platform/modules/` (fixed and tested 2026-10-26; before that it landed on the login page).
**Demo:** after `scripts/start_demo.sh --reseed` the user `demo_platform` (PlatformAdmin, synthetic) logs in with the same demo password as the other demo users. A superuser for the demo is created by hand (`createsuperuser`). Neither exists outside the demo seed.
**You do not see:** any student, grade, attendance, alert or plan. The student pages answer "not allowed".
**Ask:** the owner, if you do not have an account.

## Create a school (superuser only) — the 7-step checklist
Everything below needs the **superuser**. A PlatformAdmin cannot do it (no model permissions on purpose). Do not create a second real school before the open risks in `docs/RUNBOOK.md` are accepted.
1. **(Once, in a terminal)** `cd django_core && python manage.py createsuperuser`. Log in at `/login/`; you land on `/admin/`.
2. **School:** in a terminal `python manage.py create_school <code> "<name>"` (recommended: it also seeds the school's vocabulary), or `/admin/` → Schools → Add → name and a unique code. Both paths write a `school_create` audit event (detail `cmd` or `admin`). The code cannot be changed afterwards except by a superuser.
3. **First SchoolAdmin account:** Users → Add → username and password → Save → on the next page tick the group **SchoolAdmin**; leave "staff" and "superuser" unticked → Save. (The first password is not marked "must change"; ask them to change it at `/account/`. TO VERIFY in the running product.)
4. **Membership:** School memberships → Add → that user and the school. Without it the SchoolAdmin sees nothing. (The user picker only lists eligible users, which is why step 3 comes first.)
5. **Modules:** School modules → Add (module, kind trial or licensed, dates), or `python manage.py set_school_module <school_code> <module> --kind licensed`. Then in a terminal, once per school: `python manage.py seed_vocabulary --school <code>` (not needed after `create_school`), and for the mission module `python manage.py seed_mission --school <code>`. These two commands have no page.
6. **Hand over:** give the SchoolAdmin the username and password. They log in at `/login/`, land on `/school/` and follow the Persian quick-start (`/school/quickstart/`): academic year, classes, staff, students, bulk accounts.
7. **Check:** open `/platform/modules/` (module state, days left) and ask the SchoolAdmin to open `/school/audit/`. School creation is audit-logged since 2026-11-01 (the event belongs to the new school, so its SchoolAdmin sees it on `/school/audit/`).
**You see:** the new school in the lists. **You do not see:** a "New school" page (**NOT BUILT**; decision 2026-10-26: option A now, the command later; PlatformAdmin gets no extra powers).
**Ask:** the owner before creating a second real school.

## Switch modules on or off for a school
**Steps:** `/admin/` → School modules → Add: school, module (`advisor_ai`, `tutor_ai`, `exams`, `mission`), kind (trial needs an end date, licensed may be open), dates. Or in a terminal: `python manage.py set_school_module <school_code> <module> --kind licensed`. Ending a module means setting its end date; rows are never deleted. Some modules need a one-time terminal seed: `python manage.py seed_vocabulary --school <code>`, and for mission `python manage.py seed_mission --school <code>`.
**You see:** the module state in the operator page; every change is audit-logged.
**You do not see:** prices, plans or invoices (**NOT BUILT**; pricing is undecided).
**Ask:** the owner for trial length and licence terms (**PENDING POLICY**).

## Open the operator page
**Steps:** open `/platform/modules/` (a link "platform overview" is in the side menu of the dashboard pages for you). Use the "expiring within 14 days" filter.
**You see:** for each school: each module as locked, trial or licensed, end date, days left; AI calls today / this month against the caps.
**You do not see:** names, students, content of any kind. Every view is recorded once per school in that school's own audit log.

## Set AI call caps (superuser only)
**Steps:** `/admin/` → Schools → open the school → the two cap fields (daily, monthly). Empty means the platform default.
**You do not see:** what was asked of the assistant (only counts are kept).

## School name, branding, profile
**Steps:** the name can be changed on the same School page (superuser only). Logo, colors, address or other profile fields **do not exist** (**NOT BUILT**).

## Know the limits
- The Django admin is not school-scoped: a superuser can list every user account, including student and parent accounts (usernames are national ids) and staff assignments of all schools. Treat the superuser login as highly sensitive. Open item S9 in the checklist.
- School accounts cannot open `/admin/` (they are not staff).
