# 0030 — P3 code track, option A (C-B, C-D, C-H, C-K, C-L) — REPORT, 2026-11-01

Written for the owner. Mode: `CLAUDE.md` §6a-bis (Phase 3 autonomous, owner decision 2026-11-01). Synthetic data only. Plan: `0026-p3-exit-plan-NOTE.md` §B; decisions: `0028-p3-p8-decision-pack-PROPOSAL.md`; decision log entries 21-28 in `DECISIONS_BY_CODE.md`.

## 1. What changed
| Slice | Change | Where |
|---|---|---|
| C-B | `create_school <code> <name>`: School row + `school_create` audit event + vocabulary seed in one transaction; the Django-admin add path is audited too | `schools/management/commands/create_school.py`, `schools/admin.py` |
| C-D | Dependency audit with pip-audit; Django-side and FastAPI web-stack upgrades; `torch.load(weights_only=True)`; ML/RAG stack left as CURRENT RISK until P7 | `requirements*.txt`, `fastapi_core/main.py`, report `0029` |
| C-H | Production HTTPS/cookie/HSTS/header settings, console-only logging, project deploy checks (eip.E001-E005, W003, I006) for `check --deploy`, Bootstrap/icons/Chart.js self-hosted (no page loads anything from abroad), generic nginx example, `.ir` HTTPS notes | `config/settings/production.py`, `dashboard/deploy_checks.py`, `dashboard/static/dashboard/vendor/`, `deploy/nginx/eip.conf.example`, `DEPLOYMENT.md` §3/§3a |
| C-K | Encrypted, rotated backups with add-only off-site copy; restore into an empty database only; rehearsal script and CI job | `scripts/backup.sh`, `scripts/restore_backup.sh`, `scripts/test_backup_restore.sh`, `.github/workflows/ci.yml`, `RUNBOOK.md` §3 |
| C-L | `list_view` audit events (counts per school, no row ids) for the student, referral, alert and plan lists and the student API; single API read logged as `view_student_detail` | `schools/audit.py::record_list`, `dashboard/*views.py`, `students/views.py` |

## 2. Evidence
- Gate 1 (C-B + C-D, `scripts/run_tests.sh all` on a snapshot): SQLite 1454 OK (11 skipped) + `demo_intel` 62 OK; PostgreSQL 16: 1454 OK.
- Gate 2 (C-H + C-K + C-L, `scripts/run_tests.sh all` on the working tree before the three commits, 2026-11-01): SQLite 1475 OK (11 skipped) + `demo_intel` 62 OK; PostgreSQL 16: 1475 OK.
- FastAPI: 28 OK from a clean install of the pinned `requirements-test.txt` (Python 3.10).
- Backup rehearsal: all 22 checks pass (refusal without key, encryption, tiers, off-site, rotation, identical restore, refusals of non-empty target and tampered file).
- Mutation checks (each made the tests fail, then reverted): an external `<script>` in a template (eip.E004 test), backup without encryption (rehearsal), student list without `record_list` (3 failures).
- Production check: `check --deploy --fail-level WARNING` with complete values exits 0; with `ALLOWED_HOSTS=localhost`, an `http://` origin and an empty DB password it reports eip.E001/E002/E005 (also an automated test).

## 3. Security review (self-review of the five slices)
No access rule, role, scope or tenancy changed: every new audit call reads the rows the existing `visible_*` functions already return; the API `retrieve` uses the same `get_object` (out-of-scope = 404, tested, no event). New risks considered: the proxy header is trusted by default in production (documented: gunicorn must not be reachable directly; compose binds loopback); backups contain all data (encrypted to an offline key, mode 600/700, plain parts only in a removed work folder, off-site add-only); the vendored assets are byte-identical to the verified npm tarballs. No Medium+ finding.

## 4. Open items (not fixed here)
- **R-04 (blocker before any public server):** the application's PostgreSQL role `school_user` is a superuser (`DEPLOYMENT.md` §4). Needs a least-privilege role and a migration role (L3, own proposal).
- **C-A Django admin closure (Tier C):** waits for your go.
- FastAPI ML/RAG stack advisories (0029 §2); `scaler.joblib` pickle; S-11 untracking.
- Backups on real infrastructure (schedule, off-site target, your key) and a restore rehearsal there: after the server exists.
- HSTS steps and the certificate: at deployment.

## 5. Waiting for the owner
1. Approve or change the decision pack `0028` (especially P3-2 backup policy, P3-5 upload policy, P8-2 "Django pages for the MVP, React SPA deferred").
2. Go / no-go for C-A.
3. Legal, consent and retention (O1), and who operates the servers (P3-1).
