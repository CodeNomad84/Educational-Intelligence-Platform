# ADR-0003: Authorization model
- Status: PROPOSED (draft 2026-10-13, Phase 2.0; direction approved by owner 2026-10-13, **not ACCEPTED**)
- Date: 2026-10-03 (drafted 2026-10-13)
- Decider: owner

## Context
Only `@login_required` and a few DRF permissions existed; teachers and parents saw all students (S-01, S-04). Phase 1 contained this with an interim policy (`students/access.py`): Admin all, Parent own children, Teacher none. The target roles are Admin, Manager, Teacher, Mentor, Counselor, Parent, Student. Phase 2 needs teachers to see their own classes (P2-REQ-02) without weakening any existing control.

## Decision (proposed)
1. **Relationship-based access (option c)** evaluated in one central policy module, `students/access.py` (already the single place; extended, not replaced). Teacher ↔ class ↔ student and parent ↔ child are the relationships.
2. **Roles stay Django groups** in Phase 2 (`Admin`, `Teacher`, `Parent`). No custom user model, no `accounts.User` swap, no new dependency.
3. **Deny by default.** No recognised role, or a role without a relationship, yields an empty queryset.
4. **Not-visible objects return 404**, consistent with current behavior (no existence leak).
5. The matrix in `SECURITY.md` remains normative. It is edited only when this ADR is ACCEPTED.

### Proposed Phase 2 cells (Teacher / Admin / Parent only)
| Capability | Admin | Teacher | Parent |
|---|---|---|---|
| View student profile / Student 360 | all students | students of own assigned classes | own children (unchanged) |
| Grades and attendance **view** | all | own assigned classes | own children |
| Create/edit student, upload | allow (unchanged) | none (unchanged) | none |
| Risk / alert view | all | own assigned classes — **DECISION REQUIRED** | none |
| Alert review (acknowledge/dismiss) | allow | own assigned classes — **DECISION REQUIRED** | none |
| Manage teacher↔class assignments | allow (admin UI) | none | none |
| Dashboard aggregates, library, AI prediction | unchanged from Phase 1 | deny (unchanged) | unchanged |

Manager, Mentor, Counselor and Student cells stay `DECISION REQUIRED` and **no code is written for them in Phase 2**. Attendance/grade entry, interventions and counseling are outside Phase 2.

## Alternatives considered
(a) Groups plus ad-hoc checks in each view: rejected, because it is what produced S-01. (b) django-guardian per-object permissions: rejected for now, as it adds a dependency and needs a row per object. (d) Swap to the scaffold `accounts.User` with a `role` field: rejected for Phase 2, because changing `AUTH_USER_MODEL` on an existing database is a destructive migration and is not needed for this slice.

## Consequences (security, data, testing, customization)
- Data: needs class and assignment relations (ADR-0004; proposal 0002).
- Security: every student-data query path goes through `visible_students()`; filters, search and ordering must not widen it. Permission tests are mandatory for each path (list, detail, API, mutations).
- Future: RAG ACL (ADR-0007) and the audit log reuse the same relationships; this is why it comes before any RAG work.
- Customization: role names stay in `access.py` constants; adding Counselor later is a new role plus a new relationship, not a rewrite.

## Evidence (Stage 0 IDs, files)
S-01, S-04, `SECURITY.md` matrix and interim policy, `django_core/students/access.py`, `students/views.py:38` (API already uses `visible_students`).

## Supersedes / superseded by
None.
