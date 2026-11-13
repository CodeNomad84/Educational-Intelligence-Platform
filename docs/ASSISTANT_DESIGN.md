# ASSISTANT DESIGN — Socratic study tutor (Khanmigo-style)

Status: **PROPOSED, design only. No LLM is integrated; nothing here is built (NOT YET IMPLEMENTED).** Classification: L3
(AI provider, sensitive data, authorization). Needs owner approval + ADR before any code. Rules it must obey:
`docs/AI_GOVERNANCE.md`, `CLAUDE.md` §7–8 (AI is advisory; no student PII to external LLMs; counseling data never to AI).

## 1. Goal and behavior
A student-facing tutor that **teaches by asking**: it gives hints and next questions, not final answers to graded work;
checks understanding; stays on the student's subjects; answers in Persian. It never diagnoses, counsels, grades or decides.
Every reply carries the label «پاسخ هوش مصنوعی — ممکن است اشتباه باشد» and cites its grounding when it used school material.

## 2. Grounding and access control (ACL BEFORE retrieval)
Context is assembled by Django, never by the model or FastAPI on its own:
1. Identify the student from the session; compute the allowed set with the existing choke point (`students/access.py`,
   role Student = own record only). The set is fixed **before** any search.
2. Retrieve only from the allowed set, as **derived, minimal items**: (a) teacher recommendations flagged
   `visible_to_student`, (b) the student's subject-level grade summary (no raw exam rows), (c) school-approved teaching
   notes/rules for the student's class and subject (a new `school_id`-scoped store; teachers publish, nothing is auto-trusted).
3. Hard exclusions at the query level (not by prompt): counselor notes and referrals, parent phones and jobs, national ids,
   other students, staff-only recommendations, audit data.
4. FastAPI receives the already-filtered context plus the signed service token with `school_id`; it has no database path
   to the excluded tables (`docs/FASTAPI_DB_ROLE.md`).

## 3. Pseudonymisation layer (only when an external LLM is enabled)
Runs in Django, outbound only, deterministic per request:
* **Structured fields** → tokens: student/teacher names → `[STUDENT_1]`, `[TEACHER_1]`; school name → `[SCHOOL]`; class titles → `[CLASS_1]`.
* **Free text scrub** (student question, teacher notes before they enter the prompt): replace every roster name of the
  school (students, staff, parent names — first, last, full, with Persian/Arabic letter and digit normalisation), then
  patterns: national-id (10 digits, Persian/Latin), phone (09…, +98…), e-mail, URL, address words (خیابان، کوچه، پلاک، ساختمان + number).
* **Re-identification** only inside the platform, after the response: tokens → names from an in-memory map that is **never
  sent, stored or logged**. Unknown tokens in the output are left as tokens.
* **Fail closed:** if the scrubber raises or finds a high-risk pattern it cannot replace (e.g. a 10-digit number), the
  request is not sent and the student sees a neutral message. Residual risk (a name the roster does not contain, a rare
  story that identifies a child) cannot be removed by regexes: see risks.

## 4. External-LLM switch (school-admin, DEFAULT OFF)
* Per-school setting `assistant_external_llm_enabled = False`. Only the SchoolAdmin of that school can enable it, through a
  confirmation page that states provider, country, what is sent (pseudonymised text) and what is not.
* Enabling, disabling and every change of provider are audit-logged (who, when, school; no content). Off = the rule-based
  stub only, or no assistant; nothing leaves Django.
* While on, the chat shows a **permanent banner**: «این گفتگو برای پردازش به یک سرویس هوش مصنوعی خارجی فرستاده می‌شود؛
  نام و مشخصات شما فرستاده نمی‌شود. اطلاعات شخصی وارد نکنید. معلم/مربی ممکن است خلاصهٔ مشکلات یادگیری را ببیند.»
* Local model (Ollama, already in `docker-compose.yml`) stays the preferred option; the switch governs only external providers.

## 5. What adults see
* **Learning-gap summaries** for the subject teacher and grade lead: per student/subject, topics where hints were needed,
  repeated errors, time on task — generated as structured counters/tags, **not raw chats**. Visible only inside the
  existing access scope (teacher: assigned classes; grade lead: grade). Chats themselves are stored short-term for
  safety review only (retention to decide), readable by nobody except through the escalation path below.
* No score, risk label or counseling inference is produced by the assistant.

## 6. Safety escalation
Detector (rules first, classifier optional) for self-harm, abuse, bullying, threats, substance use, and "I'm unsafe".
On trigger: (1) the assistant replies with a fixed, human-written supportive message and tells the student **clearly that a
trusted adult at school will be informed**; (2) Django creates an escalation to the **grade lead** with minimal disclosure:
student link, category, time, and a one-line template — not the transcript; the grade lead may open the flagged excerpt
(audit-logged) and decides, optionally via the existing referral to the counselor; (3) nothing is sent to the external
LLM after the trigger in that session. Not a diagnosis; a false positive costs a conversation, a miss is the real risk.

## 7. Phased build (after approval)
P0 ADR + governance text + school setting + audit events (no LLM). P1 context builder + ACL tests + pseudonymiser with a
test corpus (names, ids, phones in Persian digits). P2 local model behind the same interface. P3 external provider,
only after the owner enables it for one pilot school. Tests required: ACL negative tests per role, exclusion tests
(counselor note never in context), scrubber corpus, switch-off sends nothing (mock transport), escalation path.

## 8. Risks
* Re-identification from context (small classes, unique stories) despite scrubbing; a free-text answer can contain facts only a roster-aware human would notice.
* Provider terms, data location and retention for minors; Iran-based users and sanctions/availability of providers.
* Hallucinated or wrong teaching content; students trusting it; cheating on graded work.
* Escalation fatigue/false alarms; a missed disclosure creates real harm; the grade lead becomes a single point of failure (absence).
* Chat storage is itself sensitive data; kids may type secrets despite the banner.
* Persian quality of models and of the scrubber (spelling variants, ZWNJ, mixed digits).

## 9. Open decisions for the owner (DECISION REQUIRED)
1. Is any external provider acceptable at all, or local-only? If external: which, which country, which contract?
2. Parent notice/consent for students under 18 — required wording, who collects it?
3. Chat retention period and who may open a flagged excerpt (grade lead only, or also counselor/admin)?
4. Fallback when the grade lead is absent (deputy role?) and the response-time expectation.
5. May teachers' written notes be used as grounding at all, and do they need a per-note "usable by assistant" flag (recommended)?
6. Graded-work policy: hints only, or allow worked examples for practice material?
7. Should students see their own gap summary (recommended) and may parents?
8. Minimum age/grades for access (grades 7–12 today).
