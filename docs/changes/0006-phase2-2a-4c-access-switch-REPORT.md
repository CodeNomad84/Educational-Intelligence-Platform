# CHANGE REPORT — Stage 2.2a-4c: access switch to current enrollment
Proposal: `0005-phase2-2a-4-access-switch-PROPOSAL.md` · Date: 2026-10-16 · Commit(s): `7e882de` (code + SECURITY/CHANGE_GUIDE/TRACEABILITY), docs sync commit follows (MODULE_MAP, ROADMAP, this report). Local only, not pushed.

## WHY
Grade Lead and Subject Teacher scope was decided by mirror fields on `Student` (`school_class`, `grade`, class year), which cannot represent history and drift from the temporal model (ADR-0011). Owner decisions D-4-1..6 (2026-10-16) move the decision to the student's CURRENT ENROLLMENT.

## WHAT
- Grade Lead: student of the assigned school whose open current enrollment (status `active`/`transferred_in`) is in the school's current year, has the assigned grade, and whose year code equals the assignment's NORMALISED year. An enrollment class, if present, must be active.
- Subject Teacher: student whose current enrollment is in a class with an active assignment (grades additionally filtered by own subject).
- Fail closed: unresolved/blank assignment year, no current enrollment, or school without a current year grants nothing.
- SchoolAdmin and Parent scopes unchanged. `access_enrollment.py` folded into `access.py`; `access_legacy.py` kept verbatim for `compare_access_parity` and revert.

## WHERE
`django_core/students/access.py` (`_current_enrollment`, `_grade_lead_q`, `visible_students`, `visible_grades`; `visible_attendances` follows via `_full_tier_q`); `management/commands/compare_access_parity.py`; tests `test_access_switch.py` (new negative tests), `test_access_parity.py` (the two 4b guard tests inverted into `SwitchGuardTests`), `test_access_c5a.py` (fixtures only: academic year + `ensure_current_enrollment`; no assert line changed). Docs: SECURITY (4c-R1), CHANGE_GUIDE, TRACEABILITY, MODULE_MAP, ROADMAP.

## HOW
One `Exists` subquery on `Enrollment` per assignment (no join duplicates), combined with the student's own `school_id`. No schema change, no migration. Rollback = revert the commit; enrollments stay and the legacy rule is active again.

## RISKS
- **4c-R1 (MEDIUM, availability not disclosure):** a student without a current enrollment, a school without a current academic year, or an unresolved assignment year is invisible to non-admin staff. A forgotten year rollover hides students until an admin acts. See SECURITY.md 4c-R1.
- **`--carry-assignments` is needed after a rollover:** `rollover_academic_year` deliberately does not carry Grade Lead / Subject Teacher assignments, so until an admin creates them for the new year and classes, non-admin staff see none of the new year's students. The command is designed (`0005` §6a), NOT BUILT; today it is a manual admin step (runbook step 7).
- **Gate proven on SYNTHETIC data only** (234 and 4,938 students). `check_access_switch_ready` and `compare_access_parity` MUST be re-run on the real data before any real student data is loaded (P3 exit rule unchanged).
- Detection gap: no automatic warning for "current year not rolled over" / "students without current enrollment" (ROADMAP item added, not built).
- Noted, not fixed (out of scope): CHANGE_GUIDE academic-years row still says "access switch 4c NOT YET IMPLEMENTED".

## Tests executed + results
See the 4c report given in chat for the SQLite/PostgreSQL runs of this stage; **NOT RE-RUN for this docs-only commit.** NOT VERIFIED here: no test output is pasted in this file.

## Security & permissions review
`/security-review` run on 4c; no finding at or above the 8/10 threshold (as reported in chat). Sub-threshold observations are listed in the chat reply, not in this file.

## Owner acceptance
4c report accepted by the owner; push pending separate approval.
