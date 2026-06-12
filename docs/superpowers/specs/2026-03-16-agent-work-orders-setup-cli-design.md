# Agent Work Orders Setup CLI — Design Spec

## Overview

An interactive, menu-driven Bash setup utility (`agentWorkOrderSetup.sh`) that guides users through configuring, deploying, and verifying the Agent Work Orders microservice. The script detects current state and presents a comprehensive status dashboard before offering actions.

## Goals

- Let users go from zero to a running Agent Work Orders service through a single interactive CLI
- Detect what is already configured/running so users know where they stand
- Support both Docker and local deployment modes
- Handle database migrations (auto-execute via `psql` when available, guide user to SQL Editor otherwise)
- Follow the same conventions as the existing `cortexSetup.sh`

## File Location

`integrations/claude-code/setup/agentWorkOrderSetup.sh`

Discoverable via:
1. MCP server endpoint: `GET /cortex-setup/agent-work-orders-setup.sh` (with URL template substitution)
2. UI download card on the MCP/Setup page (alongside the existing cortexSetup.sh card)

## Architecture

### Script Structure

```
agentWorkOrderSetup.sh
├── Helpers (colors, ask, logging — same patterns as cortexSetup.sh)
├── Detection functions
│   ├── check_dependency(name, command, version_flag)
│   ├── check_env_var(var_name)
│   ├── check_service_health(name, url)
│   └── check_db_table(table_name)
├── Status dashboard (runs on launch + menu option 7)
├── Menu loop
│   ├── 1) Configure environment
│   ├── 2) Check/install dependencies
│   ├── 3) Run database migrations
│   ├── 4) Start service (Docker)
│   ├── 5) Start service (Local)
│   ├── 6) Verify full setup
│   ├── 7) Show status dashboard
│   └── 0) Exit
└── Action implementations
```

### Conventions (from cortexSetup.sh)

- Colored output with `✓`, `!`, `✗` indicators
- `ask "prompt" "default"` function for interactive input
- `set -e` for fail-fast
- `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` for relative path resolution
- `REPO_ROOT` resolved by walking up from `SCRIPT_DIR` to find `docker-compose.yml` — abort with clear message if not found
- Respect `NO_COLOR` env var and non-TTY environments
- Never display secrets — show "set" / "not set" only
- Parse `.env` safely with `grep`/`cut` — never `source` it (avoids side effects from special characters):
  ```bash
  _env_val() { grep -E "^${1}=" "$REPO_ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2-; }
  ```
- Update `.env` values with a Python one-liner for safe handling of special characters (Supabase keys contain `=`, `/`, `+`)

## Status Dashboard

Runs automatically on launch. Checks four categories:

### Dependencies
| Check | Method | Required For |
|-------|--------|-------------|
| Docker | `command -v docker` + `docker --version` + `docker info` (daemon running?) | Docker mode |
| Claude CLI | `command -v claude` + `claude --version` | Both modes |
| GitHub CLI | `command -v gh` + `gh --version` | Both modes (PR creation) |
| Python 3.12+ | `command -v python3` + version parse ≥ 3.12 | Local mode only |
| uv | `command -v uv` + `uv --version` | Local mode only |
| Git | `command -v git` + `git --version` | Both modes |

Dashboard marks Python/uv with `~` (not applicable) when user's chosen mode is Docker-only.

### Configuration
| Check | Method |
|-------|--------|
| `.env` file | File existence at `$REPO_ROOT/.env` |
| `ENABLE_AGENT_WORK_ORDERS` | Parse `.env`, check value = `true` |
| `STATE_STORAGE_TYPE` | Parse `.env`, show value |
| `SUPABASE_URL` | Parse `.env`, check non-empty |
| `SUPABASE_SERVICE_KEY` | Parse `.env`, check non-empty |
| `GITHUB_PAT_TOKEN` | Parse `.env` or env, check non-empty (mapped to `GH_TOKEN` in Docker) |
| `ANTHROPIC_API_KEY` | Parse `.env` or env, check non-empty |
| `CLAUDE_CODE_OAUTH_TOKEN` | Parse `.env` or env, shown as alternative to `ANTHROPIC_API_KEY` |

Note: The dashboard shows `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` — at least one must be set. The script uses `GITHUB_PAT_TOKEN` (matching `.env.example`); Docker maps this to `GH_TOKEN` for the `gh` CLI.

### Services
| Check | Method |
|-------|--------|
| Cortex Server (8181) | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8181/health` |
| Cortex MCP (8051) | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8051/health` |
| Work Orders (8053) | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8053/health` |

### Database (only if Supabase credentials available)
| Check | Method |
|-------|--------|
| `cortex_agent_work_orders` | Supabase REST API: `GET /rest/v1/cortex_agent_work_orders?select=agent_work_order_id&limit=0` with `apikey` and `Authorization: Bearer` headers. HTTP 200 = exists, 404 = missing |
| `cortex_agent_work_order_steps` | Same approach (`?select=id&limit=0`) |
| `cortex_configured_repositories` | Same approach — always needed for repo config, independent of `STATE_STORAGE_TYPE` |

Note: The state tables (`cortex_agent_work_orders`, `cortex_agent_work_order_steps`) are only needed when `STATE_STORAGE_TYPE=supabase`. The `cortex_configured_repositories` table is always needed for repository configuration. The dashboard annotates accordingly.

Dashboard output example:
```
═══════════════════════════════════════════════
  Agent Work Orders — Status Dashboard
═══════════════════════════════════════════════

  Dependencies
  ✓ Docker              v27.5.1
  ✓ Claude CLI          v1.0.12
  ✓ GitHub CLI          v2.65.0
  ✗ Python 3.12+        not found
  ✓ uv                  v0.6.1
  ✓ Git                 v2.43.0

  Configuration
  ✓ .env file                      exists
  ✓ ENABLE_AGENT_WORK_ORDERS       true
  ✓ STATE_STORAGE_TYPE             supabase
  ✓ SUPABASE_URL                   set
  ✓ SUPABASE_SERVICE_KEY           set
  ✓ ANTHROPIC_API_KEY               set
  ! GITHUB_PAT_TOKEN                not set

  Services
  ✓ Cortex Server       http://localhost:8181 (healthy)
  ✓ Cortex MCP          http://localhost:8051 (healthy)
  ✗ Work Orders         http://localhost:8053 (not responding)

  Database
  ✓ cortex_agent_work_orders       exists
  ✓ cortex_agent_work_order_steps  exists
  ✗ cortex_configured_repositories missing

═══════════════════════════════════════════════
```

## Menu Actions

### 1) Configure Environment (.env)

- If `.env` missing: copy from `.env.example` or create minimal file
- Walk through agent-work-orders-specific variables interactively:
  - `ENABLE_AGENT_WORK_ORDERS` (default: `true`)
  - `STATE_STORAGE_TYPE` (choice menu: memory / file / supabase)
  - If supabase: check `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`, prompt if missing
  - `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` (at least one required — explain: API key for direct billing, OAuth for subscription)
  - `GITHUB_PAT_TOKEN` (prompt if missing, explain it's needed for PR creation; Docker maps to `GH_TOKEN`)
  - `SERVICE_DISCOVERY_MODE` (auto-detect Docker vs local, confirm with user)
- Update `.env` values using Python one-liner for safe special-character handling — preserves all non-work-order settings
- If a variable already has a value, show current value as default

### 2) Check/Install Dependencies

- Run dependency checks from dashboard
- For missing items, print platform-appropriate install instructions:
  - Docker: link to install docs
  - Claude CLI: `curl -fsSL https://claude.ai/install.sh | bash`
  - GitHub CLI: detected OS install command
  - Python/uv: platform-appropriate instructions
- Offer to re-check after user installs

### 3) Run Database Migrations

- Requires `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` — abort with message if missing
- Check which tables exist (same as dashboard DB check)
- Two migration groups checked independently:
  - **State tables** (`cortex_agent_work_orders`, `cortex_agent_work_order_steps`) — file: `migration/agent_work_orders_state.sql`, needed when `STATE_STORAGE_TYPE=supabase`
  - **Repository table** (`cortex_configured_repositories`) — file: `migration/agent_work_orders_repositories.sql`, always needed
- For each missing group:
  - If `psql` is available and `POSTGRES_URL` is set (common for local Supabase): offer to auto-execute via `psql -f <migration_file>`
  - Otherwise: print the migration file path and instruct user to paste into Supabase SQL Editor
- Verify tables exist after migration
- Note: The Supabase REST API (PostgREST) cannot execute DDL — `psql` or SQL Editor are the only options

### 4) Start Service (Docker)

- Verify Docker daemon is running
- Run `docker compose --profile work-orders up -d --build`
- Tail logs briefly (`docker compose logs -f cortex-agent-work-orders --since 5s &` with timeout)
- Poll health endpoint with timeout (30s), report success/failure
- If port 8053 is already in use, report the PID holding it

### 5) Start Service (Local)

- Verify Python 3.12+ and uv are available
- `cd` to `python/` directory
- Run `uv sync --group all` if `pyproject.toml` is newer than `.venv/`
- Set `SERVICE_DISCOVERY_MODE=local` and `ENABLE_AGENT_WORK_ORDERS=true`
- Load env vars from `.env` via `export`
- `exec` into `uv run python -m uvicorn src.agent_work_orders.server:app --port 8053 --reload` — this replaces the script process (same pattern as `make agent-work-orders`), so the menu session ends
- Print a note before exec: "Starting service... press Ctrl+C to stop"

### 6) Verify Full Setup

- Run the full status dashboard
- If all checks pass: print "Ready to create work orders!"
- If any checks fail: list what's still needed with the menu option number that fixes it

### 7) Show Status Dashboard

- Re-run the dashboard (same as on launch)

### 0) Exit

- Clean exit

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No `.env` file | Option 1 creates one |
| Supabase credentials invalid | DB check fails with "Could not connect to Supabase. Check SUPABASE_URL and SUPABASE_SERVICE_KEY" |
| Port 8053 in use | Report PID via `lsof -i :8053` or `ss -tlnp` |
| Docker not installed | Distinguished from "installed but daemon not running" |
| Partial migrations | Each table checked independently, only missing ones get migrated |
| Script run from wrong directory | `SCRIPT_DIR` resolves repo root; abort if not found |

## MCP Server Endpoint

Add to `python/src/mcp_server/mcp_server.py`:

```python
@app.get("/cortex-setup/agent-work-orders-setup.sh")
async def get_agent_work_orders_setup_script():
    # Same pattern as existing get_setup_script()
    # Template substitution for {{CORTEX_API_URL}}, {{CORTEX_MCP_URL}}
    # Returns text/plain response
```

## UI Download Card

Add a second download card to the MCP/Setup page alongside the existing cortexSetup.sh card. Card content:
- Title: "Agent Work Orders Setup"
- Description: "Interactive CLI to configure, deploy, and verify the Agent Work Orders service"
- Download button pointing to `/cortex-setup/agent-work-orders-setup.sh`
- Run instruction: `bash agentWorkOrderSetup.sh`

## README Update

Add a new section to `python/src/agent_work_orders/README.md`:
- What the setup CLI does
- How to get it (UI download or direct path)
- How to run it
- Example dashboard output
- Description of each menu option

## Out of Scope

- Windows `.bat` equivalent (can be added later)
- Auto-installing dependencies (too platform-specific; provides instructions instead)
- Managing multiple simultaneous deployments
- Configuring Claude CLI model/turn settings (advanced; can be done via `.env` directly)
