# CHANGE PROPOSAL — Phase 2.2a: temporal data model (academic years, enrollments, year-aware records)
Level: **L3** (schema, data migration, access matching, sensitive-data retention) · Status: **APPROVED for 2.2a-1..3 (owner 2026-10-16); 2.2a-4 only behind a parity test and as its own commit; `Recommendation`, real data and retention decisions DEFERRED**
Depends on: ADR-0003/0004/0005 (ACCEPTED), ADR-0010 (partly). Draft decision record: `docs/adr/0011-temporal-data-model.md` (DRAFT).
Blocks: Phase 2.2 (Student 360), 2.2b (grade entry), 2.2c (recommendations). Supersedes the "show all dates" option of D-22-1.
Owner decisions applied: D-22-1 = option (b) extended (do not build the 360 page on the flat model); D-22-2 Parent staff-only for now; D-22-3 SchoolAdmin sees all sections.

## 1. Requirement (owner, 2026-10-16)
The platform retains each student's data across ALL school years (including historical years, possibly imported) to show: trends within the current year, comparison with past years, improvement recommendations given earlier, and the whole educational/behavioural path through the school.

## 2. CURRENT behaviour — how time is stored today (read-only inspection, evidence)
| Item | What is stored | Time dimension | Evidence |
|---|---|---|---|
| `Student.grade` | one integer 7–12 | **current value only**; overwritten by the import `update_or_create` and by the form/admin; no history | `students/models.py:14`, `students/views.py:170` |
| `Student.school_class` (+ `school`, `class_name` mirror) | one nullable FK; `class_name` is overwritten from the class | **current class only**; relinking replaces it, no membership history (only Django's admin log text) | `students/models.py:31-85` |
| `SchoolClass.academic_year` | free text ≤20, blank allowed, unique with (school, title) | the only year concept; **no format rule, no dates, no "current year"**; class rows of different years are separate rows | `schools/models.py:38-53` |
| `GradeLeadAssignment.academic_year` | free text, must equal the class string exactly | matching is **string equality**: `1404` ≠ `1404-1405` ≠ `۱۴۰۴` silently grants nothing | `students/access.py:63-66` |
| `Grade` | student, subject, exam_type, score, date | **date only**; no year, class, grade-in-year, term, teacher, entered_by, source | `students/models.py:89-119` |
| `Attendance` | student, date, status, note; unique (student, date) | **date only**; no class/year | `students/models.py:121-140` |
| Student deletion | `Grade`/`Attendance` are `on_delete=CASCADE` | deleting a student **destroys their whole record** | `students/models.py` |
| Import | upsert keyed by `national_id`; class matched by title only; **no year column**; titles with several years are `ambiguous` | overwrites current fields; cannot carry a historical year | `students/views.py:154-170`, `class_resolution.py:31-35` |
| Seed / demo | dates relative to "today" (120 days); no year | demonstration only | `seed_demo.py:107-110` |

**History lost on grade promotion (CURRENT):** (1) the previous `grade` integer (overwritten); (2) the previous class membership (overwritten, `class_name` mirror too); (3) which year/class/grade a past `Grade` or `Attendance` row belonged to — it survives only as a bare date; (4) which teacher entered it; (5) a returning/repeating student's earlier years are indistinguishable; (6) a re-import in a new year silently replaces phone/jobs/grade; (7) deleting a student cascades away all grades and attendance; (8) a yearly rollover of Grade Lead assignments cannot be matched when the year strings differ in format. Past rows are not lost from the database, they are **unattributable**, so no trend-versus-past-year comparison can be made correctly.
`demo_intel` (`StudentObservation`, `CounselingNote`, `InterventionRecord`) are DEMO-scope models with their own dates, not part of this design.

## 3. Proposed model (additive; old columns untouched until the last step)
### 3.1 `schools.AcademicYear` (per school; replaces free-text years)
`school` FK (PROTECT) · `code` canonical e.g. `1404-1405` · `label` display · `start_date`, `end_date` (Gregorian, entered by an admin, never computed) · `is_current` (at most one per school; partial unique constraint) · timestamps. Unique (school, code); date ranges of one school must not overlap (validated in `clean()`, checked by a command). No new dependency (no Jalali library): dates are stored, not derived.
- `SchoolClass.academic_year` becomes an FK; the old char field is kept as `academic_year_label` during transition.
- `GradeLeadAssignment.academic_year` becomes an FK; `TeacherAssignment` is scoped through its class's year.
- **Format variants** are normalised by one function (digits `۰-۹`/`٠-٩` → ASCII; separators `- / – _ \` and whitespace; `1404`, `1404-1405`, `1404-05`, `1404/1405`, `۱۴۰۴-۱۴۰۵` → `1404-1405` as start year + 1). A value that cannot be parsed to exactly one start year (`404`, `۱۴`, words, two different start years) is **unresolved**: reported, never guessed, and its class/assignment stays unmatched (fail closed).

### 3.2 `students.Enrollment` (one student in one year)
`student` FK (PROTECT) · `academic_year` FK (PROTECT) · `school_class` FK null (PROTECT) · `grade` smallint 7–12 (grade **in that year**) · `status` (`active`, `promoted`, `retained`, `transferred_out`, `transferred_in`, `graduated`, `withdrawn`) · `started_on`, `ended_on` null · `source` (`manual`, `import`, `backfill`) · `import_batch` FK null · `created_by`, timestamps. Constraint: at most one open (`ended_on` null) enrollment per (student, academic_year); a mid-year class change closes one row and opens another. `Student.grade/school_class/class_name` stay as the **current-state mirror** of the open enrollment of the current year (like `class_name` today) until step 2.2a-4.

### 3.3 Year-aware records
- `Grade.enrollment` and `Attendance.enrollment`: nullable FK (PROTECT) first, later required for new rows. Enrollment carries year, class and grade-in-year, so no separate year/class columns are duplicated. `Grade` also gains `entered_by` (nullable) and `source`/`import_batch`.
- New natural key for `Grade`: (enrollment, subject, exam_type, date), unique, so historical re-imports are idempotent. `Attendance` keeps unique (student, date).
- Deleting a `Student` with academic history is blocked (`PROTECT`); removal is an explicit anonymisation procedure (D24-3).

### 3.4 `students.Recommendation` (improvement recommendations; never deleted)
`student` FK (PROTECT) · `enrollment` FK (PROTECT; year + class + grade) · `subject` (shared vocabulary, blank = general) · `author` FK (SET_NULL) + `author_name`/`author_role` snapshot (survives account deletion) · `text` · `visibility` (`author_only`, `subject_team`, `grade_staff`, `school_admin`) · `supersedes` FK null · `retracted_at/by/reason` · `created_at`. Append-only: an edit creates a new row that supersedes the old one; `delete()` and admin delete are disabled; retraction hides text from non-admin roles but keeps the row. Writing UI is 2.2c; this phase only creates storage and access rules.

### 3.5 `students.ImportBatch`
kind (`roster`, `grades`, `attendance`), `academic_year` FK, file SHA-256, uploaded_by, counts, dry_run flag, timestamps. Every imported row points to its batch, so a batch can be reported and reverted as a unit.

## 4. Migration and backfill (report first, no silent guesses)
Each step is its own migration or command, reversible, tested on SQLite and PostgreSQL, and on a COPY of `data/postgres` before real use (owner executes).
1. **2.2a-1 Schema only (additive):** `AcademicYear`, `Enrollment`, `ImportBatch`, `Recommendation`, nullable FKs. No data movement; no behaviour change; no access change.
2. **2.2a-2 Report:** read-only `check_academic_years` (counts and strings only): distinct `SchoolClass.academic_year` and `GradeLeadAssignment.academic_year` values with normalised result (resolved / unresolved / variants of one year); classes without year; year ranges overlapping; then `check_enrollment_backfill`: students with a class (candidate: year = class year, grade = `Student.grade`, flagged if `SchoolClass.grade` disagrees), students without a class (**no enrollment is created**), mixed-grade classes, `Grade`/`Attendance` rows whose date falls in zero or several year ranges, in a year where the student has no enrollment, or before the earliest year.
3. **2.2a-3 Admin creates `AcademicYear` rows** (admin site; dates are never inferred). `--apply` commands run only after the report is reviewed: create enrollments (`source=backfill`), link `Grade`/`Attendance` where date ∈ year range AND the student has exactly one enrollment in that year; everything else stays NULL and is listed. Idempotent, one transaction per batch, writes counts.
4. **2.2a-4 Switch access matching** (section 6) behind a parity test; then make `enrollment` required for new rows.
**Rollback:** steps 1–3 are additive, so rolling back = reverse migrations (tables/columns dropped; old columns intact) or `--revert-backfill` (deletes `source=backfill` enrollments and clears the links). Step 4 is reverted by reverting the commit. Backup before every real-DB step.

## 5. Historical import path (year-aware)
- New import mode with a required `academic_year` (existing code, e.g. `1403-1404`) chosen by the admin, not read from free text per row. Three templates: `roster` (national_id, grade, class title, status), `grades` (national_id, subject key, exam_type, score, date), `attendance` (national_id, date, status).
- Always dry-run first with a report; commit is a second explicit action.
- A historical file **never** changes current `Student` fields (name, phone, grade, class link); unknown `national_id` rows are rejected and listed, not created.
- Dates are checked against the year's range; subject keys against the vocabulary; scores against a range validator (also for entry, 2.2b).
- Idempotent through the natural keys above; each row carries `import_batch`; a batch can be reverted.
- The current-year import (today's endpoint) keeps working and additionally writes/updates the open enrollment.

## 6. Impact on access (`visible_students`, Grade Lead, Subject Teacher)
- **Today:** Grade Lead = school + `Student.grade` + linked class active with `academic_year == assignment.academic_year` (string). Subject Teacher = student in a class with an active assignment.
- **After 2.2a-4:** "current" means an open enrollment in the school's `is_current` year. Grade Lead: `Enrollment.grade == assignment.grade` in that year (the grade **in the current year**, which fixes promotion edge cases) and class active. Subject Teacher: open enrollment in a class with an active assignment in the current year.
- `visible_students` still returns `Student` rows with `full_tier`; the contract and the field policy do not change. Matching moves from string equality to FK equality; unresolved year strings grant nothing.
- **History access is separate from current-student scope** (section 7): being able to see a student today does not by itself grant any past-year row.
- Parity test: on a seeded database, old rule and new rule must return identical sets before the switch (stop on any difference).
- Query cost: joins through `Enrollment`; indexes below.

## 7. Indexes and constraints
`Enrollment`: (student, academic_year), (academic_year, school_class), (academic_year, grade, status), partial unique (student, academic_year) where `ended_on` IS NULL. `AcademicYear`: unique (school, code), partial unique (school) where `is_current`. `Grade`: (enrollment, subject, date), unique (enrollment, subject, exam_type, date). `Attendance`: (enrollment, date). `Recommendation`: (student, enrollment), (enrollment, subject). All supported on SQLite and PostgreSQL (partial indexes included).

## 8. Per-role history visibility matrix (PROPOSED; DECISION REQUIRED D-22-4)
| Data from a PAST year | SchoolAdmin | Grade Lead (student is in own CURRENT grade) | Subject Teacher (student in own CURRENT class) | Parent (own child) |
|---|---|---|---|---|
| Enrollment path (year, class, grade, status) | all years | yes, all years (to see the path) | **no** (current class only) | staff-only for now (D-22-2) |
| Grades | all subjects, all years | **all subjects, all years** | **own subject only**, all years of that subject for this student | later; D-22-2 |
| Attendance | all years | aggregates per year (rate, counts); daily rows only for the current year | **none** (as today) | later |
| Improvement recommendations of past years | all, incl. retracted | **OWNER 2026-10-16: until the 2.4 audit log exists, free text is SchoolAdmin only.** Afterwards: `grade_staff`/`school_admin` visibility; structured fields (subject, year, status) per matrix | same: free text SchoolAdmin only for now; afterwards own-subject `subject_team`/`grade_staff` | no (until a parent-facing text policy exists) |
| Identity fields (`national_id`, phone, parents) | yes | current rules (own grade) | no | own child |
| Counseling / behaviour notes | no (separate counseling policy, not in 2.2a) | no | no | no |
Recommendation: history is **opt-in per role**, not inherited from "can see the student today". A student who left the grade (promoted) is no longer visible to the old lead except through an explicit rule; recommend: a former Grade Lead sees nothing of students no longer in their grade.
**Privacy risk — a new lead/teacher inheriting earlier notes:** free-text recommendations can carry labels or opinions that follow a child for years (confirmation bias, stigma, wrong attribution). Mitigations proposed: (1) visibility levels set by the author, default `subject_team`; (2) free text of past years hidden for non-admin roles unless marked shareable; (3) a read of past-year text by a new staff member is audit-logged once 2.4 exists, and past-year free text stays unavailable to non-admins until the audit log ships; (4) show structured outcome (acted/not acted, subject) before text; (5) retraction instead of deletion; (6) no AI/RAG use of historical recommendations without an approved policy (`AI_GOVERNANCE.md`).

## 9. Retention and privacy decisions for D24 (DECISION REQUIRED, recommendation first)
| # | Question | Recommendation |
|---|---|---|
| D24-1 | Keep a graduated student's academic record, and for how long? | Keep the academic record (enrollments, grades, attendance) indefinitely as the school's permanent record; retention period and legal basis for any other data are the owner's/legal decision. Identity fields of graduates restricted to SchoolAdmin. |
| D24-2 | Transferred-out / withdrawn students | Keep read-only; access SchoolAdmin only; no new rows; no Grade Lead/Teacher access after the transfer date. |
| D24-3 | Deletion and anonymisation (e.g. family request, end of retention) | No hard delete of a student with history (PROTECT). One explicit, irreversible anonymisation procedure by SchoolAdmin with a reason: name → neutral token, `national_id`/phone/parents' data removed or hashed; aggregates and year/subject rows retained; recommendation text removed or replaced by a tombstone. Requires owner approval per case. |
| D24-4 | How long are improvement recommendations (free text) retained and shown? | Row kept (never deleted); free text visible to non-admins for the current and previous year only; older text SchoolAdmin only, unless the owner decides otherwise. |
| D24-5 | Counseling and behavioural data | Out of 2.2a. Separate, stricter retention and access with consent (2.6/2.7, D5/D24 legal review). |
| D24-6 | Backups and exports | Backups follow the same retention; no historical record in exports or AI prompts without policy; anonymisation also applies to restored copies (document the procedure). |
| D24-7 | Parent access to history | Decide after D-22-2 is lifted; default no, current page unchanged. |
| D24-8 | Who may import historical data | SchoolAdmin only, with dry-run, batch id and reversible batch. |

**Owner status of D24 (2026-10-16):** recorded as direction; retention period and legal basis are an owner decision with legal advice; no `Recommendation` model and no real data until decided.

## 10. Tests (both backends, one step at a time)
Year normalisation table (variants, unresolved, ambiguous), overlap and single-current constraints; enrollment constraints; backfill report counts and idempotence; no silent guess (unlinked student gets no enrollment, row outside ranges stays NULL); migration forward/backward on SQLite and PostgreSQL and on a copy of `data/postgres`; access parity (old vs new), promotion case (grade 10 → 11 changes the lead who sees the student), unresolved year grants nothing; history matrix per role in HTML and API; recommendation append-only (no delete via ORM, admin, API; retraction hides text but keeps row); import dry-run vs commit, idempotence, batch revert, historical file never touches current fields; choke-point guard extended to new readers; anonymisation procedure.

## 11. Risks
Large cross-cutting migration touching access matching (mitigated by additive steps, parity test, staged switch). Wrong year attribution of old rows (mitigated by report, `source=backfill` badge, NULL-over-guess). Free-text history exposure (section 8). Scale/grade conventions unverified (D-07/D-08). Import volume (chunked, transactional). The first real-data load must wait for the security baseline exit and the 2.4 audit log; historical import with synthetic data only until then.

## 12. Decisions requested
D-22-4 (history matrix, section 8) · D24-1..8 (section 9) · confirm the staged plan 2.2a-1..4 · confirm `Enrollment` as the single link (alternative: year+class columns on each record, rejected: duplication) · who enters `AcademicYear` dates (recommend SchoolAdmin in the admin site).
Gate: ADR-0011 ACCEPTED → explicit approval → implement per step → tests → `/security-review` → report.
