# 0040 — Dual frontend (frontend-men / frontend-women): CORS, session login and `/api/auth/me/` (CHANGE PROPOSAL — no application code changed)

Level: **L3** · Status: **APPROVED 2026-11-13** (owner approved the vertical slice: D0=a, D1=a, D2=a, D3=a, D4=a, D5=a, D6=a, D7=a, D8=a, D9=a; §18's D10-D12 resolved as fetch / no login route yet / backend first) · Date: 2026-11-13 · Implementation: `docs/changes/0040-dual-frontend-integration-REPORT.md` · ADR: `docs/adr/0014-two-json-frontends.md`
Branch `work/dual-frontend-integration`, created **from `phase-1/boot-security`** per STANDING RULES.

**This task changed no code, no setting, no dependency, no migration and no test, and ran no test.** It created this
file only. Everything below is labelled **CURRENT** (verified in this task, command or file quoted), **TARGET**
(proposed, not built), **DECISION REQUIRED** (yours) or **DEFERRED**. No item is fixed. No test is claimed to pass.

Why a proposal and not an implementation: the request contains (a) a **new third-party dependency**
(`django-cors-headers`), (b) a **new authentication endpoint and session/CSRF policy**, and (c) a decision that
**reopens ADR-0013 (SPA DEFERRED)**. `docs/CHANGE_PROCESS.md` classifies all three as **L3** ("new dependency",
"authN/authZ", "breaking API"). `docs/pilot/T7-SECURITY-REVIEW-REPORT.md:418` already recorded that CORS was
deliberately absent: *"Nothing to fix; do not add one without a proposal."* This is that proposal.

---

## 0. Cross-walk to `docs/templates/CHANGE_PROPOSAL.md`

| Template item | Where it is answered |
|---|---|
| 1 Requirement | §1 — the request as received, and the three scope conflicts inside it |
| 2 Current behavior | §2 — verified evidence, one row per check, with the command/file |
| 3 Desired behavior | §4 — the proposed settings, endpoints, payloads and status codes |
| 4 Affected modules | §4 (`config/settings`, `dashboard/auth_api.py`, `config/urls.py`), §12 |
| 5 Data impact | §6 — no migration for the minimum; one migration only if D5=b |
| 6 API impact | §7 — four new endpoints, CSRF/session semantics, no change to existing routes |
| 7 Frontend impact | §8 — neither frontend repository is touched; the AI call inside `frontend-women` is flagged |
| 8 AI impact | §9 — `frontend-women` already sends roster data to an external model (blocking, D9) |
| 9 Security impact | §10 — CORS+credentials, CSRF, throttle, enumeration, middleware, audit |
| 10 Testing strategy | §11 — a new auth/CORS test module plus the full sqlite+pg gate |
| 11 Documentation impact | §12 |
| 12 Customization impact | §13 — origins from the environment, no school-specific constant |
| 13 Risks | §14 |
| 14 Recommendation | §15 — the decisions D0–D9, each with a recommended option |
| (extra) Alternatives | §5 — proxy / JWT / BFF / wildcard, and why each was rejected or deferred |

---

## 1. Requirement as received (CURRENT) and the three conflicts in it

The task asks for: (1) `django-cors-headers` in `INSTALLED_APPS`/`MIDDLEWARE` with
`CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:5174", "http://localhost:8080"]` and
`CORS_ALLOW_CREDENTIALS = True`; (2) `SessionAuthentication` and `BasicAuthentication` in DRF; (3) a JSON
`POST /api/auth/login/` that "establishes the Django session"; (4) `GET /api/auth/me/` returning user, role,
`school_id` and "gender/theme scope".

Three conflicts must be resolved before any code, and none of them is a mechanical edit:

1. **Path.** The brief names `config/settings/base.py`. **CURRENT:** there is no `config/` package at the repository
   root. `ls django_core/config/settings` → `base.py demo.py development.py __init__.py production.py
   restore_check.py test_postgres.py test_sqlite.py`. The real file is `django_core/config/settings/base.py`
   (`ROOT_URLCONF = 'config.urls'`, `BASE_DIR` = `django_core/`). The brief's path is stale; I will not create a
   second settings package.
2. **ADR-0013.** `docs/adr/0013-mvp-frontend-server-rendered.md` (ACCEPTED 2026-11-01): MVP frontend =
   server-rendered Django templates + Bootstrap 5 RTL; *"React only as islands … A full React SPA is **DEFERRED**
   until after pilot feedback. **Reopening it needs a new ADR.**"* Two Vite/TanStack frontends on their own ports with
   a JSON session API is exactly that deferred case, and STANDING RULES say "No SPA/React (ADR-0013)". A CORS
   proposal cannot silently overturn an accepted ADR; **D0** asks for the ADR decision.
3. **Data model.** "gender/theme scope" has **no source in the schema**. `grep -rni 'gender'` over
   `students/models.py`, `accounts/models.py`, `schools/models.py` → **no match**. `School` has `name`, `code`,
   `grade_leads_may_reset_passwords`, AI caps — no audience/sex/theme. `User` in the scaffold `django_core/accounts/`
   has `role`, `mobile`, `national_id`, `school` — and that app is **not installed** (§2.7). Returning a
   `gender_scope` therefore means inventing data; **D5** asks where it should live.

---

## 2. CURRENT — what was verified in this task

| # | Check | Evidence (command / file) | Result |
|---|---|---|---|
| 1 | Settings package | `ls django_core/config/settings` | `base/development/production` are under `django_core/`; no root `config/` |
| 2 | `django-cors-headers` installed? | `django_core/.venv/bin/python -c "…find_spec('corsheaders')"` | `corsheaders spec: None` |
| 3 | Dependency declared? | `django_core/requirements.txt` | **absent** (Django 5.2.18, DRF 3.18.3, simplejwt 5.5.1, pandas, psycopg2, celery, redis, gunicorn, django-redis, PyJWT) |
| 4 | Any CORS setting/middleware? | repo-wide `grep -rn 'corsheaders\|CORS_'` (excluding `frontend-*`) | one hit: `docs/pilot/T7-SECURITY-REVIEW-REPORT.md:418` — *"No `django-cors-headers` … browsers block cross-origin reads by default. Nothing to fix; do not add one without a proposal."* |
| 5 | DRF authentication classes | `django_core/config/settings/base.py:96-100` | `JWTAuthentication`, then `SessionAuthentication`. **No `BasicAuthentication`** |
| 6 | DRF default permissions | same block, lines 96-108 | `DEFAULT_PERMISSION_CLASSES` is **not set** → DRF's `AllowAny` default; every view must declare its own permissions |
| 7 | Existing auth routes | `django_core/config/urls.py:19-20, 26` | `POST /api/token/` (`ThrottledTokenObtainPairView`), `POST /api/token/refresh/`, `DefaultRouter` under `/api/` (`students`) |
| 8 | `/api/auth/login/`, `/api/auth/me/` exist? | `grep -rn 'api/auth' django_core --include=*.py` | **no match** — both endpoints are **NOT YET IMPLEMENTED** |
| 9 | HTML login | `dashboard/urls.py:6-9`, `dashboard/views.py:39-64` | `GET/POST /` and `/login/`; form POST only (`request.POST`), `authenticate()`, `login()`, redirect to `home_url_for()` |
| 10 | Login brute-force control | `dashboard/throttle.py:1-143`; `dashboard/test_login_throttle.py` | per-username (5) and per-IP (20) locks in 900 s, uniform answer; also wraps `admin.site.login` and `/api/token/`; a `must_change_password` account cannot mint a JWT (403) |
| 11 | Usernames are national IDs | `dashboard/throttle.py:1-12` | guessable identifiers; any new credential endpoint must reuse the same counters |
| 12 | Forced password change | `dashboard/middleware.py:9-20` | every path except `/static/`, the password-change page and logout is **302-redirected** while `AccountProfile.must_change_password` — this includes `/api/…`, so a JSON client receives an HTML redirect |
| 13 | Roles | `students/access.py:23-47` | Django **groups**: `SchoolAdmin`, `Teacher`, `GradeLead`, `Counselor`, `Student`, `Parent`, plus `PlatformAdmin` (deliberately not in `ALL_ROLES`); `roles_for()` returns the set, empty for anonymous/inactive |
| 14 | School scope | `schools/entitlements.py:87-101` | `user_school_ids(user)` = admin memberships ∪ staff school ∪ own student record ∪ schools of visible students (parents); empty for anonymous/inactive |
| 15 | `accounts.User.role` usable? | `INSTALLED_APPS` (`base.py:17-35`), `AUTH_USER_MODEL` (no hit in `django_core/config`), `docs/CHANGE_GUIDE.md:66` | **no**: `accounts` is not installed, `AUTH_USER_MODEL` is unset (default `auth.User`), and the folder is hidden by `.git/info/exclude`. `role` must come from `roles_for()` |
| 16 | Gender / theme fields | `grep -rni 'gender'` over the three model files | **no match** in `students`, `accounts` or `schools` |
| 17 | Audit vocabulary | `schools/audit.py:6-45` | `VIEW_DETAIL`, `NATIONAL_ID_REVEAL`, `PASSWORD_RESET`, `BULK_ACCOUNTS`, … — **no `LOGIN` / `LOGIN_FAILED` action** |
| 18 | Frontends | `frontend-men/`, `frontend-women/` (both **untracked**, `git status`) | TanStack Start + Vite + Cloudflare Worker (`src/server.ts`), `vite dev`; neither contains a Django URL or an `/api/` call today |
| 19 | Frontend AI call | `frontend-women/src/lib/mentor-chat.functions.ts:68-95` | a `createServerFn` that sends `rosterDigest()` + `recentNotes` + the prompt to `@lovable.dev/ai-gateway`, model `openai/gpt-6-astra` |
| 20 | Branch base | `git rev-list --count main..phase-1/boot-security` = 0; `git log main ^phase-1` = 3 | `phase-1/boot-security` **is an ancestor of `main`**; `main` carries 3 commits phase-1 lacks (T10 branding + release readiness). This branch is based on phase-1 as the rules require; see **D0** |

Read together, rows 2-4 mean the CORS half of the task **cannot** be done as a "verification" step: the dependency is
not installed, so this is a new dependency, not a check.

---

## 3. The conflicts this proposal cannot resolve on its own

| # | Conflict | Source | Consequence if I decide alone |
|---|---|---|---|
| C1 | React SPA deferred until after pilot feedback; reopening needs a new ADR | `docs/adr/0013-…`, STANDING RULES | I would overturn an accepted ADR with a settings edit |
| C2 | Cross-origin credentialed access was reviewed and deliberately **not** added | `docs/pilot/T7-SECURITY-REVIEW-REPORT.md:418` | I would reopen a closed security finding without a review |
| C3 | No gender/theme concept exists in the schema or the policy | `students/models.py`, `schools/models.py`, `accounts/models.py` | I would invent a field and a meaning for it |
| C4 | Two frontend directories are **untracked** and contain a **second AI path to an external model with roster data** | `git status`; `frontend-women/src/lib/mentor-chat.functions.ts:68-95` | Any "integration" would silently legitimise sending student data to a third-party gateway (`AI_GOVERNANCE.md`, ADR-0008 DEFERRED) |
| C5 | The branch rule points at `phase-1/boot-security`, which is **behind `main`** | STANDING RULES vs `git log main ^phase-1` (= 3 commits) | Implementing on phase-1 would drop the T10 branding/settings work |
| C6 | `/api/token/` already returns a credential pair, and `/api/auth/login/` would be a **second** credential path | `config/urls.py:19-20` | Two login paths must share throttling, `must_change_password` and audit rules or they diverge |

---

## 4. Desired behavior (TARGET) — the design I recommend if D0–D9 are approved

### 4.1 Settings (fail-closed, dev-only defaults)

`django_core/config/settings/base.py`:

```python
INSTALLED_APPS = [..., 'rest_framework', 'corsheaders', ...]          # one new app entry

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',        # as high as possible, before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    ...
]

# No origin is trusted unless the operator names it (same policy as SERVICE_JWT_SECRET).
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if o.strip()]
CORS_ALLOW_CREDENTIALS = bool(CORS_ALLOWED_ORIGINS)  # credentials only where an explicit list exists
CORS_ALLOW_ALL_ORIGINS = False                      # never; a wildcard + credentials is invalid and unsafe
```

`django_core/config/settings/development.py` (local dev only; the list from the brief):

```python
CORS_ALLOWED_ORIGINS = ['http://localhost:5173', 'http://localhost:5174', 'http://localhost:8080']
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)   # Django's Origin check for POSTs (see 4.5)
```

`django_core/requirements.txt`: `django-cors-headers==<pinned version>` (pin, as every other dependency is pinned; the
exact version is checked against Django 5.2 at implementation time). `production.py` needs **no** CORS block: an empty
`CORS_ALLOWED_ORIGINS` means no cross-origin access, and a deployment that really wants it sets the environment
variable (D1).

### 4.2 `POST /api/auth/login/` (TARGET, JSON, session)

- Location: `django_core/dashboard/auth_api.py`, wired in `config/urls.py` as `path('api/auth/', include(...))`.
  A new Django app is **not** needed and would be a second L3 decision (`accounts` stays uninstalled).
- `authentication_classes([])`, `permission_classes([AllowAny])`, `renderer_classes([JSONRenderer])`.
- Request `{"username": "...", "password": "..."}`; both required, `username` truncated to 150 chars exactly as
  `dashboard/throttle.py:103` does.
- Refuse **before** checking the password when `throttle.is_locked(request, username)` (`:68`) → `429`
  `{"detail": LOCKED_MESSAGE}` (`:20`, `:105`) — reuse the constant, no second wording.
- `authenticate()`; on failure `throttle.record_failure(...)` → `401 {"detail": "نام کاربری یا رمز عبور اشتباه است."}`
  — one sentence for unknown user, wrong password and inactive account (no enumeration; Django's `ModelBackend`
  already refuses inactive users).
- On success `throttle.record_success(...)`, then `django.contrib.auth.login(request, user)` (this rotates the session
  key — never set `_auth_user_id` by hand), then `200` with the same body as `/api/auth/me/`.
- `AccountProfile.must_change_password = True` → **no session is created** and `403
  {"detail": "password change required", "code": "password_change_required"}` (mirrors the existing `/api/token/`
  rule at `dashboard/throttle.py:115-117`).
- The endpoint is CSRF-protected (see 4.5); it is **not** `@csrf_exempt`.

### 4.3 `GET /api/auth/me/` (TARGET, JSON)

`authentication_classes([SessionAuthentication, JWTAuthentication])` (both already configured),
`permission_classes([IsAuthenticated])`. Response `200`:

```json
{
  "id": 12, "username": "9000000001", "display_name": "…",
  "roles": ["SchoolAdmin"], "role": "SchoolAdmin",
  "schools": [{"id": 1, "name": "…"}], "school": {"id": 1, "name": "…"},
  "modules": ["exams", "mission"], "is_platform_operator": false,
  "must_change_password": false, "gender_scope": null, "theme": null
}
```

Derivation rules (no new query logic): `roles` = `students.access.roles_for(user)` (`students/access.py:35`, sorted
list); `role` = the first match in the display order of `dashboard/context_processors.py:12` `ROLE_LABELS` (a single
value for a UI that expects one); `schools` / `school` from `schools.entitlements.user_school_ids(user)`;
`modules` = `schools.entitlements.enabled_modules_for_user(user)` (`:110`); `is_platform_operator` =
`dashboard/operator_page.is_platform_operator(user)` (`:29`); `must_change_password` = the `AccountProfile` flag.
`gender_scope` and `theme` stay `null` until **D5** is answered — they are **not** inferred from a school name.

Multi-school users (**D6**): `school` is `null` when the user belongs to more than one school and no choice was made;
the chosen school can be `?school=<id>` (or an `X-School-Id` header) validated against `user_school_ids`. Falling back
to `first()` would silently show the wrong school's data.

Anonymous → `401`. A user whose `must_change_password` is set reaches this endpoint only if 4.4 is implemented.

### 4.4 `ForcePasswordChangeMiddleware` must learn about `/api/`

CURRENT: it redirects `/api/…` to the HTML page (`dashboard/middleware.py:15-19` — every path except `reverse()`d
password-change and logout, plus `/static/`). TARGET: for paths starting with `/api/` it returns
`JsonResponse({"detail": "password change required", "code": "password_change_required"}, status=403)` instead of a
302, and `POST /api/auth/login/` stays reachable (anonymous, and it answers 403 itself for such an account). The
middleware already queries `AccountProfile` on **every** authenticated request, so the branch adds no new query. This is
a change to an auth control and is part of this L3 scope, not a drive-by edit.

### 4.5 CSRF for a browser client on another origin

`CsrfViewMiddleware` is enabled (`base.py:41`), so a POST needs a token even for an anonymous view. Proposal:
add `GET /api/auth/csrf/` (`@ensure_csrf_cookie`, anonymous, returns `{"csrfToken": "…"}`) and require
`X-CSRFToken` on `POST /api/auth/login/` and `POST /api/auth/logout/`. Additionally check the `Origin` header against
`CSRF_TRUSTED_ORIGINS` as defence in depth. `SESSION_COOKIE_SAMESITE` stays at Django's `Lax`: `localhost:5173` and
`localhost:8000` are the **same site** (ports are ignored), so dev works. A frontend on a different registrable domain
(e.g. `*.lovable.app` → `api.school.ir`) would need `SameSite=None; Secure` **and** HTTPS, and is blocked by current
third-party-cookie policies — see D1.

### 4.6 `BasicAuthentication` (**recommended: do not enable**)

`rest_framework.authentication.BasicAuthentication` would accept the account password on **every** request and would
bypass `dashboard/throttle.py` (no counter, unlimited guesses), so it is a brute-force and credential-exposure path.
It has no CSRF protection either. If the owner requires it (D4), it should be (a) behind an explicit setting that is
`False` in `base.py`, (b) refused when `DEBUG = False` unless HTTPS is guaranteed, and (c) rate-limited by an
`authenticate_header`/throttle class — i.e. a larger design than "add a class name to a tuple". My recommendation is
to use `SessionAuthentication` plus the **existing** `JWTAuthentication`, which already covers machine clients.

---

## 5. Alternatives considered

| Alternative | Why not (or when) |
|---|---|
| **Same-origin reverse proxy** (serve both frontends under `https://<host>/men/`, `/women/`; Django at `/api/`) | No CORS at all, `Lax` cookies work, no `SameSite=None`, one TLS boundary. **Recommended for production** (D1). Needs nginx/Caddy config, which is an ops change (`deploy/`). |
| JWT in memory + `Authorization: Bearer` | Already supported (`/api/token/`, `JWTAuthentication`), no cookies, no CSRF, works on any origin. Downside: token storage/refresh in the browser and no server-side session revocation. |
| BFF (frontend server calls Django server-to-server, holds the session) | The TanStack Start apps already have a server runtime (Cloudflare Worker), but it would hold school credentials in a third-party platform — rejected on egress/PII grounds. |
| `CORS_ALLOW_ALL_ORIGINS = True` | Forbidden with credentials, and would let any site call the API with the user's session. Not proposed. |
| `@csrf_exempt` on login | Removes login-CSRF protection; rejected in favour of 4.5. |

---

## 6. Data impact

- **Recommended minimum (D5=a, D7=no): no model, no migration, no data migration.** CORS is settings only; the two
  endpoints read existing rows.
- **If D5=b:** one new field on `schools.School` (e.g. `audience` with `male|female|mixed`, `null=True` = unknown) plus
  one Django migration, the admin field and a test. **No back-fill**: a value is never inferred from students' names or
  from the school name. It is a configuration attribute of the school, not derived data, so no provenance column.
- **If D7=yes (login audit):** no migration (`AuditEvent.action` is a plain `CharField(max_length=40)`,
  `schools/models.py:361`), but `AuditEvent.school` is **non-nullable** (`:360`). A login event is therefore only
  recordable when the user has exactly one school; a PlatformAdmin/superuser has none (`school_ids_for_admin` returns
  empty for a superuser, `students/access.py:63`). That constraint is why I will not add login audit silently.
- The session row itself changes `django_session` as it already does for every HTML login. No new table.

---

## 7. API impact

| Endpoint | Method | Auth | Body / params | Responses |
|---|---|---|---|---|
| `/api/auth/csrf/` | GET | anonymous | — | `200 {"csrfToken": "…"}`; sets the `csrftoken` cookie |
| `/api/auth/login/` | POST | anonymous, CSRF token required | `{"username", "password"}` | `200` (same body as `/me/`), `400` missing field, `401` generic, `403` `password_change_required`, `429` locked |
| `/api/auth/me/` | GET | `IsAuthenticated` (session or JWT) | optional `?school=<id>` | `200` profile, `400` school not in the user's set, `401` anonymous |
| `/api/auth/logout/` | POST | `IsAuthenticated`, CSRF | — | `204`; `django.contrib.auth.logout()` (D8) |

- **Additive only.** `/api/token/`, `/api/token/refresh/`, `/api/students/` and every HTML route keep their behaviour.
- Error bodies use DRF's existing `{"detail": "…"}` shape, so a client can share one error handler with `/api/token/`.
- No versioning scheme is introduced (the repo has none); the contract is documented in `docs/ARCHITECTURE.md` (D8).
- `POST /api/auth/login/` and `POST /api/token/` are two credential paths; both must call the **same** throttle
  functions and the **same** `must_change_password` rule, or one becomes the weak link. That is covered by a test
  (§11, case 11).

---

## 8. Frontend impact

- **No file in `frontend-men/` or `frontend-women/` is touched by this proposal.** Both directories are untracked
  (`git status`), are not built by `scripts/run_tests.sh`, and are not in CI.
- **CURRENT:** neither app calls Django. `grep -rn 'localhost:8000\|/api/' frontend-men/src frontend-women/src` →
  **no match**. Both are static demo dashboards with hardcoded KPI numbers and hardcoded student names
  (`frontend-men/src/routes/index.tsx:20-37`). The "integration" therefore has no client code to match yet; this
  proposal defines the server contract the client would consume.
- Their themes are already separate: `frontend-men/README.md` describes a *"Boys' School / Male Staff version"* (dark
  slate + emerald/gold), `frontend-women/README.md` is a Lovable *"Pixel Perfect Replay"*. A `theme` field in `/me/`
  would duplicate a decision each app already makes at build time — see **D5**.
- The women's app hardcodes the school's name in its AI instructions («مدرسه قلمستان»,
  `mentor-chat.functions.ts:88`) and its roster in `src/data/school.ts`. If these apps are meant to serve several
  schools, that must come from `/api/auth/me/` (`school.name`), not from a constant (CLAUDE.md §7: no hard-coded
  school-specific values).

---

## 9. AI impact (**BLOCKING for any real data — separate from the CORS work**)

`frontend-women/src/lib/mentor-chat.functions.ts` is a TanStack server function that:

1. imports `@lovable.dev/ai-gateway` and calls `generateResponse({model: "openai/gpt-6-astra", …})` (`:71-95`);
2. builds the prompt from `ROSTER_SOURCE` — `rosterDigest()` plus the caller's `recentNotes` (`:76-83`) — i.e. **student
   data** (growth indicators, counsellor observations) and sends it to a **third-party gateway**.

Against `docs/AI_GOVERNANCE.md` and ADR-0008 (external provider/egress policy **DEFERRED**), this is not permitted:
no PII to an external LLM without an approved provider policy; no ACL-first retrieval (the whole roster is placed in
context regardless of the caller's role); no per-school call caps or `schools/entitlements.py` gate; no AI-call audit;
counseling notes are explicitly excluded from AI.

**Recommendation:** the CORS/login work can proceed for a *presentation-only* frontend, but no Django data may be
connected to these apps until the gateway call is removed or replaced by the existing approved path (Django → FastAPI
`/llm/complete/` with the service token, PII filter, purpose whitelist, `schools/ai_guard.py` caps and
`docqa`-style metadata-only audit — see `docs/changes/0034-p7-5-document-assistant-REPORT.md`). AI-call caps already
exist in code (`django_core/schools/ai_guard.py`, `base.py:103`), which is what the gateway path bypasses. This is
tracked as **D9** and is **not** fixed by this proposal.

---

## 10. Security impact

| Threat | Control in this proposal | Residual |
|---|---|---|
| Any site reads the API with the user's session | exact `CORS_ALLOWED_ORIGINS` allowlist, no wildcard, `CORS_ALLOW_CREDENTIALS` only when the list is non-empty | **XSS on an allowed origin = full account takeover** (cookies are `HttpOnly` but requests are credentialed) |
| Login CSRF / cross-site POST | `X-CSRFToken` + `CsrfViewMiddleware` (already on) + `Origin` check; no `@csrf_exempt` | none identified |
| Session fixation | `django.contrib.auth.login()` rotates the session key | none |
| Brute force on the new endpoint | reuses `throttle.is_locked/record_failure/record_success` (5/user, 20/IP, 900 s) | account-lockout DoS, already documented in `dashboard/throttle.py:1-12` |
| User enumeration | one generic message for unknown/wrong/inactive; `429` text reused from `LOCKED_MESSAGE` | response body and status are identical; `ModelBackend` also runs a dummy password hash for an unknown user, so timing is close but not proven equal |
| Forced-password-change bypass via API | 4.4 returns 403 for `/api/` instead of a redirect | none |
| Password replayed on every request | `BasicAuthentication` **not** enabled (4.6) | none |
| Over-exposure in `/me` | explicit allowlist of fields; **no** `national_id`, mobile, address, student rows, or notes | none if the field list is reviewed |
| PlatformAdmin leaking school scope | `school_ids_for_admin` returns empty for a superuser; `/me` reports `is_platform_operator` and an empty `schools` list | none |
| Unaudited logins | **not fixed** unless D7 is answered; `AuditEvent.school` is non-nullable | login success/failure is currently not in the audit log |
| Production misconfiguration | proposed new deploy check `eip.E007` in `dashboard/deploy_checks.py`: any `CORS_ALLOWED_ORIGINS` entry must be `https://` and must not be `*`; `CORS_ALLOW_CREDENTIALS` with an empty list is an error | existing `eip.E002` (`deploy_checks.py:26-28`) already rejects non-https `CSRF_TRUSTED_ORIGINS`, so the dev-only `http://localhost` list cannot reach production anyway |

The last row is the reason the recommended topology (D2) is a same-origin reverse proxy: it keeps `Lax` cookies, needs
no `SameSite=None`, no CORS credentials, and leaves `eip.E001/E002` as the only origin gate.

---

## 11. Test plan (TARGET — written only after approval)

New module `django_core/dashboard/test_auth_api.py` (convention: tests live beside the app, plain `TestCase`), plus
cases appended to the existing `django_core/dashboard/test_deploy_checks.py`.

| # | Case | Assertion |
|---|---|---|
| 1 | `POST /api/auth/login/` correct credentials | `200`; `response.json()['username']`; `client.session['_auth_user_id']` set |
| 2 | wrong password | `401`, generic message, **no** session key |
| 3 | unknown username | `401`, **byte-identical** body to case 2 |
| 4 | inactive user | `401`, same body; no session |
| 5 | `must_change_password` user | `403` + `code: password_change_required`; no session created |
| 6 | 5 wrong attempts then a correct one | 6th is `429` with `LOCKED_MESSAGE` (per-username counter) |
| 7 | 20 wrong attempts from one IP, distinct usernames | `429` (per-IP counter) |
| 8 | session from case 1 → `GET /api/auth/me/` | `200`; `roles == sorted(roles_for(user))`; `schools` matches `user_school_ids` |
| 9 | anonymous `GET /api/auth/me/` | `401`, JSON (not an HTML redirect) |
| 10 | JWT from `/api/token/` → `GET /api/auth/me/` | `200` (both authentication classes work) |
| 11 | `/api/token/` for a `must_change_password` user and `POST /api/auth/login/` for the same user | both refuse (parity test; C6) |
| 12 | `must_change_password` user requests `/api/students/` | `403` JSON, **not** `302` (4.4) |
| 13 | `enforce_csrf_checks=True`, POST without `X-CSRFToken` | `403`; with the token from `/api/auth/csrf/` → `200` |
| 14 | `OPTIONS /api/auth/me/` with `Origin: http://localhost:5173` and `CORS_ALLOWED_ORIGINS` overridden | `Access-Control-Allow-Origin` echoed, `Access-Control-Allow-Credentials: true` |
| 15 | same preflight with an origin **not** in the list | no `Access-Control-Allow-Origin` header |
| 16 | `/me` body keys | exact key set; `national_id`/`mobile`/`notes` absent |
| 17 | deploy check | `check_hosts_and_origins` reports `eip.E007` for `http://` and `*` origins, silent for an empty list |

Acceptance: the new module passes on sqlite **and** PostgreSQL, the existing suite is unchanged (no test edited to make a
new behaviour pass), and `manage.py check --deploy --fail-level WARNING` still passes with production settings.

---

## 12. Documentation impact

| File | Change |
|---|---|
| `docs/adr/0014-two-json-frontends.md` (**new**, only if D0 approves) | Records the decision and supersedes the deferred part of ADR-0013 |
| `docs/ARCHITECTURE.md` | New "Auth API (`/api/auth/…`)" subsection: contract from §7, threat notes from §10 |
| `docs/SECURITY.md` | CORS policy (fail-closed, dev-only list, `eip.E007`), the credential model, `/api/` behaviour of `must_change_password` |
| `docs/TESTING.md` | The new test module, and that the CORS cases use `override_settings` |
| `docs/CHANGE_GUIDE.md` | One line: the new dependency and its pin |
| `README.md` | Local run instructions (two Vite ports → one Django origin) |
| `docs/changes/0040-…-REPORT.md` (**new**, at the end) | Truth-labelled report with real command output |

---

## 13. Customization impact

- **No school-specific value in Python.** The origin list is read from the environment with the **same idiom the repo
  already uses** for `CSRF_TRUSTED_ORIGINS` (`production.py:67`):
  `[o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]`. Each deployment
  (developer laptop, pilot server, each school's host) names its own origins there; no code edit is needed per school.
- A school that gets its own hostname only adds an entry to `CORS_ALLOWED_ORIGINS` (and `ALLOWED_HOSTS`, already
  env-driven at `base.py:9`). No new setting per school, no per-school row, no `Site`-style table.
- The **empty default** means a fresh deployment exposes **no** cross-origin access until an operator opts in — the
  same fail-closed pattern as `SERVICE_JWT_SECRET`.
- If D5=b, the theme/gender attribute is a **per-school configuration value** set by the platform operator, not derived
  from students — so it stays a constant-free, data-driven value and remains in the admin, not in a template.

---

## 14. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Credentialed CORS turns any XSS in `frontend-*` into full account takeover | Medium (untrusted AI-generated frontend code, Lovable dependencies) | High | shortest possible origin list; production recommended same-origin proxy; `eip.E007` blocks http/`*` |
| R2 | A second credential path (`/api/auth/login/`) drifts from `/api/token/` (throttle, `must_change_password`) | Medium | High | one shared module, parity test (§11 case 11) |
| R3 | `SameSite=Lax` works in dev (`localhost:*` is one site) and fails on a real cross-domain deploy | High | Medium | D1/D2 decided **before** code; documented in `SECURITY.md` |
| R4 | Roster/counselling data leaves the country through the Lovable AI gateway | **Already present** | Very high | D9: remove or reroute before any real data; flagged in this proposal and in §9 |
| R5 | `must_change_password` users keep using the API because of a missed middleware branch | Low (if §4.4 is implemented with a test) | High | §11 case 12 |
| R6 | Login audit absence is discovered at audit time | Medium | Medium | D7 decides now, not after the pilot |
| R7 | Implementing on `phase-1/boot-security` drops the 3 `main`-only commits (T10 branding) | High (rule says phase-1) | Medium | D2/base-branch decision before the first code commit |
| R8 | Two untracked frontends get deleted/rewritten by their generator, invalidating the contract | Medium | Low | contract documented in `ARCHITECTURE.md` (D8), not in the frontend |
| R9 | A new pinned dependency breaks `pip install` in the deployment image | Low | Medium | pin, then `run_tests.sh sqlite` + `pg`, and the dependency audit note in the report |

---

## 15. Recommendation and the decisions I need (DECISION REQUIRED)

**Recommendation in one sentence:** approve the ADR (D0) and the production topology (D2) first; then I implement the
smallest safe version — CORS with an empty, env-driven allowlist (dev list only in `development.py`), a
CSRF-protected session login that reuses the existing throttle, `GET /api/auth/me/` built only from
`roles_for()`/`user_school_ids()`/`enabled_modules_for_user()`, and the `/api/`-aware `must_change_password` branch —
with `BasicAuthentication` **off**, `gender_scope`/`theme` **null**, and login audit **deferred**.

| D# | Question | Options | My recommendation |
|---|---|---|---|
| **D0** | ADR-0013 disposition | (a) new ADR-0014: two JSON frontends approved for **local dev / presentation**, no production student data; (b) keep ADR-0013 untouched → this task is dropped; (c) full SPA approval incl. production data | **(a)** — smallest truthful step; (c) needs its own review |
| **D1** | Base branch | (a) merge `main` into `work/dual-frontend-integration` before the first code commit (keeps the 3 T10 commits); (b) branch from `main` instead of `phase-1/boot-security`; (c) stay exactly on the phase-1 base | **(a)** — honours the rule and does not lose T10 |
| **D2** | Production topology | (a) same-origin reverse proxy: both apps under one host, Django at `/api/`, **no CORS in production**; (b) separate subdomains + `SameSite=None; Secure` + explicit CORS list; (c) keep them on Lovable's domain and call the API cross-site | **(a)**; the 5173/5174 list is **dev-only** either way |
| **D3** | Credential model | (a) session cookie for browsers **and** keep the existing JWT for machine clients; (b) JWT only (no session login); (c) session only | **(a)** |
| **D4** | `BasicAuthentication` | (a) do not enable; (b) enable behind an explicit setting, `False` by default, HTTPS-only, with throttling | **(a)** — it bypasses `dashboard/throttle.py` |
| **D5** | gender/theme scope | (a) `gender_scope: null`, `theme: null`, theme stays a frontend build-time decision; (b) new `School.audience` field + migration + admin; (c) per-user preference model | **(a)** now; (b) only if a school actually needs to be told apart by the backend |
| **D6** | Multi-school users | (a) `?school=<id>` validated against `user_school_ids`, `school` = `null` when ambiguous; (b) `X-School-Id` header; (c) `first()` silently | **(a)** — (c) risks showing the wrong school's data |
| **D7** | Login audit | (a) out of scope here, separate L2 change with a school-less sink; (b) add `LOGIN`/`LOGIN_FAILED` now, only for users with exactly one school | **(a)** — `AuditEvent.school` is non-nullable, so (b) cannot cover PlatformAdmins |
| **D8** | Logout + docs | (a) include `POST /api/auth/logout/` and document the contract in `ARCHITECTURE.md`/`SECURITY.md`; (b) no logout endpoint, document nothing | **(a)** |
| **D9** | Lovable AI gateway in `frontend-women` | (a) remove the gateway call **before** any Django data is connected (separate change); (b) approve it as an external provider (needs an `AI_GOVERNANCE.md` amendment and an egress decision) | **(a)** — currently roster + counselling notes leave to a third party |

---

## 16. If you approve (implementation order — nothing below has been done)

| Step | Files | Verify with |
|---|---|---|
| 1. ADR | `docs/adr/0014-two-json-frontends.md` | review only |
| 2. Dependency | `django_core/requirements.txt` (pinned `django-cors-headers`), install into `django_core/.venv` | `python -c "import corsheaders"` |
| 3. Settings | `django_core/config/settings/base.py` (app, middleware, fail-closed CORS), `django_core/config/settings/development.py` (dev list + `CSRF_TRUSTED_ORIGINS`) | `manage.py check` on both settings modules |
| 4. Auth module | `django_core/dashboard/auth_api.py` (csrf/login/me/logout, sharing `throttle`), `django_core/config/urls.py` (`path('api/auth/', …)`) | targeted module |
| 5. Middleware | `django_core/dashboard/middleware.py` — JSON `403` for `/api/` | targeted module |
| 6. Deploy check | `django_core/dashboard/deploy_checks.py` (`eip.E007`) | `manage.py check --deploy --fail-level WARNING` with production settings |
| 7. Tests | `django_core/dashboard/test_auth_api.py` (cases 1-16), `django_core/dashboard/test_deploy_checks.py` (case 17) | `scripts/run_tests.sh sqlite`, then `pg` |
| 8. Docs | `ARCHITECTURE.md`, `SECURITY.md`, `TESTING.md`, `CHANGE_GUIDE.md`, `README.md` | review |
| 9. Report | `docs/changes/0040-dual-frontend-integration-REPORT.md` with real command output and truth labels. `git check-ignore` confirms `django_core/dashboard/` and `django_core/config/` are **not** in `.git/info/exclude`, so the new module and tests need a plain `git add` — `git add -f` is required only if a file lands in `risk/`, `interventions/`, `core/` or the other excluded paths (none planned) | read the last lines of the test log |

**Stops I will respect:** no commit that adds the dependency before D0/D2 are answered; no production CORS entry; no
touch to `main`; no push; no frontend file edited; no change to `/api/token/`, `throttle.py` counters, `access.py` or
`entitlements.py` semantics.

## 17. Truth status of this document

- **CURRENT** (rows 1-20 of §2, plus C1-C6, §8, §9): read from the files quoted; no command failed; **no test was run**
  and **no test result is claimed**.
- **TARGET** (§4, §6 conditional parts, §7, §11): designed, **not implemented, not tested, NOT VERIFIED**.
- **DECISION REQUIRED**: D0-D9.
- **DEFERRED**: login audit (D7 if (a)), `School.audience` (D5 if (b)), the AI gateway remediation (D9), and any
  production CORS configuration (D2 if (b)).

---

## 18. Addendum (2026-11-13, second instruction) — "clean up Mock/Supabase auth, add a central API client"

The owner asked for: remove/bypass Supabase in the login pages; add `src/lib/api.ts` with
`baseURL: import.meta.env.VITE_API_URL || '/api'` and `withCredentials: true`; set the Vite ports to 5173/5174 with a
`/api` → `http://127.0.0.1:8000` proxy; and replace the mock login submit with a call to `/api/auth/login/` that
redirects on success. I fact-checked every premise before writing any code. **Nothing was changed**; this section is the
record.

| # | Premise in the instruction | CURRENT evidence | Verdict |
|---|---|---|---|
| 1 | "Mock/Supabase auth in the login pages" | `grep -rni 'login\|signin\|mock' frontend-{men,women}/src --include=*.ts --include=*.tsx` → **no match**. `ls frontend-*/src/routes` → only `index.tsx`, `README.md`, `__root.tsx`. There is no `src/pages/`, no `Login.tsx`, no auth code at all | **No target to clean up** |
| 2 | "Supabase client dependencies" | `package.json` (both apps): **no** `@supabase/*`, no `axios`. `grep -in supabase` over both `src/` trees → 8 hits, **all comments** (`src/start.ts:29-31` and `src/lib/lovable-error-reporting.ts:55` in each app), plus `AGENTS.md:18` ("do not add `supabase/migrations/`") | **Nothing to remove**; no dependency to bypass |
| 3 | "`src/lib/api.ts` with `baseURL` + `withCredentials`" | both apps use `@lovable.dev/vite-tanstack-config` + TanStack Start (SSR/Worker); no HTTP client dependency exists. `baseURL`/`withCredentials` are **axios** options; with `fetch` the equivalents are `credentials: 'include'` and a relative URL | **Doable, but needs D10** (axios = a new dependency in two untracked apps) |
| 4 | "set the port to 5173/5174 and proxy `/api`" | `vite.config.ts` calls `defineConfig` from the Lovable wrapper, whose header says it *already* handles "sandbox detection (port/host/strictPort)" and that extra config may be passed as `defineConfig({ vite: { ... } })`. A file-level `server: { port, proxy }` is therefore **not** the shape this file uses. The wrapper's source is not installed (`node_modules` absent), so its port precedence is **NOT VERIFIED** | **Doable, needs the wrapper's `vite:` key**, and the port must be checked against the wrapper's own default |
| 5 | "call `/api/auth/login/` and redirect on success" | `grep -rn 'api/auth' django_core --include=*.py` → **no match**. §4.2/§4.3 of this proposal describe the endpoint; it is **TARGET, not built** (blocked by D0-D2) | **The call would 404** until the backend lands |

Two further constraints:

- **There is no JavaScript toolchain on this machine.** `command -v node`, `command -v npm`, `command -v bun` → all
  absent; `ls frontend-*/node_modules` → *No such file or directory*. So I can write the files but **cannot** install
  `axios`, run `vite dev`, `vite build`, `eslint` or `vitest` here. Every frontend item would have to be labelled
  **NOT VERIFIED** until you run `bun install && bun dev` yourself. This is the strongest argument for D10=(a).
- **Nothing here is under version control.** `git status` lists `frontend-men/` and `frontend-women/` as untracked (`??`).
  Any edit I make is invisible to review, to `git diff`, and to any later rollback. Adding them to git is **D13**.
- **ADR-0013 / STANDING RULES** ("No SPA/React") still apply, and D0 is unanswered, so a login route in these apps is
  exactly the deferred case.

### 18.1 The change I would make once approved (sketch, not written)

```ts
// vite.config.ts (both apps; inside the wrapper's `vite` key)
defineConfig({
  tanstackStart: { server: { entry: "server" } },
  vite: { server: { port: 5173 /* 5174 for women */,
                    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } } } },
});
```

```ts
// frontend-*/src/lib/api.ts — fetch-based (zero new dependency), same public shape as axios
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
export class ApiError extends Error { constructor(public status: number, public body: unknown) { super(`HTTP ${status}`); } }
function csrfToken() { /* read the csrftoken cookie, send X-CSRFToken (proposal §4.5) */ }
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> { /* credentials: 'include' */ }
export const apiLogin = (username: string, password: string) => apiFetch("/auth/login/", { method: "POST", … });
export const apiMe = () => apiFetch("/auth/me/");
```

Plus `src/routes/login.tsx` (`createFileRoute("/login")`, a form that calls `apiLogin`, then
`router.navigate({ to: "/" })` on success and renders the `401`/`403`/`429` message inline), and the generated
`routeTree.gen.ts` is refreshed by the router plugin — **not hand-edited**.

### 18.2 Additional decisions this addendum raises

| D# | Question | Options | My recommendation |
|---|---|---|---|
| **D10** | HTTP client | (a) `fetch` wrapper, no dependency; (b) add `axios` to both `package.json` + lockfiles | **(a)** — same behaviour, no new dependency in an untracked app, `withCredentials` is `credentials: 'include'` |
| **D11** | Login route | (a) new `src/routes/login.tsx` in each app, redirect to `/`; (b) no login UI, only `src/lib/api.ts`; (c) a modal inside the existing dashboard | **(b) first, then (a)** after the backend exists |
| **D12** | Order of work | (a) Django endpoints first (this proposal §16), then the client; (b) client first, accept 404s; (c) both in one change | **(a)** — otherwise the client cannot be verified even manually |
| **D13** | Version control of the two apps | (a) `git add` both `frontend-*` trees (reviewable, rollback-able); (b) leave untracked and edit them anyway | **(a)** — editing untracked code is the real risk here |

**Status after this addendum: still BLOCKED — DECISION REQUIRED (D0-D13).** No frontend file, no `package.json`, no
`vite.config.ts` and no Django file was modified; no build, lint or test was run in this task.
