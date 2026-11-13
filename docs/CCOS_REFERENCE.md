# CCOS REFERENCE — summary extract

Status: reference summary created 2026-10-16 (owner decision D19). **Not a copy** of the CCOS master prompt; it paraphrases only the sections that `CLAUDE.md`, the ADRs and the access review rely on. The full master prompt (`MASTER PROMPT.md`) stays local and untracked. If this summary and the master prompt differ, the master prompt is the owner's source and this file must be corrected. Section numbers refer to the master prompt.

## §7 Data governance

The platform processes sensitive student/minor information. Required properties: privacy by design, least privilege, RBAC, object-level authorization where necessary, school/tenant isolation, audit and access logging, controlled data exports, secure handling of uploaded files and audio, controlled handling of counseling information, PII protection, careful use of external LLM APIs.

Data layers: Raw → Extracted → Validated → Canonical → Derived → Predictions/Insights. AI output never becomes trusted ground truth without validation.

## §18 AI / RAG governance

Govern: provider abstraction, prompt and model versioning, RAG sources, document lifecycle, metadata, access control, citations, confidence/uncertainty, evaluation, prompt-injection defense, PII handling, logging.

Two assistants: **Study Assistant** (student-facing, learning-first, age/grade appropriate, restricted scope) and **School Assistant** (staff-facing, role-aware, authorised knowledge and student context). **ACL is applied before retrieval and generation.** No autonomous agent architecture unless explicitly justified.

## §19 Counseling safety

Counseling functionality is sensitive. The system must distinguish four classes:

1. educational guidance;
2. counseling support;
3. sensitive counseling records;
4. crisis / escalation situations.

AI must not be represented as a therapist or an autonomous decision-maker.

Sensitive information must have: strict access control, auditability, retention rules, consent where applicable, controlled AI exposure.

## §23 Security governance (checklist for every significant change)

Authentication, authorization, object-level access, school isolation, SQL injection, XSS, CSRF, SSRF, insecure file upload, secret leakage, PII exposure, prompt injection, unauthorized RAG retrieval, unsafe exports, audit logging, dependency vulnerabilities. Security is not traded for implementation speed.

## Where this repository applies them

| CCOS | Repository location |
|---|---|
| §7, §23 | `SECURITY.md`, `ADR-0003`, `students/access.py` |
| §18 | `AI_GOVERNANCE.md`, `fastapi_core/auth.py` |
| §19 | `TEACHER_ACCESS_REVIEW.md` §7–§9; crisis/escalation path is **NOT DESIGNED** (separate policy document first, owner decision D18) |
