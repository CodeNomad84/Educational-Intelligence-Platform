# 0039 — T8: security fixes after the T7 review (CHANGE PROPOSAL — no application code changed)

Level: L2 · Status: **BLOCKED — DECISION REQUIRED (D0–D4)** · Date: 2026-11-11 · Branch `work/T8-security-fixes` @ `af41c59`
(from `phase-1/boot-security`)

**This task changed no code, no setting, no migration and no test, and ran no test.** It created this file and one
`BLOCKED` entry in `docs/pilot/PROGRESS.md`. Reason: `docs/pilot/QUEUE.md`, T8 row —

> `T8  L2  fix ONLY Critical/High findings of T7, one commit each, failing-test-first.`
> `     If a fix needs a design decision or touches access rules: BLOCKED. Full suite sqlite+pg.`

and `docs/pilot/T7-SECURITY-REVIEW-REPORT.md` §5.2 lists **four DECISION REQUIRED** owner questions, three of which
sit on the findings named in this task (H-1, M-4, L-5). T7 §6 also says: *"Do not do in T8 without a proposal:
anything that … changes the audit vocabulary's meaning …"* — M-5 adds an audit action.

Everything below is labelled **CURRENT** (verified in this task, command quoted), **TARGET** (proposed, not built) or
**DECISION REQUIRED** (yours). No item is FIXED. No test is claimed to pass.

---

## 0. Cross-walk to `docs/templates/CHANGE_PROPOSAL.md`

| Template item | Where it is answered |
|---|---|
| 1 Requirement | §1 — the T8 assignment and the scope conflict it contains |
| 2 Current behavior | §2 — verified line references + the commands that produced them |
| 3 Desired behavior | §3 — per finding, the exact edit and the fixed message/code |
| 4 Affected modules | §3 "Files" column (`students`, `dashboard`, `schools`, `fastapi_core`, `config/settings`) |
| 5 Data impact | §4 — no migration anywhere; M-5 adds `AuditEvent` rows only |
| 6 API impact | §5 — three new fixed `400`s on `/api/students/import/`, row-error strings change |
| 7 Frontend impact | §6 — none if M-1 is fixed in place; a nav link if the legacy route is deleted |
| 8 AI impact | §7 — M-2 only (log level/content); no model, prompt or rule change |
| 9 Security impact | §8 — closes 1 HIGH, 5 MEDIUM, 1 LOW; nothing in `students/access.py` or entitlements |
| 10 Testing strategy | §9 — failing-test-first, one test file/class per finding, then full suite sqlite+pg |
| 11 Documentation impact | §10 |
| 12 Customization impact | §11 — one new constant; no new env knob recommended |
| 13 Risks | §12 — incl. a correction to the T7 H-1 "settings defense in depth" advice |
| 14 Recommendation | §13 — the five decisions, each with a recommended option |

---

## 1. Requirement and the scope conflict (CURRENT)

The task brief for this session: *"security fixes H-1, M-1 through M-5, L-5 from the T7 review"*.

The owner-owned queue says something narrower: **only Critical/High findings**. T7 §2 has **no CRITICAL** and exactly
**one HIGH (H-1)**; M-1…M-5 are MEDIUM, L-5 is LOW. So, read literally, T8 = H-1 and nothing else, and the M/L items
named in the brief need an explicit scope decision (**D0**) before I touch them. I am not going to guess which
document wins.

H-1 itself is not mechanically decidable: T7 §5.2 item 4 asks the owner to pick the import ceiling "so T8 does not
invent the policy" (**D1**). Under the queue's rule that is a BLOCK, not a licence to choose 2 MB myself.


## 2. CURRENT — what I verified in this task

Commands were run on `work/T8-security-fixes` @ `af41c59`; the results are quoted, not remembered.

| # | Check | Command | Result (CURRENT) |
|---|---|---|---|
| 1 | Import route has no byte cap | read `students/views.py:250-277` | `file.size` is never read; the stream goes straight to `pd.read_csv(TextIOWrapper(file, …))` / `pd.read_excel(BytesIO(file.read()), …)` |
| 2 | …and no validator above it | `students/serializers.py:87-90` | `class FileUploadSerializer(serializers.Serializer): file = serializers.FileField()` — no `validators`, no `max_length` |
| 3 | No global upload limits | `grep -rn "FILE_UPLOAD_MAX_MEMORY_SIZE\|DATA_UPLOAD_MAX_MEMORY_SIZE\|DATA_UPLOAD_MAX_NUMBER" django_core/config/settings/` | `NO UPLOAD LIMITS IN SETTINGS` |
| 4 | Existing ceilings in the repo | `grep -n "MAX_FILE_BYTES\|MAX_BYTES" dashboard/bulk_accounts.py risk/catalog_services.py docqa/extract.py exams/csv_import.py` | `bulk_accounts.py:36 MAX_FILE_BYTES = 2_000_000`, `risk/catalog_services.py:18 MAX_BYTES, MAX_ROWS = 1_000_000, 200`, `docqa/extract.py:6 MAX_BYTES, MAX_TEXT = 1_000_000, 200_000`, `exams/csv_import.py:17 MAX_BYTES = 200 * 1024` |
| 5 | No row cap on the import | `grep -n "MAX_ROWS\|len(df)" students/*.py` | one hit only: `students/views.py:409 'total_rows': len(df)` — a report field, not a limit |
| 6 | No audit event on the import | `grep -n "audit\." students/views.py` | `audit` is imported (`:29`) and used by `list`/`retrieve`/national-id reveal only; `import_students` (`:250-421`) never calls it |
| 7 | M-1 timeout | `grep -n timeout dashboard/views.py` | `:157 timeout=5`, `:191 timeout=30`, `:222-224 timeout=5`, **`:263 timeout=3000`**, `:300 timeout=5` |
| 8 | M-2 logging | `grep -n "logger\." fastapi_core/main.py` | `:37 logging.basicConfig(level=logging.DEBUG)`; content-bearing line `:295 logger.debug(f"نمونه سند اول: {documents_to_add[0]}")`; also `:238` filename at INFO, `:292` count at DEBUG |
| 9 | M-3 leak sites | same grep + `grep -n "str(e)"` | `students/views.py:367,385,419`; `dashboard/views.py:168,205,281,310`; `fastapi_core/main.py:149,199,209,219,233`; plus `dashboard/views.py:163` (`response.text` into the page) |
| 10 | M-4 second app is **not in git** | `git ls-files fastapi_core` | `main_HuggingFace.py` and `rag_service_HuggingFace_Models.py` are **absent**; `git check-ignore -v` → `.git/info/exclude:19` |
| 11 | …but it does ship in the image | `cat fastapi_core/.dockerignore`, `cat fastapi_core/Dockerfile` | `.dockerignore` lists only `venv/ pycache/ *.pyc .env .venv/ .venv-win/`; the Dockerfile ends with `COPY . .` — the two local files are copied |
| 12 | L-5 session payload | `grep -n "request.session" dashboard/bulk_views.py` | `:48 request.session[SESSION_KEY] = {'school': school.pk, 'ts': time.time(), 'rows': parsed}` (`SESSION_SECONDS = 30 * 60`, `:24`) |
| 13 | Audit vocabulary has room | `grep -n "class AuditEvent" -A 22 schools/models.py` | `action = models.CharField(max_length=40, db_index=True)`, `detail = models.CharField(max_length=40)` → a new action string needs **no migration** |

## 3. TARGET — the edit proposed per finding

Sizes are diffs, not promises. One commit per finding, test first (queue rule).

| ID | File(s) | TARGET edit | Fixed text / code | Test |
|---|---|---|---|---|
| **H-1** | `students/views.py`, `students/serializers.py` | reject `file.size > IMPORT_MAX_BYTES` **before** any read; read at most `IMPORT_MAX_BYTES + 1` bytes and refuse a longer stream (both paths: csv bytes, xlsx bytes) | `400 {'error': 'حجم فایل بیش از حد مجاز است (حداکثر ۲ مگابایت).'}` | `students/test_import_security.py`: 2 MB+1 → 400, `pd.read_csv`/`read_excel` not called, no `Student` row written; exactly 2 MB reaches the parser |
| **M-1** | `dashboard/views.py` | `timeout=3000` → `AI_UPLOAD_TIMEOUT = 30`; fixed error message (see M-3) | `messages.error(request, 'سرویس هوش مصنوعی پاسخ نداد؛ دوباره تلاش کنید.')` | `dashboard/tests.py`: `mock.patch('dashboard.views.requests.post')` → `kwargs['timeout'] <= 30` |
| **M-2** | `fastapi_core/main.py` | delete `:295`; level from `LOG_LEVEL` with a **WARNING** default; no filename/content in log lines | `logging.basicConfig(level=_log_level())`, `logger.debug("chunks to store: %d", len(...))` | `fastapi_core/tests/test_security.py`: AST check — no `logger.*` call receives `text`/`content`/`documents_to_add[0]`; default level is `WARNING`, `LOG_LEVEL=DEBUG` honoured |
| **M-3** | `students/views.py`, `dashboard/views.py`, `fastapi_core/main.py` | log with `exc_info=True`, return a fixed message (FastAPI: `detail="internal_error"` + `X-Correlation-Id`); never `str(e)`, never `response.text` | row errors: `'ردیف N: خطا در پردازش این ردیف.'`; import outer: `500 {'error': 'خطا در پردازش فایل. جزئیات در گزارش سرور ثبت شد.'}` | `students/test_import_security.py`, `dashboard/tests.py`, `fastapi_core/tests/test_security.py` (mirrors the existing `test_delete_internal_error_is_500_without_leaking_details`) |
| **M-4** | `fastapi_core/.dockerignore`, `docs/PHASE1_DEFERRED_ITEMS.md`, `fastapi_core/tests/test_exposure.py` | exclude the two local files from the build context + guard test that fails when a second `FastAPI(` application exists under `fastapi_core/` (excluding `tests/`) + close deferral item 7. **Delete the local files only on your word (D2)** — they are not in git and cannot be recovered | — | `test_exposure.py` (new class) |
| **M-5** | `schools/audit.py`, `students/views.py` | `STUDENT_IMPORT = 'student_import'`; one event per import, counts only, `object` = the target School, `detail = f's{c}u{u}e{e}'` (≤ 40 chars) | e.g. `s12u3e1` | `students/test_import_security.py`: one `AuditEvent` with `action='student_import'`, that school, that user, counts only — and **no** name/national id in `detail` |
| **L-5** | `dashboard/bulk_views.py` | one of D3: (a) keep + document, (b) session holds a random token, parsed rows in the cache with a 30-min TTL, (c) re-parse on confirm from a stored upload | — | `dashboard/test_bulk_accounts.py`: session holds no national id |

## 4. Data impact

**No model change, no migration, no data migration, no index** for H-1, M-1, M-2, M-3, M-4, L-5. M-5 only **adds rows**
to `schools_auditevent`; the vocabulary constant is a Python literal and `action` is already `CharField(max_length=40)`.

## 5. API impact

* `POST /api/students/import/` gains fixed `400`s (oversize, over-row-limit if D1b) and a fixed `500` body shape
  (`{'error': <fixed text>}`; the key is unchanged, so no client change is needed).
* The `errors[]` strings change from `'ردیف N: خطا - <str(e)>'` to a fixed sentence. The characterization suite
  `students/test_import_students.py` pins today's text nowhere for that branch (checked: `grep -rn "خطا -" students/`
  → no test hit), but every assertion that counts `errors` still holds.
* FastAPI bodies: `detail` of a `500` becomes a constant. **No** success payload, route, role or claim changes.

## 6. Frontend impact

None if M-1 is fixed in place (`dashboard:library` keeps its page). If M-1 is instead resolved by deleting the legacy
route (T7's preferred option), the nav link in `dashboard/templates/dashboard/base.html:66` and `dashboard/urls.py:16`
go away. No new template, no JS (ADR-0013).

## 7. AI impact

M-2 changes log volume and level only. M-4 removes a **second** application from the image; the served application
(`uvicorn main:app`) and `llm_adapter` are untouched. No model, prompt, threshold or rule change.

## 8. Security impact

| Item | Effect |
|---|---|
| H-1 | closes a cross-tenant DoS (one SchoolAdmin request could exhaust the shared host volume / OOM every worker) |
| M-1 | removes a 50-minute worker pin (gunicorn is also started with `--timeout 3000`, so it would not recycle it) |
| M-2 | document text stops entering container logs; the level is no longer DEBUG-by-default |
| M-3 | internal detail (driver text, upstream bodies, pandas/openpyxl parser text) stops being reflected to callers |
| M-4 | an unauthenticated, cross-tenant application stops being shipped in the image |
| M-5 | the PII import becomes visible in `AuditEvent` (who/what/when, counts only) |
| L-5 | removes a second copy of parsed PII from the DB session row (options b/c of D3) |

Untouched by this proposal: `students/access.py`, school entitlements, the service-token claims, the audit *meaning* of
existing actions, and DRF's permission model. Existing audit events are neither rewritten nor deleted.

## 9. Testing strategy (failing-test-first)

1. For each accepted finding: add the test **first**, run only that module, show it failing for the right reason
   (`scripts/run_tests.sh sqlite students.test_import_security`), then implement, then re-run.
2. New file `django_core/students/test_import_security.py` (H-1, M-3, M-5). The existing
   `students/test_import_students.py` is a *characterization* file ("every later change is a deliberate, reviewed diff"),
   so it is not the right home for new guarantees. Uploads stay synthetic and in memory; nothing is written to disk.
3. `dashboard/tests.py`: M-1 timeout, M-3 fixed message, L-5 session content.
4. `fastapi_core/tests/test_security.py`: M-2 AST/log-level check, M-3 leak check on the two enabled routes
   (`/predict/`, `/documents/list/`), in the style of the existing `test_delete_internal_error_is_500_without_leaking_details`;
   `fastapi_core/tests/test_exposure.py`: the M-4 second-app guard.
5. Last step: full suite — `scripts/run_tests.sh sqlite`, then `… pg`, output redirected to a file, and the last lines of
   that file read. No pass is claimed before that.

## 10. Documentation impact

`docs/pilot/T7-SECURITY-REVIEW-REPORT.md` §2 gains a `Status` column (T7 §6 acceptance), `docs/pilot/PROGRESS.md` gets
the T8 entry, `docs/PHASE1_DEFERRED_ITEMS.md` item 7 is closed by M-4. `docs/CHANGE_PROCESS.md` needs no change.
`docs/pilot/QUEUE.md` is owner-owned and will **not** be edited by me (a D0 amendment is yours).

## 11. Customization impact

H-1 introduces one module constant (`IMPORT_MAX_BYTES`) beside `IMPORT_CHUNK` / `NATIONAL_ID_MAX_LENGTH` in
`students/views.py`; nothing becomes tenant-configurable. I recommend **no** env knob: the ceiling is a resource guard,
not a school preference.

**Correction to T7's H-1 advice (CURRENT, from Django's documented semantics):** `FILE_UPLOAD_MAX_MEMORY_SIZE` decides
when an upload spools from memory to a temp file — it is **not** a size cap — and `DATA_UPLOAD_MAX_MEMORY_SIZE` does not
apply to file fields. Adding either to `base.py` would create a false sense of a cap while changing nothing about H-1's
impact. Only the view (and, optionally, a reverse-proxy `client_max_body_size`, which lives outside this repo's tested
surface) can refuse the bytes. T7 §3 H-1 item 4 should be read with this correction.

## 12. Risks

| Risk | Mitigation |
|---|---|
| A ceiling too small for a real roster | a 2 MB CSV is ≳ 10 000 rows of this schema; a 50-student xlsx is ≈ 10 KB. D1 picks the number. |
| Removing `str(e)` makes support harder | the exception is still logged with `exc_info=True` at the boundary and M-3 adds a correlation id, so a user report can be matched to a log line |
| M-5 could log PII by accident | `detail` is a fixed count code, `object` is the School, and the test asserts that no name/national id appears |
| L-5 (b) moves PII from the session row into the cache | documented in the same commit; TTL 30 min; the cache is already used by `dashboard/throttle.py` |
| M-4 deletion of local files is irreversible | only after D2; the files are untracked, so `git rm` is impossible and a delete cannot be undone |
| Changing the `errors[]` text breaks a client | no in-repo client parses that text; the JSON keys are unchanged |

## 13. Recommendation and DECISION REQUIRED

**If D0 = (a) "H-1 only":** one commit — H-1 + its test + docs — then the full suite sqlite+pg.
**If D0 = (b) "the six findings named in the brief":** seven commits in T7 §6 order (H-1, M-5, M-3, M-2, M-1, M-4, L-5),
each with its own failing test, then the full suite.

| ID | Decision REQUIRED | Recommended |
|---|---|---|
| **D0** | Scope: (a) H-1 only, as `QUEUE.md` says; (b) H-1 + M-1…M-5 + L-5, as this brief says (then `QUEUE.md` needs your amendment note, since I must not edit it); (c) H-1 + the MEDIUMs, L-5 as a separate task | **(b)** — the brief is the newer instruction — but only if you also record it in `QUEUE.md` |
| **D1** | H-1 ceiling: (a) 2 MB flat, like `bulk_accounts`; (b) 2 MB + a row cap (n = ?); (c) a row cap derived from the school's current student count | **(a)**, plus the bounded read. No row cap in this change: for CSV the byte cap already bounds `len(df)`; (b)/(c) invent a school-size policy nobody has stated |
| **D2** | M-4: (a) keep the local files, exclude them from the build context (`.dockerignore`) + guard test; (b) also delete the two untracked local files; (c) move them to `docs/experiments/` (they would enter git and need review) | **(a)** now, and **(b)** when you confirm you do not need the experiment locally; I will not delete untracked work on my own |
| **D3** | L-5: (a) keep the parsed rows in the session and document the choice; (b) session = a random token, parsed rows in the cache (30-min TTL); (c) re-parse on confirm (needs the upload kept, i.e. extra storage) | **(b)**: no PII in the session row, no new storage concept, at the cost of the roster living ≤ 30 min in Redis |
| **D4** | M-5 vocabulary: add `STUDENT_IMPORT = 'student_import'`, `detail = s<created>u<updated>e<errors>`, `object` = the target School, one event per successful import (no event for a refused upload) | **yes** — it mirrors `BULK_ACCOUNTS` (`s12p9t3e1`) and needs no migration |

An answer of the form `D0=b D1=a D2=a D3=b D4=yes` is enough for me to start; each accepted finding then gets its own
commit with a failing test first, exactly as `QUEUE.md` requires.

---

*Nothing above was implemented when this proposal was written (see §14 for what was implemented after the answers). Branch
`work/T8-security-fixes` existed only to hold this proposal and the PROGRESS entry; `git diff --stat
phase-1/boot-security` on it showed documentation only.*

---

## 14. Implementation report (added after the owner answered, 2026-11-11)

**Answers:** `D0=b D1=a D2=a D3=b D4=yes`. Scope = H-1 + M-1…M-5 + L-5; the seven commits below are on
`work/T8-security-fixes` (nothing merged, nothing pushed, `main` untouched), each with the test that fails without it.

| # | Finding | Commit | What changed | Module test result (real run) |
|---|---|---|---|---|
| C1 | H-1 | `547ca2d` | `IMPORT_MAX_BYTES = 2 MB` + bounded read; format check before the read | `students.test_import_security` — see the `PROGRESS.md` entry |
| C2 | M-5 | `cb003da` | `audit.STUDENT_IMPORT`, detail `s<n>u<n>e<n>`, object = School | same module |
| C3 | M-3 | `26c774c` | fixed sentences + logging in Django; `_internal_error()` + `X-Correlation-Id` in FastAPI | Django + FastAPI |
| C4 | M-2 | `9d13241` | `LOG_LEVEL` (default `WARNING`); no document text or filename in logs | FastAPI 72 OK |
| C5 | M-1 | `5131c53` | `AI_UPLOAD_TIMEOUT = 30`, fixed sentence on `Timeout` | `dashboard.tests` 34 OK |
| C6 | M-4 | `f524ab2` | `.dockerignore` entries + `SingleApplicationTests` guard | `test_exposure` 7 OK |
| C7 | L-5 | `6ab08c8` | rows in the cache (30 min), session = random token | `dashboard.test_bulk_accounts` 30 OK |

Deviations from §9, all deliberate:
- The L-5 tests live in `dashboard/test_bulk_accounts.py` (next to the existing upload/preview/confirm and
  "passwords exist only in the download" tests) instead of `dashboard/tests.py`; `dashboard/tests.py` keeps the M-1 and M-3
  cases. The proposal's §9 item 3 named one file for both.
- `SingleApplicationTests` skips when `fastapi_core/` is not visible from the test's working tree (the Docker test run mounts
  only `fastapi_core` as `/app`, so the repository root is not there); it is validated natively and by CI when a CI exists.
- The M-4 guard reads `.dockerignore` instead of scanning every `.py` under `fastapi_core/`: the point of `D2=a` is that the
  local files stay on the owner's disk, so the question the test must answer is "what would the image contain", not "what
  exists locally".

Still open and out of scope (`D0=b`): L-1, L-2, L-3, L-4, L-6, L-7, L-8, L-9, L-10, L-11 — see
`docs/pilot/T7-SECURITY-REVIEW-REPORT.md` §2 (`Status`: OPEN). The PostgreSQL gate (`scripts/run_tests.sh pg`) closes T8.

