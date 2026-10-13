# ADR-0003: Authorization model
- Status: DECISION REQUIRED
- Date: 2026-10-03

## Context
Only `@login_required` and a few DRF permissions exist; teachers and parents see all students (S-01, S-04). Roles required: Admin, Manager, Teacher, Mentor, Counselor, Parent, Student.
## Options
(a) Django groups + object-level checks in code; (b) django-guardian style object permissions (new dependency); (c) relationship-based access (teacher↔class↔student, parent↔child) evaluated by a central policy module.
## Recommendation (non-binding)
(c) with a single policy module and the matrix in `SECURITY.md` as normative, no new dependency initially.
## Consequences
Drives schema (class/enrollment/guardian relations), RAG ACL and audit. Owner must fill `DECISION REQUIRED` cells first.
## Evidence
S-01, S-04, matrix in SECURITY.md.
