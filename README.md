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

## Documentation
Start with `CLAUDE.md` (AI engineering rules) and `docs/`: ARCHITECTURE, SYSTEM_MAP, MODULE_MAP, CHANGE_GUIDE, SECURITY, TESTING, AI_GOVERNANCE, CUSTOMIZATION, ROADMAP, CHANGE_PROCESS, `adr/`.
