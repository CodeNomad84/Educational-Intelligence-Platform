# EXAM AND SURVEY DESIGN — interactive exam, questionnaires, Google services

Status: `PROPOSED` — design only, no code. Both modules are **L3** (new sensitive data about children; student-facing access rules).
Nothing here is built (`NOT YET IMPLEMENTED`). Synthetic data only until the P3 exit rule is met. Owner approval required before slice 1.
Reuses: `students/access.py` scoping, `schools/audit.py` (`record`, fixed action vocabulary, no content), `TeacherAssignment.subject`
(`SUBJECT_CHOICES`), `GradeLeadAssignment`, `Consent` (governance).

## 1. Interactive exam (practice mode, not grading)

**Flow.** Student opens an assigned exam → sees one question at a time → picks an option. Wrong: the option turns red and shows
*its own* explanation; the student retries until correct. Correct: green + "why this is right", then Next. Practice, so it never
writes to `Grade` (owner may later decide otherwise: DECISION).

**Data model (`PROPOSED`, new app `exams`; every table carries `school`).**
| Model | Key fields |
|---|---|
| `Topic` | school, subject (`SUBJECT_CHOICES`), chapter, concept — a 3-level tree (subject > chapter > concept), school-editable |
| `Question` | school, author, concept→Topic, stem, `status` (draft/approved/retired), `source` (teacher/csv/ai_suggested), `approved_by` |
| `Option` | question, text, `is_correct`, **explanation** (required for every option, wrong and right) |
| `Exam` | school, subject, title, question set, target classes, open/close dates, created_by |
| `ExamSession` | exam, student, started_at, finished_at |
| `QuestionAttempt` | session, question, `seconds_spent`, `attempt_count`, `wrong_option_ids` (ordered list), `solved_at` |

No names, free text or answers beyond option ids are stored in attempt rows. Time is recorded per question; server-side clamp
(idle > N min counts as N) so a tab left open does not poison the baseline.

**Analytics (derived, recomputed on read; carries "based on N attempts").**
* Per concept/chapter/subject: first-try accuracy, attempts per question, weak/strong = relative to the student's *own* mean and a
  minimum-attempt floor (e.g. ≥ 5 questions) — below it, "not enough data".
* Cross-subject: same table side by side; speed-vs-accuracy quadrant (fast+wrong, slow+right…) per student, not per rank.
* Repeated error patterns: the same wrong option or same concept missed in ≥ 3 sessions (deterministic rule, listed with evidence).
* Trend: first-try accuracy and median time per week. **Time is shown only against the student's own baseline** (e.g. "faster than
  your usual"), never against classmates or as a score.
* Feedback: study recommendations from deterministic templates keyed on concept ("revisit chapter 3, concept X; you chose option B
  in 4 sessions"). "Observed strengths and interests" = concepts/subjects where the student chose optional extra practice or
  performed above own baseline, worded "what we observed", with the banner **"based on limited data, not definitive"**.
  **No talent labels, no fixed categories, no ranks, nothing stored as a permanent profile** — the view is computed live, and no
  `strength` or `interest` column exists.

**Visibility and rules.**
| Role | Sees |
|---|---|
| Student | own sessions and analytics only |
| Grade lead | students of their school/grade scope (same rule as `visible_students`), all subjects |
| Subject teacher | only students of own assigned classes, **only own subject's** exam data and questions |
| SchoolAdmin | question bank management and aggregates of own school; individual analytics: DECISION REQUIRED |
| Parent | DECISION REQUIRED (default: no) |
Every query goes through one `visible_*` helper (school + role), unknown/out-of-scope object → **404**, wrong role → **403**, as
elsewhere. Audit events (no content): `exam_analytics_view`, `exam_question_approve`, `exam_assign`; student's own use is not logged.
Mutation checks for each scope are required (CLAUDE.md §6a).

**AI question suggestions.** Teacher pastes a topic/chapter name (no student data); an LLM returns *draft* questions with option
explanations; they land as `draft`, `source=ai_suggested`, and become visible to students only after a teacher edits/approves
(`approved_by`). Off by default; goes through the external-LLM switch of `docs/ASSISTANT_DESIGN.md` §4. The request contains only the
topic text; no student, class or school name.

**Pages.** Student: exam list, question player (retry/explanation), my progress (trend, weak/strong, recommendations).
Teacher: question bank (filter by topic), question editor (options + explanations), CSV import with dry-run, assign exam,
class result view (own subject; per-concept heatmap, per-student drill-down). Grade lead: per-student cross-subject page,
linked from Student 360. Admin: topic tree, bank-wide approve/retire.

**3-slice plan.**
1. **Bank and player:** `Topic/Question/Option/Exam`, teacher editor + CSV import, student player, `ExamSession/QuestionAttempt`, visibility helper, audit. Tests: scope 404/403, explanations required, retry flow, school isolation.
2. **Analytics and feedback:** derived analytics, baseline-relative time, error patterns, recommendations, teacher/grade-lead/student pages, "limited data" rules, no-permanent-profile test (schema has no label fields).
3. **AI suggestions and Student 360 link:** approval-gated suggestions behind the switch, Student 360 tile, retention/cleanup command for attempts (retention period: DECISION).

## 2. Family and student questionnaires (built in, not Google Forms)

**Why in-platform.** An external form tool moves answers outside our access control, school scoping and audit log, and we could not
guarantee who reads them or when they are deleted. Everything stays in Django.

**Model (`PROPOSED`, new app `surveys`).**
| Model | Key fields |
|---|---|
| `Survey` | school, title, audience (parents/students/both), `consent_text`, `purpose`, `retention_until`, `export_enabled=False`, `visibility` (counselor+admin / +grade lead), `anonymous` flag, status |
| `SurveyQuestion` | survey, order, type (single, multi, scale 1–5, short text, yes/no), text, required, **`sensitive`** flag |
| `SurveyAssignment` | survey, target (class / grade / list of parents or students) |
| `SurveyResponse` | survey, respondent (nullable when anonymous), `consent_given_at`, submitted_at |
| `SurveyAnswer` | response, question, value |

**Rules.**
* Builder: SchoolAdmin and Counselor only. Free-text questions on sensitive topics are discouraged; the builder warns when a
  question is flagged `sensitive` ("is this needed? prefer a scale or yes/no; do not ask for names, health, family conflict details").
  Minimal-data guidance shown at creation: ask only what the stated purpose needs.
* Voluntary: the respondent sees the consent text and may decline with no consequence; no reminders that single out
  non-responders by name beyond the assignment list the counselor already sees.
* **Responses:** readable by Counselor and SchoolAdmin of the same school; grade lead only if the survey's `visibility` says so
  (default off); **never subject teachers**. Anonymous surveys show aggregates only with a minimum group size (e.g. ≥ 5).
* Retention: `retention_until` is mandatory; a cleanup command deletes answers after it (no silent extension).
* Export disabled by default; enabling is a per-survey SchoolAdmin action, audit-logged. Audit events (no content): `survey_create`,
  `survey_publish`, `survey_responses_view`, `survey_export_enable`, `survey_delete`.
* Parent respondents: scoped to their own children's assignment; student respondents: own only. Out of scope → 404.
* Counseling-type answers are **never given to AI** (`docs/AI_GOVERNANCE.md`).
* **Real data only after** the audit log (2.4, done), a written retention/consent policy approved by the owner, and the P3 exit.
  Until then: synthetic respondents only, labelled in the UI.

**Pages.** Builder (question types, sensitive flag, preview), assign, respond (parent/student, RTL, consent first), results
(counselor/admin: aggregates, per-response if non-anonymous), settings (retention, visibility, export switch).

**Slices.** (a) model + builder + respond, synthetic only, audit; (b) results views with group-size rule, retention command;
(c) export switch and grade-lead visibility option, after policy approval.

## 3. Google services — where they help without receiving student data

| Use | Student data to Google? | Note |
|---|---|---|
| Teachers author question banks in Google Sheets, download as CSV, upload to our importer | **No** (questions and explanations only) | Importer validates, dry-run, school-scoped. Safe and cheap; Excel does the same. |
| Optional "Sign in with Google" for staff | Identity (email) only | Adds a dependency and an account-linking rule; staff only, never students (L3, authN). |
| Shared drafts of questions/explanations in Docs | No | Teachers' own content; remind them not to paste student names. |
| Forms / Sheets for student or family answers | **Yes** | Not recommended (see risks). |

**Risks of sending student data to Google.** Data leaves our RBAC, school scope and audit log; the sharing model is controlled by the
form owner's Google account (link sharing, ex-employee accounts, personal accounts); no enforced retention or deletion by us;
cross-border storage and Google's terms apply; Persian names and results are identifiable even without ids; export/copy cannot
be prevented; we could not prove to parents who accessed what.

## 4. Open decisions for the owner (`DECISION REQUIRED`)
1. Approve the two modules as L3 and the slice order (exam first, questionnaires after the retention/consent policy)?
2. Exam is practice only (no `Grade` row) — confirm?
3. May the SchoolAdmin and the parent see individual exam analytics? (default: admin aggregates only, parent no)
4. Retention period for exam attempts and for each survey type; who writes the consent text (school or us)?
5. Grade-lead access to survey responses: never, or per survey?
6. Anonymous surveys: minimum group size (proposed 5)?
7. AI question suggestions: allowed at all, and which provider/country (needs the external-LLM switch decision)?
8. Google: CSV/Sheets upload only (recommended), and is "Sign in with Google" for staff wanted?
9. Subject vocabulary: keep the fixed `SUBJECT_CHOICES`, or let a school add subjects (affects `Topic`)?
10. Who owns the question content (school vs teacher) when a teacher leaves?
