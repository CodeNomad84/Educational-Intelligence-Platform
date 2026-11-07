# 0036 — Documentation reconciliation (report), 2026-11-07

**Level L1 — docs only, no code behaviour change.** Branch `work/docs-sync`, created from `phase-1/boot-security` (`a48c6a1`). Facts below were derived from code and `git log`, not from other docs; the test counts are cited from a real run.

## 1. What changed and why
| File | Change | Source of truth |
|---|---|---|
| `docs/ROADMAP.md` | P6 table row now marks P6-1/P6-2/P6-3 DONE with commit, decision and report numbers; P7 row marks the adapter (report 0032, decisions 56-59) and P7-5 assistant (report 0034, decisions 61-64) built; P9 row cites report 0035 + decisions 65-67; the Phase 2 test-count sentence now gives the 2026-11-07 numbers | commits `ecddc70`, `c816582`, `10e7f31`, `4f325ec`, `2b12adf`, `a48c6a1`; `DECISIONS_BY_CODE.md` 42, 49, 50-52, 56-59, 61-67 |
| `docs/PROJECT_CHECKLIST.md` | Test-status line updated to the 2026-11-07 run; corridor line 42 no longer lists built items as NOT YET IMPLEMENTED; three explicit P6-1/P6-2/P6-3 bullets added; `advisor_ai` placeholder replaced with the built adapter + `docqa`; a P9 PREPARED bullet added under Deployment; the Phase 3 resume note's next-step replaced with the current one (STOP for owner review) | same commits/decisions; `git log` |
| `docs/changes/0035-p9-exit-REPORT.md` | The dangling "see the addendum below" sentence is fixed (no addendum existed) | the file itself (checked) |
| `django_core/schools/entitlements.py` | Docstring: removes "the Django admin is a known UNGATED surface" — see §2 | `schools/admin.py`, `schools/test_admin_closure.py`, `SECURITY.md` line 58 |
| `docs/CHANGE_GUIDE.md` | `Verified-at` note appended for exactly the docs changed here | this report |

## 2. The Django admin claim (verified in code, then fixed)
The docstring said the Django admin is "a known UNGATED surface". Code contradicts that since C-A (S9, 2026-11-01): `schools/admin.py` sets `admin.site.has_permission = _admin_site_permission` (superuser or PlatformAdmin only) and registers platform tables only; `PlatformUserAdmin.get_queryset` excludes school-only accounts; `schools/test_admin_closure.py` pins it; `SECURITY.md` line 58 records the closure as current. The docstring is corrected (**comment-only**); no runtime behaviour changed. `manage.py test schools` → **Ran 333 tests in 83.101s, OK** (`/tmp/schools_test.log`, 2026-11-07).

## 3. The 0035 addendum
The report ended with "see the addendum below" but no addendum exists in the file or its history. **I chose to fix the sentence (not invent an addendum).** It now reads as `NOT VERIFIED`, stating that no addendum was written and that a fresh-agent review of the P9 batch is not recorded here (the P7/P7-5/P8 batches were reviewed separately: reports 0032, 0034, 0033).

## 4. Test evidence
- Latest full run cited for the counts: `/tmp/tests_run.log`, dated **2026-11-07 13:40**: Django **1565** tests on SQLite (`OK (skipped=11)`) plus `demo_intel` **62** (`OK`). That log's own footer says PostgreSQL / FastAPI / Docker were **not covered** — those stay `NOT VERIFIED` for this run.
- This session: `manage.py test schools` (settings `config.settings.test_sqlite`) → **333 tests, OK** (log `/tmp/schools_test.log`).
- NOT run this session: the full `scripts/run_tests.sh sqlite`/`pg` suites (docs-only change); counts are as cited above, not re-measured.

## 5. Truth labels
- `CURRENT`: P6-1/P6-2/P6-3, the P7 adapter, P7-5 `docqa`, C-A admin closure, the cited SQLite test result.
- `PREPARED` (nothing deployed): P9 (report 0035).
- `NOT VERIFIED`: real LLM provider behaviour; PostgreSQL/FastAPI in the cited run; any fresh-agent review of the P9 batch; real deployment/server/certificates/backup restore.
- `NOT BUILT`: student tutor, RAG over student data, parent/student view of alerts, external class on the Django side.

No real student data; no secret read; nothing pushed.
