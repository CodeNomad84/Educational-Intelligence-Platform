# Counselor manual

Who this is: the school counselor. You see a student only while an **open referral** to you exists. You land on `/counselor/`.

## See your cases
**Steps:** `/counselor/` lists students referred to you → "مشاهدهٔ پرونده" opens the case page: the reason for the referral, the Student 360 summary, and your notes.
**You see:** only referred students of your school. **You do not see:** any other student (a student without an open referral is "not found"), other schools, other counselors' cases.
**Ask:** the school admin or grade lead who referred the student.

## Write notes and close a case
**Steps:** on the case page add a note. "Close referral" ends your access to that student at once (your notes stay for the grade lead; the school admin sees only that they exist and their dates).
**You see:** your notes. While the referral is open the school admin and the grade lead of the student's grade can read them too, read only (owner decisions 2026-10-26 and 2026-10-28); after you close the case the grade lead keeps reading them and the school admin sees only that notes exist and their dates (no text). Each time note text is shown to anyone (you included) it is recorded in the audit log (counts only, no text). A "counselor only" option per note is a future idea, not built. **You do not see:** the student again after closing, unless referred again (after closing you see no notes at all).
**PENDING POLICY:** parental consent states (awaiting parent consent, declined, active), the crisis / escalation path, retention of counseling records, satisfaction feedback. None of these workflows exist yet.

## Alerts about your students
**Steps:** `/alerts/` shows alerts of referred students. You can raise one ("ثبت نگرانی" on the student page) and accept or dismiss alerts (note required for "other").
**You see:** the message and reviewer note of emotional and family alerts of your open cases (you and the person who raised an alert are the only readers; the school admin and grade lead see metadata only). Each time such a text is shown it is recorded in the audit log (no content in the log).
**You do not see:** alerts of students without an open referral.

Alerts raised by an **alert rule** show "raised by rule X" and the numbers that led to it (only for students of your open cases). You cannot edit rules.

## Intervention plans
**Steps:** `/interventions/` → plans of your cases. Create a plan (any type, including emotional), start it, add follow-ups, close it with an outcome, cancel it. A school admin may reassign an emotional plan to you.
**You see:** the full text of every emotional plan of a student with an open referral to you, including plans owned by others. **You do not see:** these texts once the referral is closed (the plan row also disappears from your list).
**PENDING POLICY:** retention; recording real children's cases before the consent policy.

## Mission reports (if licensed)
**Steps:** `/mission/students/` → a referred student's report. Read only; observers are shown anonymously.

## به‌روزرسانی ۱۴۰۵/۰۸/۱۱
در صفحهٔ پروندهٔ ارجاعی کد ملی ماسک است؛ «نمایش کامل» ثبت می‌شود و فقط تا زمانی کار می‌کند که ارجاع باز است. تاریخ‌ها شمسی‌اند. **نمی‌بینید**: دانش‌آموزان بدون ارجاع باز.

زنگ بالای صفحه: اعلان هشدار برای دانش‌آموزان با ارجاع باز؛ با بسته‌شدن ارجاع اعلان‌های آن دانش‌آموز نمایش داده نمی‌شود.
