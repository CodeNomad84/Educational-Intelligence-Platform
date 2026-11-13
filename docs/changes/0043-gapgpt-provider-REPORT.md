# Change 0043 — GapGPT provider integration (S1). REPORT

Branch `work/0043-gapgpt-provider` (from `phase-1/boot-security`). Level **L3** (new ADR + an operator-facing config
surface + a tool; no change to `students/access.py`, entitlements, audit rules, tenancy or decision 62).
Owner approved **S1** and answered **D1–D6** on 2026-11-13 (`0043-gapgpt-provider-PROPOSAL.md` §15). **S2, S3, S4 stay
`DEFERRED`**: no cloud LLM is used for any live school document QA, and no school is mapped to any provider.

## What S1 shipped (`CURRENT`)

| File | Change |
|---|---|
| `docs/adr/0008-llm-provider-and-egress.md` | **NEW**, Status **PROPOSED**: provider classes, egress policy (decision 2), the seven decisions, D1–D6 record |
| `.env.llm.example` | **NEW**, committed: placeholders only, `LLM_KEY_GAPGPT=` empty, `LLM_SCHOOL_MAP={}`, `LLM_DAILY_CAP=100` |
| `.gitignore` | `!.env.llm.example` exception; `.env.*` still blocks `.env.llm` |
| `docker-compose.yml` | one **optional** `env_file` entry for `fastapi` only — `path: .env.llm`, `required: false` |
| `tools/llm_smoke.py` | **NEW**: `--mock` (default, fake transport, no key, nothing sent) / `--live` (needs the key, one fixed non-personal prompt); `--env-file`, `--provider`, `--purpose` |
| `fastapi_core/tests/test_llm_config.py` | **NEW**, 20 offline tests |
| `docs/AI_GOVERNANCE.md` | operator section (the variables, the order of operations, the refusal rules); corrected a wrong "Django side not implemented" claim |
| `docs/DEPLOYMENT.md` | §3c: file, apply, rollback, `NOT VERIFIED` list |
| `docs/DECISIONS_BY_CODE.md` | row **68** (D1–D6) |
| `docs/adr/README.md`, `docs/CHANGE_GUIDE.md`, `docs/TESTING.md`, `.env.example`, `deploy/profiles/*.env.example` | index, sync line, test counts, pointer to `.env.llm` |

Not touched: `fastapi_core/llm_adapter.py`, `fastapi_core/main.py`, `django_core/docqa/*`,
`django_core/schools/ai_guard.py`, `django_core/students/access.py`, migrations. No new dependency, no new port, no new
mount, no schema change.

## Two deviations from the owner's literal wording (recorded, not silent)

1. **Key variable name is `LLM_KEY_GAPGPT`, not `GAPGPT_API_KEY`.** `llm_adapter.py:36` only accepts `LLM_KEY_*` names
   (independent review M1 — a key must never be reachable through a Django/secret-looking name). Changing that regex is
   L3 and would break every existing key, so the key name follows the adapter; D6's intent (one dedicated key per
   provider) is met.
2. **There is no separate `GAPGPT_BASE_URL`.** Base URL and model live inside the `LLM_PROVIDERS` JSON
   (`llm_adapter.py:60-78` validates the URL, defaults the model). A second variable would be a second source of truth
   that could silently disagree with the JSON — the failure mode is "the smoke test says OK while production calls
   somewhere else". D6's intent (configurable endpoint, `gpt-4o-mini` default) is met and tested.

## Decisions D1–D6 as implemented

- **D1 = A.** `LLM_SCHOOL_MAP={}` in the template; `test_the_example_maps_no_school` asserts that schools 0, 1 and 2 get
  `None`, and the smoke tool asserts the same for a school id that cannot exist. AI is OFF for every school after this
  change, even if an operator drops a real key into `.env.llm` and forgets the map.
- **D2.** No student PII, no student record and no cumulative record leaves the platform. The adapter's
  `external` class accepts only `policy_document`, `curriculum_text`, `question_draft` and `pedagogy`
  (`llm_adapter.py:32`), and it refuses a message that looks like a phone number or national id; `local` may additionally
  take `school_data_summary` and `document_qa`; `counseling` is refused for both. The smoke tool proves all of that
  without a key.
- **D3.** `.env.llm.example` committed (placeholders, empty key value), `.env.llm` gitignored, injected into `fastapi`
  only and **optionally**. `required: false` is deliberate: an existing deployment without the file must keep starting,
  and `docker compose config --quiet` was run with no `.env.llm` on disk to prove it.
- **D4.** Decision 62 unchanged: `document_qa`/`school_data_summary` stay `local`-only. Nothing in `docqa/` was edited.
  A test and the tool both show `document_qa -> purpose_refused` for the `external` class, so an operator who maps a
  school to GapGPT still cannot route a document question to it.
- **D5.** `tools/llm_smoke.py`: `--mock` by default, works offline with no key, prints fixed codes/counts and a preview of
  its own answer only; `--live` requires the key and sends one fixed non-personal Persian prompt. Exit codes 0/1/2
  (pass / check failed / configuration), and a self-check that fails the run if a key ever appears in its output.
- **D6.** Endpoint `https://api.gapgpt.app/v1` (placeholder, `NOT VERIFIED`), model `gpt-4o-mini` (placeholder,
  `NOT VERIFIED`), defensive caps `max_tokens 600`, `timeout 30`, `LLM_DAILY_CAP=100` per school per UTC day, on top of
  the licensed Django caps (`School.ai_daily_cap` / `ai_monthly_cap` in `schools/ai_guard.py`).

## Evidence (real runs, this branch)

| Check | Command | Result |
|---|---|---|
| New tests, host | `cd fastapi_core && python -m unittest tests.test_llm_config` | `Ran 20 tests ... OK` |
| FastAPI suite, container | `docker compose exec -T fastapi python -m unittest discover -s tests -t .` | `Ran 99 tests ... OK (skipped=32)` — 12 pre-existing exposure skips + 20 new ones, because the image mounts only `fastapi_core/` at `/app` |
| Smoke, offline | `python3 tools/llm_smoke.py --mock --env-file .env.llm.example` | `RESULT  OK — exit 0`, 17 PASS, `this check sent no student data` |
| Smoke, no config | `python3 tools/llm_smoke.py --mock` (empty environment) | `FAIL no provider configured` / `exit 2` |
| Smoke, live w/o key | `python3 tools/llm_smoke.py --live` | `exit 2` (no provider); with the example file: `needs a key` / `exit 2` |
| Compose validity | `docker compose config --quiet` (no `.env.llm` present) | `exit 0` |
| Ignore rules | `git check-ignore -v .env.llm.example .env.llm` | template not ignored; `.env.llm` matched by `.gitignore:6:.env.*` |
| Local class keeps `document_qa` | `LLM_PROVIDERS='{"ollama": {... "class": "local" ...}}' python3 tools/llm_smoke.py --mock` | `document_qa -> ok`, `school_data_summary -> ok` (decision 62 is about the external class only) |
| An `external` provider over plain HTTP is refused | same tool with `"base_url": "http://insecure.example/v1"` | `LLM_PROVIDERS is not valid configuration (bad_config)`, `exit 2` |

Full Django suite (`scripts/run_tests.sh sqlite`, output in `/tmp/suite_sqlite.log`):
`test_sqlite` → `Ran 1635 tests in 1015.327s` / `OK (skipped=11)`; `demo_intel` → `Ran 62 tests in 187.579s` / `OK`.

## Residual risks / `NOT VERIFIED`

- **GapGPT's real API.** Base URL, model ids, OpenAI-compatibility details, retention, residency, sub-processors and
  terms are `NOT VERIFIED`. The values in `.env.llm.example` are placeholders and are labelled as such in the file. No
  live call was made (no key was available), so the `--live` path is implemented but `NOT VERIFIED` end to end.
- **`LLM_DAILY_CAP` is per process, in memory.** With one `fastapi` worker it behaves; with several workers each gets its
  own counter, so the effective ceiling multiplies. The licensed cap that matters stays in Django `ai_guard`, which is
  why this one is described as defence in depth, not as the limit. Making it shared needs Redis — deliberately out of S1.
- **The PII tripwire is a heuristic** (digit-run patterns). It catches the synthetic cases in the tests and the obvious
  real ones, not a reworded record. The structural protection is the purpose whitelist plus D4's local-only document QA.
- **The repository root is invisible in the image run**, so the 20 new tests skip there (same reason `test_exposure.py`
  already skips 12). They run on the host and in the CI `fastapi` job, which checks out the repository root.
- **Copying a key into `.env.llm` is not detected** by any test — deliberately, since the file is the operator's. The
  protection is that no school is mapped and that `document_qa` cannot be routed externally.

## What S2–S4 would still need (`DEFERRED`, not started)

S2: a written retention/no-training record for the provider, then one school mapped and observed. S3: any document-QA
use — blocked until an anonymisation/redaction layer is architected and approved (it would reopen decision 62, i.e. L3).
S4: a per-school provider setting in the product (Django UI + audit + licensed caps per provider). None of these is
implied by S1; each needs its own proposal.

**Status: S1 implemented and verified as above. S2–S4 `DEFERRED`. Nothing pushed, nothing merged, `main` untouched.**


