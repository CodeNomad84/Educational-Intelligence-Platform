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
**You see:** identity, enrollment per year, grades per year and subject, attendance summary, teacher recommendations, referrals of your school, counselor notes while the referral is open, and a summary of alerts and interventions. Note text shown to you is recorded in the audit log (counts only). **After a referral is closed you see only that counselor notes exist and their dates, not their text** (owner decision 2026-10-28; the grade lead keeps reading them).
**The AI block is a demo:** «🤖 نمایش آزمایشی وضعیت (داده‌های تکمیلی موجود نیست)» asks the experimental model about this student. The school does not record homework completion, parent-communication counts or completed homework yet, so three of the numbers the model receives are placeholders; the result is therefore labelled «نمایشی / داده‌های تکمیلی موجود نیست», the percentage and the risk badge say «(نمایشی)», and it is **not a basis for a decision** (E2E audit F02, change 0044). The percentage is a whole number out of 100 in Persian digits: `۷۰%` means a 70 % risk. Each click spends one call from the daily AI quota.
**Counselor accounts and sensitive text:** you do not read emotional or family alert text or emotional plan text directly. Be aware that creating or resetting a Counselor account and referring students to it would give that account access to such text; these steps are recorded in the audit log and are accepted as an insider-trust risk (see SECURITY).
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
**Steps:** `/school/audit/`. **You see:** who did what and when, with ids and codes only. **You do not see:** the content of notes, messages or plans. Since 2026-11-01 list pages are recorded too: `list_view` with the page and the number of rows shown (for example `students:n24`, `alerts:n3`, `api_students:n24`), one line per school; a single student read through the API appears as `view_student_detail` with detail `api`; a new school appears as `school_create`. Pages with totals only (dashboard, school home) are not recorded.

## Modules (mission, exams, assistants)
**Steps:** locked modules stay visible in the menu and open an information page. Mission: `/mission/aggregate/` (counts per grade and branch status, groups under 5 hidden) and `/mission/weights/` (the weight sets: draft, simulate, send for approval, approve; the active set is read only, a copy becomes the next draft). Exams: `/exams/admin/` (per exam started / finished and first-try rate per topic, no names, groups under 5 hidden).
**You do not see:** individual students' scores in these overviews, any ranking, any export. The output is always "initial, not validated, not a decision".
**Ask:** the platform admin to switch a module on. **PENDING POLICY:** whether a second approver is required for mission weights (today one admin approves).

## Alert rules (`/rules/`)
**Steps:** set the grade scale maximum and the breaker percentage; create a rule (or start from a first proposal: "از پیشنهاد اولیه"); edit the thresholds; "Simulate" to see weekly counts on your own history (counts only, groups under 5 shown as "—", no names, no alerts created); submit for approval; approve (activate). Pause or archive at any time; to change an active rule, copy it as a new version. "Run now" runs the active rules for YOUR school; an IT person can schedule `run_rules`.
**You see:** rule versions, status, who created and approved, run history (including "breaker tripped: no alerts were raised, review the thresholds"), and per-rule counts of alerts raised, accepted and dismissed by reason (any count under 5 is shown as "—", and then the total is hidden too). **You do not see:** a score or level of any student; a list of students a rule matched (you see them as ordinary alerts after a run).
**Important:** the thresholds are a first proposal and NOT validated. Have your own teachers review them before activating. A score-based rule cannot be activated until the grade scale is set. A rule can only be of type academic, attendance or behavioral.
**Ask:** the owner/operator for scheduled runs. **PENDING POLICY:** how long rule hits and runs are kept.

## Not built
Parent notifications, a parent view of alerts or interventions, a scheduler for rules (run by command or button), ML risk, billing.

## Principal dashboard, support levels, behavior log, report card (since 2026-11-02)
**Steps:** `/dashboard/` shows one school (choose it at the top if you have several): students, attendance (30 days), average grade (45 days), unreviewed alerts, support levels, a weekly attendance chart, the students who need attention, the intervention loop (open, due, overdue, without follow-up, ready for re-evaluation) and a table per class. On the student list and Student 360 each student shows a **support level** (1 universal, 2 targeted, 3 intensive); it is calculated from open plans and unreviewed alerts and is not a label or diagnosis. On Student 360: **behavior notes** (positive or concern; add one at the bottom) and **کارنامه** (printable report card per term).
**You do not see:** rates of a class or group under 5 students ("—"); alert or plan text on the dashboard. **Ask:** the platform operator if the school selector is empty.

## راهبردهای مداخله
مدیریت مدرسه ← «راهبردهای مداخله»: فهرست پیشنهادی که هنگام ثبت برنامهٔ مداخله انتخاب می‌شود (افزودن، ویرایش، فعال/غیرفعال). شامل هیچ داده‌ای دربارهٔ دانش‌آموز نیست؛ فهرست پایه با دستور seed_strategies ساخته می‌شود.

## پروندهٔ ۳۶۰ و داشبورد (به‌روزرسانی ۱۴۰۵/۰۸/۱۱)
- **چه می‌بینید**: بالای پرونده میانگین، نرخ حضور و بیشترین افت اخیر؛ کد ملی به‌صورت `******` و چهار رقم آخر. «نمایش کامل» مقدار را نشان می‌دهد و در «گزارش دسترسی‌ها» ثبت می‌شود (`national_id_reveal`).
- **چه می‌کنید**: «ارجاع به مشاور» و «ساخت حساب دانش‌آموز» با دکمه (پنجره) باز می‌شوند. تاریخ‌ها شمسی‌اند و در فرم‌ها با سه لیست (روز، ماه، سال) انتخاب می‌شوند.
- **چه نمی‌بینید**: متن یادداشت‌های مشاور پس از بسته‌شدن ارجاع.
- **داشبورد**: سطح حمایت (۱ همگانی، ۲ هدفمند، ۳ فشرده) از هشدار و برنامه محاسبه می‌شود و برچسب دانش‌آموز نیست.
- **از چه کسی بپرسید**: پشتیبانی پلتفرم.

## اعلان‌ها و قاعدهٔ نگرانی رفتاری
زنگ بالای صفحه تعداد اعلان‌های خوانده‌نشده را نشان می‌دهد (هشدار جدید برای بررسی، نزدیک‌شدن سررسید برنامه). اعلان فقط یادآوری است و نام یا جزئیات دانش‌آموز ندارد؛ فقط مواردی را می‌بینید که خودتان مجاز به دیدنشان هستید. قاعدهٔ «نگرانی‌های رفتاری مکرر» (۳ یادداشت نگرانی در ۳۰ روز) با دستور `seed_rules` به‌صورت **پیش‌نویس** ساخته می‌شود و بدون شبیه‌سازی و تأیید شما فعال نمی‌شود؛ متن یادداشت‌ها هرگز به قاعده یا هشدار نمی‌رسد، فقط تعداد.

## کاتالوگ پیش‌فرض و درون‌ریزی Excel (قواعد)
«قواعد ← کاتالوگ پیش‌فرض»: فهرست قالب‌های آمادهٔ قاعده (بر پایهٔ شاخص‌های ABC و MTSS)؛ «بستهٔ پیشنهادی شروع» شش قالب است. «ساخت پیش‌نویس» فقط پیش‌نویس می‌سازد: باید شبیه‌سازی و سپس تأیید کنید؛ آستانه‌ها پیشنهادند و حد قانونی نیستند. قالب‌های نمره به «سقف مقیاس نمره» در تنظیمات نیاز دارند. در هر خانواده (غیبت، نمره، رفتار) قاعدهٔ قوی‌تر جای ضعیف‌تر را می‌گیرد و برای یک دانش‌آموز هشدار دوم ساخته نمی‌شود. «درون‌ریزی از Excel»: فایل نمونه را بگیرید، تکمیل و بارگذاری کنید؛ ابتدا گزارش ردیف‌به‌ردیف می‌بینید و بعد تأیید می‌کنید؛ قاعده‌ها پیش‌نویس و راهبردها غیرفعال ثبت می‌شوند. **نمی‌بینید/نمی‌توانید**: قاعدهٔ عاطفی یا خانوادگی، فرمول در فایل، فایل بزرگ‌تر از ۱ مگابایت.

## دستیار اسناد مدرسه
«دستیار اسناد» (ماژول دستیار هوشمند): اسناد **غیرشخصی** (آیین‌نامه، تقویم، روال‌ها) را در «مدیریت اسناد» بارگذاری کنید (txt، md، docx؛ با تأیید اینکه دادهٔ شخصی دانش‌آموزان ندارد). سندی که شناسه، تلفن، ایمیل یا نام دانش‌آموزان همین مدرسه دارد پذیرفته نمی‌شود. کادر مدرسه از «دستیار اسناد» می‌پرسد و بخش‌های مرتبط را با نام سند می‌بیند. «پاسخ هوشمند» به‌طور پیش‌فرض خاموش است و فقط با مدل **محلی** کار می‌کند (تنظیم سرور با پشتیبانی)؛ سقف روزانه/ماهانه اعمال می‌شود و پاسخ باید به سند ارجاع بدهد. متن سؤال‌ها در گزارش دسترسی ثبت نمی‌شود، فقط شمارش. **نمی‌بینید**: مدل‌های خارجی؛ دادهٔ دانش‌آموز در هیچ پرسشی ارسال نمی‌شود.
