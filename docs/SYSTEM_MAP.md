# SYSTEM MAP

Derived from code at commit `3404a1a` (Verified-at); the commit `3404a1a` is resolvable in this repository's history (verified 2026-10-13); Phase 1 closed at `4c096de`. Phase 1 behavior was re-verified live in Docker Compose on 2026-10-12 (see `PHASE1_FINAL_VERIFICATION.md`). Code wins on disagreement. Start here to find where a feature lives.

## CURRENT (Phase 1: runs in Docker Compose; behavior verified 2026-10-12)
```
Browser ──> Django (django_core)
             ├─ dashboard app: login, student list/detail/create, library, chat, uploads  (server-rendered templates)
             ├─ students app : Student / Grade / Attendance models, DRF API /api/students/, import, features action
             ├─ Celery worker + beat (Redis)         [tasks.py: unused welcome email; no beat schedule — B-11]
             └─ HTTP + service token (role-bearing, 60 s; config/service_auth.py) ──> FastAPI (fastapi_core, :8001, published on 127.0.0.1 only)
                                          ├─ /chat/  ──> [DISABLED for every role in Phase 1] rag_service ──> Ollama (LLM + embeddings; no embedding model pulled)
                                          ├─ /documents/ (list, delete: Admin) ; ingestion + search [DISABLED] ──> `documents` table (pgvector; created by Django migration 0007; FastAPI role `fastapi_user`: SELECT, DELETE)
                                          └─ predict (Admin only; risk model, joblib/torch files)  [prototype — non-discriminating, advisory only]
PostgreSQL (shared by Django and FastAPI — D-03) · Redis · MinIO (present in compose, unpublished; use NOT VERIFIED) · Ollama
```
Risk example today: Grade/Attendance → features (`students` features action) → FastAPI predict → probability shown. No Rule Engine, Alert, Intervention, or Student 360 exists (NOT YET IMPLEMENTED).

## TARGET pipeline
```
Attendance / Assessment / Observation / Behavior
  → Student 360 (derived features + provenance)
  → Rules / Risk engine → Risk event → Alert → Human review
  → Intervention → Follow-up → Outcome → Re-evaluation
```
Boundaries (TARGET): Django owns operational data & authorization; FastAPI is called with authenticated service identity and receives only ACL-filtered, minimal data; React talks to Django APIs only.

## Integration & AI boundaries
- Django→FastAPI: CURRENT interim service token (see ARCHITECTURE); host still hard-coded (B-08). TARGET: ADR-0002 ratification.
- FastAPI→Ollama: CURRENT hard-coded host (A-04). External LLMs: DEFERRED (ADR-0008).
- FastAPI→DB: CURRENT FastAPI connects as the least-privilege role `fastapi_user` (SELECT, DELETE on `documents`; `FASTAPI_DB_ROLE.md`); schema owned by Django (Phase 1). TARGET: ADR-0001.
