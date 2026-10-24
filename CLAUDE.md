# CLAUDE.md — Educational Intelligence Platform

Operational entry point for Claude Code. Details live in `docs/`; do not duplicate them here.
Claude Code is the implementation engine. **The human owner decides product, architecture, security and data policy.**

## 1. Project (one paragraph)
AI-native school platform (Persian/RTL users). Central concept: **Student 360**. Intended flow:
Data → Student 360 → Analytics → Rules → Risk → Alert → Human review → Intervention → Follow-up → Outcome → Re-evaluation.
AI is **advisory only**. Nothing AI-generated becomes trusted data without human validation.

## 2. Truth labels (use them; never blur them)
`CURRENT` verified in repo · `TARGET` intended, not built · `PROPOSED` awaiting approval · `NOT VERIFIED` not inspected/run ·
`NOT YET IMPLEMENTED` · `DECISION REQUIRED` owner must decide · `DEFERRED` consciously postponed.
Never claim something works without evidence (file, test output, command result). State what was run.

## 3. Architecture principles (see `docs/ARCHITECTURE.md`)
- Django = operational core (auth, RBAC, school data, workflows). FastAPI = AI/RAG layer. PostgreSQL (+pgvector). React + Bootstrap 5 RTL is the TARGET frontend (incremental).
- **Zero rewrite.** Evolve existing code. No new framework/service/dependency without a Level 3 proposal.
- Modular monolith + AI service. No microservices, Kafka, Kubernetes, agent frameworks without written justification.
- Deterministic rules before ML. Risk model is EXPERIMENTAL/PROTOTYPE. ACL is applied **before** retrieval/generation.
- School-ready, not enterprise multi-tenant: design so a school key can be added; do not hard-code one school.
- Configuration over custom code (`docs/CUSTOMIZATION.md`).

- **Modules & licensing:** four sellable keys (`advisor_ai`, `tutor_ai`, `exams`, `mission`); everything else is base, incl. Student 360, counseling and rule-based/ML risk (no LLM). Rows carry `kind` trial|licensed; a locked module stays visible in the menu (static info page); AI assistants have per-school call caps. Every new route/AI call must be gated by `schools/entitlements.py` or explicitly base. Details: `docs/ARCHITECTURE.md`.

## 4. Where truth lives
Intent: `docs/REQUIREMENTS.md` > accepted ADR (`docs/adr/`) > `docs/ARCHITECTURE.md`; the authorization matrix in `docs/SECURITY.md` is normative for permissions.
Fact: code, migrations, config, tests. Maps (`SYSTEM_MAP`, `MODULE_MAP`, `CHANGE_GUIDE`) are **derived** and lose to code.
Baseline of known defects: `docs/audit/STAGE0_BASELINE.md` (commit `3404a1a` of the owner's previous repository history; not resolvable in this repository). Do not re-audit it; cite finding IDs (e.g. S-01).
Conflict tie-break order: Security → Authorization → Data integrity → Testability → Simplicity → Core product value → Advanced AI → Optimization.
If two sources disagree: stop, report `DOCUMENTATION / CODE CONFLICT` (`/report-conflict`), do not silently pick one.

## 5. Before coding (efficient inspection)
Read only what the task needs: `git status`, then `docs/CHANGE_GUIDE.md` / `MODULE_MAP.md` to find files, then those files.
Do not dump documents into chat, repeat audits, or create unrequested files/artifacts. Keep tasks small and bounded; stop when done.

## 6. Change levels (full rules: `docs/CHANGE_PROCESS.md`)
- **L1 Routine** (bug fix, typo, small UI, test, obvious refactor): implement after inspection; report briefly.
- **L2 Significant** (new feature/model, API change, business rule, major workflow, AI prompt behavior): `/propose-change` → owner approval → implement → tests → `/report-change`.
- **L3 Architectural** (DB redesign, authN/authZ/RBAC, service boundaries, tenancy, storage, AI provider/RAG architecture, breaking API, sensitive data handling): Proposal → ADR → **explicit approval** → implement → tests → security review → report.
Unsure? Classify upward. Never execute L3 without explicit approval.

## 6a. Autonomy tiers (owner decision 2026-10-22; applies to Phases 2-3; supplements section 6, never overrides section 7)
**Tier A, act then report briefly:** Low/Info review findings (fix inline only if small and inside the same change, otherwise record in the Change Report; no separate hardening rounds); internal tooling, test and helper code; naming; file layout inside a module; error messages; refactors inside one module; commit ordering within an approved stage; docs format; continuing to the next commit of an already approved plan without stopping. May push to `phase-1/boot-security` (never force) after `scripts/run_tests.sh all` passes.
**Tier B, decide with a clear default, record it as a decision, continue; must be reversible:** Level 2 choices with an obvious recommended option.
**Tier C, stop and ask:** anything changing access rules (`visible_*`, roles, service token) or tenancy; irreversible migrations (S6, S7); schema or data model changes; product decisions (D-xx); any Medium-or-higher review finding; anything contradicting an earlier owner decision; the first entry of real data, 2.4, Counselor, and any new L3 stage; any unexpected test or mutation result.
**Cap:** at most one fix round per commit for review findings; the rest go to the open list. No hardening rounds unless the owner asks.
**Reports:** one page: what changed, evidence (test counts), Tier B decisions taken, and only the Tier C items that need the owner.
**Unchanged:** `&&` chain before every commit, both databases, `/security-review`, mutation checks for access changes, no real student data until P3 exit.

## 7. Hard rules
- Never read, print, edit or commit `.env` or secrets; never reproduce secret values found in code (cite file:line only). Rotation, not history rewrite.
- Never run `git push`, force-push, rebase, `reset --hard`, `clean`, or rewrite history or any command that writes to GitHub without the owner's explicit approval in chat for that specific action.. Check `git status` before and `git diff` after work. One focused change per commit; no unrelated edits.
- Do not bypass RBAC. New endpoints/views must declare authentication, role and object/school scope; add a permission test.
- **NO REAL STUDENT DATA** in any environment until the security baseline exit criteria (`docs/SECURITY.md`) are met. Use synthetic data only.
- Do not send student PII to external LLMs. Counseling data is never exposed to AI without an approved policy (`docs/AI_GOVERNANCE.md`).
- If you find a defect outside the task: document it (`CURRENT RISK — NOT YET FIXED` / Stage 0 ID / issue note); do not fix it silently.
- Do not delete functionality, replace working code, or add abstractions/dependencies without justification in the proposal.
- No hard-coded school-specific logic, names, thresholds or branding in core code.

## 8. Data & AI rules (summary)
Layers: Raw → Extracted → Validated → Canonical → Derived → Predictions/Insights; derived data carries provenance.
AI output is labeled, cited where RAG-based, shows uncertainty, and requires human review for any decision. AI never diagnoses, counsels or decides. Study Assistant (student-facing) and School Assistant (staff-facing) are separate.

## 9. Documentation sync
After a change, update only relevant docs: `SYSTEM_MAP`, `MODULE_MAP`, `CHANGE_GUIDE` (bump `Verified-at`), `ARCHITECTURE`, `SECURITY`, `TESTING`, `AI_GOVERNANCE`, `CUSTOMIZATION`, `ROADMAP`, ADR. Do not update mechanically. Do not create deferred docs (DATA_MODEL, API_MAP, RULE_ENGINE, DEPLOYMENT) until their phase begins.

## 10. Tests
Tests exist since Phase 1 (Django + FastAPI, stdlib only); no CI yet (T-01). Commands and gates: `docs/TESTING.md`. Run what exists; report real results; never claim "tests pass" without running them. Important flows need regression tests: login, RBAC, student/parent/teacher access, attendance, assessment, risk, alert, intervention, RAG permissions.

## 11. Explain, don't hide (human learning mode)
For significant changes give **WHY / WHAT / WHERE / HOW / RISKS** in concise engineering language. Explain any change touching >10 files, new abstraction, dependency or service. Answer "where do I change X?" with `/where-is` (evidence only, no invented paths).

## 12. Self-review & Definition of Done
Before reporting: correctness, architecture fit, security/authorization, data consistency, performance, maintainability, docs, customization, AI safety. Done = requirement understood + implemented + tests passing + security & permissions reviewed + migration handled + docs updated + customization considered + no known critical regression + Change Report (+ owner acceptance for major features). Definition: `docs/CHANGE_PROCESS.md`.

## 13. When uncertain
Ambiguous requirement → list interpretations, consequences, recommendation, and ask. Missing evidence → say `NOT VERIFIED`. Needs a decision → `DECISION REQUIRED`. Prefer asking one precise question over guessing a business rule.

## 14. Commands (`.claude/commands/`)
`/propose-change` · `/report-change` · `/where-is` · `/report-conflict` · `/audit-area`
Current phase and status: `docs/ROADMAP.md`.
