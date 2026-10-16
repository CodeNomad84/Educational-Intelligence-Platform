# CHANGE PROPOSAL — Phase 2.2a-4: access switch to current-enrollment matching
Level: **L3** (authorization matching for Grade Lead and Subject Teacher) · Status: **PROPOSED, not implemented** (2026-10-16) · Own commits, parity-gated (owner, ADR-0011).
Depends on: 2.2a-1..3 (schema, reports, backfill, historical import: CURRENT). Related: ADR-0003/0005/0011, `0003` §6, `TEACHER_ACCESS_REVIEW.md` R2/R3.

## 1. Why
Today "who is in my grade / my class" is decided by mirror fields: Grade Lead = `Student.school_id/grade` + linked class that is active with `academic_year` equal to the assignment's FREE-TEXT year (`students/access.py` `_grade_lead_q`); Subject Teacher = `Student.school_class_id` (`_teacher_assignments`). That breaks on promotion (the mirror is edited by hand), on year spelling variants (string equality: `1404` ≠ `۱۴۰۴-۱۴۰۵`) and cannot express "enrolled this year". With enrollments, "current" becomes data: an open enrollment in the school's current academic year.

## 2. Proposed rule (matching only; field policy, tiers and history rules are unchanged)
Definition **current enrollment** of a student: an `Enrollment` with `ended_on IS NULL`, `status IN (active, transferred_in)`, in the `AcademicYear` with `is_current=True`, whose `academic_year.school_id == student.school_id` (and the class, when present, is active). The unique constraint guarantees at most one per (student, year), and one current year per school gives at most one row.
- **Grade Lead** (active assignment, user active and not staff, group re-checked, as today): students with a current enrollment where `enrollment.grade == assignment.grade`, `academic_year.school_id == assignment.school_id` and `normalize(assignment.academic_year) == academic_year.code`. An unresolved/blank assignment year grants nothing (fail closed).
- **Subject Teacher**: students with a current enrollment whose `school_class` is a class with an active assignment (valid subject) of the user.
- SchoolAdmin and Parent are unchanged. `Student.grade/school_class/class_name` remain mirrors for forms, display and import; they no longer decide Grade Lead / Teacher access.
- Implemented with `Exists(Enrollment…, OuterRef('pk'))` subqueries (no join duplicates), also for the `full_tier` annotation. Indexes already exist (`enr_year_grade_status_idx`, `enr_year_class_idx`, `enr_student_year_idx`).
- `visible_grades` / `visible_attendances` keep their current semantics (a Subject Teacher: own subject; Grade Lead: all subjects and attendance of own-grade students); only the student predicate changes. Past-year visibility is the matrix of `0003` §8 and belongs to the 360 page (2.2), not to this switch.

## 3. Sub-stages (each its own commit; stop between them)
- **4a Keep enrollments current (dual-write), no access change.** Today nothing creates the current enrollment for a student created or moved after the backfill. Add one service function `ensure_current_enrollment(student)` called from `Student.save()`-adjacent paths (admin, form, API, import): creates or updates the open enrollment of the current year from `school_class`/`grade` (`source='manual'` or `'import'`), and does nothing when the school has no current year or the class year does not match it (reported, not guessed). Plus the read-only **pre-flight** `check_access_switch_ready` (counts only): schools without a current year; active students with a current-year class but no current enrollment; enrollment/mirror disagreements (grade or class); Grade Lead assignments whose year does not normalise or matches no academic year; teacher assignments whose class has no current enrollments. Zero unexplained rows is the gate.
- **4b Parity tooling, no access change.** `students/access_legacy.py` keeps the CURRENT matching functions verbatim (used only by tests and the command) and the read-only `compare_access_parity` command: for every user holding GradeLead/Teacher it computes the visible student id sets with the legacy and the new rule and prints counts only (both, only-legacy, only-new) per user and total; exit code 1 on any difference that is not in the documented list. No new rule is active yet.
- **4c The switch (own commit, single code path).** `visible_students` uses the enrollment rule. Merged only after `check_access_switch_ready` and `compare_access_parity` show zero unexplained differences on the target database (after backfill apply and admin review).
- **4d Year rollover (admin command, dry-run default).** `rollover_academic_year --to 1405-1406`: closes the open enrollments of the old year with a status chosen per row from the file or default only where evidenced, opens the next year's from a promotion map (grade + 1, class from an explicit mapping file), flips `is_current` after confirmation, deactivates Grade Lead assignments of the old year. Needed before the next school year starts, because after 4c a missing current-year enrollment makes the student invisible to leads/teachers (fail closed). Can ship after 4c but before the year changes; recorded as a deadline.

## 4. Parity test design
1. **Equivalent-data fixtures** (the multi-year synthetic seed after `backfill_enrollments --apply`, plus focused fixtures): for every seeded Grade Lead, Teacher, Parent and SchoolAdmin the two rules must return identical id sets and identical `full_tier`.
2. **Expected differences are enumerated and asserted one by one** (each is a bug fix, not a regression): (a) a promoted student with a stale class mirror: legacy shows the old lead, new shows the new one; (b) year spelling variants (`1404` vs `۱۴۰۴-۱۴۰۵`): legacy misses, new matches; (c) a student with a current enrollment but no class mirror: legacy invisible to a Grade Lead, new visible (grade from the enrollment); (d) a student whose mirror grade differs from the enrollment grade: the enrollment wins; (e) a school without a current year: new rule grants nothing (documented failure mode).
3. **Property checks** on both rules: no cross-school visibility; inactive class, inactive/staff user, left-the-group, inactive assignment, blank subject all grant nothing; union and non-widening unchanged; the existing 32 + 4 C5a tests pass unchanged except their fixtures gain enrollments through a helper; the choke-point guard test still passes.
4. **Command test**: `compare_access_parity` counts match a hand-built fixture and exit code reflects differences; writes nothing.
5. Both SQLite and PostgreSQL, one step at a time; `/security-review` on 4c.

## 5. Risks and failure modes
- **Fail-closed outages:** no current year, a missing current enrollment (new student, forgotten rollover) or an unresolved assignment year makes non-admin staff see fewer students. Mitigations: 4a keeps enrollments current, the pre-flight gate, a SchoolAdmin banner/report listing students without a current enrollment, rollover tooling (4d).
- **Two truths during transition** (mirror vs enrollment): 4a reports disagreements; after 4c the enrollment wins and the mirror is display-only.
- **Year definition:** one `is_current` year per school (constraint). A school running two parallel calendars is out of scope.
- **Data volume/performance:** `Exists` subqueries are index-backed; measure on the synthetic seed scaled up (e.g. 5k students) before 4c.
- **Security:** the rule must still re-check account state at query time (active, not staff) and the group; `full_tier` annotation uses the same predicate; the history/past-year rules are not widened by this change.

## 6. Rollback
4a/4b add code and tools only (revert the commits). 4c is a pure code change with no schema change: revert the commit and the legacy rule (kept verbatim in `access_legacy.py` until 4c is accepted in production) is active again; enrollments stay. 4d is an explicit admin command; its dry-run is the default and every enrollment it writes carries `source='rollover'`... (new source value; choice-only migration) so it can be reverted by source/batch.

## 7. Decisions requested
- **D-4-1** Which statuses count as current: recommend `active`, `transferred_in` only.
- **D-4-2** Grade Lead assignment year: match by the normalised free-text code now (recommended), convert `GradeLeadAssignment.academic_year` to an FK later.
- **D-4-3** Dual-write: a service called from the write paths (recommended, explicit) vs a `post_save` signal.
- **D-4-4** Subject Teacher scope uses the enrollment's class (recommended) rather than the mirror class link.
- **D-4-5** Rollover (4d) before or right after 4c; recommended: designed with 4a, shipped before the school year changes.
- **D-4-6** `compare_access_parity` exit-code policy: nonzero on any unexplained difference (recommended).
Gate: owner approval → 4a → 4b → pre-flight/parity on the target database → 4c → `/security-review` → report.
