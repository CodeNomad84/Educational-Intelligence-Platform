# AI GOVERNANCE

Status: CURRENT = prototype only (A-01..A-07); everything else TARGET. No autonomous agents. AI is advisory; humans decide.

## Principles
- AI output is never trusted ground truth; it is labeled as AI-generated, shows uncertainty, and cites sources (RAG).
- AI is not a therapist, counselor, diagnostician or decision-maker. Counseling data is not exposed to AI without an approved policy.
- **ACL before retrieval and generation**: retrieval filters by the requesting user's permissions first; never retrieve then redact.
- Log AI calls (who, purpose, sources, model/prompt version) without storing raw PII unnecessarily.
- No student PII and no student record to external LLMs. Hosted providers are used for non-personal content only; the
  policy itself is ADR-0008 (PROPOSED 2026-11-13) and it keeps decision 62 (local-only document QA) in force.

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
Change 0044 (2026-11-15, E2E audit F01/F02): the school-admin student page shows the probability as a whole Persian-digit percentage (`fa_percent` in `dashboard/templatetags/eip_ui.py`: ×100, no decimals — the page used to print a 0..1 value as `0.70%`) and labels the block «نمایشی / دادههای تکمیلی موجود نیست», with a sentence naming the three placeholder features and «این خروجی مبنای تصمیم نیست»; the outbound feature dict is no longer printed for the principal. Real homework/communication features remain DEFERRED (F02b), and the outbound vector still has no audit row beyond `view_detail` (F21) — the label must stay until both are closed.

## Versioning
Prompts, models and embedding versions are recorded in code/config and changes are L2 (L3 if provider/architecture changes).

## Provider adapter (P7, 2026-11-02; code `fastapi_core/llm_adapter.py`)
One OpenAI-compatible adapter, two provider classes, both OFF by default (decisions 56-57).
Example configuration (operator environment; names and model ids are placeholders, check the provider's current documentation):
- ChatGPT / OpenAI: `{"chatgpt": {"class": "external", "base_url": "https://api.openai.com/v1", "model": "<model id>", "api_key_env": "LLM_KEY_OPENAI"}}` (the key variable must be `LLM_KEY_*`, see below)
- Another hosted OpenAI-compatible API (DeepSeek, a reseller, a gateway): same shape with its own `base_url`, model and key variable.
- Local (Ollama, vLLM, LM Studio): `{"ollama": {"class": "local", "base_url": "http://ollama:11434/v1", "model": "<local model>"}}`
- Map schools: `LLM_SCHOOL_MAP={"1": "chatgpt", "2": "ollama"}`. A school not in the map has no AI.
Rules enforced in code and tests: external = non-personal purposes only plus a PII filter; local = may summarise school data the requesting user can already see; counseling data for neither; no key in logs, errors or responses; answers labelled advisory. `CURRENT` (corrected 2026-11-13, change 0043 — the earlier blanket "not implemented" was wrong): the Django side partly exists — the staff document-assistant page with a per-school switch (`docqa.AssistantSettings.ai_enabled`, OFF by default), the licensed daily/monthly caps in `schools/ai_guard.py` consumed by that path, and audit rows (`audit.DOC_ASK`, `DOC_UPLOAD`, `DOC_DELETE`, `DOC_TOGGLE`, `DOC_AI_SETTING`). Still `NOT YET IMPLEMENTED`: a per-school provider setting (the provider is chosen in the FastAPI environment, not in Django), any UI for the adapter itself, and any RAG over documents; `NOT VERIFIED`: behaviour against a real provider (no real key was used).

**Limits of the outbound filter (decision 59).** The external-class filter is a best-effort tripwire, not a guarantee: it cannot catch a first name alone, digits written in words, base64, obfuscated e-mails, transliterated names, names missing from the roster Django sends, or a description that identifies a student without a name or number, and it cannot recognise counseling content. What actually protects students is (1) the purpose whitelist and (2) Django building prompts that contain no personal data. Provider keys live in `LLM_KEY_*` variables dedicated to the adapter; the route `/llm/complete/` must only be reachable by Django (service token), never from a browser.

### Operator configuration (`CURRENT`, change 0043 / ADR-0008, 2026-11-13)

Provider configuration is data in ONE gitignored file, `.env.llm`, injected into the `fastapi` service only
(`docker-compose.yml`: optional `env_file`, `required: false` — a missing file means AI stays off, not a failed start).
Committed template: `.env.llm.example` (placeholders only, key value empty).

- `LLM_PROVIDERS` — JSON, one entry per provider: `class` (`external`/`local`), `base_url`, `model`, `api_key_env`,
  `timeout`, `max_tokens`. `external` must be `https`.
- `LLM_SCHOOL_MAP` — JSON school id → provider name. **Empty by default: no school has AI**, even with a provider listed.
- `LLM_DAILY_CAP` — adapter-side calls per school per UTC day, in memory (defence in depth; `0` blocks all). The
  licensed caps that a school sees are the Django ones (`School.ai_daily_cap` / `ai_monthly_cap`).
- The key itself: a dedicated `LLM_KEY_*` variable (GapGPT → `LLM_KEY_GAPGPT`). Django never receives it, so the only
  process that can reach a provider is the adapter.
- Verify before mapping any school: `python3 tools/llm_smoke.py --mock` (offline, no key, sends nothing) then
  `--live --env-file .env.llm` on the server (one fixed non-personal prompt). The tool prints fixed codes and counts,
  never a key.
- Mapping a school to an `external` provider is a data decision, not a config edit: record the provider's retention /
  no-training terms first (ADR-0008 decision 8), and remember the adapter refuses `document_qa` and
  `school_data_summary` for that class (decision 62).
