# Agent Work Orders Setup CLI — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an interactive menu-driven Bash setup CLI that guides users through configuring, deploying, and verifying the Agent Work Orders microservice, with a comprehensive status dashboard.

**Architecture:** A single Bash script (`agentWorkOrderSetup.sh`) following the same conventions as the existing `cortexSetup.sh`. Served via an MCP server endpoint with URL template substitution. A UI download card alongside the existing setup download. README updated with setup CLI documentation.

**Tech Stack:** Bash, curl, Python 3 (for safe .env manipulation), FastAPI/Starlette (MCP endpoint), React/TypeScript (UI card)

**Spec:** `docs/superpowers/specs/2026-03-16-agent-work-orders-setup-cli-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `integrations/claude-code/setup/agentWorkOrderSetup.sh` | Create | The main setup CLI script |
| `python/src/mcp_server/mcp_server.py` | Modify | Add `/cortex-setup/agent-work-orders-setup.sh` endpoint |
| `cortex-ui/src/features/mcp/components/AgentWorkOrdersSetupDownload.tsx` | Create | UI download card component |
| `cortex-ui/src/features/mcp/components/index.ts` | Modify | Export new component |
| `cortex-ui/src/features/mcp/views/McpView.tsx` | Modify | Add new download card below existing one |
| `python/src/agent_work_orders/README.md` | Modify | Add setup CLI documentation section |

---

## Chunk 1: The Setup Script

### Task 1: Create script skeleton with helpers

**Files:**
- Create: `integrations/claude-code/setup/agentWorkOrderSetup.sh`

- [ ] **Step 1: Create the script with shebang, color helpers, and utility functions**

Create `integrations/claude-code/setup/agentWorkOrderSetup.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── Template placeholders (substituted by MCP server) ───────────────
CORTEX_API_URL="${CORTEX_API_URL:-{{CORTEX_API_URL}}}"
CORTEX_MCP_URL="${CORTEX_MCP_URL:-{{CORTEX_MCP_URL}}}"

# ── Resolve repo root ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
while [ "$REPO_ROOT" != "/" ] && [ ! -f "$REPO_ROOT/docker-compose.yml" ]; do
  REPO_ROOT="$(dirname "$REPO_ROOT")"
done
if [ ! -f "$REPO_ROOT/docker-compose.yml" ]; then
  echo "Error: Cannot find project root (no docker-compose.yml found)." >&2
  exit 1
fi

ENV_FILE="$REPO_ROOT/.env"

# ── Color helpers (same pattern as cortexSetup.sh) ──────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_CYAN=$'\033[36m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""
  C_BLUE=""; C_GREEN=""; C_YELLOW=""
  C_RED=""; C_CYAN=""
fi

# ── UI helpers ──────────────────────────────────────────────────────
ui_success() { printf "  ${C_GREEN}✓${C_RESET} %s\n" "$1"; }
ui_warn()    { printf "  ${C_YELLOW}!${C_RESET} %s\n" "$1"; }
ui_error()   { printf "  ${C_RED}✗${C_RESET} %s\n" "$1" >&2; }
ui_info()    { printf "  ${C_DIM}%s${C_RESET}\n" "$1"; }
ui_header()  { printf "\n${C_BOLD}${C_CYAN}%s${C_RESET}\n" "$1"; }

ask() {
  local prompt="$1" default="${2:-}"
  if [ -n "$default" ]; then
    printf "  ${C_BOLD}%s${C_RESET} [${C_DIM}%s${C_RESET}]: " "$prompt" "$default"
  else
    printf "  ${C_BOLD}%s${C_RESET}: " "$prompt"
  fi
  read -r answer || true
  printf "%s" "${answer:-$default}"
}

# ── .env helpers ────────────────────────────────────────────────────
_env_val() {
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-
}

_env_set() {
  local key="$1" val="$2"
  python3 - "$ENV_FILE" "$key" "$val" <<'PYEOF'
import sys
env_file, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
lines = []
found = False
try:
    with open(env_file, "r") as f:
        lines = f.readlines()
except FileNotFoundError:
    pass
with open(env_file, "w") as f:
    for line in lines:
        if line.startswith(f"{key}="):
            f.write(f"{key}={val}\n")
            found = True
        else:
            f.write(line)
    if not found:
        f.write(f"{key}={val}\n")
PYEOF
}
```

- [ ] **Step 2: Make script executable**

Run: `chmod +x integrations/claude-code/setup/agentWorkOrderSetup.sh`

- [ ] **Step 3: Commit skeleton**

```bash
git add integrations/claude-code/setup/agentWorkOrderSetup.sh
git commit -m "feat: add agent work orders setup CLI skeleton with helpers"
```

---

### Task 2: Add status dashboard

**Files:**
- Modify: `integrations/claude-code/setup/agentWorkOrderSetup.sh`

- [ ] **Step 1: Add dependency check functions**

Append to the script after the helpers:

```bash
# ── Dependency checks ───────────────────────────────────────────────
check_dep() {
  local name="$1" cmd="$2" vflag="${3:---version}"
  if ! command -v "$cmd" &>/dev/null; then
    printf "  ${C_RED}✗${C_RESET} %-20s %s\n" "$name" "not found"
    return 1
  fi
  local ver
  ver=$("$cmd" $vflag 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
  printf "  ${C_GREEN}✓${C_RESET} %-20s %s\n" "$name" "v${ver:-unknown}"
  return 0
}

check_python312() {
  if ! command -v python3 &>/dev/null; then
    printf "  ${C_RED}✗${C_RESET} %-20s %s\n" "Python 3.12+" "not found"
    return 1
  fi
  local ver major minor
  ver=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
  major="${ver%%.*}"; minor="${ver#*.}"
  if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
    printf "  ${C_GREEN}✓${C_RESET} %-20s %s\n" "Python 3.12+" "v${ver}"
    return 0
  else
    printf "  ${C_RED}✗${C_RESET} %-20s %s (need 3.12+)\n" "Python 3.12+" "v${ver}"
    return 1
  fi
}

check_docker_daemon() {
  if ! command -v docker &>/dev/null; then
    printf "  ${C_RED}✗${C_RESET} %-20s %s\n" "Docker" "not installed"
    return 1
  fi
  if ! docker info &>/dev/null 2>&1; then
    printf "  ${C_YELLOW}!${C_RESET} %-20s %s\n" "Docker" "installed but daemon not running"
    return 1
  fi
  local ver
  ver=$(docker --version 2>&1 | grep -oE '[0-9]+\.[0-9]+[.0-9]*' | head -1)
  printf "  ${C_GREEN}✓${C_RESET} %-20s %s\n" "Docker" "v${ver:-unknown}"
  return 0
}
```

- [ ] **Step 2: Add config check function**

```bash
# ── Configuration checks ────────────────────────────────────────────
check_config() {
  local key="$1" label="${2:-$1}"
  local val
  val=$(_env_val "$key")
  if [ -z "$val" ]; then
    val="${!key:-}"  # Check current environment
  fi
  if [ -n "$val" ]; then
    # Never print secrets — show value for non-sensitive, "set" for sensitive
    case "$key" in
      *KEY*|*TOKEN*|*SECRET*|*PASSWORD*)
        printf "  ${C_GREEN}✓${C_RESET} %-32s %s\n" "$label" "set"
        ;;
      *)
        printf "  ${C_GREEN}✓${C_RESET} %-32s %s\n" "$label" "$val"
        ;;
    esac
    return 0
  else
    printf "  ${C_YELLOW}!${C_RESET} %-32s %s\n" "$label" "not set"
    return 1
  fi
}
```

- [ ] **Step 3: Add service health check function**

```bash
# ── Service health checks ───────────────────────────────────────────
check_service() {
  local name="$1" url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null || echo "000")
  if [ "$code" = "200" ]; then
    printf "  ${C_GREEN}✓${C_RESET} %-20s %s (healthy)\n" "$name" "$url"
    return 0
  else
    printf "  ${C_RED}✗${C_RESET} %-20s %s (not responding)\n" "$name" "$url"
    return 1
  fi
}
```

- [ ] **Step 4: Add database table check function**

```bash
# ── Database checks ─────────────────────────────────────────────────
check_db_table() {
  local table="$1"
  local sb_url sb_key code
  sb_url=$(_env_val "SUPABASE_URL")
  sb_key=$(_env_val "SUPABASE_SERVICE_KEY")
  if [ -z "$sb_url" ] || [ -z "$sb_key" ]; then
    printf "  ${C_DIM}-${C_RESET} %-40s %s\n" "$table" "skipped (no Supabase credentials)"
    return 2
  fi
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
    "${sb_url}/rest/v1/${table}?select=*&limit=0" \
    -H "apikey: ${sb_key}" \
    -H "Authorization: Bearer ${sb_key}" 2>/dev/null || echo "000")
  if [ "$code" = "200" ]; then
    printf "  ${C_GREEN}✓${C_RESET} %-40s %s\n" "$table" "exists"
    return 0
  else
    printf "  ${C_RED}✗${C_RESET} %-40s %s\n" "$table" "missing"
    return 1
  fi
}
```

- [ ] **Step 5: Add the full dashboard function**

```bash
# ── Status Dashboard ────────────────────────────────────────────────
show_dashboard() {
  printf "\n${C_BOLD}${C_CYAN}═══════════════════════════════════════════════${C_RESET}\n"
  printf "${C_BOLD}${C_CYAN}  Agent Work Orders — Status Dashboard${C_RESET}\n"
  printf "${C_BOLD}${C_CYAN}═══════════════════════════════════════════════${C_RESET}\n"

  ui_header "  Dependencies"
  check_docker_daemon || true
  check_dep "Claude CLI" "claude" "--version" || true
  check_dep "GitHub CLI" "gh" "--version" || true
  check_python312 || true
  check_dep "uv" "uv" "--version" || true
  check_dep "Git" "git" "--version" || true

  ui_header "  Configuration"
  if [ -f "$ENV_FILE" ]; then
    printf "  ${C_GREEN}✓${C_RESET} %-32s %s\n" ".env file" "exists"
  else
    printf "  ${C_RED}✗${C_RESET} %-32s %s\n" ".env file" "missing"
  fi
  check_config "ENABLE_AGENT_WORK_ORDERS" || true
  check_config "STATE_STORAGE_TYPE" || true
  check_config "SUPABASE_URL" || true
  check_config "SUPABASE_SERVICE_KEY" || true
  # Auth: at least one of ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
  local has_auth=false
  if _env_val "ANTHROPIC_API_KEY" &>/dev/null && [ -n "$(_env_val "ANTHROPIC_API_KEY")" ]; then
    check_config "ANTHROPIC_API_KEY" || true
    has_auth=true
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    printf "  ${C_GREEN}✓${C_RESET} %-32s %s\n" "ANTHROPIC_API_KEY" "set (env)"
    has_auth=true
  fi
  if _env_val "CLAUDE_CODE_OAUTH_TOKEN" &>/dev/null && [ -n "$(_env_val "CLAUDE_CODE_OAUTH_TOKEN")" ]; then
    check_config "CLAUDE_CODE_OAUTH_TOKEN" || true
    has_auth=true
  elif [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    printf "  ${C_GREEN}✓${C_RESET} %-32s %s\n" "CLAUDE_CODE_OAUTH_TOKEN" "set (env)"
    has_auth=true
  fi
  if [ "$has_auth" = false ]; then
    printf "  ${C_YELLOW}!${C_RESET} %-32s %s\n" "Claude auth" "neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN set"
  fi
  check_config "GITHUB_PAT_TOKEN" || true

  ui_header "  Services"
  check_service "Cortex Server" "http://localhost:8181/health" || true
  check_service "Cortex MCP" "http://localhost:8051/health" || true
  check_service "Work Orders" "http://localhost:8053/health" || true

  ui_header "  Database"
  local st
  st=$(_env_val "STATE_STORAGE_TYPE")
  if [ "$st" = "supabase" ]; then
    check_db_table "cortex_agent_work_orders" || true
    check_db_table "cortex_agent_work_order_steps" || true
  else
    printf "  ${C_DIM}-${C_RESET} %-40s %s\n" "cortex_agent_work_orders" "skipped (storage=$st)"
    printf "  ${C_DIM}-${C_RESET} %-40s %s\n" "cortex_agent_work_order_steps" "skipped (storage=$st)"
  fi
  check_db_table "cortex_configured_repositories" || true

  printf "\n${C_BOLD}${C_CYAN}═══════════════════════════════════════════════${C_RESET}\n\n"
}
```

- [ ] **Step 6: Commit dashboard**

```bash
git add integrations/claude-code/setup/agentWorkOrderSetup.sh
git commit -m "feat: add status dashboard to agent work orders setup CLI"
```

---

### Task 3: Add menu loop and configure environment action

**Files:**
- Modify: `integrations/claude-code/setup/agentWorkOrderSetup.sh`

- [ ] **Step 1: Add the configure environment function**

Append to the script:

```bash
# ══════════════════════════════════════════════════════════════════════
# Menu Actions
# ══════════════════════════════════════════════════════════════════════

# ── 1) Configure Environment ────────────────────────────────────────
action_configure_env() {
  ui_header "Configure Environment (.env)"

  if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$REPO_ROOT/.env.example" ]; then
      ui_info "No .env file found. Copying from .env.example..."
      cp "$REPO_ROOT/.env.example" "$ENV_FILE"
      ui_success ".env created from .env.example"
    else
      ui_info "No .env file found. Creating minimal .env..."
      touch "$ENV_FILE"
      ui_success ".env created"
    fi
  else
    ui_success ".env file exists"
  fi

  echo ""
  ui_info "Configuring Agent Work Orders settings..."
  echo ""

  # ENABLE_AGENT_WORK_ORDERS
  local current
  current=$(_env_val "ENABLE_AGENT_WORK_ORDERS")
  local val
  val=$(ask "Enable Agent Work Orders" "${current:-true}")
  _env_set "ENABLE_AGENT_WORK_ORDERS" "$val"

  # STATE_STORAGE_TYPE
  echo ""
  current=$(_env_val "STATE_STORAGE_TYPE")
  ui_info "Storage options: memory (ephemeral), file (disk), supabase (production DB)"
  val=$(ask "State storage type" "${current:-supabase}")
  _env_set "STATE_STORAGE_TYPE" "$val"

  # Supabase credentials if needed
  if [ "$val" = "supabase" ]; then
    echo ""
    current=$(_env_val "SUPABASE_URL")
    if [ -z "$current" ]; then
      ui_warn "SUPABASE_URL is required for supabase storage"
      val=$(ask "Supabase URL" "")
      if [ -n "$val" ]; then _env_set "SUPABASE_URL" "$val"; fi
    else
      ui_success "SUPABASE_URL already set"
    fi

    current=$(_env_val "SUPABASE_SERVICE_KEY")
    if [ -z "$current" ]; then
      ui_warn "SUPABASE_SERVICE_KEY is required for supabase storage"
      val=$(ask "Supabase Service Key" "")
      if [ -n "$val" ]; then _env_set "SUPABASE_SERVICE_KEY" "$val"; fi
    else
      ui_success "SUPABASE_SERVICE_KEY already set"
    fi
  fi

  # Claude auth
  echo ""
  local has_anthropic has_oauth
  has_anthropic=$(_env_val "ANTHROPIC_API_KEY")
  has_oauth=$(_env_val "CLAUDE_CODE_OAUTH_TOKEN")
  if [ -z "$has_anthropic" ] && [ -z "$has_oauth" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    ui_warn "Claude authentication required (at least one):"
    ui_info "  ANTHROPIC_API_KEY - for direct API billing"
    ui_info "  CLAUDE_CODE_OAUTH_TOKEN - for subscription-based auth"
    val=$(ask "Anthropic API Key (leave blank to skip)" "")
    if [ -n "$val" ]; then _env_set "ANTHROPIC_API_KEY" "$val"; fi
  else
    ui_success "Claude authentication configured"
  fi

  # GITHUB_PAT_TOKEN
  echo ""
  current=$(_env_val "GITHUB_PAT_TOKEN")
  if [ -z "$current" ] && [ -z "${GITHUB_PAT_TOKEN:-}" ]; then
    ui_warn "GITHUB_PAT_TOKEN is needed for PR creation (Docker maps to GH_TOKEN)"
    val=$(ask "GitHub PAT Token (leave blank to skip)" "")
    if [ -n "$val" ]; then _env_set "GITHUB_PAT_TOKEN" "$val"; fi
  else
    ui_success "GITHUB_PAT_TOKEN already set"
  fi

  # SERVICE_DISCOVERY_MODE
  echo ""
  current=$(_env_val "SERVICE_DISCOVERY_MODE")
  if docker info &>/dev/null 2>&1; then
    ui_info "Docker detected — suggesting docker_compose mode"
    val=$(ask "Service discovery mode" "${current:-docker_compose}")
  else
    val=$(ask "Service discovery mode (local or docker_compose)" "${current:-local}")
  fi
  _env_set "SERVICE_DISCOVERY_MODE" "$val"

  echo ""
  ui_success "Environment configuration complete!"
}
```

- [ ] **Step 2: Add the menu loop and main entry point**

Append to the script:

```bash
# ── Menu ────────────────────────────────────────────────────────────
show_menu() {
  printf "${C_BOLD}  Select an option:${C_RESET}\n"
  echo ""
  echo "  1) Configure environment (.env)"
  echo "  2) Check / install dependencies"
  echo "  3) Run database migrations"
  echo "  4) Start service (Docker)"
  echo "  5) Start service (Local)"
  echo "  6) Verify full setup"
  echo "  7) Show status dashboard"
  echo "  0) Exit"
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────
main() {
  # python3 is required for _env_set helper
  if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required to run this setup script." >&2
    echo "Install Python 3: https://www.python.org/downloads/" >&2
    exit 1
  fi

  show_dashboard

  while true; do
    show_menu
    local choice
    choice=$(ask "Choice" "")
    echo ""

    case "$choice" in
      1) action_configure_env ;;
      2) action_check_deps ;;
      3) action_run_migrations ;;
      4) action_start_docker ;;
      5) action_start_local ;;
      6) action_verify ;;
      7) show_dashboard ;;
      0) ui_info "Goodbye!"; exit 0 ;;
      *) ui_warn "Invalid option. Please enter 0-7." ;;
    esac
    echo ""
  done
}

main "$@"
```

- [ ] **Step 3: Commit menu and configure action**

```bash
git add integrations/claude-code/setup/agentWorkOrderSetup.sh
git commit -m "feat: add menu loop and configure environment action"
```

---

### Task 4: Add dependency check, migration, start, and verify actions

**Files:**
- Modify: `integrations/claude-code/setup/agentWorkOrderSetup.sh`

- [ ] **Step 1: Add check dependencies action**

Insert before the menu function:

```bash
# ── 2) Check / Install Dependencies ─────────────────────────────────
action_check_deps() {
  ui_header "Dependency Check"

  local missing=0

  check_docker_daemon || missing=$((missing + 1))
  check_dep "Claude CLI" "claude" "--version" || missing=$((missing + 1))
  check_dep "GitHub CLI" "gh" "--version" || missing=$((missing + 1))
  check_python312 || missing=$((missing + 1))
  check_dep "uv" "uv" "--version" || missing=$((missing + 1))
  check_dep "Git" "git" "--version" || missing=$((missing + 1))

  if [ "$missing" -gt 0 ]; then
    echo ""
    ui_header "  Install Instructions"
    if ! command -v docker &>/dev/null; then
      ui_info "Docker: https://docs.docker.com/get-docker/"
    fi
    if ! command -v claude &>/dev/null; then
      ui_info "Claude CLI: curl -fsSL https://claude.ai/install.sh | bash"
    fi
    if ! command -v gh &>/dev/null; then
      ui_info "GitHub CLI: https://cli.github.com/manual/installation"
    fi
    if ! command -v python3 &>/dev/null; then
      ui_info "Python 3.12+: https://www.python.org/downloads/"
    fi
    if ! command -v uv &>/dev/null; then
      ui_info "uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    echo ""
    local recheck
    recheck=$(ask "Re-check after installing? (y/n)" "n")
    if [ "$recheck" = "y" ] || [ "$recheck" = "Y" ]; then
      action_check_deps
    fi
  else
    echo ""
    ui_success "All dependencies available!"
  fi
}
```

- [ ] **Step 2: Add database migration action**

```bash
# ── 3) Run Database Migrations ──────────────────────────────────────
action_run_migrations() {
  ui_header "Database Migrations"

  local sb_url sb_key
  sb_url=$(_env_val "SUPABASE_URL")
  sb_key=$(_env_val "SUPABASE_SERVICE_KEY")
  if [ -z "$sb_url" ] || [ -z "$sb_key" ]; then
    ui_error "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
    ui_info "Run option 1 (Configure environment) first."
    return 1
  fi

  local st
  st=$(_env_val "STATE_STORAGE_TYPE")
  local state_missing=false repo_missing=false

  # Check state tables (only needed for supabase storage)
  if [ "$st" = "supabase" ]; then
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
      "${sb_url}/rest/v1/cortex_agent_work_orders?select=*&limit=0" \
      -H "apikey: ${sb_key}" -H "Authorization: Bearer ${sb_key}" 2>/dev/null || echo "000")
    if [ "$code" != "200" ]; then
      state_missing=true
    fi
  fi

  # Check repositories table (always needed)
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
    "${sb_url}/rest/v1/cortex_configured_repositories?select=*&limit=0" \
    -H "apikey: ${sb_key}" -H "Authorization: Bearer ${sb_key}" 2>/dev/null || echo "000")
  if [ "$code" != "200" ]; then
    repo_missing=true
  fi

  if [ "$state_missing" = false ] && [ "$repo_missing" = false ]; then
    ui_success "All required tables exist!"
    return 0
  fi

  # Try psql if available
  local pg_url has_psql=false
  pg_url=$(_env_val "POSTGRES_URL")
  if [ -z "$pg_url" ]; then
    pg_url="${POSTGRES_URL:-}"
  fi
  if command -v psql &>/dev/null && [ -n "$pg_url" ]; then
    has_psql=true
  fi

  if [ "$state_missing" = true ]; then
    echo ""
    ui_warn "State tables missing (cortex_agent_work_orders, cortex_agent_work_order_steps)"
    local migration_file="$REPO_ROOT/migration/agent_work_orders_state.sql"
    if [ "$has_psql" = true ]; then
      local run_it
      run_it=$(ask "Run migration via psql? (y/n)" "y")
      if [ "$run_it" = "y" ] || [ "$run_it" = "Y" ]; then
        ui_info "Executing ${migration_file}..."
        if psql "$pg_url" -f "$migration_file" 2>&1; then
          ui_success "State tables created!"
        else
          ui_error "Migration failed. Please run manually in Supabase SQL Editor."
          ui_info "File: $migration_file"
        fi
      fi
    else
      ui_info "Auto-migration requires psql + POSTGRES_URL in .env"
      ui_info "Please paste the following file into the Supabase SQL Editor:"
      printf "  ${C_BOLD}%s${C_RESET}\n" "$migration_file"
    fi
  fi

  if [ "$repo_missing" = true ]; then
    echo ""
    ui_warn "Repository table missing (cortex_configured_repositories)"
    local migration_file="$REPO_ROOT/migration/agent_work_orders_repositories.sql"
    if [ "$has_psql" = true ]; then
      local run_it
      run_it=$(ask "Run migration via psql? (y/n)" "y")
      if [ "$run_it" = "y" ] || [ "$run_it" = "Y" ]; then
        ui_info "Executing ${migration_file}..."
        if psql "$pg_url" -f "$migration_file" 2>&1; then
          ui_success "Repository table created!"
        else
          ui_error "Migration failed. Please run manually in Supabase SQL Editor."
          ui_info "File: $migration_file"
        fi
      fi
    else
      ui_info "Auto-migration requires psql + POSTGRES_URL in .env"
      ui_info "Please paste the following file into the Supabase SQL Editor:"
      printf "  ${C_BOLD}%s${C_RESET}\n" "$migration_file"
    fi
  fi

  # Verify
  echo ""
  local verify
  verify=$(ask "Verify tables now? (y/n)" "y")
  if [ "$verify" = "y" ] || [ "$verify" = "Y" ]; then
    ui_header "  Verifying..."
    check_db_table "cortex_agent_work_orders" || true
    check_db_table "cortex_agent_work_order_steps" || true
    check_db_table "cortex_configured_repositories" || true
  fi
}
```

- [ ] **Step 3: Add start Docker action**

```bash
# ── 4) Start Service (Docker) ───────────────────────────────────────
action_start_docker() {
  ui_header "Start Service (Docker)"

  if ! docker info &>/dev/null 2>&1; then
    ui_error "Docker daemon is not running. Please start Docker first."
    return 1
  fi

  # Check port
  if command -v lsof &>/dev/null; then
    local pid
    pid=$(lsof -ti :8053 2>/dev/null || true)
    if [ -n "$pid" ]; then
      ui_warn "Port 8053 is already in use (PID: $pid)"
      local cont
      cont=$(ask "Continue anyway? (y/n)" "n")
      if [ "$cont" != "y" ] && [ "$cont" != "Y" ]; then return 1; fi
    fi
  fi

  ui_info "Running: docker compose --profile work-orders up -d --build"
  (cd "$REPO_ROOT" && docker compose --profile work-orders up -d --build)

  echo ""
  ui_info "Waiting for health check..."
  local attempts=0 max_attempts=15
  while [ $attempts -lt $max_attempts ]; do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 \
      "http://localhost:8053/health" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
      ui_success "Agent Work Orders service is healthy!"
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done

  ui_warn "Service did not become healthy within 30s"
  ui_info "Check logs: docker compose logs -f cortex-agent-work-orders"
}
```

- [ ] **Step 4: Add start local action**

```bash
# ── 5) Start Service (Local) ────────────────────────────────────────
action_start_local() {
  ui_header "Start Service (Local)"

  if ! command -v python3 &>/dev/null; then
    ui_error "Python 3 is required for local mode."
    return 1
  fi
  if ! command -v uv &>/dev/null; then
    ui_error "uv is required for local mode. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 1
  fi

  # Check port
  if command -v lsof &>/dev/null; then
    local pid
    pid=$(lsof -ti :8053 2>/dev/null || true)
    if [ -n "$pid" ]; then
      ui_warn "Port 8053 is already in use (PID: $pid)"
      return 1
    fi
  fi

  local pydir="$REPO_ROOT/python"
  if [ ! -f "$pydir/pyproject.toml" ]; then
    ui_error "Cannot find python/pyproject.toml"
    return 1
  fi

  ui_info "Syncing dependencies..."
  (cd "$pydir" && uv sync --group all)

  echo ""
  ui_info "Starting service on port 8053... (Ctrl+C to stop)"
  ui_info "This will replace the setup script process."
  echo ""

  # Load env vars safely (never source .env directly — special chars break it)
  cd "$pydir"
  if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key val; do
      # Skip comments and blank lines
      case "$key" in \#*|"") continue ;; esac
      export "$key=$val"
    done < "$ENV_FILE"
  fi
  export SERVICE_DISCOVERY_MODE=local
  export ENABLE_AGENT_WORK_ORDERS=true
  exec uv run python -m uvicorn src.agent_work_orders.server:app --port 8053 --reload
}
```

- [ ] **Step 5: Add verify action**

```bash
# ── 6) Verify Full Setup ────────────────────────────────────────────
action_verify() {
  ui_header "Full Setup Verification"

  show_dashboard

  # Summarize readiness
  local issues=0

  # Check critical items
  if [ ! -f "$ENV_FILE" ]; then issues=$((issues + 1)); fi
  if [ "$(_env_val "ENABLE_AGENT_WORK_ORDERS")" != "true" ]; then issues=$((issues + 1)); fi

  local sb_url sb_key
  sb_url=$(_env_val "SUPABASE_URL")
  sb_key=$(_env_val "SUPABASE_SERVICE_KEY")
  if [ -z "$sb_url" ] || [ -z "$sb_key" ]; then issues=$((issues + 1)); fi

  local wo_code
  wo_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 \
    "http://localhost:8053/health" 2>/dev/null || echo "000")
  if [ "$wo_code" != "200" ]; then issues=$((issues + 1)); fi

  echo ""
  if [ "$issues" -eq 0 ]; then
    printf "  ${C_GREEN}${C_BOLD}✓ Ready to create work orders!${C_RESET}\n"
  else
    printf "  ${C_YELLOW}${C_BOLD}! Some items need attention:${C_RESET}\n"
    if [ ! -f "$ENV_FILE" ] || [ "$(_env_val "ENABLE_AGENT_WORK_ORDERS")" != "true" ]; then
      ui_info "  → Run option 1 to configure environment"
    fi
    if [ -z "$sb_url" ] || [ -z "$sb_key" ]; then
      ui_info "  → Run option 1 to set Supabase credentials"
    fi
    if [ "$wo_code" != "200" ]; then
      ui_info "  → Run option 4 (Docker) or 5 (Local) to start the service"
    fi
  fi
}
```

- [ ] **Step 6: Commit all actions**

```bash
git add integrations/claude-code/setup/agentWorkOrderSetup.sh
git commit -m "feat: add all menu actions (deps, migrations, start, verify)"
```

---

## Chunk 2: MCP Endpoint, UI Card, and README

### Task 5: Add MCP server endpoint to serve the setup script

**Files:**
- Modify: `python/src/mcp_server/mcp_server.py`

- [ ] **Step 1: Read the MCP server file to find the exact location of existing setup endpoints**

Read `python/src/mcp_server/mcp_server.py` and find:
- The `_render_setup_sh()` function
- The `http_cortex_setup_sh()` endpoint
- The route registration block where `mcp.custom_route("/cortex-setup.sh", ...)` is called

- [ ] **Step 2: Add render function for agent work orders setup script**

Add a new function next to the existing `_render_setup_sh()`:

```python
def _render_agent_work_orders_setup_sh(api_url: str, mcp_url: str) -> str:
    """Read agentWorkOrderSetup.sh template, substitute placeholders, return."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "setup" / "agentWorkOrderSetup.sh"
        if candidate.exists():
            content = candidate.read_text()
            content = content.replace("{{CORTEX_API_URL}}", api_url)
            content = content.replace("{{CORTEX_MCP_URL}}", mcp_url)
            return content
    raise FileNotFoundError("agentWorkOrderSetup.sh template not found")
```

- [ ] **Step 3: Add the HTTP endpoint handler**

Add next to the existing `http_cortex_setup_sh`:

```python
async def http_agent_work_orders_setup_sh(request: Request) -> PlainTextResponse:
    """Serve agentWorkOrderSetup.sh with URLs baked in."""
    api_url, mcp_url = _get_setup_urls(request)
    script = _render_agent_work_orders_setup_sh(api_url, mcp_url)
    return PlainTextResponse(
        script,
        headers={"Content-Disposition": 'attachment; filename="agentWorkOrderSetup.sh"'},
    )
```

- [ ] **Step 4: Register the route**

Add to the route registration block (next to the existing `/cortex-setup.sh` route):

```python
mcp.custom_route("/cortex-setup/agent-work-orders-setup.sh", methods=["GET"])(http_agent_work_orders_setup_sh)
```

- [ ] **Step 5: Commit MCP endpoint**

```bash
git add python/src/mcp_server/mcp_server.py
git commit -m "feat: add MCP endpoint for agent work orders setup script"
```

---

### Task 6: Add UI download card component

**Files:**
- Create: `cortex-ui/src/features/mcp/components/AgentWorkOrdersSetupDownload.tsx`
- Modify: `cortex-ui/src/features/mcp/components/index.ts`
- Modify: `cortex-ui/src/features/mcp/views/McpView.tsx`

- [ ] **Step 1: Create the download card component**

Create `cortex-ui/src/features/mcp/components/AgentWorkOrdersSetupDownload.tsx`:

```tsx
import { Download, Wrench } from "lucide-react";

export function AgentWorkOrdersSetupDownload() {
  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
          <Wrench className="w-5 h-5 text-emerald-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold text-white mb-1">Agent Work Orders Setup</h2>
          <p className="text-sm text-zinc-400 mb-4">
            Interactive CLI to configure, deploy, and verify the Agent Work Orders service.
            Includes a status dashboard, environment setup, database migrations, and service
            management.
          </p>
          <div className="flex flex-wrap gap-3 mb-4">
            <a
              href="/cortex-setup/agent-work-orders-setup.sh"
              download="agentWorkOrderSetup.sh"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm font-medium hover:bg-emerald-500/20 transition-colors"
            >
              <Download className="w-4 h-4" />
              agentWorkOrderSetup.sh
              <span className="text-xs text-zinc-500">Mac / Linux</span>
            </a>
          </div>
          <p className="text-xs text-zinc-500">
            Save to your project root and run{" "}
            <code className="text-emerald-400">bash agentWorkOrderSetup.sh</code> to get started.
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Export the component from barrel file**

Add to `cortex-ui/src/features/mcp/components/index.ts`:

```typescript
export * from "./AgentWorkOrdersSetupDownload";
```

- [ ] **Step 3: Add the card to McpView**

In `cortex-ui/src/features/mcp/views/McpView.tsx`:
1. Add `AgentWorkOrdersSetupDownload` to the import from `"../components"`
2. Update `useStaggeredEntrance([1, 2, 3, 4], 0.15)` to `useStaggeredEntrance([1, 2, 3, 4, 5], 0.15)` to account for the new card
3. Insert after the existing `<CortexSetupDownload />` block (after line 92):

```tsx
      {/* Agent Work Orders Setup */}
      <motion.div variants={itemVariants}>
        <AgentWorkOrdersSetupDownload />
      </motion.div>
```

- [ ] **Step 4: Commit UI card**

```bash
git add cortex-ui/src/features/mcp/components/AgentWorkOrdersSetupDownload.tsx \
       cortex-ui/src/features/mcp/components/index.ts \
       cortex-ui/src/features/mcp/views/McpView.tsx
git commit -m "feat: add Agent Work Orders setup download card to MCP page"
```

---

### Task 7: Update README with setup CLI documentation

**Files:**
- Modify: `python/src/agent_work_orders/README.md`

- [ ] **Step 1: Read the current README to find the right insertion point**

Read `python/src/agent_work_orders/README.md` and identify where to insert the new section. Best placement: after the "Quick Start" / running sections and before "Configuration".

- [ ] **Step 2: Add setup CLI section**

Insert the following section at the identified location:

```markdown
## Setup CLI

An interactive setup utility that guides you through the full Agent Work Orders configuration.

### Getting the Script

**From the UI:** Download from the MCP Status Dashboard page → "Agent Work Orders Setup" card.

**From the repo:** The script lives at `integrations/claude-code/setup/agentWorkOrderSetup.sh`.

### Running

```bash
bash agentWorkOrderSetup.sh
```

The script automatically detects your current setup state and shows a status dashboard:

```
═══════════════════════════════════════════════
  Agent Work Orders — Status Dashboard
═══════════════════════════════════════════════

  Dependencies
  ✓ Docker              v27.5.1
  ✓ Claude CLI          v1.0.12
  ✓ GitHub CLI          v2.65.0
  ✓ Python 3.12+        v3.12.3
  ✓ uv                  v0.6.1
  ✓ Git                 v2.43.0

  Configuration
  ✓ .env file                      exists
  ✓ ENABLE_AGENT_WORK_ORDERS       true
  ✓ STATE_STORAGE_TYPE             supabase
  ✓ SUPABASE_URL                   set
  ✓ SUPABASE_SERVICE_KEY           set
  ✓ ANTHROPIC_API_KEY              set
  ! GITHUB_PAT_TOKEN               not set

  Services
  ✓ Cortex Server       http://localhost:8181 (healthy)
  ✓ Cortex MCP          http://localhost:8051 (healthy)
  ✗ Work Orders         http://localhost:8053 (not responding)

  Database
  ✓ cortex_agent_work_orders       exists
  ✓ cortex_agent_work_order_steps  exists
  ✓ cortex_configured_repositories exists

═══════════════════════════════════════════════
```

### Menu Options

| Option | Description |
|--------|-------------|
| **1) Configure environment** | Interactive `.env` setup for all agent work order variables |
| **2) Check dependencies** | Verify all required tools are installed with install instructions |
| **3) Run migrations** | Check and create missing database tables (via `psql` or SQL Editor guidance) |
| **4) Start (Docker)** | Build and start via `docker compose --profile work-orders` |
| **5) Start (Local)** | Start locally with `uv run uvicorn` on port 8053 |
| **6) Verify setup** | Full dashboard + readiness assessment |
| **7) Status dashboard** | Re-display the status dashboard |
```

- [ ] **Step 3: Commit README update**

```bash
git add python/src/agent_work_orders/README.md
git commit -m "docs: add setup CLI section to Agent Work Orders README"
```
