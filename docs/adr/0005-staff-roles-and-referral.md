# ADR-0005: Staff roles, scoping and counseling referral
- Status: **ACCEPTED for decisions 1–9** (owner, 2026-10-16: they govern C4–C5a, Phase 2.1). Decisions 10–12 are **direction only** (PROPOSED) for Phases 2.6/2.7 and need a detailed design after policy/legal review (owner D24).
- Date: 2026-10-16
- Decider: owner
- Level: L3 (authorization model, sensitive data, state machine). Source: `docs/TEACHER_ACCESS_REVIEW.md` v3 and the owner's decisions of 2026-10-15/16.

**Scope:** this ADR covers roles 2–4 of the platform's role list (Grade Lead, Subject Teacher, Counselor) only. The full eight-role map (School Principal, Platform Admin, Student, Administrative staff, Parent and the naming of today's overloaded `Admin` group) is a separate ADR (ADR-0010, DRAFT).

## Context
ADR-0003 modelled one "Teacher" role that sees students of assigned classes. The owner's product decision (2026-10-15) replaces it with three staff roles: **Grade Lead** (مربی پایه), **Subject Teacher** (معلم درس) and **Counselor** (مشاور). Inspection (`TEACHER_ACCESS_REVIEW.md` §1) found: `Student.grade` is the only grade key (integer 7–12); `SchoolClass` has no grade; `TeacherAssignment.subject` is free text while `Grade.subject` has 15 fixed choices; there is no audit log (S-05), referral, recommendation or counseling-record model. CCOS §19 (see `docs/CCOS_REFERENCE.md`) requires strict access, auditability, retention, consent and controlled AI exposure for counseling data.

## Decision
**Roles and scope (Phase 2.1, C4–C5a)**
1. **Three staff roles as Django groups** (consistent with ADR-0003 §2): `Teacher` (= Subject Teacher, existing name kept), `GradeLead`, `Counselor`. Names are constants in `students/access.py`. No custom user model.
2. **Grade Lead scope = grade.** Assigned by an Admin in the admin site through `GradeLeadAssignment(user, school, grade, academic_year, is_active, created_by)`; no self-service. Several Grade Leads per grade are allowed; a grade without a lead grants nothing. Assignments are yearly; year rollover deactivates them. Visibility: students of the assignment's school and grade.
3. **Subject Teacher scope = active class + own subject.** Uses `TeacherAssignment`; `subject` becomes **access-relevant** and is constrained to the same fixed vocabulary as `Grade.subject`. Grade rows of other subjects are never returned. In C5a a Subject Teacher sees no attendance.
4. **Counselor scope = active referral** only (decisions 10–11); never from class or grade; **not built before the audit log (2.4)**.
5. **Union without widening.** A user may hold several roles; visibility is the union of the grants, but the field/subject policy belongs to the grant through which a row is visible. A Grade Lead who is also a Subject Teacher sees `national_id` and full detail only inside own grades; elsewhere only own subject/own classes with the Subject Teacher field policy.
6. **Field policy by role** (explicit serializer lists chosen server-side): Admin and Grade Lead (own grades) see `national_id`, contact and parents' fields; Subject Teacher and Counselor never see `national_id`, phone, parents' jobs or `parent_user`. `national_id`/phone are searchable only by Admin and Grade Lead inside their own scope. Never in exports, AI/RAG or logs. Grade Lead `national_id` is enabled **only with synthetic data until the 2.4 audit log exists**; identity-field reads are audited from 2.4 on (owner D1, D17).
7. **Deny by default; 404 outside scope** (unchanged from ADR-0003 §3). One choke point: `visible_students()` and a new `visible_grades()` in `students/access.py`; filters, search and ordering cannot widen it.
8. **Writes.** Student create/update/delete/import stay Admin only. Grade Lead may later create referrals and recommendations; Subject Teacher may later enter grades for own class and subject only. Each write re-checks the same relationship server-side.
9. **Privileges.** The three groups hold **zero** model permissions and are never staff. The grant command (C4) creates the groups and grants assignment-model permissions to Admin staff only; `auth.*` stays superuser-only (ADR-0003 §6).

**Referral and feedback (Phases 2.6/2.7, direction only)**
10. **Referral workflow with Admin-visible stuck points:** states `submitted`, `counselor_declined`, `awaiting_parent_consent`, `parent_declined`, `active`, `closed` (+ optional `withdrawn`); per-transition timestamp and actor; Admin sees state, days in state and the waiting party but never notes. Consent is recorded (method, by whom, when; a parent may record it through the Parent account). **A referral never becomes `active` without parental consent; no exception path** (owner D5/D16). Every transition and every counselor read is audit-logged. Closing removes counselor access immediately.
11. **Counseling safety (CCOS §19):** four record classes are kept apart (educational guidance, counseling support/referral metadata, sensitive counseling records, crisis/escalation); sensitive records live in separate tables, owner-of-record access only, no Admin read, no break-glass in Phase 2, retention period set before real use, excluded from AI/RAG/exports and not importable by the AI layer. The crisis/escalation path is **not designed here**; it needs a separate policy document first (owner D18).
12. **Satisfaction feedback:** after `closed`, family and counselor each record a structured rating (plus optional free text) in a separate model; participation is voluntary with no effect on services; Admin sees ratings and aggregates only (minimum cell size 5, configurable), never free text or note content; individual-level views only by explicit later decision.

## Alternatives considered
(a) Keep one Teacher role and bolt grade-lead rules on in views: rejected (ad-hoc checks produced S-01). (b) A `role` field/custom user model (ADR-0003 alternative d): still rejected, `AUTH_USER_MODEL` swap on a live database. (c) Per-object permission library (django-guardian): rejected, new dependency, row per object. (d) Scope the Grade Lead through `SchoolClass.grade` only: rejected as the sole key, because the field does not exist yet and legacy students may have no class; `Student.grade` is the key, `SchoolClass.grade` (nullable) is added for class-based views. (e) Counselor visible by assignment to students (no referral): rejected by owner; access must be time-bounded and consented. (f) A consent bypass for emergencies: rejected for now (owner D5); a future bypass needs a legal opinion and a new ADR. (g) Ship the Counselor before the audit log: rejected (CCOS §19 auditability).

## Consequences (security, data, testing, customization)
- Data (C4b/C5a): new `GradeLeadAssignment`; `TeacherAssignment.subject` constrained plus a data check of existing rows; nullable `SchoolClass.grade`. Later: referral, consent, recommendation, counseling-record and feedback models (2.6/2.7). All migrations reversible and reviewed on both backends.
- Security: broader PII exposure to Grade Lead (whole grade, including `national_id`): mitigated by grade-only scope, no export/AI path, synthetic-data-only until audit, identity-read audit from 2.4. Summed grants must be tested for non-widening. `/security-review` before each of C5a, 2.6 and grade entry.
- Testing: backend-neutral permission matrix per role (see `TEACHER_ACCESS_REVIEW.md` §3); regression tests that new roles get 403 on every FastAPI data route.
- Customization: role names, stale-referral threshold and feedback minimum count are configuration/constants; nothing school-specific in code.
- Rollback: C4/C5a are isolated commits; reverting C5a returns the new roles to "no access".
- Subject vocabulary: fixed choices shared with `Grade.subject` (owner D12). Open: D6, D8–D11, D20–D23 of `TEACHER_ACCESS_REVIEW.md` §10, and the policy/legal review (D24) before 2.6/2.7.

## Evidence (Stage 0 IDs, files)
S-01, S-04, S-05, D-06; `django_core/students/access.py`, `students/models.py` (`Student.grade`, `Grade.subject`), `schools/models.py` (`SchoolClass`, `TeacherAssignment`), `dashboard/views.py`, `students/views.py`, `students/serializers.py`; `docs/TEACHER_ACCESS_REVIEW.md` v3; `docs/CCOS_REFERENCE.md` §19.

## Supersedes / superseded by
Amends ADR-0003 (decisions 2, 4, 5 and the Phase 2 matrix are superseded in part; see its Amendments section) and ADR-0004 (decisions 1 and 5 extended; see its Amendments section). Does not supersede either ADR as a whole. Numbering note: the earlier reservation of 0005 for "Data layering & provenance" moves to 0009 (`docs/adr/README.md`).
