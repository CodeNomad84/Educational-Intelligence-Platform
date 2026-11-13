# Educational Intelligence Platform

AI-native school platform for monitoring and supporting student growth, built around **Student 360**.

Product name shown in the UI: **سکوی آموزشی-تربیتی آرمان نو** — *Arman-e-No Educational & Upbringing Platform*.
It comes from `PLATFORM_NAME` / `PLATFORM_NAME_EN` in `django_core/config/settings/base.py` (T10); no template
carries it as a literal.
AI is advisory; humans decide.

> **Status: early prototype. Phase 1 fixes the known start-up blockers and contains the critical authorization holes, but PostgreSQL/FastAPI bring-up was last verified on 2026-10-12 and has not been re-run since (deferred verification gate). Must not hold real student data.** See `docs/SECURITY.md` and `docs/audit/STAGE0_BASELINE.md`. Copy `.env.example` to `.env` and set `SERVICE_JWT_SECRET` before running.

## CURRENT (baseline commit `3404a1a` plus Phase 1 changes on branch `phase-1/boot-security`, closed at `4c096de`; both are in this repository's history)
- Django (`django_core/`): students API + server-rendered dashboard
- FastAPI (`fastapi_core/`): RAG chat/documents, prototype risk model
- PostgreSQL (pgvector), Redis, MinIO, Ollama via `docker-compose.yml`

## TARGET
Django core + FastAPI AI layer + PostgreSQL, React + Bootstrap 5 (RTL) frontend migrated incrementally, rules/risk/alert/intervention pipeline, RAG assistants with access control, multi-school configuration. Not yet implemented.

## Local development: two frontends + one Django origin (ADR-0014, 2026-11-13)
`frontend-men/` and `frontend-women/` are presentation apps that talk to the Django API **through their own dev server**,
so the browser sees one origin and the session cookie + CSRF token need no CORS entry:

| App | Dev server | API |
|---|---|---|
| `frontend-men` | `http://localhost:5173` | `/api/*` proxied to `http://127.0.0.1:8000` |
| `frontend-women` | `http://localhost:5174` | `/api/*` proxied to `http://127.0.0.1:8000` |

1. Start Django: `docker compose up django` (or `django_core/.venv/bin/python django_core/manage.py runserver 127.0.0.1:8000`).
2. In each app: `bun install && bun dev`. The API client is `src/lib/api.ts` (`VITE_API_URL` defaults to `/api`,
   `credentials: 'include'`, `X-CSRFToken` from the cookie that `GET /api/auth/csrf/` sets).
3. Cross-origin calls made by hand (without the proxy) need the origin in `CORS_ALLOWED_ORIGINS`; development already lists
   the four loopback origins, production lists none until an operator sets the variable.

Contract: `docs/ARCHITECTURE.md` ("Auth API"), rules: `docs/SECURITY.md`. **Neither app is in the test gate and neither
may hold real student data yet.**

## Documentation
Start with `CLAUDE.md` (AI engineering rules) and `docs/`: ARCHITECTURE, SYSTEM_MAP, MODULE_MAP, CHANGE_GUIDE, SECURITY, TESTING, AI_GOVERNANCE, CUSTOMIZATION, ROADMAP, CHANGE_PROCESS, `adr/`.
