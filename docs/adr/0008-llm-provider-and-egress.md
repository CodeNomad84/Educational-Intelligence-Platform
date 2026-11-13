# ADR-0008: one provider-agnostic LLM adapter; external egress only for non-personal purposes

- Status: **PROPOSED 2026-11-13** (owner answered D1–D6 of `docs/changes/0043-gapgpt-provider-PROPOSAL.md` on
  2026-11-13: S1 approved, S2–S4 `DEFERRED`. Only the owner marks ACCEPTED.)
- Date: 2026-11-13
- Decider: owner
- Level: L3 (AI provider + data egress; sensitive-data handling)
- Relation: replaces the DEFERRED reservation at `docs/adr/README.md:17`. Builds on decisions 56, 57, 59, 61–63
  (`docs/DECISIONS_BY_CODE.md`); **keeps decision 62 in force**. Does not touch ADR-0007 (RAG, still DEFERRED).
- Scope: the decision is recorded; **only S1 of change 0043 is implemented** (config surface, example, key-free
  smoke check, tests). No school is mapped to a cloud provider in the default or pilot state.

## Context

`CURRENT` facts this decision starts from (evidence in change 0043 §2):

- `fastapi_core/llm_adapter.py` is already provider-agnostic: one stdlib `urllib` client for
  `POST {base_url}/chat/completions`, no vendor SDK, no dependency. GapGPT, OpenAI, DeepSeek, a gateway or a local
  Ollama `/v1` are all the same code path (decision 56, `llm_adapter.py:1-4`).
- Two classes, both OFF by default: `external` (data leaves the platform) and `local`
  (`llm_adapter.py:30-33`). An `external` provider is refused for `document_qa` and `school_data_summary`
  (`llm_adapter.py:229-231`); that refusal is decision 62, a privacy rule, not a limitation.
- Configuration is environment-only: `LLM_PROVIDERS` (JSON), `LLM_SCHOOL_MAP` (JSON), `LLM_DAILY_CAP`
  (`llm_adapter.py:11-15,81-111`). Keys are read only from an `LLM_KEY_*` variable named in the config
  (`llm_adapter.py:36-37,70-74`) — review M1: the variable is dedicated to the adapter, so a Django secret can never
  be pointed at by a typo.
- The `fastapi` service deliberately receives neither `.env` nor Django's secrets
  (`docker-compose.yml:142-146`) and has no published port (`docker-compose.yml:136-138`), so the adapter is reachable
  only by Django over the internal network.
- **Gap until this change**: no file in the repository let an operator place provider configuration. `.env.example` had
  no `LLM_*` line, the compose `fastapi` service mounted only `.env.service`/`.env.fastapi`, and every test used a mock
  transport, so no smoke path existed at all.
- GapGPT itself is `NOT VERIFIED`: its site served a JavaScript shell and its documentation host was unreachable when
  this was written. Base URL, model ids, retention, residency and terms are therefore **assumptions in the example
  file**, not facts. A reseller is a **sub-processor** for any text sent to it.

## Decision

1. **One adapter, configuration only (D1 = A).** Connecting a provider is configuration: `LLM_PROVIDERS` +
   `LLM_SCHOOL_MAP` + one `LLM_KEY_*` value. No provider-specific code, class, SDK or dependency, ever (decision 56).
   "Connected" means the platform *can* reach the provider, not that any school uses it: the default and pilot state is
   `LLM_SCHOOL_MAP={}` — no school has AI.
2. **External egress is limited to the four non-personal purposes (D2).** `policy_document`,
   `curriculum_text`, `question_draft`, `pedagogy`. **Zero student PII and zero student records** leave the platform to a
   hosted provider — not "redacted", not "anonymised", not in a summarised form. Cumulative or individual student data
   stays inside the platform. The outbound filter (`llm_adapter.py:114-154`) is defence in depth and stays documented as
   a best-effort tripwire (decision 59); the real protection is the purpose whitelist plus Django building non-personal
   prompts.
3. **Decision 62 stays intact (D4).** `document_qa` and `school_data_summary` remain `local`-class-only. Registering a
   cloud provider in the catalog does **not** make the document-QA page use it: `docqa/services.py:105-112` requires
   `class == "local"` and keeps doing so. Sensitive document QA stays bound to a local backend until an
   anonymisation/redaction layer is formally architected — that is its own L3 change, not this one.
4. **Configuration lives in a service-scoped file (D3).** Committed placeholder file `.env.llm.example`; operator file
   `.env.llm` (gitignored) injected into the `fastapi` service **only**, as an optional `env_file` entry
   (`required: false`): a missing file is a no-op, not a startup failure. Django does not receive these variables and
   never holds the key — the adapter in FastAPI is the single egress point. One owner per secret, the pattern already
   used by `.env.service`, `.env.fastapi` and `.env.minio`.
5. **The key variable is `LLM_KEY_*` (deviation from D6, recorded).** D6 proposed `GAPGPT_API_KEY`; the adapter accepts
   only names matching `LLM_KEY_[A-Z0-9_]{1,56}` (`llm_adapter.py:36`) and rejects names containing `SERVICE_JWT`,
   `SECRET`, `PASSWORD`, `DATABASE`, `POSTGRES`, `DJANGO`, `TOKEN_SIGNING` (`llm_adapter.py:37`). The deployed name is
   therefore **`LLM_KEY_GAPGPT`**. Accepting an arbitrary name would weaken review M1 — the rule that stops a config
   typo from pointing the adapter at a Django secret.
6. **Base URL and model live inside `LLM_PROVIDERS` (deviation from D6, recorded).** D6 offered
   `https://api.gapgpt.app/v1` "or configured via `GAPGPT_BASE_URL`". A separate `GAPGPT_BASE_URL` variable is a second
   source of truth that can silently disagree with the JSON, and it would need adapter code plus a consistency rule.
   Instead the JSON carries `base_url` and `model` — one place per provider, validated for scheme, host and absent
   userinfo (`llm_adapter.py:60-78`). The values in `.env.llm.example` are **placeholders to confirm against the
   provider's documentation**.
7. **Defensive caps remain (D6).** Code-level: `timeout ≤ 60 s`, `max_tokens ≤ 4000`, ≤ 8000 outbound characters,
   ≤ 20 messages, ≤ 3 concurrent calls per school (`llm_adapter.py:35,75-77,174-182`). Operator-level: `LLM_DAILY_CAP`
   (per school per UTC day, in memory, default 200; `0` blocks everything). Product-level: the licensed per-school daily
   and monthly caps in `schools/ai_guard.py:26-43`, consumed in Django **before** anything is sent. The example ships
   `LLM_DAILY_CAP=100` and `max_tokens: 600`.
8. **A reseller is a sub-processor.** Any text given to GapGPT may be retained by it under terms this project has not
   seen (`NOT VERIFIED`). Consequences: only non-personal content (decision 2); no school mapped by default (decision 1);
   the operator records the provider's retention/no-training terms before the first school is mapped; switching
   providers is a configuration change recorded as a decision.
9. **Verification is offline by default.** `tools/llm_smoke.py` exercises the real adapter code path with a fake
   transport (`--mock`, the default) and makes one live call only with the explicit `--live` flag plus a key. Both paths
   print fixed codes and counts — never the key, never provider error text. Tests never touch the network.

## Alternatives considered

- **A GapGPT-specific client/SDK.** Rejected: new dependency, breaks provider-agnosticism, contradicts decision 56 and
  `CLAUDE.md` §3, and makes a second provider a code change.
- **Put the provider config in `.env` (Django's file).** Rejected: FastAPI deliberately does not read `.env`
  (`docker-compose.yml:142-143`), so the config would be invisible to the only process that uses it, while Django would
  hold a foreign secret.
- **Put the config in compose `environment:` with `${…}` interpolation.** Rejected: the compose file is versioned, so
  provider names, model ids and URLs would become code; and `${…}` resolves from `.env`, i.e. Django's file again.
- **Store the key in the database (an admin UI).** Rejected: a secret in the app DB and in every backup, outside the
  `LLM_KEY_*` rule; a per-school provider setting would first need ACL, audit and a rotation story.
- **Enable `document_qa` for `external` "because school documents are not personal".** Rejected: reverses decision 62 as
  a side effect, and a school document can still contain names (a disciplinary letter, a scholarship list). That needs
  its own change with a redaction layer.
- **Make `.env.llm` a required file.** Rejected: a fresh or non-AI deployment must not fail to start. Optional
  `env_file` entry + empty `LLM_PROVIDERS` = AI OFF, which is the existing default anyway.

## Consequences

- **Security.** No new port, route, role or ACL: `/llm/*` is unchanged and still service-token-only. The key exists in
  exactly one place (`.env.llm` on the server, gitignored, one service's environment) and is never logged, returned or
  put in an error (`llm_adapter.py:41-46,235-241,250-260`). Egress for the `external` class stays non-personal-only and
  `document_qa` stays local-only, so the most sensitive AI path is unchanged. A missing `.env.llm` cannot break startup.
- **Data.** No model, migration, index or data migration. The adapter stores no content, only counters (`_USAGE`), and
  the smoke tool sends one fixed non-personal prompt and prints only its own answer.
- **Testing.** New `fastapi_core/tests/test_llm_config.py` (offline): the example file is a valid config, it maps no
  school, the key name satisfies the M1 rule, compose wires the file into `fastapi` only and optionally, and the smoke
  tool's mock path exits 0 while printing no key. The existing 22 adapter tests are unchanged.
- **Customization.** A different provider (another reseller, the school's own Ollama) is an edit to `.env.llm` — no code.
  No school name, id, threshold or brand enters code; the only provider name is data in an example file.
- **Operations.** The operator copies `.env.llm.example` to `.env.llm`, fills the key and the model id, restarts
  `fastapi`, runs `python3 tools/llm_smoke.py` on the host (`--mock` first, then `--live`), and only then decides whether
  to map a school. Rollback: empty `LLM_SCHOOL_MAP`, or delete `.env.llm`, and restart — no migration, no data effect.

## Evidence (`CURRENT`, this repository)

- `fastapi_core/llm_adapter.py` (261 lines): config shape `:11-15`, classes `:30-33`, key-name rule `:36-37`,
  validation `:60-78`, loading/mapping `:81-111`, outbound filter `:114-154`, caps `:157-182`, transport without
  redirects or environment proxies `:189-207`, `complete()` `:225-261`.
- `fastapi_core/main.py`: `/llm/status/` `:188-196`, `/llm/complete/` `:199-209` (staff roles `:185`, 200 KB body cap).
- `django_core/docqa/services.py:105-123` (local-only gate), `django_core/schools/ai_guard.py:26-43` (licensed caps).
- `docker-compose.yml:133-155` (fastapi: no port, no `.env`), `.gitignore:5-7` (`.env.*` ignored, examples kept).
- `NOT VERIFIED`: GapGPT's real base URL, model ids, retention, residency and terms; one live call, its latency and cost.

## Supersedes / superseded by

Supersedes the DEFERRED reservation "0008 | LLM provider & data egress" in `docs/adr/README.md` (no file existed before
this one). Not superseded. ADR-0007 (RAG architecture) remains DEFERRED and is unaffected: this decision covers the
provider adapter and its egress, not retrieval over documents.

