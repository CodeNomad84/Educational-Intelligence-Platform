#!/bin/bash
# R-04 (P9): least-privilege PostgreSQL roles, created ONCE when the data directory is first initialised (the official image runs
# /docker-entrypoint-initdb.d/*.sh as the bootstrap superuser, POSTGRES_USER). After this the application NEVER connects as a superuser:
#
#   school_owner  owns the schema and all tables; used ONLY by the one-shot `migrate` service (DDL). NOSUPERUSER NOCREATEDB NOCREATEROLE.
#   school_app    the runtime role of Django / Celery: SELECT INSERT UPDATE DELETE on tables, USAGE on sequences. No DDL, no TRUNCATE,
#                 no role or extension management. NOSUPERUSER NOCREATEDB NOCREATEROLE.
#
# Needs DB_OWNER_PASSWORD and DB_APP_PASSWORD (environment of the postgres container). The extension `vector` needs a superuser once:
# it is created here, by the bootstrap role. Existing databases: use deploy/postgres-maintenance/r04-convert-existing.sql (NOT in this folder: the image would run it at first start) (docs/DEPLOYMENT.md section 4a).
set -euo pipefail
: "${DB_OWNER_PASSWORD:?DB_OWNER_PASSWORD is required}" "${DB_APP_PASSWORD:?DB_APP_PASSWORD is required}"
[ "${#DB_OWNER_PASSWORD}" -ge 16 ] && [ "${#DB_APP_PASSWORD}" -ge 16 ] || { echo "role passwords must be at least 16 characters" >&2; exit 1; }
[ "$DB_OWNER_PASSWORD" != "$DB_APP_PASSWORD" ] || { echo "owner and app passwords must differ" >&2; exit 1; }
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v owner_pw="$DB_OWNER_PASSWORD" -v app_pw="$DB_APP_PASSWORD" <<'SQL'
SELECT current_database() AS dbname \gset
CREATE ROLE school_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE school_app   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'app_pw';
CREATE EXTENSION IF NOT EXISTS vector;
ALTER DATABASE :"dbname" OWNER TO school_owner;
ALTER SCHEMA public OWNER TO school_owner;
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO school_owner, school_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO school_app;
ALTER DEFAULT PRIVILEGES FOR ROLE school_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO school_app;
ALTER DEFAULT PRIVILEGES FOR ROLE school_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO school_app;
SQL
