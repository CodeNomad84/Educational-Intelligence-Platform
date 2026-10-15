# STAFF ACCESS REVIEW (Grade Lead / Subject Teacher / Counselor) — PROPOSAL v3 (owner decisions recorded 2026-10-16)

Status: **PROPOSED** (2026-10-15), revised after the owner's three-role product decision and the owner's decisions of 2026-10-15 (D1, multi-role, referral workflow, satisfaction feedback). Supersedes the single-"Teacher" v1 of this file and, where they conflict, ADR-0003, ADR-0004 and `changes/0002-…`. Document only; no code. File name is kept because `ADR-0003` and `TRACEABILITY.md` P2-REQ-20 refer to it. Truth labels per `CLAUDE.md`. Basis: tracked code at `HEAD` (`e0cf762`).

## 0. Owner decision being implemented

| Role | Persian | Scope | Fields | Actions (target) |
|---|---|---|---|---|
| **Grade Lead** | مربی پایه | all students of the assigned grade(s) | full detail (contact, parents) **including `national_id`** (owner decision D1) | view; refer to counselor; write improvement recommendations |
| **Subject Teacher** | معلم درس | students of assigned classes, **only in own subject** | no `national_id`, phone, parents' jobs, `parent_user` | later: enter grades for own subject, see own-subject trend, write recommendations |
| **Counselor** | مشاور | a student only while an **active referral** exists | decided per policy (D6) | read; counseling notes (separate sensitive record); every read audit-logged |

A user may hold several roles; visibility is the **union** of the roles, but **a role never widens another role's scope** (a Grade Lead who is also a Subject Teacher sees only own subject/own classes outside the lead's grades). Out-of-scope objects return 404.

## 1. Read-only inspection: what exists (`CURRENT`) and what is missing

| Topic | Finding | Evidence |
|---|---|---|
| Roles | Django groups `Admin`, `Teacher`, `Parent`; superuser = Admin. No `GradeLead`/`Counselor` | `students/access.py:11-13`; FastAPI `auth.py:21` has only Admin/Teacher constants |
| Group creation | `seed_demo` creates `Admin`, `Parent` groups only; no tracked code creates `Teacher` (NOT VERIFIED elsewhere). C4's command will create all three | `students/management/commands/seed_demo.py:244-245` |
| `visible_students` | Admin all, Parent own children, everything else none | `students/access.py:30-43` |
| `Student.grade` | `IntegerField`, choices 7–12 (هفتم…دوازدهم). **This is the grade-level key** | `students/models.py:7-14` |
| `SchoolClass` | `school`, `title` (free text ≤50), `academic_year` (free text ≤20), `is_active`. **No grade field**; the grade of a class is not stored and cannot be derived reliably from `title` | `schools/models.py:30-52` |
| `TeacherAssignment` | `teacher`, `school_class`, `subject` (free text ≤50, blank allowed), `created_by`; unique (teacher, class, subject). `subject` is not tied to any vocabulary | `schools/models.py:56-93` |
| `Grade` (scores) | `student` FK, `subject` = **CharField with 15 fixed choices** (math, physics, … computer), `exam_type` (midterm/final/quiz/project), `score` float (no range validator seen), `date`. **No class, academic year, teacher or entered-by field** | `students/models.py:89-119` |
| `Attendance` | `student`, `date`, `status`, `note`; unique (student, date). **Not per-subject** | `students/models.py:121-140` |
| "Assessment" model | **Not in tracked code.** Exists only in the archived scaffold apps (`academics`, `behavior`) on branch `archive/scaffold-apps-2026-10-13` | `git ls-files` for both dirs is empty; `academics/models.py` untracked |
| Grade Lead / referral / counseling-note / recommendation models | `NOT YET IMPLEMENTED` | no such tracked model |
| Audit log | `NOT YET IMPLEMENTED` (S-05); Phase 2.4 | `ROADMAP.md` 2.4 |
| Student detail page | shows grades and attendance of the student without subject filtering | `dashboard/views.py:84-170` |
| API | `StudentViewSet` queryset = `visible_students`; filters/search include `national_id` | `students/views.py:174-193` |

Note (2026-10-16): the v1 access-path table (17 paths) was replaced by this inspection. Its path 17, the unauthenticated debug route `/test-fastapi/`, was **removed** (owner-approved L2; regression test `RemovedDebugRouteTests`). No other unauthenticated data route exists in `config/urls.py`.

### What each capability needs

| Capability | Needs | Gap |
|---|---|---|
| Grade Lead scope by grade | `GradeLeadAssignment(user, school, grade, academic_year, is_active)`; `visible_students` branch `Student.grade == a.grade` (+ school, + active) | New model. Student has no academic year; the year is only on its class (`school_class.academic_year`), so legacy/unlinked students need a rule (D4) |
| Subject Teacher "own subject only" | A vocabulary shared by `TeacherAssignment.subject` and `Grade.subject` | **Mismatch**: free text vs 15 choices. Needs `subject` constrained to the same choices (or a `Subject` model) plus data cleanup; otherwise matching is by fragile string equality |
| Subject-scoped data visibility | Query `Grade` rows by `(student in assigned class, subject == assigned subject)`; hide other subjects | Today the detail page shows all grades. Needs a subject-filtered read view; attendance is not per-subject (D7) |
| Grade entry by teacher | Write path with class + subject + academic-year checks; `entered_by`; score range validation; edit window | `Grade` has no `entered_by`/class/year; migration needed (L3 data change) |
| Recommendations | New record: author, student, subject (optional), text, visibility | New model |
| Referral lifecycle | `CounselingReferral(student, referred_by, counselor?, status, consent, created/closed)` with a state machine and transition rules | New model |
| Counselor read access | Visibility = active referral; per-read audit entry | Requires audit log first |
| Counseling notes | Separate sensitive-record storage (§7) | New model + policy |

## 2. Proposed access rules

Rules R1–R12 are `PROPOSED`. They supersede v1 R1–R14 and ADR-0003 decision 4–5.

R1. **Single choke point.** `visible_students(user)` (and a new `visible_grades(user)`) in `students/access.py` decide row visibility for every path; no view builds its own queryset. Output is the **union** over the user's roles; no role → empty (fail closed). **Non-widening rule:** the field/subject policy is attached to the grant through which a row is visible, not to the user. A student visible only through a Subject Teacher assignment keeps the Subject Teacher field policy and own-subject grades even if the same user is Grade Lead of another grade. Where a row is reachable through several grants, the most permissive grant that actually covers that row applies (never a grant from an unrelated grade or class). Implementation shape (per-role querysets or grant-tagged rows) is decided at C5a.

R2. **Grade Lead.** `Student.objects.filter(school=a.school, grade=a.grade)` for each active `GradeLeadAssignment` of the user, restricted to the assignment's academic year when D4 says so. Inactive assignment grants nothing. Assigned only by an Admin in the admin site; no self-service; `created_by` recorded.

R3. **Subject Teacher.** Students are visible only through `TeacherAssignment` → active `SchoolClass` → student. The subject is **access-relevant**: grade rows and any subject-specific records are visible only where `row.subject == assignment.subject`. Student identity rows are visible (name, grade, class). Rows of other subjects are never returned, in HTML or API.

R4. **Counselor.** Visible set = students with at least one referral in state `active` assigned to this counselor. Closing (or declining) a referral removes access immediately, with no cache. Counselor access never derives from class or grade.

R5. **Field policy per role** (explicit serializer lists chosen by role; never by client parameter):

| Field | Admin | Grade Lead | Subject Teacher | Counselor | Parent (own child) |
|---|---|---|---|---|---|
| name, grade, class | yes | yes | yes | yes | yes |
| `phone_number`, `father_job`, `mother_job`, `parent_user` | yes | yes | **no** | D6 | yes |
| `national_id` | yes | **yes** (owner D1, conditions R5a) | **no** | **no** | yes |
| own-subject grades | yes | all subjects | own subject | D6 | all |
| attendance | yes | yes | D7 | D6 | yes |
| counseling notes | no (ADR: Admin none) | no | no | owner of record | no |

R5a. **`national_id` conditions (owner D1).** Shown in list and detail for **Grade Lead (own grades only) and Admin only**; never to Subject Teacher or Counselor; never in exports, AI prompts, embeddings or RAG; never in logs. When the audit log exists (2.4), every read of an identity field by a non-Parent role is audited (actor, student, field set, time; not the value).

R6. **Search / filter / ordering cannot probe.** `national_id` and phone are searchable/filterable only by Admin and Grade Lead (within own scope; an out-of-scope id returns the same empty result as a non-existent one). For Subject Teacher and Counselor they are removed from `search_fields`/`filterset_fields`; ordering fields are limited to visible fields. These roles cannot test whether an identifier exists.

R7. **404 outside scope** (not 403), consistent with Parent.

R8. **Writes.** Student create/update/delete/import stay Admin only. Grade Lead may create referrals and recommendations; Subject Teacher may (later) enter grades for own class+subject only; every write checks the same relationships as reads, server-side.

R9. **Referral workflow with Admin-visible stuck points** (owner item 3; `PROPOSED`). Explicit states, each transition timestamped and attributed:

| State | Meaning | Waiting on | Entered by |
|---|---|---|---|
| `submitted` | Grade Lead referred the student | Counselor | Grade Lead |
| `counselor_declined` | Counselor declined (reason code required) | Grade Lead / Admin | Counselor |
| `awaiting_parent_consent` | Counselor accepted; family must agree | Family | Counselor |
| `parent_declined` | Family declined | Grade Lead / Admin | Parent or recorder |
| `active` | Consent recorded; counselor access granted | Counselor | system on consent |
| `closed` | Counseling ended (outcome code) | Satisfaction feedback (§9) | Counselor / Admin |
| `withdrawn` (optional) | Grade Lead cancelled before activation | none | Grade Lead |

Allowed transitions: `submitted → counselor_declined | awaiting_parent_consent | withdrawn`; `awaiting_parent_consent → active | parent_declined | withdrawn`; `active → closed`. `counselor_declined`, `parent_declined`, `withdrawn` and `closed` are terminal (a new referral is a new record); closed referrals are immutable.

**Admin visibility:** a referral-status view lists all referrals with current state, **days in state** and the "waiting on" party, so "counselor has not acted" is distinguishable from "family has not agreed". Admin sees workflow metadata only, never notes (§7). A configurable threshold (e.g. `REFERRAL_STALE_DAYS`) marks stuck items (configuration, not hard-coded).

**Parental consent record:** `consent_status`, `consent_method` (fixed choices: in person, phone, written form, parent portal), `consent_recorded_by` (user; the parent may record it through their Parent account), `consent_at`, optional `consent_note` (no clinical content). **Rule:** a referral cannot become `active` without recorded consent; there is **no exception path** (owner D5).

**Exception path (WITHDRAWN 2026-10-16, owner D5/D16: not implemented; recorded as a rejected design):** only Admin (not Grade Lead or Counselor) may activate without consent, with a mandatory reason code from a fixed list and a free-text justification; the referral is flagged `consent_exception=true`, audit-logged and listed in an Admin exceptions report; family notification as policy requires. Whether the exception exists, who may use it and its legal grounds are the owner's/legal decision (D5, D16).

Every transition is audit-logged (R10).

R10. **Audit.** Every counselor read of a student record or note, every referral transition, and every assignment change writes an audit entry (who, what, when, object, result). The Counselor role must not ship before the audit log exists.

R11. **AI/RAG/exports.** No role gets AI prediction, RAG or FastAPI data routes through this change; counseling data is excluded from AI and from exports until a separate approved policy (`AI_GOVERNANCE.md`).

R12. **Admin site / privileges.** Teachers, Grade Leads and Counselors are never staff; their groups hold **zero** model permissions. Assignment models are managed by Admin staff with explicit permissions granted by the C4 command; `auth.*` stays superuser-only (ADR-0003 decision 6, unchanged).

R13. **Landing/menu.** Grade Lead and Subject Teacher land on the student list; Counselor lands on the referral inbox. Menus come from `roles_for()` (all groups), not the first group.

## 3. Tests required (backend-neutral; SQLite and PostgreSQL)

| Role / area | Tests |
|---|---|
| Union | user with Grade Lead + Subject Teacher sees the union; no duplicates; user with no role sees none |
| Grade Lead scope | sees all students of assigned grade, none of other grades; two grades; other school; inactive assignment; assignment of other academic year (per D4); student with `school_class` NULL (per D4) |
| Grade Lead fields | payload contains contact/parent fields **and `national_id`** for own grades only; other grades 404; search by `national_id` works only inside scope and gives the same empty result for missing and out-of-scope ids; identity-field read audited once 2.4 exists |
| national_id exposure | absent for Subject Teacher/Counselor in HTML, API, search, ordering; absent from every export and AI/RAG path |
| Subject Teacher scope | sees students of assigned active class only; not other classes; inactive class; unassigned |
| Subject-only visibility | grades of other subjects absent in list/detail/API/trend; only own subject rows; two assignments with two subjects; assignment `subject` outside the vocabulary rejected |
| Subject Teacher fields | no `national_id`, phone, parents' jobs, `parent_user` (HTML and API) |
| Search/filter/order | `national_id`/phone probing returns nothing for non-Admin; hidden-field ordering ignored/rejected |
| Writes | Subject Teacher/Grade Lead cannot create/update/delete/import students (403); grade entry (later) limited to own class+subject, rejects other subject/class and out-of-range scores |
| Referral lifecycle | allowed and forbidden transitions per role/state; counselor sees student only in `active`; every other state, including `closed`, gives no counselor access on the next request; terminal states immutable; cannot become `active` without consent, no bypass exists; per-transition timestamps present; Admin status view shows state, days in state and waiting-on party and exposes no note text; a parent can record consent only for own child; stale threshold read from configuration |
| Satisfaction feedback | §9 tests |
| Non-widening | Grade Lead + Subject Teacher user: a student outside own grades keeps Subject Teacher fields (no `national_id`) and own-subject grades only; a student in own grade shows `national_id`; Subject Teacher + Parent union unchanged |
| Counselor | no access without referral; no access to students of other counselors' referrals; notes visible only to owner of record |
| Audit logging | each counselor read, transition and assignment change creates one entry with actor/object; failure to write the audit entry denies the read |
| Admin/privilege | the three groups have zero permissions; none can open `/admin/`; C4 command is idempotent and never grants `auth.*` |
| Parent/Admin unchanged | existing tests stay green |
| FastAPI | tokens of the new roles get 403 on every data route |
| Query count | list for a Grade Lead with several grades and a teacher with several classes stays bounded |

`/security-review` is mandatory before each of C5a, the referral/counselor commit and any grade-entry commit.

## 4. Risks

- Subject vocabulary mismatch (free text vs 15 choices) silently grants nothing or too much; must be fixed before R3 ships.
- Grade-by-integer scope over-grants when students have a wrong `grade`; imports (P3) now validate identifiers but not grade correctness beyond choices.
- Union of roles can accumulate more access than intended; admin UI should show a user's roles together.
- A new queryset using `Student.objects`/`Grade.objects` directly bypasses scoping; needs a review rule and a test enumerating views.
- Counseling data is the highest-sensitivity tier; storage, retention, consent and AI exposure must be decided before the model exists (§7).
- Without audit logging the Counselor cannot be accountable; sequencing in §6 enforces that.
- Grade Lead sees full contact data **and `national_id`** of a whole grade (owner decision): a large PII surface. Mitigations: grade-only scope, audit of identity-field reads once 2.4 exists, no export/AI path, no logging of values. Until audit exists those reads are not audited: a conscious `CURRENT RISK` to accept, or enable the field only after 2.4 (D17).
- Rollback: each commit isolated; reverting C5a returns these roles to "none".

## 5. Level, ADRs and documents to change

Level: **L3** (authorization model, new sensitive data, state machine). Proposal → ADR → explicit approval → implement → tests → security review → report.

| Document | Action | Exactly what |
|---|---|---|
| ADR-0003 | **Amend** (status note + decisions 1, 4, 5 and the Phase 2 matrix) | Roles: Teacher → Subject Teacher; add Grade Lead and Counselor groups; field policy per role; scope is class+subject for teachers and grade for Grade Lead; counselor by referral; "Teacher never receives…" kept for Subject Teacher only; "Counselor later = new role + relationship" (consequences) is now realised |
| ADR-0004 | **Amend** (small) | Add `GradeLeadAssignment` to the `schools` app; note `SchoolClass` has no grade; `TeacherAssignment.subject` becomes access-relevant and vocabulary-constrained; academic-year handling decision (D4) |
| **ADR-0005 (WRITTEN 2026-10-16; decisions 1–9 ACCEPTED)** | Create | Staff roles and referral model: three roles, union rule, referral state machine, counselor audit requirement, consent field, 404 rule. Cleaner than rewriting 0003 because 0003 is ACCEPTED and cites other roles as "future" |
| ADR-0006 or section in ADR-0005 | Create | Counseling record storage/retention/consent/AI exposure (§7) |
| `changes/0002-…` | Add a "superseded in part by ADR-0005" note | C4/C5 boundaries re-cut below |
| `SECURITY.md` | Rows | Matrix: add Grade Lead and (confirm) Counselor columns; "View student profile", "Create/edit student", "Attendance entry", "Grades entry/view", "Counseling records", "Student 360", "Risk/alert", "Intervention manage" rows; fix stale "CURRENT: all students" cells; S-04 status |
| `ROADMAP.md` | Re-sequence | §6 |
| `TRACEABILITY.md` | Rows | P2-REQ-02, -03, -16, -17 (reword for roles), -20 (review gate covers the three roles); new rows: grade-lead scope, subject-only visibility, referral lifecycle, counselor audit, counseling record safety |
| `MODULE_MAP.md` | Rows | `schools` (add `GradeLeadAssignment`), `students` (grade visibility, referral/recommendation models when built), new access/audit module |
| `CHANGE_GUIDE.md` | Rows | "Change who sees which student", "Add a role", "Change referral workflow", "Where counseling data lives"; bump `Verified-at` |
| `AI_GOVERNANCE.md` | Section | Counseling data excluded from AI/RAG/exports (§7) |
| `TESTING.md` | Section | New permission-test matrix (§3) |

## 6. Proposed re-sequencing (`ROADMAP.md` Phase 2)

| Step | Content | Level | Depends on |
|---|---|---|---|
| 2.1-C4 | grant command: creates groups `Admin`/`Teacher`/`GradeLead`/`Counselor` with **zero** model permissions; grants model permissions on assignment models to Admin staff only | L2 | none |
| gate | this review accepted + ADR-0005 | — | owner |
| 2.1-C4b | `GradeLeadAssignment` model + admin; subject vocabulary alignment for `TeacherAssignment.subject`/`Grade.subject` + data check | L3 | gate |
| **2.1-C5a** | **read-only** Grade Lead + Subject Teacher visibility, field policy, search rules, landing | L3 | C4b |
| 2.1-C6 | docs/matrix/traceability for C5a | L1 | C5a |
| 2.2 | teacher-scoped Student 360 read view (per role field policy) | L2 | C5a |
| 2.2b | grade entry (own class + subject) with `entered_by`, validation | L3 | C5a |
| 2.2c | improvement recommendations | L2 | C5a |
| **2.4** | **audit log + alert/review** | L2 | C5a |
| **2.6 (new)** | `CounselingReferral` workflow (R9), consent record, Admin status view, Counselor role, counseling record | L3 | **2.4 audit exists**, consent policy, §7 decisions |
| **2.7 (new)** | **Satisfaction feedback** (§9): separate model, family and counselor ratings, Admin aggregates | L3 | 2.6 (closed referrals), policy/legal review |
| 2.3, 2.5 | rules/risk, synthetic seed | as before | seed must be extended with the three roles |

Counselor is deliberately **after** audit logging (2.4); no counselor code, group permissions or access path is merged earlier.

## 7. Counseling safety (CCOS §19, cross-checked)

Source: `MASTER PROMPT.md` §19 "Counseling Safety" (untracked, excluded locally via `.git/info/exclude`; read 2026-10-15). `NOT VERIFIED` flag removed. Cross-check:

| CCOS §19 requirement | Status in this proposal |
|---|---|
| Counseling functionality is sensitive | covered |
| Distinguish educational guidance / counseling support / sensitive counseling records / crisis-escalation | **GAP in v2, now added below (7.1)** |
| AI must not be represented as a therapist or autonomous decision-maker | **GAP in v2, now added (7.7)** |
| Strict access control | R4, R5, R12, 7.2 |
| Auditability | R10, 7.3 |
| Retention rules | 7.4, D11 |
| Consent where applicable | R9 consent record, D5 |
| Controlled AI exposure | R11, 7.6 |

7.1 **Four record classes** (separate storage tiers): (a) *educational guidance*: recommendations by Grade Lead/Subject Teacher, ordinary student data; (b) *counseling support*: the referral workflow metadata (R9), visible to Admin as workflow only; (c) *sensitive counseling records*: notes, separate tables, owner of record only; (d) *crisis/escalation*: a distinct flag/path (who is notified, SLA, documentation). The crisis path is `NOT DESIGNED`; it needs the owner's policy and must not be improvised in code (D18).
7.2 **Access:** notes and (c)/(d) records only to the counselor of record; no Admin read by default; no break-glass in Phase 2.
7.3 **Audit:** every read/write logged; logs hold no note text and no `national_id` value.
7.4 **Retention:** a stated period and archival/deletion procedure before real use (D11); no cascade deletion from `Student` without review.
7.5 **Consent:** per R9; the satisfaction feedback in §9 is a separate consent-free-of-consequence record.
7.6 **AI:** counseling records, referral content and feedback text are excluded from RAG, embeddings, prompts, predictions and exports until a separate approved policy; enforced by code (models not importable by the AI layer) and tests.
7.7 **AI representation:** any AI output near counseling is labelled advisory, never presented as therapy, diagnosis or decision (`AI_GOVERNANCE.md`).
7.8 **Display:** notes only in the counselor view; never in lists, Parent or teacher pages.
7.9 No real data until Phase 3 exit.

**Proposal:** add the CCOS master prompt (or a short "CCOS summary" extract of the sections the repo relies on: §19 and the data/AI governance sections) under `docs/` as a tracked reference, e.g. `docs/CCOS_REFERENCE.md`. Reasons: `CLAUDE.md` and ADRs cite CCOS; the file is currently untracked and excluded, so reviewers and CI cannot see what is cited. Recommendation: a **summary extract** (docs-only, L1), not the 1547-line file verbatim, unless you want it public in the repository; the file is currently excluded locally on purpose (D19). Not committed.

## 8. Referral workflow: see R9; Admin status view

Summary for review: states `submitted`, `counselor_declined`, `awaiting_parent_consent`, `parent_declined`, `active`, `closed` (+ optional `withdrawn`); per-transition timestamp and actor; Admin sees state, days in state and who is being waited on; consent method/by/when recorded (parent may self-record); activation without consent is not possible (no exception path, owner D5).

## 9. Satisfaction feedback after counseling (PROPOSED; separate model and phase 2.7)

Trigger: a referral reaches `closed`. Two independent records per closed referral:

| Record | Author | Content | Visibility |
|---|---|---|---|
| Family feedback | parent/guardian (via Parent account, or recorded by staff with method noted) | structured rating 1–5 (overall) plus fixed-choice items (e.g. felt heard, process clear, scheduling convenient, would use again: yes/no/unsure); optional free text | rating + items: Admin (aggregates; individual only by explicit decision); free text: not visible to Admin; visibility to the counselor is opt-in by the family (D22) |
| Counselor self-assessment | counselor | structured process rating 1–5 plus fixed items (goals reached partly/fully/not, barriers: scheduling/engagement/resources/other); optional free text | rating + items: Admin; free text: author only |

Rules:
1. **Voluntary, no consequences:** family participation is optional and has no effect on the student's services; the family is told, in the prompt, that Admin can see the rating (not the comments) and what it is for.
2. **Counselor feedback is a self-assessment of the process,** with fixed prompts that cannot ask for an opinion about the family; free text is moderated by wording and by being visible to the author only.
3. **Privacy boundary:** Admin sees ratings and aggregate statistics, **not** free-text comments and **not** counseling note content (unless the owner decides otherwise, D22).
4. **Minimum cell size:** aggregates per counselor/period are shown only when at least **N = 5** closed referrals with feedback exist in the cell; below that, nothing is shown (cell suppression), and neighbouring cells cannot be combined to infer a small group (no overlapping period drill-down). Threshold is configuration (D20).
5. **Individual-level views** (one family's rating) only by explicit owner decision with its own access rule and audit (D21).
6. **Storage:** separate table(s); keyed by referral; no link from feedback to notes; excluded from AI/RAG/exports (§7.6); retention per D11.
7. **Audit:** Admin aggregate views and any individual access are audited.
8. **Counselor is not ranked from low-count data;** Admin evaluation of the *service* is the stated purpose, not staff discipline (policy statement to be approved).
9. **Policy/legal review recommended** before building (consent wording to families, data-protection obligations, treatment of minors' feedback).

Tests (2.7): feedback only for `closed` referrals of own child (family) or own referral (counselor); one record per author per referral; Admin API/HTML never returns free text or note content; aggregates suppressed below N and above-N cells contain no individual rows; the counselor sees no family rating at individual level (or per D22); non-participation does not alter referral or student data; AI/export paths do not import the feedback models; audit entries present.

## 10. Decisions

Owner decisions already taken (2026-10-15): D1 Grade Lead sees `national_id` (conditions R5a); multi-role union with non-widening (R1); referral workflow with Admin-visible stuck points and consent rule (R9); satisfaction feedback as a separate later phase (§9); recommendations of D2, D3, D4, D7, D12, D13, D14, D15 accepted.

Accepted recommendations (unchanged): D2 union; D3 several Grade Leads per grade and an unassigned grade fails closed; D4 yearly assignments (assignment carries `academic_year`; rollover deactivates); D7 Subject Teacher sees **no** attendance in C5a; D12 subject vocabulary = fixed choices shared with `Grade.subject`; D13 nullable `SchoolClass.grade`; D14 groups `Teacher`, `GradeLead`, `Counselor`; D15 L3 with ADR-0005.

Owner decisions of 2026-10-16 (recorded):

| # | Decision |
|---|---|
| D17 | **DECIDED:** the Grade Lead sees `national_id` **only with synthetic data until the 2.4 audit log exists**. No real student data before Phase 3 anyway; enabling the field for real data requires 2.4 (identity-field reads audited). |
| D5 | **DECIDED:** **no consent exception path is implemented.** A referral never becomes `active` without recorded parental consent. The "exception path" paragraph in R9 is withdrawn (kept only as rejected design). |
| D16 | **DECIDED** as recommended: no exception path (see D5); any future exception requires a legal opinion and a new ADR. |
| D18 | **DECIDED:** the crisis/escalation path goes into a **separate policy document first**; it is not part of C4, C5a or 2.6 code. |
| D19 | **DECIDED:** `docs/CCOS_REFERENCE.md` (summary of §19 and the data/AI governance sections, no full copy), committed separately. |
| D24 | **DECIDED:** policy/legal review is required **before building 2.6/2.7**; it is **not** a blocker for C4/C5a. |

Still open (`DECISION REQUIRED`):

| # | Decision | Recommendation |
|---|---|---|
| D6 | Counselor's visible fields during an active referral | names, grade, class, own referral/notes; contact fields and grades only if the referral grants them; `national_id` never (owner) |
| D8 | Who may transition (R9) | as R9 table; Admin may close or withdraw |
| D9 | Dedicated DB role/schema for counseling data | later; table separation now |
| D10 | Break-glass access to notes | none in Phase 2 |
| D11 | Retention period for referrals, notes, feedback | policy/legal decision before real data |
| D20 | Minimum count for aggregates | N = 5, configurable |
| D21 | Individual-level family ratings visible to Admin? | No |
| D22 | Free-text comments: who may read | Family text: **Admin none**; the counselor of record sees it only if the family ticks "share with my counselor", otherwise nobody reads it (kept for the family's own record or deleted per D11). Counselor text: author only |
| D23 | Family feedback channel (Parent portal vs staff-recorded) | Parent account preferred; staff-recorded allowed with method noted |

C4 stays in scope: creates the three groups (`Teacher`, `GradeLead`, `Counselor`) with zero model permissions. After the open decisions are answered, C4 is proposed first, then C4b/C5a.
