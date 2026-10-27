# Decisions taken by Claude Code in "Phase 2 autonomous" mode

Mode: CLAUDE.md §6a-bis (owner decision 2026-10-27, temporary). One entry per decision that would otherwise have been asked to the owner.
Format: date · slice · decision · reason · alternative · how to reverse.

| # | Date | Slice | Decision | Reason | Alternative | How to reverse |
|---|------|-------|----------|--------|-------------|----------------|
| 1 | 2026-10-27 | Counselor-note audit | New action `counselor_note_view`, detail `n<count>`, written only when note text is rendered; object = the Student on the 360 page, the Referral on the counselor case page. | Closes the audit gap without touching who can read notes; counts only keeps content out of the log. | One event per note (noisier, same information). | Remove the two `audit.record(... COUNSELOR_NOTE_VIEW ...)` calls and the constant; old rows stay (append-only). |
