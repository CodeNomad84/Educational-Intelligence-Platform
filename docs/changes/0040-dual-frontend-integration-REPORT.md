# 0040 — Dual-frontend integration: session auth + CORS + shared API client (report), 2026-11-13

**Level L3 — approved proposal `0040-dual-frontend-integration-PROPOSAL.md` (owner approved the vertical slice on
2026-11-13: D0=a, D1=a, D2=a, D3=a, D4=a, D5=a, D6=a, D7=a, D8=a, D9=a; §18's D10–D12 resolved as *fetch client* /
*no login page yet* / *backend first*). ADR: `docs/adr/0014-two-json-frontends.md`.**
Branch `work/dual-frontend-integration`, created from `phase-1/boot-security`. Local commits only — nothing pushed.

Truth labels used below: **CURRENT** = verified by a command in this session; **NOT VERIFIED** = written but not executed;
**TARGET** = intended behaviour, not yet exercised end-to-end; **DEFERRED** = explicitly out of scope.

## 1. What was delivered

| Area | Change | Status |
|---|---|---|
| Backend | `dashboard/auth_api.py` — `/api/auth/csrf/`, `login/`, `logout/`, `me/` (new, 153 lines) | CURRENT (18 tests) |
| Backend | `config/urls.py` include `api/auth/`; additive, `/api/token/` untouched | CURRENT |
| Backend | `requirements.txt` + `django-cors-headers==4.9.0`; app + middleware in `base.py` | CURRENT (installed in venv, suites ran) |
| CORS | fail-closed `CORS_ALLOWED_ORIGINS` from env, `CORS_ALLOW_CREDENTIALS` only when the list is non-empty, `CORS_ALLOW_ALL_ORIGINS = False` | CURRENT |
| Dev CORS | `development.py` adds the four loopback origins + env-only `CSRF_TRUSTED_ORIGINS` | CURRENT |
| Deploy check | `eip.E007` in `dashboard/deploy_checks.py`: wildcard/`*` refused, any non-https origin refused (loopback `http://` tolerated) | CURRENT (7 tests) |
| Middleware | `ForcePasswordChangeMiddleware` answers `/api/…` with JSON 403 `password_change_required` instead of an HTML 302; `csrf/`, `login/`, `logout/` stay reachable | CURRENT |
| Frontend | identical `src/lib/api.ts` in both apps (`credentials: 'include'`, CSRF header, `ApiError`, `mustChangePassword`) | **NOT VERIFIED** (no JS toolchain on this host) |
| Frontend | `vite.config.ts`: ports 5173/5174, `strictPort`, `/api` → `http://127.0.0.1:8000` | **NOT VERIFIED** |
| Frontend | third-party AI gateway removed (`@lovable.dev/ai-gateway`, `ai-gateway.types.ts`, `src/generated/`); `mentor-chat.functions.ts` now extractive/local | **NOT VERIFIED** |
| Frontend | `MascotAssistant.tsx` reads `public/assets/mascot/*` instead of Lovable asset manifests | **NOT VERIFIED** |
| Docs | ADR-0014, `ARCHITECTURE.md` §Auth API, `SECURITY.md`, `TESTING.md`, `CHANGE_GUIDE.md`, `README.md` | CURRENT |

The four `Frontend` rows were, until 2026-11-13, in **separate git repositories** inside `frontend-men/` and
`frontend-women/`. On the owner's decision both nested `.git` directories were removed and the trees are now **tracked in
this repository** on the same branch — see §5.2.

## 2. Security-relevant decisions as implemented

- **No `BasicAuthentication`** on `login/` (no password per request, no throttle bypass); `login/` is `csrf_protect`
  because `APIView` is exempt inside Django's middleware chain.
- **Throttle parity**: `login/` uses `dashboard/throttle.py` counters — same lockout as the HTML page and `/api/token/`.
- **`must_change_password`**: `login/` refuses with 403 `{"code": "password_change_required"}` *after* recording the
  success, exactly like `/api/token/`.
- **`me/`/`logout/`** declare `(JWTAuthentication, SessionAuthentication)` in that order, so an anonymous caller gets 401
  (not DRF's 403) while a session caller still gets CSRF enforcement.
- **`me/`** returns `gender_scope: null` and `theme: null` (D5 — nothing to derive them from), `school: null` for a
  multi-school user unless `?school=<id>` names a school the user belongs to (400 otherwise). No national id, mobile or
  note in any response.
- **Login is not audited** (D7): `AuditEvent.school` is non-nullable and a pre-auth login has no school.
- **CORS is fail-closed**: empty env list ⇒ no cross-origin access at all; credentials are only allowed to named origins.

## 3. Test evidence

| Command | Result |
|---|---|
| `manage.py test dashboard.test_auth_api dashboard.test_deploy_checks` (sqlite) | `Ran 36 tests ... OK` (CURRENT) |
| `scripts/run_tests.sh sqlite` (check + `makemigrations --check --dry-run` + 11 apps + demo) | `Ran 1635 tests ... OK (skipped=11)`, `Ran 62 tests ... OK`, `ALL DJANGO CHECKS AND TESTS PASSED` (CURRENT) |
| `manage.py check --deploy --fail-level WARNING` with production settings, `CORS_ALLOWED_ORIGINS=http://men.example.ir` | exit 1, `(eip.E007) CORS_ALLOWED_ORIGINS entry 'http://men.example.ir' must be an https:// origin` (CURRENT) |
| same command with `https://men.example.ir,https://women.example.ir` | exit 0, only the staged-HSTS info `eip.I006` (CURRENT) |
| `scripts/run_tests.sh pg` (PostgreSQL 16 container) | exit 0, `Ran 1635 tests in 1625.180s`, `OK (skipped=1)`, `POSTGRESQL CHECKS AND TESTS PASSED` (CURRENT) — §4 |
| Frontend `npm ci` / `tsc` / `vitest` | **NOT VERIFIED** — no Node/JS toolchain on this host; the code is now tracked here (§5.2) but no CI job builds it |

## 4. PostgreSQL leg — CURRENT

`scripts/run_tests.sh pg` rebuilt `eip-test-django:local` from `requirements.txt` (so pip really installed the new
`django-cors-headers==4.9.0` pin) and ran the same suite in a disposable `pgvector/pgvector:pg16` container:

| Command | Result |
|---|---|
| `scripts/run_tests.sh pg` | exit **0**; `Ran 1635 tests in 1625.180s`; `OK (skipped=1)`; `POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)` (CURRENT, `/tmp/full_pg.log`) |

Same 1635 tests as the sqlite leg; the skip counts differ (sqlite `skipped=11`, pg `skipped=1`) because several tests are
conditional, e.g. `students/test_tooling.py:417` runs only in the PostgreSQL container
(`@unittest.skipUnless(os.environ.get("EIP_TEST_CONTAINER") == "1", …)`). Both legs now pass, so the auth API, the CORS
settings and `eip.E007` are verified on SQLite **and** PostgreSQL.

## 5. Known gaps / follow-ups (DEFERRED)

1. **No login page in the frontends yet**: `apiLogin()` exists in `src/lib/api.ts` but no route consumes it (D11 — the
   pages come in a follow-up change). Until then the client is dead code from the app's point of view.
2. **Frontend version control — RESOLVED 2026-11-13 (monorepo, owner decision).** History: `frontend-men/` and
   `frontend-women/` each contained their **own `.git`** (branch `main`, a single "Add project README" commit), so
   `git add` on any path inside them was a silent no-op and no frontend file could enter this repository's history. The
   work was first committed inside each app's repo (`work/0040-json-api-client`: `108d345` men, `603f78d` women). The
   owner then chose **Option A — monorepo**: both `.git` directories were removed (history saved first as bundles,
   `/tmp/frontend-history/frontend-men.bundle`, `frontend-women.bundle`), and both trees are committed here as plain
   files — 174 files, incl. `src/lib/api.ts`, `vite.config.ts`, `MascotAssistant.tsx`, `mentor-chat.functions.ts`,
   `package.json`, `bun.lock`, `.gitignore`, `.lovable/project.json` (metadata, no credential) and the four
   `public/assets/mascot/*.png`; `node_modules`/`dist` are excluded by each app's own `.gitignore`. Recorded in ADR-0014
   (decision note) and corrected in `SECURITY.md`/`TESTING.md`. Still open: `scripts/run_tests.sh` builds no JS
   (**TARGET**) — a lint/typecheck/build job remains a follow-up.
3. **`@lovable.dev/vite-tanstack-config` may override `server.strictPort`** via its sandbox detection; unknown without a
   JS toolchain. Consequence would be a port drift, not a security issue.
4. `/api/auth/me/` exposes nothing new, but a future field must be added to the accessor list in
   `test_auth_api.ProfileTests` first (the test asserts the exact key set).
