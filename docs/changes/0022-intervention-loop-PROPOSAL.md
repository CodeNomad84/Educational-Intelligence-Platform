# 0022 — Close the loop: alert > human review > intervention > follow-up > outcome > re-evaluation (CHANGE PROPOSAL, Tier C — nothing is implemented)

Written 2026-10-26 for the owner. Level: L2 with Tier C parts (new tables, `access.py` rules, student-related sensitive records). Synthetic data only. Gap analysis: `0021-mvp-gap-REPORT.md`.

## 1. Goal and smallest slice
One school, staff only: a concern becomes an **alert**; a person **accepts or dismisses** it (dismissal needs a coded reason); acceptance leads to an **intervention** (who, type, plan, due date, status); the owner writes **follow-ups**; closing records an **outcome**; Student 360 shows what was done and when a **re-evaluation** is due. Deterministic, no AI, no notifications, no parent view.

## 2. Reuse versus rewrite (`DECISION REQUIRED`, question 1)
Existing shells: `risk.RiskEvent`, `risk.Alert`, `interventions.InterventionPlan`, `InterventionFollowUp`. They have **no migrations and are not in `INSTALLED_APPS`**, so nothing is applied and nothing in this slice edits an applied migration. They cannot be used as written: FKs to the non-existent `accounts.User`; UUID primary keys (audit `object_id` is 20 characters); no `school` column; `Alert` fans out one row per recipient role with `is_read`, which cannot carry a review decision.
Recommendation: **keep the four model names, their purpose and most field names, and rewrite the files** before their first migration: integer pk, `settings.AUTH_USER_MODEL`, a `school` FK on each, and the review/outcome fields below. No second set of models is created. The demo-only `demo_intel.InterventionRecord` stays untouched (demo settings only).

## 3. Data model (new tables only)
Conventions as `Referral`/`CounselorNote`: `school` is `PROTECT`, `editable=False`, always copied from `student.school`; free text is length-limited; a student's `CASCADE` follows the `Referral` precedent (see question 9).

| Model (app) | Fields |
|---|---|
| `RiskEvent` (`risk`), append-only | school, student, `risk_type` (existing choices), `severity` (existing), `risk_score` nullable (manual events have none), `detected_by` (`rule_engine`, `teacher`, `counselor`, `admin`; `ai_model` not offered), `explanation` required, ≤500, created_at |
| `Alert` (`risk`) | school, student, `risk_event` FK, `raised_by` nullable user, `message` ≤300, `status` new/accepted/dismissed, `reviewed_by`, `reviewed_at`, `dismiss_reason` (code), `review_note` ≤300. Dropped from the shell: `recipient_role`, `is_read`, `alert_type` (type comes from the event). One alert, many eligible reviewers, first review wins |
| `InterventionPlan` (`interventions`) | school, student, `alert` FK null (a plan may also start without an alert), `owner` (responsible staff), `created_by`, `intervention_type` (academic, behavioral, emotional, social), `goal` ≤300, `action_plan` ≤1000, `start_date`, `due_date` (required), `status` planned/active/completed/cancelled, `outcome` (code, empty until close), `outcome_note` ≤500, `closed_at`, `reevaluate_on` date null |
| `InterventionFollowUp` (`interventions`) | plan, author, `followup_date`, `progress_note` ≤1000, `assessment` code on_track / needs_change / blocked. The shell's float `effectiveness_score` is dropped (an unvalidated number invites ranking) |

Codes: dismiss reasons `not_relevant`, `already_handled`, `duplicate`, `data_error`, `other`; outcomes `improved`, `no_change`, `worse`, `not_assessable`. Both lists are configuration (a constant per code, Persian labels), not school-specific logic. Nothing is a stored label of the student: alerts and plans are records of what staff did.

## 4. State machines (illegal transitions raise and are tested)
- **Alert:** `new` → `accepted` | `dismissed`; `dismissed` → `new` only by SchoolAdmin ("reopen", audit-logged). A review is one conditional UPDATE (`status='new'` in the WHERE) so two reviewers cannot both win. `accepted` is final; its plan carries the work.
- **Plan:** `planned` → `active` → `completed`; `planned`/`active` → `cancelled`. Completing requires an outcome code and sets `closed_at`; `reevaluate_on` defaults to closing date + 30 days (editable). Completed/cancelled plans are read-only (add a new plan instead). The shell's `in_progress`, `evaluating` and `failed` are dropped: `active` covers in progress, `outcome=worse|no_change` replaces failed (Tier B, reversible before first migration).
- **Follow-up:** append-only (no edit, no delete); only while the plan is `active`.

## 5. Who may see and act (normative once approved)
| Role | Alerts | Plans and follow-ups |
|---|---|---|
| Subject Teacher | **raise** one for a student of an own class (message only); sees only alerts they raised and their status/reason code | none |
| Grade Lead | review alerts of own grade; raise | create/own/edit plans for own-grade students; follow-ups; sees plan type, status, dates, outcome code of counseling-tier plans, not their text |
| SchoolAdmin | all alerts of own school(s): review, reopen, raise | all plans of own school(s): create, reassign owner, cancel, add follow-ups |
| Counselor | alerts of students with an OPEN referral to them: review, raise | plans they own for referred students; text of `emotional` plans readable only by the owner counselor and the SchoolAdmin; **closing the referral ends access** (as for notes) |
| Parent, Student | none (404) | none (404) |
| Superuser/PlatformAdmin | none (platform account holds no school data) | none |

Out of scope or wrong school: 404; wrong role: 403 (as elsewhere). Owners must themselves see the student (checked on assignment).

## 6. `students/access.py` integration (Tier C: new access rules)
Add `visible_alerts(user)`, `visible_plans(user)`, `visible_followups(user)` built from the existing building blocks (`_school_admin_q`, `_grade_lead_q`, `_counselor_q`, `visible_students`), each ending in the school/role scope exactly as `visible_referrals` does; Teacher branch = `raised_by=user` AND still sees the student. Field policy for the counseling-tier text is a helper beside `full_tier`. Every view queries only through these helpers. The "no raw `Student.objects`" choke-point guard test is extended to the new apps. Mutation checks are mandatory (see §10).

## 7. Audit (ids and counts only, never text)
New fixed actions in `schools/audit.py`: `alert_raise`, `alert_review` (detail `accepted` | `dismissed:<code>`), `alert_reopen`, `intervention_create`, `intervention_status` (detail new status), `intervention_outcome` (detail outcome code), `followup_add`, `intervention_view`. Student 360 views stay under `view_student_360`.

## 8. Student 360 and re-evaluation hook (derived on read, nothing stored)
A tile on Student 360 (full-tier staff only): open alerts, active plans, closed plans with outcome code and date. A "re-evaluation due" list on the alerts page: completed plans whose `reevaluate_on` has passed with no later follow-up or new alert. A new alert of the same `risk_type` within 90 days after a plan closed is tagged "recurred after intervention #N". The effectiveness formula of doc 12 §16.3 is **not** in this slice (needs rules and repeated risk scores).

## 9. Module gate, retention, migration risk
- **Gate:** base, not sellable. No `module=` on routes; a test proves every route works with zero `SchoolModule` rows. School scope still applies everywhere. Document as base in `ARCHITECTURE.md`.
- **Retention:** nothing is deleted in this slice. Doc 12 §19.4 (cited in `core/models.py`) says risk events 3 years; no period is decided for plans/follow-ups. Text is bounded; the audit holds no content. A cleanup command follows once the owner sets the period (question 6). Real data stays blocked by the P3 and legal items in `0021`.
- **Migration risk:** two new apps get `0001` migrations that only create tables, depending only on the latest `students` and `schools` migrations. No applied migration changes; no data changes in other apps; existing databases get empty tables. Rollback: migrate both apps to zero, remove from `INSTALLED_APPS`. Must keep `schools/test_fresh_migrate.py` (migration order guard) green, plus a check that `makemigrations --check` is clean and the migration plan order is unchanged.

## 10. Test plan (all on SQLite and PostgreSQL)
Models and constraints; every legal and illegal transition; double-review race (second review refused); role × route matrix (allowed / 403 / 404) for each view; two-school leak suite in the style of `students/test_cross_school_writes.py` (alert, plan and follow-up of another school: read and every write refused, state unchanged); counselor loses access when the referral closes; teacher sees only own alerts; parent/student get nothing; zero-module-rows works; audit rows exist with codes and no text; no export route; Student 360 tile scoped; guard against raw `Student.objects`; migration tests above. Mutation checks required: drop the school filter in each `visible_*`; drop the open-referral condition; let the review UPDATE ignore `status='new'`; let any staff edit a plan they do not own; let Grade Lead read emotional text. `run_tests.sh all` green before each commit.

## 11. Deliberately NOT in this slice
AI suggestions or summaries; notifications of any kind (mail, SMS, push, badges); parent or student portal; the rule engine (ROADMAP 2.3: the slice has one internal function `raise_alert(...)` that rules will call later; the demo rules in `demo_intel/rules.py` are not ported); effectiveness scoring; export, reports and school-wide aggregates; referral consent states (2.6) and the crisis/escalation policy (D18); reminders; bulk actions; editing history of closed plans.

## 12. Effort
About four commits: (1) apps, models, migrations, access helpers, tests for them; (2) alert raise/review views and menu; (3) plans, follow-ups, outcome; (4) Student 360 tile, re-evaluation list, audit, docs. Roughly 70-90 new tests; 3-4 working sessions, then `/security-review`.

## 13. Open questions for the owner
1. Rewrite the shells as in §2 (recommended), or keep the shell field names exactly even if that means a UUID pk and a custom audit column?
2. Reviewers: SchoolAdmin and Grade Lead, plus the Counselor for referred students; teachers only raise. Agreed?
3. May the Grade Lead read the text of `emotional` plans? Proposed: no (type, status, dates, outcome code only).
4. Source of alerts in this slice: manual only (proposed), or also port two demo rules (attendance shift, low average)?
5. Dismiss reason codes and outcome codes as listed; is a note mandatory for `other`?
6. Retention period for alerts, plans, follow-ups, risk events (3 years in doc 12 for risk events).
7. May an intervention about a real child be recorded before the consent/legal policy exists? Proposed: synthetic data only, as now.
8. May a plan start without an alert (proposed yes, `alert` null)?
9. Student deletion: `CASCADE` (follows `Referral`) or `PROTECT` (history survives)?
10. Re-evaluation default of 30 days after closing; recurrence window 90 days.
