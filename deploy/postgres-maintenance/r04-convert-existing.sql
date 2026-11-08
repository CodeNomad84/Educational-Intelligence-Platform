-- R-04 (P9): convert an EXISTING database that the application uses as a superuser (school_user) to the two least-privilege roles.
-- Run ONCE, as a superuser, in a maintenance window, AFTER a verified backup (RUNBOOK section 3), against the application database:
--   psql -v ON_ERROR_STOP=1 -U <superuser> -d school_db -v owner_pw="$DB_OWNER_PASSWORD" -v app_pw="$DB_APP_PASSWORD" \
--        -v old_role=school_user -f r04-convert-existing.sql
-- It does not drop the old role (do that yourself after the application has run for a while as the new roles).
-- Rollback: ALTER DATABASE/SCHEMA ... OWNER TO <old_role>; REASSIGN OWNED BY school_owner TO <old_role>; point DB_USER back (not advised).
SELECT current_database() AS dbname \gset
CREATE ROLE school_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE school_app   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'app_pw';
CREATE EXTENSION IF NOT EXISTS vector;
-- Not REASSIGN OWNED: the old role is normally the cluster's bootstrap superuser, whose system-pinned objects cannot be reassigned.
-- Every relation (table, partitioned table, sequence, view, materialised view, foreign table) of schema public changes owner explicitly.
SELECT set_config('r04.old_role', :'old_role', false);
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT c.oid::regclass AS rel, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind IN ('r','p','S','v','m','f')
             AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_setting('r04.old_role'))
             AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')      -- extension members stay as they are
  LOOP
    EXECUTE format('ALTER %s %s OWNER TO school_owner',
      CASE r.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END, r.rel);
  END LOOP;
END $$;
ALTER DATABASE :"dbname" OWNER TO school_owner;
ALTER SCHEMA public OWNER TO school_owner;
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO school_owner, school_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO school_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO school_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO school_app;
ALTER DEFAULT PRIVILEGES FOR ROLE school_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO school_app;
ALTER DEFAULT PRIVILEGES FOR ROLE school_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO school_app;
