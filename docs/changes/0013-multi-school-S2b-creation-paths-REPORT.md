# CHANGE REPORT — Multi-school hosting, stage S2b: every student-creation path assigns a school
Proposal: `0010-multi-school-hosting-PROPOSAL.md` §9 (S2b) · ADR-0012 decision 8 · Level: L3 · Date: 2026-10-22 · Commits (local, **not pushed**): `a29b44b` (resolver), `f1dd456` (API + dashboard form), `82f3ccf` (live import + Django admin), `45f541f` (seed commands), and the docs commit that carries this report · Status: **IMPLEMENTED locally; awaiting owner acceptance.** S6, S3, 2.2-0, 2.2 and 2.4 are NOT started.
Rule that still applies: NO REAL STUDENT DATA until the P3 exit criteria and the 2.4 audit log. Everything below ran on synthetic data.

## WHY
ADR-0012 decision 8: no hidden "the only School" default. Before `Student.school` can become NOT NULL (S6) and the SchoolAdmin read scope can be switched on (S3), no write path may create or edit a student without a decided, authorised school.

## WHAT
One rule, `students/student_school.py: resolve_student_school(user, school_class, target_school_id, existing_school_id)`, used by every path:
1. a class is given → its school (a target that disagrees is an error);
2. else an explicit `target_school`;
3. else an existing student keeps its school;
4. else a non-superuser with exactly ONE active membership → that school (implied);
5. else rejected (zero memberships; several memberships without a target; a superuser without a target: a superuser may name any school but is never defaulted).
The result must be one of the user's schools (`school_ids_for_admin`; superuser: any existing school) and an existing student's school never changes. Errors are `StudentSchoolError` with a stable code and a message that does not distinguish a foreign school from a missing one.

Paths wired (all owner decisions of 2026-10-22 applied):
- **API** (`f1dd456`): `StudentSerializer` has a write-only `target_school`; `validate()` sets `school_id` on create and update. `school` stays read-only.
- **Dashboard form** (`f1dd456`): `StudentForm(user=...)`; `target_school` choices are the user's schools; the add-student template shows the field. `user=None` fails closed.
- **Live import** (`82f3ccf`): optional multipart `target_school`, resolved BEFORE the file is read; the "exactly one School" shortcut is gone; class candidates are the importer's school only; a `national_id` that belongs to a student of ANOTHER school is rejected per row with the fixed text `این کد ملی قابل ثبت نیست.` and nothing is written (`ImportSchoolConflict`); a school-less student is assigned the importer's school (see DECISION REQUIRED below).
- **Django admin** (`82f3ccf`): `StudentAdminForm` with a `target_school` field, bound per request to the acting user and the stored school (`get_form` builds a subclass per request). Tension with ADR-0012 §4 recorded as an open item for S9 in 0010 §7.
- **Seeds** (`45f541f`): `seed_demo --school <code>` (required when several Schools exist; the only School otherwise; unknown code = error); `seed_temporal_*` give every student the synthetic school, except `NoClass0` of `seed_temporal_synthetic`, kept school-less on purpose as the roster-test fixture (documented in the seed; goes with S6).
- **Not creation paths (verified, read-only):** `import_history`, `rollover_academic_year`, `backfill_enrollments` create no `Student` rows.
- **No migration, no change to `visible_*`, permission classes or the token.**

## WHERE
`students/student_school.py` (new), `students/serializers.py`, `students/views.py`, `students/admin.py`, `dashboard/forms.py`, `dashboard/views.py`, `dashboard/templates/dashboard/student_form.html`, `students/management/commands/seed_demo.py`, `seed_temporal_synthetic.py`, `seed_temporal_realistic.py`. Tests: `students/test_student_school.py` (27), `test_student_school_paths.py` (19), `test_student_admin_school.py` (7), `ImportTargetSchoolTests` (6) in `test_import_students.py`, `demo_intel/tests.py: SeedDemoSchoolTests` (3), `students/test_seed_realistic.py: SeedSchoolAssignmentTests` (2); existing fixtures (import, API, form, enrollment-sync tests) gave their SchoolAdmin a membership and four import tests were rewritten deliberately (zero / several-school expectations, mock signature).

## HOW (risks and behaviour changes, stated plainly)
- A SchoolAdmin **without a valid membership can no longer create or edit students** (API, form, admin, import). Run `backfill_school_memberships` first while exactly one School exists.
- A student with no class and no school is no longer creatable without a target (the old behaviour created school-less rows).
- The import no longer links classes "only when exactly one School exists"; it links inside the importer's school.
- Editing a student of a school outside the user's schools is now rejected (400), also before S3.

## EVIDENCE (real results)
| Commit | SQLite (`students dashboard schools`) | `demo_intel` | PostgreSQL 16 |
|---|---|---|---|
| `a29b44b` | 743 OK (8 container-only skipped) | 34 OK | 743 OK |
| `f1dd456` | 762 OK (8) | 34 OK | 762 OK |
| `82f3ccf` | 775 OK (8) | 34 OK | 775 OK |
| `45f541f` | 777 OK (8) | 37 OK | 777 OK |
Each via `scripts/run_tests.sh all`, chained with `&&` before the commit.

**Mutation checks** (copy, mutate, run, restore, sha256 identical, clean tree):
- Resolver (6): drop the allowed check → 5 tests fail (`test_one_membership_and_a_foreign_class_is_rejected`, `…foreign_target…`, `test_superuser_naming_a_missing_school…`, …); drop the school-change check → `test_existing_school_cannot_change_by_target_or_class`; superuser default → `test_superuser_with_a_single_school_is_still_not_defaulted`; drop class/target mismatch → `test_class_and_target_that_disagree_are_rejected`; implied with several → 4 tests; drop the no-school gate → 5 tests.
- API/form (7): no `school_id` → 4 API tests; `existing_school_id=None` → 6 tests (`test_school_of_an_existing_student_cannot_change`, …); form not setting the school → `test_implied_required_and_explicit`; all schools as choices → `test_target_school_choices_are_the_users_schools_only`; view without `user=` → 2 tests; target ignored → 6 tests. **Equivalent mutant (survived):** the form's `existing_school_id` is irrelevant because the add view is create-only.
- Import/admin (8): drop the conflict check → `test_a_national_id_of_another_school_is_rejected_unchanged_and_without_revealing_it`, `test_a_linked_student_of_another_school_is_rejected_too`, `test_a_student_of_another_school_is_not_moved_or_linked`; fixed school `1` → many; no `school_id` written → 7+ tests; admin not setting school → 2; admin user unbound → 5; admin existing school lost → `test_an_existing_students_school_cannot_be_changed`; target ignored → 3. **Equivalent mutant (survived):** class candidates not filtered by school: `resolve_class(school_ids=[school_id])` filters again (defence in depth).
- Seeds (4): no `school=` in `seed_demo` → 2 tests; first-School default → `test_several_schools_need_the_school_option`; synthetic ignoring `in_school` → `test_temporal_synthetic_has_exactly_one_deliberately_school_less_student`, `test_rejections_are_reported_not_guessed`; realistic back to None → `test_temporal_realistic_gives_every_student_a_school`.

## SECURITY REVIEW (`/security-review` per code commit, static read-only reviews, ALL findings; none High; nothing fixed, per the standing rule)
| Commit | Result |
|---|---|
| `a29b44b` | F1 (Low-Medium, 9) `_as_pk` does not catch `OverflowError` (unreachable through the API/form today: DRF `IntegerField` / `ModelChoiceField` reject first). F2 (Medium, 7) the "school cannot change" guard depends on the caller passing `existing_school_id` (both wired callers do). F3 (Medium, 6) the class is trusted as passed; the DB does not enforce `student.school == class.school` (only `Student.save()`). F4 (Low, 6) check order leaks which school a foreign class belongs to (mismatch before not-allowed). F5 (Info) account-state codes. F6 (Low-Medium, 6) TOCTOU between resolving and writing. F7 (Low, 5) public `allowed_school_ids` could be misused as a visibility filter. F8 (Low, 8) lenient integer parsing (floats, `+5`, underscores, Persian digits). F9, F10 (superuser with a class implicitly selects the school: consistent with rule 1), F11 (English messages in a Persian UI). |
| `f1dd456` | F-A (**Medium, 7**) any single-membership admin can adopt any school-less student (see DECISION REQUIRED). F-B (Low-Medium, 5) the update-path race on `school_id` (extends F6). F-C (Low, 6) the F4 oracle is reachable (foreign class + varying `target_school`). F-D (Low, 7) the dashboard template does not render `school_class` errors, so a class/target mismatch is invisible. F-E (Low, 4) class queryset unscoped (S4a), PATCH on a foreign student returns 400 instead of 404 (S3). F-F (Low, 6) bypass writers remain (import before `82f3ccf`, admin, seeds, bulk). Tests mask: no PUT test, dashboard tests assert status only. |
| `82f3ccf` | F1 (**Medium, 7**) per-row TOCTOU: for a not-yet-existing national_id `select_for_update` locks nothing, so a student created by another school between the check and `update_or_create` can be overwritten and moved. F2 (Low-Medium, 8) the conflict row is an existence oracle for national_ids of other schools (inherent in "reject the row"); no throttle or audit. F3 (Low, 7) side channels: `preserved_links`, `class_blank` and `unmatched_classes` (`no_unique_school`) also count conflict rows. F4 (**Medium, 8**) legacy school-less adoption is wider for the import. F5 (Medium-Low, 7) the same in the admin on any edit. F6 (Low, 6) admin class selector unscoped; `SCHOOL_NOT_ALLOWED` attached to `target_school`. F7 (Low, 6) membership not re-checked during a long import. F8 (Low, 7) broad `except` returns `str(e)`; `school_id` rebound in a loop of `_plan_class_links`. F9 (Low, 6) no file/row cap. F10 test gaps (race, side channels, duplicate ids, PlatformAdmin and inactive membership at the wiring level). Out of scope noticed: admin changelist/delete unscoped (S3). |
| `45f541f` | F1 (**Low-Medium, 9; a real ordering defect of this commit**) `seed_demo --reset` deletes the demo data BEFORE `_school()` runs, so with several Schools and no/typo `--school` the command wipes the demo DB and then fails (demo DB only; the guard still runs first). Recommendation: call `_school()` right after `_guard()`, before `_reset()`, plus a test `--reset` + school error leaves the students intact. F2 (Low, 6) `--school ""` falls through to the sole-School auto-pick (use `is not None`). F3 (Info, 7) thin error text (zero Schools; codes not listed). F4 (Low, 4) the demo users get no `SchoolMembership` (matters from S3). F5 (Low, 6, pre-existing) the synthetic seeds' guard is only "Student table empty" + the confirm flag, and `get_or_create(code='synthetic-temporal')` can attach to a real School. F6 (Low, 7) `NoClass0` is school-less on purpose; the S6 marker is prose only (recommendation: a test that fails when it is still created at S6). F7 (Low) the realistic seed no longer produces school-less dirty rows (covered by the synthetic seed only). F8 (Low, 7) test gaps (`--reset` + school error, zero Schools, guard-before-school order). Checked safe: guard first, no write before the transaction in a plain seed, exact code lookup, reset scope unchanged, no secrets in messages. |

## DECISION REQUIRED (owner)
**Adoption of school-less (legacy) students.** Three reviews found the same behaviour: a student with `school IS NULL` is assigned to the acting user's school by an ordinary edit (API/admin, implied single membership), or by an import that contains its national_id, and the school can never change afterwards. Until S3/S6 every SchoolAdmin can reach every student, so in a multi-school host one school can take another's legacy students. Options: (a) accept until S6 (NOT NULL) and keep the hard gate "no second School before S1–S9 are accepted" as the control (current state; the gate already forbids a second School); (b) reject adoption by default: an existing school-less student can only be edited by naming the school explicitly, and the import skips such rows; (c) forbid adoption outside `backfill_student_school`. Recommendation: (a) now, because no second School may exist before S9, plus (c) as part of S6. **Not changed.**

## OPEN ITEMS (recorded, none started)
**To fix first if the owner agrees (small, mine): review F1 of `45f541f`: `seed_demo --reset` runs before the school check.** Review findings above (F1/F4 resolver ordering and type strictness, F-B/F1 write races → S4a conditional update, F3 side channels of the import, F-D template error display, F2 import throttle/row cap/audit). The Django-admin field vs ADR-0012 §4 (S9, recorded in 0010 §7). `NoClass0` school-less fixture (goes with S6).

## OWNER ACCEPTANCE
Pending. Not pushed. S6 and later need their own explicit approval.
