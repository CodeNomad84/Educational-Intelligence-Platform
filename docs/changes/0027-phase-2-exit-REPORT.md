# 0027 — Phase 2 exit report (autonomous run 2026-10-27 to 2026-10-28)

Status: **owner decisions of 2026-10-28 applied (section 6a); STOPPED before Phase 3.** The Phase 3 start waits for the owner (remove `CLAUDE.md` §6a-bis first). Synthetic data only; nothing pushed to `main`/`Test`; no force-push; no LLM, billing or S8-S10.

## 1. Built in this run (commits on `phase-1/boot-security`, pushed up to `224593b`, CI green)
| Commit | What |
|---|---|
| `a95e299` | `counselor_note_view` audit event (counts only, only when note text is displayed); access unchanged; `CLAUDE.md` §6a-bis (temporary mode, to be removed at Phase 3); `docs/DECISIONS_BY_CODE.md` |
| `29c05ee` | 0025 c1: `risk/signals.py` (8 pure metrics, closed catalog), tables `Rule`, `RuleHit`, `RuleRun`, `RuleSettings` (migration `risk.0002_rules`, tables only), parity tests against the demo maths |
| `86f15a0` | 0025 c2: clause validation, lifecycle (draft > simulated > pending > active > paused > archived), simulation (aggregate counts, groups under 5 withheld), SchoolAdmin pages `/rules/`, the system read path `system_scope_*`; `risk` + `interventions` added to the test gate and CI (they were missing) |
| `f086850` | 0025 c3: runner `run_school`, command `run_rules`, circuit breaker, cooldown, per-student transaction, `system` audit actor, run-now button, run history, quality aggregates, rule label on alerts, real PostgreSQL race test |
| `8709f0a` | 0025 c4: `seed_rules` (4 starter drafts, "first proposal, not validated"), Student 360 trend tile, SECURITY/SYSTEM_MAP/MODULE_MAP/CHANGE_GUIDE/RUNBOOK/TESTING, manuals (school admin, grade lead, counselor, teacher) |
| `224593b` | Review follow-ups: rules pages never write on GET; quality row total hidden when a cell is withheld |
| after `224593b`, uncommitted until this report is committed | checklist updates; this report |

## 2. What exists per pipeline stage (Data > Student 360 > Analytics > Rules > Risk > Alert > Review > Intervention > Follow-up > Outcome > Re-evaluation)
- Data, Student 360, Alert, Review, Intervention, Follow-up, Outcome, Re-evaluation: built before this run (0022/0023), unchanged.
- **Analytics:** `risk/signals.py` + Student 360 trend tile (12 weekly absence rates; subject averages over three 45-day periods), derived from the viewing user's own `visible_*` helpers; nothing stored. CURRENT.
- **Rules:** deterministic, SchoolAdmin-authored, versioned, simulated before approval, single approver (optional second approver, default off). No score, no levels, no ML. CURRENT.
- **Risk event / Alert from rules:** the runner raises ordinary alerts (`detected_by='rule_engine'`, no raiser) with the evidence in the text and a `RuleHit` per alert. CURRENT.
- Not built (by design): scheduler (command + button only), notifications, AI-suggested rules, composite risk score.

## 3. Evidence
- Final local gate `scripts/run_tests.sh all` on the tree at `224593b`: **SQLite 1430 tests OK (11 skipped = PostgreSQL-only) + 62 `demo_intel` OK; PostgreSQL 16 1430 tests OK, 0 skipped** (includes `risk/test_rules_race_postgres.py`, a real concurrent-run race). FastAPI not covered by the script.
- GitHub CI run 40595954280 on `224593b`: `fastapi`, `sqlite`, `postgres` all green.
- Mutation checks (each failed a test): hash check at activation, admin gate, sensitive risk type, frozen live versions, second approver, grade-scale fail-closed, system-scope enrollment filter and school filter, small-group withholding (simulation and quality), circuit breaker, cooldown (new alert, open plan), atomic alert+hit, insufficient-data counting, parity window bound, note-view audit call (both views), GET writes nothing. NOT run as a mutation: removing the unique hit constraint (the test DB is built from migrations; the PostgreSQL race test covers it).
- Slice security review (self-review, no findings >= Medium) and the independent review (section 6).

## 4. Open risks and items for the record
- Independent review findings 1-4: all handled per the owner's decisions of 2026-10-28, see section 6a.
- Rule hits and runs retention: PENDING POLICY (same as alerts).
- Thresholds of the 4 starter rules are unvalidated assumptions from the demo; no school may activate one before its own teachers review them (owner pilot task).
- Closed-referral counselor notes: decided 2026-10-28 and implemented (SchoolAdmin metadata only; Grade Lead unchanged; Counselor none). See section 6a.
- Open info items carried over (checklist): list pages not audit-logged, no rate limit on raising alerts, `risk/loop_testing.py` lives in the app package, local git exclude requires `git add -f` for `risk/` and `interventions/`.

## 5. Skipped because they need an owner/legal/product decision (listed, not built)
- Roadmap 2.6 referral consent states and 2.7 satisfaction feedback (L3; consent, legal review).
- Questionnaires (family/student), retention, external LLM, parent notifications and messaging, billing.
- **The principals' questionnaire task (instruction 3 of the autonomous-mode message): NOT DONE. The "separate, fuller message" with its spec never reached this session. Please resend it.**
- Migration-order fix (touches applied migrations), S7 per-school national id uniqueness, `Referral`/`CounselorNote` CASCADE vs PROTECT (changes applied models).

## 6. Independent full-branch security review (fresh agent, did not write the code; given only the repo, `docs/SECURITY.md`, `students/access.py`, `schools/audit.py`) — RAW FINDINGS, unedited

> # Security review: django_core (branch phase-1/boot-security)
>
> Scope: static, read-only review. I read `docs/SECURITY.md`, `students/access.py` and `schools/audit.py` first. I then went through the dashboard views, `risk/`, `exams/`, `missions/`, `interventions/`, the DRF `StudentViewSet` and serializers, the settings, throttle, bulk-accounts, password-reset and admin modules, and the templates. I did not run the test suite or modify anything.
>
> I found no cross-school (tenant) leak, no injection or XSS, no CSRF gap, and no misuse of the system read path. The four findings are one Medium and three Low, all of them insider or hardening issues (see "Not a finding" below for what I ruled out).
>
> ## Findings
>
> ### 1. Medium. A SchoolAdmin can read the "never for SchoolAdmin" sensitive text by minting or taking over a Counselor account
> - **Category:** privilege escalation / authorization-matrix bypass (insider)
> - **Where:**
>   - `dashboard/password_reset.py:60` (`_ineligible_for_admin`) and `:154` (`admin_reset`)
>   - `dashboard/school_views.py:127` (`staff_list`, `kind=counselors`) with `dashboard/school_forms.py` `StaffAccountForm`
>   - `dashboard/counselor_views.py:47` (`student_refer`)
>   - `students/access.py:349` (`_text_scope`), `:433` (`visible_alert_texts`), `:401` (`may_cancel_or_reassign_plan`)
> - **Description:** `docs/SECURITY.md` says the SchoolAdmin "never" reads the message of an `emotional` or `family` alert, or the text of an `emotional` plan and its follow-ups. That gate only looks at the logged-in user's role. A SchoolAdmin controls everything it needs to become a Counselor:
>   - They can create a Counselor account for their school.
>   - They can refer any student of the school to that Counselor (`student_refer` allows ADMIN). That opens a referral, which `_counselor_q` treats as a grant.
>   - They can reset the password of an existing Counselor, because `_ineligible_for_admin` only excludes self, inactive, staff, superuser and SchoolAdmin/PlatformAdmin accounts.
>   - They can reassign an emotional plan to such a Counselor (`may_cancel_or_reassign_plan` plus `valid_plan_owner`).
> - **Exploit:**
>   1. The SchoolAdmin creates the Counselor `c1` at `/school/counselors/` with a password they chose.
>   2. They refer the target student to `c1` from the Student 360 page.
>   3. They log in as `c1` and open `/alerts/`, `/interventions/<id>/` and `/counselor/case/<id>/`. All `emotional` and `family` alert messages and `emotional` plan texts are displayed, and the counselor notes are readable too.
>   - The only trace is `password_reset`, `staff_account_create` and `referral_create` audit rows, plus `alert_text_view` rows attributed to `c1`. Nothing blocks it.
> - **Fix:**
>   - Exclude Counselor accounts, and any account holding a text-reading grant, from `_ineligible_for_admin`, or require a second actor (platform or another admin) for a Counselor password reset.
>   - Do not let a SchoolAdmin both create a Counselor account and refer students to it without a second approver or at least an alert.
>   - Block reassigning an emotional plan to an account the same admin created or reset within N days.
>   - If the owner accepts this trust model, document it explicitly in `SECURITY.md`. The current text says "never", which is not true end to end.
>
> ### 2. Low. JWT refresh tokens survive a password reset, a forced password change and role changes
> - **Category:** session/authentication
> - **Where:** `config/urls.py` (stock `TokenRefreshView`), `dashboard/password_reset.py:77` (`_do_reset`), `dashboard/throttle.py:99`
> - **Description:** `password_reset.py`'s docstring says "Existing sessions of the account end (the session hash changes)". That holds for the cookie session only.
>   - SimpleJWT 5.4.0 is configured with defaults: no blacklist app, and `TokenRefreshSerializer` checks only `is_active`.
>   - A refresh token minted before a reset keeps minting access tokens for its full lifetime (default 1 day), and each access token works against `/api/students/` with the account's roles.
>   - Setting `must_change_password` does not block this. `ForcePasswordChangeMiddleware` only looks at the session user, and the `must_change_password` check lives only in `ThrottledTokenObtainPairView`.
> - **Exploit:** an attacker holding a stolen parent or student refresh token keeps reading the child's record (national id, `parent_user`, phone for full tier) after the school resets the compromised account, for up to 24 hours.
> - **Fix:** enable `rest_framework_simplejwt.token_blacklist` with `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION`, or set `CHECK_REVOKE_TOKEN: True`. SimpleJWT 5.4.0 ships a `REVOKE_TOKEN_CLAIM` of `hash_password`, so that setting is present and ties tokens to the password hash. Also make the middleware or an API permission refuse `must_change_password` accounts.
>
> ### 3. Low. The student national-id uniqueness error is a cross-school existence oracle
> - **Category:** cross-tenant information disclosure
> - **Where:** `students/models.py:12` (`national_id` is globally `unique=True`), `students/serializers.py` (`StudentSerializer`), `dashboard/forms.py` (`StudentForm`, `ModelForm`)
> - **Description:** the bulk import (`ImportSchoolConflict`) and bulk accounts (`GENERIC`) deliberately hide whether a national id belongs to another school. The standard ModelForm/DRF unique validators do not. They answer "student with this national id already exists" regardless of school.
> - **Exploit:** any SchoolAdmin posts `POST /api/students/` (or the `/students/add/` form) with a guessed 10-digit id. A uniqueness error confirms the child is enrolled in some other school. Ten-digit ids are enumerable.
> - **Fix:** drop the automatic unique validator on `national_id` in the serializer and form, and map a clash to the same generic message the import path uses. Alternatively wait for the planned S7 move to per-school uniqueness.
>
> ### 4. Low. The "second approver" rule for rules is bypassable by editing another admin's draft
> - **Category:** authorization / integrity (insider)
> - **Where:** `risk/lifecycle.py:149` (`approve`) and `:69` (`edit`). The check is `created_by_id == actor.pk`, and `edit` never changes `created_by`.
> - **Description:** with `RuleSettings.require_second_approver` on, only the original creator is barred from approving. Another SchoolAdmin B can open admin A's draft, rewrite the clauses, simulate, submit and approve it. B alone authored the active content and no one else reviewed it. The check should key on the last editor of the parameters, not the original creator.
> - **Impact:** limited to a four-eyes control. Rule risk types are restricted to academic, attendance and behavioral, and the circuit breaker applies.
> - **Fix:** record `last_edited_by` (or `params_author`) on `edit` and `create`, and compare the approver against that field.
>
> ## Not a finding / checked and clean
> - **System read path:**
>   - `system_scope_*` in `students/access.py:468-490` requires one explicit positive int school id, and it ignores user input.
>   - Its only importer is `risk/rules.py` (verified by grep).
>   - The callers get the school only from the admin's membership-derived page school (`_current_school`, validated against `allowed_school_ids`), or from the `run_rules --school` command.
>   - Every `lifecycle` function re-checks `school_ids_for_admin` under `select_for_update`.
>   - The runner writes only alerts, events, hits, runs and audit rows, and rule risk types are validated and DB-constrained (not emotional/family). Rules are data from a closed metric catalog, with no eval or text evaluation.
>   - Simulation and quality pages are SchoolAdmin-only aggregates over that admin's own school, so the withholding of groups under 5 is not bypassable by anyone who is not already entitled to see the rows.
> - **Authorization and tenant isolation:**
>   - Every dashboard, exams, missions, interventions and rules view is `role_required` or `school_page`, with the object looked up inside the user's scope (404, not 403). I found no IDOR.
>   - API `/api/students/`: `get_queryset` is `visible_students`, writes are admin-only, and the serializer's class/parent choices are school-scoped (`OwnSchoolClassField`, `OwnSchoolParentField`).
>   - Counselor-note and sensitive-alert text gates are applied at the queryset level (`apply_alert_text_policy`) and not in templates. Plan text is likewise gated by `visible_plan_texts`.
>   - Audit rows hold ids and codes only. `AuditEvent` is append-only at the model level, and `detail` is capped at 40 characters.
>   - The audit page is scoped to the admin's current school.
> - **Injection / XSS / CSRF:**
>   - No raw SQL, `.extra`, `mark_safe` or `|safe` outside the vendored `.venv`.
>   - The only `cursor()` use is a fixed introspection call.
>   - Chart data is passed with `json_script`.
>   - Login `next` is validated with `url_has_allowed_host_and_scheme`.
>   - Excel output forces string cells (no formula injection). Excel and CSV uploads are size-limited and parsed server-side only.
>   - All POST views have `{% csrf_token %}` or `@require_POST` under the default `CsrfViewMiddleware`. I found no `csrf_exempt`.
> - **Password handling:** generated passwords come from `secrets`, are shown once with `Cache-Control: no-store`, and are not logged or audited. Password reset targets are tightly filtered for Grade Lead. The login, JWT and admin-login throttles do not trust `X-Forwarded-For` by default.
> - **Known and documented, so not re-reported:**
>   - Production settings have no `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS or password validators (S-10).
>   - The document library and FastAPI delete are not school-scoped (Report 0017). `delete_document_view` also interpolates `parent_id` into the FastAPI URL path unquoted, which is admin-only.
>   - Parent receives `parent_user` and `national_id` of own child (C5a-R2).
>   - Third-party scripts load from the jsDelivr CDN without SRI.
>   - `logout_view` accepts GET (logout CSRF, trivial).
>   - The Django admin is a known ungated surface for staff users with model permissions.
>   - The demo scope is loaded only under `config.settings.demo`.

Claude's note on the raw findings (not part of the reviewer's text): finding 1 is classified Medium, so under the stop rules it needs your decision; I did not fix it. Options: (a) accept the insider trust model and correct the word "never" in `SECURITY.md`; (b) block SchoolAdmin password reset of Counselors and require a second actor for Counselor creation + referral; (c) both. Finding 4's fix adds a column to the new `Rule` table (unreleased, no real data) and is cheap; finding 2 is an authentication-configuration change; finding 3 changes validators on the Student create path. I have not verified any of the four findings myself.

## 6a. Status of the independent review findings (after the owner's decisions of 2026-10-28)
| # | Severity | Status | Commit | Evidence |
|---|---|---|---|---|
| 1 | Medium | **Accepted risk with detective controls (option a).** Path demonstrated by test; SECURITY.md wording corrected ("no direct read", not "never"); audit of counselor account creation, role grant, password reset and referral creation verified by test; a Grade Lead can never reset a Counselor or SchoolAdmin (test); residual risk (second actor for sensitive role changes) recorded in the checklist as a possible later hardening | `df740d8` | `dashboard/test_sensitive_role_path.py` (5 tests) |
| 2 | Low | **Fixed.** `SIMPLE_JWT['CHECK_REVOKE_TOKEN']`: tokens are bound to a hash of the password; a token issued before a reset/change is rejected (the old refresh token may still mint an access token, which is rejected). No new table, no migration | `85b2417` | `students/test_token_revocation.py` (3 tests; mutation fails 2) |
| 3 | Low | **Fixed.** One fixed message for a taken national id in the form, the API and the import report, identical for same-school and other-school ids, naming no school (the refusal itself remains until S7) | `4decf4e` | `students/test_national_id_message.py` (5 tests; mutation fails 3) |
| 4 | Low | **Fixed.** New column `Rule.last_edited_by` (migration `risk.0003`); with the switch on the approver must differ from the creator AND the last editor | `75000d0` | `risk/test_rules_lifecycle.py` (3 new tests; mutation fails) |
| - | - | Closed-referral counselor notes (owner decision 3): SchoolAdmin metadata only; Grade Lead unchanged; Counselor sees nothing after close | `d8f7d80` | `dashboard/test_lead_counselor_notes.py` |

## 7. Owner tasks for Phase 3 (from `0026-p3-exit-plan-NOTE.md`, plus this run)
1. (Done 2026-10-28.) Findings and closed-referral notes decided and applied.
2. The principals' questionnaire: spec arrives in the owner's next message (handled after this report).
3. Legal/consent/retention policy (gates 2.6, 2.7, questionnaires, hits/runs retention); hosting and operator; backup policy.
4. Pilot: have the school's own teachers review the starter thresholds before any rule is activated; set the grade scale per school.
5. Remove `CLAUDE.md` §6a-bis at the Phase 3 start.
6. Schedule `run_rules` per school (RUNBOOK §3b) once rules are activated.

## 8. Decision log (every entry of `docs/DECISIONS_BY_CODE.md`)
See the table below (copied from the file at the time of this report).

| # | Date | Slice | Decision | Reason | Alternative | How to reverse |
|---|------|-------|----------|--------|-------------|----------------|
| 1 | 2026-10-27 | Counselor-note audit | New action `counselor_note_view`, detail `n<count>`, written only when note text is rendered; object = the Student on the 360 page, the Referral on the counselor case page. | Closes the audit gap without touching who can read notes; counts only keeps content out of the log. | One event per note (noisier, same information). | Remove the two `audit.record(... COUNSELOR_NOTE_VIEW ...)` calls and the constant; old rows stay (append-only). |
| 2 | 2026-10-27 | Rules 0025 c1 | Per-school knobs (grade scale max, breaker %, second-approver switch) live in a NEW table `risk.RuleSettings`, not as columns on `School`. | 0025 forbids changes to existing tables; the migration stays tables-only. | Columns on `schools.School` (schema change of an existing table, Tier C). | Move the three fields to School in a later migration and drop the table. |
| 3 | 2026-10-27 | Rules 0025 c1 | `baseline_days` means the LENGTH of the window immediately before the recent one, for attendance and grades (demo: 30/60 attendance, 45/75 grades = demo's 120-day offset). Starter rules use these values. | One consistent meaning; numbers are identical to the demo (parity test). | Offset-from-today semantics (differs per metric). | Change `signals._window` calls and the starter clauses. |
| 4 | 2026-10-27 | Rules 0025 c1 | Rule severity limited to yellow/orange (DB choices); `RuleRun` has one row per rule per run (simulation or live) with a `status` (ok / breaker_tripped / no_scale). | Matches proposal severities; per-rule rows are what the breaker and the quality page need. | A batch row plus per-rule rows. | Add a nullable-rule batch row in a later migration. |
| 5 | 2026-10-28 | Rules 0025 c2 | Rule pages live at `/rules/` (own `risk/urls.py`, namespace `rules`), reuse the SchoolAdmin `school_page` decorator (school = validated selection among the admin's memberships) and a "قواعد هشدار" link in the school nav. | Same pattern as the other SchoolAdmin pages; base module, no gate. | Put the views in `dashboard/`. | Move `risk/views.py` and the URL include. |
| 6 | 2026-10-28 | Rules 0025 c2 | Simulation reads through the same system read path as the runner (`risk/rules.py`), not through the admin's `visible_*`; output is counts only (groups under 5 shown as "—", fired total too). | One implementation of evaluation = what you simulate is what runs; the admin only sees aggregates anyway. | Per-user `visible_*` for simulation (different numbers than the runner). | Swap the loader in `rules.load_school`. |
| 7 | 2026-10-28 | Rules 0025 c2 | Rule `code` must match `[a-z0-9][a-z0-9_-]{0,39}`; a code is created once (v1) and new versions only through "clone"; one unfinished version per code. | Stable keys, no path/markup surprises. | Free-form code. | Relax the regex in `lifecycle.create`. |
| 8 | 2026-10-28 | Rules 0025 c2 | Second approver (when the switch is on) = the approver must differ from the rule's author (`created_by`), checked in the lifecycle; the author of a clone is whoever cloned it. | Simplest meaningful four-eyes rule; no extra table. | Track who simulated/submitted too. | Edit `lifecycle.approve`. |
| 9 | 2026-10-28 | Rules 0025 c2 | Added `risk interventions` to the test labels of `scripts/run_tests.sh` (sqlite and pg) and `.github/workflows/ci.yml`. They were missing, so the 0022/0023 loop tests and the new rule tests were not part of the gate (96 tests; all pass). | A gate that skips the module it must protect is worth nothing; tooling change (Tier A). | Leave as is. | Remove the two labels. |
| 10 | 2026-10-28 | Rules 0025 c3 | Cooldown clock = the `evaluated_on` date of the last hit of the same rule CODE (all versions), not the alert's wall-clock `created_at`. | A run with `--as-of` must behave the same as a run on that day; code (not version) so a new version does not reset the cooldown. | Alert `created_at`. | `risk/rules.py::_blocked_by_cooldown`. |
| 11 | 2026-10-28 | Rules 0025 c3 | The "run now" button uses the page's school (`school_page`: validated selection among the admin's memberships; for a one-school admin it is simply that school). The request cannot name another school (tested). | Condition (a) "derive from membership"; multi-school admins already choose a school in the nav. | Refuse the button for multi-school admins. | `risk/views.py::run_now`. |
| 12 | 2026-10-28 | Rules 0025 c3 | Breaker compares `hits * 100 > percent * evaluated` (strictly more than N%). A missing settings row uses the default 15. A rule with only insufficient data never counts as a hit. | Matches "more than 15%". | `>=`. | One line in `_run_rule`. |
| 13 | 2026-10-28 | Rules 0025 c4 | Seeded starters keep their Persian title plus the suffix "(پیشنهاد اولیه، اعتبارسنجی‌نشده)" as the visible label; no schema flag. The admin may rename when editing. The demo seed hook is NOT added (answer 8: demo frozen). | No new column; honest label until a teacher review. | A `validated` boolean (schema change). | `seed_rules.LABEL`. |
| 14 | 2026-10-28 | Rules 0025 c4 | Trend tile = weekly absence rate for 12 weeks (week needs >= 3 records) and subject averages over three 45-day periods, computed from the viewing user's own `visible_attendances/visible_grades`; shown to SchoolAdmin and Grade Lead only. | No new access path; Parent sees nothing new (proposal 3). | System read path for the tile (rejected: would bypass per-user scope). | `dashboard/student360.py`, `risk/trends.py`. |
| 15 | 2026-10-28 | Rules follow-up 1 | `RuleSettings` is no longer created on GET: pages use saved settings or unsaved defaults (15%, no scale, one approver); the row is created when the SchoolAdmin saves. Test: GET writes nothing. | Owner follow-up; GET must be side-effect free. | `get_or_create` on GET. | `risk/views.py::_settings`. |
| 16 | 2026-10-28 | Rules follow-up 2 | Rule-quality: when ANY cell of a row is withheld (under 5, including a zero cell), the row total is hidden as well. Simpler than a documented convention and it closes the subtraction route. Side effect: small schools often see "—" for totals. | Owner chose "the simpler"; code change is three lines and needs no explanation to users. | Keep the total and document it as a display convention. | `risk/quality.py` (`withheld_cell`). |
