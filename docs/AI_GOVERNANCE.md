# AI GOVERNANCE

Status: CURRENT = prototype only (A-01..A-07); everything else TARGET. No autonomous agents. AI is advisory; humans decide.

## Principles
- AI output is never trusted ground truth; it is labeled as AI-generated, shows uncertainty, and cites sources (RAG).
- AI is not a therapist, counselor, diagnostician or decision-maker. Counseling data is not exposed to AI without an approved policy.
- **ACL before retrieval and generation**: retrieval filters by the requesting user's permissions first; never retrieve then redact.
- Log AI calls (who, purpose, sources, model/prompt version) without storing raw PII unnecessarily.
- No student PII to external LLMs unless an approved provider/egress policy exists (ADR-0008 DEFERRED).

## Assistants (TARGET, separate)
| | Study Assistant | School Assistant |
|---|---|---|
| Audience | Student | Staff (role-aware) |
| Scope | Learning-first, age/grade-appropriate, restricted | Authorized school knowledge + permitted student context |
| Data | Own learning context only | Per authorization matrix |

## RAG governance (TARGET; ADR-0007 DEFERRED)
Document lifecycle (draft→approved→archived), metadata (owner, audience, sensitivity), per-document ACL, citations, relevance threshold, prompt-injection defense, evaluation set, pinned model/embedding versions.
CURRENT gaps: no ACL/metadata/threshold/injection defense, zero-vector embedding fallback, unpinned models (A-04).

## Risk model
CURRENT: EXPERIMENTAL/PROTOTYPE — trained on a synthetic label, 3 of 8 serving features constant (A-01, A-02). Must not drive real decisions. Rules (deterministic, versioned, simulated, human-approved; lifecycle Draft→Simulated→Pending Approval→Active→Paused→Archived) precede ML. AI-suggested rules always need human approval.

## Versioning
Prompts, models and embedding versions are recorded in code/config and changes are L2 (L3 if provider/architecture changes).
