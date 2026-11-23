# 0045 — Domain hardening, dynamic routing & 6-role gateway exposure — REPORT

- Status: **DONE & VERIFIED** (live stack + test suite)
- Branch: `main`
- Scope: Task 1 (domain abstraction, SPA/SSR routing, API/CORS) + the gateway routing gap that hid the 6-role product.

## 1. What changed

| File | Change |
|---|---|
| `.env` (gitignored) | Centralized the domain block: added `APP_DOMAIN_MEN` / `APP_DOMAIN_WOMEN` / `API_BASE_URL`, added the missing `WOMEN_HOST` (`nasim.arman-no.meysamai.ir`), fixed `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS` (the phantom `arman.meysamai.ir` is gone), removed the junk `school_owner` line and the unused `DB_USER=school_user`. |
| `.env.example` | Documented the single-source-of-truth domain scheme (was missing `DB_*_PASSWORD`, `WOMEN_HOST`, origins). |
| `docker-compose.yml` | Gateway `MEN_HOST`/`WOMEN_HOST` and Django `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`CORS_ALLOWED_ORIGINS` are now **derived from `APP_DOMAIN_*`** — changing two `.env` values reconfigures both sites with no other edit. |
| `deploy/nginx/frontends.conf` | (a) Documented the SSR fallback — `try_files $uri /index.html` is intentionally absent (Nitro `node-server`, no static file root). (b) Added a regex location routing Django's HTML product routes (`/school`, `/students/…/360`, `/teacher`, `/counselor`, `/grade`, `/dashboard`, `/mission`, `/exams`, `/rules`, `/assistant`, `/me`, …) to Django, so deep links render instead of 404. |

## 2. Verification (actually run)

- `docker compose config` — `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `MEN_HOST`, `WOMEN_HOST` resolve to `arman-no.meysamai.ir` + `nasim.arman-no.meysamai.ir`; nested `${…}` interpolation works.
- Recreated `gateway` + `django`; live curl through `127.0.0.1:8080`:
  - `Host: arman-no.meysamai.ir` `GET /` → 200 (men app); `Host: nasim.arman-no.meysamai.ir` `GET /` → 200 (women app).
  - Deep routes (`/school/`, `/dashboard/`, `/students/1/360/`, `/teacher/`, `/counselor/`, `/grade/`, `/mission/`, `/exams/`, `/rules/`, `/assistant/`) → **302 → `/login/?next=…`** (was 307→404) on both hosts.
  - `/api/auth/csrf/` → 200, `/api/auth/me/` → 401 (correct anonymous behaviour).
  - Phantom `arman.meysamai.ir` and stale `women.localhost` → 404.
- Django test suite (role journeys): `dashboard.test_e2e_user_flow dashboard.test_a11y_render` → **45 tests OK (expected failures=1)** — login redirects per role, a11y walk across all 6 demo roles.
- `scripts/preflight.py .env` — remaining items are production-only (see §4).

## 3. What the two React apps still are (not changed)

`frontend-men` / `frontend-women` are TanStack Start **Nitro `node-server` SSR** apps with a **single `/` route**: hardcoded demo dashboards (KPI numbers, student names, charts). They do **not** call the Django API yet, and they do **not** implement the 6-role views. The complete, tested 6-role product is the **Django** server-rendered app, now reachable through the gateway (this change).

## 4. Production handover notes

- **Women domain** set to `nasim.arman-no.meysamai.ir` (owner-provided). Both apps now share the `arman-no.meysamai.ir` registrable domain.
- **Before real data / TLS:** generate `EIP_BACKUP_PUBKEY`, rotate `DB_ADMIN_PASSWORD` to ≥16 chars, and remove `localhost,127.0.0.1` from `ALLOWED_HOSTS` (dev base only).
- **`SERVICE_JWT_SECRET`** lives in `.env.service` (correct; preflight reads only `.env`).
