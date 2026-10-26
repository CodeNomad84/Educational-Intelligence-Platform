# 0025 — Deterministic rules and derived analytics in the core DB, feeding the existing alerts (CHANGE PROPOSAL, Tier C — nothing is implemented)

Written 2026-10-26 for the owner. Pipeline stages 3-5 of `0021` (analytics, rules, risk event). Level: L2 with Tier C parts (new tables, a system-level read path over student data, a rule lifecycle that creates alerts about children). Synthetic data only. No AI, no ML, no AI-suggested rules (out of scope by your instruction).

## 1. Goal and how it is smaller than the Qalamestan engine
A SchoolAdmin can define a few **deterministic rules** over attendance and grades, simulate them on the school's own history, approve them, and from then on the platform raises ordinary alerts (`risk.services.raise_alert`, `RiskEvent.detected_by='rule_engine'`) that go through the **existing human review and intervention loop** (0022/0023). Staff still decide; nothing is stored as a label or score of a student.
Smaller than Qalamestan on purpose: **4 rule kinds**, one closed catalog of ~8 metrics, one connective per rule (all / any), **no composite score, no levels, no protective factors, no weights tables, no per-student parameters**. A rule either fires for a student on a date or it does not, and says exactly why.

## 2. What exists to reuse (and the duplication rule)
- `demo_intel/rules.py` (thresholds, Persian rule names) and `engine.py` (`_analyze`: windows, absence shift, late count, subject drop, low average, minimum-record guards) run only under demo settings on demo-only models, with 58 tests. They are the **specification** for the maths.
- Core data to read: `students.Attendance` (date, status present/absent/late/sick), `students.Grade` (subject, score, date), `students.Enrollment`. No observation table exists in the core (`behavior` is not installed): behaviour rules are NOT in this slice.
- **One engine:** the new `risk/signals.py` (pure metric functions) and `risk/rules.py` (evaluation) become the single implementation. The demo is **not modified** in this slice and keeps working. The metric functions are ported line for line and pinned by **parity tests** that feed the same synthetic rows to both implementations (the parity test file runs under demo settings, where both exist). A later, optional slice makes `demo_intel` call the core metrics so only one copy remains (question 8).

## 3. Derived analytics (stage 3): `risk/signals.py`, nothing stored
Pure functions over rows the caller passes in; each metric returns a number **and** the count of records it used, or `None` when below the minimum (never a guess):
`absence_rate(window)`, `absence_shift_pp(recent, baseline)`, `late_count(window)`, `absent_days(window)`, `max_consecutive_absences(window)`, `avg_score(window)`, `subject_drop(recent, earlier)` (largest drops, at most N subjects), `grades_count(window)`. Windows are in days relative to the evaluation date; every metric has a `min_records` guard (as in the demo). Aggregated with grouped queries per school (not one query per student).
Visible result in this slice: a **"trend" tile on Student 360** (weekly absence rate for 12 weeks, subject averages by period) for the roles that already read attendance and grades there (SchoolAdmin, Grade Lead; Parent sees nothing new). Class- or grade-level analytics pages are NOT in this slice.

## 4. Rules (stage 4)
### Data model (new tables only; integer pks; `school` PROTECT; never edits applied migrations)
| Model (app `risk`) | Fields |
|---|---|
| `Rule` (one row = one **version**) | school, `code` (stable key per school, e.g. `attendance_shift`), `version`, `kind` (one of the 4 built-ins), `title`, `risk_type` (only academic, attendance, behavioral; **never emotional or family**), `severity`, `connective` (`all`/`any`), `clauses` JSON (list of `{metric, op, threshold, window_days, baseline_days, min_records}` validated against the metric catalog; at most 4 clauses; no free expressions, nothing is executed), `cooldown_days`, `status` (draft, simulated, pending_approval, active, paused, archived), `params_hash` (set at simulation), `created_by`, `approved_by`, `approved_at`, `created_at` |
| `RuleHit` | school, rule, student (PROTECT), alert (FK), `evaluated_on`, `evidence` JSON (metric values and record counts used), unique (rule, student, evaluated_on) |
| `RuleRun` | school, rule (null for a batch), `mode` (simulation / live), `as_of`, `started_at`, `triggered_by` (user or null = scheduled), counts (students evaluated, hits, alerts raised, skipped by cooldown, skipped for insufficient data) |
Constraints: at most one `active` or `paused` version per (school, `code`); `active`/`archived` rows are immutable (clone to edit); `simulated`/`pending_approval` require `params_hash` equal to the current parameters (editing resets to draft). Same pattern as the mission weight lifecycle (`missions/lifecycle.py`).
### The 4 starter rules (seeded as drafts per school by a command, thresholds ported from the demo and labelled "unvalidated first proposal", editable as configuration; no school name or number is in code)
1. `attendance_shift`: absence rate of the last 30 days exceeds the previous 60 days by ≥ 10 percentage points, with ≥ 5 records in each window.
2. `repeated_absence`: ≥ 3 absent days in the last 14 days (or ≥ 2 consecutive), with ≥ 5 records.
3. `low_average`: average score of the last 45 days below 12 (scale max configurable, default 20), with ≥ 3 grades.
4. `grade_drop`: a subject's recent average (45 days) is ≥ 3 below its earlier average (45-120 days), at most 2 subjects, with ≥ 2 grades in each window.
Severity per rule (yellow / orange); a rule may combine clauses with `all` or `any` (for example `low_average` AND `grade_drop`).
### Lifecycle (Draft > Simulated > Pending approval > Active > Paused > Archived)
Draft (edit freely) → **Simulated**: run the rule over the school's own history at weekly `as_of` dates for the last N weeks; the result is **aggregate counts** (students who would have fired per week and per grade, groups under 5 withheld, no names, nothing stored except the `RuleRun` counts and `params_hash`) → Pending approval → **Active** (single approver, any SchoolAdmin; optional second approver switch like mission, default off) → **Paused** (SchoolAdmin, immediate, no approval; resume = back to Active) → **Archived**. Activation of a version retires the previous active version of the same code.

## 5. Alerts from rules (stage 5)
`risk/rules.py` evaluates every active rule for the school at `as_of`; for each student who fires and is not inside the rule's cooldown (no open `new`/`accepted` alert of that rule and student within `cooldown_days`), it calls `raise_alert(student, risk_type, severity, message, explanation, detected_by='rule_engine', raised_by=None)` and stores a `RuleHit` with the evidence. The message is a deterministic template ("absence rate 40% in the last 30 days against 15% before, 12 records") built from the evidence, never free text, never a diagnosis. The alert then follows the normal review rules, including the sensitive-text gate (rule alerts can never be of a sensitive type). Triggering: management command `run_rules [--school CODE] [--as-of DATE]` (cron or Celery later; needs `--school` once several schools exist, classified NEEDS_SCHOOL in `schools/test_command_scope.py`) and a "run now" button for the SchoolAdmin (own school only). Nothing runs automatically in this slice.

## 6. Who may do what
| Role | Rules |
|---|---|
| SchoolAdmin (own schools) | create, edit drafts, simulate, request approval, approve, pause, archive, run now; sees all rule versions and `RuleRun` counts |
| Grade Lead, Teacher, Counselor | no rules page; they see the **alerts** a rule raised (normal visibility) and, on the alert, "raised by rule `code` v2" and its evidence numbers |
| Parent, Student, superuser, PlatformAdmin | nothing |
Module gate: **base** (no `module=`); a test proves the routes work with zero `SchoolModule` rows.

## 7. `students/access.py` integration (Tier C)
- `visible_rules(user)`: SchoolAdmin of the rule's school, fail closed; everybody else `.none()`.
- A new, explicit **system read path** for the runner: `system_scope_students(school)` (all students of ONE school, by school id, never "all") and the attendance/grade querysets through it. It is the only place that reads student data without a user; it is imported only by `risk/rules.py` (guard test), requires an explicit school, and is audit-logged as a system run (`rule_run`, user `system`). This is the one genuinely new access concept and the main review target.
- Alerts, hits and evidence go through the existing `visible_alerts` rules; `RuleHit` is read only through the alert it belongs to.

## 8. Audit (ids and counts only)
`rule_create`, `rule_edit`, `rule_status` (detail = new status), `rule_simulate` (counts), `rule_run` (counts; actor `system` when scheduled), and the existing `alert_raise` (detail = rule code). `audit.record` gains a `system` actor (user None, username `system`) — today it accepts only a user.

## 9. Retention, migration risk, performance
- Retention: no period decided (waits for the legal policy); hits and runs are kept with their alerts; nothing is deleted automatically. A rule hit is as sensitive as the alert it created.
- Migration: `risk.0002` creates three new tables only (no change to existing tables); dependencies on the latest `students`/`schools`; guards as for 0022 (`makemigrations --check`, fresh-migrate guard, plan order unchanged, test that the migration only creates tables).
- Performance: grouped queries per school (attendance counts and grade averages by student and window), indexes on (enrollment, date) already exist; target: a school of 1,000 students evaluates all active rules in seconds; a test with a few thousand synthetic rows asserts a bounded query count.

## 10. Test and mutation plan (SQLite and PostgreSQL)
Metric unit tests (windows, minimum-record guards, `None` below minimum); **parity tests** against the demo maths (same rows, same numbers); clause validation (unknown metric, operator, too many clauses, scale, risk type `emotional` refused); lifecycle (every legal and illegal move; edit after simulation resets; one active per code; immutability; single approver; pause/resume); simulation writes no alert, no hit, hides groups under 5; runner (cooldown, dedupe, insufficient data skipped, `raised_by` null, `detected_by='rule_engine'`, evidence stored, idempotent per day); two-school isolation (a run for school A never reads or alerts school B; wrong `--school` refused); role matrix for the rules pages; zero-module-rows works; alert from a rule follows the review/visibility tests; Student 360 trend tile scoped; audit has codes only; command-scope guard classifies `run_rules`; guard that `system_scope_students` is imported only by the runner. Mutations (each must fail a test): runner without the school filter; cooldown ignored; minimum-record guard removed; window off by one; simulation that writes alerts; `emotional` accepted as rule risk type; activation without a matching `params_hash`; non-SchoolAdmin can approve; edit of an active version allowed.

## 11. Deliberately NOT in this slice
AI-suggested rules or any LLM; ML; a composite risk score, HIGH/MEDIUM/LOW levels or protective factors (the demo's scoring is not ported: question 4); behaviour/observation rules (no core table); rules on mission, exam or counseling data; per-student or per-class thresholds; notifications of any kind; scheduling infrastructure (Celery beat) — the command is cron-ready only; class/grade analytics pages; export; parent view; automatic activation; changing the demo engine.

## 12. Effort
Five commits: (1) `signals.py`, models, migration, parity tests; (2) rule validation, lifecycle, simulation, SchoolAdmin pages; (3) runner + command + `system_scope_students` + alerts + audit system actor; (4) Student 360 trend tile, seed command for the 4 drafts, demo seed hook, manuals, docs; (5) security review fixes. Roughly 110-140 new tests, 4-5 working sessions, then `/security-review` (Medium or higher stops for your decision).

## 13. Open questions for you
1. Rules are authored by the SchoolAdmin only (Grade Lead can see but not edit). Agreed?
2. Single approver (as mission) or the optional second approver, default off?
3. Starter thresholds are the demo's unvalidated assumptions (grade scale 0-20). Who validates them with teachers, and when (before or after a pilot)?
4. No composite score or levels (each rule stands alone). Do you want the demo's "level" idea at all, or is "which rules fired" enough?
5. Cooldown default (proposed 14 days per rule and student), and may a rule re-fire while its earlier alert is only `accepted`?
6. Rule risk types limited to academic / attendance / behavioral (never emotional or family). Agreed?
7. Triggering: command + "run now" button only, scheduling later. Agreed, or should a scheduled run be in this slice?
8. Converge the demo onto the core metrics later (one copy), or keep the demo frozen?
9. Should Grade Lead and Counselor see the rule evidence numbers on the alert (proposed yes: they are attendance and grade figures they can already read), or only the message?
10. Retention for hits and runs (waits for the legal policy; same as alerts).
