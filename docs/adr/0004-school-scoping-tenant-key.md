# ADR-0004: School scoping / tenant key
- Status: ACCEPTED (owner decisions of 2026-10-13, Phase 2.1.0 design review; effective for Phase 2)
- Date: 2026-10-03 (revised 2026-10-13, accepted 2026-10-13)
- Decider: owner

## Context
The product must serve more than one school eventually, but enterprise multi-tenancy is out of scope. `Student.national_id` is globally unique (D-06); grade/subject/status choices are hard-coded (D-09). Phase 2 needs classes and teacher assignments (ADR-0003), which are school-owned data.

## Decision
1. Introduce a tracked app **`schools`** with `School`, `SchoolClass` and `TeacherAssignment`, using **integer primary keys** (Django default, consistent with `students.*`). The untracked scaffold is preserved on branch `archive/scaffold-apps-2026-10-13` before it is rewritten.
2. Phase 2 runs with **one default School row**; its display name comes from configuration (`DEFAULT_SCHOOL_NAME`) or an admin edit, never from code.
3. `SchoolClass.school` is required. `Student.school` is added **nullable** and made required only by a later, separate migration after all rows are populated.
4. **`Student.school_class` is the source of truth** for a student's class. `Student.class_name` becomes a **deprecated, read-only mirror** (set from `school_class.title`); when `school_class` is empty it holds legacy free text. It is not removed in Phase 2.
5. `SchoolClass.is_active` is kept: an inactive class grants no teacher access and is not offered for import or forms.
6. **Import and forms resolve existing active classes only; they never auto-create a class.** Unmatched names are reported and the student stays unassigned.
7. Scoping is **row-level in one database**, enforced through the central helpers in `students/access.py`. No schema-per-tenant, database-per-school or tenant middleware.
8. `Student.national_id` stays globally unique in Phase 2 (`DEFERRED`: becomes `(school, national_id)` when a second school exists).

## Alternatives considered
Database-per-school or schema-per-tenant: rejected for now (operational cost, no second school). No school key: rejected (retrofit cost). Reusing the untracked `schools` scaffold unchanged: rejected, because its `TeacherAssignment` targets `accounts.User` (an `AUTH_USER_MODEL` swap) and it includes a grade-level model Phase 2 does not need. UUID keys: rejected for Phase 2 (cost to change later is accepted; value is cross-school data merging, not needed now).

## Consequences (security, data, testing, customization)
- Data: new tables plus a reversible data migration that creates the default School and one class per distinct non-empty `class_name` (exact match after trimming only; near-duplicates are reported, never merged).
- Security: with one school, school scope and class scope coincide; tests still assert the school filter, including a two-school fixture.
- Customization: nothing school-specific in code (CLAUDE.md §7).

## Evidence (Stage 0 IDs, files)
D-06, D-09; `django_core/students/models.py`; scaffold `schools/models.py` (preserved on the archive branch).

## Supersedes / superseded by
None.
