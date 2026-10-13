# FASTAPI DATABASE ROLE — SETUP, VERIFICATION, ROLLBACK (Phase 1)

**Status:** CURRENT (Phase 1). The role is created **by hand**, not by a Django migration (automation is DECISION REQUIRED, Phase 2).
**Why this file is `.md`:** `.gitignore` ignores `*.sql`; keeping the SQL inside Markdown keeps it in the repository.
**No secrets belong in this file.** The role password is set interactively and stored only in the gitignored `.env.fastapi`.

## 1. Facts this procedure is based on
| Item | Value | Source |
|---|---|---|
| Database | `school_db` | `docker-compose.yml` (`POSTGRES_DB`), `fastapi_core/rag_service.py` (`DB_NAME`) |
| Schema / table | `public.documents` | `students` migration `0007_rag_documents_table`; `rag_service.py` |
| Admin role (owner, superuser) | `school_user` | `docker-compose.yml` (`POSTGRES_USER`); also Django's role |
| Service role | `fastapi_user` | `.env.fastapi` → `DB_USER` |
| Host / port (inside Compose) | `postgres:5432` (not published to the host) | `docker-compose.yml` |
| Service code connects with | `DB_USER` / `DB_PASSWORD` from its environment (`.env.fastapi`) | `rag_service.get_db_connection()` |

**SQL the Phase 1 FastAPI service can execute** (`fastapi_core/rag_service.py`), and what each needs:
| Statement | Reachable in Phase 1? | Privilege |
|---|---|---|
| `SELECT to_regclass('public.documents') IS NOT NULL` (startup) | yes | none (catalog function) |
| pgvector `register_vector` type lookup on connect | yes | none (catalog) |
| list query: `SELECT … FROM documents … GROUP BY parent_id` | yes (`GET /documents/list/`, Admin) | `SELECT` on `documents` |
| `DELETE FROM documents WHERE id = …` / `WHERE parent_id = …` | yes (Admin) | `DELETE` and `SELECT` (the `WHERE` reads columns) |
| `INSERT INTO documents …` | **no** — routes disabled (`disabled_in_phase1`) | not granted |
| similarity `SELECT … embedding <=> …` | **no** — search/chat disabled | covered by `SELECT` if re-enabled |

Nothing the service runs needs `INSERT`, `UPDATE`, `TRUNCATE`, sequence access, schema `CREATE`, or any Django table.

## 2. Order on a fresh installation (the role does not exist yet)
1. `docker compose up -d postgres` — initializes `school_db` and the admin role `school_user` from the Compose environment.
2. Run the Django migrations (`docker compose up -d django`, or `docker compose exec django python manage.py migrate`). This creates `public.documents` and the `vector` extension (`students/0007`).
3. Run **section 3** (pre-checks) and **section 4** (setup) **as the PostgreSQL administrative role `school_user`**.
4. Set the password (**section 5**) and write `.env.fastapi` (**section 6**).
5. `docker compose up -d fastapi`, then run **section 7** (verification).

Commands marked **[ADMIN]** are run as `school_user` through the container's local socket. Commands marked **[SERVICE]** exercise `fastapi_user` (through `SET ROLE` or through the FastAPI container); they never need the admin password.

## 3. Pre-checks [ADMIN] (read-only)
```bash
docker compose exec -T postgres psql -U school_user -d school_db -At -c "
  select 'database: ' || current_database();
  select 'documents table: ' || (to_regclass('public.documents') is not null);
  select 'pgvector: ' || coalesce((select extversion from pg_extension where extname='vector'),'MISSING');
  select 'role exists: ' || exists(select 1 from pg_roles where rolname='fastapi_user');
  select 'server: ' || current_setting('server_version');"
```
Continue only if `documents table: true` and `pgvector` is not `MISSING`. The setup script below also aborts when the table is missing.

## 4. Setup [ADMIN] — idempotent, non-destructive
Safe to run on a fresh database and to re-run on an existing one. It never drops or alters data, only privileges of `fastapi_user`. Edit the two `\set` lines only if the database or role name differs.

<!-- sql:setup -->
```sql
\set ON_ERROR_STOP on
\set role fastapi_user
\set dbname school_db

-- Abort unless Django migrations have created the table.
SELECT to_regclass('public.documents') IS NOT NULL AS documents_exist \gset
\if :documents_exist
\else
  \echo 'ABORT: public.documents is missing. Run the Django migrations first.'
  \quit
\endif

BEGIN;

-- Create the role only if it does not exist yet (no password here; see section 5).
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT', :'role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') \gexec

-- Re-assert the attributes in case the role pre-existed with different ones.
ALTER ROLE :"role" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

-- Converge: drop any table/sequence privileges this role holds in `public`, then grant the minimum.
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM :"role";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"role";

GRANT CONNECT ON DATABASE :"dbname" TO :"role";
GRANT USAGE   ON SCHEMA public      TO :"role";
GRANT SELECT, DELETE ON TABLE public.documents TO :"role";

COMMIT;
```
Run it with:
```bash
docker compose exec -T postgres psql -U school_user -d school_db < fastapi_role_setup.sql   # save the block above to a local file first
```

**Not granted, deliberately:** superuser, `CREATEDB`/`CREATEROLE`, ownership of the database or any table, `CREATE` on schema `public`, `INSERT`/`UPDATE`/`TRUNCATE`/`REFERENCES`/`TRIGGER` on `documents`, any privilege on `documents_id_seq` or on a Django table, and role membership.

**When ingestion or search is re-enabled later** (a reviewed change, not now): add `INSERT` on `public.documents` and `USAGE` on `public.documents_id_seq`, and update this file.

## 5. Set the password [ADMIN] — interactive, nothing echoed or logged
```bash
docker compose exec postgres psql -U school_user -d school_db     # note: no -T, a TTY is required
```
then, at the `school_db=#` prompt:
```
\password fastapi_user
```
`\password` prompts twice, hashes client-side and never echoes the value or writes it to the shell history. Generate a long random value locally (for example `python3 -c "import secrets; print(secrets.token_urlsafe(36))"`) and use only URL-safe characters.

## 6. Configure the service
Create `.env.fastapi` in the project root (gitignored by `.env.*`, mode 600) containing exactly:
```
DB_USER=fastapi_user
DB_PASSWORD=<the value you set in section 5>
```
`docker-compose.yml` loads it into the `fastapi` service only. The remaining connection settings (`DB_NAME`, `DB_HOST`, `DB_PORT`) come from the `environment:` block there. FastAPI must not use `school_user`.

## 7. Verification
### 7.1 [ADMIN] attributes and grants (read-only)
```bash
docker compose exec -T postgres psql -U school_user -d school_db -At -c "
  select 'attrs: super=' || rolsuper || ' createdb=' || rolcreatedb || ' createrole=' || rolcreaterole
         || ' repl=' || rolreplication || ' bypassrls=' || rolbypassrls || ' login=' || rolcanlogin
  from pg_roles where rolname='fastapi_user';
  select 'table grants: ' || coalesce(string_agg(table_name || '=' || privs, '; '), 'none') from (
    select table_name, string_agg(privilege_type, ',' order by privilege_type) privs
    from information_schema.role_table_grants where grantee='fastapi_user' group by 1) g;
  select 'schema CREATE: ' || has_schema_privilege('fastapi_user','public','CREATE');
  select 'database CREATE: ' || has_database_privilege('fastapi_user','school_db','CREATE');
  select 'sequence USAGE: ' || has_sequence_privilege('fastapi_user','public.documents_id_seq','USAGE');
  select 'member of roles: ' || count(*) from pg_auth_members m join pg_roles r on r.oid=m.member where r.rolname='fastapi_user';"
```
Expected: `super=false createdb=false createrole=false repl=false bypassrls=false login=true`; `table grants: documents=DELETE,SELECT`; `schema CREATE: false`; `database CREATE: false`; `sequence USAGE: false`; `member of roles: 0`.

### 7.2 [SERVICE] permitted and denied operations (transactional, rolled back, no data touched)
Runs as the admin but switches to the service role with `SET LOCAL ROLE`, so no password is needed. Every statement is attempted inside its own block; the whole transaction is rolled back.

<!-- sql:verify -->
```sql
BEGIN;
SET LOCAL ROLE :"role";
DO $$
DECLARE stmt text; bad int := 0;
  allowed text[] := ARRAY[
    'SELECT to_regclass(''public.documents'') IS NOT NULL',
    'SELECT count(*) FROM documents',
    'SELECT title, content, metadata FROM documents ORDER BY id LIMIT 1',
    'DELETE FROM documents WHERE id = -1',
    'DELETE FROM documents WHERE parent_id = ''__verify__'''];
  denied text[] := ARRAY[
    'INSERT INTO documents (title) VALUES (''x'')',
    'UPDATE documents SET title = ''x'' WHERE id = -1',
    'TRUNCATE documents',
    'DROP TABLE documents',
    'CREATE TABLE public.verify_probe (a int)',
    'SELECT 1 FROM students_student LIMIT 1',
    'SELECT 1 FROM auth_user LIMIT 1',
    'SELECT 1 FROM django_session LIMIT 1',
    'SELECT 1 FROM django_migrations LIMIT 1',
    'SELECT nextval(''documents_id_seq'')'];
BEGIN
  RAISE NOTICE 'effective role: %', current_user;
  FOREACH stmt IN ARRAY allowed LOOP
    BEGIN EXECUTE stmt; RAISE NOTICE 'allowed ok  : %', left(stmt, 60);
    EXCEPTION WHEN OTHERS THEN bad := bad + 1; RAISE NOTICE 'ALLOWED FAILED: % (%)', left(stmt, 60), SQLERRM; END;
  END LOOP;
  FOREACH stmt IN ARRAY denied LOOP
    BEGIN EXECUTE stmt; bad := bad + 1; RAISE NOTICE 'DENIED BUT PERMITTED: %', left(stmt, 60);
    EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE 'denied ok   : %', left(stmt, 60);
              WHEN OTHERS THEN bad := bad + 1; RAISE NOTICE 'UNEXPECTED ERROR: % (%)', left(stmt, 60), SQLERRM; END;
  END LOOP;
  RAISE NOTICE 'RESULT: % problem(s)', bad;
END $$;
ROLLBACK;
```
```bash
docker compose exec -T postgres psql -U school_user -d school_db -v role=fastapi_user < fastapi_role_verify.sql
```
Expected last line: `RESULT: 0 problem(s)`.

### 7.3 [SERVICE] through the real service code
```bash
docker compose exec -T fastapi python - <<'EOF'
import logging; logging.disable(logging.CRITICAL)
import rag_service as r
c = r.get_db_connection(); cur = c.cursor()
cur.execute("select current_user, (select rolsuper from pg_roles where rolname = current_user)")
print("effective role / superuser:", cur.fetchone())      # expect ('fastapi_user', False)
print("documents_table_exists():", r.documents_table_exists())   # expect True
EOF
```
Also confirm the service started cleanly: `docker compose logs --tail=20 fastapi` shows `Table 'documents' found.`

## 8. Rollback (does not delete application data)
Disables the role and removes its privileges. `documents` and every Django table are untouched.

<!-- sql:rollback -->
```sql
\set ON_ERROR_STOP on
\set role fastapi_user
\set dbname school_db
BEGIN;
REVOKE ALL ON TABLE public.documents FROM :"role";
REVOKE USAGE ON SCHEMA public FROM :"role";
REVOKE CONNECT ON DATABASE :"dbname" FROM :"role";
ALTER ROLE :"role" NOLOGIN;
COMMIT;
```
After rollback the role has `NOLOGIN` and no table privileges, so the FastAPI service cannot connect (startup logs `Could not check 'documents' table`; document routes fail); Django is unaffected. (`CONNECT` on the database is also granted to `PUBLIC` by PostgreSQL's default, so it is `NOLOGIN` that blocks the connection.) To go back to the fully set-up state, run section 4 again.

Optional, only if the role must disappear entirely: confirm it owns nothing, then drop it. `DROP ROLE` fails safely if dependencies remain.
```sql
SELECT count(*) AS owned_objects FROM pg_class WHERE relowner = (SELECT oid FROM pg_roles WHERE rolname = 'fastapi_user');
-- only if owned_objects = 0:
DROP ROLE fastapi_user;
```
Do **not** "fix" a FastAPI connection problem by pointing `.env.fastapi` at `school_user`: that restores the superuser access this procedure exists to remove.

## 9. Known limits
- `school_user` (the Django and Celery role) is still a superuser (R-04, deferred).
- The role setup is manual; `\password` needs an interactive terminal. Both are DECISION REQUIRED for automation in Phase 2.
- Row-level security on `documents` is not configured (document-level ACL is NOT VERIFIED and RAG is disabled in Phase 1).
