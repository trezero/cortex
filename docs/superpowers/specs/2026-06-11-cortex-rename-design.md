# Cortex Rename — Design Spec

**Date:** 2026-06-11 (rev 2, post adversarial review)
**Status:** Approved (design), pending implementation plan
**Branch:** `rename`

## Context

This repo is a heavily customized fork of `coleam00/Archon`. Upstream has pivoted to an
entirely different product (a YAML workflow engine for AI coding) that still ships under
the name "Archon" and claims overlapping artifacts on disk: `.archon/` directories inside
target repos, a `.claude/skills/archon` skill, and the "archon" identity in MCP configs.

The owner wants to keep using this fork as the Trinity platform's knowledge/memory/task
brain while also adopting the new upstream Archon in the same projects. Both cannot
coexist under the same name. This fork is therefore renamed end-to-end to **Cortex**.

Decisions made during design:

| Decision | Choice |
|---|---|
| New name | **Cortex** (`cortex-server`, `cortex_*` tables, `/cortex-setup`, `CORTEX_HOST`, `.cortex/`, `cortex-memory`) |
| Database tables | Rename `archon_*` → `cortex_*` in place via one SQL migration |
| Connected projects | Automated migration script (Python, cross-platform), preserving project/machine IDs |
| GitHub repo | Rename `trezero/archon-trinity` → `trezero/cortex`; drop dead `coleam00` upstream remote |
| Cloudflare | Add `cortex.persalto.io` alongside `archon.persalto.io`; retire old host only after fleet sweep |
| Local folder | `~/projects/Trinity/archon` → `~/projects/Trinity/cortex`; `archon-ui-main/` → `cortex-ui/` |
| Compatibility | None. No shims, no dual-name support (fix-forward rule) |

This spec was adversarially reviewed by two independent agents (missed-surface lens and
execution-design lens); their confirmed findings are incorporated below.

## Naming surface inventory

### Internal (repo-only, no external consumers)

- Docker compose: services/containers `archon-server`, `archon-mcp`, `archon-agents`,
  `archon-frontend`/`archon-ui`, `archon-cloudflared`; named volumes `archon-*-data`
  (volumes mount `/app/data`, which nothing reads — safe to orphan).
- Env vars: `ARCHON_HOST`, `ARCHON_SERVER_PORT`, `ARCHON_MCP_PORT`, `ARCHON_AGENTS_PORT`,
  `ARCHON_UI_PORT`, `ARCHON_TUNNEL_TOKEN`, `VITE_ARCHON_SERVER_PORT` (in `.env`,
  `.env.example`, `docker-compose.yml`, Dockerfiles, `Makefile`, Python config, frontend).
- Python: `pyproject.toml` name `archon`; FastMCP server name `archon-mcp-server`
  (`python/src/mcp_server/mcp_server.py`); **MCP tool names** `archon_search_sessions`
  and `archon_get_session` (`python/src/mcp_server/features/sessions/session_tools.py`)
  → `cortex_search_sessions`/`cortex_get_session`; FastAPI title/description;
  `ARCHON_VERSION` and User-Agent strings; `ArchonContext`;
  `python/src/server/config/service_discovery.py` hostname mappings (`archon-server`,
  `archon-mcp`, `archon-agents`, `startswith("archon-")` filter); `main.py` health check
  querying `archon_sources`.
- Tests: `python/tests/` has ~219 archon references including `test_archon_scanner.py`
  and table-name assertions — must be renamed in Phase 1 or the Phase 2 pytest gate fails.
- Frontend: `archon-ui-main/` directory; package name `archon-ui`; localStorage keys;
  custom event `archon:credentials-updated`; branding strings; `vite.config.ts` proxy to
  `archon-agent-work-orders`.
- CI/CD: `.github/workflows/ci.yml` (`working-directory: ./archon-ui-main`,
  `cache-dependency-path`, image tags `archon-*:test`, `ARCHON_*_PORT` build args),
  `release-notes.yml` (diffs `archon-ui-main/`), `claude-review.yml`/`claude-fix.yml`
  prompts naming "Archon".
- Backup/restore: `scripts/backup/archon-backup.sh` discovers tables via
  `tablename LIKE 'archon_%'` → must become `cortex_%`; `archon-restore.sh`,
  `archon-verify-restore.sh`, dump/env filenames. **Known pre-existing bug:** the user
  crontab entry points at `/home/winadmin/projects/archon/...` which no longer exists —
  scheduled backups are currently dead and must be re-pointed at the new path.
- Repo dev tooling: `.claude/commands/archon-setup.md`, `.claude/commands/archon/*.md`,
  `.kiro/agents/archonSetup.md`, `.kiro/patterns/archon-dev.md`, `.kiro/settings/mcp.json`,
  `archon-example-workflow/`, `agentWorkOrderSetup.sh` (greps for `archon-server`,
  checks `archon_agent_work_orders` tables).
- Docs: README.md, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, ARCHON_MCP_SETUP.md,
  archonIntegration.md, PRPs/ai_docs/, docs/ tree.

### Database (one-time migration, data preserved)

- ~30 tables prefixed `archon_` — **enumerate from the live schema**
  (`pg_tables WHERE tablename LIKE 'archon_%'`), not from repo SQL.
- **Functions: enumerate from `pg_proc` where the body or name matches `archon`**, not
  from repo files. Known set: `match_archon_crawled_pages(_multi)`,
  `match_archon_code_examples(_multi)`, `hybrid_search_archon_crawled_pages(_multi)`,
  `hybrid_search_archon_code_examples(_multi)` (live code paths via
  `hybrid_search_strategy.py`); non-prefixed functions whose **bodies** embed archon
  table names and must be recreated (`increment_access_count`, `archive_task`); and
  `search_session_observations`, which exists **only in the live DB** (no repo SQL) yet
  is called by `session_service.py` — it must be dumped from the live DB and recreated.
  `ALTER TABLE RENAME` does not rewrite function bodies.
- `archon_migrations` tracking table: renamed in place **preserving rows** (row contents
  are filenames containing no "archon", so history survives); the rename migration
  self-records into `cortex_migrations`. `migration_service.py` constants updated in the
  same change.
- Indexes/triggers/RLS policies bind by OID and survive renames (stale names are
  cosmetic; rename them in the same migration for hygiene). No archon-prefixed enum
  types, views, or sequences exist.
- Registry data: `cortex_extensions` rows store **full extension content + SHA-256
  content_hash** (`extension_service.py`). The migration (or a post-migration script)
  must rewrite content bodies (archon references inside skill/command markdown) and
  recompute hashes, or every extension shows as locally-modified/stale on next sync.
- Central project row: update the archon repo's own project row (`title: "archon"`,
  github_repo) to `cortex` / new repo URL, or future setup/scan runs (which match by
  directory basename and normalized GitHub URL) will create a duplicate project.
- Python table-name constants across `python/src/server/services/` and the SQL files in
  `migration/` are updated in the same change.

### External contract (artifacts living in OTHER repos/machines)

Created by `archonSetup.sh`/`.bat`, `archon-scanner.py`, and extension sync across ~20+
projects on 4 machines (WIN-AI-PC WSL, WIN-AI-PC Windows, MacBookPro-M1, WhiteShark):

- `.mcp.json` entry keyed `"archon"` → local `http://{host}:8051/mcp` or remote
  `https://archon.persalto.io/mcp` **with CF-Access headers that must be preserved**.
- `.claude/archon-config.json`, `.claude/archon-state.json`,
  `.claude/archon-memory-buffer.jsonl` (and their internal `archon_*` JSON keys).
- `.claude/plugins/archon-memory/` (plugin + its own `.mcp.json` key `archon-memory`).
- `.claude/skills/` and `.claude/commands/`: all 7 distributed extensions — the
  `archon-*` ones (`archon-memory`, `archon-bootstrap`, `archon-link-project`,
  `archon-extension-sync`, `archon-move-project`) **and** the non-archon-named ones
  whose content references archon (`scan-projects`, `postman-integration`, `api-docs`).
- **Injected CLAUDE.md blocks**: target repos' CLAUDE.md files contain
  `<!-- archon-rules-start -->…<!-- archon-rules-end -->` sections (from
  `claude-md-snippet.md`) referencing archon state files and commands — must be replaced
  with the cortex snippet (and new marker names).
- `~/.claude/settings.json` hooks (SessionStart/Stop/PostToolUse) pointing at
  `archon-memory` script paths; `~/.claude/archon-state.json` (global machine state —
  note: it is `archon-state.json` at global scope, not `archon-config.json`).
- `mcp__archon__*` permission strings in projects' `.claude/settings.local.json`
  allow-lists (stale after rename → re-prompts; migrate script rewrites to
  `mcp__cortex__*`).
- `.gitignore` entries naming the archon files; `~/.claude/CLAUDE.md` global rules
  mandating the archon gitignore block (user updates this by hand or via the sweep).
- `.archon/` knowledge directories — direct collision with Archon V2's
  `.archon/workflows/`.
- Remote machines additionally have `~/.config/archon/cf-access.env` (contains
  `ARCHON_URL=...`) and `~/.config/archon/archon.mcp.json` planted by
  `provision-machine.sh`.
- Backend routes serving the bundles: `/archon-setup/*` → `/cortex-setup/*` (note: the
  old plugin's self-update check will 404 after this — by design; the migrate script is
  the only repair path).
- Stale Claude Code state dirs: `~/.claude/projects/-home-winadmin-projects-Trinity-archon`
  (active — rename to new path key) and `-home-winadmin-projects-archon` (stale).
- Out-of-band: Postman Cloud collection/environment names derived from "Archon" live in
  Postman SaaS — rename manually or via the postman sync tooling, low priority.

### Outer identity

- GitHub `trezero/archon-trinity` → `trezero/cortex`; `version.py`
  `GITHUB_REPO_OWNER`/`GITHUB_REPO_NAME`; local `origin` remote; remove `upstream`.
- Cloudflare tunnel "archon-persalto" (id unchanged): **add** `cortex.persalto.io`
  ingress + DNS CNAME and add the hostname to the **existing** Access app (a new app
  would invalidate every machine's service token against the `approved-machines`
  policy). `archon.persalto.io` stays live until Phase 5 completes, then is removed.
- Local path `~/projects/Trinity/archon` → `~/projects/Trinity/cortex`.

## Architecture of the rename (phased, verification-gated)

Guiding rule: **rename and verify the central system first; only then touch connected
projects. The old public hostname stays alive until every remote machine is migrated.**

### Phase 0 — Safety net
- Fix the dead backup crontab path, run a full Supabase backup, verify the dump is
  non-empty.
- Clean git state on branch `rename`.

### Phase 1 — Rename the core repo
One coordinated change on the `rename` branch covering everything in the Internal +
Database inventory above: DB rename migration (tables from live schema, functions from
`pg_proc`, tracking-table self-record, registry content rewrite + hash recompute,
central project row update), Python (constants, package, MCP server + tool names, env
vars, routes, service discovery, health check), tests, docker-compose, `.env*`,
Makefile, CI workflows, backup scripts, distribution artifacts (`cortexSetup.sh/.bat`,
`cortex-scanner.py`, `cortex-memory` plugin, all 7 extensions including content-only
updates to `scan-projects`/`postman-integration`/`api-docs`, `claude-md-snippet.md`
with new `cortex-rules-*` markers, state-file names and JSON keys), frontend
(`cortex-ui/` dir, package, branding, storage keys), and docs.

### Phase 2 — Migrate DB, then verify locally (gate)
**Order matters:** (1) stop the old stack; (2) run the DB rename migration against the
old schema; (3) `docker compose up --build` the renamed stack. Starting the renamed
server before the migration would make the migration runner see a missing tracking
table and offer to re-create empty `cortex_*` tables (silent data-orphaning) — this
ordering is mandatory. Then: backend `uv run pytest` + frontend `vitest`; MCP connect
with the new `"cortex"` key in this repo's `.mcp.json`; exercise RAG search (including
hybrid search), session search, projects/tasks, extension list; UI smoke test.
Nothing external is touched until this passes.

### Phase 3 — Connected-project migration script
New `cortex-migrate` script, **written in Python** (same pattern as the scanner) so it
runs on Linux/macOS/Windows alike, served by the backend. Per machine it sweeps all
known project roots and, per project:
1. Renames `.claude/archon-config.json` → `cortex-config.json`, `archon-state.json` →
   `cortex-state.json`, `archon-memory-buffer.jsonl` → `cortex-memory-buffer.jsonl`,
   rewriting internal keys while **preserving project_id, machine_id, fingerprint**.
2. Rewrites `.mcp.json`: renames the `"archon"` key to `"cortex"` **only if its URL
   matches a known Cortex/Archon host** (localhost:8051, LAN IP, `*.persalto.io`) — so
   the sweep can never clobber an upstream Archon V2 entry; preserves CF-Access
   `headers`; updates remote URLs to `cortex.persalto.io`.
3. Removes all 7 old extensions (skills/commands/plugin) and installs the new cortex
   tarballs.
4. Replaces the `<!-- archon-rules-start/end -->` block in the project's CLAUDE.md with
   the cortex snippet.
5. Updates `.gitignore` entries; rewrites `mcp__archon__*` permission strings in
   `.claude/settings.local.json` to `mcp__cortex__*`.
6. Renames `.archon/` → `.cortex/`.
7. Once per machine, **after all projects on that machine are migrated**: rewrites
   `~/.claude/settings.json` hook paths to cortex-memory scripts; renames
   `~/.claude/archon-state.json` → `cortex-state.json`; on remote machines renames
   `~/.config/archon/` → `~/.config/cortex/` and rewrites `cf-access.env` keys.
   (Hooks swap last because they are machine-global while plugin dirs are per-project;
   swapping early would silently break memory capture in unmigrated projects.)

Migrated-marker: **presence of `.claude/cortex-config.json`** (not the `.mcp.json` key,
whose absence conflates "migrated" with "never configured"). Idempotent: re-runs skip
migrated projects; per-project failures are logged with a success/failure summary and
never leave a project half-renamed (state files rename first, marker file is the final
write of the per-project sequence).

### Phase 4 — Outer identity
- GitHub: `gh api` rename to `trezero/cortex`; update `origin`; remove `upstream`;
  `version.py` constants (already renamed in Phase 1; verify release lookup works).
- Cloudflare: add `cortex.persalto.io` (DNS CNAME + tunnel ingress + existing Access
  app). Do **not** remove the archon hostname yet.
- Local folder: `mv ~/projects/Trinity/archon ~/projects/Trinity/cortex`; rename
  `~/.claude/projects/-home-winadmin-projects-Trinity-archon` to the new path key;
  delete the stale `-home-winadmin-projects-archon` dir; fix the backup crontab path
  (again, to the final location); update MEMORY.md references.

### Phase 5 — Fleet sweep (gate per machine)
Run `cortex-migrate` on each machine: WIN-AI-PC WSL (this box), WIN-AI-PC Windows,
MacBookPro-M1, WhiteShark. **Known window:** until a machine is swept, its hooks fail
silently (they swallow errors) and the old plugin's self-update 404s — memory capture
is paused on that machine, nothing is lost or corrupted. Verification per machine: open
one migrated project in Claude Code, confirm `cortex` MCP tools load, session hooks
fire, LeaveOff Point loads. After all machines pass: remove the `archon.persalto.io`
ingress rule, DNS record, and Access-app hostname; optionally rename the tunnel and
Access app labels.

## Error handling

- DB migration runs inside a transaction against the old schema with the stack stopped;
  on failure nothing is renamed and the Phase 0 backup is the recovery path.
- `cortex-migrate`: `--dry-run` mode prints planned changes; per-project failures are
  reported (continue-and-log batch rule) with exact paths; no silent fallbacks — if the
  Cortex API is unreachable it fails fast with the URL it tried.
- The Phase 2 gate explicitly tests hybrid search and session search (the two paths
  backed by DB functions the repo SQL doesn't fully define).

## Testing

- Phase 1 includes renaming `python/tests/` fixtures so the Phase 2 gate is meaningful.
- `cortex-migrate` is first exercised with `--dry-run`, then against a scratch copy of
  one real project (e.g. a cp -r of emailBrain), before the fleet sweep.
- CI must pass on the renamed branch before Phase 4's GitHub rename.

## Out of scope

- Any change to the new upstream Archon V2 repo (`~/projects/archonV2`).
- Compatibility shims, dual-name support, or backward-compatible aliases.
- Renaming the Supabase project/infrastructure itself (only objects inside it).
- Postman Cloud collection renames (manual, low priority, post-sweep).
