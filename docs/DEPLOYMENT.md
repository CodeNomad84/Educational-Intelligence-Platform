# DEPLOYMENT — DRAFT PROPOSAL

Status: **PROPOSED / DRAFT** (2026-10-15). Nothing here is implemented unless marked `CURRENT`. Created on the owner's instruction (R-03 decision); not an approved design.

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

`NOT YET IMPLEMENTED` (verified by reading `production.py` and `base.py`; no matches for these names):

| Setting | Proposed value | Why |
|---|---|---|
| `ALLOWED_HOSTS` | exact public hostname(s) only, set via env | Host-header validation |
| `CSRF_TRUSTED_ORIGINS` | `https://<domain>` | Required for HTTPS behind a proxy (Django ≥ 4) |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` | Only if the proxy strips and sets the header itself; wrong config lets clients spoof HTTPS |
| `SECURE_SSL_REDIRECT` | `True` (or redirect at the proxy) | No plaintext sessions |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` | Cookies never over HTTP |
| `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE` | `True`, `'Lax'` | Reduce XSS/CSRF impact |
| `SECURE_HSTS_SECONDS` | start 3600, raise after verification; `INCLUDE_SUBDOMAINS` only if all subdomains are HTTPS | HSTS is hard to undo; stage it |
| `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS='DENY'`, referrer policy | on | Standard hardening |
| Admin URL | non-default path and/or proxy IP allow-list | `/admin/` is a high-value target |
| `/test-fastapi/` and `api/token/` | review before exposure | `/test-fastapi/` is an unauthenticated debug route that returns exception text (`config/urls.py`); the JWT token endpoint needs rate limiting |
| Login rate limiting / lockout | `NOT YET IMPLEMENTED` | Needs a decision (proxy rate limit vs app-level) |

`python manage.py check --deploy` must be clean against the production settings; it becomes a deployment gate.

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
| D1 | Hosting location and **data residency** | School premises server, Iranian domestic provider, or foreign cloud. Residency/legal requirements for student data apply once real data is allowed. |
| D2 | Domain name and TLS certificates | Owned domain; ACME (Let's Encrypt) vs organisational CA; internal-only name for an intranet deployment |
| D3 | Audience | Public internet demo vs private/intranet/VPN only. Recommendation: private (VPN or IP allow-list) until Phase 3 exit |
| D4 | Data in the hosted instance | **Synthetic data only** until Phase 3 exit (fixed rule; D4 is only "which synthetic set") |
| D5 | Reverse proxy product | nginx / Caddy / Traefik |
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
