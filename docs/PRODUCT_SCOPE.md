# PRODUCT SCOPE — DRAFT

Status: **DRAFT / PROPOSED** (2026-10-16; owner decisions of 2026-10-16 recorded in sections 2, 4 and 6). Docs only; nothing here is built or approved. Owner decisions are listed at the end. Truth labels per `CLAUDE.md`. Competitor/reference products are named by the owner as **orientation only**: this draft did **not** research them, and nothing below claims what they contain (`NOT VERIFIED`). No pricing or licensing content (out of scope by the owner's instruction).

## 1. Two product pillars

| | Pillar A — AI study assistant + educational intelligence | Pillar B — School administration automation |
|---|---|---|
| Role in the product | **The differentiator** | **The commercial layer** (what a school buys first and renews) |
| Reference (orientation only) | An AI tutor such as Khanmigo: learning-first, restricted scope, age/grade appropriate | Iranian school-ERP style products (Madyar, Abrisham ERP, Hamkelasi named by the owner; features `NOT VERIFIED`) |
| Users | Students (Study Assistant), staff (School Assistant, Student 360, rules, alerts, counseling referral) | Principal, administrative staff, teachers, parents |
| Core flow (CLAUDE.md §1) | Data → Student 360 → Analytics → Rules → Risk → Alert → Human review → Intervention → Follow-up → Outcome | Registration → timetable → attendance → grades → report cards → letters → communication |
| Status | Prototype pieces: risk model (EXPERIMENTAL), RAG (Admin-only, disabled for others), demo scope | `CURRENT`: Student records, import, class structure (Phase 2.1). Almost nothing else built |
| Safety posture | AI advisory only; ACL before retrieval; counseling data never to AI (CCOS §18–19) | Standard school PII rules; audit; role scoping (ADR-0003/0005/0010) |
| Depends on | audit log (2.4), security baseline (P3), RAG/provider ADRs (0007/0008), crisis policy (D18) | the same security baseline; Pillar B data feeds Pillar A |

**How they connect:** Pillar B creates the reliable, structured data (attendance, grades, classes, parents) that Pillar A needs, and gives schools an everyday reason to use the system. Pillar A is why a school chooses this platform over a plain ERP. Sequence therefore interleaves: B's data core first (already the Phase 2 direction), A's assistant after the safety gates.

## 2. Candidate administration modules (Pillar B)

**Owner decision (2026-10-16): the scope is the minimal office set only: student registry/file, attendance, grades, report cards, letters.** The LATER and DEFER rows below are a **list of possible modules, not a plan**; none is scheduled and each would need its own proposal.

Candidate list, generic school-office functions. Labels: **MIN** = minimal office set (direction), **LATER** = later module, **DEFER** = not now.

| Module | What it does | Data it needs | Set | State today |
|---|---|---|---|---|
| Student registry & enrollment | records, classes, parents, import | `Student`, `SchoolClass`, `parent_user` | MIN | `CURRENT` (basic) |
| Attendance | daily presence, absence reasons, totals | `Attendance` | **MIN** | model only; no entry UI |
| Grades & assessments | score entry per subject/exam, term summaries | `Grade` (+ class, year, entered-by) | **MIN** | model only; no entry path |
| Report cards | printable term/year report | grades, attendance totals, identifiers | **MIN** | `NOT YET IMPLEMENTED` |
| Letters & certificates | templated letters (enrolment confirmation, etc.) | student, class, parent contact | **MIN** | `NOT YET IMPLEMENTED` |
| Parent communication | notices, SMS/messaging, parent view | contacts, consent to notify | LATER | `NOT YET IMPLEMENTED` |
| Timetable / class schedule | weekly schedule, teacher/class load | classes, subjects, assignments | LATER | `NOT YET IMPLEMENTED` |
| Discipline / behavior log | incidents, positive notes | student, staff, event | LATER (sensitive; interacts with Pillar A) | scaffold only (archived) |
| Exams & question banks | exam scheduling, grading workflow | classes, subjects | LATER | — |
| Staff records | teacher profiles, assignments | users, assignments | LATER | assignments `CURRENT` |
| Fees / finance | tuition, invoices, payments | finance data, payment provider | DEFER (regulatory, integration) | — |
| Payroll / HR | staff payroll | HR data | DEFER (out of core focus) | — |
| Transport, library, inventory, canteen | operational extras | various | DEFER | — |
| Reports & exports for authorities | official statistics | aggregated school data | LATER (needs export policy) | — |

**Minimal office set (proposed first):** student registry (exists) + attendance + grades + report cards + letters. This is also exactly the set the owner named for the Administrative staff role in ADR-0010 (report cards, letters, attendance).

## 3. Multi-school configurability

How one codebase can be sold/installed for several schools without per-school code (`CLAUDE.md` §7: no hard-coded school logic):

| Mechanism | Today | Proposed direction |
|---|---|---|
| School key | `School` model, one default row; `Student.school`, `SchoolClass.school` (ADR-0004) | keep the key on every new school-owned table; a second school is data, not code |
| Per-school settings | `DEFAULT_SCHOOL_NAME` env; thresholds config-driven by principle (`CUSTOMIZATION.md`) | a settings model per school (grading scale, term structure, subject list, absence rules, report-card template, letter templates) |
| Vocabularies | grade levels 7–12, 15 subjects hard-coded in model choices | school-configurable subject list and grade structure behind a stable internal key (ties to D12 now fixed choices; a `Subject` model is the later step) |
| Templates | HTML templates in code | document templates (letters, report cards) stored as configuration with a school override |
| Roles | groups (ADR-0010) | same roles everywhere; per-school assignments (`GradeLeadAssignment`, `TeacherAssignment`) |
| Deployment | single-school Docker stack | per-school instance **or** one multi-school instance: `DECISION REQUIRED` (row-level isolation exists; `national_id` becomes `(school, national_id)` with a second school, ADR-0004 §8) |
| Branding | not hard-coded | per-school name/logo/RTL print layout in configuration |

**Why this supports selling to several schools:** every school-specific behavior is data or configuration; onboarding a school becomes "create School, import classes and students, assign staff, pick templates", not a code change. Cross-school isolation tests become a standing requirement once a second school exists.

## 4. Build vs integrate

| Area | Build in platform | Integrate / defer |
|---|---|---|
| Registry, attendance, grades, report cards, letters | build (core, owns the data AI needs) | — |
| SMS / messaging | thin adapter | provider integration (choice, cost, privacy) |
| Payment / fees | — | integrate with an approved gateway, or defer entirely |
| Identity / SSO | Django accounts | external SSO later |
| LLM / embeddings | provider abstraction | local model default; external provider only under ADR-0008 |
| Existing school databases | import via CSV/Excel (exists) | connectors later (CCOS §21) |

### 4.1 Option: integrate with an existing school-automation product via API

A candidate path next to building the office set: exchange data with an established school-automation product (the products the owner named are examples) through its API instead of, or alongside, building Pillar B modules. **Nothing is built now; this section only keeps the option open.**

(a) **Requirements for any data that leaves the platform** (CCOS §7 data governance: privacy by design, least privilege, controlled exports, PII protection; CCOS §17 customization: behavior configured, not coded, per school; the owner cited "17/7"):
- a written **data contract** per integration: which entities, which fields, direction, frequency, purpose;
- **minimal fields**: no `national_id`, phone, parents' jobs or counseling/risk data unless the contract names a need and the owner approves; minors' data is the strictest tier;
- **ACL before export**: the same role/scope rules that gate a screen gate an integration; an integration identity is a role with its own scope (not an Admin session);
- audit of every export (needs 2.4), retention and deletion rules at the receiver, and a legal/consent review for minors' data;
- counseling data, AI chat content and risk scores are **never** exported by integration without a separate approved policy.

(b) **Feasibility: `NOT VERIFIED`.** Whether any named product offers a **public, stable API** is unknown. Before deciding, verify from **public documentation pages only** (no accounts, no private material, no scraping of authenticated areas): API existence, authentication, versioning, entities exposed, terms of use. Record findings in this document with the URL and date.

(c) **Adapter boundary in the design:** an integration adapter interface between the platform's domain (students, classes, attendance, grades) and any external system, with a platform-owned canonical shape (Raw → Extracted → Validated → Canonical, CCOS §7). Build-in modules and external connectors then sit behind the same boundary, so choosing integrate or build later does not change the domain or the access layer. No code now.

| Path | Pros | Cons / risks |
|---|---|---|
| Build the minimal office set | one data owner, fewer exports, fits Pillar A data needs | effort, parity with established products |
| Integrate via API | faster to a school's existing workflow | dependence on an external API (`NOT VERIFIED`), minors' data leaving the platform, contract/legal work, adapter maintenance |
| Both behind the adapter | keeps both open | adapter design cost up front |

## 5. Dependencies and order (proposal)

1. Phase 2.1 finish: roles 2–4 read-only (ADR-0005), `Admin` rename (ADR-0010).
2. 2.4 audit log; P3 security baseline (gates real data and the roles in ADR-0010 direction).
3. Pillar B minimal office set on top of that (attendance, grades entry, report cards, letters), then LATER modules by owner priority.
4. Pillar A: Student 360, rules/risk/alerts (2.2–2.4), referral/counselor (2.6), then P7 Study Assistant with crisis policy, consent, ADR-0007/0008.
5. Multi-school settings (section 3) introduced as the first school-specific configuration appears, not speculatively.

## 6. Decisions the owner must make (`DECISION REQUIRED`)

| # | Decision | Recommendation |
|---|---|---|
| P1 | Is Pillar B in the same product/repository, with Pillar A as module set | Yes: one platform, shared data and roles |
| P2 | Minimal office set membership | **DECIDED (owner 2026-10-16):** registry/file + attendance + grades + report cards + letters only |
| P3 | Order: Pillar B data core before Pillar A assistant | Yes; the assistant needs audit, P3 and the crisis policy anyway |
| P4 | Which LATER modules, and in what order | **Not planned (owner 2026-10-16):** the LATER/DEFER rows are a list, not a plan |
| P11 | Integrate via API (section 4.1): pursue at all, and which product | Not now; first verify public API documentation (`NOT VERIFIED`), then decide; keep the adapter boundary in the design |
| P12 | Data contract template for outbound data | Required before any integration (fields, purpose, retention, ACL) |
| P5 | Fees/finance and payroll | DEFER; integrate or exclude, not build now |
| P6 | One instance per school vs multi-school instance | Decide before P9; design keeps the school key either way |
| P7 | Per-school configuration scope for Phase 2–4 | Report-card template, subject list, grading scale only |
| P8 | Language/locale and calendar | Persian, Jalali calendar as a deliberate requirement (`NOT VERIFIED` how dates are stored/displayed today) |
| P9 | Positioning against reference products | Owner to supply the comparison; this draft did not research them |
| P10 | Pricing/licensing | Out of scope for this document |

## 7. What this document does not claim

No competitor feature list, no market claims, no effort estimates. It is a scope and ordering draft to be corrected by the owner before any module proposal (each module needs its own L2/L3 proposal under `CHANGE_PROCESS.md`).
