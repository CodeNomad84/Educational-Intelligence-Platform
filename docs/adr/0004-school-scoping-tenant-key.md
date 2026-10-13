# ADR-0004: School scoping / tenant key
- Status: PROPOSED
- Date: 2026-10-03

## Context
Product must serve multiple schools eventually, but premature enterprise multi-tenancy is out of scope. `Student.national_id` is globally unique (D-06); config is hard-coded (D-09).
## Decision (proposed)
Introduce a `School` entity and a nullable-then-required school foreign key on school-owned data when the domain model is redesigned (Phase 2–4). Single database, row-level scoping in queries via a central helper; no schema-per-tenant.
## Alternatives
Database-per-school; schema-per-tenant (rejected for now); no key (rejected: retrofit cost).
## Consequences
Uniqueness constraints become school-scoped; every query path needs scoping tests. L3.
## Evidence
D-06, D-09.
