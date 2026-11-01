# DEPLOYMENT — DRAFT PROPOSAL

Status: **PROPOSED / DRAFT** (2026-10-15; §3/§3a updated 2026-11-01 by P3 C-H, owner decisions OW-1..OW-4 in `changes/0028`). Nothing here is implemented unless marked `CURRENT`. Created on the owner's instruction (R-03 decision); not an approved design.

> **NO REAL STUDENT DATA in any environment until the Phase 3 security baseline exit criteria (`SECURITY.md`) are met.** Everything below, including any public or hosted demo, uses synthetic data only.

## 1. Scope

- `CURRENT` setting: **Dev/Demo on a single VM.** Django is published on `127.0.0.1:8000` only (`50b3b67`); FastAPI on `127.0.0.1:8001`; PostgreSQL, Redis, MinIO are not published; Ollama is loopback-only. Access from outside the VM requires an SSH tunnel.
- `TARGET` of this document: the minimum architecture for a **web-server deployment** (a hostname reachable by users). That is a decision gate, see section 9. Level: L3 (service boundaries, storage, authN exposure) → ADR + explicit owner approval before any implementation.

## 2. Target architecture (PROPOSED)

```
Internet ──443──> reverse proxy (TLS, HSTS, headers, rate limit)
                      │  (internal network only)
                      ├──> gunicorn / Django   (no published port)
                      │        ├──> PostgreSQL (no published port)
                      │        ├──> Redis      (no published port)
                      │        └──> FastAPI    (no published port; Django-issued service JWT only)
                      └──> static files (served by proxy; collectstatic output)
```

- One public entry point: the reverse proxy on 80 (redirect only) and 443.
- Gunicorn binds inside the container network; the compose file publishes **no** application, database, cache or object-store port in this profile.
- FastAPI is reachable only from Django (it already requires a service token); it is never routed by the proxy.
- Celery and Celery beat run on the same internal network, no ports.
- Ollama/MinIO are optional; if enabled they stay internal.
- Proxy product (nginx / Caddy / Traefik) is `DECISION REQUIRED`; no framework change is implied.

## 3. Django settings required (production profile)

`CURRENT` in `config/settings/production.py`: `DEBUG = False` (no env override), `SECRET_KEY` fail-closed (length / placeholder checks), PostgreSQL, Redis cache. `ALLOWED_HOSTS` comes from the `ALLOWED_HOSTS` env var (default `localhost,127.0.0.1`).

`CURRENT` since 2026-11-01 (`config/settings/production.py`, tests `dashboard/test_deploy_checks.py`), values from the environment:

| Setting | Value | Env |
|---|---|---|
| `ALLOWED_HOSTS` | exact public host name(s) | `ALLOWED_HOSTS` (deploy check eip.E001 refuses empty, `*`, localhost-only) |
| `CSRF_TRUSTED_ORIGINS` | `https://<domain>` | `CSRF_TRUSTED_ORIGINS` (eip.E002 refuses `http://`) |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` | on unless `EIP_BEHIND_TLS_PROXY=0`; the proxy must overwrite the header and gunicorn must not be reachable directly |
| `SECURE_SSL_REDIRECT` | `True` | `SECURE_SSL_REDIRECT` (eip.W003 if on without the proxy header) |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` (fixed) | — |
| `SECURE_HSTS_SECONDS` | 3600 by default (staged; raise to 604800, then 31536000) | `SECURE_HSTS_SECONDS`; eip.I006 reminds while below one year |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` / `PRELOAD` | off / off (preload fixed off) | `SECURE_HSTS_INCLUDE_SUBDOMAINS` |
| nosniff, `X_FRAME_OPTIONS='DENY'`, referrer `same-origin` | on (fixed) | — |
| `LOGGING` | console, WARNING+, no e-mail handler, no request bodies | — |
| Database password | must be set | eip.E005 |
| Login/token rate limiting | `CURRENT` in the app (`dashboard/throttle.py`) plus the proxy (`deploy/nginx/eip.conf.example`); behind a proxy set `THROTTLE_TRUSTED_PROXIES` | — |
| No external assets in pages | Bootstrap, icons and Chart.js are self-hosted (`dashboard/static/dashboard/vendor/`) | eip.E004 scans first-party templates |
| Admin URL | still `/admin/`; optional IP allow-list at the proxy (example config); closure of the admin = C-A (Tier C) | — |

Release gate: `DJANGO_SETTINGS_MODULE=config.settings.production python manage.py check --deploy --fail-level WARNING` with the real environment (exit 0; Django's W005/W021 are silenced on purpose, see the settings comment).

## 3a. HTTPS for a `.ir` domain (owner decision OW-3; decision pack 0028 P3-3/P3-4)

- **Provider-agnostic:** TLS ends at any reverse proxy; `deploy/nginx/eip.conf.example` is a complete generic example (HTTP→HTTPS redirect, ACME challenge path, TLS 1.2/1.3, upload limit, rate limits for login/token, static files, no direct media). Caddy or HAProxy work the same way; a hosting provider's CDN/WAF may sit in front, but the platform must stay secure without it.
- **Certificate:** any ACME CA (renew 30 days before expiry; monitor expiry) or a commercial certificate. Whether a given CA issues for `.ir` and is reachable from the chosen hosting network is **NOT VERIFIED**; check at setup and keep a second CA as fallback. No OCSP stapling (the CA's responder may be unreachable from a domestic network).
- **HSTS staging:** 1 hour > 1 week > 1 year, each step only after a week without HTTPS problems; `includeSubDomains` only when every subdomain serves HTTPS; never preload during the pilot.
- **National-network resilience:** pages load nothing from abroad (eip.E004). Fonts, scripts and stylesheets are served by the platform, so a server inside Iran keeps working during an international outage. Certificate renewal still needs the CA: renew early.
- **Dedicated install (school's own server, OW-1):** same files; the school's domain or a subdomain of the platform's; the school names its operator (0028 P3-1).


## 4. Prerequisites (blockers)

1. **R-04: `school_user` is a PostgreSQL superuser** (`SECURITY.md`, deferred). Must be fixed before any web-server deployment: a least-privilege application role owning only its schema (no `SUPERUSER`, `CREATEDB`, `CREATEROLE`), plus a separate migration role if needed. Requires a migration runbook and PostgreSQL verification (L3, own proposal).
2. R-03 closed for Dev/Demo (loopback). A web server needs the proxy + HTTPS above.
3. Redis has no authentication: acceptable only while unpublished and internal; add `requirepass` or ACL if the network is shared.
4. Phase 3 security baseline exit criteria met (also gates real data).
5. CI (T-01) running both SQLite and PostgreSQL suites, so a deployment candidate is tested (currently deferred).
6. Torch/model artifacts: S-11 (tracked pickle model binaries) decision made; model loading is `torch.load` on tracked files.

## 5. Secrets handling (PROPOSED)

- Secrets only via environment / secret files outside git (`.env`, `.env.fastapi` are untracked; never printed or committed).
- Distinct values per environment; `SECRET_KEY` and the FastAPI service-token secret must differ between dev, demo and production.
- Separate DB credentials per service (Django role, `fastapi_user` SELECT/DELETE on `documents`, Celery).
- Rotation procedure documented before go-live (rotation, never history rewrite). Anything ever committed or pasted in chat is treated as compromised.
- No secrets in container images or build args; no secrets in logs.

## 6. Backups and recovery (PROPOSED)

- Scheduled `pg_dump` (or base backup + WAL if RPO needs it) to storage outside the VM disk; encrypted at rest.
- Retention and RPO/RTO: `DECISION REQUIRED`.
- A restore is rehearsed on a throwaway instance before go-live and after each schema change.
- Uploaded documents / MinIO objects and model files are included in scope.
- `CURRENT` practice (dev): manual directory copy `data/postgres.bak-<date>`; this is not a backup strategy.

## 7. Logging and monitoring (PROPOSED)

- Container stdout/stderr to the Docker log driver with size rotation; proxy access logs kept separately.
- No student PII (names, national_id, phone) in application logs; request logging excludes bodies.
- Authentication events (login success/failure, role/permission changes) logged; audit trail design belongs to Phase 2.4.
- Healthchecks and restart policies (`NOT YET IMPLEMENTED`): add for postgres, redis, django, fastapi.
- Alerting/uptime: `DECISION REQUIRED`.

## 8. Operations

- Run migrations as a separate, explicit step (not at every container start) once the production profile exists; `CURRENT` compose runs `migrate` + `collectstatic` on django start.
- Remove `--reload` and bind mounts of source from the production profile; images are built, not mounted.
- Remove dev-only exposures (`--reload` in FastAPI CMD, source volumes).
- Pin and patch base images; rebuild on a schedule.
- Fresh-install order is in `FASTAPI_DB_ROLE.md`.

## 9. Decisions the owner must make (`DECISION REQUIRED`)

| # | Decision | Options / notes |
|---|---|---|
| D1 | Hosting location and **data residency** | **DECIDED 2026-11-01 (OW-1):** Iranian servers (shared) or the school's own server (dedicated). Legal residency rules still with O1. |
| D2 | Domain name and TLS certificates | **DECIDED 2026-11-01 (OW-3):** `.ir` domain; certificate from any ACME CA or a commercial one (§3a) |
| D3 | Audience | Public internet demo vs private/intranet/VPN only. Recommendation: private (VPN or IP allow-list) until Phase 3 exit |
| D4 | Data in the hosted instance | **Synthetic data only** until Phase 3 exit (fixed rule; D4 is only "which synthetic set") |
| D5 | Reverse proxy product | Any (OW-4, provider-agnostic); nginx example in `deploy/nginx/` |
| D6 | Who operates it | Named owner/operator, on-call expectation, patch cadence |
| D7 | Backup RPO/RTO and storage target | See section 6 |
| D8 | Authentication hardening | Rate limit/lockout, MFA for Admin (future), admin URL exposure |
| D9 | R-04 fix timing | Prerequisite for section 2; own L3 proposal |
| D10 | Single school vs multi-school host | Design stays "school key can be added"; do not hard-code one school |

## 10. Next step if approved

1. Owner answers D1–D3 and D5–D7.
2. R-04 proposal (least-privilege roles) and PostgreSQL migration runbook.
3. ADR for the deployment profile (L3), then a `docker-compose.prod.yml` + production settings proposal, `check --deploy` clean, restore rehearsal.
4. Security review per `SECURITY.md` before any hostname goes live.

This file is a draft; it does not authorise changes to compose, settings or infrastructure.
