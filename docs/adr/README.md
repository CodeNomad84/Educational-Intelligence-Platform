# Architecture Decision Records

Purpose: record decisions that are hard to reverse. Template: `TEMPLATE.md`. One ADR per decision; ADRs are never deleted — supersede them.
Status values: PROPOSED · ACCEPTED · SUPERSEDED · DEFERRED · DECISION REQUIRED. Only the owner marks ACCEPTED.
Established decisions (Django core, FastAPI AI layer, PostgreSQL, React target, AI advisory) live in `../ARCHITECTURE.md`, not as ADRs.

| ADR | Title | Status | Phase |
|---|---|---|---|
| 0001 | Service boundary & database ownership | PROPOSED (partly implemented in Phase 1) | 1 |
| 0002 | Service-to-service authentication | PROPOSED (interim implemented in Phase 1) | 1 |
| 0003 | Authorization model | DECISION REQUIRED | 2 |
| 0004 | School scoping / tenant key | PROPOSED | 2–4 |
| 0005 | Data layering & provenance | FUTURE — DEFERRED (no file yet; to be proposed in Phase 4) | 4 |
| 0006 | React frontend mechanics | DEFERRED | 4/8 |
| 0007 | RAG architecture | DEFERRED | 7 |
| 0008 | LLM provider & data egress | DEFERRED | 7 |

Only 0001–0004 files exist now. 0005–0008 are numbering reservations for future/deferred decisions; each file is created only when its phase begins (no speculative ADRs). Until then, references to them mean "future decision", not an existing record.
