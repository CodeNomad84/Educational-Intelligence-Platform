# CHANGE PROPOSAL — Phase 2.2: Student 360 staff read view (split into 2.2-0 and 2.2)
Supersedes: `0004-phase2-2-student-360-PROPOSAL.md` · Date: 2026-10-18 · Status: **PROPOSED — owner approved the PROPOSAL only (2026-10-18); 2.2-0 and 2.2 are NOT approved for implementation**
Levels: **2.2-0 = L3** (authorization read rule) · **2.2 = L2** (read-only page through the access layer).
Owner decisions applied: D-22-1 (b) extended; D-22-2 Parent staff-only (Parent keeps the existing detail page); D-22-3 SchoolAdmin sees all sections; D-22-4 free text SchoolAdmin only until 2.4; **D-22-5 (2026-10-18) Subject Teacher sees own-subject grades of the CURRENT year only (Option B)**.
Rule that still applies: NO REAL STUDENT DATA until the P3 exit criteria (`SECURITY.md`) are met. Synthetic data only.

## 1. Current state (repository evidence, 2026-10-18)
- CURRENT: no Student 360 view, route or template. `dashboard/urls.py` has `students/<int:pk>/` (`student_detail_view`) only.
- CURRENT: `student_detail_view` (`dashboard/views.py:83-105`) scopes through `visible_students`, `visible_grades`, `visible_attendances` but averages over ALL years (the query has no year). C5a-R1 records that a Subject Teacher sees own-subject grades of all years.
- CURRENT: temporal data exists: `AcademicYear`, `Enrollment`, nullable `Grade.enrollment` / `Attendance.enrollment` (`students/models.py`), 4c enrollment-based access (`students/access.py`, `7e882de`), `rollover_academic_year`.
- CURRENT: the detail page can POST 8 aggregate numbers to FastAPI `/predict/` only with `?predict=true` and only for SchoolAdmin (`dashboard/views.py:141-145`); several inputs are hard-coded placeholders (C5a-R4). RAG chat is disabled for every role (`dashboard/views.py:182`).
- NOT YET IMPLEMENTED: `Recommendation`, behaviour/emotional/counseling data, Counselor role, the 2.4 audit log, any Student 360 UI, `visible_enrollments`.

## 2. Split
| Step | Level | Content |
|---|---|---|
| **2.2-0** | **L3** | `visible_enrollments(user)` in `students/access.py`; Option B in `visible_grades` (Subject Teacher: own subject, current year only); `check_access_switch_ready` additions (§6); negative and mutation tests; `/security-review`; own commit(s). |
| **2.2** | **L2** | The read-only page `GET /students/<id>/360/` (§3), template, tests, docs, Change Report. Starts only after 2.2-0 is accepted. |
| 2.2-L1 (PROPOSED) | L1 | Rollover warning (§7). Not built. |

## 3. Scope of the page (2.2)
**In scope now (staff roles: SchoolAdmin, Grade Lead, Subject Teacher; Parent excluded):**
| Dimension | Content | Role limits |
|---|---|---|
| Identity | name, grade, class, school; other fields by tier | **`national_id` appears only for full-tier rows, only on SYNTHETIC data. No code path may expose it for real data before P3 exit AND the 2.4 audit log.** The 2.2 release gate includes a test that the field is absent for the limited tier and an explicit note in the Change Report. |
| Path | enrollment per year: class, grade-in-year, status, source badge (`backfill` = inferred) | SchoolAdmin and Grade Lead: all years; Subject Teacher: none |
| Academic | grades attributed to a year through `Grade.enrollment`; derived averages/trend labelled "derived, advisory, unvalidated"; "insufficient data" when n < 3 | SchoolAdmin and Grade Lead: all subjects, all years; **Subject Teacher: own subject, current year only** |
| Attendance | per-year counts and rate | SchoolAdmin: all; Grade Lead: per-year aggregates, daily rows for the current year; Subject Teacher: none (unchanged, D7) |

**Explicitly EXCLUDED (not in 2.2-0 nor 2.2):**
- `Attendance.note` (free text; can carry sensitive remarks) — not rendered for any role in the 360 page;
- Recommendations (model not built; free text SchoolAdmin only until 2.4);
- behaviour, emotional, counseling data — no model, no policy, Counselor is never built before the audit log; I cannot show these are safe, so they stay out;
- interventions; risk score; **any `predict` call from the 360 page**;
- Parent access to 360 (D-22-2); exports (CSV/PDF/print API); AI/RAG.
Every block names its source table, row count and latest record date; a section the role may not see is omitted, not blanked.

## 4. Access: no new bypass
- The view starts with `get_object_or_404(visible_students(request.user), pk=pk)`: an unseen student is a 404 (the 4c choke point).
- Grades only from `visible_grades(user)`, attendance only from `visible_attendances(user)`, path only from the new `visible_enrollments(user)`; **no raw `Student/Grade/Attendance/Enrollment.objects` in the view**.
- `visible_enrollments(user)` = `Enrollment.objects.filter(student__in=visible_students(user))`, narrowed per §3: SchoolAdmin all; Grade Lead all years of students in their current grade; Subject Teacher `none()`; Parent `none()`; unknown role `none()`. Same account rule as today (`_may_hold_scoped_grants`: active, non-staff, non-superuser).
- **Option B in `visible_grades`:** for a Subject Teacher assignment the grade row must satisfy: `student` in the current-enrollment set of the assigned class (as today), `subject` equals the assigned subject, **and** `enrollment` is not null, `enrollment.student_id == grade.student_id`, and `enrollment.academic_year.is_current` in the school of the assignment. A grade without an enrollment link is NOT visible to a Subject Teacher (fail closed). Full-tier grants (SchoolAdmin, Grade Lead, Parent) are unchanged by 2.2-0.
- A former Grade Lead/Teacher of a promoted student sees nothing, because visibility follows the CURRENT enrollment.
- The choke-point guard test (`QuerysetChokePointTests`) is extended to cover the new view and `visible_enrollments`.

## 5. Option B (owner decision D-22-5)
Alternatives considered: A (own subject, all years — today's behaviour and the 0003 §8 default; exposes earlier years' scores from other teachers with no audit log); C (current plus previous year). Chosen: **B**, because narrowing after rollout is harder than widening later and the audit log (2.4) does not exist yet. Consequences: a Subject Teacher has no year-over-year view (Grade Lead and SchoolAdmin keep it); unlinked grades are invisible to teachers (availability risk, mitigated by §6). The ROADMAP/SECURITY entry C5a-R1 is updated when 2.2-0 lands.

## 6. `check_access_switch_ready` additions (2.2-0)
The command already treats "a place where staff would see fewer rows than today" as a BLOCKER (`check_access_switch_ready.py` docstring, `BLOCKERS`).
| Check | Count | Classification | Recommendation |
|---|---|---|---|
| Grades with `enrollment` NULL whose student has a current enrollment in a class with an active Subject Teacher assignment | `grades_unlinked_visible_today` | **BLOCKER** | Under Option B these rows disappear for the teacher; by the command's own definition that is a blocker. Fix with `backfill_enrollments` or the import. |
| Grades whose `enrollment.student_id != grade.student_id` (or the enrollment's school differs from the student's) | `grades_enrollment_mismatch` | **BLOCKER** | Hidden under B and an integrity error. |
| Attendance with `enrollment` NULL (students with a current enrollment) | `attendance_unlinked` | **WARNING (informational, does not change the verdict)** | Subject Teachers see no attendance and full-tier attendance visibility is unchanged by 2.2-0; the 360 page would show these rows as "year not attributed". Becomes a blocker only if a later step narrows attendance by year. |
Tests: each check has a positive and a zero case; the verdict stays NOT READY with a blocker present and READY with only warnings; `compare_access_parity` keeps counting students (unchanged).

## 7. PROPOSED L1 item (NOT BUILT): rollover warning
`rollover_academic_year --flip-current` with a target `start_date` in the future prints a warning (never rejects): rollover enrollments carry `started_on=target.start_date` (`rollover_academic_year.py:200-202`) and become CURRENT for access the moment the year is flipped. The access rule is deliberately NOT changed to require `started_on <= today` (D-4-1: "current" is the year flag; a date condition would hide students between flip and start, the 4c-R1 availability failure, and legacy rows have empty `started_on`). Repository evidence: the only writer that can produce a future `started_on` is this command; sync, import and backfill do not, and there is no admin/API/serializer write path for `Enrollment`.

## 8. Impact
- **Data:** no schema change, no migration, read-only.
- **API:** one Django view `GET /students/<id>/360/`; no REST endpoint, no write.
- **Frontend:** one server-rendered Bootstrap 5 RTL template (existing style); provenance badges; empty states say "no data".
- **AI: none.** No AI, FastAPI or LLM call is made and no student data leaves Django in this step; a test asserts `requests` is not called by the 360 view and that the page offers no predict control.
- **Security:** larger read surface for Grade Lead and SchoolAdmin; synthetic data only; `/security-review` before 2.2-0 is accepted and again before 2.2 release.
- **Documentation:** SECURITY (matrix row, C5a-R1 update), CHANGE_GUIDE (bump Verified-at), MODULE_MAP, TRACEABILITY, TESTING, ROADMAP; Change Reports `0008` (2.2-0) and `0009` (2.2). No deferred docs created.

## 9. Testing strategy
**2.2-0 (negative tests first):**
- Subject Teacher: sees own-subject current-year grades of students currently in the assigned class; does NOT see a past-year grade, an unlinked grade (enrollment NULL), a grade whose enrollment belongs to another student, another subject, another class, another school, a grade after the class assignment is deactivated, or any `visible_enrollments` row.
- Grade Lead and SchoolAdmin: `visible_grades` unchanged (regression); `visible_enrollments` per §4; former Grade Lead of a promoted student gets nothing; inactive/staff/superuser accounts grant nothing; Parent and unknown role get `none()`.
- Fail-closed cases: school without a current year, unresolved assignment year, student without a current enrollment.
- **Mutation checks (each must make at least one named test fail; results reported with test names):**
  1. the year normalisation in `_grade_lead_q` (`normalize_academic_year` / `status != RESOLVED` skip: remove the skip and use the raw text);
  2. the class-active check in `_grade_lead_q` (`Q(school_class__isnull=True) | Q(school_class__is_active=True)`: drop it);
  3. the new year/enrollment condition in `visible_grades` (drop `enrollment__isnull`, the `enrollment.student_id` match, and `academic_year.is_current` separately);
  4. the existing enrollment conditions again as regression (`ended_on`, `status`, `is_current`, school).
  Mutations are made on a local edit restored from a scratchpad copy; the working tree must be reported clean afterwards.
- Suites: SQLite and PostgreSQL 16; FastAPI untouched.
**2.2:** per-role scope and tier; 404 for unseen students; section omission per role; `national_id` absent for the limited tier; `Attendance.note` and `parent_user` absent from HTML; no `predict`/AI call; provenance badges and empty states; choke-point guard covers the view; mutation check on the view's `get_object_or_404(visible_students(...))`.

## 10. Risks
- R1 Option B hides unlinked grades from teachers → §6 blocker; run the check on the data before 2.2-0 goes live.
- R2 `national_id` exposure to Grade Lead on a richer page → synthetic data only; no real data before P3 exit and 2.4; test for the limited tier.
- R3 Misreading derived averages → labels, minimum n, no causal claims.
- R4 Grade scale not verified (D-07/D-08).
- R5 Free-text leakage → `Attendance.note` and recommendations excluded.
- R6 Past-year exposure for Grade Lead (all years) is a policy not yet backed by the audit log → synthetic only until 2.4.
- R7 Rollover flip with a future start date (§7, PROPOSED).
- R8 Gate proven on synthetic data only (4c-R1): re-run on real data before real use.

## 11. Approval
Owner approved this proposal text on 2026-10-18 (decisions D-22-5 and the 2.2-0 / 2.2 split). **Still required before code:** explicit approval to implement 2.2-0; then, after 2.2-0 is accepted with its `/security-review`, explicit approval for 2.2.
