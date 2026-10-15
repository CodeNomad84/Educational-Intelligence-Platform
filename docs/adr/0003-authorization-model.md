# ADR-0003: Authorization model
- Status: ACCEPTED (owner decisions of 2026-10-13, Phase 2.1.0 design review; effective for Phase 2). **AMENDED in part by ADR-0005 (decisions 1–9 ACCEPTED 2026-10-16): see Amendments at the end; the original text below is kept unchanged.**
- Date: 2026-10-03 (drafted 2026-10-13, accepted 2026-10-13)
- Decider: owner

## Context
Only `@login_required` and a few DRF permissions existed; teachers and parents saw all students (S-01, S-04). Phase 1 contained this with an interim policy (`students/access.py`): Admin all, Parent own children, Teacher none. The target roles are Admin, Manager, Teacher, Mentor, Counselor, Parent, Student. Phase 2 needs teachers to see their own classes (P2-REQ-02) without weakening any existing control.

## Decision
1. **Relationship-based access (option c)** evaluated in one central policy module, `students/access.py` (extended, not replaced). Relationships: teacher ↔ class ↔ student and parent ↔ child.
2. **Roles stay Django groups** in Phase 2 (`Admin`, `Teacher`, `Parent`). No custom user model, no `accounts.User` swap, no new dependency. A superuser is Admin.
3. **Deny by default.** No recognised role, or a role without a relationship, yields an empty queryset. Objects outside scope return 404.
4. **School/class scope** per ADR-0004: a teacher sees a student only through an assignment to the student's **active** class in the same school.
5. **Field minimization.** A teacher does not receive `national_id`, `phone_number`, `father_job`, `mother_job` or `parent_user`, in HTML or API output, and cannot search or filter by them.
6. **Admin-site management.** Assignments are managed by admin staff (group `Admin` + `is_staff`) holding explicit model permissions, granted by an explicit command run by a superuser. `auth.*` permissions (users, groups, permissions) remain **superuser-only**. Teachers are never staff and the Teacher group holds no model permissions.
7. The matrix in `SECURITY.md` remains normative and is updated when the behavior ships (commit C6).

### Phase 2 matrix (Admin / Teacher / Parent; other roles unchanged and not coded)
| Capability | Admin | Teacher | Parent |
|---|---|---|---|
| Student list, detail, API read | all | students of own **active** assigned classes | own children |
| Visible fields | all | name, grade, class, grades, attendance (no `national_id`, phone, parents' jobs) | all fields of own child (unchanged) |
| Create/edit/delete student, import, upload | allow | deny | deny |
| Manage School / SchoolClass / TeacherAssignment | admin site with explicit permissions | deny | deny |
| Risk indicators view (Phase 2.3) | all | assigned students | none |
| Alert acknowledge + add note (Phase 2.4) | allow | assigned students | none |
| Intervention ownership | **future**: Counselor owns (role does not exist yet; no code in Phase 2) | may *flag/propose* only — details DECISION REQUIRED when interventions are built | none |
| Dashboard aggregates, library, chat, AI prediction, `features` | unchanged | deny | unchanged |
| Post-login landing | dashboard | student list | student list |

Manager, Mentor, Counselor, Student cells stay `DECISION REQUIRED`; no code for them in Phase 2.

## Alternatives considered
(a) Groups plus ad-hoc checks in each view: rejected, because it is what produced S-01. (b) django-guardian per-object permissions: rejected for now (new dependency, a row per object). (d) Swap to scaffold `accounts.User` with a `role` field: rejected, because changing `AUTH_USER_MODEL` on an existing database is destructive and unnecessary for this slice.

## Consequences (security, data, testing, customization)
- Data: class and assignment relations (ADR-0004, proposal 0002).
- Security: every student-data query path goes through `visible_students()`; filters, search and ordering must not widen it. A `TEACHER_ACCESS_REVIEW.md` is written and reviewed **before** the access change ships (before C5).
- Future: RAG ACL (ADR-0007), the audit log (S-05) and alert review reuse the same relationships, which is why this precedes any RAG work.
- Customization: role names stay in `access.py` constants; adding Counselor later is a new role plus a new relationship, not a rewrite.

## Evidence (Stage 0 IDs, files)
S-01, S-04, `SECURITY.md` matrix and interim policy, `django_core/students/access.py`, `students/views.py` (API uses `visible_students`), `students/serializers.py` (`fields='__all__'`, to be replaced), `dashboard/templates/dashboard/base.html` (role check on first group).

## Amendments (2026-10-16, through ADR-0005 decisions 1–9, ACCEPTED; effective as C4–C5a ship)
The three-role product decision of 2026-10-15 replaces the single "Teacher" model. The text above is not edited; this table says what still stands.

| Item | Status | Change |
|---|---|---|
| Decision 1 (relationship-based, central `access.py`) | UNCHANGED | relationships now: grade-lead ↔ grade ↔ student, teacher ↔ class+subject ↔ student, counselor ↔ active referral ↔ student, parent ↔ child |
| Decision 2 (roles are groups `Admin`, `Teacher`, `Parent`) | **AMENDED** | groups `GradeLead` and `Counselor` added; `Teacher` means Subject Teacher |
| Decision 3 (deny by default, 404 outside scope) | UNCHANGED | |
| Decision 4 (teacher sees a student through an assignment to an active class) | **SUPERSEDED IN PART** | Subject Teacher: active class **and own subject only**; Grade Lead: by grade; Counselor: active referral; union without widening |
| Decision 5 (teacher never receives `national_id`, phone, parents' jobs, `parent_user`) | **AMENDED** | holds for Subject Teacher and Counselor; **Grade Lead (own grades) and Admin see them**, with the conditions of ADR-0005 §6 |
| Decision 6 (admin-site management; Teacher group has no model permissions) | UNCHANGED, extended | applies equally to `GradeLead` and `Counselor` groups |
| Decision 7 (matrix in `SECURITY.md` updated when behavior ships) | UNCHANGED | C6/C5a docs |
| Phase 2 matrix: "Visible fields" for Teacher (incl. attendance) | **SUPERSEDED IN PART** | Subject Teacher sees own-subject grades and no attendance in C5a |
| Phase 2 matrix: "Intervention ownership: Counselor future" | **REALISED LATER** | Counselor via referral in 2.6 (needs 2.4 audit); not before |
| Phase 2 matrix: Post-login landing (Teacher → list) | UNCHANGED | Grade Lead the same; Counselor lands on the referral inbox (2.6) |
| Consequences: `TEACHER_ACCESS_REVIEW.md` before C5 | SATISFIED | v3 written; committed `bd03b07` |

## Supersedes / superseded by
Amended in part by ADR-0005 (decisions 1–9 ACCEPTED 2026-10-16).
