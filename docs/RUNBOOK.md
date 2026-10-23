# Owner runbook (one page)

Status: demo and pilot on SYNTHETIC data only. Commands run from the repository root unless noted.

## 1. Run the demo
```
DEMO_PASSWORD='choose-a-password' scripts/start_demo.sh --reseed   # deletes demo_db.sqlite3, migrates, seeds 40 synthetic students
```
Open http://127.0.0.1:8000/login/ . Users (all use that password): `demo_admin` (SchoolAdmin), `demo_gradelead`, `demo_teacher`, `demo_counselor`, `demo_parent`, `demo_student`. Each logs in and lands on its own page (admin `/school/`, grade lead `/grade/`, teacher `/teacher/`, counselor `/counselor/`, parent `/students/`, student `/me/`). Without `--reseed` the script refuses a seed older than one day (`DEMO_ALLOW_STALE=1` overrides). If migrate fails the script prints the fix. The demo only ever touches `django_core/demo_db.sqlite3`.

## 2. Create a school and its administrator (platform superuser)
The superuser is the PLATFORM account: it manages schools and accounts and sees no student data.
1. `cd django_core && python manage.py createsuperuser` (use the normal settings, not the demo ones), then open `/admin/`.
2. *Schools → Add*: name and a unique code.
3. *Users → Add*: the school administrator's username and a strong password; put the user in the group **SchoolAdmin** (not staff, not superuser).
4. *School memberships → Add*: that user + the school. Without a membership the administrator sees nothing.
5. The administrator logs in at `/login/` and lands on `/school/`: academic year → classes → teacher / grade-lead / counselor accounts and assignments → students (add or import) → student and parent accounts. The audit log is at `/school/audit/`.
6. **Bulk accounts (SchoolAdmin, `/school/accounts/`):** download the empty template, fill sheet `Students` (`name, national_id, grade, class`, optional `father_national_id, mother_national_id, father_name, mother_name`) and/or `Teachers` (`name, national_id`, optional `phone`); store national ids as TEXT. Upload → preview (nothing is written; errors listed per row) → confirm. The confirm step downloads `login-sheet.xlsx` with a random initial password per account (username = national id; parent username = father's id, else mother's, one parent account for all children). Print and hand it out, then delete the file: passwords are shown once and cannot be recovered. Every new user must change the password at first login; every user can change it at `/account/`. At most 150 new accounts per upload (hashing ~0.5 s each: split large files by grade, and run gunicorn with `--timeout 180`). Roles of existing staff (Teacher / GradeLead with grades / Counselor) are set at `/school/staff-roles/`; a SchoolAdmin can not create SchoolAdmins or touch other schools' users.
Do not create a second real school before the open risks below are accepted (rule recorded in `docs/changes/0010`).

## 3. Backup and restore
* Demo: nothing to back up; `--reseed` rebuilds it.
* SQLite development DB: stop the server, copy `django_core/db.sqlite3` (and never commit it).
* PostgreSQL (docker): `docker exec postgres_db pg_dump -U "$POSTGRES_USER" school_db > backup-$(date +%F).sql`; restore into an EMPTY database: `docker exec -i postgres_db psql -U "$POSTGRES_USER" school_db < backup-YYYY-MM-DD.sql`. Store backups outside the VM disk, encrypted. NOT automated and NOT rehearsed: schedule and test a restore before any real data (`docs/DEPLOYMENT.md`).
* **Rehearse it (synthetic demo data only):** `scripts/backup_restore_check.sh` backs up the demo DB (read-only, sha256 checked before/after), restores the SQL dump into a separate EMPTY database, runs `manage.py check` and `migrate --check` on the restored copy, and compares row counts of students, grades, recommendations and audit events (any difference fails). `scripts/backup_restore_check.sh sqlite` runs only the SQLite path; `scripts/backup_restore_check.sh pg` runs only the PostgreSQL path (disposable PostgreSQL 16 container on an internal network, `pg_dump` then `psql` into an empty database; needs Docker and the local images `pgvector/pgvector:pg16` and `eip-test-django:local`, exit 3 if missing). Without an argument it runs SQLite, then PostgreSQL if Docker is available, otherwise it prints "SKIPPED (not verified)". Another SQLite file: `SOURCE_DB=/path/copy.sqlite3 scripts/backup_restore_check.sh sqlite`. It never touches `db.sqlite3`, `data/postgres` or `.env`. Last run: see the change report (`docs/changes/`).
* Before applying any migration to a real database, back it up. Never `--fake` migration `students.0015`.

## 4. What is NOT done
* **No real LLM.** FastAPI chat / RAG / ingestion are disabled (HTTP 403 in Phase 1). The student "study assistant" and the risk views are rule-based demo stubs; no student data leaves Django.
* **No real student data** until you approve it: the audit log exists (`/school/audit/`), but the security exit criteria (`docs/SECURITY.md`) are not signed off.
* Counseling content is never exposed to AI. Recommendations are staff-only unless the teacher marks them visible to the student.

## 5. Open risks (not fixed)
* Django admin is not school-scoped for SchoolAdmins (use the dashboard); only the superuser should use `/admin/`.
* `national_id` is globally unique (one school per person for now); a person in two schools is not supported.
* Passwords: bulk-created accounts are forced to change the generated password at first login (web pages only: `/api/token/` still issues JWTs to a flagged account - NOT FIXED), but there is no lockout / rate limiting, no strength rules beyond length 8 (and not all-digits), no 2FA, and no "reset a user's password" page yet (a lost login sheet means a platform-admin reset in `/admin/`).
* Bulk accounts keep the uploaded rows (names, ids) in the server-side session for up to 30 minutes until confirmed or cancelled; passwords are never stored. The sheet is a plain xlsx (a PDF needs a new dependency and a Persian font: not done).
* The audit log is append-only in the application, not tamper-proof against someone with database access; it is not yet reviewed for completeness (e.g. list pages, exports, Django admin actions).
* Import: the concurrent-write race is handled (conditional write, generic error) but the PostgreSQL thread test is skipped; batch files of the maintenance commands are signed but have no per-row provenance (R-a).
* FastAPI documents are school-scoped by the token; ingestion is disabled, so the scope has not been exercised with real documents.
* The Grade Lead / risk dashboards use simple explainable rules, not validated models; they need human review.
* No CI, no HTTPS / reverse proxy configuration, no scheduled backups, no monitoring.
* Open review items are listed in `docs/changes/0017-multi-school-S3-school-admin-scope-REPORT.md`.
