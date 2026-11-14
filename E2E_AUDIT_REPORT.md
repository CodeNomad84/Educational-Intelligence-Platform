# E2E QA / UX audit — Educational-Intelligence-Platform

**Date:** 2026-11-14 · **Branch:** `work/e2e-audit` (from `main` @ `899b305`) · **Change level:** L1 (audit + tests only,
no product code changed) · **Next free change number:** 0044 (the standing rule text says 0039 and is stale).

Truth labels used below: **CURRENT** = observed in a run I made; **TARGET** = what the product should do;
**NOT VERIFIED** = stated but not measured here; **DECISION REQUIRED** = a product/owner call, not a bug fix.

---

## 1. What was audited and how

Two legs, both driven through the real entry points (no internal shortcuts):

| Leg | Entry point | Provider boundary |
|---|---|---|
| Django UI | `django.test.Client` → real URLs, real login form, real templates, real ORM, real `docqa` service | `docqa.services.requests` replaced by a mock (FastAPI is a separate process) |
| FastAPI | `fastapi.testclient.TestClient` → real `main.py` app, real routing/auth/pydantic/status mapping | a **real HTTP server** on `127.0.0.1` speaking the OpenAI-compatible API (`tests/e2e_support.StubProvider`) |

New files (test-only, nothing in `risk/`, `interventions/`, `core/`):

* `django_core/dashboard/test_e2e_user_flow.py` — 39 tests (6 of them `@unittest.expectedFailure`, see §4)
* `fastapi_core/tests/test_e2e_llm_flow.py` — 25 tests (1 `expectedFailure`)
* `fastapi_core/tests/e2e_support.py` — fake heavy modules + the real stub provider

All data is synthetic. `SERVICE_JWT_SECRET` is generated per run (Django) or a random `token_urlsafe(48)` (service).

### 1.1 Commands and raw results (CURRENT)

```
# Django leg (config.settings.test_sqlite, in-memory SQLite)
$ cd django_core && DJANGO_SETTINGS_MODULE=config.settings.test_sqlite \
    .venv/bin/python manage.py test dashboard.test_e2e_user_flow -v 2
Ran 39 tests in 7.552s
OK (expected failures=6)

# FastAPI leg (verified image, source mounted read-only, no network)
$ docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/fastapi_core:/app:ro" -w /app educational-intelligence-platform-fastapi:latest \
    python -m unittest discover -s tests -t . -v
Ran 124 tests in 4.623s
OK (skipped=32, expected failures=1)
```

The FastAPI leg adds 25 tests to the 99 that existed (99 → 124); the 32 skips are pre-existing.

Baselines measured before writing anything (unchanged by this audit): Django `docqa` 24 tests OK in 4.178s;
FastAPI 99 tests OK in 2.852s. `scripts/run_tests.sh sqlite` and `pg` results are in §7.

### 1.2 How to re-run

```
scripts/run_tests.sh sqlite                                     # includes the new Django tests (dashboard.* discovery)
docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/fastapi_core:/app:ro" -w /app educational-intelligence-platform-fastapi:latest \
  python -m unittest discover -s tests -t . -v                  # includes the new FastAPI tests
```

No CI edit was needed: `.github/workflows/ci.yml` already runs `python -m unittest discover -s tests -t .`, and
`scripts/run_tests.sh` already runs `manage.py test students dashboard … docqa`, so both new modules are discovered.

---

## 2. Verdict in one paragraph

The security scaffolding is in good shape and the audited journeys behave correctly at the *authorisation* level:
every role gate, school scoping, prompt scoping, screening, audit-code-only logging and the FastAPI service-token
contract passed (39 + 25 tests). The gaps are in the **product surface**: the one AI feature a school admin actually
clicks (`پیشبینی وضعیت با هوش مصنوعی`) displays a probability 100× too small (F01) and is computed from four invented
numbers (F02) that the page then shows the admin as "the data sent to the AI"; the assistant has no loading state on a
request that can block for 68 s (F06) and charges the daily cap for calls that failed (F05); and three of the four roles
that may use `/assistant/` have no link to it (F11). None of this is a data-leak; all of it damages the pilot.

---

## 3. The journeys that were walked (CURRENT)

### 3.1 Staff journey: login → school home → students → student detail → prediction

| # | Step | Result | Test |
|---|---|---|---|
| 1 | `POST /login/` with a wrong password | 200, form re-rendered, one Persian message, **no session** | `test_01` |
| 2 | `POST /login/` as SchoolAdmin | 302 → `/school/`, session created, target page 200 | `test_02` |
| 3 | `POST /login/` per role | Teacher→`/teacher/`, Counselor→`/counselor/`, GradeLead→`/grade/`, Parent→`/students/` | `test_03` |
| 4 | `POST /login/?next=https://evil.example/` | 302 → `/school/` — the off-site `next` is dropped | `test_04` |
| 5 | `GET /school/` (principal dashboard) | 200, **53 SQL queries**, 55–84 ms server time | `test_05` |
| 6 | `GET /students/` | 200, **51 SQL queries**, another school's student never appears | `test_05` |
| 7 | `GET /students/<pk>/` | 200, **58 SQL queries**; another school's id → **404** (not 403: no existence oracle) | `test_05`, `test_06` |
| 8 | Teacher/GradeLead scope | teacher: own class 200, other class 404; GradeLead: own grade 200, other grade 404 | `test_07` |
| 9 | Counselor/Student on `/students/` | 403 | `test_08` |
| 10 | `GET /students/<pk>/?predict=true` as SchoolAdmin | 200, prediction block; **1 upstream call per page view** | `test_27` |
| 11 | Same as Teacher/GradeLead/Parent | no button, no upstream call | `test_32` |
| 12 | Upstream 500 | page still renders, error box shows `خطا در سرویس هوش مصنوعی (کد 500).` | `test_33` |

### 3.2 Assistant journey: upload → chunks → ask → answer with citations

| # | Step | Result | Test |
|---|---|---|---|
| 1 | Anonymous → `/assistant/` | 302 to `/login/?next=/assistant/` | `test_09` |
| 2 | Admin, GradeLead, Teacher, Counselor → `/assistant/` | 200 · Parent, Student → 403 | `test_10` |
| 3 | Admin → `/assistant/documents/` | 200 · Teacher/GradeLead/Counselor → 403 | `test_11` |
| 4 | `POST /assistant/documents/` with a `.txt` + attestation | 302, document + 1 chunk stored, `uploaded_by` set, audit `doc_upload` detail `c1` | `test_13` |
| 5 | … with a `.docx` | paragraphs extracted, `source_name` kept | `test_14` |
| 6 | … no attestation / empty / `.pdf` / corrupt docx / UTF-16 / >1 MB / >200k chars / duplicate title / student name | nine specific Persian messages, **nothing written** | `test_15` |
| 7 | … a case-variant of an existing title (`handbook` vs `Handbook`) | accepted → two documents, two answers | `test_16` (F18) |
| 8 | `POST /assistant/` with the school switch off | plain search, **zero network calls**, audit `search:k1` | `test_18` |
| 9 | … switch on, no local provider mapped | excerpts + `مدل زبانی محلی … فعال نیست` notice, **nothing billed** | `test_19` |
| 10 | … switch on, provider mapped | answer + `[1]` highlighted + AI label, audit `ai:k1c1`, quota 1 | `test_17` |
| 11 | … provider 5xx | excerpts + `پاسخ هوشمند در دسترس نبود`, audit `search:k1:error`, **quota still 1** | `test_20` → F05 |
| 12 | … 31st question in a 10-minute window | refused with the rate message **before** any call | `test_22` |
| 13 | … empty / 501 chars / national id in the question | three specific messages, no retrieval, audit `refused:screen` | `test_23` |
| 14 | … no match / document deactivated | `در اسناد مدرسه بخش مرتبطی پیدا نشد.`, nothing billed, audit `none` | `test_24`, `test_25` |
| 15 | … identical question twice | **two** completions, quota 2 | `test_26` (F14) |
| 16 | `GET /school/audit/` as admin | `doc_ask` visible, **question/answer/document text absent**; counselor → 403 | `test_34` |
| 17 | Missing `SERVICE_JWT_SECRET` with the switch on | **HTTP 500** instead of the search fallback | `test_39` (F17) |

### 3.3 Service contract: Django → FastAPI

| Case | Result | Test |
|---|---|---|
| `GET /llm/status/` for a mapped school | `{"enabled": true, "class": "local"}`, no provider call | `test_01` |
| … school not in `LLM_SCHOOL_MAP` | `{"enabled": false, "class": null}` | `test_02` |
| … invalid `LLM_PROVIDERS` JSON | status reads "off"; `/llm/complete/` → 503 `bad_config` (never 500) | `test_03` |
| … `external` provider over `http://` | refused (TLS only for the keyed class) | `test_04` |
| `POST /llm/complete/` (local, ok) | 200 `{text,label,provider_class,model,usage}`; upstream got model / temperature 0.2 / max_tokens 600, no key header, `avoid_names` not forwarded | `test_05` |
| … with `api_key_env` | `Authorization: Bearer …` upstream, key never in the response | `test_06` |
| … provider 500 / garbage JSON / `choices: []` / timeout | 502 `upstream_error` every time; a 1 s timeout cut a 2 s provider at **1.01 s** | `test_07`–`test_09` |
| … purpose outside the whitelist (`counseling`, empty) | 422 `purpose_refused`, no provider call | `test_10` |
| … no token / wrong secret / Parent / empty roles | 401, 401, 403, 403 | `test_11` |
| … `scope: "ai"` token | 200 on `/llm/*` only; 403 on `/documents/list/` and `/predict/` | `test_11b` |
| … token without / with a malformed `schools` claim | 401 | `test_12` |
| … token with two schools | 403 `Exactly one school is required.` | `test_13` |
| … school id in the body instead of the token | ignored; an unmapped school gets 403 `AI is not enabled for this school.` | `test_14` |
| daily cap reached | 429 `cap_reached`, provider not called | `test_15` |
| 4 concurrent asks, one school | `[200, 200, 200, 429]` (semaphore of 3, non-blocking acquire) | `test_17` |
| `POST /predict/` and `/api/v1/predict/` | identical 200 contract, `risk_probability` in 0..1, `is_high_risk == p > 0.5` | `test_18` |
| … bad vector (missing key, `"seven"`, `null`) | 422 | `test_19` |
| … Teacher / Parent / ai-scope / no token | 403 / 403 / 403 / 401 | `test_20` |
| `/chat/`, `POST /documents/`, `/documents/search/` | still 403 for Admin (Phase-1 policy); `/` stays public | `test_21` |
| any response | no prompt echo, no key, no upstream host/port, no traceback | `test_22` |
| startup with a weak secret | `RuntimeError` (refuses to boot); requests then 503 | `test_23` |
| `Authorization: Bearer ` (blank) | 401 | `test_24` |

---

## 4. Findings

Severity: **P1** = fix before any pilot use · **P2** = fix in the pilot window · **P3** = polish/next slice.
Every finding names the test that pins it (a plain test = "this is what happens now"; `expectedFailure` = "this is the
TARGET and it does not hold yet").

### F01 — The risk probability is shown 100× too small · **P1**
* **CURRENT:** the service returns a probability in 0..1 (`main.py` `round(risk_prob, 4)`), the page renders
  `{{ prediction.risk_probability|floatformat:2 }}%`. Measured: `[E2E] F01: model probability 0.70 is rendered as 0.7%`.
  A 70 % risk reads as "0.7 %" and a 4 % risk as "0.04 %".
* **TARGET:** show `70%` (multiply by 100 in the view or use `widthratio`).
* **Where:** `django_core/dashboard/templates/dashboard/student_detail.html:42`.
* **Impact:** the only number that drives the admin's decision is wrong by two orders of magnitude — worse than a
  missing feature, because it looks authoritative.
* **Effort:** 15 min + a template test.
* **Test:** `test_28_F01_the_risk_probability_is_shown_as_a_percentage` (expectedFailure).

### F02 — The prediction is computed from invented numbers and presented as real · **P1**
* **CURRENT:** `dashboard/views.py:142-155` hard-codes `avg_completion_rate = 0.8`, `total_communications = 3`,
  `completed_homework = 12` and computes `attendance_rate = 1 - absences/(days+1)` (which is `1.0`, i.e. perfect
  attendance, for a student with no attendance rows). The page then prints the dict:
  `[E2E] F02: features sent for a student with no homework records: {'grade': 7, 'attendance_rate': 1.0,
  'avg_completion_rate': 0.8, 'avg_exam_score': 0, 'total_absences': 0, 'total_lates': 0, 'total_communications': 3,
  'completed_homework': 12}`. Two students with completely different histories produce the same vector.
  A second copy of the same constants exists at `students/views.py:461-480` (see F21).
* **TARGET:** every feature comes from a real, auditable source; until such data exists the block must say "نمایشی /
  دادههای تکمیلی موجود نیست" and must not be labelled a prediction.
* **Impact:** a school makes a decision about a child on fabricated inputs; the UI even discloses the fabrication
  (`(دادههای ارسالشده به هوش مصنوعی: …)`) without explaining it. This is the highest reputational risk in the product.
* **Effort:** 1–2 days (data model for homework/communications) or 2 h (label it a demo).
* **Test:** `test_29_F02_the_prediction_is_computed_from_the_students_real_numbers` (expectedFailure).

### F03 — The FastAPI address is hard-coded in seven places and `/predict` is served twice · **P2**
* **CURRENT:** `"http://fastapi:8001…"` appears at `dashboard/views.py:169,203,239,276,316`, `students/views.py:509`
  and `docqa/services.py:19` (the only occurrence that is a named constant). `main.py` registers the same handler twice
  (`@app.post("/predict/")` and `@router_v1.post("/predict/")`) and the audit confirms both answer identically.
* **TARGET:** one settings-driven base URL and one route per operation.
* **Impact:** the service cannot be moved/renamed without a code change; timeouts and headers are copy-pasted with
  different values (5 s, 30 s, 65 s, `AI_UPLOAD_TIMEOUT`); the duplicate route doubles the surface to review.
* **Effort:** 2–4 h, mechanical, well covered by the new tests.
* **Test:** `test_21`/`test_18` (both predict paths) + every `docs`/assistant test exercises the URLs.

### F04 — The prediction is a GET side effect · **P2**
* **CURRENT:** `<a href="?predict=true">` (`student_detail.html:31`). Two page views = two FastAPI inferences:
  `[E2E] F04: two page views made predict_calls=2`. A refresh, a prefetch, a bookmark or the back button each re-bill.
* **TARGET:** a POST with CSRF, or a cached result per student/day.
* **Impact:** unbounded, invisible inference spend and non-idempotent GET semantics.
* **Effort:** 1 h (+ the result cache if chosen).
* **Test:** `test_30_F04_a_refresh_does_not_repeat_the_prediction_call` (expectedFailure).

### F05 — A failed AI call is charged to the daily quota (both sides) · **P2**
* **CURRENT:** Django charges `ai_guard.consume()` at `docqa/services.py:147` **before** `_complete()`; FastAPI
  increments its counter in `_take_slot()` at `llm_adapter.py:238` before the transport. Measured: a provider 500 leaves
  `quota_used=1` (Django) and, service-side, `after a 502 the next call returns 429` with `LLM_DAILY_CAP=1`.
* **TARGET:** charge only for a call that produced an answer (or refund on failure).
* **Impact:** one provider outage can exhaust a school's whole daily cap with zero answers delivered; the admin sees
  "سقف روزانه پر شده" while never having received a single reply.
* **Effort:** 2 h (move the charge after the call, or consume/refund in a transaction).
* **Test:** `test_21_F05_…` (Django) and `test_16_F05_…` (service), both expectedFailure; companions `test_20`/`test_07`
  prove the request path and the error mapping work.

### F06 — No loading state, no streaming, 68 s worst case · **P2**
* **CURRENT:** the ask form is a plain POST; `docqa/services.py` allows `timeout=3` for `/llm/status/` and `timeout=65`
  for `/llm/complete/` and the template shows nothing until the response arrives. Worst case = 68 s of a held gunicorn
  worker and a form that looks frozen (users double-submit — see F14). Measured with a mocked provider: 77–87 ms of
  Django work plus the two round trips.
* **TARGET:** a disabled button + spinner (2 h), then streaming or an async job with polling (DECISION REQUIRED).
* **Impact:** the assistant's first impression in a pilot is a spinner-less pause; double submits are billed (F14).
* **Effort:** 2 h for the minimum; 1–2 days for streaming.
* **Test:** `test_36` asserts the real timeouts (3 s / 65 s) and prints the wall time.

### F07 — Every ask re-tokenises the whole school corpus · **P2**
* **CURRENT:** `retrieve()` loads **all** active chunks of the school, builds a `Counter` of tokens per chunk and ranks
  in Python on every ask (`docqa/services.py:85-101`); no token cache, no chunk cache. Measured:
  `retrieve corpus=50_chunks ms=16.5` and `retrieve corpus=500_chunks ms=149.6–160.1` — linear at ≈0.3 ms/chunk, and a
  school may hold up to 5000 chunks (≈1.5–2 s of pure Python per question, inside the request, single-threaded).
* **TARGET:** cache the per-document token counts (invalidate on upload/toggle/delete), or move retrieval to the
  database (PostgreSQL full-text / `pg_trgm` are already available).
* **Impact:** the assistant slows down exactly where it should be fast (large schools), and the cost lands on the same
  worker as the 65 s LLM call.
* **Effort:** 4 h (cache) / 1–2 days (DB search).
* **Test:** `test_35` prints both measurements.

### F08 — `cache.incr` on a just-vanished key raises and 500s the assistant · **P3**
* **CURRENT:** `docqa/views.py:56-58` and `:78-79` do `cache.add(key, 0, WINDOW)` then `cache.incr(key)`. If the key is
  evicted between the two calls (`LocMemCache` culls at 300 entries by default; a restart or a culling pass mid-request
  is enough) `incr` raises `ValueError`, which nothing catches → 500 on the assistant page. The same pattern is used for
  the upload counter.
* **TARGET:** `try: count = cache.incr(key) except ValueError: cache.set(key, 1, WINDOW); count = 1`.
* **Impact:** an intermittent 500 that is invisible in a test suite and very hard for a school to report.
* **Effort:** 30 min. **NOT VERIFIED** as a live failure (needs the eviction race); the code path is plain to read.
* **Test:** none (a test would have to fake the eviction; listed as a code-reading finding).

### F09 — The service-side daily cap lives in one process's memory · **P2**
* **CURRENT:** `llm_adapter.py` keeps `_USAGE = {}` (module level, "in memory: defence in depth") and
  `MAX_CONCURRENT_PER_SCHOOL = 3` in a module-level dict. With N uvicorn workers each worker gets its own cap and its own
  semaphore, so the effective limits are `N × LLM_DAILY_CAP` and `N × 3`.
* **TARGET:** Redis (or the DB) for both, or run a single worker and say so in the runbook.
* **Impact:** the licence-shaped limit the operator believes in is not the one enforced; a burst across workers is not
  throttled as designed.
* **Effort:** 1 day (Redis is already in the stack for Django's cache).
* **Test:** **NOT VERIFIED** — a single-process test cannot observe the multiplication; the evidence is the module dict
  plus its own comment. (The per-process behaviour *is* tested: `test_15`, `test_17`.)

### F10 — Deprecated startup hook · **P3**
* **CURRENT:** `main.py:83` uses `@app.on_event("startup")`. Hard evidence:
  `python -W error::DeprecationWarning -c "import main"` →
  `DeprecationWarning: on_event is deprecated, use lifespan event handlers instead.`
* **TARGET:** a `lifespan` context manager (FastAPI ≥0.93 style).
* **Impact:** will break on the next major FastAPI bump; until then only noise. The hook itself works (the startup
  validation is exercised by `test_23`).
* **Effort:** 1 h.

### F11 — Three of the four roles that may use the assistant have no way in · **P2**
* **CURRENT:** `role_required(*STAFF)` lets Admin, GradeLead, Teacher and Counselor open `/assistant/` (`test_10`), but
  the navigation renders the module menu only for `IS_SCHOOL_ADMIN` (`base.html:58`). Measured:
  `[E2E] F11: a nav link to /assistant/ on each role home: {'GradeLead': False, 'Teacher': False, 'Counselor': False}`.
* **TARGET:** a nav entry for every role that passes the gate — the context processor already computes the URL in
  `VISIBLE_MODULES`; only the template condition needs widening.
* **Impact:** the feature is invisible to 3 of its 4 audiences; a teacher will never find it in a pilot.
* **Effort:** 1–2 h (template + one test flip).
* **Test:** `test_12_F11_…` (expectedFailure).

### F12 — The legacy library page is a guaranteed dead end · **P2**
* **CURRENT:** `/library/` is live for a SchoolAdmin (`test_37` asserts 200); its form accepts `.pdf/.doc/.docx` up to
  10 MB and forwards to FastAPI's `/upload-document/`, which is `disabled_in_phase1` for **every** role. Measured
  message: `خطا در آپلود: AI features are disabled.` — an English platform string in a Persian UI, after a full upload.
  The live assistant accepts only `txt/md/docx`, so the two pages contradict each other, and `/chat/` (403 for all) still
  ships a template.
* **TARGET:** one document library (`/assistant/documents/`); hide or delete `/library/`, `/upload-document/`, `/chat/`
  and their templates.
* **Impact:** an admin's first attempt at "کتابخانه" always fails; the failure names an internal feature flag in English.
* **Effort:** 2 h (URLs + nav + templates + tests).
* **Test:** `test_37_F12_…` (characterisation of today's behaviour).

### F13 — `library_view` swallows every exception · **P3**
* **CURRENT:** `dashboard/views.py:237-244` wraps the FastAPI call in `try: … except: pass` — a bare except that also
  swallows `KeyboardInterrupt`/`SystemExit` and turns any failure into an empty list.
* **TARGET:** `except requests.RequestException` plus a visible "سرویس در دسترس نیست" state (or delete the page per F12).
* **Impact:** silent breakage — no log line, no way for an operator to notice.
* **Effort:** 30 min (moot if F12 removes the page). **Test:** covered indirectly by `test_37`.

### F14 — No answer cache and a fixed prompt budget · **P3**
* **CURRENT:** an identical question costs a second completion and a second quota unit:
  `[E2E] identical question twice -> complete_calls=2 quota=2`. The prompt is a fixed top-4 × 900 chars (`TOP_K`,
  `CHUNK_CHARS`) with no relevance floor — a weak match is sent as if it were evidence.
* **TARGET:** a short-lived answer cache keyed by (school, normalised question, document-set version) and a score floor.
* **Impact:** wasted spend on re-clicks (F06 produces exactly those re-clicks) and answers built on noise.
* **Effort:** 4 h (cache) + 2 h (threshold). **Test:** `test_26` measures it.

### F15 — (superseded) — merged into F19
An earlier draft listed "one generic 503 for two different failures" here. Re-testing showed the Django side *does*
distinguish unconfigured / unreachable / non-200 (`views.py:178-183`); the real defect is that it prints the raw upstream
status code to the school admin, which is F19.

### F16 — The React frontends are not wired to the product · **DECISION REQUIRED**
* **CURRENT:** `frontend-men/src/lib/api.ts` exists but **no module imports it** (`grep` over `frontend-men/src` finds
  only `@/lib/utils` for `cn`); `frontend-women` has no API client at all. Both are Vite/React presentational apps
  (ADR-0013 forbids a SPA, so this is consistent) — every journey above is a Django template.
* **TARGET:** state which artefact the pilot ships. If the templates are the product, the frontends are dead weight and
  should be marked as such (or removed); if not, the API-wiring work is a phase of its own.
* **Impact:** UX review of the frontends can only be static; a reviewer who opens them sees a product that does not
  exist. No user-facing defect today.
* **Effort:** 0 to document, days to wire.

### F17 — A missing `SERVICE_JWT_SECRET` turns the ask page into a 500 · **P2**
* **CURRENT:** `config/settings/base.py:95` defaults the secret to `''` and no deploy check refuses to start. The AI
  branch of `docqa.services.ask()` calls `service_headers()` at `services.py:141`, outside every `try`, so with the
  switch on and a matching document the request raises `ImproperlyConfigured` → Django's 500 page. Measured:
  `[E2E] F17: ask without SERVICE_JWT_SECRET -> status=500`.
* **TARGET:** catch `ImproperlyConfigured` exactly as the prediction page does (`views.py:178`) and show the excerpts
  with the usual notice; and/or fail at startup like FastAPI does (`auth.validate_service_secret`).
* **Impact:** the most likely misconfiguration in a new deployment produces the least helpful page, and it does so only
  for the assistant (the predict page degrades gracefully).
* **Effort:** 1 h. **Test:** `test_39_F17_…` (expectedFailure).

### F18 — Two spellings of one title create two documents · **P3**
* **CURRENT:** the constraint is `UniqueConstraint(school, title)` — exact. Uploading `Handbook` and then `handbook`
  stores both (`test_16`), and both are retrieved and cited.
* **TARGET:** compare on `normalize(title)` (the module already has `docqa.screen.normalize`), or block on identical
  `char_count` + first-chunk hash.
* **Impact:** duplicated answers with different citation numbers from the same text; double the retrieval cost.
* **Effort:** 1 h (+ migration for a functional unique index).

### F19 — The school admin is shown the upstream HTTP status code · **P3**
* **CURRENT:** `dashboard/views.py:28` builds `خطا در سرویس هوش مصنوعی (کد {status}).` and the template prints it
  (`test_33` asserts `(کد 500)`). The assistant, by contrast, shows a Persian notice and hides the code in the audit row.
* **TARGET:** one vocabulary for both AI surfaces: a Persian sentence the user can act on ("سرویس هوش مصنوعی در دسترس
  نیست؛ بعداً تلاش کنید") and the code only in the log/audit.
* **Impact:** leaks internal detail, gives no next step, and is inconsistent with the assistant two clicks away.
* **Effort:** 30 min.

### F20 — 51–58 SQL queries per dashboard page · **P3**
* **CURRENT:** `[E2E] school_home queries=53`, `student_list queries=51`, `student_detail queries=58` (in-memory
  SQLite, tiny fixture: 2 schools, 3 students). Server time 55–84 ms here; a real school with a few hundred students
  multiplies both.
* **TARGET:** fix the N+1s (most come from per-student attribute access in the template plus repeated
  `visible_*` scope evaluation) with `select_related`/`prefetch_related` and by resolving the scope once.
* **Impact:** the pages every role opens first are the slowest in the product; the pilot's largest school will feel it.
* **Root cause:** **NOT VERIFIED** in detail (not instrumented per query); the count itself is measured.
* **Effort:** 1–2 days. **Test:** `test_05` prints the numbers and fails above 120.

### F21 — The API has a second, unmetered copy of the prediction · **P2**
* **CURRENT:** `students/views.py:461-480` (`get_features`, `predict_status`) rebuilds the same placeholder vector
  (`avg_completion_rate: 0.8`, `total_communications: 3`, `completed_homework: 12`) for the DRF routes
  `/api/students/<pk>/features/` and `/api/students/<pk>/predict/`. The gate is the Admin role (same as the page), so
  the two agree on who may call, but **neither** path calls `ai_guard.consume()` — measured
  `AICallUsage.objects.count() == 0` after an API prediction (`test_38`).
* **TARGET:** one feature builder, one call path, metered like the assistant (which *is* capped).
* **Impact:** the "license cap" an operator sells on covers the assistant only; predictions are free and unlimited, and
  a fix to F02 has two places to land.
* **Effort:** 4 h (delete the copy or delegate to one service).
* **Test:** `test_38_F21_…` (characterisation, prints the echoed vector).

---

## 5. Measurements (CURRENT, this machine)

| What | Value | Where it comes from |
|---|---|---|
| `GET /school/` | 53 queries, 55–84 ms | `test_05` |
| `GET /students/` | 51 queries, 56–75 ms | `test_05` |
| `GET /students/<pk>/` | 58 queries, 59–77 ms | `test_05` |
| `retrieve()`, 50 chunks | 16.5–17.3 ms | `test_35` |
| `retrieve()`, 500 chunks | 149.6–160.1 ms (≈0.31 ms/chunk, linear) | `test_35` |
| Assistant ask, provider mocked | 77–87 ms of Django work + 2 sequential round trips | `test_36` |
| Assistant timeouts | status 3 s + completion 65 s → **68 s** worst case | `test_36` |
| Service timeout enforcement | provider timeout 1 s vs a 2 s stub → 502 at **1.01 s** | `test_09` |
| Concurrent asks, one school | 3 in flight, 4th → 429 `busy` | `test_17` |
| Identical question twice | 2 completions, quota 2 | `test_26` |
| Failed completion | quota charged (1) but no answer | `test_20`, `test_21` |
| Full Django e2e module | 39 tests, 7.55 s | §1.1 |
| Full FastAPI e2e module (whole suite) | 124 tests, 4.62 s | §1.1 |

Not measured here: real provider latency/token price (no key, no outbound network in this environment) and PostgreSQL
timings (see §7 for the suite result, not a benchmark).

---

## 6. UX review (the Django template product)

### What is good — keep it
* **Specific, actionable Persian errors.** Nine distinct upload messages (`test_15`), a distinct rate-limit message, a
  distinct screening message, and a distinct "no relevant section" state. This is rare and valuable.
* **Honest AI framing.** The answer carries the label `هوش مصنوعی؛ فقط پیشنهادی و ممکن است اشتباه باشد. تصمیم با انسان
  است.`, an answer without `[n]` citations is flagged as untrustworthy, and every AI failure degrades to the retrieved
  excerpts with a notice instead of an error page (`test_17`–`test_20`).
* **The screen tells you why it refused.** The question and the document are both screened (national id, phone, e-mail,
  a student's name) and the refusal explains the rule rather than the regex.
* **404, not 403, for another school's student** — no existence oracle (`test_06`, `test_07`).
* **Audit page shows codes, never content**, and the answer's sources are visible with the cited excerpts highlighted
  (`test_34`).
* **Login**: one message for a wrong password, throttled per username and per IP, off-site `?next=` dropped (`test_01`–`test_04`).
* **Accessibility basics are present** in `base.html` (`aria-hidden` on icons, `aria-label` on locks, `eip-nav-link`
  with an `active` state), and the RTL layout is consistent across the pages I read.

### What is bad — the user-visible list
1. **"احتمال ریسک: 0.7%"** (F01) — the single worst string in the product.
2. **"دادههای ارسالشده به هوش مصنوعی: {'grade': 7, 'attendance_rate': 1.0, …}"** (F02) — a Python dict rendered to a
   school principal, containing numbers that were never measured.
3. **"خطا در سرویس هوش مصنوعی (کد 500)."** (F19) — an HTTP status where a next step should be.
4. **"خطا در آپلود: AI features are disabled."** (F12) — English, from a flag the user cannot see, on a page that
   cannot ever succeed.
5. **A form that freezes for up to a minute** with no spinner and no disabled button (F06), which invites the
   double-submit that F14 bills twice.
6. **A feature the user cannot find**: `/assistant/` has no nav entry for Teacher / GradeLead / Counselor (F11).
7. **A nav section "دستیار و منابع" that offers two permanently disabled items** ("چت با هوش مصنوعی", "کتابخانه —
   بهزودی") next to a live assistant, while the real library page is at a different URL (F12).

### Copy-level suggestions (cheap, no decision needed)
* "احتمال ریسک: ۷۰٪" — Persian digits, no decimals for a probability, and a one-line explanation of what the model
  looked at.
* Replace the raw dict with the three numbers that matter (`غیبت`, `تاخیر`, `میانگین نمره`) and a "بر پایهٔ …" line.
* The assistant form should say how long an answer takes ("تا ۳۰ ثانیه") and disable the button after the first click.

---

## 7. Full suites (regression proof for this audit)

### 7.1 `scripts/run_tests.sh sqlite` — PASSED (CURRENT, run in this audit)

```
>> [config.settings.development] manage.py check
System check identified no issues (0 silenced).
>> [config.settings.development] manage.py makemigrations --check --dry-run
No changes detected
>> [config.settings.test_sqlite] manage.py test students dashboard schools vocabulary missions exams risk interventions docqa
Ran 1674 tests in 1460.916s
OK (skipped=11, expected failures=6)
>> [config.settings.demo] manage.py test demo_intel
Ran 62 tests in 300.303s
OK

ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)
```

The suite now collects 1674 tests, 39 of which are new; the 6 expected failures are exactly the finding markers in
`dashboard/test_e2e_user_flow.py`, so nothing else in the suite is red. (The 11 skips are pre-existing.)

### 7.2 `scripts/run_tests.sh pg` — PASSED (CURRENT, run in this audit)

```
>> [PostgreSQL 16 container] manage.py check
System check identified no issues (0 silenced).
>> [PostgreSQL 16 container] manage.py makemigrations --check --dry-run
No changes detected
>> [PostgreSQL 16 container] manage.py test students dashboard schools vocabulary missions exams risk interventions docqa
Found 1674 test(s).
...
Ran 1674 tests in 1943.716s

OK (skipped=1, expected failures=6)
Destroying test database for alias 'default'...
```

Run with `DJANGO_IMAGE=eip-test-django:local PG_IMAGE=pgvector/pgvector:pg16` (both images already local, so no build and no
pull); the script removed its container and private network on exit. 1674 collected, same 6 expected failures. The skip
count differs from SQLite (11 → 1) exactly as the script's header documents: the container-only and PostgreSQL-only tests
skip without PostgreSQL, and `EIP_REQUIRE_PG=1` turns the latter into real runs instead of skips.

### 7.3 FastAPI

`Ran 124 tests in 4.623s → OK (skipped=32, expected failures=1)` (see §1.1) — run inside the verified image with
`--network none`, i.e. the same conditions as the baseline. Re-confirmed after the last edit to the test files:
`Ran 124 tests in 5.227s → OK (skipped=32, expected failures=1)` and, on the Django side,
`Ran 39 tests in 8.158s → OK (expected failures=6)`.


---

## 8. Roadmap

### P1 — before the pilot touches a school (≈2 days)
1. **F01** percentage (15 min) — one line, one test.
2. **F02** stop presenting invented numbers as a prediction: either wire real data or label the block as a demo and
   remove the "prediction" wording (2 h for the label, 1–2 days for the data). **Owner decision needed.**
3. Re-run both new modules + `scripts/run_tests.sh sqlite` and `pg`; flip the two `expectedFailure` markers.

### P2 — inside the pilot window (≈1 week)
4. **F05** charge the cap only for a delivered answer (Django + service).
5. **F06** disable the button + spinner + a stated expected wait (and one submit per question).
6. **F11** nav entry for Teacher / GradeLead / Counselor.
7. **F12** retire `/library/`, `/upload-document/`, `/chat/` (and the "بهزودی" nav stubs).
8. **F17** catch `ImproperlyConfigured` on the ask path and add a deploy check for `SERVICE_JWT_SECRET`.
9. **F21** delete the duplicate feature builder; meter predictions like the assistant.
10. **F03** one FastAPI base URL in settings, one `/predict` route.
11. **F04** POST (or cache) for the prediction.
12. **F07** cache per-document token counts.
13. **F09** move the service cap/semaphore to Redis, or pin workers to 1 in the runbook.

### P3 — next slice (≈1 week)
14. **F18** case-insensitive document titles; **F14** answer cache + relevance floor; **F19** one error vocabulary;
    **F20** N+1 pass on the three dashboard pages; **F08** `incr` guard; **F10** lifespan hook; **F13** the bare except.

### Decision required
* **F02** — real data vs "demo" label (product/owner).
* **F16** — are `frontend-men` / `frontend-women` part of the product at all?
* **F06** — is a 68 s blocking POST acceptable for the pilot, or is streaming/async in scope now?
* **F09** — how many FastAPI workers does a pilot deployment run? (Determines whether the cap is real.)

---

## 9. Not verified / limits of this audit

* **No real provider call.** No API key and no outbound network in this environment; the service leg uses a real HTTP
  stub on loopback. Provider behaviour (latency, truncation, non-OpenAI error shapes) is unmeasured.
* **No browser.** No JS, no rendering engine, no accessibility scanner: RTL/visual/contrast claims are read from the
  templates, and the "no loading state" claim is from the markup (no JS in `docqa/home.html`).
* **No PostgreSQL timing.** The `pg` run proves the suite passes on PostgreSQL, not its performance.
* **Multi-worker behaviour (F09)** cannot be observed in a single process.
* **F08** is a code-reading finding; the eviction race was not reproduced.
* **F20** root cause not instrumented per query; only the counts are measured.
* **The React frontends** were reviewed statically only (F16).
* **FastAPI `/predict/` model quality** — the model is faked in tests; only the contract is verified.
* **No load test** beyond the 4-thread burst in `test_17`.

---

## 10. Governance notes (no change proposed here)

* This audit is **L1**: three test files + this report, no product code touched. Each fix above becomes an L2 change
  starting at `docs/changes/0044-…-PROPOSAL.md` and stops for approval.
* The AI governance rules held under test: prompts contain only the school's active document excerpts and the screened
  question (asserted, `test_17`); no student name/national id reaches the provider; the audit log stores codes only
  (`test_34`); `document_qa` is a LOCAL-class purpose only and an `external` provider over plain http is refused
  (`test_04`, `test_10`).
* One governance gap worth naming, without calling it a breach: the **prediction** sends a student's grade and
  attendance figures to the FastAPI service with no screening and no audit row beyond `view_detail`, and the service
  keeps no record of it. It is not an external LLM, so the hard rule is not broken — but the data flow is undocumented
  in AI_GOVERNANCE and should be added there (F02/F21 work).
* The new tests follow the repo's existing doubles (`test_security.py`'s fake modules) and add a real HTTP stub; nothing
  in `risk/`, `interventions/`, `core/` was created, so no `git add -f` was needed.







