# Architecture Decision Records

Purpose: record decisions that are hard to reverse. Template: `TEMPLATE.md`. One ADR per decision; ADRs are never deleted — supersede them.
Status values: PROPOSED · ACCEPTED · SUPERSEDED · DEFERRED · DECISION REQUIRED. Only the owner marks ACCEPTED.
Established decisions (Django core, FastAPI AI layer, PostgreSQL, React target, AI advisory) live in `../ARCHITECTURE.md`, not as ADRs.

| ADR | Title | Status | Phase |
|---|---|---|---|
| 0001 | Service boundary & database ownership | PROPOSED (partly implemented in Phase 1) | 1 |
| 0002 | Service-to-service authentication | PROPOSED (interim implemented in Phase 1) | 1 |
| 0003 | Authorization model | ACCEPTED 2026-10-13 (Phase 2 scope; other roles unchanged) | 2 |
| 0011 | Temporal data model (academic years, enrollments) | DRAFT / PROPOSED 2026-10-16 | 2 |
| 0004 | School scoping / tenant key | ACCEPTED 2026-10-13 (integer PKs, `schools` app) | 2–4 |
| 0005 | Staff roles, scoping and counseling referral | ACCEPTED 2026-10-16 for decisions 1–9 (roles 2–4; amends 0003/0004; L3); 10–12 direction only | 2 |
| 0006 | React frontend mechanics | DEFERRED | 4/8 |
| 0007 | RAG architecture | DEFERRED | 7 |
| 0008 | LLM provider & data egress | DEFERRED | 7 |
| 0009 | Data layering & provenance | FUTURE — DEFERRED (renumbered from 0005 on 2026-10-16; no file yet; to be proposed in Phase 4) | 4 |
| 0010 | Platform role map (all 8 roles; `Admin` naming) | DRAFT 2026-10-16 (PROPOSED; L3) | 2–3 |

Only 0001–0005 and 0010 (DRAFT) files exist now. 0006–0009 are numbering reservations for future/deferred decisions; each file is created only when its phase begins (no speculative ADRs). Until then, references to them mean "future decision", not an existing record.
