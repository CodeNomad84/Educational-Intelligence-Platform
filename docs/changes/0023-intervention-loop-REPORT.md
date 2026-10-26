# 0023 — Intervention loop: change report and security review (2026-10-26)

Implements `0022-intervention-loop-PROPOSAL.md` on the owner's answers of 2026-10-26. Synthetic data only. Base module (no `module=`).

## What changed
| Commit | Content |
|---|---|
| `9063a1c` | `risk/` and `interventions/` rewritten before their first migration (integer pk, `AUTH_USER_MODEL`, `school` FK, `PROTECT` on student), `0001` migrations (tables only), services, `students/access.py` helpers (`raisable_students`, `plan_students`, `visible_alerts`, `reviewable_alerts`, `visible_plans`, `visible_plan_texts`, `visible_followups`, `may_*`, `valid_plan_owner`), audit actions, API student delete answers 409 when linked rows exist |
| `e8e367e` | alert pages: raise, accept / dismiss with a coded reason (`other` needs a note), reopen (SchoolAdmin), one menu entry per role |
| `63c0715` | plan pages: create (from an accepted alert or directly), start, follow-ups, complete with outcome, cancel, reassign; every plan view audit-logged (`intervention_view`, `text` or `meta`) |
| `b136cca` | Student 360 tile, re-evaluation list and recurrence tag (derived on read), synthetic demo seed, docs (authorization table in `SECURITY.md`, maps, checklist) |
| review fixes | see below |

## Evidence
`scripts/run_tests.sh all` after the review fixes: **1268 tests OK on SQLite (10 skipped as before), 58 `demo_intel` OK, 1268 OK on PostgreSQL.** CI green on `9063a1c`, `e8e367e`, `63c0715`. `makemigrations --check` clean; `schools/test_fresh_migrate.py` green (plan order unchanged); a test pins that the two loop migrations only create tables and indexes/constraints on their own models. About 100 new tests: model constraints, every legal and illegal transition, double review, role × route matrix, two-school leak checks (read and every write), counselor loses access when the referral closes, zero `SchoolModule` rows, emotional text absent from the rendered HTML for SchoolAdmin and a non-owner Grade Lead, audit rows with codes and no text, no export, one menu entry per role, raw-manager guard on the new views, demo seed and `--reset`.

Mutation checks (each made at least one test fail unless noted): `visible_alerts` / `visible_plans` unscoped; counselor ignoring the open-referral condition; review UPDATE ignoring `status='new'`; anyone may edit or cancel a plan; SchoolAdmin or Grade Lead reading emotional text (in `access.py`, as owner grant, and in the view); every view's scoped lookup replaced by the raw manager (alert raise/review/reopen, plan detail/actions/create, Student 360 tile); recurrence window and kind; re-evaluation date test; reviewer note shown to everyone. One equivalent mutant: follow-ups unscoped in `plan_detail` (the template shows them only when the text gate is true, so the second guard is redundant).

## Security review of the slice (diff `9063a1c^..HEAD`)
Checked: object-level scope on every route and service, role gates, CSRF (all state changes are POST with tokens), mass assignment (forms only), XSS (autoescape; `linebreaksbr` escapes), races (review and status moves are single conditional UPDATEs; follow-up under a row lock), audit content, PII in logs, migration safety, the FastAPI database role (explicit grants on `documents` only, so the new tables are unreachable from FastAPI), Django admin (the two apps are deliberately not registered), input edge cases.

| # | Finding | Severity | State |
|---|---|---|---|
| F1 | `GET /students/<id>/plan/new/?alert=abc` raised a 500 (non-numeric alert id) | Low | **Fixed**, regression test |
| F2 | The alerts list showed the reviewer's free-text note to the teacher who raised the alert; the approved rule is status and reason code only | Low-Medium | **Fixed** (note shown only to reviewers), test + mutation |
| F3 | **FIXED (option (a), owner decision 2026-10-26; see below).** Was: **an alert's message is not gated by risk type.** The owner's rule protects the text of `emotional` plans and follow-ups, but a person can put the same sensitive content into the message of an `emotional`/`family` alert, which every SchoolAdmin and Grade Lead in scope can read. The gate can be bypassed by habit, not by a bug | Medium (design gap) | **Fixed** |
| F4 | List pages, the Student 360 tile and the alerts list are not audit-logged (plan pages are). Same open item as the RUNBOOK "audit completeness review" | Info | open |
| F5 | No rate limit on raising alerts | Info | open |
| F6 | `risk/loop_testing.py` (test fixture, imports `dashboard.test_counselor`) lives in the app package | Info | open |
| F7 | Local `.git/info/exclude` hides `django_core/{risk,interventions,behavior,governance,accounts,core}`; the loop apps were added with `git add -f` and new files there need it too | Info | open (checklist) |

**F3 options (owner decides; this changes an access rule, Tier C):** (a) for alerts of type `emotional` or `family`, show the message only to the raiser and a Counselor with an open referral, and metadata (type, status, date) to SchoolAdmin and Grade Lead, exactly like plans (recommended: one rule, one mental model; about one small commit with tests); (b) keep as is and add a visible warning on the form (cheap, relies on people); (c) no free text for those two types, coded severity only. 

## Not done, by instruction
Rule/risk engine (the loop's `raise_alert` is its entry point), AI suggestions, notifications, parent or student view, exam slice 3, questionnaires, LLM work, S8-S10, any change to `Referral`/`CounselorNote` (still `CASCADE`, recorded as an open item).

## F3 fix (option (a), 2026-10-26)
`students/access.py` now holds the text policy beside the plan-text helper: `visible_alert_texts`, `visible_alert_notes` and `apply_alert_text_policy`. For `emotional` and `family` alerts the message and the review note are readable only by the raiser and a Counselor with an OPEN referral; SchoolAdmin and Grade Lead keep metadata. A teacher never reads a reviewer's note. Views call the policy once on what they render and blank the objects in memory, so no template decides access; the plan-create page uses it too. Every display of a sensitive message is audit-logged (`alert_text_view`, risk type only).
**Workflow check (as requested):** accept, dismiss and "create a plan from an accepted alert" all work on metadata alone, and `other` still works (the reviewer writes the required note without being able to read the message, and cannot read it back afterwards: strict reading of the rule). Nothing needed unlocking. Tests (`dashboard/test_loop_alert_text.py`, 8): role × alert type matrix for message and note, rendered pages, two-school isolation, counselor loses access when the referral closes, audit has codes only. Mutations that failed tests: Grade Lead or SchoolAdmin reading the message, SchoolAdmin reading the note, teacher raiser reading the note, SchoolAdmin added to the text gate, the view skipping the policy.
