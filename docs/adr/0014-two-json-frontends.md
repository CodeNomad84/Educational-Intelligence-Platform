# ADR-0014: two presentation frontends (`frontend-men`, `frontend-women`) may run as React SPAs against one Django origin
- Status: **ACCEPTED 2026-11-13** (owner, answers D0-D9 of `docs/changes/0040-dual-frontend-integration-PROPOSAL.md`)
- Date: 2026-11-13
- Decider: owner
- Level: L3 (changes the TARGET of `ARCHITECTURE.md` established decision 4 and adds an auth surface)
- Relation: **amends the "SPA is DEFERRED" part of ADR-0013 for presentation/pilot use only**; leaves ADR-0013's rule that
  real student data is served by server-rendered Django templates untouched.

## Context
`frontend-men/` (boys' school) and `frontend-women/` (girls' school) are two TanStack Start + React 19 dashboards that
live in this repository (as **tracked** directories since the monorepo decision of 2026-11-13, see the decision note at
the end: the two nested `.git` repos were removed and the trees added on the same branch), are not built by
`scripts/run_tests.sh`, are not in CI, and until
this change called no Django endpoint at all: every number and name on screen is a constant in `src/routes/index.tsx` and
`src/data/school.ts`. They were produced on a third-party builder platform, which is also why `frontend-women` shipped a
server function that sent roster data and counselling notes to an external AI gateway (`@lovable.dev/ai-gateway`).

The owner wants both apps shown and, later, fed by the platform. ADR-0013 deferred "a full React SPA" until after pilot
feedback and reserved every new island for its own L2 proposal. That decision stands for **real data**; a presentation
layer needs an explicit, narrow exception plus an authentication contract, or the apps will grow their own one.

CURRENT facts the decision is built on (verified in the proposal): `corsheaders` was not installed; `/api/auth/…` did not
exist (only `/api/token/`, a throttled JWT pair); no `BasicAuthentication`; `DEFAULT_PERMISSION_CLASSES` unset; the
`must_change_password` middleware answered `/api/…` with a **302 to an HTML page**; no gender/theme field in any model.

## Decision
1. `frontend-men` and `frontend-women` may exist as **presentation/pilot** React apps. Real student data stays behind
   Django templates and the existing `visible_*` scopes until the authorization model (ADR-0003) is settled; wiring a
   student-data endpoint into either app is a new L2 proposal that must name the endpoint and its ACL.
2. **One origin.** The recommended deployment serves both apps behind the same reverse proxy as Django, so the browser
   never makes a cross-origin request (D2=a). In local dev each app proxies `/api` to `http://127.0.0.1:8000` from its own
   Vite server (5173 / 5174).
3. **Session authentication, not a new token store.** `POST /api/auth/login/` calls `authenticate()` + `login()`, so the
   browser holds the ordinary `sessionid` cookie it already holds for the HTML pages. `credentials: 'include'` is the
   whole client-side credential handling; nothing is kept in `localStorage` (D3=a).
4. **CSRF stays on.** `GET /api/auth/csrf/` sets the cookie, `X-CSRFToken` is required on `login/` and `logout/`; no view
   is `csrf_exempt`. `SameSite=Lax` is kept: same-origin (proxy) or same-site (`localhost:5173` → `localhost:8000`) works.
5. **No `BasicAuthentication`** anywhere (D4=a): it would accept the account password on every request and bypass
   `dashboard/throttle.py`. `GET /api/auth/me/` accepts only `SessionAuthentication` and the existing
   `JWTAuthentication`, and `POST /api/auth/login/` uses the **same** throttle functions and the same
   `must_change_password` refusal as `/api/token/` and the HTML login.
6. **`/api/…` answers JSON.** `ForcePasswordChangeMiddleware` returns `403 {"detail", "code"}` for an `/api/` path instead
   of a 302; only `login/`, `csrf/` and `logout/` under `/api/auth/` stay reachable for a flagged account.
7. **CORS is fail-closed.** `CORS_ALLOWED_ORIGINS` is empty unless an operator names origins in the environment;
   `CORS_ALLOW_ALL_ORIGINS` is `False`; the deploy check `eip.E007` refuses a wildcard and any non-https origin that is not
   loopback.
8. **No school data to a third party (D9).** `frontend-women/src/lib/mentor-chat.functions.ts` no longer imports
   `@lovable.dev/ai-gateway` and no longer sends roster or counselling data anywhere; it answers extractively from the
   built-in knowledge base on the server. AI features stay off until ADR-0008 (provider/egress policy) is decided.

## Alternatives considered
- **Keep ADR-0013 verbatim (no SPA at all).** Cheapest to secure, but the two apps already exist and the owner wants them
  demonstrated; leaving them without an auth contract is what produced the gateway call.
- **JWT in the browser** (`/api/token/` + `Authorization: Bearer`). Already supported and needs no CSRF, but it puts a
  long-lived credential in JavaScript storage and loses server-side session revocation. Kept for machine clients only.
- **A backend-for-frontend** on the app's Worker runtime: would hold school credentials on a third-party platform; refused
  on egress/PII grounds.
- **`CORS_ALLOW_ALL_ORIGINS = True`**: invalid with credentials and hands the session to any site; refused.

## Consequences (security, data, testing, customization)
- Security: one new auth surface, reviewed as L3, sharing the existing throttle, CSRF and password-change rules; no new
  token table, no schema change, no migration. `/api/…` now fails loudly (JSON 403) instead of redirecting.
- Data: no model change. `AuditEvent.school` is non-nullable, so **login is not audited** (D7=a, deferred to a separate
  L2 proposal); `gender_scope`/`theme` are `null` because no such field exists (D5=a) and are never inferred.
- Testing: `dashboard/test_auth_api.py` (18 tests: login, enumeration parity, throttle parity with `/api/token/`, CSRF,
  JWT, `/me/` key set, multi-school `?school=`, CORS reflect/refuse) and `CorsDeployCheckTests` in
  `dashboard/test_deploy_checks.py`. The pre-existing suite is unchanged.
- Customization: each deployment names its own origins through the environment; no school-specific value in code. The two
  apps own their own theme at build time (`frontend-*/README.md`), so no theme field is introduced.
- Cost: two extra dev servers and one new dependency (`django-cors-headers==4.9.0`). The frontends are tracked
  (monorepo decision, 2026-11-13) but outside the test gate: a change in them is only as safe as its review.

## Decision note — the two apps become part of this repository (2026-11-13)
Owner decision after delivery (resolves D13 of `docs/changes/0040-dual-frontend-integration-PROPOSAL.md` as **(a)**):
`frontend-men/` and `frontend-women/` each shipped with their **own** `.git` (branch `main`, one commit), which is why
`git add` inside them was a silent no-op and the 0040 frontend work could not be reviewed from this repository. The
nested `.git` directories were removed (their history was saved first as bundles, `/tmp/frontend-history/*.bundle`) and
both trees are now committed on `work/dual-frontend-integration`. Consequences: the frontend code is reviewable and
rollback-able here; each app keeps its own `.gitignore` (`node_modules`, `dist`, `.output`, `.wrangler`, `*.local`);
`scripts/run_tests.sh` still does not build them, so a JS toolchain (lint/typecheck/build) remains a **TARGET**, not a
CURRENT gate. No new dependency was added to either `package.json`.

## Evidence (files)
`django_core/dashboard/auth_api.py` (the four views), `django_core/config/urls.py` (`/api/auth/` include),
`django_core/config/settings/base.py` (app, middleware, fail-closed CORS), `django_core/config/settings/development.py`
(loopback dev list), `django_core/dashboard/middleware.py` (JSON 403 branch), `django_core/dashboard/deploy_checks.py`
(`eip.E007`), `django_core/dashboard/test_auth_api.py`, `frontend-*/src/lib/api.ts`, `frontend-*/vite.config.ts`,
`frontend-women/src/lib/mentor-chat.functions.ts`.

## Supersedes / superseded by
Amends ADR-0013 (item 4, SPA DEFERRED) for presentation/pilot frontends only; does not supersede it for student data.
Complemented (not superseded) by **ADR-0015** (2026-11-13), which turns decision 2 ("one origin per app") into the deployed
topology: one loopback nginx gateway, two SSR Node services, `edge`/`backend` network split. ADR-0015 honours decisions 3–8
of this document unchanged (session cookie, CSRF, fail-closed CORS, no `localStorage` token, no third-party egress) and
records the one deliberate local-profile exception: the compose stack sets `SECURE_SSL_REDIRECT=0` because it terminates no
TLS itself (the code default stays `True`; a server sets `1` behind its TLS proxy).

