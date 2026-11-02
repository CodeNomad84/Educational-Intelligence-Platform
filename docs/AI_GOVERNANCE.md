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

## Provider adapter (P7, 2026-11-02; code `fastapi_core/llm_adapter.py`)
One OpenAI-compatible adapter, two provider classes, both OFF by default (decisions 56-57).
Example configuration (operator environment; names and model ids are placeholders, check the provider's current documentation):
- ChatGPT / OpenAI: `{"chatgpt": {"class": "external", "base_url": "https://api.openai.com/v1", "model": "<model id>", "api_key_env": "OPENAI_API_KEY"}}`
- Another hosted OpenAI-compatible API (DeepSeek, a reseller, a gateway): same shape with its own `base_url`, model and key variable.
- Local (Ollama, vLLM, LM Studio): `{"ollama": {"class": "local", "base_url": "http://ollama:11434/v1", "model": "<local model>"}}`
- Map schools: `LLM_SCHOOL_MAP={"1": "chatgpt", "2": "ollama"}`. A school not in the map has no AI.
Rules enforced in code and tests: external = non-personal purposes only plus a PII filter; local = may summarise school data the requesting user can already see; counseling data for neither; no key in logs, errors or responses; answers labelled advisory. `NOT YET IMPLEMENTED`: the Django side (UI, per-school provider setting, the licensed call caps and audit of AI calls) and any RAG over documents; `NOT VERIFIED`: behaviour against a real provider (no real key was used).

**Limits of the outbound filter (decision 59).** The external-class filter is a best-effort tripwire, not a guarantee: it cannot catch a first name alone, digits written in words, base64, obfuscated e-mails, transliterated names, names missing from the roster Django sends, or a description that identifies a student without a name or number, and it cannot recognise counseling content. What actually protects students is (1) the purpose whitelist and (2) Django building prompts that contain no personal data. Provider keys live in `LLM_KEY_*` variables dedicated to the adapter; the route `/llm/complete/` must only be reachable by Django (service token), never from a browser.
