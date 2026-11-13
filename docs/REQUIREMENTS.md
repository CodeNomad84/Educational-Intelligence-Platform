# REQUIREMENTS

**Status: SKELETON — owner import required.** The full product requirements and ERD exist only outside this repository (owner's materials). They were NOT available during Phase 0 (the Claude Project contains only the CCOS master prompt). Nothing below is invented; it restates product intent already given by the owner.
Authority: intent-level source of truth (REQUIREMENTS > accepted ADR > ARCHITECTURE). Until imported, requirements are `NOT VERIFIED` in-repo.

## Product vision (owner-stated)
AI-native school operating & educational intelligence platform. Central concept: **Student 360** (academic, attendance, behavioral, emotional, social, motivation, responsibility, growth, intervention history).

## Intended flow (TARGET)
Data → Student 360 → Analytics/Trends → Rules → Risk detection → Risk event → Alert → Human review → Intervention → Follow-up → Outcome → Re-evaluation.

## Actors (TARGET)
Admin, Manager (principal/school leadership), Teacher, Mentor, Counselor, Parent, Student. Permissions: see authorization matrix in `SECURITY.md` (many cells `DECISION REQUIRED`).

## Capability areas (TARGET — priority per `ROADMAP.md`)
Authentication/RBAC · Students/Parents/Teachers/Classes · Attendance · Assessments · Observations · Behavior · Family interaction · Student 360 · Rules/Risk/Alerts · Interventions · Data ingestion (CSV/XLSX/PDF/audio/forms/APIs) · RAG + Study/School assistants · Counseling (sensitive) · Reports · Multi-school configuration.

## Import checklist for the owner
- [ ] Functional requirements with IDs (REQ-xxx)
- [ ] ERD / entity definitions
- [ ] Role permission policy (resolves matrix `DECISION REQUIRED` cells)
- [ ] Grading scale (0–20 vs 0–100) and attendance vocabulary (see Stage 0 D-07, D-08)
- [ ] Language policy for UI and docs
