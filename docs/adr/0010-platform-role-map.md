# ADR-0010: Platform role map
- Status: **DRAFT / PROPOSED**; **decision 2 rename `Admin` → `SchoolAdmin` ACCEPTED and IMPLEMENTED 2026-10-16** (`88a60a5` constants, `55babae` rename + `students/0010` + FastAPI; migration not yet applied to `data/postgres`, owner step after backup); the rest stays DRAFT (2026-10-16, revised after owner decisions of the same day; only the owner marks ACCEPTED). Owner positions so far: `PlatformAdmin` accepted in principle; Student role redefined as AI Study Assistant access (not own-record access); Administrative staff direction only.
- Date: 2026-10-16
- Decider: owner
- Level: L3 (authorization model, privileged roles, naming across services)
- Relation: ADR-0005 covers roles 2–4 in detail and stays unchanged. This ADR maps **all eight roles**, fixes the overloaded `Admin` name and defines the privileged technical role. It does not add code.

## Context
Owner role list (2026-10-16): 1 School Principal (مدیر مدرسه), 2 Grade Lead (مربی پایه), 3 Subject Teacher (معلم درس), 4 Counselor (مشاور), 5 Parent, 6 Student, 7 Administrative staff (letters, report cards, office features), 8 Platform Admin (technical: password management, RAG document management; must **not** see school/student data).

`CURRENT` (code, `HEAD` `7baca25`+): three roles exist as Django groups `Admin`, `Teacher`, `Parent` (`students/access.py:10-13`); a superuser is treated as `Admin` (`access.py:21-22`). The single `Admin` role does everything: all students, import, create, RAG documents, prediction, dashboard, and (through `is_superuser`) the Django admin. It therefore conflates the school's head with technical administration, which is the opposite of the owner's requirement for role 8. There is no Student, Administrative-staff or Platform-Admin role. `accounts/`, `governance/` (AuditLog, Consent) and `behavior/` exist only in the archived scaffold, not in tracked code.

## Decision (proposed)
1. **Eight roles, eight identities.** Each role is a Django group (consistent with ADR-0003 §2); a user may hold several; visibility is the union without widening (ADR-0005 §5). Role names are constants in `students/access.py` and `fastapi_core/auth.py`, mirrored by the service token's `roles` claim.
2. **Split and rename the overloaded `Admin`** (owner: `PlatformAdmin` accepted in principle; fallback `TechAdmin` = metadata read-only technical role if the split proves problematic). Today's `Admin` group becomes **`SchoolAdmin`** (role 1, School Principal and delegated school managers). A new **`PlatformAdmin`** group is role 8. The rename is its own L3 commit (D-R1) with a reversible data migration, executed **after C4 and before C5a** so that C5a is written against the final names. It is **not** part of C4.
3. **Superuser is break-glass, not a daily role.** One owner-held superuser exists for installation and recovery. Until `PlatformAdmin` exists the current mapping (superuser ⇒ school admin) stays; when `PlatformAdmin` ships, the mapping is removed so that a superuser is *not* automatically a school-data reader in the application (D-R2).
4. **Platform Admin sees no school or student data in the application.** It has no access path to `Student`, `Grade`, `Attendance`, assignments, referrals, counseling or feedback, in HTML, API, search or Django admin. It manages accounts and technical configuration only (section "Platform Admin").
5. **Student, Administrative staff and Platform Admin are direction only.** They are built after the 2.4 audit log and the Phase 3 security baseline exit (section "Build order").
6. **Deny by default, 404 outside scope, one choke point** (ADR-0003 §3, ADR-0005 §7) apply to every role.

## Role map

| # | Role | Group (proposed) | Exists today? | Built when |
|---|---|---|---|---|
| 1 | School Principal | `SchoolAdmin` (renamed from `Admin`) | yes, as `Admin` | rename before C5a |
| 2 | Grade Lead | `GradeLead` | no | C4 (group), C5a (access) |
| 3 | Subject Teacher | `Teacher` (name kept) | group only; scope none today | C4/C5a |
| 4 | Counselor | `Counselor` | no | group at C4; access in 2.6 after 2.4 audit |
| 5 | Parent | `Parent` | yes (`parent_user`) | unchanged |
| 6 | Student | `Student` | no | direction only; **P7** (RAG + AI assistants), after 2.4 audit and P3 exit |
| 7 | Administrative staff | `AdminStaff` (name: D-R7) | no | direction only; minimal office set (report cards, letters, attendance), after 2.4 and P3 |
| 8 | Platform Admin | `PlatformAdmin` | no (superuser today) | direction only; earliest with the production profile (`DEPLOYMENT.md`) |

### Rename impact (`Admin` → `SchoolAdmin`), citations at `HEAD`

| Location | Use |
|---|---|
| `django_core/students/access.py:10,13,22,39` | `ADMIN = 'Admin'`, `ALL_ROLES`, superuser mapping, `visible_students` |
| `django_core/students/permissions.py:14,37` | literal `'Admin'` group name in `IsAdminUser` and `IsAdminOrReadOnly` |
| `django_core/dashboard/views.py:43,69,84,91,142,171,213,234,284,316` | `ADMIN in roles`, `role_required(ADMIN…)` |
| `django_core/demo_intel/views.py:30,46,86` | `role_required(ADMIN)` |
| `django_core/dashboard/templates/dashboard/base.html:33` | literal `'Admin'` and `groups.all.0.name` (**checks only the first group**, a defect noted in ADR-0003 evidence) |
| `django_core/students/management/commands/seed_demo.py:244` | `Group.objects.get_or_create(name="Admin")` |
| `fastapi_core/auth.py:20`, `fastapi_core/main.py:113,160,261,275` | `ADMIN = "Admin"` and `require_roles(ADMIN)` |
| tests | many `ADMIN` constants and group names in `students`, `dashboard`, `demo_intel` tests |
| `docs/` | SECURITY.md matrix, ADR-0003, TRACEABILITY, MODULE_MAP |

**Migration approach (proposal):** (a) constants first: replace literals by the constants (no behaviour change); (b) one data migration renaming `Group(name='Admin')` to `SchoolAdmin`, reversible, in `students`; (c) FastAPI `auth.py` accepts the new name in the same commit (same repo, same compose, tokens live 60 s, so no compatibility window is needed); (d) tests and docs updated; (e) a regression test that no `'Admin'` literal remains outside the migration. Rollback: revert the commit and run the reverse migration.

## Matrix (per role; PROPOSED beyond ADR-0005)

Legend: scope = who/what rows; "own" = own record. `—` = denied.

| Capability | Channel | 1 Principal | 2 Grade Lead | 3 Subject Teacher | 4 Counselor | 5 Parent | 6 Student | 7 Admin staff | 8 Platform Admin |
|---|---|---|---|---|---|---|---|---|---|
| Student list/detail | web UI, API | school | own grades | assigned classes | active referral | own children | — (no self-view; later decision D-R5) | school, minimal fields (report cards, letters) | — |
| `national_id` | web UI, API | yes | yes (own grades) | — | — | own child | — | printed documents only (D-R8) | — |
| Phone, parents' jobs, `parent_user` | web UI, API | yes | yes | — | — | own child | — | contact for letters | — |
| Grades (scores) | web UI, API | all | all subjects, own grades | own subject | per referral (D6) | own children | — (self-view later) | summary for report cards, read-only | — |
| Attendance | web UI, API | yes | yes | — (C5a) | per referral (D6) | own children | — (self-view later) | summary for report cards | — |
| Grade entry | web UI, API | yes (correction) | — | own class+subject (later) | — | — | — | — | — |
| Recommendations | web UI, API | read all | write/read | write/read own subject | read per referral | read (shared ones, D-R6) | — | — | — |
| Referral | web UI, API | workflow status | create | — | handle | consent | — | — | — |
| Counseling notes/feedback text | web UI (counselor view only); never API list, never AI chat | — | — | — | owner of record | — | — | — | — |
| Risk scores / alerts (advisory) | web UI, API | yes | own grades (2.3/2.4) | assigned (2.3/2.4) | per referral | — | — | — | — |
| Create/edit/import students | web UI, API (Admin only) | yes | — | — | — | — | — | limited (D-R8) | — |
| Letters / report cards | web UI (generated documents) | approve | — | — | — | own child's | — | produce | — |
| Users, passwords, group membership | Django admin / web UI | role assignment (D-R3) | — | — | — | — | — | — | accounts and passwords |
| RAG documents | web UI, API (FastAPI) | manage (D-R4) | — | — | — | — | — | — | upload/delete, metadata only |
| Audit log | web UI | read school-level | — | — | — | — | — | — | technical logs only |
| Staff AI assistant | AI chat (staff) | per ADR-0007 | per ADR-0007 | per ADR-0007 | **never counseling data** | — | **Study Assistant only (AI chat, restricted)** | — | — |
| Django admin site | Django admin | assignments via explicit perms (ADR-0003 §6) | — | — | — | — | — | — | users/groups only |

Explicitly denied for every non-listed cell, and in all cases: counseling notes to anyone but the counselor of record; counseling/feedback content to AI, RAG or exports; `national_id` to Subject Teacher, Counselor and Platform Admin.

## Platform Admin (role 8)

**Purpose:** keep the platform running without being able to read school data.

**May do:** create/disable accounts, reset passwords, manage non-privileged group membership if D-R3 allows, upload/delete RAG documents, view technical health. **May see:** user account fields (username, name, active flag, groups), document **metadata** only (id, title, parent/group id, created time, size/status), not document content; technical logs without student values.

**Denied in the application:** any `Student`, `Grade`, `Attendance`, school, class, assignment, referral, counseling or feedback record, in HTML, API, search, ordering and Django admin; the staff AI assistant; exports; assigning themselves `SchoolAdmin` or `PlatformAdmin` (separation of duties: D-R3).

**What the Django admin exposes today (`CURRENT`):** the models registered in tracked, installed apps are `Student` (`students/admin.py:27`), `School`, `SchoolClass`, `TeacherAssignment` (`schools/admin.py:13-40`), plus Django's `auth.User`/`Group`. Access to `/admin/` is limited to `is_staff` users with model permissions; superusers see everything. `Document` has no admin registration. In demo settings `demo_intel` registers `StudentObservation`, `CounselingNote`, `InterventionRecord` (`demo_intel/admin.py:6-8`): demo only, synthetic data. A `PlatformAdmin` staff account must therefore be given **only** `auth` permissions, never `students`/`schools` permissions, and a test must assert it.

**Infrastructure-level reality (R-04):** the application separation is **not** cryptographic. `school_user` is a PostgreSQL superuser used by Django and Celery (`SECURITY.md` deferred item R-04); anyone with host/shell access can run `docker compose exec postgres psql -U school_user …` (`docker-compose.yml:114`) or read the volume. FastAPI's `fastapi_user` is limited to `SELECT, DELETE` on `documents` (`FASTAPI_DB_ROLE.md`). Therefore the claim "Platform Admin cannot see school data" is valid **only for the application**; it requires: R-04 fixed (least-privilege DB roles), server/shell access held by a separate person or process from day-to-day Platform Admin, and (later) database/volume encryption and backups access control (`DEPLOYMENT.md` §5–6). Until then the claim must be stated as application-level only.

**Document content:** a `documents` row holds `content` and metadata (`students/models.py:144-150`); the FastAPI list route groups by `parent_id` (`FASTAPI_DB_ROLE.md` list-query row). Whether the current list response exposes content is `NOT VERIFIED`; the proposal is a metadata-only projection for the Platform Admin route.

## Student (role 6) — AI Study Assistant user (redefined 2026-10-16)

**Owner decision:** the Student role exists to use the **AI Study Assistant** (RAG chat, Khanmigo-like): learning-first, age/grade appropriate, restricted scope, **ACL applied before retrieval and generation** (CCOS §18). A student does **not** get access to their own full record in the application; any self-view of grades/attendance is a separate later decision (D-R5).

**Allowed:** chat with the Study Assistant over an allow-listed corpus (learning material for the student's grade/subjects, per ADR-0007); conversation history of their own chats (retention D-R16).
**Denied:** `Student`/`Grade`/`Attendance` records of anyone including self, parents' data, `national_id`, other students, referrals, counseling notes and feedback, risk scores and alerts, recommendations, staff assistant, any export. The assistant must not be given counseling, risk or alert data as context; student identity fields are not placed in prompts.

**Minor-user risks (all open; none may be built before they are decided):**

| Risk | Required handling |
|---|---|
| LLM provider and data transfer | no student PII or chat content to an external provider without an approved egress policy (ADR-0008, `AI_GOVERNANCE.md`); local model (Ollama) is the default assumption |
| Chat logging and retention | what is logged, who may read it (never Admin by default), retention period and deletion; logs hold no counseling content |
| Content filtering / safety | age-appropriate filter on input and output, topic restriction to learning scope, prompt-injection defence, refusal behaviour |
| **Crisis / escalation** | **critical for this role** (D18): a student may disclose self-harm, abuse or danger in chat; a separate policy document must define detection, who is notified, response time and documentation **before** the chat exists; the assistant must never act as a counselor |
| Parental consent | consent (and age rules) before a minor account is created and before chats are stored; legal review |
| AI is not a therapist | CCOS §19: no diagnosis, therapy or decisions; labelled advisory; escalates to humans |
| Impersonation / account sharing | account provisioning, password reset by Platform Admin only, no self-service identity claims |
| Link to the record | needs a `Student ↔ User` link that does not exist today (`parent_user` is the only user link): nullable one-to-one, L3 data change; chat identity may instead be pseudonymous (D-R15) |

**Build:** direction only, in **P7 (RAG + AI assistants)**, after the 2.4 audit log and P3 security baseline exit; also requires ADR-0007 (RAG), ADR-0008 (provider/egress), the crisis policy (D18) and the legal review.

## Administrative staff (role 7) — direction only
**Minimal office set (direction):** report cards, letters, attendance. Everything else is a later module (see `PRODUCT_SCOPE.md`). Needs: student name, class, grade, term/year, subject scores (read-only summary), attendance totals, parents' names and contact for letters, and an identifier on the printed report card (`national_id` or school student number: D-R8). **Denied:** counseling data, referrals, risk scores/alerts, recommendations, behavior notes, parents' jobs, grade or attendance entry, student import, user/role management, RAG documents, the AI assistant. Output is generated documents; every generation is audit-logged (needs 2.4). Scope: whole school (office role), possibly narrowed later by grade.

## Build order

| Step | Content | Depends on |
|---|---|---|
| now | ADR-0005 roles 2–4: C4 (three groups, zero permissions) | owner approval |
| next | `Admin` → `SchoolAdmin` rename (own L3 commit) | ADR-0010 accepted |
| C4b/C5a | Grade Lead and Subject Teacher read-only | rename, ADR-0005 |
| 2.4 | audit log | — |
| 2.6/2.7 | referral, Counselor, feedback | 2.4, policy/legal review |
| after 2.4 **and** P3 exit | Administrative staff (minimal office set), Platform Admin (with R-04 fix and the production profile); Student/Study Assistant in P7 | audit, security baseline |
| P7 | Study Assistant for Student role (RAG chat) with crisis policy, consent, ADR-0007/0008 | audit, P3, policy/legal |
| later | report-card / letter generation | the above |

No Student, Administrative or Platform Admin code is merged before audit logging and the security baseline exit; they remain `NOT YET IMPLEMENTED`.

## Alternatives considered
(a) Keep `Admin` as the school role and treat superuser as Platform Admin: rejected, the superuser is all-seeing, contradicting role 8. (b) Rename only the new technical role (`TechAdmin`) and keep `Admin`: smaller change, but leaves the misleading name that already caused S-04-style over-trust; recommended fallback if the rename is judged too costly now. (c) A custom user model with a `role` field: rejected (ADR-0003 alternative d). (d) Platform Admin with read access to everything "for support": rejected by the owner's requirement.

## Consequences (security, data, testing, customization)
- Security: a coordinated rename touches Django and FastAPI; a missed literal silently denies (deny by default) rather than over-grants, but would lock the principal out of RAG documents; tests enumerate every `role_required`. Platform Admin separation is application-level until R-04.
- Data: group rename migration; later `Student.user` link and account provisioning for minors.
- Testing: per-role matrix tests (including "Platform Admin gets 404/403 on every student path and every school model in the admin"), a no-`'Admin'`-literal test, FastAPI role tests.
- Customization: group names are constants; per-role field lists are serializer configuration, not scattered `if` statements.

## Evidence (Stage 0 IDs, files)
S-01, S-04, S-05, R-04; `students/access.py`, `students/permissions.py`, `dashboard/views.py`, `dashboard/templates/dashboard/base.html:33`, `fastapi_core/auth.py`, `fastapi_core/main.py`, `schools/admin.py`, `students/admin.py`, `demo_intel/admin.py`, `docker-compose.yml:114`, `docs/FASTAPI_DB_ROLE.md`, `docs/DEPLOYMENT.md`, `docs/CCOS_REFERENCE.md`.

## Open decisions (each with a recommendation)

| # | Decision | Recommendation |
|---|---|---|
| D-R1 | **Rename DONE in code 2026-10-16 (`55babae`; real-DB migration pending owner).** `PlatformAdmin` still DRAFT. Original: Rename `Admin` → `SchoolAdmin` and add `PlatformAdmin`; when | **PlatformAdmin accepted in principle (owner)**; own L3 commit after C4, before C5a; fallback `TechAdmin` (metadata read-only) if the split proves problematic |
| D-R2 | Remove "superuser ⇒ school admin" | Yes, when `PlatformAdmin` exists; keep until then; one break-glass superuser held by the owner |
| D-R3 | Who assigns roles/groups | Platform Admin creates accounts/resets passwords; **Principal** approves staff-role assignment through a Principal-only screen; nobody can self-grant `SchoolAdmin`/`PlatformAdmin`; `auth.*` stays superuser-only until that screen exists |
| D-R4 | Who manages RAG documents | Platform Admin uploads/deletes (metadata view); Principal manages school-policy documents; document ACL per ADR-0007; metadata-only projection for Platform Admin |
| D-R5 | Self-view of own grades/attendance for students | **Not now**; separate later decision. `national_id` never shown to students |
| D-R6 | Recommendations visible to Parent/Student | Only items the author marks "shared"; default private to staff |
| D-R7 | Group name for role 7 | `AdminStaff` (`SchoolOffice` if the owner prefers) |
| D-R8 | Administrative staff identifier and edit rights | read-only summaries; identifier only on generated documents; student create/import stays Principal-only |
| D-R9 | Minor accounts and parental consent for the Study Assistant | Policy/legal decision before role 6 is built; consent recorded per student |
| D-R10 | What the Student sees of a referral | Nothing (student has no record view) |
| D-R14 | Study Assistant corpus and scope | Allow-listed learning material only; no staff or student data; per ADR-0007 |
| D-R15 | Student identity in the assistant | Pseudonymous session id by default; link to `Student` only if a use case requires it |
| D-R16 | Chat logging/retention | Log for safety review with a short retention; readable by a designated safeguarding role only, never counseling content |
| D-R17 | Crisis/escalation policy before any student chat | Mandatory (D18); no pilot without it |
| D-R11 | Platform Admin and logs | Technical logs without student values; every Platform Admin action audit-logged |
| D-R12 | Statement of the "cannot see school data" claim | Application-level only until R-04, host-access separation and encryption are done |
| D-R13 | Principal scope when a second school exists | Per-school (ADR-0004 school key); no cross-school principal in Phase 2 |

## Supersedes / superseded by
Does not supersede an ADR. Extends ADR-0003 (role set) and ADR-0005 (roles 2–4); proposes the final names for the roles ADR-0003 calls `Admin`, `Teacher`, `Parent`. Becomes effective for naming only when ACCEPTED.
