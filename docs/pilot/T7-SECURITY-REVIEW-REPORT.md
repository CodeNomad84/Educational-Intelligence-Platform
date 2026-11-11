# T7 — Whole-branch security review (Phase 1 pilot)

**Status: REPORT ONLY — every fix is DEFERRED to T8. No application code, settings, migration, template or
test was modified by this task.**

| Item | Value |
|---|---|
| Branch reviewed | `work/T7-security-review` (created from `phase-1/boot-security` @ `4a516c2`) |
| Review type | Static review of the whole branch diff surface plus the touched subsystems (read-only) |
| Code changes | **None.** `git diff --stat` below shows only this report and `PROGRESS.md` |
| Test suite | Deliberately **not** run (task constraint); no code was changed, so there is nothing new to test |
| Fix owner | **T8** (see §6 handoff list) |
| Severity scale | CRITICAL = unauthenticated cross-tenant/account takeover; HIGH = authenticated platform-wide impact; MEDIUM = scoped impact or defense-in-depth gap; LOW = hardening/hygiene |

## 0. How to read this report

* **Nothing here is fixed.** Each finding is a RECOMMENDATION for T8; this document must not be read as a
  statement that the branch is or is not safe to ship.
* Every finding carries a `path:line` produced by reading the current file on this branch (not from memory).
* Severity reflects **reachability on this branch as deployed by `docker-compose.yml`** (which runs
  `uvicorn main:app` for the AI service and gunicorn for Django), not a hypothetical deployment.
* Findings that are already recorded owner deferrals are marked as such and are **not** re-opened here.

## 1. Scope and method

Static review of: settings (`config/settings/{base,development,production}.py`), URL maps
(`config/urls.py`, `dashboard/urls.py`, app URL modules), the access layer (`students/access.py`,
`students/student_school.py`, `schools/entitlements.py`), every `role_required` / `school_page` /
`require_module` / `require_pilot_flag` usage, DRF (`students/views.py`, `students/serializers.py`,
`students/permissions.py`), all upload paths, the service-token bridge
(`config/service_auth.py`, `fastapi_core/auth.py`, `fastapi_core/main.py`), the LLM adapter
(`fastapi_core/llm_adapter.py`), `docqa/`, the legacy library routes (`dashboard/views.py`),
`dashboard/{throttle,middleware,password_reset,bulk_views}.py`, deployment files
(`docker-compose.yml`, `fastapi_core/Dockerfile`, `deploy/postgres/10-roles.sh`) and every template that
renders server data.

Method: grep sweeps for the classic defect classes (IDOR lookups, raw SQL, `|safe`, `mark_safe`,
`csrf_exempt`, CORS, `verify=False`, `SECRET`, upload reads, `str(e)`), then a manual read of every hit so
that each finding below has a real line reference. The IDOR sweep was exhaustive:
`grep -rn "get_object_or_404(" dashboard/ risk/ missions/ exams/ docqa/` — all 41 hits were read.

## 2. Summary

| ID | Severity | Finding | Location |
|---|---|---|---|
| H-1 | **HIGH** | Student import reads an unbounded upload (no byte cap) — memory/disk exhaustion, platform-wide | `django_core/students/views.py:248-272` |
| M-1 | MEDIUM | Legacy library upload calls the AI service with a 3000-second timeout | `django_core/dashboard/views.py:259-264` |
| M-2 | MEDIUM | AI service logs at DEBUG, including uploaded document text | `fastapi_core/main.py:37, :292-295` |
| M-3 | MEDIUM | Raw exception text / upstream response bodies returned to clients | `students/views.py:367,385,419`; `dashboard/views.py:163,168,205,281,310`; `fastapi_core/main.py:149,199,209,219,233` |
| M-4 | MEDIUM | Second, unauthenticated FastAPI application shipped in the image (`main_HuggingFace.py`) with an unscoped RAG backend | `fastapi_core/main_HuggingFace.py:98-256` |
| M-5 | MEDIUM | Bulk student import (API) writes PII with no audit event | `django_core/students/views.py:248-419` |
| L-1 | LOW | Logout works over GET (CSRF-free logout) | `django_core/dashboard/views.py:50-52` |
| L-2 | LOW | AI service `/docs` and `/openapi.json` are unauthenticated | `fastapi_core/main.py:57` |
| L-3 | LOW | Disabled AI upload route buffers the whole file with no size cap | `fastapi_core/main.py:235-247` |
| L-4 | LOW | `FEEDBACK_URL` is not scheme-validated before being rendered into `href` | `config/settings/base.py:124`; `dashboard/templates/dashboard/base.html:124` |
| L-5 | LOW | Parsed national ids held in the DB session row for up to 30 minutes | `django_core/dashboard/bulk_views.py:23-33,48` |
| L-6 | LOW | Bare `except: pass` hides AI-service failures | `django_core/dashboard/views.py:227-228` |
| L-7 | LOW | Docstring claims the superuser sees all students; the code grants nothing | `django_core/students/access.py:169-171` vs `:130-137` |
| L-8 | LOW | `TokenRefreshView` is unthrottled and refresh tokens are not blacklisted on logout | `django_core/config/urls.py:19-20` |
| L-9 | LOW | Image default command runs uvicorn with `--reload` | `fastapi_core/Dockerfile` (final `CMD`) |
| L-10 | LOW | No fail-closed `DEFAULT_PERMISSION_CLASSES` for DRF | `config/settings/base.py:90-102` |
| L-11 | LOW | Every container runs as root; the Django image default command is `runserver` | `django_core/Dockerfile:1-15`, `fastapi_core/Dockerfile:1-27`, `docker-compose.yml:27-188` |

**CRITICAL: none found.** No unauthenticated data path, no cross-tenant read/write, and no secret exposure
was found on this branch; §4 lists what was checked and came back clean.

## 3. Findings

### H-1 (HIGH) — `POST /api/students/import/` reads an unbounded upload

**Location:** `django_core/students/views.py:248-272` (the `import` action: decorator `:248-249`, method
`:250`, `resolve_student_school` `:256-261`, file read `:268-272`)

**What happens.** The action validates *which school* the rows go to before touching the file (good), then
reads it with no size limit at all:

```python
270:  df = pd.read_csv(TextIOWrapper(file, encoding='utf-8-sig'), converters=TEXT_COLUMNS)
272:  df = pd.read_excel(BytesIO(file.read()), converters=TEXT_COLUMNS)
```

It is the only upload path on the branch without a byte cap. Every other one caps the payload before use:

| Path | Cap |
|---|---|
| `dashboard/bulk_accounts.py:36` (`MAX_FILE_BYTES = 2_000_000`) | 2 MB |
| `risk/catalog_services.py:18` (`MAX_BYTES = 1_000_000`) | 1 MB |
| `docqa/extract.py:6` (`MAX_BYTES = 1_000_000`) | 1 MB |
| `exams/csv_import.py:17` (`MAX_BYTES = 200 * 1024`) | 200 KB |
| `dashboard/views.py:246` (legacy library) | 10 MB |

**Risk impact.** `DATA_UPLOAD_MAX_MEMORY_SIZE` does not bound file uploads; Django spools the body to
`/tmp` in the Django container. An authenticated SchoolAdmin can therefore (a) fill the container's disk
with one request — the host volume is shared with Postgres and MinIO in the default compose file — and
(b) make `pd.read_csv` / `pd.read_excel` materialise an arbitrarily large frame (xlsx additionally
decompresses in memory). The result is an out-of-memory kill of the Django workers **for every tenant on
the instance**, i.e. cross-tenant impact from a single request. The precondition is an authenticated
account (`IsAdminUser` via `get_permissions`), so this is privilege abuse, not anonymous access — hence
HIGH, not CRITICAL. It is scriptable: no rate limit exists on uploads.

**Recommended remediation (T8).**
1. Reject `file.size > MAX_IMPORT_BYTES` (same constant family as `bulk_accounts`: 2 MB) **before** reading
   the stream, returning `400` with a fixed message.
2. Read at most `MAX_IMPORT_BYTES + 1` bytes and treat a longer stream as an error (the pattern already
   used by `risk/views.py:272` and `docqa/views.py:87`).
3. Cap the parsed row count (`len(df)`) with a per-school limit and reject beyond it.
4. Add `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` to `config/settings/base.py` as
   defense in depth, plus a regression test that a 3 MB upload is refused with `400`.

---

### M-1 (MEDIUM) — Legacy library upload uses a 3000-second timeout to a disabled service

**Location:** `django_core/dashboard/views.py:259-264` (`timeout=3000` on `:263`)

**What happens.** `upload_document_view` (SchoolAdmin) forwards a ≤10 MB file to
`http://fastapi:8001/upload-document/` with `timeout=3000` (50 minutes). That route is Phase-1 disabled
(`fastapi_core/auth.py::disabled_in_phase1` answers `403`), so today the call returns immediately and the
long timeout is dormant. `delete_document_view` (`:297-301`) uses 5 s and `library_view` (`:222-224`) uses
5 s — this call is the outlier by three orders of magnitude.

**Risk impact.** A Django worker is blocked for the whole timeout. If the AI container hangs, is slow, or a
proxy black-holes the connection, each SchoolAdmin POST pins one gunicorn worker for up to 50 minutes; with
a small worker pool, a handful of requests (or one retrying form) takes the application down for all
schools. Compose starts gunicorn with `--timeout 3000` (`docker-compose.yml:52`), so gunicorn will not even
recycle the pinned worker. Secondary: the 10 MB body is materialised in the Django process (`uploaded_file.read()` on `:258`)
before being sent.

**Recommended remediation (T8).** Prefer deleting the route: the Phase-1 ingestion path is the P7-5
`docqa` flow (`docqa/views.py`, `docqa/extract.py`, `docqa/services.py`), which already caps bytes, screens
PII and audits. If the legacy page must stay, set the timeout to ≤ 30 s, stream the file instead of
`read()`, and return a fixed error message (see M-3).

---

### M-2 (MEDIUM) — AI service logs at DEBUG and logs document content

**Location:** `fastapi_core/main.py:37` (`logging.basicConfig(level=logging.DEBUG)`), `main.py:292-295`
(`logger.debug(f"نمونه سند اول: {documents_to_add[0]}")`), also `main.py:238`, `:298`;
`fastapi_core/rag_service.py:19` (`logging.basicConfig(level=logging.INFO)`, repeated at
`main_HuggingFace.py:186`).

**What happens.** The AI process starts a root logger at DEBUG with no configuration, so every
`urllib3`/`psycopg2`/`httpx` DEBUG line, every SQL statement and every provider request shape lands in the
container log. `:295` writes the **first chunk of an uploaded document** (up to `CHUNK_CHARS` characters)
into the log at DEBUG.

**Risk impact.** Container logs are collected, rotated and shipped by operators and are not covered by the
Django audit rules. Once the ingestion route is re-enabled (a one-line dependency swap in
`fastapi_core/auth.py`), school document text — the `docqa` screener exists precisely to keep student PII
out of such documents — would be copied into logs where it is retained and readable by anyone with host
access. Log volume is also a cost/DoS lever (the RAG path logs per chunk).

**Recommended remediation (T8).** Delete `:295` (never log content), take the level from the environment
with a WARNING default, and mirror `config/settings/production.py:80-86` (explicit handlers, no request
bodies). Add a test asserting that no `logger.debug` call receives document text.

---

### M-3 (MEDIUM) — Raw exception text and upstream bodies returned to clients

**Location:**
* `django_core/students/views.py:367`, `:385` (per-row `str(e)`), `:419` (outer
  `f'خطا در پردازش فایل: {str(e)}'` with HTTP 500)
* `django_core/dashboard/views.py:163` (`response.text` of the AI service), `:168`, `:205`, `:281`,
  `:310` (`str(e)` of `requests` exceptions)
* `fastapi_core/main.py:149`, `:199`, `:209`, `:219`, `:233` (`detail=f"... {str(e)}"`)

**Risk impact.** Internal detail is reflected to the caller: ORM/validation messages, driver messages
(`psycopg2`), pandas/openpyxl parser text and upstream AI-service bodies (`:163` puts the AI service's
response body into the page). This is reconnaissance material (table/column names, library versions,
internal hostnames such as `Failed to establish a new connection: fastapi:8001`), and `:163` can echo
returned document/AI text into the SchoolAdmin page. No stack traces or SQL text were observed leaking
(`DEBUG` is `False` in production), so this is disclosure of internals, not credential exposure.

**Recommended remediation (T8).** Log the exception with `exc_info=True` at the boundary, return a fixed
message plus an opaque correlation id, and never include `str(exc)` or `response.text` in a user-visible
payload. The import path should map failures onto its existing fixed-vocabulary row errors.

---

### M-4 (MEDIUM) — A second, entirely unauthenticated FastAPI application ships in the same image

**Location:** `fastapi_core/main_HuggingFace.py:98-256` — `/` `:98`, `/predict/` `:128`, `/chat/` `:158`,
`/documents/` `:166`, `/documents/search/` `:174`, `/upload-document/` `:188`, `/documents/list/` `:256`.
**No route declares a dependency** (`grep -n "Depends("` returns nothing for that file), so there is no
service-token check, no role check and no school scoping. Its backend
`fastapi_core/rag_service_HuggingFace_Models.py` contains **no `school_id` at all** (its only "school"
strings are the literals in `DB_NAME` / `DB_USER` at `:12-13`), i.e. every tenant's documents are one query
away.

**Reachability (important).** Not reachable in the current deployment: `docker-compose.yml:131` runs
`uvicorn main:app`, and `docker-compose.yml:115-117` publishes no port for the service. This is already a
recorded owner deferral — `docs/PHASE1_DEFERRED_ITEMS.md:14` item 7 ("Untracked HuggingFace FastAPI
variants … not reviewed for service-auth or ACL parity"). It is restated here only so the severity is on
record: it becomes **CRITICAL the moment it is adopted**.

**Risk impact.** Anyone who runs `uvicorn main_HuggingFace:app` (or "fixes" the legacy import mismatch —
`main_HuggingFace.py:18` imports `rag_service`, whose functions now require a `school_id`, so the legacy
routes currently raise `TypeError`) exposes anonymous, cross-tenant document read/write and anonymous risk
scoring on the compose network.

**Recommended remediation (T8, minimal).** Either delete both files or move them out of the importable
package (e.g. `docs/experiments/`), and add a guard test in the style of
`fastapi_core/tests/test_exposure.py` that fails if a second `FastAPI(` application exists under
`fastapi_core/`. Full ACL parity stays a deferred L3 decision for the owner.

---

### M-5 (MEDIUM) — Bulk student import writes PII with no audit event

**Location:** `django_core/students/views.py:248-419` (the whole `import` action). Reads on the same
viewset are audited (`:227` list, `:232` detail, `:234` national-id reveal) and the page-level bulk account
creation is audited (`dashboard/bulk_views.py:93`, `audit.BULK_ACCOUNTS`, counts only). The API import —
which creates and updates student records, including national ids — records **nothing**.

**Risk impact.** A mass create/update of a school's student records (or a repeated import that silently
overwrites rows) leaves no trace in `AuditEvent`, so the SchoolAdmin's audit page cannot answer "who loaded
this roster, and when", and an incident responder cannot distinguish a legitimate import from tampering.
This contradicts the read-side policy (`schools/audit.py:1`: "who/what/when only") and the project's audit
rules.

**Recommended remediation (T8).** Add one event per import, counts only (`s<created>u<updated>e<errors>`),
in the same style as `BULK_ACCOUNTS`, and extend the vocabulary in `schools/audit.py`. No names, no
national ids.

---

### L-1 (LOW) — Logout works over GET

**Location:** `django_core/dashboard/views.py:50-52` (`def logout_view` … `logout(request)`), routed without
`@require_POST`.

**Risk impact.** A third-party page can sign a user out with `<img src="…/logout/">` (a CSRF-free state
change). No data is exposed; the impact is a denial-of-service nuisance and noisy audit-free sessions.

**Recommended remediation (T8).** `@require_POST` (or `django.contrib.auth.views.LogoutView`), with a POST
form in the header menu; keep everything else identical.

---

### L-2 (LOW) — AI service `/docs` and `/openapi.json` are unauthenticated

**Location:** `fastapi_core/main.py:57` (`app = FastAPI(title=…, description=…, version=…)`, so `docs_url`
and `openapi_url` keep their defaults). The service is not published to the host
(`docker-compose.yml:115-117`), so only containers on the compose network can reach it.

**Risk impact.** Any container on the network (or a future proxy rule) can enumerate every route, schema and
parameter name without a token — useful reconnaissance for a service that is otherwise token-gated.

**Recommended remediation (T8).** `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)` in
production (env-gated for development), and add it to `fastapi_core/tests/test_exposure.py`.

---

### L-3 (LOW) — Disabled AI upload route buffers the whole file with no size cap

**Location:** `fastapi_core/main.py:235-247` — `suffix` check on `:240-242`, then
`content = await file.read()` on `:245` with no bound; the text extractors on `:249-263` are unbounded too.

**Risk impact.** Inert today (`disabled_in_phase1` answers `403` before the handler runs) and the container
is not published, so this is not exploitable now. It is a latent DoS/PII path: the moment the route is
re-enabled, a single authenticated Admin can exhaust the AI container's memory, which also serves
`/llm/complete/`.

**Recommended remediation (T8).** Cap the incoming bytes (and `content-length`) at the same 10 MB ceiling
Django uses, read in bounded chunks, and reuse `docqa/extract.py`'s member/uncompressed limits for docx/pdf.

---

### L-4 (LOW) — `FEEDBACK_URL` is not scheme-validated before being rendered into `href`

**Location:** `django_core/config/settings/base.py:124` (`FEEDBACK_URL = os.environ.get('FEEDBACK_URL',
'').strip()`), rendered at `django_core/dashboard/templates/dashboard/base.html:122-124` (`<a href="{{
FEEDBACK_URL }}">`). Auto-escaping does not neutralise a `javascript:` scheme.

**Risk impact.** An operator (or a compromised env file) can set `FEEDBACK_URL=javascript:…` and get script
execution in the session of every authenticated staff user — a stored XSS with operator-level preconditions.
The comment at `base.py:121-123` already states the link must be a fixed URL; only the code is missing the
check.

**Recommended remediation (T8).** Validate at startup: empty, or `http`/`https` with a host; otherwise fall
back to empty and log a warning (the fail-closed style used by `production.py:11-22`). Alternatively
render it as text unless `urlsplit(...).scheme in ('http', 'https')`.

---

### L-5 (LOW) — Parsed national ids held in the DB session row for up to 30 minutes

**Location:** `django_core/dashboard/bulk_views.py:23-33` (`SESSION_KEY`, `SESSION_SECONDS = 30 * 60`,
`_stored`) and `:48` (`request.session[SESSION_KEY] = {... 'rows': parsed}`).

**Risk impact.** The parsed workbook rows — names, national ids, parent national ids — live in the server-side
session record until confirm/cancel/timeout. That is a second copy of PII outside the student tables, with
the session table's own retention, readable by anyone with database access and not visible in the audit
trail.

**Recommended remediation (T8, optional).** Keep only a checksum + row count in the session and re-parse
the (transient) upload on confirm, or trim the stored fields to what the preview needs. Document the current
choice if it is kept.

---

### L-6 (LOW) — Bare `except: pass` hides AI-service failures

**Location:** `django_core/dashboard/views.py:227-228`.

**Risk impact.** A misconfigured or failing AI service is indistinguishable from "no documents" for the
operator; a persistent failure (or an actively failing auth bridge) is silently swallowed, which slows
detection of the very problems this review cares about.

**Recommended remediation (T8).** `except (ImproperlyConfigured, requests.RequestException) as exc:` + 
`logger.warning(...)` (no message content) and, if useful, a template hint.

---

### L-7 (LOW) — Docstring claims the superuser sees all students; the code grants nothing

**Location:** `django_core/students/access.py:169-171` (docstring: "a superuser: all (explicit temporary
branch until S8)") versus `:130-137` (`_school_admin_q` returns `None` when `SchoolAdmin` is not held) and
`:63` (`roles_for` strips superusers).

**Risk impact.** No live vulnerability — the code is deny-by-default and the docstring is stale. The risk is
that a future editor "implements the documentation" and turns a superuser into a cross-tenant read bypass,
i.e. the comment is now an attractive nuisance in the most sensitive file of the branch.

**Recommended remediation (T8).** Delete the superuser clause from the docstring (and from any sibling
docstring such as `visible_attendances`), or state explicitly "a superuser gets nothing here (Slice 0);
superuser access is a separate, unreviewed decision (S8/0038)". Documentation-only change.

---

### L-8 (LOW) — Refresh endpoint unthrottled, refresh tokens not blacklisted on logout

**Location:** `django_core/config/urls.py:19-20` — `/api/token/` is throttled
(`dashboard/throttle.py:99-110`), `/api/token/refresh/` is the stock `TokenRefreshView`.

**Risk impact.** Refresh attempts are not rate-limited (they carry a valid signed token, so this is minor),
and `logout_view` does not revoke anything: a copy of a refresh token stays usable for its lifetime after
logout. `SIMPLE_JWT = {'CHECK_REVOKE_TOKEN': True}` (`base.py:85-88`) already kills tokens on password
change, which covers the dangerous case (account takeover after reset).

**Recommended remediation (T8, optional).** Apply the same throttle class to the refresh view and document
the token lifetime/rotation policy; full blacklist support (`token_blacklist` app) is a DECISION REQUIRED
(it needs a migration).

---

### L-9 (LOW) — Image default command runs uvicorn with `--reload`

**Location:** `fastapi_core/Dockerfile` (final `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port",
"8001", "--reload"]`). `docker-compose.yml:131` overrides it without `--reload`, so compose is fine.

**Risk impact.** Anyone running the image directly (`docker run`, a future Kubernetes manifest, or an
`openapi`-style side deployment) gets a file-watching development server in production: extra CPU, restarts
on file change, no graceful shutdown. Not a data-exposure issue by itself.

**Recommended remediation (T8).** Drop `--reload` from the image; keep the watcher as a compose-only
override if it is still wanted for development.

---

### L-10 (LOW) — No fail-closed `DEFAULT_PERMISSION_CLASSES` for DRF

**Location:** `django_core/config/settings/base.py:90-102` — `DEFAULT_AUTHENTICATION_CLASSES`, filter
backends and pagination are set, `DEFAULT_PERMISSION_CLASSES` is not (DRF's default is `AllowAny`). The one
viewset in the tree is correct (`students/views.py` `get_permissions` + `IsAuthenticated`/`IsAdminUser`).

**Risk impact.** Defense in depth: the next viewset added without an explicit permission class would be
readable anonymously, and the mistake would not be caught by any existing test.

**Recommended remediation (T8).** Set `'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated']`
(explicitly inheriting `AllowAny` where genuinely needed) and/or add a check that every `APIView`/`ViewSet`
declares permissions.

---

### L-11 (LOW) — Every container runs as root; the Django image default command is `runserver`

**Location:** `django_core/Dockerfile:1-15` and `fastapi_core/Dockerfile:1-27` — neither declares `USER`, and
no service in `docker-compose.yml` (`:27-188`) sets `user:`. `django_core/Dockerfile:15` is
`CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]`; compose overrides it with gunicorn
(`docker-compose.yml:51-52`), so the dev server is only reached by a direct `docker run`.

**Risk impact.** Defense in depth, not a live vulnerability (no write primitive was found in §3/§4): the
Django process runs as root **with `./django_core` mounted read-write** (`docker-compose.yml:35`), so any
future file-write or template-injection bug escalates from "renders attacker data" to "persists code in the
application tree". Same for the other services, including the AI container on the shared compose network.

**Recommended remediation (T8).** Add a non-root `USER` to both images; in production drop the read-write
source mount (mount read-only, plus a separate writable volume for `staticfiles`/`media`); remove the
`runserver` default command.


## 4. Checked and clean (CURRENT)

These were examined and produced no finding; they are listed so T8/T9 do not redo the work and so a later
change that breaks one of them is recognisable as a regression.

| Area | Result |
|---|---|
| Multi-tenant / IDOR sweep | All 41 `get_object_or_404` calls in `dashboard/`, `risk/`, `missions/`, `exams/`, `docqa/` are scoped by a `visible_*` / `*_students` queryset, a `school=` filter, `staff_queryset(school, kind)`, or an explicit follow-up scope check (`exams/views_results.py:31-33`, `exams/views.py:291-296`, `:304-309`). No unscoped object read found. |
| Access layer | `students/access.py` denies by default: `visible_students` returns `none()` without a grant (`:172-173`), an empty SchoolAdmin school set grants nothing (`_school_admin_q`, `:130-137`), a superuser holds no role (`:63`), and `student_school.resolve_student_school` requires an explicit target for a superuser and re-checks membership (`:86-104`). |
| Service token (Django → FastAPI) | 60 s TTL; `iss`/`aud`/`exp`/`sub` required; HS256; weak or placeholder secrets fail closed (`config/service_auth.py:24-46`, `fastapi_core/auth.py:78-101`); `scope: "ai"` tokens are refused on non-AI routes (`auth.py:118-131`); the AI school always comes from the signed claim, never from the request body (`main.py:180`, `:205`). |
| Raw SQL | Exactly one `connection.cursor()` (`students/student_school.py:54`) and it is introspection only — no interpolation, no user input. No `RawSQL`, `.extra()` or `.raw()` anywhere in application code. |
| Secrets | No secret file is tracked (`git ls-files` shows only `.env.example` variants); `.env` / `.env.*` are ignored (`.gitignore:5-7`); `SERVICE_JWT_SECRET` and `SECRET_KEY` have no defaults and fail closed (`config/settings/production.py:11-22`, `config/service_auth.py:43-46`); the LLM adapter never returns or logs a key (`fastapi_core/llm_adapter.py:36-58`). |
| CSRF | `CsrfViewMiddleware` is active; every mutating view is `@require_POST` / POST-only or method-checked; `_nid_script.html:5` sends `X-CSRFToken`; there is no `csrf_exempt` in the tree. Only L-1 (GET logout) is a gap. |
| CORS | No `django-cors-headers`, no `CORS_*` setting, no CORS middleware on either service → browsers block cross-origin reads by default. Nothing to fix; do not add one without a proposal. |
| XSS | No `\|safe`, no `mark_safe`, no `format_html` with unescaped input (`dashboard/templatetags/eip_ui.py:18`, `:42` escape); inline `<script>` blocks interpolate only the CSRF token and `{% url %}` output. |
| Upload validation elsewhere | Extension plus magic/decompression caps in `docqa/extract.py:16-60` and `risk/catalog_services.py:116-123` (zip member and uncompressed-size limits); byte caps in every path except H-1. |
| Brute force | The login page and `/api/token/` share one throttle (`dashboard/throttle.py:99-110`, `views.py:30`); lockout keys on username **and** address; `X-Forwarded-For` is honoured only behind configured proxies (`throttle.py:52-60`); no user enumeration (identical answer for unknown names). |
| Forced password change | `dashboard/middleware.py:12-25` confines a flagged account to the change page on every path, including the API. |
| Password reset | Random temporary password, shown once with `Cache-Control: no-store` (`password_reset.py:70-74`), never stored and never audited; hourly cap plus a capped event for the grade lead; `404` for out-of-scope targets. |
| PII field policy | `students/serializers.py:74-84` masks `national_id` on list and on write responses and drops identity fields for teacher-tier rows; the one detail read that returns the full id is audited (`students/views.py:234`). |
| Security settings | `production.py:55-77`: `DEBUG=False` fixed, SSL redirect, secure cookies, staged HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `CSRF_TRUSTED_ORIGINS` from env. |
| Notification / report scoping | `risk/notifications.visible_notifications`, `missions/views_reports._student`, `exams` analytics small-group suppression (`MIN_GROUP = 5`) and the `full_tier=True` guard on `student_360` / `reveal_national_id` all re-check scope at read time. |
| AI caps | `schools/ai_guard.consume` serialises on `select_for_update` (`ai_guard.py:33-43`), so the per-school daily/monthly counters cannot be raced. |
| Compose / infra | Only Django and Ollama publish host ports and both bind `127.0.0.1` (`docker-compose.yml:33`, `:181`); Postgres, Redis, MinIO and FastAPI publish none. The Postgres init scripts create schema-scoped roles (`school_owner` DDL, `school_app` DML) and the runtime never connects as the bootstrap superuser (`docker-compose.yml:50`, `:56`, `:76`). FastAPI deliberately does not receive `.env` (`:122-126`). Containers do run as root — that is L-11, not repeated here. |

## 5. Limits of this review

### 5.1 NOT VERIFIED

This review is **static only**; per the task constraint no command was executed against a running stack and
no new test was written. Specifically not verified:

| Item | Why it is NOT VERIFIED |
|---|---|
| Dynamic exploitation of any finding | No request was sent; H-1's impact is reasoned from Django's upload behaviour + `pandas` semantics, not measured. |
| Dependency/CVE exposure | No `pip-audit`/`trivy`/`safety` run. Pinned versions (e.g. `torch==2.0.1` at `fastapi_core/Dockerfile:16`) are outside this review. |
| Per-role × per-endpoint authorization matrix | The IDOR sweep is a static read of every lookup; it is not an authorization test that proves each role gets the expected `200`/`403`/`404`. |
| Pilot-flag gating of every route | Decorators (`require_pilot_flag`, `require_module`) were read, not exercised route by route. |
| Throttle effectiveness under load | Constants and keying were read (`dashboard/throttle.py`); no load test, no observation of the lockout in a live process. |
| Live Postgres privileges | Derived from `deploy/postgres/*.sql` and compose env; not checked with `\du` / `\dp` on the deployment. |
| Log retention and shipping | M-2's impact depends on the operator's log pipeline, which is not in the repository. |

### 5.2 DECISION REQUIRED (owner)

1. **M-4** — delete the HuggingFace variant outright, or keep it quarantined outside the package as an
   experiment? (It is already deferral item 7; T8 needs a decision to act.)
2. **L-8** — is `token_blacklist` in scope? It adds an app and a migration, so it cannot be a silent fix.
3. **L-5** — keep the parsed roster in the session and document it, or re-parse on confirm?
4. **H-1** — pick the import ceiling (2 MB like `bulk_accounts`, or a row cap derived from the school's
   student count) so T8 does not invent the policy.

### 5.3 Truth labels used in this document

Everything in §2–§4 is **CURRENT** as observed at `4a516c2` on `work/T7-security-review`. Nothing here is
**TARGET**. "Clean" in §4 means "no issue found by reading"; it is not a test result. No item is marked
FIXED, because nothing was fixed by this task.

## 6. T8 handoff

Suggested order — smallest diffs and highest value first. Sizes are rough (S ≤ ~30 lines + one test).

| # | Finding | First step in T8 | Size |
|---|---|---|---|
| 1 | H-1 | Byte cap + row cap + `400` + regression test in `students/views.py` | S |
| 2 | M-5 | One audit event per import, counts only, plus the vocabulary in `schools/audit.py` | S |
| 3 | M-3 | Remove `str(e)` / `response.text` from every client-visible payload; log with `exc_info=True` | S–M |
| 4 | M-2 | Delete the DEBUG content line; log level from the environment | S |
| 5 | M-1 | Delete the legacy library route, or `timeout ≤ 30` + stream the file | S |
| 6 | M-4 | Delete/quarantine `main_HuggingFace*.py` + second-app guard test | S (after decision 5.2.1) |
| 7 | L-1, L-2, L-9, L-10, L-11 | POST logout, disable `/docs`, drop `--reload`, DRF default permission, non-root `USER` | S each |
| 8 | L-3, L-4, L-6, L-7 | Size cap, `FEEDBACK_URL` scheme check, real `except`, docstring correction | S |
| 9 | L-5, L-8 | Only after the decisions in §5.2 | M |

**Proposed acceptance for T8 (not agreed yet).** Each of H-1 and M-1…M-5 closed with a test that fails on
the T7 branch and passes on the T8 branch; the full suite green on sqlite and then pg, with the output file
read; §2 of this report amended in place with a `Status` column and a commit hash per finding; L-items
either closed or explicitly re-deferred with a reason.

**Do not do in T8 without a proposal:** anything that changes the access model (`students/access.py`
semantics), the audit vocabulary's meaning, the service-token claims, or the DRF permission model beyond the
`DEFAULT_PERMISSION_CLASSES` default — those are L2/L3 and need `docs/changes/NNNN-*.md` first.

---

*End of report. Fixes are T8's; this task changed no application code.*








