# 0030 — Demo-track exit report (P3 code, P5, demo track), 2026-11-02

**Built.** P3 code track: C-A Django admin closure, C-B `create_school`, C-D dependency audit (0029), C-H production hardening, C-K backups, C-L audit completeness. P5: principal dashboard, derived support levels, behavior log (parents see positive only), printable report card. Demo track: Student 360 rework (key signals, attendance bar, year labels, modals), masked national id with audited reveal, self-hosted Jalali picker, disabled "به‌زودی" menu items, fitted chart axes, 390px fixes, P6-1 strategy library, `seed_demo_school` (204 students, `--as-of`), `scripts/reset_demo_school.sh` (not run: it deletes `demo_db.sqlite3`; NOT VERIFIED), `docs/owner/DEMO_SCRIPT.fa.md`.

**Decisions** (log `DECISIONS_BY_CODE.md`): 33-38 (earlier slices), 39 masked id + reveal, 40 Jalali picker, 41 disabled menu items, 42 strategy library, 43 demo seed relative dates.

**Tests / CI.** `scripts/run_tests.sh all` at `6c8bfbb`: SQLite 1489 OK + demo_intel 62 OK; PostgreSQL 1489 OK. Pushed; CI run 41401371210: postgres, fastapi, backup, sqlite all success. Later commits (mobile CSS, seed `--as-of`, review fixes) were verified with affected modules only; the full suite runs before the next push.

**Browser check (screenshots opened).** Jalali picker on the behavior form (1405/08/05 stored 2026-10-27) and the plan form (1405/08/12 and 1405/09/12 stored 2026-11-03 and 2026-12-03). At 390px the Student 360 page was wider than the screen; fixed (`.eip-shell { overflow-x: clip }`, tables wrapped), page width now 390. Dashboard at 390 was already fine. Screenshots: `var/screenshots/p10` (git-ignored).

## Independent security review (fresh agent, read-only, no tests run) — raw findings
No Critical, High or Medium: no STOP.
- **L-1 Low** The REST API `/api/students/` returns the full national id (serializers.py:42, views.py:196-233), unmasked and unaudited, to full-tier users already scoped by `visible_students`. Masking is a UI control only. **Closed 2026-11-02 on owner approval** (decision 44): list masked, detail read audited.
- **L-2 Low** The picker could clear or change an existing date outside its year window, and `sync()` ran on load. **Fixed**: year range widens to the existing value; `sync()` only runs when there is no value.
- **L-3 Low** A duplicate strategy title would raise IntegrityError (500). **Fixed**: `clean_title` per school; `typical_days` 1-365 validated server-side.
- **L-4 Low** `seed_demo_school` had no environment guard. **Fixed**: refuses when non-superuser accounts exist outside DEBUG/DEMO_MODE; password at least 8 chars.
- **L-5 Low** No negative tests for the reveal endpoint. **Added**: GET 405, other school's student 404, other family's child 404, anonymous no access, no audit written on refusal.
- **I-1 Info** Strategy changes are not audited (configuration only). Not changed.
- **I-2 Info** `behavior_new` uses `date.today()` (one-day skew near midnight), accepts any past date. Not changed.
- **I-3 Info** The reveal script ignored error responses. **Fixed** (shows an error text). The inline CSRF token would conflict with a strict CSP if one is added later.
- **I-4 Info** Strategy picker truncates a goal at "·" (cosmetic). Not changed.
Checked and fine (reviewer): reveal view role/object/school scope, require_POST, CSRF, audit without the value, Counselor closed referral 404, other family 404; mask in every template (only the admin edit form and the admin's own upload preview print it); report card scope and audit; modals only built for allowed roles; strategy pages school-scoped, no mass assignment, autoescaped; behavior read/write scope; picker JS has no XSS or network; seed refuses a non-empty student table. Not verified by the reviewer: `SECURITY.md` line-by-line, Django admin exposure of `Strategy`/`BehaviorNote`.

**Owner items.** L-1 (mask or audit the API, or accept and document); S-11 file modes; real-server tasks O1-O9 unchanged.
