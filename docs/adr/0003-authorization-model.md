# ADR-0003: Authorization model
- Status: ACCEPTED (owner decisions of 2026-10-13, Phase 2.1.0 design review; effective for Phase 2)
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

## Supersedes / superseded by
None.
