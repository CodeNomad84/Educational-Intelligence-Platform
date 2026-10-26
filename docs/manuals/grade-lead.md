# Grade lead manual

Who this is: the person responsible for one grade (matched through the students' current enrollment in the current academic year). You land on `/grade/`.

## See your grade
**Steps:** `/grade/` (dashboard of your grade) and `/students/` (list). Open a student, then "پرونده ۳۶۰" (Student 360).
**You see:** students of your grade only; identity, grades, attendance summary, recommendations, referrals, and a metadata summary of alerts and interventions.
**You do not see:** other grades or schools. If the school year has not been rolled over or your assignment has the wrong year, your students disappear (it fails closed): ask the school admin.
**Ask:** the school admin for assignment problems.

## Refer a student to a counselor
**Steps:** on the Student 360 page use the referral box (counselor and a short reason). The counselor then sees that student until the referral is closed.
**You see:** the referral in the Student 360 page. **TO VERIFY:** by code (`visible_counselor_notes`) a grade lead can read the counselor's notes of students of the own grade, read only; confirm with the owner that this is wanted before publishing.

## Raise and review alerts
**Steps:** "ثبت نگرانی" on a student page raises an alert. `/alerts/` lists alerts of your grade: Accept, or Dismiss with a reason (note required for "other"). Accepted alerts offer "create an intervention plan".
**You do not see:** the message and reviewer note of emotional or family alerts unless you raised them (metadata only; you can still decide).

## Intervention plans
**Steps:** `/interventions/` → plans of your grade. Create a plan from an accepted alert or directly; open it to start, add follow-ups, close with an outcome, or cancel. You may own an emotional plan you created; then only you and a counselor with an open referral can read its text.
**You do not see:** the text of emotional plans owned by someone else (type, status, dates, owner, outcome code only).
**PENDING POLICY:** retention; whether real children's cases may be recorded before the consent policy exists (synthetic only for now).

## Reset passwords (only if the school enabled it)
**Steps:** `/grade/resets/` → Student and Parent accounts of your grade, up to 20 per hour; a refused attempt is logged for the school admin.
**You do not see:** staff accounts or other grades.

## Mission module (if licensed)
**Steps:** `/mission/` → open an activity → the observation grid; `/mission/students/` → a student's report (who gave which score is visible to you); forms for activity choices and parent meetings; the plan with 2-3 suggested paths is written at the bottom of the report.
**You do not see:** a ranking or a final decision; every result says "initial, not validated, not a decision, never for admission or placement".

## Exams overview (if licensed)
**Steps:** `/exams/lead/`: your grade's students per subject, name order, figures only from 5 solved questions. **You do not see:** time compared between students.
