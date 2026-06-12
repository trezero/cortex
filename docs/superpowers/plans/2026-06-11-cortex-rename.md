# Cortex Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename this Archon fork end-to-end to **Cortex** — repo internals, database, distributed artifacts in ~20 connected projects on 4 machines, GitHub repo, Cloudflare hostname, and local folders — per `docs/superpowers/specs/2026-06-11-cortex-rename-design.md`.

**Architecture:** Five verification-gated phases. Phase 1 renames everything inside the repo (including a new DB migration, written but NOT run). Phase 2 stops the stack, runs the migration against the old schema, then boots and verifies the renamed stack. Phase 3 builds and tests a cross-platform Python migration script for connected projects. Phase 4 renames the outer identity (GitHub, Cloudflare additive, local folders). Phase 5 sweeps the fleet, then retires the old hostname.

**Tech Stack:** PostgreSQL/Supabase (dynamic SQL via pg catalog), Python 3.12 stdlib (migrate script), bash/sed/git-mv (mechanical renames), gh CLI, Cloudflare API.

**Conventions used throughout:**
- The case-mapping sed (referred to as "the rename sed"):
  ```bash
  sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
  ```
  `archon-ui-main` → `cortex-ui` must run FIRST (else it becomes `cortex-ui-main`).
- Excluded from all content sweeps: `.git/`, `node_modules/`, `docs/superpowers/specs/2026-06-11-cortex-rename-design.md`, `docs/superpowers/plans/2026-06-11-cortex-rename.md` (these two documents describe the rename and intentionally say "archon").
- All repo work happens on the existing `rename` branch.
- Live DB access: run SQL in the Supabase SQL editor (or `psql "$SUPABASE_DB_URL"` if direct), using the credentials from `.env`.

---

## Phase 0 — Safety Net

### Task 1: Fix dead backup cron and take a verified backup

**Files:** none in repo (crontab + filesystem only)

- [ ] **Step 1: Confirm the cron path is dead**

Run: `crontab -l | grep archon-backup`
Expected: a line pointing at `/home/winadmin/projects/archon/scripts/backup/archon-backup.sh` (path does not exist).

- [ ] **Step 2: Re-point cron at the real path**

Run: `crontab -l | sed 's|/home/winadmin/projects/archon/|/home/winadmin/projects/Trinity/archon/|' | crontab -` then `crontab -l | grep archon-backup` to confirm.
(Note: Task 17 re-points this again after the folder rename — that is expected.)

- [ ] **Step 3: Run a backup now and verify it is non-empty**

Run: `bash /home/winadmin/projects/Trinity/archon/scripts/backup/archon-backup.sh`
Then: `ls -lh ~/archon-backups/ | tail -3` and confirm the newest dump is > 1 MB. If the script fails, STOP and fix it before anything else — this backup is the rollback path for the whole plan.

- [ ] **Step 4: Confirm clean git state**

Run: `git status --porcelain` → empty; `git branch --show-current` → `rename`.

---

## Phase 1 — Rename the Core Repo

### Task 2: Write the DB rename migration (do NOT run it yet)

**Files:**
- Create: `migration/0.1.0/036_rename_to_cortex.sql`

This migration runs against the OLD schema with the stack stopped (Task 9). It uses the pg catalog dynamically, so it is complete regardless of drift between repo SQL and the live DB (this is how it catches `search_session_observations`, which exists only in the live DB).

- [ ] **Step 1: Create the migration file with this exact content**

```sql
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
    newdef := replace(replace(replace(def, 'archon_', 'cortex_'),
                              'Archon', 'Cortex'), 'archon', 'cortex');
    EXECUTE format('DROP FUNCTION %s', r.oid::regprocedure);
    EXECUTE newdef;
  END LOOP;
END $$;

-- 5. Registry rows: rename extensions and rewrite their stored content + hash.
--    (content_hash is hex sha256 of content — matches the Python side.)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
UPDATE cortex_extensions
SET name = replace(name, 'archon', 'cortex'),
    content = replace(replace(replace(content, 'archon-ui-main', 'cortex-ui'),
                              'Archon', 'Cortex'), 'archon', 'cortex'),
    content_hash = encode(digest(
        replace(replace(replace(content, 'archon-ui-main', 'cortex-ui'),
                'Archon', 'Cortex'), 'archon', 'cortex'), 'sha256'), 'hex')
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
```

- [ ] **Step 2: Sanity-check counts the migration must preserve (live DB, read-only)**

Run in Supabase SQL editor and RECORD the numbers (used to verify in Task 10):
```sql
SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'archon\_%';
SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.prokind='f'
  AND (p.proname ILIKE '%archon%' OR pg_get_functiondef(p.oid) ILIKE '%archon%');
SELECT count(*) FROM archon_extensions WHERE name ILIKE '%archon%' OR content ILIKE '%archon%';
```

- [ ] **Step 3: Verify the content_hash format assumption**

Run: `grep -rn "content_hash" python/src/server/services/extensions/extension_service.py | head -5`
Expected: hashing via `hashlib.sha256(...).hexdigest()` over the raw content string. If the Python code hashes anything other than the bare content (e.g., name+content), adjust the `digest(...)` expression in step 5 of the SQL to match exactly.

- [ ] **Step 4: Commit**

```bash
git add migration/0.1.0/036_rename_to_cortex.sql
git commit -m "feat: add DB rename migration archon_* -> cortex_*"
```

### Task 3: Rewrite historical migration SQL and backup scripts

**Files:**
- Modify: `migration/complete_setup.sql`, `migration/0.1.0/*.sql` (all EXCEPT `036_rename_to_cortex.sql`), `migration/0.1.0/DB_UPGRADE_INSTRUCTIONS.md`
- Rename+Modify: `scripts/backup/archon-backup.sh` → `cortex-backup.sh`, `archon-restore.sh` → `cortex-restore.sh`, `archon-verify-restore.sh` → `cortex-verify-restore.sh`

- [ ] **Step 1: Rewrite migration SQL content (excluding 036)**

```bash
grep -rIl -i archon migration/ | grep -v 036_rename_to_cortex | \
  xargs sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```
(Migration re-run safety: the runner compares `(version, migration_name)` filename pairs only — rewriting file CONTENT never triggers re-runs, and no migration FILENAMES contain "archon", so none need renaming.)

- [ ] **Step 2: Rename and rewrite backup scripts**

```bash
git mv scripts/backup/archon-backup.sh scripts/backup/cortex-backup.sh
git mv scripts/backup/archon-restore.sh scripts/backup/cortex-restore.sh
git mv scripts/backup/archon-verify-restore.sh scripts/backup/cortex-verify-restore.sh
grep -rIl -i archon scripts/ | xargs sed -i 's/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```
This changes the table-discovery pattern to `tablename LIKE 'cortex_%'` and dump filenames to `cortex.dump`/`cortex.env`. (The cron still calls the OLD script name until Task 17 — acceptable: the old script file is gone after this commit, so backups pause between Task 3 and Task 17; the Task 1 backup covers the window. If you want zero gap, also run `crontab -l | sed 's/archon-backup.sh/cortex-backup.sh/' | crontab -` now — but the `cortex_%` pattern only finds tables after Task 10's migration, so a manual backup right before Task 10 is the real safety step and is included there.)

- [ ] **Step 3: Verify**

Run: `grep -rIl -i archon migration/ scripts/ | grep -v 036_rename_to_cortex`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add -A migration/ scripts/
git commit -m "feat: rename archon -> cortex in migration SQL and backup scripts"
```

### Task 4: Rename the Python backend (src + tests)

**Files:**
- Modify: everything under `python/` containing "archon" (106 files in `src/`, plus tests)
- Rename: `python/src/server/static/archon-scanner.py` → `cortex-scanner.py`, `python/tests/test_archon_scanner.py` → `test_cortex_scanner.py`

This single sweep covers: `pyproject.toml` name, FastMCP server name `archon-mcp-server` → `cortex-mcp-server` (`python/src/mcp_server/mcp_server.py:360`), MCP tool names `archon_search_sessions`/`archon_get_session` → `cortex_*` (`python/src/mcp_server/features/sessions/session_tools.py`), `/archon-setup/*` routes → `/cortex-setup/*` (`mcp_server.py:1025-1028`), env vars `ARCHON_*` → `CORTEX_*`, table constants, `migration_service.py` tracking-table name, `main.py:340` health check, `service_discovery.py` hostnames, user-agents, `version.py`.

- [ ] **Step 1: Rename archon-named files**

```bash
git mv python/src/server/static/archon-scanner.py python/src/server/static/cortex-scanner.py
git mv python/tests/test_archon_scanner.py python/tests/test_cortex_scanner.py
```

- [ ] **Step 2: Run the rename sed over python/**

```bash
grep -rIl -i archon python/ | \
  xargs sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```

- [ ] **Step 3: Fix the GitHub repo constant to the literal new repo name**

In `python/src/server/config/version.py`, the sed produced `GITHUB_REPO_NAME = "Cortex"`. Edit it to:
```python
GITHUB_REPO_NAME = "cortex"
```
(the new GitHub repo will be lowercase `trezero/cortex`, Task 15).

- [ ] **Step 4: Verify zero archon references and lint**

```bash
grep -rIl -i archon python/ ; echo "exit=$?"
```
Expected: no file list, `exit=1`.
```bash
cd python && uv run ruff check && cd ..
```
Expected: no new errors (pre-existing warnings unrelated to the rename are acceptable).

- [ ] **Step 5: Run the unit tests that don't need a live stack**

Run: `cd python && uv run pytest -x -q && cd ..`
Expected: same pass/fail profile as before the rename (run `git stash && uv run pytest -q; git stash pop` first if you need a baseline). Failures mentioning "archon" indicate a missed rename — fix before committing.

- [ ] **Step 6: Commit**

```bash
git add -A python/
git commit -m "feat: rename archon -> cortex across Python backend, MCP server, and tests"
```

### Task 5: Rename integrations (setup scripts, plugin, extensions, commands, snippet, cloudflare)

**Files:**
- Rename: `integrations/claude-code/setup/archonSetup.sh` → `cortexSetup.sh`, `archonSetup.bat` → `cortexSetup.bat`
- Rename: `integrations/claude-code/plugins/archon-memory/` → `cortex-memory/`
- Rename: `integrations/claude-code/extensions/archon-{bootstrap,extension-sync,link-project,memory,move-project}` → `cortex-*`
- Rename: `integrations/claude-code/commands/archon-setup.md` → `cortex-setup.md`, `integrations/claude-code/commands/archon/` → `commands/cortex/`
- Modify: ALL files under `integrations/` containing archon (includes `claude-md-snippet.md` markers, `scan-projects.md`, `postman-integration/`, `api-docs/`, `agentWorkOrderSetup.sh`, `cloudflare/provision-machine.sh`, `cloudflare/README.md`)

- [ ] **Step 1: Rename archon-named files and directories**

```bash
cd integrations/claude-code
git mv setup/archonSetup.sh setup/cortexSetup.sh
git mv setup/archonSetup.bat setup/cortexSetup.bat
git mv plugins/archon-memory plugins/cortex-memory
for e in bootstrap extension-sync link-project memory move-project; do
  git mv extensions/archon-$e extensions/cortex-$e
done
git mv commands/archon-setup.md commands/cortex-setup.md
git mv commands/archon commands/cortex
cd ../..
```

- [ ] **Step 2: Rename any remaining archon-named files inside integrations**

```bash
find integrations -depth -name '*archon*' -not -path '*/.git/*' | while read -r p; do
  git mv "$p" "$(echo "$p" | sed 's/archonSetup/cortexSetup/; s/archon/cortex/')"
done
find integrations -iname '*archon*' | wc -l
```
Expected final count: `0`.

- [ ] **Step 3: Rewrite content (this also renames the CLAUDE.md snippet markers `archon-rules-start/end` → `cortex-rules-start/end`)**

```bash
grep -rIl -i archon integrations/ | \
  xargs sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```

- [ ] **Step 4: Verify**

Run: `grep -rIl -i archon integrations/` → no output.
Spot-check the three content-only extensions got rewritten: `grep -rn "cortex" integrations/claude-code/commands/scan-projects.md | head -3` and `grep -rn "Cortex MCP" integrations/claude-code/extensions/postman-integration/SKILL.md | head -3` show cortex naming.

- [ ] **Step 5: Commit**

```bash
git add -A integrations/
git commit -m "feat: rename archon -> cortex across distributed integrations"
```

### Task 6: Rename Docker, env, Makefile

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `Makefile`, any `Dockerfile*` under `python/`
- Modify (NOT committed): `.env`

- [ ] **Step 1: Rewrite tracked files**

```bash
grep -rIl -i archon docker-compose.yml .env.example Makefile python/Dockerfile* 2>/dev/null | \
  xargs sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```
This renames services/containers (`cortex-server`, `cortex-mcp`, `cortex-agents`, `cortex-frontend`/`cortex-ui`, `cortex-cloudflared`), volumes (`cortex-*-data` — old `archon-*-data` volumes hold only unused `/app/data` mounts and are safe to orphan), and env vars.

- [ ] **Step 2: Update the local `.env` by hand**

Edit `.env`: rename `ARCHON_*` keys → `CORTEX_*`, `ARCHON_TUNNEL_TOKEN` → `CORTEX_TUNNEL_TOKEN`, and set `VITE_ALLOWED_HOSTS=archon.persalto.io,cortex.persalto.io` (both hosts until Phase 5 completes; drop the archon one in Task 19).

- [ ] **Step 3: Verify compose parses**

Run: `docker compose config --quiet && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example Makefile python/Dockerfile* 2>/dev/null
git commit -m "feat: rename archon -> cortex in docker, env, and make tooling"
```

### Task 7: Rename the frontend

**Files:**
- Rename: `archon-ui-main/` → `cortex-ui/`
- Modify: 47 files inside it containing archon (package.json name, vite.config.ts proxy, localStorage keys, `archon:credentials-updated` event, branding strings, Dockerfile)

- [ ] **Step 1: Rename the directory, then rewrite content**

```bash
git mv archon-ui-main cortex-ui
grep -rIl -i archon cortex-ui --exclude-dir=node_modules | \
  xargs sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```

- [ ] **Step 2: Verify**

```bash
grep -rIl -i archon cortex-ui --exclude-dir=node_modules
```
Expected: no output.
```bash
cd cortex-ui && npx tsc --noEmit && npm run biome && cd ..
```
Expected: clean (or identical to pre-rename baseline).

- [ ] **Step 3: Run frontend tests**

Run: `cd cortex-ui && npx vitest run 2>&1 | tail -5 && cd ..`
Expected: same pass profile as before the rename.

- [ ] **Step 4: Commit**

```bash
git add -A cortex-ui archon-ui-main 2>/dev/null; git add -A
git commit -m "feat: rename archon-ui-main -> cortex-ui and all frontend naming"
```

### Task 8: CI workflows, repo tooling, root + docs sweep

**Files:**
- Modify: `.github/workflows/*.yml` (ci.yml `working-directory`/cache paths/image tags, release-notes.yml, claude-review.yml, claude-fix.yml)
- Rename+Modify: `ARCHON_MCP_SETUP.md` → `CORTEX_MCP_SETUP.md`, `archonIntegration.md` → `cortexIntegration.md`, `archon-example-workflow/` → `cortex-example-workflow/`, `.claude/commands/archon-setup.md` → `cortex-setup.md`, `.claude/commands/archon/` → `.claude/commands/cortex/`, `.kiro/agents/archonSetup.md` → `cortexSetup.md`, `.kiro/patterns/archon-dev.md` → `cortex-dev.md`
- Modify: `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `PRPs/`, `docs/` (excluding the two rename documents), `.kiro/settings/mcp.json`

- [ ] **Step 1: Rename archon-named files/dirs in these areas**

```bash
for p in $(find .github .claude .kiro PRPs docs . -maxdepth 2 -iname '*archon*' -not -path './.git/*' -not -path './cortex-ui/*' -not -path './python/*' -not -path './integrations/*' -not -path './migration/*' -not -path './scripts/*' 2>/dev/null | sort -u); do
  git mv "$p" "$(echo "$p" | sed 's/ARCHON/CORTEX/; s/archonSetup/cortexSetup/; s/archonIntegration/cortexIntegration/; s/archon/cortex/')" 2>/dev/null || \
  mv "$p" "$(echo "$p" | sed 's/ARCHON/CORTEX/; s/archonSetup/cortexSetup/; s/archonIntegration/cortexIntegration/; s/archon/cortex/')"
done
find . -iname '*archon*' -not -path './.git/*' -not -path './node_modules/*' -not -path '*/node_modules/*' | wc -l
```
Expected final count: `0`. (Untracked files like `.claude/archon-config.json` fall to plain `mv` — they are this repo's own state files; renaming them now is correct since the renamed plugin/hooks expect cortex names. The internal keys get rewritten in step 2's sweep only for tracked files — fix the two untracked JSON state files by hand: open `.claude/cortex-config.json` and `.claude/cortex-state.json` and rename any `archon_*` keys to `cortex_*`.)

- [ ] **Step 2: Rewrite content everywhere that remains**

```bash
grep -rIl -i archon . \
  --exclude-dir=.git --exclude-dir=node_modules \
  --exclude=docs/superpowers/specs/2026-06-11-cortex-rename-design.md \
  --exclude=docs/superpowers/plans/2026-06-11-cortex-rename.md | \
  xargs sed -i 's/archon-ui-main/cortex-ui/g; s/ARCHON/CORTEX/g; s/Archon/Cortex/g; s/archon/cortex/g'
```

- [ ] **Step 3: Restore honest upstream attribution in README.md**

The sweep mangled references to the upstream project. Review `git diff README.md`, remove upstream-specific badges/links (trendshift badge, coleam00 CI badge, coleam00 discussions/kanban links — now pointing at nonexistent `coleam00/Cortex` URLs), and add this line near the top, exactly:

```markdown
> Cortex began as a fork of [Archon](https://github.com/coleam00/Archon) by Cole Medin, before upstream pivoted to a different product. It is now an independent project.
```
Also fix any other mangled upstream mentions found by: `grep -rn "coleam00" README.md CONTRIBUTING.md CLAUDE.md AGENTS.md docs/ PRPs/` — every `coleam00/Cortex` should either be removed or restored to `coleam00/Archon` (when genuinely referring to upstream).

- [ ] **Step 4: Final repo-wide gate**

```bash
grep -rIl -i archon . --exclude-dir=.git --exclude-dir=node_modules \
  --exclude=docs/superpowers/specs/2026-06-11-cortex-rename-design.md \
  --exclude=docs/superpowers/plans/2026-06-11-cortex-rename.md
```
Expected output: ONLY files whose remaining "Archon" refers to the upstream project (README attribution; possibly CONTRIBUTING). Read each hit and confirm it is intentional.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: rename archon -> cortex in CI, docs, and repo tooling"
```

---

## Phase 2 — Migrate DB, Then Verify Locally (GATE)

### Task 9: Stop the old stack and run the DB migration

**ORDER IS MANDATORY:** migration BEFORE the renamed stack boots. If the renamed server starts first, its migration runner sees no `cortex_migrations` table, treats the DB as fresh, and offers to create empty `cortex_*` tables alongside your data.

- [ ] **Step 1: Take a final pre-migration backup**

Run: `bash scripts/backup/cortex-backup.sh` — wait, its pattern is now `cortex_%` which matches nothing pre-migration. Instead run the archived old logic directly:
```bash
git show HEAD~7:scripts/backup/archon-backup.sh > /tmp/archon-backup-old.sh && bash /tmp/archon-backup-old.sh
```
(Adjust `HEAD~7` to whatever commit precedes Task 3; find it with `git log --oneline -- scripts/backup/archon-backup.sh`.) Verify the dump: `ls -lh ~/archon-backups/ | tail -2`, newest > 1 MB.

- [ ] **Step 2: Stop the stack**

Run: `docker compose down`
Expected: all containers stopped; `docker ps | grep -ci 'archon\|cortex'` → `0`.

- [ ] **Step 3: Run `migration/0.1.0/036_rename_to_cortex.sql`**

Paste the full file into the Supabase SQL editor and run it (or `psql "$DB_URL" -f migration/0.1.0/036_rename_to_cortex.sql`).
Expected: success, no exception from the trigger guard. If the guard raises, list the offending triggers (`SELECT tgname, relname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE NOT tgisinternal`), add explicit `DROP TRIGGER`/`CREATE TRIGGER` recreation for them to the migration, and re-run.

- [ ] **Step 4: Verify against the counts recorded in Task 2 step 2**

```sql
SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'archon\_%';  -- 0
SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'cortex\_%';  -- = old archon count
SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.prokind='f'
   AND (p.proname ILIKE '%archon%' OR pg_get_functiondef(p.oid) ILIKE '%archon%');        -- 0
SELECT migration_name FROM cortex_migrations ORDER BY applied_at DESC LIMIT 3;            -- includes 036_rename_to_cortex
SELECT count(*) FROM cortex_sources;                                                      -- > 0 (data survived)
SELECT title FROM cortex_projects WHERE title IN ('archon','cortex');                     -- 'cortex'
```

- [ ] **Step 5: Verify one extension hash matches Python's algorithm**

```sql
SELECT name, content_hash FROM cortex_extensions LIMIT 1;
```
Then locally: `python3 -c "import hashlib,sys; print(hashlib.sha256(open('/tmp/x','rb').read()).hexdigest())"` after saving that row's content to `/tmp/x` — hashes must match. If not, recompute hashes from Python for all rows (small script using the supabase client) before proceeding.

### Task 10: Boot the renamed stack and run the verification gate

- [ ] **Step 1: Build and start**

Run: `docker compose up --build -d`
Then: `docker compose ps` → `cortex-server`, `cortex-mcp`, `cortex-ui`, `cortex-agents` all healthy/running.
Then: `curl -s http://localhost:8181/health` → healthy JSON (this exercises the renamed `cortex_sources` health check); `curl -s http://localhost:8051/health` → healthy.

- [ ] **Step 2: Run both test suites**

```bash
cd python && uv run pytest -q; cd ..
cd cortex-ui && npx vitest run 2>&1 | tail -5; cd ..
```
Expected: pre-rename pass profile.

- [ ] **Step 3: Point this repo's MCP config at the new name**

Edit `.mcp.json` (gitignored): change key `"archon"` → `"cortex"` (URL unchanged: `http://172.16.1.230:8051/mcp`). Restart the Claude Code session afterward to pick it up.

- [ ] **Step 4: MCP round-trip smoke test (in a fresh Claude Code session, or via curl)**

Verify these tools respond with real data: `health_check`, `rag_get_available_sources`, `rag_search_knowledge_base` (exercises `match_cortex_*`/`hybrid_search_cortex_*`), `cortex_search_sessions` (exercises `search_session_observations`'s rewritten body), `find_projects`, `find_extensions` (names now `cortex-*`).

- [ ] **Step 5: UI smoke test**

Open `http://localhost:3737` — knowledge sources list loads, projects view loads, settings load. Branding says Cortex.

- [ ] **Step 6: Verify the setup bundle routes**

```bash
curl -sI http://localhost:8051/cortex-setup/extensions.tar.gz | head -1   # 200
curl -sI http://localhost:8051/cortex-setup/commands.tar.gz | head -1     # 200
curl -sI http://localhost:8051/cortex-setup/plugin/cortex-memory.tar.gz | head -1  # 200
curl -s  http://localhost:8051/cortex-setup/claude-md-snippet.md | head -3 # cortex-rules-start marker
```

**GATE: do not proceed to Phase 3 until every step above passes.**

---

## Phase 3 — Connected-Project Migration Script

### Task 11: Write `cortex-migrate.py`

**Files:**
- Create: `python/src/server/static/cortex-migrate.py`

Python 3.8+ stdlib only (like the scanner) so it runs on Linux/macOS/Windows. Per-project marker: presence of `.claude/cortex-config.json` (written LAST). Only rewrites an `"archon"` MCP key whose URL matches known Cortex hosts — never touches an upstream Archon V2 entry.

- [ ] **Step 1: Create the script with this content**

```python
#!/usr/bin/env python3
"""Migrate projects from Archon naming to Cortex naming.

Run once per machine:  python3 cortex-migrate.py --api-url http://HOST:8181 \
    --mcp-url http://HOST:8051 [--roots DIR ...] [--dry-run]
Remote machines add:   --cf-client-id ID --cf-client-secret SECRET
"""
import argparse, json, re, shutil, ssl, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path

KNOWN_HOST_PAT = re.compile(r"(localhost|127\.0\.0\.1|172\.16\.\d+\.\d+|[a-z0-9.-]*persalto\.io)")
OLD_SKILLS = ["archon-memory", "archon-bootstrap", "archon-link-project",
              "archon-extension-sync", "archon-move-project", "api-docs",
              "postman-integration", "scan-projects"]
OLD_COMMANDS = ["archon-setup.md", "scan-projects.md", "archon"]
RULES_RE = re.compile(r"<!-- archon-rules-start -->.*?<!-- archon-rules-end -->", re.DOTALL)

def ren(s):  # case-preserving archon->cortex for strings/keys
    return s.replace("ARCHON", "CORTEX").replace("Archon", "Cortex").replace("archon", "cortex")

def ren_keys(obj):
    if isinstance(obj, dict):
        return {ren(k): ren_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ren_keys(v) for v in obj]
    if isinstance(obj, str) and "persalto.io" in obj:
        return obj.replace("archon.persalto.io", "cortex.persalto.io")
    return obj

class Migrator:
    def __init__(self, args):
        self.api, self.mcp, self.dry = args.api_url.rstrip("/"), args.mcp_url.rstrip("/"), args.dry_run
        self.headers = {}
        if args.cf_client_id:
            self.headers = {"CF-Access-Client-Id": args.cf_client_id,
                            "CF-Access-Client-Secret": args.cf_client_secret}
        self.ok, self.skipped, self.failed = [], [], []

    def fetch(self, url, dest):
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)

    def act(self, desc, fn):
        print(f"  {'[dry-run] ' if self.dry else ''}{desc}")
        if not self.dry:
            fn()

    def migrate_project(self, proj: Path):
        cl = proj / ".claude"
        if (cl / "cortex-config.json").exists():
            self.skipped.append(str(proj)); print(f"SKIP (migrated): {proj}"); return
        old_cfg = cl / "archon-config.json"
        if not old_cfg.exists():
            return
        print(f"MIGRATING: {proj}")
        cfg = ren_keys(json.loads(old_cfg.read_text()))

        # 1. state files (config content held back; written LAST as the marker)
        for old, new in [("archon-state.json", "cortex-state.json"),
                         ("archon-memory-buffer.jsonl", "cortex-memory-buffer.jsonl")]:
            if (cl / old).exists():
                if old.endswith(".json"):
                    data = json.dumps(ren_keys(json.loads((cl / old).read_text())), indent=2)
                    self.act(f"rewrite {old} -> {new}",
                             lambda d=data, o=old, n=new: ((cl / n).write_text(d), (cl / o).unlink()))
                else:
                    self.act(f"rename {old} -> {new}", lambda o=old, n=new: (cl / o).rename(cl / n))

        # 2. .mcp.json: only touch an "archon" key pointing at OUR hosts
        mcp_file = proj / ".mcp.json"
        if mcp_file.exists():
            mc = json.loads(mcp_file.read_text())
            entry = mc.get("mcpServers", {}).get("archon")
            if entry and KNOWN_HOST_PAT.search(entry.get("url", "")):
                entry["url"] = entry["url"].replace("archon.persalto.io", "cortex.persalto.io")
                mc["mcpServers"]["cortex"] = entry          # headers preserved as-is
                del mc["mcpServers"]["archon"]
                self.act("rewrite .mcp.json archon -> cortex",
                         lambda d=json.dumps(mc, indent=2): mcp_file.write_text(d))

        # 3. extensions: remove old, install new bundles
        for s in OLD_SKILLS:
            for sub in ("skills", "commands"):
                t = cl / sub / s
                if t.exists():
                    self.act(f"remove {sub}/{s}", lambda t=t: shutil.rmtree(t, ignore_errors=True))
        for c in OLD_COMMANDS:
            t = cl / "commands" / c
            if t.exists():
                self.act(f"remove commands/{c}",
                         lambda t=t: shutil.rmtree(t, ignore_errors=True) if t.is_dir() else t.unlink())
        old_plugin = cl / "plugins" / "archon-memory"
        if old_plugin.exists():
            self.act("remove plugins/archon-memory", lambda: shutil.rmtree(old_plugin, ignore_errors=True))
        if not self.dry:
            with tempfile.TemporaryDirectory() as td:
                for url, dest in [(f"{self.mcp}/cortex-setup/extensions.tar.gz", cl / "skills"),
                                  (f"{self.mcp}/cortex-setup/commands.tar.gz", cl / "commands")]:
                    tb = Path(td) / "b.tar.gz"; self.fetch(url, tb)
                    dest.mkdir(parents=True, exist_ok=True)
                    with tarfile.open(tb) as t: t.extractall(dest)
                tb = Path(td) / "p.tar.gz"
                self.fetch(f"{self.mcp}/cortex-setup/plugin/cortex-memory.tar.gz", tb)
                pdir = cl / "plugins" / "cortex-memory"; pdir.mkdir(parents=True, exist_ok=True)
                with tarfile.open(tb) as t: t.extractall(pdir)
                req = pdir / "requirements.txt"
                if req.exists():
                    subprocess.run([sys.executable, "-m", "venv", str(pdir / ".venv")], check=True)
                    pip = pdir / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
                    subprocess.run([str(pip), "install", "-q", "-r", str(req)], check=True)
        else:
            print("  [dry-run] install cortex extension/command/plugin bundles")

        # 4. CLAUDE.md rules block
        cmd_file = proj / "CLAUDE.md"
        if cmd_file.exists() and "archon-rules-start" in cmd_file.read_text():
            snippet_path = Path(tempfile.gettempdir()) / "cortex-snippet.md"
            if not self.dry:
                self.fetch(f"{self.mcp}/cortex-setup/claude-md-snippet.md", snippet_path)
                new_text = RULES_RE.sub(snippet_path.read_text().strip(), cmd_file.read_text())
                cmd_file.write_text(new_text)
            print(f"  {'[dry-run] ' if self.dry else ''}replace CLAUDE.md archon-rules block")

        # 5. .gitignore + settings.local.json permission strings
        gi = proj / ".gitignore"
        if gi.exists() and "archon" in gi.read_text():
            self.act("rewrite .gitignore", lambda: gi.write_text(ren(gi.read_text())))
        sl = cl / "settings.local.json"
        if sl.exists() and "mcp__archon__" in sl.read_text():
            self.act("rewrite settings.local.json permissions",
                     lambda: sl.write_text(sl.read_text().replace("mcp__archon__", "mcp__cortex__")))

        # 6. .archon -> .cortex
        if (proj / ".archon").exists():
            self.act("rename .archon -> .cortex", lambda: (proj / ".archon").rename(proj / ".cortex"))

        # 7. marker LAST
        self.act("write cortex-config.json + remove archon-config.json",
                 lambda: ((cl / "cortex-config.json").write_text(json.dumps(cfg, indent=2)),
                          old_cfg.unlink()))
        self.ok.append(str(proj))

    def migrate_machine(self):
        home = Path.home()
        st = home / ".claude" / "settings.json"
        if st.exists() and "archon" in st.read_text():
            self.act("rewrite ~/.claude/settings.json hooks", lambda: st.write_text(ren(st.read_text())))
        gs = home / ".claude" / "archon-state.json"
        if gs.exists():
            def mv_global_state():
                (home / ".claude" / "cortex-state.json").write_text(
                    json.dumps(ren_keys(json.loads(gs.read_text())), indent=2))
                gs.unlink()
            self.act("rename global archon-state.json", mv_global_state)
        cfgdir = home / ".config" / "archon"
        if cfgdir.exists():
            def mv_cfg():
                new = home / ".config" / "cortex"; cfgdir.rename(new)
                for f in new.iterdir():
                    if "archon" in f.name: f.rename(new / ren(f.name))
                    target = new / ren(f.name) if "archon" in f.name else f
                    if target.suffix in (".env", ".json"):
                        target.write_text(ren(target.read_text()))
            self.act("migrate ~/.config/archon -> ~/.config/cortex", mv_cfg)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True); ap.add_argument("--mcp-url", required=True)
    ap.add_argument("--roots", nargs="*", default=[str(Path.home() / "projects")])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cf-client-id", default=""); ap.add_argument("--cf-client-secret", default="")
    ap.add_argument("--skip-machine", action="store_true",
                    help="skip the once-per-machine hook/global-state migration")
    args = ap.parse_args()
    m = Migrator(args)
    for root in args.roots:
        for cfg in sorted(Path(root).glob("*/.claude/archon-config.json")) + \
                   sorted(Path(root).glob("*/*/.claude/archon-config.json")):
            try:
                m.migrate_project(cfg.parent.parent)
            except Exception as e:
                m.failed.append(f"{cfg.parent.parent}: {e}")
                print(f"  FAILED: {e}", file=sys.stderr)
    if not args.skip_machine and not m.failed:
        m.migrate_machine()   # hooks swap only after every project migrated cleanly
    elif m.failed:
        print("\nMachine-level hook migration SKIPPED due to project failures — fix and re-run.")
    print(f"\nMigrated: {len(m.ok)}  Skipped: {len(m.skipped)}  Failed: {len(m.failed)}")
    for f in m.failed: print(f"  FAIL {f}")
    sys.exit(1 if m.failed else 0)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile python/src/server/static/cortex-migrate.py && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add python/src/server/static/cortex-migrate.py
git commit -m "feat: add cortex-migrate script for connected-project migration"
```

### Task 12: Serve the migrate script from the backend

**Files:**
- Modify: `python/src/server/api_routes/scanner_script_api.py` (post-Task-4 it already serves `cortex-scanner.py`)

- [ ] **Step 1: Add a route mirroring the existing scanner route**

Open `scanner_script_api.py`; it defines `SCRIPT_PATH` pointing at `static/cortex-scanner.py` and a GET route returning it. Add directly below, following the file's existing response style exactly (same response class and headers as the scanner route):

```python
MIGRATE_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "cortex-migrate.py")

@router.get("/migrate-script")
async def get_migrate_script():
    """Serve the cortex-migrate.py script for connected-machine migration."""
    with open(MIGRATE_SCRIPT_PATH) as f:
        content = f.read()
    return PlainTextResponse(content, headers={"Content-Disposition": 'attachment; filename="cortex-migrate.py"'})
```
(If the scanner route uses `FileResponse` or a different decorator path, copy that pattern instead — the route must live under the same router so the URL prefix matches the scanner's.)

- [ ] **Step 2: Restart and verify**

First find the router prefix: `grep -n "APIRouter\|prefix" python/src/server/api_routes/scanner_script_api.py` and note the prefix the scanner route is served under (same base the `/scan-projects` command downloads from). Then:

```bash
docker compose restart cortex-server && sleep 5
curl -s http://localhost:8181/<prefix>/migrate-script | head -3
```
Expected: the script's shebang and docstring.

- [ ] **Step 3: Commit**

```bash
git add python/src/server/api_routes/scanner_script_api.py
git commit -m "feat: serve cortex-migrate script from backend"
```

### Task 13: Test the migrate script on a scratch project, then one real project

- [ ] **Step 1: Dry-run against a scratch copy**

```bash
mkdir -p /tmp/migrate-test && cp -r ~/projects/emailBrain /tmp/migrate-test/
python3 python/src/server/static/cortex-migrate.py \
  --api-url http://172.16.1.230:8181 --mcp-url http://172.16.1.230:8051 \
  --roots /tmp/migrate-test --dry-run --skip-machine
```
Expected: each planned action printed with a `[dry-run]` prefix, summary `Migrated: 1  Skipped: 0  Failed: 0`, and NO file changes (`diff -rq ~/projects/emailBrain /tmp/migrate-test/emailBrain` → identical).

- [ ] **Step 2: Real run against the scratch copy**

Re-run without `--dry-run`. Then verify in the copy: `.claude/cortex-config.json` exists with `cortex_api_url` keys; `.claude/archon-config.json` gone; `.mcp.json` has `"cortex"` key; `.claude/skills/cortex-memory/` exists; `.claude/plugins/cortex-memory/` exists; CLAUDE.md contains `<!-- cortex-rules-start -->`; `.cortex/` exists if `.archon/` did; re-run is a no-op (`SKIP (migrated)`).

- [ ] **Step 3: Migrate ONE real project and verify in Claude Code**

```bash
python3 python/src/server/static/cortex-migrate.py \
  --api-url http://172.16.1.230:8181 --mcp-url http://172.16.1.230:8051 \
  --roots ~/projects --dry-run | head -40   # review the full sweep plan first
```
Then migrate just emailBrain by temporarily using `--roots` pointed at a directory containing only it, OR accept the full local sweep now if the dry-run output looks right (this is Phase 5 work arriving early for this machine — fine, the script is idempotent). Open emailBrain in Claude Code: `cortex` MCP tools load, session hooks fire (check a new session shows the LeaveOff/context injection), `/cortex-memory` skill available.

- [ ] **Step 4: Clean up and commit nothing (no repo changes in this task)**

`rm -rf /tmp/migrate-test`

---

## Phase 4 — Outer Identity

### Task 14: GitHub rename + push

- [ ] **Step 1: Push the rename branch and verify CI**

```bash
git push -u origin rename
gh run watch || gh run list --branch rename --limit 3
```
Expected: CI green (workflows now use `cortex-ui` paths — this validates Task 8).

- [ ] **Step 2: Merge `rename` → `main`** (after user confirms)

```bash
gh pr create --base main --head rename --title "Rename project to Cortex" --fill
```
Merge once checks pass.

- [ ] **Step 3: Rename the GitHub repo and update remotes**

```bash
gh api -X PATCH repos/trezero/archon-trinity -f name=cortex
git remote set-url origin https://github.com/trezero/cortex.git
git remote remove upstream
git remote -v   # origin -> trezero/cortex only
git fetch origin && git pull origin main
```
(GitHub auto-redirects the old URL, so unmigrated clones keep working.)

### Task 15: Cloudflare — ADD cortex.persalto.io (do not remove archon yet)

Credentials: `source /mnt/e/Projects/persalto-operating-space/cloudflare.persalto.env.local` (CF API token). Account `0b7d745203c82b5866aa75ef74bb8def`, zone `66f1b9309b25bb65ab691a0483acf144`, tunnel `0d035a48-2574-4af5-8c29-5da306fa9eb9`, Access app `1082b663-fc56-4a98-8334-aa648815450a`.

- [ ] **Step 1: Add DNS CNAME**

```bash
curl -sX POST "https://api.cloudflare.com/client/v4/zones/66f1b9309b25bb65ab691a0483acf144/dns_records" \
  -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"type":"CNAME","name":"cortex","content":"0d035a48-2574-4af5-8c29-5da306fa9eb9.cfargotunnel.com","proxied":true}' | python3 -m json.tool | grep '"success"'
```
Expected: `"success": true`

- [ ] **Step 2: Add cortex ingress rules to the tunnel config (additive)**

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/0b7d745203c82b5866aa75ef74bb8def/cfd_tunnel/0d035a48-2574-4af5-8c29-5da306fa9eb9/configurations" \
  -H "Authorization: Bearer $CF_API_TOKEN" > /tmp/tunnel-config.json
```
Edit `/tmp/tunnel-config.json`: duplicate every `archon.persalto.io` ingress rule with hostname `cortex.persalto.io` (keep service targets — note services are docker DNS names which Task 6 renamed: update the cortex rules to `http://cortex-mcp:8051` etc., and ALSO update the existing archon-hostname rules to the new service names, since the old docker services no longer exist). Keep the catch-all 404 LAST. PUT it back:
```bash
curl -sX PUT ".../configurations" -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" -d @/tmp/tunnel-config-updated.json | grep '"success"'
```

- [ ] **Step 3: Add the hostname to the EXISTING Access app**

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/0b7d745203c82b5866aa75ef74bb8def/access/apps/1082b663-fc56-4a98-8334-aa648815450a" \
  -H "Authorization: Bearer $CF_API_TOKEN" > /tmp/access-app.json
```
PATCH the app adding `cortex.persalto.io` to `self_hosted_domains` (keep `archon.persalto.io` in the list). Do NOT create a new app — service tokens are bound to this app's policy.

- [ ] **Step 4: Verify end-to-end with the test service token**

```bash
source /mnt/e/Projects/persalto-operating-space/archon-access-tokens.env.local
curl -s -o /dev/null -w "%{http_code}" https://cortex.persalto.io/api/health \
  -H "CF-Access-Client-Id: $CLIENT_ID" -H "CF-Access-Client-Secret: $CLIENT_SECRET"   # 200
curl -s -o /dev/null -w "%{http_code}" https://cortex.persalto.io/api/health           # 403 (no token)
curl -s -o /dev/null -w "%{http_code}" https://archon.persalto.io/api/health \
  -H "CF-Access-Client-Id: $CLIENT_ID" -H "CF-Access-Client-Secret: $CLIENT_SECRET"   # still 200 (old host alive)
```

- [ ] **Step 5: Update provision-machine.sh references check**

Task 5's sweep already renamed `integrations/cloudflare/provision-machine.sh` contents to cortex; confirm: `grep -c archon integrations/cloudflare/provision-machine.sh` → `0`.

### Task 16: Local machine sweep + folder rename (this WSL box)

- [ ] **Step 1: Run the full local sweep (if not already done in Task 13 step 3)**

```bash
python3 python/src/server/static/cortex-migrate.py \
  --api-url http://172.16.1.230:8181 --mcp-url http://172.16.1.230:8051 --roots ~/projects
```
Expected: `Failed: 0`; machine-level hooks rewritten in `~/.claude/settings.json`.

- [ ] **Step 2: Rename the repo folder**

```bash
cd ~ && mv ~/projects/Trinity/archon ~/projects/Trinity/cortex && cd ~/projects/Trinity/cortex
```

- [ ] **Step 3: Migrate Claude Code per-project state to the new path key**

```bash
mv ~/.claude/projects/-home-winadmin-projects-Trinity-archon \
   ~/.claude/projects/-home-winadmin-projects-Trinity-cortex
ls ~/.claude/projects/ | grep -i archon   # check for strays
```
If the stale `-home-winadmin-projects-archon` dir exists, inspect it (`ls`) and delete it if it only contains old transcripts: `rm -rf ~/.claude/projects/-home-winadmin-projects-archon`.
Also rewrite memory content: `sed -i 's/Trinity\/archon/Trinity\/cortex/g; s/Archon/Cortex/g; s/archon/cortex/g' ~/.claude/projects/-home-winadmin-projects-Trinity-cortex/memory/MEMORY.md` (review the diff — memory files referencing the upstream Archon V2 should keep that name).

- [ ] **Step 4: Final crontab fix**

```bash
crontab -l | sed 's|/projects/Trinity/archon/scripts/backup/archon-backup.sh|/projects/Trinity/cortex/scripts/backup/cortex-backup.sh|' | crontab -
crontab -l | grep cortex-backup
```
Run the backup once to confirm it now dumps `cortex_*` tables: `bash ~/projects/Trinity/cortex/scripts/backup/cortex-backup.sh && ls -lh ~/archon-backups/ | tail -2` (dump > 1 MB).

- [ ] **Step 5: Update the user's global rules**

Edit `~/.claude/CLAUDE.md`: in the gitignore-block guidance, replace the `archon-*` filenames with `cortex-*` equivalents and `.archon/` with `.cortex/`, and rename mentions of "Archon (extension registry + sync workflow)" to Cortex. (User-owned file — show the diff to the user.)

- [ ] **Step 6: Restart docker from the new path**

```bash
cd ~/projects/Trinity/cortex && docker compose up -d && curl -s http://localhost:8181/health
```
Expected: healthy. (Compose project name may change with the folder name; old `archon_*` networks/volumes can be pruned later with `docker system prune` — not required.)

---

## Phase 5 — Fleet Sweep, Then Retire the Old Hostname

### Task 17: Migrate each remaining machine

Per machine, in order: **WIN-AI-PC (Windows side) → MacBookPro-M1 → WhiteShark**.

- [ ] **Step 1: Windows (local network, no CF token needed)**

In PowerShell/cmd:
```bat
curl -s http://172.16.1.230:8181/<prefix>/migrate-script -o %TEMP%\cortex-migrate.py
python %TEMP%\cortex-migrate.py --api-url http://172.16.1.230:8181 --mcp-url http://172.16.1.230:8051 --roots %USERPROFILE%\projects
```
(`<prefix>` = the route prefix confirmed in Task 12 step 2.)

- [ ] **Step 2: Remote machines (MacBook, WhiteShark) — via the NEW hostname with CF-Access**

On each machine:
```bash
source ~/.config/archon/cf-access.env   # still old path pre-migration; provides client id/secret
curl -s https://cortex.persalto.io/<prefix>/migrate-script \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -o /tmp/cortex-migrate.py
python3 /tmp/cortex-migrate.py --api-url https://cortex.persalto.io --mcp-url https://cortex.persalto.io \
  --roots ~/projects --cf-client-id "$CF_ACCESS_CLIENT_ID" --cf-client-secret "$CF_ACCESS_CLIENT_SECRET"
```
(Adjust env var names to whatever `cf-access.env` actually contains — check the file first. Note: on remote machines the MCP/API share the one hostname via path routing, hence both URLs identical.)

- [ ] **Step 3: Verify each machine**

On each: open one migrated project in Claude Code → `cortex` MCP tools load; new session shows the injected Cortex context (LeaveOff Point); `~/.config/cortex/` exists on remote machines (`~/.config/archon/` gone); `Failed: 0` in the script summary.

### Task 18: Retire archon.persalto.io and finish

- [ ] **Step 1: Remove the old hostname (only after ALL machines verified)**

- Tunnel config: GET the config again, remove all `archon.persalto.io` ingress rules, PUT back.
- Access app: PATCH removing `archon.persalto.io` from `self_hosted_domains`.
- DNS: `curl -sX DELETE .../dns_records/<archon-record-id>` (find the id via `GET /dns_records?name=archon.persalto.io`).
- Verify: `curl -s -o /dev/null -w "%{http_code}" https://archon.persalto.io/api/health -H ...token...` → 404/530 (no route), and `https://cortex.persalto.io/api/health` with token → 200.
- Optionally rename the tunnel ("archon-persalto" → "cortex-persalto") and Access app label ("Archon" → "Cortex") — labels only, zero functional impact.

- [ ] **Step 2: Drop the old host from VITE_ALLOWED_HOSTS**

Edit `.env`: `VITE_ALLOWED_HOSTS=cortex.persalto.io`. Restart: `docker compose up -d`.

- [ ] **Step 3: Final LeaveOff Point**

Run `git status --porcelain`, then `manage_leaveoff_point(action="update")` with component "Cortex Rename", a summary of completed phases, any remaining items (e.g., Postman Cloud collection renames — manual, low priority), `system_name` from `.claude/cortex-state.json`, and `git_clean` accordingly.

---

## Rollback Notes

- **Before Task 9 (DB migration):** everything is repo-only on the `rename` branch — `git checkout main` restores the old world; the old stack still runs.
- **After Task 9:** roll back the DB by restoring the Task 9 backup (`scripts/backup/cortex-restore.sh` — note its internals now expect cortex names; for an archon-era restore use the old script from git history) and checking out `main`.
- **After Phase 5:** rollback is not practical; fix forward (the migrate script's per-project idempotency means individual project issues are re-runnable).
