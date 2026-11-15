# Teacher manual (subject teacher)

Who this is: a teacher assigned to one or more classes and a subject. You land on `/teacher/`.

## Enter grades and recommendations
**Steps:** `/teacher/` → choose your class and subject → the sheet: add a grade; open a student to write a recommendation. A recommendation is staff-only unless you tick "visible to the student" (then the student and parents can read it).
**You see:** the students of that class (name and class, limited details). **You do not see:** national ids, parents' phones, attendance, other classes or subjects, other teachers' grades.
**Ask:** the school admin if a class or subject is missing from your list.

## Raise a concern about a student
**Steps:** open the student page → "ثبت نگرانی" → type, severity, a short factual description → save. Write only what you observed.
**You see afterwards:** `/alerts/` lists only the alerts you raised, with status (new / accepted / dismissed) and the reason code.
**You do not see:** who reviewed it beyond that, the reviewer's note, any intervention plan, or alerts raised by others.
**Ask:** the grade lead or the school admin about what happened.

## Question bank and exams (if the exams module is licensed)
**Steps:** `/exams/teacher/` → topics (codes like `math.ch3.fractions`), write a question with an explanation for every option, or import a CSV (preview first, nothing saved until you confirm) → get a question approved (it stays a draft until you do) → create an exam for your classes and publish it. Results: per exam, students of your classes; first-try percentages only from 5 solved questions, per-question figures only from 5 students.
**You see:** your own subject and classes. **You do not see:** time compared between students, ranking, other teachers' banks, any export. A question can be edited only by its author and only until its first attempt.

## Mission observations (if the mission module is licensed)
**Steps:** `/mission/` → open an activity → the grid: score the indicators you actually observed ("not observed" is allowed and is excluded). `/mission/students/<id>/report/` shows only a status for your own observations and the indicators still to observe.
**You do not see:** other people's scores, any suggested path, the weights. (Whether teachers may fill the activity-choice and parent-meeting forms: not allowed today; owner decision.)

You do not see alerts raised by alert rules (only alerts you raised yourself) and you have no rules page.

## Not built
Attendance entry by teachers (**TO VERIFY**: no teacher attendance page exists in `dashboard/urls.py`), parent messaging.

## Behavior notes (since 2026-11-02)
On a student's page in your class (`/teacher/...`) you can add a short positive or concern note at the bottom. **You see:** only the notes you wrote yourself. **You do not see:** notes by other staff, support levels, report cards.

## به‌روزرسانی ۱۴۰۵/۰۸/۱۱
یادداشت رفتاری (مثبت یا نگرانی) برای دانش‌آموزان کلاس‌های خودتان ثبت می‌شود و فقط یادداشت‌های خودتان را می‌بینید. تاریخ‌ها شمسی‌اند و با سه لیست روز، ماه و سال انتخاب می‌شوند. کد ملی دانش‌آموزان را نمی‌بینید. **سؤال**: مسئول پایه.

## دستیار اسناد
اگر ماژول فعال باشد، در منوی «دستیار» گزینهٔ «دستیار اسناد مدرسه» را می‌بینید و از آن دربارهٔ آیین‌نامه‌ها و روال‌های مدرسه می‌پرسید (اگر مدیر دستیار را خاموش کرده باشد، این گزینه نمایش داده نمی‌شود). نام یا شناسهٔ دانش‌آموز را در سؤال ننویسید (پذیرفته نمی‌شود). پاسخ فقط از اسناد غیرشخصی مدرسه است و پیشنهادی است؛ تصمیم با شماست. بعد از زدن «پرسش» دکمه غیرفعال می‌شود و این پیام را می‌بینید: «در حال ارسال… ممکن است تا ۳۰ ثانیه طول بکشد»؛ در این فاصله دوباره کلیک نکنید. **نمی‌بینید**: داده یا نمرهٔ دانش‌آموز در این دستیار. **سؤال**: مدیر مدرسه.
