# Grade lead manual

Who this is: the person responsible for one grade (matched through the students' current enrollment in the current academic year). You land on `/grade/`.

## See your grade
**Steps:** `/grade/` (dashboard of your grade) and `/students/` (list). Open a student, then "پرونده ۳۶۰" (Student 360).
**You see:** students of your grade only; identity, grades, attendance summary, recommendations, referrals, and a metadata summary of alerts and interventions.
**You do not see:** other grades or schools. If the school year has not been rolled over or your assignment has the wrong year, your students disappear (it fails closed): ask the school admin.
**Ask:** the school admin for assignment problems.

## Refer a student to a counselor
**Steps:** on the Student 360 page use the referral box (counselor and a short reason). The counselor then sees that student until the referral is closed.
**You see:** the referral and, on the Student 360 page, the counselor's notes of students of your own grade, read only (owner decision 2026-10-26: you are the main implementer of the counselor's advice). Notes stay readable after the referral is closed. You cannot write or edit notes. Each time note text is shown to you it is recorded in the audit log (counts only, no text).
**You do not see:** notes of other grades or schools. Note the difference: for emotional or family alerts and for the text of emotional intervention plans you see metadata only.

## Raise and review alerts
**Steps:** "ثبت نگرانی" on a student page raises an alert. `/alerts/` lists alerts of your grade: Accept, or Dismiss with a reason (note required for "other"). Accepted alerts offer "create an intervention plan".
**You do not see:** the message and reviewer note of emotional or family alerts unless you raised them (metadata only; you can still decide).

Some alerts are raised by an **alert rule** your school activated: the alert says "raised by rule X" and its text shows the numbers behind it (for example absence rate or average). It is not a diagnosis; accept or dismiss it like any other. You cannot edit rules; ask the school admin if a rule raises too many alerts.

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

## Support levels, behavior notes, report card (since 2026-11-02)
On your student list and Student 360 each student of your grade shows a support level (calculated from open plans and unreviewed alerts; not a diagnosis). On Student 360 you read and add behavior notes (positive or concern) and open the printable report card per term. **You do not see:** students outside your grade.

## به‌روزرسانی ۱۴۰۵/۰۸/۱۱
پروندهٔ ۳۶۰ دانش‌آموزان پایهٔ شما: خلاصه (میانگین، حضور، افت اخیر) در بالا؛ کد ملی ماسک است و «نمایش کامل» ثبت می‌شود. در «هشدارها» هر مورد را می‌پذیرید یا رد می‌کنید و برای موردهای پذیرفته‌شده «برنامهٔ مداخله» می‌سازید؛ می‌توانید از «کتابخانهٔ راهبردها» شروع کنید (متن قابل ویرایش است). یادداشت رفتاری (مثبت یا نگرانی) و کارنامه از همین پرونده. تاریخ‌ها شمسی‌اند. **نمی‌بینید**: دانش‌آموزان پایه‌های دیگر و محتوای جلسات مشاوره. **سؤال**: مدیر مدرسه.

زنگ بالای صفحه: اعلان هشدارهای جدید پایهٔ شما و سررسید برنامه‌های مداخله؛ بدون نام دانش‌آموز. فقط موارد داخل محدودهٔ خودتان را می‌بینید.

## دستیار اسناد
اگر ماژول فعال باشد، در منوی «دستیار» گزینهٔ «دستیار اسناد مدرسه» را می‌بینید و از آن دربارهٔ آیین‌نامه‌ها و روال‌های مدرسه می‌پرسید (اگر مدیر دستیار را خاموش کرده باشد، این گزینه نمایش داده نمی‌شود). نام یا شناسهٔ دانش‌آموز را در سؤال ننویسید (پذیرفته نمی‌شود). پاسخ فقط از اسناد غیرشخصی مدرسه است و پیشنهادی است؛ تصمیم با شماست. بعد از زدن «پرسش» دکمه غیرفعال می‌شود و این پیام را می‌بینید: «در حال ارسال… ممکن است تا ۳۰ ثانیه طول بکشد»؛ در این فاصله دوباره کلیک نکنید. **نمی‌بینید**: داده یا نمرهٔ دانش‌آموز در این دستیار. **سؤال**: مدیر مدرسه.
