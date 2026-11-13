# ADR-0002: Service-to-service authentication
- Status: PROPOSED — interim implementation in Phase 1 (HS256 service token with roles, env `SERVICE_JWT_SECRET`); owner ratification DECISION REQUIRED
- Date: 2026-10-03

## Context
FastAPI routes are unauthenticated and port 8001 is published; Django calls carry no JWT (S-02, B-08). A JWT helper exists in `fastapi_core/auth.py` with a default-secret fallback (S-03).
## Decision (proposed)
Every FastAPI route requires authentication; Django calls with a service credential plus the end-user's identity/claims; FastAPI is not published outside the compose network; secrets come only from environment.
## Alternatives
Network-only isolation (insufficient alone); mTLS (heavier, deferred); shared API key (acceptable interim, `DECISION REQUIRED`).
## Consequences
Required for Critical Security Containment; L3. Interim approach is an owner decision before Phase 1.
## Evidence
S-02, S-03, B-08, S-06.
