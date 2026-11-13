# 0042 — Frontends in containers + one edge gateway (report), 2026-11-13

**Level L3 — proposal `0042-frontend-containers-PROPOSAL.md`; owner approved D1–D7 on 2026-11-13 (Gemini envelope) and
issued the Celery/Kombu dependency mandate. ADR: `docs/adr/0015-frontend-containers-and-gateway.md`.**
Branch `work/0042-frontend-containers`, created from `phase-1/boot-security`. Local commits only — nothing pushed.
**Closed 2026-11-13:** owner confirmed D7=a, the `kombu==5.4.0` pin and the result-file monitoring change, and authorized the
merge into `main` (`git merge --no-ff`, local; **not pushed** — see §9).

Truth labels below: **CURRENT** = verified by a command in this session; **NOT VERIFIED** = written but not executed;
**TARGET** = intended, not yet exercised; **DECISION REQUIRED** = needs the owner.

## 1. What was delivered

| # | Item | Evidence | Status |
|---|---|---|---|
| D1 | `nitro: { preset: "node-server" }` in `frontend-men/vite.config.ts` and `frontend-women/vite.config.ts` | `bun run build` in the image build stage produced `.output/server/index.mjs`; the running containers serve `/` | CURRENT |
| D2 | Multi-stage `Dockerfile` per app (`oven/bun:1-alpine` build → `node:22-alpine` runtime, non-root) | `docker compose build frontend_men frontend_women` → images 254 MB / 246 MB, build stages green | CURRENT |
| D3 | `gateway` service (`nginx:1.27-alpine`), one `server` block per app + shared Django routes | `deploy/nginx/frontends.conf`, `deploy/nginx/eip_proxy.conf`; curl matrix in §4 | CURRENT |
| D4 | Two networks: `edge` (gateway, both frontends, Django) / `backend` (Django, PostgreSQL, Redis, FastAPI, Celery, MinIO, Ollama) | `docker network inspect …_edge` lists only the four edge containers; static test `FrontendExposureTests` | CURRENT |
| D5 | Gateway on `127.0.0.1:${FRONTEND_HTTP_PORT:-8080}`, Django moved to `127.0.0.1:${DJANGO_HTTP_PORT:-8010}` | `docker compose ps` ports column | CURRENT |
| D6 | JS gate inside the build stage: `bun install --frozen-lockfile` → `eslint` → `tsc --noEmit` → `vitest` → `vite build` | build logs: `LINT_OK`/`TSC_OK`/`TEST_OK`/`BUILD_OK` for both apps | CURRENT |
| D7 | Local TLS policy — see §5 (implemented as variant **a**, not b) | `/api/auth/csrf/` = 200, `/api/auth/me/` = 401 JSON through the gateway | CURRENT |
| — | Celery/Kombu blocker: `kombu==5.4.0` pinned next to `celery==5.4.0`, `redis==5.0.8` | container import check + worker log `Connected to redis… ready.` | CURRENT |

## 2. Files

**Created** (the two under `deploy/` are tracked normally; the frontend files live inside the two app directories):

| Path | Purpose |
|---|---|
| `docs/adr/0015-frontend-containers-and-gateway.md` | the L3 ADR (owner's path spelling; the proposal wrote `…-and-edge-gateway.md`) |
| `frontend-men/Dockerfile`, `frontend-men/.dockerignore` | boys' app image |
| `frontend-women/Dockerfile`, `frontend-women/.dockerignore` | girls' app image |
| `deploy/nginx/frontends.conf` | gateway `server` blocks (rendered from a template with `MEN_HOST`/`WOMEN_HOST`) |
| `deploy/nginx/eip_proxy.conf` | shared `proxy_pass http://django:8000` + forwarding headers, included by both blocks |
| `docs/changes/0042-frontend-containers-REPORT.md` | this file |

**Modified:** `docker-compose.yml` (networks, `frontend_men`, `frontend_women`, `gateway`, `frontends-dev` profile,
`ALLOWED_HOSTS`/`SECURE_SSL_REDIRECT`, Django port 8010, network membership of every service),
`django_core/requirements.txt` (kombu pin), both `frontend-*/vite.config.ts` (`node-server`, `VITE_DEV_API_TARGET`,
bracket access), both `frontend-*/src/lib/api.ts` (bracket access + formatting), `frontend-women/vitest.config.ts` (zod
inlining), `frontend-women/bun.lock` (stale `@lovable.dev/ai-gateway` entries removed), 20 `frontend-*/src/**` files
(prettier pass, see §5.4), `fastapi_core/tests/test_exposure.py` (+`FrontendExposureTests`),
`docs/{DEPLOYMENT,SECURITY,TESTING,CHANGE_GUIDE}.md`, `docs/adr/0014-two-json-frontends.md` (note).

## 3. Commands that produce the stack

```
docker compose build frontend_men frontend_women     # JS gate + images only
docker compose up -d --build                         # everything (migrate runs first, gateway waits for health)
```

No new host tooling is required: the host has no Node, and both builds run entirely inside the containers.

## 4. Live evidence (`CURRENT`, 2026-11-13)

`docker compose ps` after `docker compose up -d --build` — all twelve services (the gateway waits for both frontends to
report healthy before it starts, so nothing here is a race):

```
celery_beat      Up  8000/tcp
celery_worker    Up  8000/tcp
django_core      Up  127.0.0.1:8010->8000/tcp
fastapi_core     Up  8001/tcp
frontend_gateway Up (healthy)  127.0.0.1:8080->80/tcp
frontend_men     Up (healthy)  3000/tcp
frontend_women   Up (healthy)  3000/tcp
minio_storage    Up  9000/tcp
ollama_server    Up  127.0.0.1:11435->11434/tcp
postgres_db      Up  5432/tcp
redis_cache      Up  6379/tcp
```

Gateway matrix (`curl` against `127.0.0.1:8080`, `Host` header set explicitly):

| Request | Result |
|---|---|
| `Host: men.localhost` `GET /` | **200**, `<title>سکوی آموزشی-تربیتی آرمان نو \| سامانه هوشمند رشد</title>` (17 138 bytes) |
| `Host: women.localhost` `GET /` | **200**, `<title>داشبورد رشد و شکوفایی \| آرمان‌نو - نسیم</title>` (93 500 bytes) — a different app, different hash |
| `Host: men.localhost` `GET /api/auth/csrf/` | **200** `{"csrfToken":"…"}` (JSON, not a 301) |
| `Host: women.localhost` `GET /api/auth/me/` | **401** `{"detail":"اطلاعات برای اعتبارسنجی ارسال نشده است."}` |
| `Host: men.localhost` `GET /media/x.png` | **404** (uploads are not served) |
| `GET /` with no/unknown `Host` | **404** (`default_server`) |
| `GET /healthz` | **200** |

Isolation and versions:

- `docker network inspect educational-intelligence-platform_edge` → `frontend_women frontend_gateway django_core frontend_men`
  (no PostgreSQL, Redis, FastAPI, MinIO or Ollama).
- `docker exec frontend_men getent hosts postgres` (and `frontend_women → redis`, `frontend_gateway → fastapi`) → no record
  (the lookup times out instead of resolving); the gateway has no route for these names either.
- `docker exec celery_worker python -c 'import kombu, redis, celery; print(...)'` → `kombu 5.4.0 redis 5.0.8 celery 5.4.0`;
  `pip show kombu` → `Version: 5.4.0`. Worker log: `Connected to redis://redis:6379/0` … `celery@<id> ready.`
- `docker logs django_core` → no `DisallowedHost`, no traceback.
- `docker compose config --quiet` → exit 0; resolved `ALLOWED_HOSTS: localhost,127.0.0.1,men.localhost,women.localhost`,
  `SECURE_SSL_REDIRECT: "0"` for the Django service only.

## 5. Deviations from the approved proposal (all mechanical or forced, each justified)

1. **D7 implemented as variant (a), not (b).** Presenting `X-Forwarded-Proto: https` at the gateway was built first and
   fails verification: Django compares the browser's `Origin: http://men.localhost:8080` with `get_host()` +
   `is_secure()`, so `login/`/`logout/` would answer **403 CSRF**, and an `http://` origin cannot be allow-listed
   (`eip.E002` forbids it). The compose profile therefore sets `SECURE_SSL_REDIRECT=${SECURE_SSL_REDIRECT:-0}` (code
   default still `True`, server profile sets `1`), and the gateway forwards the real scheme and `Host` as `$http_host`
   (port preserved, which the CSRF comparison needs). The owner's instruction allowed either variant ("`False` **or** via
   `X-Forwarded-Proto`"); **flag for confirmation in the acknowledgements below**. Consequence, documented in
   `DEPLOYMENT.md` §3b and `SECURITY.md`: over plain HTTP a browser discards the fixed-`Secure` session cookie, so a local
   *login* needs TLS; reading the pages and the csrf/`me` endpoints works.
2. **`ALLOWED_HOSTS` is appended, not defaulted.** `.env` already defines `ALLOWED_HOSTS=localhost,127.0.0.1`, so a
   `${ALLOWED_HOSTS:-…men.localhost…}` default would never apply and the gateway would get `400 DisallowedHost`. Compose
   now passes `${ALLOWED_HOSTS:-localhost,127.0.0.1},${MEN_HOST:-men.localhost},${WOMEN_HOST:-women.localhost}`.
3. **`frontend-women/bun.lock` regenerated** (55 deletions): it still pinned the `@lovable.dev/ai-gateway` packages removed
   in change 0040, so `bun install --frozen-lockfile` could not succeed and the app was unbuildable by anyone. Regenerated
   with `bun install`, committed in this change, verified by `--frozen-lockfile` afterwards.
4. **Formatting pass over 20 `src/**` files** (both apps) so the D6 lint gate passes: `prettier` wrapping of long lines and
   imports. No token-level behaviour change (spot-checked diff `frontend-women/src/data/school.ts` and
   `Student360Dialog.tsx`: line wrapping only). Two `import.meta.env[…]`/`process.env[…]` bracket accesses as
   `noPropertyAccessFromIndexSignature` demands.
5. **`frontend-women/vitest.config.ts`: `server.deps.inline: ["zod"]`.** Externalised, the CJS `zod` loads through bare
   Node under vitest and the named `z` import comes back `undefined` (`z.object is not a function`) — a pre-existing test
   breakage that only surfaced once the lockfile allowed an install. One line, test-only.
6. **No `frontend-men/vitest.config.ts` change**: men already passed.
7. **Gateway config split in two files** (`frontends.conf` + `eip_proxy.conf`): the Django forwarding block appears four
   times per app, and one included file keeps the three copies of the header rules identical.
8. **`frontends-dev` profile added** (D3 allowed "in place of separate ports"): opt-in `bun run dev` containers on
   5173/5174, so nobody has to switch to host Node later.
9. **ADR filename** follows the owner's instruction (`0015-frontend-containers-and-gateway.md`); the proposal's §11
   spelling was `…-and-edge-gateway.md`. Paths in `DEPLOYMENT.md`/`SECURITY.md`/`TESTING.md` use the file that exists.


## 6. Test evidence

| Gate | Command | Result |
|---|---|---|
| Python, SQLite | `scripts/run_tests.sh sqlite` | `manage.py check` clean, `makemigrations --check` "No changes detected", **`Ran 1635 tests … OK (skipped=11)`**, `demo_intel` **`Ran 62 tests … OK`** → `ALL DJANGO CHECKS AND TESTS PASSED` |
| Python, PostgreSQL 16 | `scripts/run_tests.sh pg` | `makemigrations --check` "No changes detected", **`Ran 1635 tests in 1688.779s … OK (skipped=1)`** → `POSTGRESQL CHECKS AND TESTS PASSED` |
| FastAPI exposure | `django_core/.venv/bin/python fastapi_core/tests/test_exposure.py` | `Ran 12 tests … OK` (5 pre-existing `ExposureTests`, **5 new `FrontendExposureTests`**, 2 `SingleApplicationTests`) |
| JS gate, per app | inside `docker compose build` | `LINT_OK` (0 errors, 9 pre-existing warnings each), `TSC_OK`, `TEST_OK` (1 routing test each), `BUILD_OK`, `.output/server/index.mjs` produced |
| End-to-end | `docker compose up -d --build` + the curl matrix | §4 |

## 7. `NOT VERIFIED`, `DECISION REQUIRED`, `DEFERRED`

- **NOT VERIFIED — server profile.** No TLS proxy, no real domain, no certificates were exercised here. The claim "the
  school's proxy forwards `men.<domain>`/`women.<domain>` to `127.0.0.1:8080`" is a documented procedure
  (`DEPLOYMENT.md` §3b), not a tested path.
- **NOT VERIFIED — a real browser login over HTTP.** `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` are `True`, so the local
  HTTP origin cannot store the session cookie (see §5.1). Confirmed only at the HTTP level (`csrf/` 200, `me/` 401).
- **NOT VERIFIED — `frontends-dev` profile.** The services are declared and `docker compose config` accepts them; they were
  not started in this session.
- **NOT VERIFIED — a fresh-machine build.** Both images were built with a warm bun/apt/pip cache; a cold build was not timed.
- **RESOLVED 2026-11-13 — D7 variant.** Was `DECISION REQUIRED`; the owner approved **(a)** `SECURE_SSL_REDIRECT=0` through
  the compose profile (code default `True`) — evidence and the approval wording are in §9.
- **DECISION REQUIRED (unchanged from 0040) — no authentication in front of the frontends.** They render constant demo data
  and consume only `/api/auth/*`; an authenticated area still needs its own L2/L3 proposal.
- **DEFERRED — CSP and the remaining hardening headers**, and **DEFERRED — a CI job that builds the images** (the JS gate is
  local/`docker compose build` only, because CI (T-01) is itself deferred).
- **DEFERRED — `EIP_BEHIND_TLS_PROXY`.** Untouched; with the gateway forwarding the real scheme it is irrelevant locally and
  belongs to the TLS-proxy decision.

## 8. Rollback

1. `docker compose stop gateway frontend_men frontend_women` — the Python stack keeps running unchanged (nothing in Django
   imports or depends on the two apps; `/api/`, `/admin/` are reachable directly on `127.0.0.1:8010`).
2. Full revert: `git checkout <commit-before> -- docker-compose.yml django_core/requirements.txt deploy/nginx` and remove the
   two image directories' `Dockerfile`/`.dockerignore`; `docker compose up -d` restores the single-network stack.
3. The kombu pin must be reverted **together** with the compose change, otherwise `celery_worker` returns to
   `VersionMismatch` (kombu 5.7 vs redis-py 5.0.8).

## 9. Owner approvals — **GRANTED 2026-11-13** (change closed)

The owner (Gemini envelope, "تأییدیه رسمی رهبری پروژه") confirmed both items and authorized the merge:

1. **D7 = (a) — APPROVED.** `SECURE_SSL_REDIRECT=0` applies **only** through the compose profile (local/dev); the codebase
   default for production stays `True`. Owner's reason, verbatim in substance: it is the only way local CSRF/session tests
   are not blocked without TLS while production stays safe.
2. **`kombu==5.4.0` — APPROVED.** Exact pairing with `celery==5.4.0` / `redis-py==5.0.8`; guarantees worker stability.
3. **Monitoring change — ACCEPTED.** A result-file watcher instead of dot-polling (the pg run buffers stderr, so dot counts
   are blind).

Merge authorization: "مجوز ادغام (Merge) شاخه `work/0042-frontend-containers` در شاخه اصلی و بسته شدن پرونده 0042 صادر می‌شود."
Executed locally as `git merge --no-ff work/0042-frontend-containers` into `main` on 2026-11-13 (the merge commit is the
`git log` record; this file deliberately carries no hash). **Nothing was pushed** — `main` moves only in this repository,
and `git push` still needs a separate, explicit instruction. The platform is now **deployment-ready at the infrastructure
level** for the Docker stack; the `NOT VERIFIED` / `DECISION REQUIRED` items in §7 (TLS proxy, browser login over HTTP,
`frontends-dev`, cold build, no auth wall in front of the demo frontends) remain open and unchanged.



## 10. Commits (local only, on `work/0042-frontend-containers`)

Three commits, so the risky parts can be reverted independently (the branch was created as `work/frontend-containers` and
renamed to `work/0042-frontend-containers` before the first commit, so the name in the proposal and here matches):

1. **`chore(deps): pin kombu==5.4.0 for celery 5.4 / redis 5.0.8`** — `django_core/requirements.txt`.
2. **`feat(frontends): node-server build target + multi-stage images + JS gate`** — both `vite.config.ts`,
   `frontend-women/vitest.config.ts`, the 4 new image files, the prettier/bracket-access edits under `frontend-*/src/`,
   `frontend-women/bun.lock`.
3. **`feat(deploy): edge gateway, edge/backend split, docs 0042`** — `docker-compose.yml`, `deploy/nginx/*.conf`,
   `docs/adr/0015-*.md`, `docs/changes/0042-*.md`, `docs/{DEPLOYMENT,SECURITY,TESTING,CHANGE_GUIDE}.md`,
   `docs/adr/0014-two-json-frontends.md`, `fastapi_core/tests/test_exposure.py`.

Not committed (untracked workspace noise, unrelated to 0042): `.clinerules/`, `.vscode/`, `docs/pilot/QUEUE.md`.
No file of this change falls under `.git/info/exclude`, so no `git add -f` was needed.
