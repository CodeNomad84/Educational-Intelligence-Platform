# 0043 — Connecting GapGPT as an `external` AI provider (CHANGE PROPOSAL — nothing is implemented)

Written 2026-11-13. **Level: L3** (AI provider + data-egress architecture; it activates the DEFERRED **ADR-0008**
"LLM provider & data egress"; it can weaken a privacy rule that a previous owner decision fixed). Per
`docs/CHANGE_PROCESS.md`: **proposal → ADR → explicit owner approval** before the first line of code.
**Status: PROPOSED.** Nothing below exists: no provider was configured, no key was created, no call was made, no file
outside this proposal was touched.
Truth labels: `CURRENT` (verified in this working tree, evidence given as `file:line`) · `TARGET` · `PROPOSED` ·
`DECISION REQUIRED` · `NOT VERIFIED` · `DEFERRED`.

Read with: `fastapi_core/llm_adapter.py` (the whole file, 261 lines) · `fastapi_core/main.py` §`/llm/*` ·
`django_core/docqa/{services,models}.py` · `docs/AI_GOVERNANCE.md` §"Provider adapter" ·
`docs/adr/README.md` (ADR-0008 = DEFERRED) · `docs/changes/0028-p3-p8-decision-pack-PROPOSAL.md` OW-6 ·
`docs/DECISIONS_BY_CODE.md` decisions 56, 57, 59, 62, 63.

---

## 1. Requirement

The owner asked on 2026-11-13, in one line, with no further detail:

> «پروپوزال Change 0043 برای اتصال GapGPT را باز کن» (open Change 0043 for connecting GapGPT).

That names a **provider**, not a behaviour, so it has four readings. This proposal does **not** guess which one is
meant — it prices all four and asks (**D1**):

| # | Reading | Size | What it needs |
|---|---|---|---|
| **A** | **Proof of connectivity**: the operator configures GapGPT and one call succeeds, no school is mapped, no user-facing feature changes | smallest | env only + a repeatable, key-free test/smoke path (nothing in the repo shows how today — §2.5) |
| **B** | **GapGPT for the document-QA page** (the only Django→AI path that exists) | L3 + privacy decision | it **contradicts decision 62**: `document_qa` is LOCAL-class-only, `CURRENT` (§2.3) |
| **C** | **Per-school provider selection in the product** (Django setting/DB column + admin, instead of the env map) | L3, new model + migration | new model, admin, audit, migration; not needed for a pilot with one provider |
| **D** | **GapGPT-specific code** (SDK/endpoint branch) | rejected | contradicts decision 56 and `llm_adapter.py:1-4` (provider-agnostic, stdlib only) |

`CURRENT` context that makes this smaller than it sounds: GapGPT is already **named in the repo three times as a
configuration example**, not as a feature — `fastapi_core/llm_adapter.py:2` ("resellers (e.g. GapGPT)"),
`docs/DECISIONS_BY_CODE.md:63` (decision 56: "resellers (GapGPT-style)"), and
`docs/changes/0028-p3-p8-decision-pack-PROPOSAL.md:17` (OW-6). So "connecting GapGPT" is a **policy + configuration
+ documentation** job, not a new adapter. The only code questions are the smoke test (A) and, if D1 answers B, the
class rule for `document_qa`.

**Recommendation: A now, B/C `DEFERRED` until the owner answers §14 D2–D5.** Reasons in §14.

## 2. Current behaviour (`CURRENT`, with evidence)

### 2.1 The adapter already speaks GapGPT's protocol

| Fact | Evidence |
|---|---|
| One OpenAI-compatible client: `POST {base_url}/chat/completions`, stdlib `urllib`, no vendor SDK, no dependency. | `fastapi_core/llm_adapter.py:1-4,199-206,245` |
| Providers are pure configuration from the environment: `LLM_PROVIDERS` (JSON), `LLM_SCHOOL_MAP` (school → provider), `LLM_DAILY_CAP`. | `llm_adapter.py:11-15,81-92,95-111` |
| Two classes only: `external` (hosted, data leaves) and `local`. **Both OFF** unless an operator configures a provider *and* maps a school. | `llm_adapter.py:30,95-111`; a school absent from the map gets `None` → `403` at the route (`main.py:209`) |
| `external` must be **HTTPS**, must carry an `api_key_env`, and that variable name must match `LLM_KEY_[A-Z0-9_]{1,56}` and may not contain `SERVICE_JWT`, `SECRET`, `PASSWORD`, `DATABASE`, `POSTGRES`, `DJANGO`, `TOKEN_SIGNING`. | `llm_adapter.py:36-37,64,70-74` |
| Transport hardening already in place: **no redirects**, **no environment proxies**, timeout capped at 60 s, `max_tokens` capped at 4000, `temperature` fixed at 0.2, at most 3 calls in flight per school. | `llm_adapter.py:75-77,192-207,242-243` |
| A non-200 answer becomes the fixed code `upstream_error` (`502`); provider text is never returned to the caller or logged. | `llm_adapter.py:250-259`; `main.py:181-182` |
| `/llm/status/` discloses only `{enabled, class}` — never a URL, a model id or a key. | `main.py:188-196` |
| `/llm/complete/` accepts only staff roles (`Admin`, `Teacher`, `GradeLead`, `Counselor`), takes the school **from the signed token, never from the body**, and caps the body at 200 KB. | `main.py:185,199-204` |

**Conclusion for D1=A:** GapGPT-style resellers are *already supported by design*; the missing pieces are an
operator-facing place to put the config (§2.5) and a way to prove it works without a real key in a test suite (§10).

### 2.2 What the `external` class refuses today (the crux of reading B)

| Fact | Evidence |
|---|---|
| Allowed purposes for `external`: `policy_document`, `curriculum_text`, `question_draft`, `pedagogy`. | `llm_adapter.py:32` |
| `local` adds **`school_data_summary`** and **`document_qa`**. | `llm_adapter.py:33` |
| Therefore an `external` provider is refused (`purpose_refused`, 422) for `document_qa` and `school_data_summary`. | `llm_adapter.py:229-231`; `main.py:181` |
| All `external` messages pass the outbound PII tripwire (10+ digit runs, mobile numbers, e-mail, roster names) on every message **and** on the joined conversation. | `llm_adapter.py:134-141,233-234` |
| The tripwire is documented as **best-effort, not a guarantee** — it cannot catch a first name, digits in words, base64, transliteration, `(at)`, a name missing from the roster, or an indirect description; it cannot detect counseling content. | `llm_adapter.py:114-118`; `docs/AI_GOVERNANCE.md:38`; decision 59 (`DECISIONS_BY_CODE.md:66`) |

### 2.3 The only Django → FastAPI AI path is document-QA, and it is deliberately `local`-only

| Fact | Evidence |
|---|---|
| `_local_provider_active()` calls `GET /llm/status/` and returns `True` **only** if `class == "local"`. | `django_core/docqa/services.py:105-112` |
| `_complete()` posts `purpose: "document_qa"` to `/llm/complete/`. | `django_core/docqa/services.py:114-123` |
| Owner decision 62: `document_qa` exists **for the local class only** ("the external class refuses it"); if the provider is off, not local, capped or failed, the page degrades to **plain document search with excerpts**. | `docs/DECISIONS_BY_CODE.md:69` |
| Per-school switch, OFF by default and audited: `AssistantSettings.ai_enabled` (SchoolAdmin). | `django_core/docqa/models.py:35-40` |

**Consequence (`CURRENT`):** mapping a school to GapGPT does **not** switch the AI answer page on — it keeps it off,
by design, and the page falls back to excerpts. Reading B is therefore a **rule change** (decision 62), not a config
change, and must be treated as such.

### 2.4 Caps already exist on both sides

| Fact | Evidence |
|---|---|
| Django licensed caps: `ai_guard.consume(school, 'advisor_ai')` / `'tutor_ai'`, per day and per month; `AICapReached` is raised **before** anything is sent. | `django_core/schools/ai_guard.py:1-6,31-43` |
| Defaults `AI_DEFAULT_DAILY_CAP=100`, `AI_DEFAULT_MONTHLY_CAP=1000`, overridable per school. | `django_core/config/settings/base.py:119-120`; `schools/ai_guard.py:26-28` |
| FastAPI defence in depth: `LLM_DAILY_CAP` (default 200 per UTC day) held in memory — it multiplies across workers and resets on restart, and is documented as defence in depth only. | `llm_adapter.py:15`; decision 59 L4 (`DECISIONS_BY_CODE.md:66`) |
| `uvicorn --workers 2` → the in-memory cap and the 3-in-flight gate are **per worker**, i.e. effectively doubled. | `docker-compose.yml` (`fastapi:` → `command:`) |

### 2.5 The gap: **nowhere in the repo to configure a provider, and nothing that proves it works**

| Fact | Evidence |
|---|---|
| The `fastapi` service deliberately does **not** read `.env` — only `.env.service` (service token) and `.env.fastapi` (DB role). | `docker-compose.yml` §`fastapi:` (`env_file:` plus the explicit comment "Deliberately NOT env_file: .env") |
| `LLM_PROVIDERS` / `LLM_SCHOOL_MAP` / `LLM_DAILY_CAP` / `LLM_KEY_*` appear in **no** env example, profile or compose file. | `grep -n LLM .env.example` → none (the file is 16 lines); `grep -rn LLM deploy/profiles/*.example` → only a warning comment at `deploy/profiles/shared-iranian-server.env.example:18` |
| `.gitignore:5-7` ignores `.env` and `.env.*` but allows `.env.example` → a new provider file is gitignored by default (correct), and its example must be added by hand. | `.gitignore:5-7` |
| `AI_GOVERNANCE.md:31-35` shows JSON *shapes* for a provider but names **no file** an operator can put them in — for a compose deployment that is currently unusable advice. | `docs/AI_GOVERNANCE.md:29-38` |
| `/llm/status/` is the only health signal and it needs a signed staff token, while FastAPI publishes no port → an operator cannot smoke-test it from outside the compose network. | `fastapi_core/main.py:188-196`; `docker-compose.yml` §`fastapi:` (no published port) |
| Every test uses a mock transport; no real provider was ever called. | `fastapi_core/tests/test_llm_adapter.py`; `docs/changes/0032-p7-exit-REPORT.md:3`; `docs/AI_GOVERNANCE.md:36` |

### 2.6 `DOCUMENTATION / CODE CONFLICT` (reported, not silently resolved — `CLAUDE.md` §4)

`docs/AI_GOVERNANCE.md:36` states: *"`NOT YET IMPLEMENTED`: the Django side (UI, per-school provider setting, the
licensed call caps and audit of AI calls)"*. The code contradicts the last two clauses: the licensed caps exist
(`schools/ai_guard.py`), the AI call path exists (`django_core/docqa/services.py:105-123`) and it is audited
(`audit.DOC_ASK`, decision 62). What is genuinely missing is a **per-school provider setting** and a **UI** — a
narrower statement than that sentence makes. Marked **`DOCUMENTATION / CODE CONFLICT`**; to be corrected in §11 step 9
after approval, and **not** fixed by this proposal (this file changes no other document).

### 2.7 GapGPT itself: `NOT VERIFIED`

`gapgpt.app` returned only a JavaScript application shell (no API documentation) and `docs.gapgpt.app` was
unreachable from this environment. So **none** of the following is known from this repository or from a source this
agent could read — all of it must come from the owner or the provider's current documentation:

- the exact `base_url` (does it end in `/v1`, and does it answer `POST {base}/chat/completions`?),
- the model ids on offer today, and whether they are pinned aliases or moving pointers,
- whether it resells OpenAI / Anthropic / Google models or serves domestic models only,
- streaming/retry support (the adapter sends **non-streaming** requests only, `llm_adapter.py:242`),
- **prompt retention, logging and training use**, data residency and jurisdiction,
- billing currency and terms (Rial);
- the provider's terms of service on school data and on users under 18.

Nothing in this proposal depends on guessing these; §10 is written so that the smoke test fails loudly and safely if
the provider's shape differs.

## 3. Desired behaviour (`TARGET`)

**S1 — configuration + proof (reading A); the part I recommend approving now.**
1. A documented, gitignored home for provider config that the `fastapi` service **actually reads** (an
   `.env.fastapi.example` block, or a dedicated `.env.llm` added to `env_file:` — **D3**), holding `LLM_PROVIDERS`,
   `LLM_SCHOOL_MAP` (empty) and `LLM_DAILY_CAP`.
2. Placeholders only in the committed example (decision 66 style): `LLM_KEY_GAPGPT=<set on the server file only>`.
3. **No school is mapped in S1.** After S1 every user sees exactly what they see today: AI off.
4. A repeatable **manual** smoke path that proves connectivity — one command, run by the owner, which
   (a) refuses to run unless `LLM_KEY_GAPGPT` is set, (b) sends one fixed non-personal Persian prompt with purpose
   `policy_document`, (c) prints **only** `ok|failed`, the provider class, the model id, the HTTP status and token
   usage — never the key, never the base URL, never the answer text, (d) exits non-zero on failure.
5. A **config test** (mock transport, no key) proving that a GapGPT-shaped entry parses and that a malformed entry is
   refused with `bad_config`.

**S2 — GapGPT for one real school (`DEFERRED`; needs D2).** Map exactly one school, `class: external`. The AI answer
page stays **off** (decision 62) and shows its existing "not local" notice; nothing in the UI changes.

**S3 — reading B: `document_qa` over GapGPT (`DEFERRED`; needs D2 + D4).** Only with an explicit owner decision that
replaces decision 62 for the external class, plus the privacy/legal answer in D4. This is the only part that
*loosens* a rule; the recommendation is **not** to do it in this change.

**S4 — reading C: per-school provider in the product (`DEFERRED`).** Model + migration + admin + audit; only when a
second provider (e.g. a school's own Ollama) becomes a product requirement.

**S5 — nothing else.** Out of scope: streaming, embeddings/RAG, per-user keys, billing, a prompt library, a prompt UI,
a chatbot.

## 4. Affected modules (by path; `MODULE_MAP` is derived and loses to code)

| Module | S1 | S3 (deferred) | S4 (deferred) |
|---|---|---|---|
| `fastapi_core/llm_adapter.py` | none (config only); the smoke helper may live beside it | purpose whitelist for `document_qa` (one line + docs) | none |
| `fastapi_core/main.py` (`/llm/*`) | none | none | none |
| `fastapi_core/tests/test_llm_adapter.py` | + config-shape cases | + `document_qa` accepted for external (only if approved) | — |
| `django_core/docqa/services.py` | none | drop the `class == "local"` gate | none |
| `django_core/docqa/tests.py` | + "external class degrades to search" regression | — | — |
| `django_core/schools/ai_guard.py` | none | none | none |
| `docker-compose.yml` | possibly one `env_file:` line (D3) | — | — |
| `.env.example` / `.env.fastapi.example` / `deploy/profiles/*` | + placeholder block | — | — |
| `docs/AI_GOVERNANCE.md`, `docs/DEPLOYMENT.md` | + operator section; fix the §2.6 conflict | update the class rule | + per-school setting |
| `docs/adr/0008-llm-provider-and-egress.md` | **DEFERRED → PROPOSED** (owner accepts) | amend | amend |

## 5. Data impact

- **S1/S2: no model, no migration, no data.** The database stays byte-identical.
- **S4 (deferred)**: a `provider`/`model` column on the per-school AI settings (or a new `SchoolLLMSettings`) plus a
  migration, a SchoolAdmin edit path and an audit event. Not proposed now: with one provider, `LLM_SCHOOL_MAP` does
  the job with no schema risk (decision 56).
- **No provenance/layer change**: nothing GapGPT returns is written to the database. `document_qa` answers are shown,
  the audit row carries counts and codes only (decisions 62, 63).

## 6. API impact

- **None.** S1/S2 change no endpoint, no schema, no status code. `/llm/status/` keeps returning `{enabled, class}`
  only — adding `provider` or `model` there would leak operator configuration to staff clients and is **not**
  proposed.
- The smoke path of §3.4 is a **CLI** helper run inside the container
  (`docker compose exec fastapi …` — naming decided with D5), **not** an HTTP route: no new surface, no port, nothing
  a browser can reach. `fastapi_core/tests/test_exposure.py` keeps its invariant (no published port, no nginx proxy
  to FastAPI).
- Reason codes already returned by `/llm/complete/` cover every failure the smoke test can hit: `not_configured` 503,
  `bad_config` 503, `purpose_refused`/`pii_refused` 422, `cap_reached`/`busy` 429, `upstream_error` 502
  (`main.py:181-182`).

## 7. Frontend impact

- **None.** No template, no template tag, no JS. The document-QA page already renders three states (AI answer, excerpt
  search, nothing) and already shows the "provider is not local" notice when the class is not `local` (decision 62;
  `django_core/docqa/services.py:105-112`). S1 leaves every page exactly as it is today.
- If S3 is ever approved, the only frontend consequence is that the page shows an AI answer where it now shows
  excerpts; that wording belongs to that change, not this one.

## 8. AI impact (`docs/AI_GOVERNANCE.md` is the governing text)

| Aspect | Position in S1 | Position if S3 is later approved |
|---|---|---|
| Provider class | `external` — data leaves the platform | unchanged |
| Purposes | only the 4 external ones: `policy_document`, `curriculum_text`, `question_draft`, `pedagogy` | would add `document_qa` (needs D4) |
| Student PII | never; tripwire on every message and on the joined conversation (decision 59) | unchanged |
| Counseling | never a purpose for either class | unchanged |
| School data | the external class cannot ask for `school_data_summary` | unchanged |
| Prompt/answer logging | not logged; only `llm_call` with school, class, purpose, status and token counts (`llm_adapter.py:260`) | unchanged |
| Model pinning | the model id comes from operator config in `LLM_PROVIDERS`; changing it is a config change that must be recorded in `DECISIONS_BY_CODE.md` (A-04 class of risk) | unchanged |
| Advisory label | returned on every answer (`LABEL_FA`, `llm_adapter.py:31`) | unchanged |
| Third parties | **GapGPT is a reseller**: platform data may pass through the reseller *in addition to* the model vendor. That party is a new sub-processor, covered by no existing decision. | same, now over school documents |

**Open governance question (`DECISION REQUIRED`, D4):** the hard rule "no student PII to external LLMs" is satisfied
by the purpose whitelist plus Django building non-personal prompts. It is **not** satisfied by the tripwire alone
(`docs/AI_GOVERNANCE.md:38`). Any use of GapGPT therefore rests on a written statement about **what the reseller may
retain** — which does not exist today (`NOT VERIFIED`).

## 9. Security impact

| Topic | Rule for this change | Evidence / basis |
|---|---|---|
| Key handling | the key lives **only** in `LLM_KEY_GAPGPT` on the server's gitignored env file; never in the repo, compose, an image, a log line, an error string or a `/llm/*` response | `llm_adapter.py:36-37,70-74,235-241`; `main.py:188-196` |
| Key rotation | replace the value in the env file and restart `fastapi`; no code change, no migration | decision 56 |
| Reachability | `/llm/complete/` stays reachable only from Django with the signed service token; the smoke helper runs *inside* the container; no port is published | `docker-compose.yml` §`fastapi:`; decision 59 L5 |
| Egress | the adapter ignores environment proxies and refuses redirects, so the host must reach the confirmed `base_url` **directly over HTTPS on 443**; on an Iranian shared server this must be verified against the ISP's egress rules | `llm_adapter.py:192-207` |
| Caps | licensed caps stay in Django (`ai_guard`); the FastAPI cap stays defence in depth | `ai_guard.py:31-43` |
| Audit | `doc_ask` keeps recording counts and codes only, never the question or the answer | decisions 62, 63 |
| Access rules | **unchanged** — no `visible_*`, no role, no school scope and no token claim is touched by S1 | proposal touches no `students/access.py` |
| Contract / legal | terms on retention, on under-18 users and on educational data are `NOT VERIFIED`; a reseller can log prompts. Until D4 is answered, S1 must not carry content the school would not publish | §2.7 |
| Secrets in tests | no key is ever added to a test; the config tests use the mock transport that already exists | `fastapi_core/tests/test_llm_adapter.py` |

**One explicit non-goal:** this change does **not** enable any route that sends student names, national ids, grades,
attendance or counseling notes to GapGPT. No current purpose allows it, and the proposal keeps that lock as it is.

## 10. Testing strategy

**Automated (no key, no network — the existing mock transport):**

1. `fastapi_core/tests/test_llm_adapter.py`
   - a GapGPT-shaped entry (`class: external`, `api_key_env: LLM_KEY_GAPGPT`) parses; `provider_for_school` returns it
     for the mapped school and `None` for an unmapped one;
   - the same entry with `http://` → `bad_config`; with `api_key_env: DJANGO_SECRET_KEY` → `bad_config`; with
     `timeout: 120` → `bad_config` (keeps the "≤ 60 s" rule);
   - `document_qa` and `school_data_summary` still raise `purpose_refused` for the `external` class;
   - a message with a national id / mobile number / roster name still raises `pii_refused` **before** any transport
     call;
   - a mocked 401/500 from the provider becomes `upstream_error`, and the log line carries no key, no URL, no prompt.
2. `django_core/docqa/tests.py` — with the school mapped to an `external` provider, `ask()` returns `mode: "search"`
   (excerpts + notice, **no** `/llm/complete/` call). This locks decision 62 so a later change cannot flip the class
   rule silently.
3. `scripts/run_tests.sh` needs **no** change: same modules, same runners.

**Manual, owner-run, once (exit criteria for S1):**

4. Put the real provider entry and key in the server env file (**never** in this repo), restart `fastapi`, run the
   smoke helper. Expected: `ok`, class `external`, the confirmed model id, HTTP 200, non-zero token usage. Failures map
   to the documented codes (`not_configured`, `bad_config`, `upstream_error`), which tells the operator *which* of the
   §2.7 unknowns is wrong without printing anything secret.
5. Confirm the negative side: with `LLM_SCHOOL_MAP` empty, `/llm/status/` reports `enabled: false` and the docqa page
   offers plain search — the "AI off" proof for the pilot.

**Not tested, by design:** the real provider's answer quality, latency and cost. Those are owner observations
(`NOT VERIFIED`), recorded in the Change Report.

## 11. Documentation impact (step 9 of the workflow; only what the change actually touches)

| Document | Change |
|---|---|
| `docs/AI_GOVERNANCE.md` | add a concrete **operator** block for S1 (which file, which variables, placeholder-only example, how to run the smoke helper); **fix the §2.6 conflict** (the "NOT YET IMPLEMENTED" sentence) as a reported correction, not a silent one |
| `docs/DEPLOYMENT.md` | short "configuring an external AI provider" subsection: env file, restart, smoke test, rollback (remove the vars + restart) |
| `deploy/profiles/shared-iranian-server.env.example` (+ dedicated profile) | placeholder block, no values, keeping the existing warning at line 18 |
| `.env.example` (or new `.env.fastapi.example`) | pointer block only, plus the note that the key never goes in `.env` (that file is for Django) |
| `docs/adr/0008-llm-provider-and-egress.md` | **created** at this change: DEFERRED → PROPOSED, recording the reseller/sub-processor position, retention unknown, and the class rule for `document_qa` |
| `docs/adr/README.md` | row 0008 updated; if approved, `ACCEPTED <date>` |
| `docs/DECISIONS_BY_CODE.md` | one new row (next free number is **68**) recording D1–D5's answers as decisions |
| `docs/manuals/*` | only if S3 is approved (the docqa page's behaviour changes); **nothing** for S1 |
| `docs/CHANGE_GUIDE.md` | bump `Verified-at` for the touched files |
| `docs/changes/0043-gapgpt-provider-REPORT.md` | written at step 10, with the real test tails and the smoke result |

`MODULE_MAP` / `SYSTEM_MAP`: one line each for the new env file if D3 adds a service-level file; otherwise no change.

## 12. Customization impact (`docs/CUSTOMIZATION.md`)

- Everything GapGPT-specific is **configuration**: `base_url`, `model`, `api_key_env`, `timeout`, `max_tokens`,
  per-school mapping. No school name, id, threshold or brand is hard-coded — the only literal that could appear is the
  *provider name* in an example file, which is data, not code.
- A second provider (another reseller, or a school's own Ollama) needs **no code**: another key in `LLM_PROVIDERS` and
  another entry in `LLM_SCHOOL_MAP` (decision 56). That is the acceptance test for this design, and S1 must not
  weaken it.
- Rejected alternative D (a GapGPT-specific code path) would break this property, which is another reason to refuse it.

## 13. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The provider's `base_url`/path differs from `{base}/chat/completions` | S1 smoke test fails with `upstream_error` | §2.7 lists the exact unknowns; the owner confirms from the provider's docs before S1; the failure code tells us it is the shape, not the key |
| A reseller retains prompts (retention unknown) | privacy / reputational | D4 before any school is mapped; S1 uses one fixed non-personal prompt; no student data ever |
| Someone maps a school expecting the docqa page to answer | expectation failure, support load | §2.3 documented; the page's notice already says the provider is not local; S3 stays a separate approved change |
| Key leaks through logs/errors | credential compromise | adapter never logs or returns keys (`llm_adapter.py:235-260`); smoke helper prints codes + counts only; key only in a gitignored file, `.gitignore:5-7` |
| Key accidentally written into `.env` (Django's file) | FastAPI would not see it; Django would hold a foreign secret | D3 decides the file; the example says explicitly which file, and `.env.example` says the key does not belong in `.env` |
| Egress blocked by the Iranian host/ISP, or a proxy is expected | provider unreachable (`upstream_error`) | adapter deliberately ignores env proxies (`llm_adapter.py:196`); verify egress on the target server as part of S1's manual step |
| Model id silently changes (alias drift) | answer quality/cost change without a trace | model id is in config; a change must be recorded as a decision (A-04 class of risk) |
| In-memory cap doubles with 2 workers | more calls than the operator expects | licensed caps stay in Django (`ai_guard`), where the real limit is enforced |
| Cost in Rial without a budget | financial | `max_tokens ≤ 4000` per call, `LLM_DAILY_CAP`, Django caps; the smoke test reports token usage so the owner can price one call before mapping a school |

## 14. Recommendation, alternatives, ADR, decisions

**Recommendation: approve S1 only** — configuration + operator documentation + a key-free smoke path + automated
config tests — with **no school mapped**, so the platform's behaviour is unchanged and nothing can reach GapGPT from a
user action. Keep S2/S3/S4 `DEFERRED` until D2 and D4 are answered in writing, and until ADR-0008 exists.

Reasons: (1) S1 is the only part that is reversible by deleting two environment variables; (2) it closes a real
`CURRENT` gap — today **nobody can configure or verify a provider from this repository** (§2.5); (3) S2 changes
nothing for users while exposing the platform to a reseller whose retention terms are `NOT VERIFIED`; (4) S3 requires
reversing decision 62, which is a privacy rule and should never be reversed as a side effect of "connecting a
provider".

**Scope conflict to note (owner-owned file, read only):** `docs/pilot/QUEUE.md:2` fixes the pilot-ready scope as
"base + mission + exams; advisor_ai, tutor_ai, **docqa** and Counselor OFF" with AI off. S2/S3 therefore cannot be
scheduled inside the pilot scope without the owner editing that line. This proposal does not touch `QUEUE.md`.

**Alternatives considered**

1. **Do nothing until a local model is chosen** — consistent with decision 62, but leaves the operator unable to test
   *any* provider path, including a future Ollama one. Rejected as the whole answer; S1 is worth doing regardless of
   which provider is finally used.
2. **Point `LLM_SCHOOL_MAP` at GapGPT for a demo school and call the page "AI-ready"** — misrepresents state
   (the page would show excerpts, not answers) and breaks the pilot scope line. Rejected.
3. **Enable `document_qa` for the external class silently "because it is just school documents"** — reverses decision
   62 without an owner decision. Rejected (that is exactly what S3 asks for explicitly instead).
4. **Add a GapGPT SDK / dedicated client** — new dependency, breaks provider-agnosticism, contradicts decision 56 and
   `CLAUDE.md` §3 ("no new framework/service/dependency without an L3 proposal"). Rejected.
5. **Store the key in the Django admin database** — a secret in the app DB, outside the `LLM_KEY_*` rule, visible to
   any future backup. Rejected.

**ADR needed: yes — ADR-0008 "LLM provider & data egress".** It is currently `DEFERRED` and no file exists
(`docs/adr/README.md:17`). This change creates it as **PROPOSED** and records, at minimum: the two provider classes,
the reseller as a sub-processor, retention `NOT VERIFIED`, the purpose whitelist as the real protection (not the
tripwire), and the class rule for `document_qa`. The owner's acceptance of it is the gate for S2/S3.

### `DECISION REQUIRED` (owner)

| # | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Which reading of "connect GapGPT" is intended? | (a) A: proof of connectivity only, no school mapped (b) A+B: also enable document-QA over GapGPT (c) A+C: per-school provider setting in the product (d) A+B+C | **a** now; b/c later as separate changes |
| **D2** | May non-personal content (school policy/curriculum text, drafted questions, pedagogy prompts) leave the platform to GapGPT at all? | (a) yes, only the four `external` purposes (b) no — keep the external class unused until a local/domestic-hosted model is ready (c) yes, but only after a written retention/no-training agreement with the provider | **a** for S1's single smoke prompt; **c** before any school is mapped |
| **D3** | Where does the provider configuration live, given `fastapi` deliberately does not read `.env`? | (a) extend `.env.fastapi` (b) new gitignored `.env.llm` added to `env_file:` (c) compose `environment:` with `${…}` interpolation from `.env` | **b** — matches the existing one-file-per-secret-owner pattern (`.env.service`, `.env.fastapi`, `.env.minio`) and keeps DB credentials apart from AI keys |
| **D4** | Does `document_qa` stay LOCAL-class-only (decision 62)? | (a) yes, unchanged (b) allow it for the external class on attested non-personal documents (c) allow it only under a no-retention agreement | **a** (this proposal) |
| **D5** | Where does the manual smoke helper live? | (a) `fastapi_core/llm_smoke.py`, run with `docker compose exec fastapi python llm_smoke.py` (b) `scripts/` on the host (needs its own network path and the key) (c) a temporary management command | **a** — the module is already mounted at `/app` and the key is already in that container's environment; no new mount, no new port |
| **D6** | Which model id, and what is the monthly budget? | owner supplies the provider's current model id(s) and a Rial ceiling | needed **before** S1's manual step; recorded as a new row in `DECISIONS_BY_CODE.md` (next free number **68**) |

### Explicitly out of scope

Streaming, tool/function calling, embeddings and RAG over documents, a per-user or per-teacher key, billing or
invoicing, a prompt-editing UI, a chat widget, student- or parent-facing AI, counseling data, and **any** change to
`students/access.py`, entitlements, audit rules or school isolation.

**Status: APPROVED for S1 on 2026-11-13** (owner; answers to D1–D6 below). S2, S3 and S4 remain `DEFERRED`. ADR-0008 was
written as `docs/adr/0008-llm-provider-and-egress.md` (PROPOSED) and S1 was implemented on branch
`work/0043-gapgpt-provider`; results, evidence and the two recorded deviations are in
`docs/changes/0043-gapgpt-provider-REPORT.md`.

## 15. Approval record (owner, 2026-11-13)

| # | Answer | Effect on this proposal |
|---|---|---|
| **D1** | **A** — configuration plumbing only; no school mapped | S1 only; S2–S4 stay `DEFERRED`; `LLM_SCHOOL_MAP={}` in the template and a test asserts it |
| **D2** | The four `external` purposes only; **zero** student PII or student records | Unchanged from the adapter's existing rule; stated as ADR-0008 decision 2. The retention/no-training terms must be recorded **before** any school is mapped |
| **D3** | `.env.llm.example` (committed) + `.env.llm` (gitignored); pass to `fastapi` with a no-op default | Implemented as an **optional** `env_file` entry (`required: false`) — a missing file must not stop the service. Django receives nothing |
| **D4** | Decision 62 stays intact; sensitive doc QA stays local-only | No change to `docqa/services.py`; `LLM_KEY_*` only in `fastapi`; the smoke tool asserts `document_qa -> purpose_refused` for an `external` provider |
| **D5** | `tools/llm_smoke.py`, `--mock` by default, live only with a key | Implemented there (this proposal's recommendation (a) is therefore **not** followed; the owner's choice needs no container mount and works with `--env-file .env.llm`) |
| **D6** | OpenAI-compatible endpoint, model `gpt-4o-mini`, defensive caps | Recorded with **two deviations**: the key variable is `LLM_KEY_GAPGPT`, not `GAPGPT_API_KEY` (`llm_adapter.py:36` accepts only `LLM_KEY_*`, review M1); and there is no separate `GAPGPT_BASE_URL` — base URL and model live inside the `LLM_PROVIDERS` JSON, one source of truth. Caps: `max_tokens 600`, `timeout 30`, `LLM_DAILY_CAP=100` |

`NOT VERIFIED` after this change: GapGPT's real base URL, model ids, retention, residency and terms, and the latency/cost of
a live call (no key was available and no call was made). S1 does not enable any school.
