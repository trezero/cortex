-- 036_rename_to_cortex.sql
-- Renames every archon_* table/index/policy and recreates every function whose
-- name or body references archon, then rewrites registry rows and self-records.
-- MUST run against the old schema with all Archon services STOPPED.

BEGIN;

-- Guard: abort if any archon-referencing function is bound to a trigger we don't
-- recreate dynamically (we'd need CASCADE, which we refuse to do blindly).
DO $$
DECLARE n INT;
BEGIN
  SELECT count(*) INTO n
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace ns ON ns.oid = p.pronamespace
  WHERE ns.nspname = 'public' AND NOT t.tgisinternal
    AND (p.proname ILIKE '%archon%' OR pg_get_functiondef(p.oid) ILIKE '%archon%');
  IF n > 0 THEN
    RAISE EXCEPTION 'Found % trigger(s) bound to archon-referencing functions — review pg_trigger before proceeding', n;
  END IF;
END $$;

-- 1. Rename tables (FKs, indexes, triggers, policies follow by OID).
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname = 'public' AND tablename LIKE 'archon\_%'
  LOOP
    EXECUTE format('ALTER TABLE public.%I RENAME TO %I',
                   r.tablename, 'cortex_' || substring(r.tablename from 8));
  END LOOP;
END $$;

-- 2. Cosmetic: rename archon-named indexes.
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT indexname, tablename FROM pg_indexes
           WHERE schemaname = 'public' AND indexname LIKE '%archon%'
  LOOP
    EXECUTE format('ALTER INDEX public.%I RENAME TO %I',
                   r.indexname, replace(r.indexname, 'archon', 'cortex'));
  END LOOP;
END $$;

-- 3. Cosmetic: rename archon-named policies.
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT policyname, tablename FROM pg_policies
           WHERE schemaname = 'public' AND policyname ILIKE '%archon%'
  LOOP
    EXECUTE format('ALTER POLICY %I ON public.%I RENAME TO %I',
                   r.policyname, r.tablename,
                   replace(replace(r.policyname, 'archon', 'cortex'), 'Archon', 'Cortex'));
  END LOOP;
END $$;

-- 4. Recreate every function whose name or stored body references archon.
--    ALTER TABLE RENAME does not rewrite stored function bodies, so we rebuild
--    each definition text with archon_->cortex_ (covers match_archon_*,
--    hybrid_search_archon_*, archive_task, increment_access_count, and
--    search_session_observations which has no repo SQL).
DO $$
DECLARE r RECORD; def TEXT; newdef TEXT;
BEGIN
  FOR r IN SELECT p.oid
           FROM pg_proc p
           JOIN pg_namespace ns ON ns.oid = p.pronamespace
           WHERE ns.nspname = 'public' AND p.prokind = 'f'
             AND (p.proname ILIKE '%archon%' OR pg_get_functiondef(p.oid) ILIKE '%archon%')
  LOOP
    def := pg_get_functiondef(r.oid);
    newdef := replace(replace(replace(replace(def, 'archon_', 'cortex_'),
                              'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex');
    EXECUTE format('DROP FUNCTION %s', r.oid::regprocedure);
    EXECUTE newdef;
  END LOOP;
END $$;

-- 5. Registry rows: rename extensions and rewrite their stored content + hash.
--    (content_hash is hex sha256 of content — matches the Python side.)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
UPDATE cortex_extensions
SET name = replace(name, 'archon', 'cortex'),
    content = replace(replace(replace(replace(content, 'archon-ui-main', 'cortex-ui'),
                              'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex'),
    content_hash = encode(digest(
        replace(replace(replace(replace(content, 'archon-ui-main', 'cortex-ui'),
                'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex'), 'sha256'), 'hex')
WHERE name ILIKE '%archon%' OR content ILIKE '%archon%';

-- 6. Central project row: prevent duplicate-project creation after the
--    folder + GitHub renames (setup matches by dir basename / GitHub URL).
UPDATE cortex_projects
SET title = 'cortex',
    github_repo = replace(replace(coalesce(github_repo, ''),
                  'archon-trinity', 'cortex'), 'Archon', 'cortex')
WHERE title = 'archon';

-- 7. Self-record (the tracking table was just renamed to cortex_migrations;
--    historical rows survive because they only contain filenames).
INSERT INTO cortex_migrations (version, migration_name)
VALUES ('0.1.0', '036_rename_to_cortex')
ON CONFLICT DO NOTHING;

COMMIT;
