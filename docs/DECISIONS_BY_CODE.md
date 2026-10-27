# Decisions taken by Claude Code in "Phase 2 autonomous" mode

Mode: CLAUDE.md §6a-bis (owner decision 2026-10-27, temporary). One entry per decision that would otherwise have been asked to the owner.
Format: date · slice · decision · reason · alternative · how to reverse.

| # | Date | Slice | Decision | Reason | Alternative | How to reverse |
|---|------|-------|----------|--------|-------------|----------------|
| 1 | 2026-10-27 | Counselor-note audit | New action `counselor_note_view`, detail `n<count>`, written only when note text is rendered; object = the Student on the 360 page, the Referral on the counselor case page. | Closes the audit gap without touching who can read notes; counts only keeps content out of the log. | One event per note (noisier, same information). | Remove the two `audit.record(... COUNSELOR_NOTE_VIEW ...)` calls and the constant; old rows stay (append-only). |
| 2 | 2026-10-27 | Rules 0025 c1 | Per-school knobs (grade scale max, breaker %, second-approver switch) live in a NEW table `risk.RuleSettings`, not as columns on `School`. | 0025 forbids changes to existing tables; the migration stays tables-only. | Columns on `schools.School` (schema change of an existing table, Tier C). | Move the three fields to School in a later migration and drop the table. |
| 3 | 2026-10-27 | Rules 0025 c1 | `baseline_days` means the LENGTH of the window immediately before the recent one, for attendance and grades (demo: 30/60 attendance, 45/75 grades = demo's 120-day offset). Starter rules use these values. | One consistent meaning; numbers are identical to the demo (parity test). | Offset-from-today semantics (differs per metric). | Change `signals._window` calls and the starter clauses. |
| 4 | 2026-10-27 | Rules 0025 c1 | Rule severity limited to yellow/orange (DB choices); `RuleRun` has one row per rule per run (simulation or live) with a `status` (ok / breaker_tripped / no_scale). | Matches proposal severities; per-rule rows are what the breaker and the quality page need. | A batch row plus per-rule rows. | Add a nullable-rule batch row in a later migration. |
