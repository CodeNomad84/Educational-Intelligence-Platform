# CHANGE PROCESS & DEFINITION OF DONE

## Levels (classify upward when unsure)
| Level | Examples | Flow |
|---|---|---|
| L1 Routine | bug fix, typo, small UI, test, obvious refactor | inspect → implement → test → short report |
| L2 Significant | new feature/model, API change, business rule, major workflow, AI prompt behavior | Proposal → approval → implement → tests → Report |
| L3 Architectural | DB redesign, authN/authZ/RBAC, service boundary, tenancy, storage, RAG/AI provider, breaking API, sensitive-data handling, new dependency/service | Proposal → ADR → explicit approval → implement → tests → security review → Report |

## 11-step workflow
1 Requirement · 2 Inspection (`git status`, relevant code/docs) · 3 Classification · 4 Proposal (`templates/CHANGE_PROPOSAL.md`) · 5 Approval · 6 Implement (small, focused) · 7 Tests · 8 Security review · 9 Docs sync · 10 Report (`templates/CHANGE_REPORT.md`) · 11 Owner acceptance → commit.
L1 may skip steps 4–5. Never push without owner authorization.

## Definition of Done (project-wide)
Requirement understood + implementation complete + tests passing (real run, real results) + security reviewed + permissions reviewed (RBAC, object, school scope) + migration handled and reversible + documentation updated + customization considered (no hard-coded school logic) + no known critical regression + Change Report completed. Major features additionally need **owner acceptance**. "Done" without evidence is not done.

## Documentation sync
Update only what the change affects: SYSTEM_MAP, MODULE_MAP, CHANGE_GUIDE (bump `Verified-at`), ARCHITECTURE, SECURITY, TESTING, AI_GOVERNANCE, CUSTOMIZATION, ROADMAP, ADR. Deferred docs (DATA_MODEL, API_MAP, RULE_ENGINE, DEPLOYMENT) are created only when their phase starts.

## Conflicts & ambiguity
Doc/code conflict → report, don't silently resolve (`/report-conflict`). Ambiguous requirement → interpretations, consequences, recommendation, ask.

## Self-review checklist
Correctness · architecture fit · security · data consistency · performance · maintainability · docs · customization · AI safety.
