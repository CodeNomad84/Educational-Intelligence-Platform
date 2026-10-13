# ADR-0004: School scoping / tenant key
- Status: PROPOSED (revised draft 2026-10-13, Phase 2.0; owner approved introducing a School model on 2026-10-13, **not ACCEPTED**)
- Date: 2026-10-03 (revised 2026-10-13)
- Decider: owner

## Context
The product must serve more than one school eventually, but enterprise multi-tenancy is out of scope. `Student.national_id` is globally unique (D-06); grade/subject/status choices are hard-coded (D-09). Phase 2 needs classes and teacher assignments (ADR-0003), which are school-owned data.

## Decision (proposed)
1. Introduce a `School` entity. Phase 2 runs with **one default School row**; its display name comes from configuration or an admin edit, never from code.
2. School-owned records carry a school key: `SchoolClass.school` is required; `Student.school` is added **nullable** and made required only by a later, separate migration after all rows are populated.
3. Scoping stays **row-level in one database**, enforced through the central helpers in `students/access.py` and the school-owning relation of each query. No schema-per-tenant, no database-per-school, no tenant middleware.
4. `Student.national_id` stays globally unique in Phase 2 (`DEFERRED`: it becomes `(school, national_id)` when a second school exists; a new constraint then needs its own migration and duplicate review).
5. `Student.class_name` (free text) is kept, marked deprecated, until its consumers (forms, seed, `demo_intel`) are migrated; Phase 2.1 does not remove it.
6. **DECISION REQUIRED — primary key type** for the new tables: integer (Django default, consistent with `students.*`) or UUID (as in the untracked scaffold `core.BaseModel`). Recommendation: integer, because it matches the existing tables and avoids installing `core`; UUID adds value only for cross-school data merging and is costly to change later.

## Alternatives considered
Database-per-school or schema-per-tenant: rejected for now (operational cost, no second school). No school key: rejected (retrofit cost across every table). Reusing the untracked `schools` scaffold unchanged: rejected, because its `TeacherAssignment` targets `accounts.User` (an `AUTH_USER_MODEL` swap) and it includes a grade-level model Phase 2 does not need.

## Consequences (security, data, testing, customization)
- Data: new tables plus a data migration that creates the default School and classes from distinct `class_name` values; reversible.
- Security: with one school, "school scope" and "class scope" coincide; tests still assert the school filter so a second school cannot silently leak.
- Testing: every query path needs a scoping test; a two-school fixture test is added in 2.1 even though production has one school.
- Customization: nothing school-specific in code (CLAUDE.md §7); naming, thresholds and branding are configuration.

## Evidence (Stage 0 IDs, files)
D-06, D-09; `django_core/students/models.py`; scaffold `django_core/schools/models.py` (untracked, inspected 2026-10-13).

## Supersedes / superseded by
None.
