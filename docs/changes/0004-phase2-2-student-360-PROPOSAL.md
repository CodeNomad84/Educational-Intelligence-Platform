# CHANGE PROPOSAL — Phase 2.2: staff Student 360 read view (REVISED: depends on 2.2a)
Level: **L2** once 2.2a is implemented (reads through the access layer; no new authorization model) · Status: **PROPOSED, BLOCKED by `0003` (2.2a)** · 2026-10-16
Owner decisions applied: D-22-1 = option (b) extended (not built on the flat model); D-22-2 Parent staff-only (Parent keeps the existing detail page); D-22-3 SchoolAdmin sees all sections.
Supersedes the earlier chat proposal of the same phase (single-year page, "all years, all entered by" label).

## 1. What changes versus the first proposal
The page is **not** built until academic years, enrollments and year-aware records exist (2.2a-1..4). Reason: a trend or comparison needs each score attributed to a year, class and grade; today a `Grade` is only a date (see `0003` §2).

## 2. WHAT (after 2.2a)
`GET /students/<id>/360/` (staff roles only), scope via `visible_students`; history rows via the matrix in `0003` §8 and the existing `visible_grades`/`visible_attendances` extended to enrollments. Sections: identity (tier rules), **path** (enrollment per year: class, grade-in-year, status), **academic** (same-year trend and past-year comparison), **attendance** (same), **recommendations** (history, by visibility), **not available yet** (behaviour, emotional, interventions: `NOT YET IMPLEMENTED`, no invented values). No AI prediction, no risk score, no counseling data, no writes, no exports.

## 3. Presentation: same-year trend versus past-year comparison, with provenance
```
Student 360 — <name> · grade 10 · class 10-A · year 1404-1405 (current)
┌ Path ───────────────────────────────────────────────────────────────┐
│ 1402-1403  grade 8  8-B   promoted    source: import batch #12      │
│ 1403-1404  grade 9  9-A   promoted    source: backfill (inferred)   │
│ 1404-1405  grade 10 10-A  active      source: manual                │
└─────────────────────────────────────────────────────────────────────┘
┌ Academic — Math ────────────────────────────────────────────────────┐
│ THIS YEAR (1404-1405)   n=6  avg 14.2   trend ▲ +1.8 (first→last)  │
│ [score by date, current year only]                                  │
│ PAST YEARS              1403-1404 n=8 avg 12.9 · 1402-1403 n=7 avg 13.4 │
│ Same period last year   avg 12.5 (weeks 1–12 of 1403-1404)          │
│ Provenance: Grade rows · enrollment ids · entered by · batches      │
│ Notes: different class/teacher/exams per year; scale not verified;  │
│        "insufficient data" if n < 3; no causal claims               │
└─────────────────────────────────────────────────────────────────────┘
┌ Attendance ─────────────────────────────────────────────────────────┐
│ THIS YEAR rate 0.94 (absent 5, late 3) · LAST YEAR rate 0.97        │
└─────────────────────────────────────────────────────────────────────┘
┌ Earlier recommendations (visible to you) ───────────────────────────┐
│ 1403-1404 · Math · by Teacher X (role snapshot) · status: acted     │
│ text shown only if the author shared it with your role              │
└─────────────────────────────────────────────────────────────────────┘
```
Rules: every block names its source table, row count and latest record date; inferred rows (`source=backfill`) carry a visible badge; a section that the role may not see is omitted, not blanked; empty states say "no data". Same-year trend uses only rows of the open enrollment's year; the comparison aligns by weeks since year start using `AcademicYear.start_date`, and by exam type where present. Averages and trends are labelled derived, advisory and unvalidated, never as risk.

## 4. Tests, risks, review
Per `0003` §10 plus: scope and tier per role, past-year row visibility per matrix, provenance labels and badges present, empty states, no cross-year leakage for a Subject Teacher (own subject only), choke-point guard covers the new view. `/security-review` before release. Risks: derived-number misreading (labelled), free-text history exposure (matrix), grade scale unverified (D-07/D-08).

## 5. Dependencies and order
2.2a-1 → 2.2a-2 (report, owner reviews) → 2.2a-3 (admin creates years, backfill) → 2.2a-4 (access switch, parity) → **2.2 (this page)** → 2.2b grade entry (own class + subject, year-aware) → 2.2c recommendations UI.
