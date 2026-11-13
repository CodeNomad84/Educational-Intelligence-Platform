# PRODUCT BACKLOG — comparable products and a recommended top 10

Status: `PROPOSED` (owner decides priorities). Research date: 2026-10-23, web search, vendor pages and district pages only —
vendor claims are **NOT independently verified**. "Have / Partial / Missing" is judged against the repository
(`docs/CHANGE_GUIDE.md`, `docs/ROADMAP.md`); each row names the module so it can be checked.

Post-integration roadmap: the five **Fast-Path UX & Low-Friction Data Entry / Macro-Analytics** work packages are recorded in
[`docs/changes/0041-fast-path-ux-and-macro-data-PROPOSAL.md`](changes/0041-fast-path-ux-and-macro-data-PROPOSAL.md) — a **proposal
only, nothing implemented**. §4 below is the pointer; the work packages are not part of the top-10 in §3 until the owner chooses.

## 1. What comparable products are valued for

| Product | Most valued features (as described by the sources) | Source |
|---|---|---|
| **Panorama Student Success** | One early-warning view over attendance, behavior, discipline and course performance; MTSS tiers (Tier 2/3 identification); intervention creation and progress tracking; a library of 700+ suggested strategies; nightly import from the SIS; survey products (family, staff, student climate/SEL) feeding the picture | [Panorama Academy](https://academy.panoramaed.com/article/500-what-is-panorama-student-success) · [Utah selection, press release](https://www.rutlandherald.com/news/business/panorama-education-selected-as-utah-s-statewide-early-warning-system-vendor/article_64cdacf2-e41d-5ab5-864d-634f43e92018.html) |
| **ClassDojo** | Teacher–parent messaging (1:1 and group) with one-tap translation; class and school "stories" (updates, photos); student portfolios shared with parents | [ClassDojo Translate](https://blog.classdojo.com/introducing-classdojo-translate/) · [Wikipedia](https://en.wikipedia.org/wiki/ClassDojo) (language counts differ between sources) |
| **PowerSchool** (SIS + Performance Matters) | System of record for enrollment, attendance, discipline, grades, transcripts; real-time gradebook; parent/student portal (attendance, assignments, report cards, teacher email, alert notifications); early-warning indicators combining assessment, attendance, behavior | [Seattle Public Schools product page](https://www.seattleschools.org/departments/dots/software-information/powerschool-product/) · [Westfield case study](https://go.powerschool.com/rs/861-RMI-846/images/Westfield_Public_Schools_Reaching_At_Risk_Students_With_Performance_Matters.pdf) · [TrustRadius](https://www.trustradius.com/products/powerschool-student-information-system) (a reviewer asks for automatic late/absence alerts to parents) |
| **Khanmigo** (assistant) | Guides with questions instead of giving answers; screening of unsafe exchanges; adults (teacher/parent) notified of flagged messages; chat history visible to parents/teacher/admin and students are told so; daily interaction cap | [Khan Academy help](https://support.khanacademy.org/hc/en-us/articles/13860282793869) · [School Data Leadership review](https://schooldataleadership.org/systems/artifiicial-intelligence/khanmigo) (Khan's own descriptions; teacher-dashboard details not confirmed) |

## 2. Mapping to this platform

| Feature (value) | Status | Where / note |
|---|---|---|
| Role-based access, school scope, audit log | **Have** | `students/access.py`, `schools/audit.py` — stronger than most school apps in scope control |
| Grades, attendance entry and import | **Have** | `dashboard/teacher_views.py`, `students/views.py` import |
| Student 360 (one page per student) | **Have** (read-only) | `dashboard/student360.py` |
| Parent and student portals (own data only) | **Have** (basic) | `/students/`, `/me/` |
| Teacher feedback visible to student/parent | **Have** | `Recommendation.visible_to_student` |
| Counselor referral and case notes | **Have** | `dashboard/counselor_views.py` |
| Early-warning view (attendance + grades + behavior) | **Partial** | rule-based demo dashboards (`demo_intel`, grade-lead page); not a production rule engine; Alert model NOT YET IMPLEMENTED |
| Intervention tracking and follow-up outcome | **Missing** | flow step "Intervention → Follow-up → Outcome" NOT YET IMPLEMENTED (Phase 6) |
| MTSS-style tiers / strategy library | **Missing** | needs a school-approved list of strategies (owner content decision) |
| Parent notifications (absence, low grade) | **Missing** | `students/tasks.py` unused; no channel chosen (SMS/e-mail/in-app) — DECISION REQUIRED |
| Teacher–parent messaging | **Missing** | `TeacherParentCommunication` model exists, no UI; moderation and privacy to decide |
| Report cards / transcripts (printable) | **Missing** | Persian-format PDF/XLSX export |
| Behavior / discipline log with trend | **Partial** | `behavior` app exists; no teacher UI (to verify) |
| Surveys (student climate, family) | **Missing** | needs a privacy policy before any collection |
| Homework / assignments | **Partial** | `Homework` model only |
| Assistant: Socratic tutor | **Partial** | rule-based stub `students/study_assistant.py`; design in `docs/ASSISTANT_DESIGN.md` (no LLM yet) |
| Assistant: safety flags to adults, transparency to student | **Missing** | in the design |
| Multi-language / translation | **n/a** | Persian first; only needed if non-Persian-speaking families exist |
| Bulk onboarding of accounts | **Have** (this round) | `/school/accounts/` (Excel, dry-run, login sheet) |

## 3. Recommended top-10 backlog (value for a Persian-language school, risk, dependency order)

1. **Alerts from deterministic rules** (absence streak, grade drop) with a review queue for the grade lead — completes the core flow step "Risk → Alert → Human review"; explainable; no new service. (L2)
2. **Interventions with follow-up and outcome** — a small record linked to an alert/referral: owner, action, due date, result. This is what Panorama's customers pay for and what turns the dashboards into a process. (L2)
3. **Parent notifications for absence / low result** (in-app first, then SMS/e-mail once the owner chooses a channel) — the most requested gap in PowerSchool reviews. (L2, DECISION REQUIRED on channel)
4. **Printable report card / progress sheet per student** (XLSX/PDF, Persian, school header from configuration). (L1–L2)
5. **Parent ↔ teacher messaging, text only, school-scoped, logged** — ClassDojo's core value; start with one-way announcements and "request a meeting". (L2)
6. **Behavior / discipline log UI for teachers** feeding the early-warning rules. (L2)
7. **Strategy library for interventions** (school-written, not imported content) shown as suggestions to the human reviewer. (L2, content by the school)
8. **Student-facing study assistant with an LLM** under the access, pseudonymisation and escalation rules of `docs/ASSISTANT_DESIGN.md` (after approval; default OFF). (L3)
9. **Satisfaction / climate micro-surveys** (anonymous, aggregated, minimum group size) — only after a privacy policy exists. (L3: sensitive data)
10. **Operational hardening that unlocks real data**: rate limiting / lockout, HTTPS, scheduled backups with a tested restore, CI, 2FA for SchoolAdmin. Not a feature, but it gates items 3, 5 and 8. (L3)
11. **Interactive exam / practice with per-option explanations and learning analytics** — design in `docs/EXAM_AND_SURVEY_DESIGN.md` §1 (3 slices). (L3: new student-level data)
12. **In-platform family and student questionnaires** (consent, retention, restricted access; no Google Forms) — `docs/EXAM_AND_SURVEY_DESIGN.md` §2. Refines item 9; real data only after the retention/consent policy. (L3)

## 4. Upcoming Fast-Path Enhancements (Post Proposal 0040)

Recorded, not approved: each row is a **work package of
[`0041`](changes/0041-fast-path-ux-and-macro-data-PROPOSAL.md)**, `Status: PROPOSED`, with its own gates (§5.3 there). Level is the
change level that a future implementation proposal must carry, not a claim that it is scheduled.

| WP | Title | Level | Gate before any code | Outcome in one line |
|---|---|---|---|---|
| WP-1 | Negative attendance (bulk-exception flow) | L2 | owner answers D-1.1/D-1.2; **closes the §2 "attendance entry: Have" conflict** (see 0041 §2.2 — there is no write path today) | a class is marked in seconds: everyone present by default, only exceptions tapped |
| WP-2 | Ladder-style grade grid (keyboard UX) | L2 | D-2.1/D-2.2/D-2.3 | type, Enter, type, Enter — each cell saved without a page reload |
| WP-3 | Zero-hardware OMR answer-sheet scanner | L3 | new dependency + service-boundary ADR (D-3.1) | a phone photo of a bubble sheet becomes a confirmed score proposal |
| WP-4 | Voice-to-incident logging (Whisper + extraction) | L3 | local-only provider, prompt/model versioning, no-write-without-confirm test (D-4.1) | a 20-second voice note becomes a draft `BehaviorNote` a teacher confirms |
| WP-5 | Macro-analytics & regional governance (B2G) | L3 | `Region` schema + new authority role + fifth entitlement key + legal sign-off (D-5.1–D-5.5) | aggregates with k-anonymity and secondary suppression, never a child's row |

Order and rationale: 0041 §5. Recommendation: WP-1 first (a correctness gap), WP-2 second, WP-3/WP-4 deferred until the pilot shows the
volume, WP-5 treated as a decision rather than a backlog item (0041 §14.2 — a static annual report may satisfy the same ask).

## 5. Method and limits
Four standard searches (one per product); results are marketing pages, district pages and one review site. Feature lists
may be out of date or differ by edition. No product was tried. Use this as a hypothesis list, then confirm with teachers
and parents of the pilot school before building.
