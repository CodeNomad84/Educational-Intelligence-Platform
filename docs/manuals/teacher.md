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

## Not built
Attendance entry by teachers (**TO VERIFY**: no teacher attendance page exists in `dashboard/urls.py`), parent messaging.
