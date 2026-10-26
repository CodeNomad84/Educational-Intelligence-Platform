# Platform admin manual (superuser and PlatformAdmin)

Who this is: the people who run the platform, not a school. Two kinds exist today:
- **Superuser**: can do everything below. Created in a terminal (`createsuperuser`).
- **PlatformAdmin** (a staff account in the group `PlatformAdmin`): today can only manage module rows and open the operator page. It has no permission to create schools or users on purpose.
Neither role sees student records. Details and evidence: `docs/changes/0024-platform-onboarding-NOTE.md`.

## Log in
**Steps:** open `/login/`, enter username and password. A superuser lands on `/admin/`. A PlatformAdmin: where they land is **TO VERIFY**; open `/admin/` or `/platform/modules/` directly.
**You do not see:** any student, grade, attendance, alert or plan. The student pages answer "not allowed".
**Ask:** the owner, if you do not have an account.

## Create a school (superuser only)
**Steps:** `/admin/` → Schools → Add → name and a unique code (the code cannot be changed afterwards by anyone but a superuser). Then create the first school administrator: Users → Add (username, password) → on the next page tick the group **SchoolAdmin** and leave "staff" and "superuser" unticked. Then School memberships → Add (that user and the school); without it the administrator sees nothing.
**You see:** the new school in the list; the administrator can log in at once.
**You do not see:** a "New school" page or a wizard (**NOT BUILT**; the proposal is in 0024 §5).
**Ask:** the owner before creating a second real school (rule in `docs/RUNBOOK.md`).
Note: the first administrator is not forced to change the password at first login (**TO VERIFY**); ask them to change it at `/account/`.

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
