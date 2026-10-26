# School admin manual

Who this is: the person who runs one school's data and accounts. You only ever see your own school. Start at `/school/`; the Persian quick-start page is `/school/quickstart/`.

## First time: set up the school
**Steps:** (1) academic year: `/school/years/` → add the year and mark it current. (2) classes: `/school/classes/` → New. (3) staff: `/school/teachers/`, `/school/gradeleads/`, `/school/counselors/`; give each person their roles and assignments (a teacher: class and subject; a grade lead: grade and year). (4) students and families: next section.
**You see:** the lists you created. **You do not see:** other schools.
**Ask:** the platform admin if a menu item you expect is missing or locked (modules).

## Create accounts in bulk from Excel
**Steps:** `/school/accounts/` → download the template → fill sheet `Students` (name, national id, grade, class; optional parent ids and names) and/or `Teachers` → upload → read the preview (nothing is saved yet; errors are listed per row) → confirm → save the login sheet that downloads. Keep national ids as text.
**You see:** a preview, then a one-time sheet with each account's first password. **You do not see:** the passwords again; they are not stored. If a sheet is lost, issue a new temporary password from the reset page.
**Ask:** nobody; but treat the sheet as confidential.

## Reset a password
**Steps:** `/school/resets/` → find the person → reset → give them the temporary password; they must choose a new one at first login. The same page has the switch "grade leads may reset passwords" (default off).
**Audit:** every reset is recorded.

## Look at one student (Student 360) and refer to a counselor
**Steps:** `/students/` → open a student → "پرونده ۳۶۰" (Student 360). Use the referral box to send the student to a counselor with a short reason.
**You see:** identity, enrollment per year, grades per year and subject, attendance summary, teacher recommendations, referrals and counselor notes of your school, and a summary of alerts and interventions.
**You do not see:** the text of an emotional-type intervention plan or its follow-ups; the message of an emotional or family alert; students of other schools.

## Review alerts
**Steps:** `/alerts/` → for a new alert, **Accept** or **Dismiss** with a reason (the note is required for "other"). A dismissed alert can be reopened by you. An accepted alert offers "create an intervention plan".
**You see:** type, severity, status, dates, who raised and who reviewed. **You do not see:** the message and the reviewer's note of emotional or family alerts (you can still decide on the metadata). A teacher's note-free status only.
**Ask:** the counselor for the substance of a sensitive alert.

## Intervention plans
**Steps:** `/interventions/` lists plans (default: open ones). Open a plan to see its status. You can create a plan (not an emotional one), start it, add follow-ups and close it with an outcome on non-emotional plans, cancel any plan, and hand a plan to another owner (an emotional plan only to a counselor or grade lead who sees the student). A closed plan shows its re-evaluation date (30 days after closing); plans past that date with nothing new are listed at the top.
**You do not see:** the goal, action plan, outcome note or follow-ups of an emotional plan, and you cannot create or own one. Every view of a plan page is recorded in the audit log.
**PENDING POLICY:** how long alerts and plans are kept; nothing is deleted automatically today.

## Audit log
**Steps:** `/school/audit/`. **You see:** who did what and when, with ids and codes only. **You do not see:** the content of notes, messages or plans.

## Modules (mission, exams, assistants)
**Steps:** locked modules stay visible in the menu and open an information page. Mission: `/mission/aggregate/` (counts per grade and branch status, groups under 5 hidden) and `/mission/weights/` (the weight sets: draft, simulate, send for approval, approve; the active set is read only, a copy becomes the next draft). Exams: `/exams/admin/` (per exam started / finished and first-try rate per topic, no names, groups under 5 hidden).
**You do not see:** individual students' scores in these overviews, any ranking, any export. The output is always "initial, not validated, not a decision".
**Ask:** the platform admin to switch a module on. **PENDING POLICY:** whether a second approver is required for mission weights (today one admin approves).

## Not built
Parent notifications, a parent view of alerts or interventions, an automatic risk engine (alerts are raised by hand), billing.
