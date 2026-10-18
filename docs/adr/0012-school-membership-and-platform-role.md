# ADR-0012: School membership, platform role and per-school student identity
- Status: **ACCEPTED 2026-10-19** (owner; drafted 2026-10-18). Accepting this ADR approves the decisions, **not any implementation stage**: nothing here is implemented, and each stage of `changes/0010` needs its own explicit approval.
- Date: 2026-10-18
- Decider: owner
- Level: L3 (authorization, tenancy, schema, service boundary)
- Detail: `docs/changes/0010-multi-school-hosting-PROPOSAL.md`
- Relation: completes ADR-0010 positions 2–4 (PlatformAdmin, superuser as break-glass, platform role sees no student data); amends ADR-0004 decisions 3 and 8 (applied to ADR-0004 as a dated Amendments section on 2026-10-19; effective as stages S6/S7 ship); keeps ADR-0004 decision 7 (row-level scoping in one database) unchanged.

## Context
CURRENT (audit 2026-10-18): the `SchoolAdmin` group (and any superuser) is global; `visible_students/grades/attendances` return unfiltered querysets for it (`students/access.py:117,138,154`); no model links a user to a school for this role; `Student.national_id` is globally unique and the import upserts by it alone; `Student.school` is nullable; the Django admin is unscoped; the FastAPI service token carries no school and `documents` has no school column. The product must host several schools, each with its own SchoolAdmin(s), plus a platform owner above them. Owner decisions of 2026-10-18: multi-school before Student 360; separate `PlatformAdmin`; Django admin for platform administrators only (after dashboard equivalents exist); two `Student` rows for a person in two schools; shared database with row-level `school_id`.

## Decision (ACCEPTED 2026-10-19)
1. **Tenancy:** one PostgreSQL database, row-level `school_id`, enforced only through `students/access.py` (ADR-0004 decision 7 confirmed). No tenant middleware, schema-per-tenant or database-per-school in the code. **Physical separation per customer is achieved by deploying the same code and image with separate configuration, never by copying code.**
2. **`SchoolMembership(user, school, is_active, created_by, …)`**, unique `(user, school)`, many-to-many through the model. It scopes the `SchoolAdmin` group. Hygiene as `GradeLeadAssignment`: creation checks (active, not superuser, group `SchoolAdmin`) and a **query-time re-check** of account state, group and membership. A superuser cannot be a school member.
3. **Fail closed:** a SchoolAdmin without a valid membership sees nothing; with several memberships the reader sees the union; a write names exactly one target school that must be in the user's memberships; the school is never taken from an uploaded file.
4. **`PlatformAdmin`** is an explicit Django group (role 8 of ADR-0010): manages schools, memberships, accounts and technical configuration; has no student/grade/attendance/enrollment access in the application, including the Django admin (Option A, accepted; Option B "read allowed" contradicts ADR-0010 position 4 and is not adopted by this draft). The **superuser** remains for Django-level administration and recovery; the mapping "superuser ⇒ SchoolAdmin" is removed in its own revertible stage. A superuser's technical ability to read the database is acknowledged and handled organisationally until the 2.4 audit log exists.
5. **A person in two schools is two `Student` rows;** `national_id` is unique per school: `UniqueConstraint(school, national_id)`; `Student.school` becomes required. A transfer splits history across rows; there is no cross-school link or read.
6. **FastAPI/RAG:** the service token carries the `schools` claim; `documents` gets `school_id`; every retrieval, listing and delete filters by it in SQL before ranking; a document without a school is invisible (ACL before retrieval).
7. **Django admin** is restricted to `PlatformAdmin` and superuser only after every SchoolAdmin task of the Django admin has been given a disposition: `page` (a school-scoped dashboard page), `PlatformAdmin duty`, or `operator command` (changes/0010 §7). Grades and attendance are proposed as import-only for now (no manual entry page). Staff and parent accounts are a PlatformAdmin duty for now; **Teacher and Grade Lead assignment pickers cannot be school-scoped until users have a school link**, so those assignments stay a PlatformAdmin duty until then.
8. **Every student-creation path assigns a school explicitly** (the class's school, else an explicit target school validated against the user's memberships, else the write is rejected); there is **no hidden "only School" default**. Stage S2b, then `Student.school` NOT NULL (S6) before the SchoolAdmin read scope is switched on (S3). Order: S1, S2, S2b, S6, S3, S4, S5, S7, S8, S9, S10.
9. **`parent_user` choices** are limited, as a stopgap, to parents already linked to a student of the user's schools; a parent new to a school is linked by the PlatformAdmin until a link flow exists. **School-less documents** are invisible to every school (one-time backfill while exactly one School exists).

## Amendment to ADR-0004 (text as applied on 2026-10-19)
- Decision 3: replace "`Student.school` is added nullable and made required only by a later, separate migration" with "…and is made required by stage S6 of `changes/0010` (after population while exactly one School exists)".
- Decision 8: replace "`Student.national_id` stays globally unique in Phase 2 (DEFERRED: becomes `(school, national_id)` when a second school exists)" with "`Student.national_id` is unique per school: `UniqueConstraint(school, national_id)` (stage S7 of `changes/0010`). The same person in two schools is two rows; no cross-school identity link exists."

## Alternatives considered
- Database-per-school / schema-per-tenant: rejected for the code (ADR-0004); available as a deployment of the same image with separate configuration.
- A `school` FK on the user (single school per SchoolAdmin): rejected by the owner's many-to-many requirement.
- Keeping global `national_id` uniqueness with one shared `Student`: rejected (owner 2026-10-18): it forces cross-school visibility of one record or a person-level ACL that does not exist yet.
- Denormalising `school` onto grades/attendance/enrollments: not now; reach the school through the student (see proposal D-MS-2).
- Interim scoped Django admin for SchoolAdmins: not recommended (proposal D-MS-4).

## Consequences (security, data, testing, customization)
- **Security:** removes the only unscoped data role; adds a cross-school negative test suite and six mutation checks; the platform role has no data path (Option A). Residual: superuser; shared `SERVICE_JWT_SECRET`; no audit log before 2.4.
- **Data:** new table `SchoolMembership`; `Student.school` NOT NULL and the `national_id` constraint change are irreversible-ish and run only after a dry-run report on a copy of synthetic data; `documents.school_id` added.
- **Testing:** two-school fixture everywhere; SQLite and PostgreSQL run separately.
- **Customization:** no school-specific code; separate customers run separate configurations of the same image.
- **Process:** the order of stages is fixed in changes/0010 §9; no real student data until P3 exit and the 2.4 audit log; no second `School` row before stages S1–S9 are accepted.

## Evidence (Stage 0 IDs, files)
S-01, S-04, S-05, D-06; `django_core/students/access.py:20,36,57-65,117,138,154`; `students/models.py:12,34-41,57-66`; `students/views.py:96,162-171,183-212`; `students/permissions.py:15-17`; `dashboard/views.py:59-62`; `schools/admin.py`; `schools/management/commands/setup_staff_roles.py:21-27`; `config/service_auth.py`; `fastapi_core/auth.py`; `fastapi_core/rag_service.py:151-155,245,259`; ADR-0004, ADR-0005, ADR-0010, ADR-0011.

## Supersedes / superseded by
Completes ADR-0010 (positions 2–4); amends ADR-0004 (decisions 3, 8) on acceptance. Supersedes nothing.
