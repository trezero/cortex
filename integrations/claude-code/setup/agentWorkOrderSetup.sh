#!/usr/bin/env bash
# Agent Work Orders Setup CLI — Interactive setup for the Agent Work Orders microservice
# Provides a dashboard, configuration wizard, migration helper, and service launcher.
set -euo pipefail

# ── Template placeholders (substituted by MCP server when served) ────────────
CORTEX_API_URL="${CORTEX_API_URL:-{{CORTEX_API_URL}}}"
CORTEX_MCP_URL="${CORTEX_MCP_URL:-{{CORTEX_MCP_URL}}}"

# Fall back to defaults if placeholders were not substituted (script run directly from repo)
# CORTEX_HOST, _SERVER_PORT, _MCP_PORT are resolved after ENV_FILE is located (below)
if [ "$CORTEX_API_URL" = "{{CORTEX_API_URL}}" ]; then
  _NEEDS_URL_FALLBACK=true
else
  _NEEDS_URL_FALLBACK=false
fi

# ── Resolve repo root by walking up to find docker-compose.yml ───────────────
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

# ── Resolve CORTEX_HOST and service ports from .env ─────────────────────────
_read_env() { grep "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'\'']\|["'\''"]$//g'; }
CORTEX_HOST="${CORTEX_HOST:-$(_read_env CORTEX_HOST)}"
CORTEX_HOST="${CORTEX_HOST:-localhost}"
_SERVER_PORT="${CORTEX_SERVER_PORT:-$(_read_env CORTEX_SERVER_PORT)}"
_SERVER_PORT="${_SERVER_PORT:-8181}"
_MCP_PORT="${CORTEX_MCP_PORT:-$(_read_env CORTEX_MCP_PORT)}"
_MCP_PORT="${_MCP_PORT:-8051}"
_WO_PORT="${AGENT_WORK_ORDERS_PORT:-$(_read_env AGENT_WORK_ORDERS_PORT)}"
_WO_PORT="${_WO_PORT:-8053}"

# Apply URL fallback now that CORTEX_HOST and ports are resolved
if [ "$_NEEDS_URL_FALLBACK" = "true" ]; then
  CORTEX_API_URL="http://${CORTEX_HOST}:${_SERVER_PORT}"
  CORTEX_MCP_URL="http://${CORTEX_HOST}:${_MCP_PORT}"
fi

# ── Color helpers (detect TTY, respect NO_COLOR) ────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
  C_RESET=$'\033[0m'
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_BLUE=$'\033[34m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_CYAN=$'\033[36m'
else
  C_RESET=""
  C_BOLD=""
  C_DIM=""
  C_BLUE=""
  C_GREEN=""
  C_YELLOW=""
  C_RED=""
  C_CYAN=""
fi

# ── UI helpers ───────────────────────────────────────────────────────────────

ui_success() {
  printf "  %s✓%s %s\n" "$C_GREEN" "$C_RESET" "$1"
}

ui_warn() {
  printf "  %s!%s %s\n" "$C_YELLOW" "$C_RESET" "$1"
}

ui_error() {
  printf "  %s✗%s %s\n" "$C_RED" "$C_RESET" "$1" >&2
}

ui_info() {
  printf "  %s%s%s\n" "$C_DIM" "$1" "$C_RESET"
}

ui_header() {
  printf "\n%s%s%s\n" "$C_BOLD$C_CYAN" "$1" "$C_RESET"
}

ask() {
  local prompt="$1"
  local default="${2:-}"
  local answer

  if [ -n "$default" ]; then
    printf "  %s%s%s [%s]: " "$C_BOLD" "$prompt" "$C_RESET" "$default" >&2
  else
    printf "  %s%s%s: " "$C_BOLD" "$prompt" "$C_RESET" >&2
  fi

  read -r answer || true
  printf "%s\n" "${answer:-$default}"
}

# ── .env helpers ─────────────────────────────────────────────────────────────

# Safe parse of .env value — only reads the .env file, never checks environment
_env_val() {
  local val
  val="$(grep "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  # Strip surrounding quotes (written by _env_set for special-char values)
  val="${val%\"}"; val="${val#\"}"
  val="${val%\'}"; val="${val#\'}"
  printf "%s" "$val"
}

# Check .env first, then fall back to shell environment
_env_or_shell_val() {
  local val=""
  val="$(_env_val "$1")"
  if [ -n "$val" ]; then
    printf "%s" "$val"
  else
    printf "%s" "${!1:-}"
  fi
}

# Safe .env writer — uses embedded Python for special-character handling
_env_set() {
  local key="$1"
  local val="$2"
  python3 - "$ENV_FILE" "$key" "$val" <<'PYEOF'
import sys, os, re
env_file, key, val = sys.argv[1], sys.argv[2], sys.argv[3]

lines = []
if os.path.isfile(env_file):
    with open(env_file, "r") as f:
        lines = f.readlines()

pattern = re.compile(rf"^{re.escape(key)}=")
found = False
new_lines = []
for line in lines:
    if pattern.match(line):
        # Wrap in double quotes if value contains special chars
        if any(c in val for c in " #$'\"\\!&|;`(){}[]<>"):
            new_lines.append(f'{key}="{val}"\n')
        else:
            new_lines.append(f"{key}={val}\n")
        found = True
    else:
        new_lines.append(line)

if not found:
    if any(c in val for c in " #$'\"\\!&|;`(){}[]<>"):
        new_lines.append(f'{key}="{val}"\n')
    else:
        new_lines.append(f"{key}={val}\n")

with open(env_file, "w") as f:
    f.writelines(new_lines)
PYEOF
}

# ── Status Dashboard Detection Functions ─────────────────────────────────────

# Check if a command exists, show name and version
check_dep() {
  local name="$1"
  local cmd="$2"
  local version_flag="${3:---version}"

  if command -v "$cmd" &>/dev/null; then
    local ver=""
    ver="$("$cmd" $version_flag 2>&1 | head -1)" || ver="installed"
    printf "    %s%-14s%s %s✓%s  %s\n" "$C_BOLD" "$name" "$C_RESET" "$C_GREEN" "$C_RESET" "$ver"
    return 0
  else
    printf "    %s%-14s%s %s✗  not found%s\n" "$C_BOLD" "$name" "$C_RESET" "$C_RED" "$C_RESET"
    return 1
  fi
}

# Check Python >= 3.12
check_python312() {
  if command -v python3 &>/dev/null; then
    local ok=""
    ok="$(python3 -c "import sys; print('yes' if sys.version_info >= (3, 12) else 'no')" 2>/dev/null)" || ok="no"
    if [ "$ok" = "yes" ]; then
      local ver=""
      ver="$(python3 --version 2>&1)" || ver=""
      printf "    %s%-14s%s %s✓%s  %s\n" "$C_BOLD" "Python 3.12+" "$C_RESET" "$C_GREEN" "$C_RESET" "$ver"
      return 0
    else
      local ver=""
      ver="$(python3 --version 2>&1)" || ver="unknown"
      printf "    %s%-14s%s %s✗  %s (need 3.12+)%s\n" "$C_BOLD" "Python 3.12+" "$C_RESET" "$C_RED" "$ver" "$C_RESET"
      return 1
    fi
  else
    printf "    %s%-14s%s %s✗  not found%s\n" "$C_BOLD" "Python 3.12+" "$C_RESET" "$C_RED" "$C_RESET"
    return 1
  fi
}

# Check Docker daemon — distinguish "not installed" vs "daemon not running"
check_docker_daemon() {
  if ! command -v docker &>/dev/null; then
    printf "    %s%-14s%s %s✗  not installed%s\n" "$C_BOLD" "Docker" "$C_RESET" "$C_RED" "$C_RESET"
    return 1
  fi
  if docker info &>/dev/null; then
    local ver=""
    ver="$(docker --version 2>&1 | head -1)" || ver="running"
    printf "    %s%-14s%s %s✓%s  %s\n" "$C_BOLD" "Docker" "$C_RESET" "$C_GREEN" "$C_RESET" "$ver"
    return 0
  else
    printf "    %s%-14s%s %s!  installed but daemon not running%s\n" "$C_BOLD" "Docker" "$C_RESET" "$C_YELLOW" "$C_RESET"
    return 1
  fi
}

# Check a config key from .env + environment, mask secrets
check_config() {
  local key="$1"
  local label="$2"
  local val=""
  val="$(_env_val "$key")"

  if [ -n "$val" ]; then
    # Mask sensitive values (KEY, TOKEN, SECRET, PASSWORD patterns)
    if echo "$key" | grep -qiE '(KEY|TOKEN|SECRET|PASSWORD)'; then
      printf "    %s%-30s%s %s✓%s  set\n" "$C_BOLD" "$label" "$C_RESET" "$C_GREEN" "$C_RESET"
    else
      printf "    %s%-30s%s %s✓%s  %s\n" "$C_BOLD" "$label" "$C_RESET" "$C_GREEN" "$C_RESET" "$val"
    fi
    return 0
  else
    printf "    %s%-30s%s %s✗  not set%s\n" "$C_BOLD" "$label" "$C_RESET" "$C_RED" "$C_RESET"
    return 1
  fi
}

# Check service health by curling an endpoint with 3s timeout
check_service() {
  local name="$1"
  local url="$2"
  local status=""
  status="$(curl -sf -m 3 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)" || status="000"

  if [ "$status" = "200" ]; then
    printf "    %s%-26s%s %s✓%s  healthy (%s)\n" "$C_BOLD" "$name" "$C_RESET" "$C_GREEN" "$C_RESET" "$url"
    return 0
  else
    printf "    %s%-26s%s %s✗  unreachable (%s)%s\n" "$C_BOLD" "$name" "$C_RESET" "$C_RED" "$url" "$C_RESET"
    return 1
  fi
}

# Check if a Supabase table exists via REST API
# Returns: 0 = exists (200), 1 = missing/error, 2 = skipped (no credentials)
check_db_table() {
  local table="$1"
  local supabase_url=""
  local supabase_key=""
  supabase_url="$(_env_val "SUPABASE_URL")"
  supabase_key="$(_env_val "SUPABASE_SERVICE_KEY")"

  if [ -z "$supabase_url" ] || [ -z "$supabase_key" ]; then
    printf "    %s%-36s%s %s-  skipped (no credentials)%s\n" "$C_BOLD" "$table" "$C_RESET" "$C_DIM" "$C_RESET"
    return 2
  fi

  local rest_url="${supabase_url}/rest/v1/${table}?select=*&limit=0"
  local http_code=""
  http_code="$(curl -sf -m 5 -o /dev/null -w "%{http_code}" \
    -H "apikey: ${supabase_key}" \
    -H "Authorization: Bearer ${supabase_key}" \
    "$rest_url" 2>/dev/null)" || http_code="000"

  if [ "$http_code" = "200" ]; then
    printf "    %s%-36s%s %s✓%s  exists\n" "$C_BOLD" "$table" "$C_RESET" "$C_GREEN" "$C_RESET"
    return 0
  else
    printf "    %s%-36s%s %s✗  missing (HTTP %s)%s\n" "$C_BOLD" "$table" "$C_RESET" "$C_RED" "$http_code" "$C_RESET"
    return 1
  fi
}

# ── Status Dashboard ─────────────────────────────────────────────────────────

show_dashboard() {
  printf "\n"
  printf "  %s╔══════════════════════════════════════════════════════╗%s\n" "$C_CYAN" "$C_RESET"
  printf "  %s║   Agent Work Orders — Status Dashboard              ║%s\n" "$C_BOLD$C_CYAN" "$C_RESET"
  printf "  %s╚══════════════════════════════════════════════════════╝%s\n" "$C_CYAN" "$C_RESET"

  # --- Dependencies ---
  ui_header "  Dependencies"
  check_docker_daemon || true
  check_dep "Claude CLI" "claude" "--version" || true
  check_dep "GitHub CLI" "gh" "--version" || true
  check_python312 || true
  check_dep "uv" "uv" "--version" || true
  check_dep "Git" "git" "--version" || true

  # --- Configuration ---
  ui_header "  Configuration"

  if [ -f "$ENV_FILE" ]; then
    printf "    %s%-30s%s %s✓%s  %s\n" "$C_BOLD" ".env file" "$C_RESET" "$C_GREEN" "$C_RESET" "$ENV_FILE"
  else
    printf "    %s%-30s%s %s✗  not found%s\n" "$C_BOLD" ".env file" "$C_RESET" "$C_RED" "$C_RESET"
  fi

  check_config "ENABLE_AGENT_WORK_ORDERS" "ENABLE_AGENT_WORK_ORDERS" || true
  check_config "STATE_STORAGE_TYPE" "STATE_STORAGE_TYPE" || true
  check_config "SUPABASE_URL" "SUPABASE_URL" || true
  check_config "SUPABASE_SERVICE_KEY" "SUPABASE_SERVICE_KEY" || true

  # Auth check: need at least one of ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
  # Check both .env and shell environment for auth variables
  local has_anthropic="" has_oauth=""
  has_anthropic="$(_env_or_shell_val "ANTHROPIC_API_KEY")"
  has_oauth="$(_env_or_shell_val "CLAUDE_CODE_OAUTH_TOKEN")"
  if [ -n "$has_anthropic" ] || [ -n "$has_oauth" ]; then
    local auth_method=""
    if [ -n "$has_anthropic" ] && [ -n "$has_oauth" ]; then
      auth_method="ANTHROPIC_API_KEY + OAUTH"
    elif [ -n "$has_anthropic" ]; then
      auth_method="ANTHROPIC_API_KEY"
    else
      auth_method="CLAUDE_CODE_OAUTH_TOKEN"
    fi
    printf "    %s%-30s%s %s✓%s  %s\n" "$C_BOLD" "Claude auth" "$C_RESET" "$C_GREEN" "$C_RESET" "$auth_method"
  else
    printf "    %s%-30s%s %s✗  need ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN%s\n" "$C_BOLD" "Claude auth" "$C_RESET" "$C_RED" "$C_RESET"
  fi

  check_config "GITHUB_PAT_TOKEN" "GITHUB_PAT_TOKEN" || true

  # --- Services ---
  ui_header "  Services"
  check_service "Cortex Server (:${_SERVER_PORT})" "http://${CORTEX_HOST}:${_SERVER_PORT}/health" || true
  check_service "Cortex MCP (:${_MCP_PORT})" "http://${CORTEX_HOST}:${_MCP_PORT}/health" || true
  check_service "Work Orders (:${_WO_PORT})" "http://${CORTEX_HOST}:${_WO_PORT}/health" || true

  # --- Database ---
  ui_header "  Database"

  local storage_type=""
  storage_type="$(_env_val "STATE_STORAGE_TYPE")"

  if [ "$storage_type" = "supabase" ]; then
    check_db_table "cortex_agent_work_orders" || true
    check_db_table "cortex_agent_work_order_steps" || true
  else
    printf "    %s%-36s%s %s-  skipped (STATE_STORAGE_TYPE=%s)%s\n" \
      "$C_BOLD" "cortex_agent_work_orders" "$C_RESET" "$C_DIM" "${storage_type:-memory}" "$C_RESET"
    printf "    %s%-36s%s %s-  skipped (STATE_STORAGE_TYPE=%s)%s\n" \
      "$C_BOLD" "cortex_agent_work_order_steps" "$C_RESET" "$C_DIM" "${storage_type:-memory}" "$C_RESET"
  fi

  check_db_table "cortex_configured_repositories" || true

  echo
}

# ── Menu Actions ─────────────────────────────────────────────────────────────

# Action 1: Configure .env
action_configure_env() {
  ui_header "Configure Environment"

  # Create .env from .env.example if missing
  if [ ! -f "$ENV_FILE" ]; then
    local example_file="$REPO_ROOT/python/.env.example"
    if [ -f "$example_file" ]; then
      cp "$example_file" "$ENV_FILE"
      ui_success "Created .env from python/.env.example"
    else
      touch "$ENV_FILE"
      ui_success "Created empty .env"
    fi
  else
    ui_info ".env already exists at $ENV_FILE"
  fi

  echo

  # ENABLE_AGENT_WORK_ORDERS
  local current=""
  current="$(_env_val "ENABLE_AGENT_WORK_ORDERS")"
  local val=""
  val="$(ask "Enable agent work orders (true/false)" "${current:-true}")"
  _env_set "ENABLE_AGENT_WORK_ORDERS" "$val"
  ui_success "ENABLE_AGENT_WORK_ORDERS=$val"
  echo

  # STATE_STORAGE_TYPE
  current="$(_env_val "STATE_STORAGE_TYPE")"
  printf "  %sState storage type:%s\n" "$C_BOLD" "$C_RESET"
  echo "    [1] memory   — In-memory (lost on restart, good for development)"
  echo "    [2] file     — File-based JSON (persists locally)"
  echo "    [3] supabase — PostgreSQL via Supabase (recommended for production)"
  echo
  local default_choice="1"
  if [ "$current" = "file" ]; then default_choice="2"; fi
  if [ "$current" = "supabase" ]; then default_choice="3"; fi

  local storage_choice=""
  while true; do
    storage_choice="$(ask "Storage type (1, 2, or 3)" "$default_choice")"
    case "$storage_choice" in
      1) _env_set "STATE_STORAGE_TYPE" "memory"; ui_success "STATE_STORAGE_TYPE=memory"; break ;;
      2) _env_set "STATE_STORAGE_TYPE" "file"; ui_success "STATE_STORAGE_TYPE=file"; break ;;
      3) _env_set "STATE_STORAGE_TYPE" "supabase"; ui_success "STATE_STORAGE_TYPE=supabase"; break ;;
      *) ui_warn "Please enter 1, 2, or 3." ;;
    esac
  done
  echo

  # Supabase credentials (if supabase chosen)
  if [ "$storage_choice" = "3" ]; then
    current="$(_env_val "SUPABASE_URL")"
    val="$(ask "Supabase URL" "${current:-}")"
    if [ -n "$val" ]; then
      _env_set "SUPABASE_URL" "$val"
      ui_success "SUPABASE_URL set"
    fi

    current="$(_env_val "SUPABASE_SERVICE_KEY")"
    val="$(ask "Supabase service key" "${current:-}")"
    if [ -n "$val" ]; then
      _env_set "SUPABASE_SERVICE_KEY" "$val"
      ui_success "SUPABASE_SERVICE_KEY set"
    fi
    echo
  fi

  # Claude auth
  printf "  %sClaude authentication (need at least one):%s\n" "$C_BOLD" "$C_RESET"
  current="$(_env_val "ANTHROPIC_API_KEY")"
  val="$(ask "Anthropic API key (Enter to skip)" "${current:-}")"
  if [ -n "$val" ]; then
    _env_set "ANTHROPIC_API_KEY" "$val"
    ui_success "ANTHROPIC_API_KEY set"
  fi

  current="$(_env_val "CLAUDE_CODE_OAUTH_TOKEN")"
  val="$(ask "Claude Code OAuth token (Enter to skip)" "${current:-}")"
  if [ -n "$val" ]; then
    _env_set "CLAUDE_CODE_OAUTH_TOKEN" "$val"
    ui_success "CLAUDE_CODE_OAUTH_TOKEN set"
  fi
  echo

  # GITHUB_PAT_TOKEN
  current="$(_env_val "GITHUB_PAT_TOKEN")"
  val="$(ask "GitHub personal access token" "${current:-}")"
  if [ -n "$val" ]; then
    _env_set "GITHUB_PAT_TOKEN" "$val"
    ui_success "GITHUB_PAT_TOKEN set"
  fi
  echo

  # SERVICE_DISCOVERY_MODE — auto-detect Docker
  local detected_mode="local"
  if docker info &>/dev/null && docker compose ps --services 2>/dev/null | grep -q "cortex-server"; then
    detected_mode="docker_compose"
  fi
  current="$(_env_val "SERVICE_DISCOVERY_MODE")"
  val="$(ask "Service discovery mode (local / docker_compose)" "${current:-$detected_mode}")"
  _env_set "SERVICE_DISCOVERY_MODE" "$val"
  ui_success "SERVICE_DISCOVERY_MODE=$val"
  echo

  ui_success "Configuration saved to $ENV_FILE"
  echo
}

# Action 2: Check dependencies
action_check_deps() {
  ui_header "Dependency Check"
  echo

  local missing=0

  check_docker_daemon || { missing=$((missing + 1)); true; }
  check_dep "Claude CLI" "claude" "--version" || { missing=$((missing + 1)); true; }
  check_dep "GitHub CLI" "gh" "--version" || { missing=$((missing + 1)); true; }
  check_python312 || { missing=$((missing + 1)); true; }
  check_dep "uv" "uv" "--version" || { missing=$((missing + 1)); true; }
  check_dep "Git" "git" "--version" || { missing=$((missing + 1)); true; }

  echo
  if [ "$missing" -gt 0 ]; then
    ui_warn "$missing dependency/dependencies missing. Install instructions:"
    echo
    if ! command -v docker &>/dev/null; then
      ui_info "Docker:      https://docs.docker.com/get-docker/"
    fi
    if ! command -v claude &>/dev/null; then
      ui_info "Claude CLI:  curl -fsSL https://claude.ai/install.sh | bash"
    fi
    if ! command -v gh &>/dev/null; then
      ui_info "GitHub CLI:  https://cli.github.com/"
    fi
    if ! command -v python3 &>/dev/null; then
      ui_info "Python 3.12: https://www.python.org/downloads/"
    fi
    if ! command -v uv &>/dev/null; then
      ui_info "uv:          curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    if ! command -v git &>/dev/null; then
      ui_info "Git:         https://git-scm.com/downloads"
    fi
    echo
    local recheck=""
    recheck="$(ask "Re-check after installing? (y/n)" "n")"
    if [ "$recheck" = "y" ] || [ "$recheck" = "Y" ]; then
      action_check_deps
    fi
  else
    ui_success "All dependencies installed."
  fi
  echo
}

# Action 3: Run database migrations
action_run_migrations() {
  ui_header "Database Migrations"
  echo

  local supabase_url="" supabase_key=""
  supabase_url="$(_env_val "SUPABASE_URL")"
  supabase_key="$(_env_val "SUPABASE_SERVICE_KEY")"

  if [ -z "$supabase_url" ] || [ -z "$supabase_key" ]; then
    ui_error "SUPABASE_URL and SUPABASE_SERVICE_KEY are required for migrations."
    ui_info "Run option [1] Configure environment first."
    echo
    return
  fi

  local storage_type=""
  storage_type="$(_env_val "STATE_STORAGE_TYPE")"

  local state_migration="$REPO_ROOT/migration/agent_work_orders_state.sql"
  local repo_migration="$REPO_ROOT/migration/agent_work_orders_repositories.sql"

  # --- Group 1: State tables (only for supabase storage) ---
  if [ "$storage_type" = "supabase" ]; then
    ui_info "Checking state tables (STATE_STORAGE_TYPE=supabase)..."
    local state_ok=true
    check_db_table "cortex_agent_work_orders" || state_ok=false
    check_db_table "cortex_agent_work_order_steps" || state_ok=false

    if [ "$state_ok" = "false" ]; then
      echo
      ui_warn "State tables need to be created."

      local postgres_url=""
      postgres_url="$(_env_val "POSTGRES_URL")"
      if command -v psql &>/dev/null && [ -n "$postgres_url" ]; then
        local run_psql=""
        run_psql="$(ask "Run migration with psql? (y/n)" "y")"
        if [ "$run_psql" = "y" ] || [ "$run_psql" = "Y" ]; then
          if [ -f "$state_migration" ]; then
            ui_info "Executing $state_migration..."
            if psql "$postgres_url" -f "$state_migration" 2>&1; then
              ui_success "State migration executed."
            else
              ui_error "psql execution failed. Run manually in Supabase SQL Editor."
            fi
          else
            ui_error "Migration file not found: $state_migration"
          fi
        fi
      else
        ui_info "Auto-execute not available (no psql or POSTGRES_URL)."
        if [ -f "$state_migration" ]; then
          ui_info "Migration file: $state_migration"
          ui_info "Copy and paste into Supabase SQL Editor to create tables."
        else
          ui_error "Migration file not found: $state_migration"
        fi
      fi
    else
      ui_success "State tables already exist."
    fi
    echo
  else
    ui_info "Skipping state tables (STATE_STORAGE_TYPE=${storage_type:-memory}, not supabase)."
    echo
  fi

  # --- Group 2: Repository table (always needed) ---
  ui_info "Checking repository configuration table..."
  local repo_ok=true
  check_db_table "cortex_configured_repositories" || repo_ok=false

  if [ "$repo_ok" = "false" ]; then
    echo
    ui_warn "Repository configuration table needs to be created."

    local postgres_url=""
    postgres_url="$(_env_val "POSTGRES_URL")"
    if command -v psql &>/dev/null && [ -n "$postgres_url" ]; then
      local run_psql=""
      run_psql="$(ask "Run migration with psql? (y/n)" "y")"
      if [ "$run_psql" = "y" ] || [ "$run_psql" = "Y" ]; then
        if [ -f "$repo_migration" ]; then
          ui_info "Executing $repo_migration..."
          if psql "$postgres_url" -f "$repo_migration" 2>&1; then
            ui_success "Repository migration executed."
          else
            ui_error "psql execution failed. Run manually in Supabase SQL Editor."
          fi
        else
          ui_error "Migration file not found: $repo_migration"
        fi
      fi
    else
      ui_info "Auto-execute not available (no psql or POSTGRES_URL)."
      if [ -f "$repo_migration" ]; then
        ui_info "Migration file: $repo_migration"
        ui_info "Copy and paste into Supabase SQL Editor to create table."
      else
        ui_error "Migration file not found: $repo_migration"
      fi
    fi
  else
    ui_success "Repository configuration table already exists."
  fi

  # --- Verification ---
  echo
  ui_info "Verifying tables after migration..."
  if [ "$storage_type" = "supabase" ]; then
    check_db_table "cortex_agent_work_orders" || true
    check_db_table "cortex_agent_work_order_steps" || true
  fi
  check_db_table "cortex_configured_repositories" || true
  echo
}

# Action 4: Start with Docker
action_start_docker() {
  ui_header "Start via Docker Compose"
  echo

  # Check Docker daemon
  if ! docker info &>/dev/null; then
    if ! command -v docker &>/dev/null; then
      ui_error "Docker is not installed."
    else
      ui_error "Docker daemon is not running. Start Docker and try again."
    fi
    echo
    return
  fi

  # Check port 8053
  local port_in_use=""
  if command -v lsof &>/dev/null; then
    port_in_use="$(lsof -i :8053 -sTCP:LISTEN -t 2>/dev/null | head -1)" || true
  elif command -v ss &>/dev/null; then
    port_in_use="$(ss -tlnp | grep ':8053 ' 2>/dev/null | head -1)" || true
  fi
  if [ -n "$port_in_use" ]; then
    ui_warn "Port 8053 is already in use."
    local proceed=""
    proceed="$(ask "Continue anyway? (y/n)" "n")"
    if [ "$proceed" != "y" ] && [ "$proceed" != "Y" ]; then
      echo
      return
    fi
  fi

  ui_info "Starting work-orders profile..."
  if (cd "$REPO_ROOT" && docker compose --profile work-orders up -d --build 2>&1); then
    ui_success "Docker containers started."
  else
    ui_error "docker compose failed. Check Docker logs for details."
    echo
    return
  fi

  # Poll health endpoint for 30s, tail logs in background for visibility
  echo
  ui_info "Waiting for service to become healthy..."
  trap 'kill "$log_pid" 2>/dev/null || true' INT TERM
  docker compose -f "$REPO_ROOT/docker-compose.yml" logs -f cortex-agent-work-orders --since 5s &
  local log_pid=$!
  local attempts=0
  local max_attempts=15
  while [ "$attempts" -lt "$max_attempts" ]; do
    local code=""
    code="$(curl -sf -m 3 -o /dev/null -w "%{http_code}" "http://${CORTEX_HOST}:${_WO_PORT}/health" 2>/dev/null)" || code="000"
    if [ "$code" = "200" ]; then
      kill "$log_pid" 2>/dev/null || true
      trap - INT TERM
      echo
      ui_success "Work Orders service is healthy at http://${CORTEX_HOST}:${_WO_PORT}"
      echo
      return
    fi
    printf "."
    sleep 2
    attempts=$((attempts + 1))
  done

  kill "$log_pid" 2>/dev/null || true
  trap - INT TERM
  echo
  ui_warn "Service did not become healthy within 30 seconds."
  ui_info "Check logs: docker compose logs -f cortex-agent-work-orders"
  echo
}

# Action 5: Start locally
action_start_local() {
  ui_header "Start Locally (uvicorn)"
  echo

  # Verify Python 3.12+
  if ! command -v python3 &>/dev/null; then
    ui_error "Python 3 is not installed."
    echo
    return
  fi

  local py_ok=""
  py_ok="$(python3 -c "import sys; print('yes' if sys.version_info >= (3, 12) else 'no')" 2>/dev/null)" || py_ok="no"
  if [ "$py_ok" != "yes" ]; then
    ui_error "Python 3.12+ is required. Current: $(python3 --version 2>&1)"
    echo
    return
  fi

  # Verify uv
  if ! command -v uv &>/dev/null; then
    ui_error "uv is not installed. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo
    return
  fi

  # Check port 8053
  local port_in_use=""
  if command -v lsof &>/dev/null; then
    port_in_use="$(lsof -i :8053 -sTCP:LISTEN -t 2>/dev/null | head -1)" || true
  elif command -v ss &>/dev/null; then
    port_in_use="$(ss -tlnp | grep ':8053 ' 2>/dev/null | head -1)" || true
  fi
  if [ -n "$port_in_use" ]; then
    ui_warn "Port 8053 is already in use."
    local proceed=""
    proceed="$(ask "Continue anyway? (y/n)" "n")"
    if [ "$proceed" != "y" ] && [ "$proceed" != "Y" ]; then
      echo
      return
    fi
  fi

  # Install dependencies (skip if .venv is up to date)
  if [ "$REPO_ROOT/python/pyproject.toml" -nt "$REPO_ROOT/python/.venv/" ] 2>/dev/null; then
    ui_info "Syncing dependencies..."
    if (cd "$REPO_ROOT/python" && uv sync --group all 2>&1); then
      ui_success "Dependencies installed."
    else
      ui_error "uv sync failed."
      echo
      return
    fi
  else
    ui_info "Dependencies up to date."
  fi

  # Load env vars safely — never source .env
  if [ -f "$ENV_FILE" ]; then
    ui_info "Loading environment from $ENV_FILE..."
    while IFS='=' read -r key value; do
      # Skip comments and empty lines
      case "$key" in
        \#*|"") continue ;;
      esac
      # Validate key is a valid env var name
      if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        continue
      fi
      # Strip surrounding quotes from value
      value="${value%\"}"
      value="${value#\"}"
      value="${value%\'}"
      value="${value#\'}"
      export "$key"="$value"
    done < "$ENV_FILE"
  fi

  # Force required env vars
  export SERVICE_DISCOVERY_MODE="local"
  export ENABLE_AGENT_WORK_ORDERS="true"

  echo
  ui_info "Starting uvicorn on port 8053..."
  ui_info "Press Ctrl+C to stop."
  echo

  # exec replaces this shell process with uvicorn
  cd "$REPO_ROOT/python"
  exec uv run python -m uvicorn src.agent_work_orders.server:app --port 8053 --reload
}

# Action 6: Verify setup
action_verify() {
  ui_header "Verification"
  echo

  show_dashboard

  # Summarize critical checks
  local issues=()

  if [ ! -f "$ENV_FILE" ]; then
    issues+=("1 - .env file missing (run option [1] to configure)")
  fi

  local enabled=""
  enabled="$(_env_val "ENABLE_AGENT_WORK_ORDERS")"
  if [ "$enabled" != "true" ]; then
    issues+=("1 - ENABLE_AGENT_WORK_ORDERS is not 'true' (run option [1])")
  fi

  local supabase_url="" supabase_key=""
  supabase_url="$(_env_val "SUPABASE_URL")"
  supabase_key="$(_env_val "SUPABASE_SERVICE_KEY")"
  if [ -z "$supabase_url" ] || [ -z "$supabase_key" ]; then
    issues+=("1 - Supabase credentials missing (run option [1])")
  fi

  local has_anthropic="" has_oauth=""
  has_anthropic="$(_env_or_shell_val "ANTHROPIC_API_KEY")"
  has_oauth="$(_env_or_shell_val "CLAUDE_CODE_OAUTH_TOKEN")"
  if [ -z "$has_anthropic" ] && [ -z "$has_oauth" ]; then
    issues+=("1 - Claude auth missing — set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN (run option [1])")
  fi

  local svc_code=""
  svc_code="$(curl -sf -m 3 -o /dev/null -w "%{http_code}" "http://${CORTEX_HOST}:${_WO_PORT}/health" 2>/dev/null)" || svc_code="000"
  if [ "$svc_code" != "200" ]; then
    issues+=("4/5 - Work Orders service not running (run option [4] or [5])")
  fi

  echo
  if [ ${#issues[@]} -eq 0 ]; then
    printf "  %s%sReady to create work orders!%s\n" "$C_BOLD" "$C_GREEN" "$C_RESET"
  else
    ui_warn "Issues found:"
    for issue in "${issues[@]}"; do
      printf "    %s→ Option [%s]%s\n" "$C_YELLOW" "$issue" "$C_RESET"
    done
  fi
  echo
}

# ── Menu ─────────────────────────────────────────────────────────────────────

show_menu() {
  printf "  %s%sActions:%s\n" "$C_BOLD" "$C_CYAN" "$C_RESET"
  echo "    [1] Configure environment (.env)"
  echo "    [2] Check dependencies"
  echo "    [3] Run database migrations"
  echo "    [4] Start with Docker Compose"
  echo "    [5] Start locally (uvicorn)"
  echo "    [6] Verify setup"
  echo "    [7] Refresh dashboard"
  echo "    [0] Exit"
  echo
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  # Require python3 for .env helpers
  if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required. Install Python 3 and re-run this script." >&2
    exit 1
  fi

  show_dashboard
  show_menu

  while true; do
    local choice=""
    choice="$(ask "Choose an action" "")"

    case "$choice" in
      1) action_configure_env; show_menu ;;
      2) action_check_deps; show_menu ;;
      3) action_run_migrations; show_menu ;;
      4) action_start_docker; show_menu ;;
      5) action_start_local ;;  # exec replaces process, no return
      6) action_verify; show_menu ;;
      7) show_dashboard; show_menu ;;
      0|q|Q|exit)
        echo
        ui_info "Goodbye."
        echo
        exit 0
        ;;
      "")
        show_menu
        ;;
      *)
        ui_warn "Invalid choice. Enter 0-7."
        ;;
    esac
  done
}

main "$@"
