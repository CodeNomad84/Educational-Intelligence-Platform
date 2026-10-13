# ADR-0001: Service boundary and database ownership
- Status: PROPOSED — Phase 1 implemented the Django-owns-schema part (`students/0007`, FastAPI DDL removed); dimension policy and role privileges still DECISION REQUIRED
- Date: 2026-10-03

## Context
Django and FastAPI share one PostgreSQL database; FastAPI creates and may drop a `documents` table outside Django migrations and writes with an unrestricted connection (D-03, D-04, S-08).
## Decision (proposed)
Django owns the schema and all migrations. FastAPI accesses data only through a restricted DB role or via Django APIs; vector tables, if kept in the shared DB, are created by Django migrations.
## Alternatives
(a) FastAPI keeps own schema in a separate DB; (b) FastAPI reads via Django API only; (c) status quo (rejected).
## Consequences
Removes drop-table risk and dual definitions; requires FastAPI refactor (L3). Decision between (a)/(b)/restricted role is `DECISION REQUIRED` at Phase 1.
## Evidence
D-01, D-03, D-04, S-08.
