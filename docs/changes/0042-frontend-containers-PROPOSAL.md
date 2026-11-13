# 0042 — Containerised `frontend-men` / `frontend-women` + one edge gateway (CHANGE PROPOSAL — nothing is implemented)

Written 2026-11-13. **Level: L3** (new services, deployment topology, new public ingress, build-config change in
two apps) → per `docs/CHANGE_PROCESS.md` this needs a **proposal → ADR-0015 → explicit owner approval** before the first
line of code. **Status: PROPOSED.** Nothing below is implemented; no Dockerfile, compose service, nginx file or frontend
config was changed for this proposal.
Truth labels: `CURRENT` (verified in this working tree / by a command, evidence given) · `TARGET` · `PROPOSED` ·
`DECISION REQUIRED` · `NOT VERIFIED` · `DEFERRED`.

Read with: `docs/adr/0014-two-json-frontends.md`, `docs/changes/0040-dual-frontend-integration-REPORT.md`,
`docs/DEPLOYMENT.md` (§2, §3a), `deploy/nginx/eip.conf.example`, `frontend-men/{package.json,vite.config.ts,bunfig.toml}`,
`frontend-women/{package.json,vite.config.ts}`.

---

## 1. Requirement

The owner asked (2026-11-13) for the whole platform to come up with **one docker command** on a laptop and on a server,
including both Persian frontends, **without installing Node.js by hand**:

> «برای فرانت‌های frontend-men و frontend-women داکرفایل و کانفیگ Nginx مناسب بر اساس ADR-0014 بنویس و آن‌ها را به
> عنوان سرویس‌های مجزا به docker-compose.yml اضافه کن تا کل پلتفرم (فرانت + بک) با یک دستور داکر روی لوکال و سرور
> بدون نیاز به نصب دستی Node بالا بیاید.»

Scope: packaging and serving only. This proposal does **not** add a login page, does **not** wire student data into the
apps (ADR-0014 §1 keeps that behind a separate L2 proposal), and does **not** add an AI feature (§8).

**Precondition (CURRENT, same session).** The stack was down with a stale PostgreSQL data directory: `data/postgres`
contained a database created with a different bootstrap role, the entrypoint logged *"Skipping initialization"*, so
`deploy/postgres/10-roles.sh` had never run and `school_owner`/`school_app` did not exist. The directory was preserved as
`data/postgres.bak-20261113-122102` and the stack was re-created from an empty data directory. Note: `docker compose
down -v` alone would **not** have fixed it, because the data directory is a **bind mount** (`docker-compose.yml:152`),
not a named volume.

## 2. Current behaviour (`CURRENT`, with evidence)

### 2.1 Compose

| Fact | Evidence |
|---|---|
| Services today: `django`, `migrate`, `celery`, `celery_beat`, `fastapi`, `postgres`, `redis`, `minio`, `ollama`. **No frontend service, no nginx service.** | `docker-compose.yml:27-187` |
| Django is published on **loopback only**: `127.0.0.1:8000:8000`. | `docker-compose.yml:32-33` |
| FastAPI publishes **no** port (only reachable over the compose network); a test fails if a port is published. | `docker-compose.yml:116-118`; `fastapi_core/tests/test_exposure.py` |
| PostgreSQL / Redis / MinIO publish no host port; Ollama is `127.0.0.1:11435`. | `docker-compose.yml:147,159,167-168,179-181` |
| Only the compose default network exists: every container can reach PostgreSQL directly. | `docker-compose.yml` (no `networks:` key) |
| Neither frontend has a Dockerfile or a `.dockerignore`. | `find frontend-men frontend-women -iname 'Dockerfile*'` → empty |

### 2.2 The two frontends

| Fact | Evidence |
|---|---|
| Tracked TanStack Start 1.168 + React 19 apps built by Vite 8; scripts are `build: "vite build"`, `dev: "vite dev"`, `test: "vitest run"`. | `frontend-men/package.json:6-15,50,90,95`; same in `frontend-women` |
| Dependencies are installed with **bun** (`bun.lock`, `bunfig.toml` with a 24 h `minimumReleaseAge`); there is no `package-lock.json`. | `frontend-men/bun.lock`, `frontend-men/bunfig.toml:1-7` |
| The config is the **Lovable wrapper** `@lovable.dev/vite-tanstack-config@2.26.5`, not plain `vite`. | `frontend-men/vite.config.ts:10` |
| That wrapper defaults nitro to **`cloudflare-module`** outside the Lovable sandbox: `const nitroOpts = { defaultPreset: "cloudflare-module", ...userNitroOpts }`. A plain `vite build` therefore emits a **Workers bundle (`dist/server`, `dist/client`), not a Node server**. | wrapper `dist/index.js` v2.26.5, read from unpkg 2026-11-13 — `CURRENT`, external |
| The wrapper lets a caller-supplied `nitro` object win over `defaultPreset`, so `defineConfig({ nitro: { preset: "node-server" } })` is the supported override. | same source (`...userNitroOpts`, `if (!nitroOpts.preset …)`) |
| In **dev only**, each app proxies `/api` to `http://127.0.0.1:8000` (ports 5173 / 5174, `strictPort`); `vite preview` and the build do not proxy. | `frontend-men/vite.config.ts:21-29`; `frontend-women/vite.config.ts:21-29` |
| The browser client uses a **relative** base URL (`VITE_API_URL` default `/api`) with `credentials: "include"`, i.e. it expects one origin and the ordinary `sessionid` cookie. | `frontend-men/src/lib/api.ts:13,115` |
| No `gender_scope`/`theme` field exists; every number on screen is still a constant and **there is no login page yet** (`apiLogin()` is unused). | `docs/changes/0040-…-REPORT.md:41-43,74-75` |
| Neither app is built by the test gate; no CI job builds JS; `npm ci`/`tsc`/`vitest` are **NOT VERIFIED** (no Node toolchain on this host). | `docs/adr/0014-…md:70-71,79-81`; `scripts/run_tests.sh` has no JS step |

### 2.3 Django settings a same-origin gateway must respect

| Fact | Evidence |
|---|---|
| `ALLOWED_HOSTS` is env-driven, default `localhost,127.0.0.1`; every new hostname (e.g. `men.localhost`) must be added. | `django_core/config/settings/base.py:9` |
| `SECURE_SSL_REDIRECT` defaults to **True** and `EIP_BEHIND_TLS_PROXY` to **True** in the production settings compose uses. A local HTTP gateway therefore needs `SECURE_SSL_REDIRECT=0` (and `EIP_BEHIND_TLS_PROXY=0` when nothing terminates TLS), otherwise `/api/…` answers **301 → https**. | `django_core/config/settings/production.py:62-64` |
| `CSRF_TRUSTED_ORIGINS` is env-only; unnecessary locally behind one origin with `SameSite=Lax`, required for two real `https://` hostnames. | `django_core/config/settings/production.py:67`; ADR-0014 §4 |
| The existing proxy example covers **Django only** (static alias, `/media/` 404, auth rate limit, `eip_proxy.conf`); it has no frontend `server` block. | `deploy/nginx/eip.conf.example:1-58` |
| ADR-0014 decision 2: both apps are served behind **the same reverse proxy as Django**, so the browser makes no cross-origin request (D2=a). | `docs/adr/0014-two-json-frontends.md:30-32` |


## 3. Desired behaviour (`TARGET`)

One command, on a laptop and on a school server:

```sh
docker compose up -d --build            # backend + both frontends + edge proxy
```

After it returns, `docker compose ps` shows every service `Up` (frontends and gateway `healthy`), and a browser opens
the boys' app at `http://men.localhost:8080/` and the girls' app at `http://women.localhost:8080/`
(hostnames/port are env-tunable, §12). Each app calls `/api/…` on **its own origin**; the gateway forwards those paths to
`django:8000` over the compose network.

### 3.1 Planned pieces (all `PROPOSED`)

| # | Piece | Content |
|---|---|---|
| P1 | `frontend-men/Dockerfile`, `frontend-women/Dockerfile` | Multi-stage: **build** on `oven/bun:1-alpine` (exact tag/digest pinned at implementation) → `bun install --frozen-lockfile` → `bun run build`; **runtime** on `node:22-alpine` running `node .output/server/index.mjs` as the non-root `node` user, `EXPOSE 3000`, `HEALTHCHECK` on `/`. No source bind mount, no `.env` inside the image. |
| P2 | `frontend-*/.dockerignore` | `node_modules`, `dist`, `.output`, `.wrangler`, `*.log`, `.git` — keeps the build context small (disk was at 95 %, 8.2 GB free). |
| P3 | `frontend-*/vite.config.ts` (+2 lines each) | `nitro: { preset: "node-server" }` so the wrapper emits a self-hosted Node server instead of a Workers bundle. Dev ports and the `/api` dev proxy stay untouched. |
| P4 | `deploy/nginx/frontends.conf` | One nginx file, **one `server` block per app** (`server_name ${MEN_HOST}` / `${WOMEN_HOST}`): `location /api/` → `http://django:8000` (`Host` overwritten, no `X-Forwarded-Proto: https` locally), `location /` → `http://frontend_men:3000` / `http://frontend_women:3000`, `location /media/` → 404, rate limit on `/(login|api/auth|api/token)`, `client_max_body_size`, `server_tokens off`, security headers (Django's headers do **not** cover responses nginx generates). |
| P5 | `docker-compose.yml` | Three new services: `frontend_men`, `frontend_women` (build from their dirs, **no host ports**, `restart: unless-stopped`, healthcheck) and `gateway` (`nginx:1.27-alpine`, `127.0.0.1:${FRONTEND_HTTP_PORT:-8080}:80`, mounts `deploy/nginx/frontends.conf`, `depends_on` both frontends `service_healthy` **and** `django`, healthcheck). Optional `frontends-dev` profile (`bun run dev`, bind mounts, 5173/5174) for hot reload — D3. |
| P6 | Networks | Two networks: `edge` (gateway ↔ frontends ↔ django) and `backend` (django ↔ postgres/redis/fastapi/celery). The frontends must **not** reach PostgreSQL/Redis; Django joins both. |
| P7 | Docs | `docs/DEPLOYMENT.md` §3b (local + server), `SECURITY.md` (new public surface), `TESTING.md` (JS gate), `CHANGE_GUIDE.md` `Verified-at`, ADR-0014 decision note + new **ADR-0015**. |

### 3.2 Server profile

Same compose file with the gateway **not** published publicly: the school's TLS proxy (`deploy/nginx/eip.conf.example`,
adapted) terminates 443 and proxies `men.<domain>` / `women.<domain>` to `127.0.0.1:8080`, preserving `Host` so nginx
picks the right `server` block. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` gain the two `https://` origins. Certificates
stay outside this stack (no ACME client, no key in git).

## 4. Affected modules

`frontend-men/`, `frontend-women/` (Dockerfile + `.dockerignore` + 2-line config change each) · `deploy/nginx/` (new
file) · `docker-compose.yml` (3 services, 2 networks, env defaults) · docs (§11). **No Django module, model, view, URL,
template or migration is touched**; `/api/auth/…` and the CORS policy stay exactly as delivered by 0040.

## 5. Data impact

None. No model, migration, index or data migration. The frontends keep **no** copy of school data (all numbers are
constants) and store **no token** in `localStorage` (ADR-0014 §3). Persistent state stays in `./data/{postgres,redis,minio,ollama}`.


## 6. API impact

No new endpoint and no schema change. The existing `/api/auth/{csrf,login,logout,me}/` are reached through the gateway on
the app's own origin, so `CORS_ALLOWED_ORIGINS` stays **fail-closed and empty** locally (ADR-0014 §5, `eip.E007`). Server
deployments add the two `https://` origins and hostnames to `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` through the
environment; no code default changes.

## 7. Frontend impact

- **Build target only**: `nitro: { preset: "node-server" }` in each `vite.config.ts`. `bun run dev`, ports 5173/5174 and
  the `/api` dev proxy are unchanged, so the current local workflow still works.
- Because the apps are served same-origin, `src/lib/api.ts` needs **no** change (relative `/api`, `credentials: "include"`).
- **NOT VERIFIED until approval**: that `bun install --frozen-lockfile` and `bun run build` succeed for either app on
  `oven/bun:1-alpine` (the 24 h `minimumReleaseAge` guard in `bunfig.toml` can slow or refuse a fresh install), and that
  the node-server output path is `.output/server/index.mjs` for nitro `3.0.260603-beta`. The implementation step starts
  with a build spike and records the real exit codes/paths in the report.
- A JS gate (`bun run lint`, `bun run test`) becomes runnable in-container; whether it enters `scripts/run_tests.sh` is D6.

## 8. AI impact

None. No prompt, model, RAG or provider change. The external Lovable AI gateway was already removed in 0040; the SSR
container makes **no** outbound AI call and holds no key. FastAPI stays off the gateway.

## 9. Security impact (L3 review required)

| Topic | Proposed control |
|---|---|
| New public surface | Only two SSR pages with constant demo data; `/api` proxied to Django; `/media/` 404; **no** route to `fastapi:8001`, `postgres`, `redis`, `minio` or `ollama`. |
| Network segmentation | `edge` vs `backend` networks (§3.1 P6): a compromised frontend container cannot open a Postgres socket. |
| Secrets | No `.env` mounted, no build args, no `VITE_*` secret (Vite inlines them into the bundle), no token in `localStorage`. Gateway config contains no credential. |
| CSRF / sessions | Same-origin only; `SameSite=Lax` and CSRF stay on; gateway must **not** strip `Cookie`/`X-CSRFToken` or rewrite `Host`. |
| Headers | nginx sets `X-Content-Type-Options`, `X-Frame-Options`/frame-ancestors, `Referrer-Policy`, and a conservative CSP for the pages **it** serves (Django's middleware does not see them). |
| Abuse | `limit_req` on login/token paths in addition to Django's own throttle; `client_max_body_size`; `server_tokens off`. |
| TLS | Local: loopback-bound gateway over HTTP. Server: TLS terminates in the existing outer proxy; no certificate inside this stack. |
| Supply chain | Base images pinned by tag+digest at implementation; `bun install` uses the committed lockfile; no new npm dependency. |
| Data policy | Pilot/presentation only: **no real student data** in either app (ADR-0014 §1, `SECURITY.md`). |
| Deployment check | `SECURE_SSL_REDIRECT` / `EIP_BEHIND_TLS_PROXY` must be set per environment (§2.3); a wrong value breaks login with a 301, it does not silently weaken TLS. |

## 10. Testing strategy

1. `docker compose config --quiet` (interpolation, no required var missing) — **CURRENT** for today's file.
2. Build only the new images: `docker compose build frontend_men frontend_women` → both exit 0 (**NOT VERIFIED**, build spike).
3. `docker compose up -d` → `docker compose ps` shows `frontend_men`, `frontend_women`, `gateway` `Up (healthy)` and
   `django_core` `Up`; `docker compose logs migrate` ends with a successful migrate.
4. Gateway checks (real output recorded in the report):
   - `curl -s -o /dev/null -w '%{http_code}' -H 'Host: men.localhost' http://127.0.0.1:8080/` → 200; same for women.
   - `curl -s -H 'Host: men.localhost' http://127.0.0.1:8080/api/auth/csrf/` → JSON + `Set-Cookie: csrftoken`.
   - `curl -s -o /dev/null -w '%{http_code}' -H 'Host: men.localhost' http://127.0.0.1:8080/api/auth/me/` → **401 JSON** (not 403/302).
   - `curl -s -o /dev/null -w '%{http_code}' -H 'Host: men.localhost' http://127.0.0.1:8080/media/x` → 404.
   - `docker compose port frontend_men 3000` → empty (no host port published); `docker compose exec frontend_men wget -qO- http://postgres:5432` fails (network isolation).
5. Backend regression: `manage.py test dashboard.test_auth_api dashboard.test_deploy_checks` (the CORS/host surface), then
   the full `scripts/run_tests.sh sqlite` and `… pg` at the end of implementation, output redirected to a file and read back.
6. Optional JS gate: `bun run lint` and `bun run test` inside the build stage (D6).
7. **Negative test to keep**: a published frontend port or a gateway route to `fastapi` must fail a check (mirroring
   `fastapi_core/tests/test_exposure.py`), so the topology cannot regress silently.


## 11. Documentation impact

| File | Change |
|---|---|
| `docs/adr/0015-frontend-containers-and-edge-gateway.md` | **New ADR** (required for L3): build target, gateway topology, two networks, exposure rules. |
| `docs/adr/0014-two-json-frontends.md` | Decision note pointing to ADR-0015 (serving/deployment of the two apps). |
| `docs/DEPLOYMENT.md` | New §3b "Frontends + edge gateway" (local and server), network topology, the `SECURE_SSL_REDIRECT`/`EIP_BEHIND_TLS_PROXY` requirement. |
| `docs/SECURITY.md` | New subsection under "JSON auth API and CORS": public surface, network segmentation, headers, no secrets in images. |
| `docs/TESTING.md` | The new checks (§10) and whether the JS gate is mandatory. |
| `docs/CHANGE_GUIDE.md` | `Verified-at` bump and the new file locations. |
| `docs/changes/0042-…-REPORT.md` | Written after implementation, with real build/run output. |
| `docs/manuals/*` | Only if a role's visible workflow changes (it does not — no data screen is added). |

## 12. Customization impact

Nothing school-specific in code: `MEN_HOST`, `WOMEN_HOST`, `FRONTEND_HTTP_PORT`, image tags and the two origins are
compose/environment values, with loopback defaults for a laptop. Each app keeps its own build-time theme
(`frontend-*/README.md`), so no theme field is introduced. A future school key/domain is a `.env` change, not a code change.

## 13. Risks

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Nitro override does not produce a Node server (wrapper assumptions, beta nitro) | medium / blocks the plan | Build spike first (P3), record the real output; fallbacks: `nitro.output`, `vite preview` server, or static SPA build (`spa` mode) as a separate decision |
| `bun install --frozen-lockfile` fails (lockfile drift, 24 h release guard) | medium / blocks the build | Fail loudly in CI/local; never `--no-frozen-lockfile` silently; document the exact bun tag |
| Disk pressure (8.2 GB free; 58 GB images, 14 GB reclaimable) | medium / build failure | `docker image prune`/`builder prune` before the first build; frontend images are small (<300 MB) |
| Memory: two Node SSR servers + torch/FastAPI on a laptop | medium / slow | `NODE_OPTIONS` limit, `mem_limit`, and a compose **profile** if the owner prefers |
| Security headers missing on SSR responses | high if forgotten | explicit header block in nginx + a curl assertion in §10 |
| Dev/prod drift (compose prod uses `production.py` with TLS redirect on) | high locally | `.env` values documented; `/api` 200-vs-301 assertion in §10 |
| Two hostnames (`men.localhost`) not resolvable on some OS/proxy | low | fallback to two ports `8080`/`8081` (D2=b) |
| Frontend images drift from the repo | low | images built from the repo in compose; no registry push in this change |

## 14. Recommendation, alternatives, decisions

**Recommendation: approve P1–P7 with `node-server` SSR and one nginx gateway on hostnames.** It satisfies ADR-0014
decision 2 literally (one origin per app, no CORS entry), keeps Node inside Docker (no host install), and adds no
dependency to either `package.json`.

**Alternatives considered**

1. **Static SPA build (TanStack Start `spa` mode) served by nginx** — fewest moving parts and no Node runtime, but it
   changes the apps' rendering model (SSR error wrapper, `src/start.ts` middleware) and is a bigger behavioural change
   than the 2-line nitro preset. Kept as a fallback if the build spike fails.
2. **`bun run dev` containers only** — hot reload, but not a server profile; the production build would stay unverified.
   Offered as an optional profile (D3), not as the main answer.
3. **One container running nginx + node under a process supervisor** — fewer services, harder to health-check and to
   rebuild independently; rejected.
4. **Publish the two Vite preview ports (5173/5174) and let the browser call `127.0.0.1:8000` cross-origin** — needs CORS
   entries and `SameSite` care, contradicts ADR-0014 decision 2; rejected.

**ADR needed:** yes — **ADR-0015** (service topology + edge gateway). No Django model, API or auth change.

**DECISION REQUIRED (owner)**

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | Serving mode | (a) `node-server` SSR (b) static SPA (c) dev-only containers | **a** |
| D2 | Local addressing | (a) `men.localhost` / `women.localhost` on one port `8080` (b) two ports 8080/8081 (c) path prefixes `/men`, `/women` | **a** (c forces a basepath change in both apps) |
| D3 | Dev profile | (a) none (built images only) (b) optional `frontends-dev` profile with bind mounts + hot reload | **b**, opt-in via `--profile` |
| D4 | Always-on vs profile | (a) frontends start with `docker compose up` (b) behind a `frontends` profile | **a** (the requirement is "one command") |
| D5 | Gateway binding | (a) `127.0.0.1:8080` (b) `0.0.0.0:8080` for a LAN demo | **a**; (b) only with the owner's explicit approval |
| D6 | JS gate in `scripts/run_tests.sh` | (a) build only (b) build + `lint` + `vitest` | **b** once the images build reliably |
| D7 | Network split (`edge`/`backend`) | (a) yes (b) keep one default network | **a** |

**Explicitly out of scope:** login page, real student data in either app, AI features, TLS termination inside this stack,
registry publishing, CI for JS, and any change to `/api/auth/…`.

**Status: PROPOSED — awaiting the owner's answers to D1–D7 and approval before any Dockerfile, compose, nginx or
`vite.config.ts` line is written.**

