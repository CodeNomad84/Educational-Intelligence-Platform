# ADR-0011: Temporal data model (academic years, enrollments, year-aware records)
- Status: **ACCEPTED for scope 2.2a-1..3** (owner, 2026-10-16: schema, read-only reports, admin-created years and backfill). **Stage 2.2a-4 (access switch) is accepted only behind a parity test and as its own commit.** The `Recommendation` model, real data, retention periods and legal basis remain **DECISION REQUIRED / DEFERRED** (owner decision with legal advice; synthetic data only).
- Date: 2026-10-16
- Decider: owner
- Level: L3 (schema, migration, access matching, retention)
- Detail: `docs/changes/0003-phase2-2a-temporal-data-model-PROPOSAL.md`

## Context
Owner requirement: retain each student's data across all school years (including imported history) to show same-year trends, comparison with past years, earlier recommendations and the whole educational path. CURRENT: `Student.grade` and `school_class` hold only the current state; `SchoolClass.academic_year` and `GradeLeadAssignment.academic_year` are free text matched by string equality; `Grade` and `Attendance` carry only a date; import is keyed by `national_id`, has no year, and overwrites current fields; deleting a student cascades away grades and attendance. Past rows survive but are unattributable to a year, class or grade, and promotion loses the previous grade and class.

## Decision (PROPOSED)
1. `AcademicYear` per school: canonical code (`1404-1405`), start/end dates entered by an admin, one current year per school; free-text years are normalised by one function and unresolved values are reported, never guessed.
2. `Enrollment` (student, year, class, grade-in-year, status, source) is the unit of history; `Student.grade/school_class/class_name` remain a mirror of the current open enrollment until the access switch.
3. `Grade` and `Attendance` link to an enrollment (nullable first, required for new rows); a natural key on `Grade` makes historical import idempotent.
4. `Recommendation` is append-only and never deleted (supersede/retract), carrying year, class, subject and an author snapshot; visibility levels are set by the author.
5. Year-aware historical import with dry-run, batch id and revertible batches; it never overwrites current student fields.
6. Migration in four reversible steps (schema, report, admin-created years + backfill, access switch behind a parity test); no enrollment is created without evidence; NULL over guess.
7. History visibility is opt-in per role (matrix in the proposal); deletion of a student with history is replaced by an explicit anonymisation procedure (retention decisions D24-1..8 open).

## Owner decisions recorded 2026-10-16
1. `Enrollment` is the single link; stages 2.2a-1..4; `AcademicYear` dates are entered by SchoolAdmin in the admin site.
2. **History matrix accepted with one change:** until the 2.4 audit log exists, past-year free-text notes and recommendations are visible to **SchoolAdmin only**. Structured data (grades, averages, attendance aggregates, path) follows the matrix of the proposal §8.
3. Retention (D24-1..8) is recorded as **direction**; the retention period and legal basis are an owner decision with legal advice. No `Recommendation` model and no real data until decided; synthetic data is fine.
4. Implementation starts with 2.2a-1 only: schema (`AcademicYear`, `Enrollment`, `ImportBatch`, nullable `enrollment` FKs on `Grade`/`Attendance`) and two read-only reports; no access change, no backfill apply.

## Alternatives considered
(a) Year and class columns on every `Grade`/`Attendance` row: duplicated, drifts from the roster; rejected. (b) Keep the flat model and derive years from dates: needs a calendar, loses class/grade, breaks on promotion and repeats; rejected. (c) Snapshot the whole student per year: heavy and duplicative; rejected. (d) A Jalali calendar library to compute years: new dependency, not needed because dates are stored; rejected. (e) Event-sourcing/audit-style history: disproportionate for the school scale; rejected.

## Consequences
- **Security:** history access is a separate decision from current scope; past-year free text is the main exposure and is gated by visibility levels, the matrix and (later) the audit log; no AI/RAG use of history without policy.
- **Data:** additive migrations; old columns untouched until the last step; PROTECT on history FKs; anonymisation procedure replaces deletion.
- **Testing:** parity test old vs new access rule, backfill/no-guess tests, migration forward/backward on both backends and on a copy of `data/postgres`.
- **Customization:** year format variants are handled by configuration of the normaliser input, not school-specific code; no hard-coded calendar.
- **Open:** D-22-4 (history matrix), D24-1..8 (retention), who enters year dates.

## Evidence
`students/models.py` (Student, Grade, Attendance), `schools/models.py` (SchoolClass.academic_year, GradeLeadAssignment), `students/access.py:63-66`, `students/views.py:154-170`, `students/class_resolution.py:31-35`, `seed_demo.py:107-110`; `docs/changes/0003-…-PROPOSAL.md` §2.

## Supersedes / superseded by
Extends ADR-0004 (class year becomes an FK) and ADR-0005 (Grade Lead year matching). Supersedes nothing yet.
