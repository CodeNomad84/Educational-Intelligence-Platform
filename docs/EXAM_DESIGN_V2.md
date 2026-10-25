# EXAM DESIGN V2 — updates `EXAM_AND_SURVEY_DESIGN.md` §1 (exam module only)

Status: Slice 1 `CURRENT` (2026-10-25, owner-approved); slices 2-4 `PROPOSED`. Still **L3** (student-facing access, new child data). Owner approval required before slice 1.
Synthetic data only. Questionnaires (§2 of the old document) are out of scope here and unchanged. Written 2026-10-25.

## 1. What changes versus V1

| Topic | V1 | V2 |
|---|---|---|
| Module gate | not mentioned | sellable key **`exams`** (already declared in `schools/entitlements.py`, listed as "coming soon"; add it to `BUILT` only when slice 1 ships) |
| Topics | own `Topic` table, 3-level tree | `VocabularyTerm` (school-scoped, dated, never edited in place, rename = new term with `replaces`); no `Topic` table |
| AI suggestions | "off by default", own switch | gated by `exams` **and** counted by the AI call cap (`schools/ai_guard.consume`) |
| Trial | not mentioned | trial data survives and is readable again after a licensed row is added (test required by `ARCHITECTURE.md`) |
| Slices | 3 | 4, with the gate and vocabulary in slice 1 |

## 2. Module gate (`module='exams'`)

* Every route: `role_required(..., module='exams')` at request level **and** `require_module(obj.school_id, 'exams')` on the object's
  school, exactly as `missions/views.py` and `views_reports.py` do. Disabled = reads and writes blocked, data retained.
* Menu: the entry shows for all roles that use it; when the module is locked it links to the static info page
  (`dashboard/module_info.py`, add `exams` to `BUILT` at slice 1 so it stops saying "coming soon").
* Required gating tests (same set as mission): allowed, denied (no row), expired, not started, trial, cross-school, and
  **trial data readable after a licensed row is added**. Plus a no-export check and the sidebar duplicate test.
* Student-facing pages are gated by the student's school; a student of a school without `exams` gets 403, not an empty page.

## 3. Topics as `VocabularyTerm`

* New domains in `vocabulary/models.py` (`DOMAINS` + migration altering `choices`, as `0002_alter_vocabularyterm_domain` did for mission):
  `exam_topic` (concept level, the unit analytics group by) and optionally `exam_chapter`. `seed_vocabulary` gets default terms per school.
* `VocabularyTerm` is flat (no parent). Subject stays the fixed `SUBJECT_CHOICES` on `Question`/`Exam`; the topic term carries the
  concept name. **DECISION REQUIRED:** is flat subject + chapter + concept (three independent attributes, no tree) enough, or does the
  tree need a `parent` link on `VocabularyTerm` (schema change to a shared table, Tier C)? Recommendation: flat.
* Renaming a topic never rewrites history: old attempts keep pointing at the old term; analytics group by `replaces` chain.
* Questions reference a term (FK, PROTECT); a retired term stays readable for old attempts and cannot be chosen for new questions.

## 4. AI call cap

* AI question suggestions (slice 4) call `ai_guard.consume(school, 'exams')` **before** any provider call and stop on `AICapReached`
  (nothing is sent). Counts only, no content. `AICallUsage.module_key` is a free string, so no migration; the caps themselves are the
  per-school `ai_daily_cap` / `ai_monthly_cap` shared with the other assistants. **DECISION REQUIRED:** separate caps for `exams`?
* The request contains only the topic text (no student, class or school name). Output lands as `draft`, `source=ai_suggested`, and is
  invisible to students until a teacher approves it. Off until the external-LLM switch of `docs/ASSISTANT_DESIGN.md` §4 is decided.
* No LLM is involved in slices 1-3; analytics and recommendations are deterministic templates.

## 5. Slice plan

| Slice | Content | Gate to ship |
|---|---|---|
| 1 Bank and player | app `exams`; `Question/Option/Exam/ExamSession/QuestionAttempt`; vocabulary domains + seed; teacher editor + CSV import (dry-run); student player (retry + per-option explanation); one `visible_*` helper; audit events (no content); `exams` gate and the 7 gating tests | scope 404/403 matrix with mutation checks; explanations required; school isolation; no `Grade` row written; `run_tests.sh all` green |
| 2 Analytics | derived, recomputed on read: first-try accuracy per topic, baseline-relative time, repeated-error rule (≥ 3 sessions), "based on N attempts" and the minimum-attempt floor; student / teacher (own subject) / grade lead pages | schema has no strength/interest/label column (test); no ranking or sorting by score; "limited data" banner |
| 3 Feedback and links | deterministic study recommendations keyed on topic; Student 360 tile (grade lead scope); retention cleanup command | retention period decided by the owner |
| 4 AI suggestions | approval-gated draft questions behind the switch, cap and gate above | owner decision on provider and country |

## 6. Rules carried over unchanged from V1

Practice mode (no `Grade` row); time shown only against the student's own baseline; Subject Teacher sees only own subject and own
classes; SchoolAdmin sees aggregates (groups under 5 suppressed, as in mission); Parent: no view by default; no export; counseling data
never reaches AI; audit logs counts and ids only.

## 7. Decisions for the owner

1. Flat topics (subject + chapter + concept as separate attributes) or a tree (needs a `parent` link on `VocabularyTerm`)?
2. Separate AI caps for `exams`, or share the existing per-school caps?
3. Still open from V1: practice-only confirmation, SchoolAdmin/parent individual analytics, retention period, question ownership when a
   teacher leaves, AI suggestions allowed at all.

## 8. Owner decisions 2026-10-25 and what Slice 1 did

* **Topics:** flat, with hierarchical codes in `VocabularyTerm` (`math.ch3.fractions` = subject.chapter.concept); no `parent` field; a tree stays a later Tier C decision. Note: `VocabularyTerm.code` is a `SlugField`, whose validator (no dots) only runs in forms, not in `save()`; codes are therefore validated by the topics page itself (`<subject>.ch<N>.<a-z0-9_ concept>`, at most 50 characters).
* **AI call cap:** exams get their own counter and limits (decided). Not built in Slice 1 because nothing in Slice 1 calls an LLM; it lands with Slice 4 (school fields for the exams caps, `ai_guard` keyed on `exams`).
* **Slice 1 scope:** gate on every route; question bank (Subject Teacher, own school and subject, per-option explanations required by a database constraint and by the editor); topics page; exam creation (approved questions, own classes, optional window, publish and unpublish); student list and player (wrong option turns red with its own explanation, retry until correct, then why the right answer is right); attempts record seconds (each step clamped to 300 s), attempt count and wrong option ids in order; practice only (no `Grade` row). **Deferred to a later slice** (Tier B, easy to add): CSV import with dry-run, exam editing, SchoolAdmin/Grade Lead views, teacher-facing results (analytics are Slice 2).
* **Editing rule:** a question is edited only by its author and only until the first attempt; any edit returns it to draft. Retire and write a new version after that.
