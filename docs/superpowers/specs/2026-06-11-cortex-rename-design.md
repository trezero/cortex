# Cortex Rename — Design Spec

**Date:** 2026-06-11
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
| Connected projects | Automated migration script, preserving project/machine IDs (no re-registration) |
| GitHub repo | Rename `trezero/archon-trinity` → `trezero/cortex`; drop dead `coleam00` upstream remote |
| Cloudflare | `archon.persalto.io` → `cortex.persalto.io` on the existing tunnel |
| Local folder | `~/projects/Trinity/archon` → `~/projects/Trinity/cortex`; `archon-ui-main/` → `cortex-ui/` |
| Compatibility | None. No shims, no dual-name support (fix-forward rule) |

## Naming surface inventory (from exploration)

### Internal (repo-only, no external consumers)

- Docker compose: services/containers `archon-server`, `archon-mcp`, `archon-agents`,
  `archon-frontend`/`archon-ui`, `archon-cloudflared`; named volumes `archon-*-data`.
- Env vars: `ARCHON_HOST`, `ARCHON_SERVER_PORT`, `ARCHON_MCP_PORT`, `ARCHON_AGENTS_PORT`,
  `ARCHON_UI_PORT`, `ARCHON_TUNNEL_TOKEN`, `VITE_ARCHON_SERVER_PORT` (in `.env`,
  `.env.example`, `docker-compose.yml`, `Makefile`, Python config, frontend config).
- Python: `pyproject.toml` name `archon`; FastMCP server name `archon-mcp-server`
  (`python/src/mcp_server/mcp_server.py`); FastAPI title/description; `ARCHON_VERSION`
  and User-Agent strings (`Archon-Bug-Reporter`, `Archon-Discovery`); `ArchonContext`.
- Frontend: `archon-ui-main/` directory; package name `archon-ui`; localStorage keys
  (`archon:chat-default-model`, `archon_projects_active_filter`, `archon_provider_models`);
  custom event `archon:credentials-updated`; branding strings.
- Docs: README.md, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, ARCHON_MCP_SETUP.md,
  archonIntegration.md, PRPs/ai_docs/, docs/ tree.

### Database (one-time migration, data preserved)

- ~30 tables prefixed `archon_` (settings, sources, crawled_pages, code_examples,
  page_metadata, projects, tasks, project_sources, sessions, extensions,
  extension_versions, project_extensions, systems, system_extensions, leaveoff_points,
  materialization_history, prompts, migrations, document_versions, agent_work_orders,
  agent_work_order_steps, configured_repositories, postman_collections, skills tables, …
  enumerate from live schema at implementation time).
- 4 RPC functions: `match_archon_crawled_pages`, `match_archon_crawled_pages_multi`,
  `match_archon_code_examples`, `match_archon_code_examples_multi`.
- Indexes/triggers/policies embedding the `archon_` prefix.
- Python table-name constants across `python/src/server/services/` and migration SQL in
  `migration/` must be updated in the same change.

### External contract (artifacts living in OTHER repos/machines)

Created by `archonSetup.sh`/`.bat`, `archon-scanner.py`, and extension sync across ~20+
projects on 4 machines (WIN-AI-PC WSL, WIN-AI-PC Windows, MacBookPro-M1, WhiteShark):

- `.mcp.json` entry keyed `"archon"` → `http://{host}:8051/mcp` or remote URL.
- `.claude/archon-config.json` (machine fingerprint, `archon_api_url`, `archon_mcp_url`,
  project_id, install_scope), `.claude/archon-state.json` (system_name,
  archon_project_id, sources), `.claude/archon-memory-buffer.jsonl`.
- `.claude/plugins/archon-memory/` (plugin + its own `.mcp.json` key `archon-memory`).
- `.claude/skills/`: `archon-memory`, `archon-bootstrap`, `archon-link-project`,
  `archon-extension-sync`, `scan-projects`; `.claude/commands/`: `archon-setup.md`, etc.
- `~/.claude/settings.json` hooks (SessionStart/Stop/PostToolUse) pointing at
  `archon-memory` script paths.
- `.gitignore` entries naming the archon files.
- `.archon/` knowledge directories (`.archon/knowledge/`, `.archon/index.md`) — these
  directly collide with Archon V2's `.archon/workflows/`.
- Backend routes serving the bundles: `/archon-setup/extensions.tar.gz`,
  `/archon-setup/commands.tar.gz`, `/archon-setup/plugin/archon-memory.tar.gz`,
  `/archon-setup/claude-md-snippet.md`, `/api/setup/script-sh|bat`.
- Extension registry rows in `archon_extensions` carry the `archon-*` extension names.

### Outer identity

- GitHub `trezero/archon-trinity`; `version.py` `GITHUB_REPO_OWNER`/`GITHUB_REPO_NAME`.
- Cloudflare tunnel "archon-persalto" ingress for `archon.persalto.io`, Access app
  "Archon", `integrations/cloudflare/provision-machine.sh`, `VITE_ALLOWED_HOSTS`.
- Local path `~/projects/Trinity/archon`; Claude Code per-project state keyed to that
  path (`~/.claude/projects/-home-winadmin-projects-Trinity-archon/`).

## Architecture of the rename (phased, verification-gated)

The guiding rule: **rename and verify the central system first; only then touch
connected projects.** At no point are both ends broken simultaneously.

### Phase 0 — Safety net
- Full Supabase backup via the existing backup script.
- Clean git state on branch `rename`; commit this spec.

### Phase 1 — Rename the core repo
One coordinated change on the `rename` branch covering: DB migration SQL (table + RPC +
index renames), Python constants/package/MCP server name/env vars/routes, docker-compose,
`.env*`, Makefile, distribution artifacts (`cortexSetup.sh/.bat`, `cortex-scanner.py`,
`cortex-memory` plugin, `cortex-*` skills/commands, state-file names and JSON keys),
frontend (`cortex-ui/` dir, package, branding, storage keys), and docs. Registry rows in
the renamed `cortex_extensions` table get their extension names updated (SQL in the same
migration or a small script).

### Phase 2 — Verify locally (gate)
`docker compose up --build`; backend `uv run pytest` + frontend `vitest`; run the DB
migration; connect MCP with the new `"cortex"` key in this repo's `.mcp.json`; exercise
RAG search, projects/tasks, extension list via MCP tools; UI smoke test. Nothing external
is touched until this passes.

### Phase 3 — Connected-project migration script
New `cortex-migrate` script served by the backend (same pattern as the scanner). Per
machine it sweeps all known project roots and, per project:
1. Renames `.claude/archon-config.json` → `cortex-config.json`, `archon-state.json` →
   `cortex-state.json`, `archon-memory-buffer.jsonl` → `cortex-memory-buffer.jsonl`,
   rewriting internal keys (`archon_api_url` → `cortex_api_url`, etc.) while **preserving
   project_id, machine_id, and fingerprint** so nothing re-registers.
2. Rewrites `.mcp.json`: key `"archon"` → `"cortex"`, URL updated (new host for remote
   machines using the Cloudflare hostname).
3. Removes `.claude/skills/archon-*`, `.claude/commands/archon-*`,
   `.claude/plugins/archon-memory/`; downloads + installs the new `cortex-*` tarballs.
4. Updates `.gitignore` entries (removes archon names, adds cortex names).
5. Renames `.archon/` → `.cortex/`.
6. Once per machine: rewrites `~/.claude/settings.json` hook paths to the cortex-memory
   scripts; updates any global `~/.claude/archon-config.json`.
Idempotent: safe to re-run; skips already-migrated projects.

### Phase 4 — Outer identity
- GitHub: `gh api` rename to `trezero/cortex`; update `origin` remote; remove `upstream`
  remote; update `version.py` constants.
- Cloudflare: add `cortex.persalto.io` CNAME to tunnel `archon-persalto` (tunnel id
  unchanged; optionally rename the tunnel/Access app labels), update tunnel ingress
  hostname, Access app domain, `VITE_ALLOWED_HOSTS`, `provision-machine.sh`. Remove the
  old `archon.persalto.io` record after the fleet sweep (Phase 5) completes.
- Local folder: `mv ~/projects/Trinity/archon ~/projects/Trinity/cortex`; rename the
  Claude Code project-state dir `~/.claude/projects/-home-winadmin-projects-Trinity-archon`
  to the new path key so memory/settings follow; fix any absolute paths in local tooling.

### Phase 5 — Fleet sweep (gate per machine)
Run `cortex-migrate` on each machine: WIN-AI-PC WSL (this box), WIN-AI-PC Windows,
MacBookPro-M1, WhiteShark. Verification per machine: open one migrated project in Claude
Code, confirm `cortex` MCP tools load, session hooks fire, and LeaveOff Point loads.
Then retire `archon.persalto.io`.

## Error handling

- DB migration runs inside a transaction; on failure, nothing renamed. Backup taken in
  Phase 0 is the recovery path.
- `cortex-migrate` reports per-project success/failure lists (batch-processing rule:
  continue on per-project failure, log loudly, never leave a project half-renamed — each
  project's migration is ordered so the `.mcp.json` swap happens last, making "migrated"
  detectable and retries safe).
- No silent fallbacks: if the script can't reach the Cortex API, it fails fast.

## Testing

- Phase 2 gate is the primary regression net (full local stack + test suites + MCP
  round-trip on renamed tables).
- `cortex-migrate` gets a dry-run mode (`--dry-run` prints planned changes) and is first
  exercised against a scratch copy of one real project before the fleet sweep.

## Out of scope

- Any change to the new upstream Archon V2 repo (`~/projects/archonV2`).
- Compatibility shims, dual-name support, or backward-compatible aliases.
- Renaming Supabase project/infrastructure itself (only tables/functions inside it).
