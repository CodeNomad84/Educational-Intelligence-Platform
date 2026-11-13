# 0032 — Phase 7 exit report (AI adapter), 2026-11-02

**Built.** `fastapi_core/llm_adapter.py`: one OpenAI-compatible client (ChatGPT/OpenAI as a configuration example; DeepSeek-style APIs, resellers, Azure-style gateways and local Ollama/vLLM/LM Studio by configuration only), two provider classes, both OFF unless an operator maps a school; `POST /llm/complete/` (SchoolAdmin token, one school from the token). Rules in code: external = whitelisted non-personal purposes + outbound filter; local adds `school_data_summary`; counseling for neither; labelled advisory; keys from dedicated `LLM_KEY_*` variables, never logged or returned; usage logged without content; per-school daily cap and concurrency gate. No UI and no Django call path exist yet, so no student data can reach the route. No real key was configured or called; every test uses a mock transport.

**Decisions:** 56, 57, 59. **Tests:** FastAPI suite 56 tests OK (28 before P7; no network). Mutation checks by hand (each fails a test): outbound filter removed, purpose check removed, http for external, key not required, content logged, key-variable guard off, normalisation off, joined-conversation check off, redirects followed, concurrency gate off.

**Independent review (fresh agent, read-only; raw findings, owner approved the fix round):**
- M1 Medium FIXED: `api_key_env` could name any environment variable (exfiltration of platform secrets); now dedicated `LLM_KEY_*` plus a deny list.
- M2 Medium FIXED as far as a filter can be: bypasses via zero-width characters, Arabic letter variants, fullwidth digits, long digit runs, split messages; limits stated plainly in `AI_GOVERNANCE.md`.
- L1 redirects forwarded the Authorization header: FIXED (no redirects, no env proxies). L2 untyped body: FIXED. L3 threadpool exhaustion: FIXED (3 in flight per school, timeout at most 60 s). L5 `avoid_names` trusted from the caller: documented (only Django may call). L4 in-memory cap: documented.
- Info: 401/429 from a provider map to one `upstream_error` (an operator cannot tell a bad key from an outage); the local class has no PII filter by design.

**Owner tasks / not done:** the Django side (provider setting per school visible to the SchoolAdmin, prompt building with ACL, licensed `advisor_ai` call caps, audit of AI calls, UI); RAG over documents; verifying behaviour against a real provider (needs a real key: owner decision); legal review before any student data goes to any class.
