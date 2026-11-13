# ADR-0015: the two frontends run as containerised Node SSR servers behind one edge gateway

- Status: **ACCEPTED 2026-11-13** (owner, answers D1–D7 of `docs/changes/0042-frontend-containers-PROPOSAL.md`)
- Date: 2026-11-13
- Decider: owner
- Level: L3 (new services, deployment topology, new ingress, build-config change in two apps)
- Relation: implements decision 2 of **ADR-0014** (one origin per app) for deployment; leaves ADR-0014's rules on session
  auth, CSRF, CORS and "no real student data in either app" untouched. Adds no Django model, view, URL or migration.

## Context
`frontend-men` and `frontend-women` are TanStack Start 1.168 + React 19 apps built by Vite 8 through the Lovable wrapper
`@lovable.dev/vite-tanstack-config@2.26.5`. `CURRENT` facts this decision starts from (evidence in change 0042 §2):

- Neither app had a Dockerfile, a `.dockerignore`, a compose service or an nginx route; the host has **no Node toolchain**,
  so the owner could not run them at all, and `scripts/run_tests.sh` has no JS step.
- The wrapper defaults nitro to **`cloudflare-module`**: a plain `bun run build` emits a Workers bundle, not a server that
  can be started with `node`. A caller-supplied `nitro` object overrides `defaultPreset` — that is the supported hook.
- Dependencies come from `bun.lock` (no `package-lock.json`), with a 24 h `minimumReleaseAge` guard in `bunfig.toml`.
- `frontend-women/bun.lock` was **stale** (it still listed `@lovable.dev/ai-gateway`, removed in 0040), so any
  `bun install --frozen-lockfile` failed: the app could not be built reproducibly by anyone.
- Compose production settings (`config/settings/production.py`) default `SECURE_SSL_REDIRECT=True` and
  `EIP_BEHIND_TLS_PROXY=True`; every request to `/api/…` over plain HTTP therefore answered **301**, and
  `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` are fixed `True`.
- Only the compose default network existed: any container, including a presentation frontend, could open a PostgreSQL
  socket. Django was published on `127.0.0.1:8000`, which on the owner's machine is already taken by an unrelated project.

## Decision
1. **Build target: `node-server` (D1).** Each app sets `nitro: { preset: "node-server" }` — two lines in
   `vite.config.ts`, no other build option, no new npm dependency. The build emits a self-hosted Node server
   (`.output/server/index.mjs`) that listens on `PORT=3000` inside the container. `bun run dev` (ports 5173/5174 and the
   `/api` dev proxy) is unchanged, so the existing local workflow keeps working.
2. **Multi-stage images, no host Node (D2).** Build on `oven/bun:1-alpine` (`bun install --frozen-lockfile` → JS gate →
   `bun run build`), run on `node:22-alpine` as the non-root `node` user with only `.output` copied in. The image holds no
   `.env`, no secret, no `VITE_*` secret and no source tree; `PORT`/`NODE_ENV` are the only runtime knobs. Lockfile policy:
   `--frozen-lockfile` is mandatory; when `package.json` changes, `bun.lock` is regenerated and committed in the same
   change (never `--no-frozen-lockfile` silently). The women's lockfile was regenerated under this rule (0042).
3. **JS gate in the image (D6).** `bun run lint`, `bunx tsc --noEmit`, `bun run test` (vitest) and `bun run build` run in
   the build stage and must exit 0, so a frontend that fails lint/typecheck/tests cannot produce a deployable image.
   Making the existing code pass required a repository formatting pass (`prettier` via `eslint --fix`) and two bracket
   accesses (`import.meta.env["VITE_API_URL"]`, `process.env["VITE_DEV_API_TARGET"]`) demanded by
   `noPropertyAccessFromIndexSignature`; both are mechanical, no behaviour change.
4. **One edge gateway (D3).** A single `nginx:1.27-alpine` service is the only ingress:
   `127.0.0.1:${FRONTEND_HTTP_PORT:-8080}` on a laptop. It reads `MEN_HOST` / `WOMEN_HOST` (`men.localhost` /
   `women.localhost` by default) from the environment through the image's template mechanism, one `server` block per app,
   and forwards: `/api/`, `/admin/`, `/static/` → `django:8000`; `/` → `frontend_men:3000` or `frontend_women:3000`;
   `/media/` → 404; an unknown `Host` → 404 (`default_server`). The browser therefore calls `/api/…` on the app's own
   origin, which is ADR-0014 decision 2 literally; `CORS_ALLOWED_ORIGINS` stays empty locally.
5. **Two networks (D4, D7 = a).** `edge` = gateway + both frontends + Django; `backend` = Django + `postgres`, `redis`,
   `fastapi`, `celery`, `celery_beat`, `minio`, `ollama`. The frontends are **not** members of `backend`, so a compromised
   or buggy SSR process cannot open a PostgreSQL or Redis socket; the database is never on `edge`.
6. **Exposure (D5).** The frontends publish **no** host port (a mirror of the FastAPI rule,
   `fastapi_core/tests/test_exposure.py`); FastAPI keeps no port and is not routed by the gateway. Django's host port is
   for debugging only and moves to `127.0.0.1:${DJANGO_HTTP_PORT:-8010}` because the owner's `:8000` is occupied by
   another project. Neither PostgreSQL, Redis, MinIO nor Ollama is published, and the gateway has no route to any of them.
7. **Local TLS policy (D7 = a).** The gateway forwards the real client scheme and the compose profile runs Django
   with `SECURE_SSL_REDIRECT=${SECURE_SSL_REDIRECT:-0}`; the code default in `production.py` stays `True`, and a server
   deployment must set `1` behind its TLS proxy. The alternative the owner also allowed — presenting
   `X-Forwarded-Proto: https` at the gateway (D7 = b) — was implemented first and **rejected during verification**:
   Django compares the browser's `Origin: http://men.localhost:8080` with `request.get_host()` and `is_secure()`, so a
   faked https scheme makes `login`/`logout` answer 403 CSRF, and `CSRF_TRUSTED_ORIGINS` may not carry an `http://`
   origin (deploy check `eip.E002`). `Host` is forwarded as `$http_host` so the port survives that comparison.
   Known limitation: the fixed `Secure` session/CSRF cookies are not stored by a browser over plain HTTP, so a real
   local login needs TLS (a local proxy or tunnel); neither app has a login page yet, and `/api/auth/…` answers
   correctly (200 csrf, 401 me). In the server profile the school's existing TLS proxy terminates 443 and forwards
   `men.<domain>` / `women.<domain>` to `127.0.0.1:8080` preserving `Host`; `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
   gain the two https origins through the environment, no code default changes.
8. **Optional hot-reload profile (D3).** `--profile frontends-dev` runs `bun run dev` in `oven/bun:1-alpine` with the source
   bind-mounted and a named volume for `node_modules`, publishing 5173/5174 on loopback. It is opt-in only; the default
   `docker compose up` starts the built images.
9. **`ALLOWED_HOSTS` for the new names.** Compose passes
   `ALLOWED_HOSTS=${ALLOWED_HOSTS:-localhost,127.0.0.1,men.localhost,women.localhost}`; an explicit value in `.env`
   (server profile) still wins. No `SECURE_*` default is relaxed by this change.
10. **Celery/Redis pair pinned.** `kombu` is pinned to `5.4.0` next to `celery==5.4.0` and `redis==5.0.8`: an unpinned
    kombu resolved to 5.7.0, whose Redis transport refuses redis-py < 6.1 (`VersionMismatch`) and made `celery_worker`
    exit 1 — a defect independent of the frontends, fixed in the same change because "one command brings everything up"
    requires a surviving worker.

## Alternatives considered
- **Static SPA build (TanStack Start `spa` mode) served by nginx.** No Node runtime and fewer services, but it changes the
  apps' rendering model (SSR error wrapper, `src/start.ts`) — a bigger behavioural change than a two-line preset override.
  Kept as a fallback, not chosen.
- **`bun run dev` containers only.** Hot reload and no build, but never exercises the production build and leaves the
  server profile unverified; offered only as an opt-in profile.
- **Publish 5173/5174 and call Django cross-origin from the browser.** Needs CORS entries, `SameSite` care and contradicts
  ADR-0014 decision 2; refused.
- **One container running nginx + Node under a supervisor.** Fewer containers, harder to health-check and to rebuild
  independently; refused.
- **Present `X-Forwarded-Proto: https` at the gateway (D7 = b).** Keeps `SECURE_SSL_REDIRECT=True` untouched, but makes
  `request.is_secure()` disagree with the browser's `http` origin: CSRF verification fails on any POST through the
  gateway, and the `http://` origin cannot be allow-listed (`eip.E002`). Tried and reverted — the compose profile sets
  `SECURE_SSL_REDIRECT=0` instead and the server profile keeps `1` behind real TLS.
- **Keep one flat compose network.** Simplest, but leaves every presentation container one socket away from PostgreSQL;
  refused (D4).
- **`--no-frozen-lockfile` to get past the stale women's lock.** Hides a reproducibility defect and silently changes
  dependency versions on every build; refused — the lockfile is regenerated and committed instead.

## Consequences
- **Security.** One new ingress, loopback-bound by default, serving two pages of constant demo data and proxying `/api`,
  `/admin`, `/static` to Django. No route to FastAPI, PostgreSQL, Redis, MinIO or Ollama; `/media/` 404; rate limits on
  login/token paths in addition to Django's throttle; `server_tokens off`; `nosniff`, `X-Frame-Options: DENY` and
  `Referrer-Policy: same-origin` on responses nginx itself generates. No secret is baked into a frontend image, and no
  token is stored in `localStorage` (ADR-0014 §3). `SECURE_SSL_REDIRECT`, `EIP_BEHIND_TLS_PROXY`, CSRF and `SameSite`
  stay exactly as delivered by 0040.
- **Data.** None: no model, migration, index or data migration; the apps still hold no school data and no persistence.
- **Testing.** The JS gate now runs inside the image build (lint, typecheck, vitest, build) and is therefore part of
  `docker compose build`; the Python gate is unchanged. Gateway behaviour (200 on `/`, JSON on `/api/auth/csrf/`, 401 on
  `/api/auth/me/`, 404 on `/media/`, no published frontend port, no frontend→postgres route) is verified by commands
  recorded in `docs/changes/0042-…-REPORT.md`, and the exposure rule stays a test (`fastapi_core/tests/test_exposure.py`)
  that is extended for the new services.
- **Operations.** `docker compose up -d --build` from an empty data directory is the whole procedure; the school server
  adds the outer TLS proxy and two hostnames. Rebuilding one frontend does not restart the other. Disk: two extra images
  (Node runtime) and a bun dependency layer per app; the build stage is the heavy part and is cached on the lockfile.
- **Customization.** `MEN_HOST`, `WOMEN_HOST`, `FRONTEND_HTTP_PORT`, `DJANGO_HTTP_PORT` and the two origins are environment
  values with loopback defaults; a school domain is a `.env` change, not a code change.

## Compliance with standing rules
- ADR-0013 (no React SPA for real data) is untouched: this decision packages the existing presentation apps and adds no
  data screen, endpoint or ACL.
- ADR-0014 decisions 2–8 remain in force: same origin, session auth, CSRF on, fail-closed CORS, no third-party egress.
- Data access still goes through `students/access.py`; no entitlement or audit rule is modified.
- The school's TLS/certificate handling stays outside this stack (no ACME client, no key in git).

