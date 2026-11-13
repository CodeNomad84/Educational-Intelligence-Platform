> SUPERSEDED IN PART (S6-3, Report 0016): the `save()` guard, `is_existing` and the rollover skip described here were removed once the column became NOT NULL (students.0015). The text below is the historical record.

# CHANGE REPORT — Multi-school hosting, stage S6-1: no adoption of school-less students; code and tests ready for NOT NULL
Proposal: `0010-multi-school-hosting-PROPOSAL.md` (S6 row, EXPLICIT CONSTRAINT, S6 REQUIREMENTS) · ADR-0012 · Level: L3 (Tier A continuation approved 2026-10-23: S6-1 only, no migration) · Commits: `b4beb90` (S6-1), `363f484` (review round).
Rule that still applies: NO REAL STUDENT DATA until the P3 exit criteria and the 2.4 audit log. Everything below ran on synthetic data.

## WHY
S6 makes `Student.school` NOT NULL. Before that (1) nothing but `backfill_student_school` may give an existing school-less student a school (owner requirement 1; S2b used to adopt it for the actor), (2) tests and seeds must not need a NULL school, (3) there must be a read-only pre-flight.

## WHAT / WHERE
- `students/student_school.py`: `resolve_student_school(..., is_existing=True)` rejects an existing student without a school (`student_without_school`, after the no-access check). Wired in `serializers.py` (API), `dashboard/forms.py`, `admin.py`.
- `students/views.py` `_write_import_row`: a row for a student whose school differs from the import school, **including NULL**, gets the generic `ImportSchoolConflict`.
- `students/models.py`: `Student.save()` raises `SchoolAssignmentRefused` when an existing row stored without a school would get a school or a class (which derives one). The stored value is the one recorded by `from_db`/`refresh_from_db`/`save`; if unknown (deferred field, `Student(pk=…)` clone, instance created without a school) it is read with one query. Queryset `update()` (the backfill) is untouched.
- `rollover_academic_year`: plan and apply skip `student_without_school` (otherwise the new guard would abort an apply).
- New read-only `check_student_school_ready [--json]` (counts only; exit 1 unless no NULL school and no class/school mismatch; same `plan_assignments` as the backfill).
- `seed_temporal_synthetic`: `NoClass0` has a school (no class). About 20 fixtures/helpers now give an explicit school. Tests that need a NULL row stay and carry the marker `S6-2:retire` (`grep -rn "S6-2:retire" django_core`).

## EVIDENCE (final `scripts/run_tests.sh all`, `&&` chain, exit 0)
SQLite 800 tests OK (8 skipped, container-only) + `demo_intel` 41 OK; PostgreSQL 800 OK, none skipped. New: `test_school_less_students` (negative test over API PATCH ×3 actors ×5 payloads, Django admin, live import, dashboard form, `save()`, deferred/partial-refresh/clone cases, backfill still works), resolver, command, rollover.
Mutation checks (tree restored byte-identical, sha256): resolver check removed → 29 failures (resolver, API, admin, form); import adoption back → masked by the `save()` guard (same outcome, by design), with the guard also off → the import tests fail; `save()` guard off, refresh tracker off, serializer/form/admin without `is_existing`, command ignoring NULL → each fails its named test; fix round: always-record refresh, trusting an unknown value, rollover skip removed → named tests fail. One mutation survives by design: dropping the "record after save" line (only saves a query; the unknown path still guards).
Empirical NOT NULL run on a disposable copy (never committed): before S6-1 240 tests failed (234 in 23 files from 26 creation sites, plus 6 `demo_intel`); after S6-1 only the `S6-2:retire` tests fail (36 at that run, before the review-round tests; backfill 11, multischool checks 7, batch hardening 3, school-less negative tests 10, ready command 3, import adoption 1, migration 0009 1, …); `demo_intel` passes.
Dry run on synthetic copies (scratch SQLite): `seed_temporal_synthetic` 18 students, `seed_temporal_realistic` (scale 0.1) 26 students: `check_student_school_ready` READY (0 NULL, 0 mismatches). A copy with one forced NULL row: NOT READY, exit 1, `backfill_student_school` dry run: unresolved 1 (two Schools). Scratch migration (copy only) AlterField NOT NULL on SQLite: forward and back OK on the synthetic copy; on the copy with a NULL row it fails with `IntegrityError` and rolls back. PostgreSQL migration NOT RUN (S6-2).

## SECURITY REVIEW (`/security-review`, static; all findings)
`b4beb90`: F1 Medium 8 partial refresh re-records a local school — FIXED `363f484`. F2 Medium 9 deferred field disarms guard — FIXED. F3 Medium 8 `Student(pk=…)` clone — FIXED (query); bulk/raw paths (`bulk_create(update_conflicts)`, `bulk_update`, `update()`, `loaddata`, `save_base(raw)`) stay open until S6-2 (NOT NULL) — no such use in repo code. F4 Low 7 instance created without a school — FIXED. F5 Low/Info 6 stale instance (revert race; silent NULL write-back after a backfill) — NOT FIXED, narrow, closes at S6-2. F6 Low 7 rollover apply aborts on a school-less student — FIXED. F7 Info 6 distinct message "This student cannot be edited here." reveals a school-less student to an actor who can already read the row — NOT FIXED. F8 Info 9 PATCH of any field on a school-less student returns 400 under `target_school` — intended. F9 Info 7 import counters (`class_blank`/`unmatched`) skewed for rejected school-less rows — NOT FIXED. F10 Info 8 docstring — FIXED. The fix round (`363f484`) was not reviewed again (one round per commit).

## RISKS / OPEN
- `save()` guard is soft; the hard stop is S6-2 (Tier C, NOT started). S6-2 must also decide the fate of the `S6-2:retire` tests and of `backfill_student_school` (kept until S7).
- NULL-tolerant branches remain until S6-3.
- Before S6-2 on any real database: `check_student_school_ready` must be READY there.
