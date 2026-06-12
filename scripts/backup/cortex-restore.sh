#!/usr/bin/env bash
# cortex-restore.sh — Restore Cortex-specific data on the backup server
# Restores only cortex_* tables into the existing Supabase instance.
# Does NOT touch the localSupabase .env or restart Supabase — assumes it's already running.
#
# Usage:
#   ./cortex-restore.sh              # Restore from "latest" backup
#   ./cortex-restore.sh 2026-03-18_120000  # Restore from specific backup

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────
BACKUP_BASE="$HOME/cortex-backups"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_DIR="${CORTEX_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
GLOBAL_CLAUDE_DIR="/home/winadmin/.claude"
# Claude Code project memory uses the absolute path with slashes replaced by dashes
CORTEX_PATH_SLUG="$(echo "$CORTEX_DIR" | sed 's|^/||; s|/|-|g')"
MEMORY_DIR="$GLOBAL_CLAUDE_DIR/projects/-${CORTEX_PATH_SLUG}/memory"
DB_CONTAINER="supabase-db"

# Determine which backup to restore
BACKUP_NAME="${1:-latest}"
if [[ "$BACKUP_NAME" == "latest" ]]; then
    if [[ ! -L "$BACKUP_BASE/latest" ]]; then
        echo "ERROR: No 'latest' symlink found in $BACKUP_BASE" >&2
        exit 1
    fi
    BACKUP_DIR=$(readlink -f "$BACKUP_BASE/latest")
    BACKUP_NAME=$(basename "$BACKUP_DIR")
else
    BACKUP_DIR="$BACKUP_BASE/$BACKUP_NAME"
fi

echo "============================================"
echo " Cortex Restore: $BACKUP_NAME"
echo " CORTEX_DIR: $CORTEX_DIR"
echo "============================================"
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 1: Validate backup
# ──────────────────────────────────────────────────────────────────────
echo "[1/7] Validating backup..."

if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "ERROR: Backup directory not found: $BACKUP_DIR" >&2
    exit 1
fi

MISSING=""
[[ ! -f "$BACKUP_DIR/cortex.dump" ]] && MISSING="$MISSING cortex.dump"
[[ ! -f "$BACKUP_DIR/env/cortex.env" ]] && MISSING="$MISSING env/cortex.env"

if [[ -n "$MISSING" ]]; then
    echo "ERROR: Missing critical files in backup:$MISSING" >&2
    exit 1
fi

DUMP_SIZE=$(stat -c%s "$BACKUP_DIR/cortex.dump")
DUMP_SIZE_MB=$((DUMP_SIZE / 1024 / 1024))
echo "  Backup valid: cortex.dump (${DUMP_SIZE_MB} MB), env files present"

# ──────────────────────────────────────────────────────────────────────
# Step 2: Place Cortex .env files (NOT localSupabase — it has its own)
# ──────────────────────────────────────────────────────────────────────
echo "[2/7] Placing Cortex .env files..."

mkdir -p "$CORTEX_DIR"
cp "$BACKUP_DIR/env/cortex.env" "$CORTEX_DIR/.env"
echo "  $CORTEX_DIR/.env"

if [[ -f "$BACKUP_DIR/env/postmanskill.env" ]]; then
    mkdir -p "$CORTEX_DIR/postmanSkill"
    cp "$BACKUP_DIR/env/postmanskill.env" "$CORTEX_DIR/postmanSkill/.env"
    echo "  $CORTEX_DIR/postmanSkill/.env"
fi

# Check for host.docker.internal — may need adjustment on native Docker
if grep -q 'host.docker.internal' "$CORTEX_DIR/.env" 2>/dev/null; then
    if ! docker info 2>/dev/null | grep -q "Docker Desktop"; then
        echo "  WARNING: .env references host.docker.internal. On native Docker, you may need"
        echo "           to update SUPABASE_URL to use the host's actual IP or localhost"
    fi
fi

echo "  NOTE: localSupabase .env was NOT touched (backup server has its own Supabase config)"

# ──────────────────────────────────────────────────────────────────────
# Step 3: Restore Claude state
# ──────────────────────────────────────────────────────────────────────
echo "[3/7] Restoring Claude state..."

CLAUDE_STATE_DIR="$BACKUP_DIR/claude-state"

if [[ -d "$CLAUDE_STATE_DIR" ]]; then
    mkdir -p "$CORTEX_DIR/.claude"
    for f in cortex-state.json cortex-config.json cortex-memory-buffer.jsonl settings.local.json; do
        if [[ -f "$CLAUDE_STATE_DIR/$f" ]]; then
            cp "$CLAUDE_STATE_DIR/$f" "$CORTEX_DIR/.claude/"
            echo "  .claude/$f"
        fi
    done

    for d in skills commands agents; do
        if [[ -d "$CLAUDE_STATE_DIR/$d" ]]; then
            rm -rf "$CORTEX_DIR/.claude/$d"
            cp -r "$CLAUDE_STATE_DIR/$d" "$CORTEX_DIR/.claude/"
            echo "  .claude/$d/"
        fi
    done

    if [[ -d "$CLAUDE_STATE_DIR/plugins" ]]; then
        mkdir -p "$CORTEX_DIR/.claude/plugins"
        rsync -a --exclude='.venv' "$CLAUDE_STATE_DIR/plugins/" "$CORTEX_DIR/.claude/plugins/"
        echo "  .claude/plugins/ (excluding .venv)"
    fi

    if [[ -f "$CLAUDE_STATE_DIR/global-settings.json" ]]; then
        mkdir -p "$GLOBAL_CLAUDE_DIR"
        cp "$CLAUDE_STATE_DIR/global-settings.json" "$GLOBAL_CLAUDE_DIR/settings.json"
        echo "  ~/.claude/settings.json"
    fi

    if [[ -d "$CLAUDE_STATE_DIR/memory" ]]; then
        mkdir -p "$MEMORY_DIR"
        cp -r "$CLAUDE_STATE_DIR/memory/"* "$MEMORY_DIR/" 2>/dev/null || true
        echo "  auto-memory -> $MEMORY_DIR"
    fi
else
    echo "  No claude-state directory in backup (skipped)"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 4: Verify Supabase is running (do NOT start/restart it)
# ──────────────────────────────────────────────────────────────────────
echo "[4/7] Checking Supabase..."

STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$DB_CONTAINER" 2>/dev/null || echo "not_found")
if [[ "$STATUS" == "healthy" ]]; then
    echo "  $DB_CONTAINER is healthy"
else
    echo "  ERROR: $DB_CONTAINER is not healthy (status: $STATUS)" >&2
    echo "  Supabase must be running before restore. Start it with:" >&2
    echo "    cd /home/winadmin/projects/localSupabase && docker compose up -d" >&2
    exit 1
fi

# Verify pgvector extension is available (needed for cortex_crawled_pages embeddings)
HAS_VECTOR=$(docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c \
    "SELECT 1 FROM pg_extension WHERE extname='vector';" 2>/dev/null || echo "0")
if [[ "$HAS_VECTOR" != "1" ]]; then
    echo "  Enabling pgvector extension..."
    docker exec "$DB_CONTAINER" psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null
fi
echo "  pgvector: available"

# ──────────────────────────────────────────────────────────────────────
# Step 5: Restore cortex_* tables
# ──────────────────────────────────────────────────────────────────────
echo "[5/7] Restoring cortex_* tables (this may take 2-3 minutes)..."

# Run pre-restore SQL: creates required extensions and custom types
if [[ -f "$BACKUP_DIR/pre-restore.sql" ]]; then
    echo "  Running pre-restore.sql (extensions + custom types)..."
    docker exec -i "$DB_CONTAINER" psql -U postgres -d postgres < "$BACKUP_DIR/pre-restore.sql" 2>&1 | \
        grep -v "^$\|already exists" | head -10 || true
fi

# Copy dump into container
docker cp "$BACKUP_DIR/cortex.dump" "$DB_CONTAINER:/tmp/cortex.dump"

# Restore with:
#   --clean --if-exists: drops/recreates only objects IN the dump (cortex_* tables)
#   --no-owner: skip ownership assignment (avoids "must be member of role" errors
#               when source and target Supabase have different role configurations)
#   --no-privileges: skip GRANT/REVOKE (same reason)
docker exec "$DB_CONTAINER" pg_restore \
    -U postgres -d postgres --clean --if-exists --no-owner --no-privileges \
    /tmp/cortex.dump 2>&1 | \
    grep -E "(ERROR|FATAL)" | grep -v "does not exist" | head -20 || true

# Clean up dump file in container
docker exec "$DB_CONTAINER" rm -f /tmp/cortex.dump

# Verify table count after restore
RESTORED_COUNT=$(docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c \
    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'cortex_%';")
echo "  Database restore complete ($RESTORED_COUNT cortex_* tables)"

# ──────────────────────────────────────────────────────────────────────
# Step 6: Start Cortex
# ──────────────────────────────────────────────────────────────────────
echo "[6/7] Starting Cortex..."

cd "$CORTEX_DIR"
docker compose up -d 2>&1 | grep -v "^$" || true
echo "  Cortex containers starting..."

sleep 10

# ──────────────────────────────────────────────────────────────────────
# Step 7: Health checks and summary
# ──────────────────────────────────────────────────────────────────────
echo "[7/7] Running health checks..."

SERVER_OK=false
MCP_OK=false

for i in 1 2 3; do
    if curl -sf http://localhost:8181/health > /dev/null 2>&1; then
        SERVER_OK=true
        break
    fi
    sleep 5
done

for i in 1 2 3; do
    if curl -sf http://localhost:8051/health > /dev/null 2>&1; then
        MCP_OK=true
        break
    fi
    sleep 5
done

echo "  Cortex Server (8181): $( [[ "$SERVER_OK" == true ]] && echo 'HEALTHY' || echo 'UNREACHABLE' )"
echo "  Cortex MCP    (8051): $( [[ "$MCP_OK" == true ]] && echo 'HEALTHY' || echo 'UNREACHABLE' )"

echo ""
echo "============================================"
echo " Restore Summary"
echo "============================================"
echo "  Backup:        $BACKUP_NAME"
echo "  Dump size:     ${DUMP_SIZE_MB} MB"
echo "  Tables:        $RESTORED_COUNT cortex_* tables"
echo "  CORTEX_DIR:    $CORTEX_DIR"
echo "  Server:        $( [[ "$SERVER_OK" == true ]] && echo 'OK' || echo 'FAILED' )"
echo "  MCP:           $( [[ "$MCP_OK" == true ]] && echo 'OK' || echo 'FAILED' )"
echo "  Restored at:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

if [[ "$SERVER_OK" == false || "$MCP_OK" == false ]]; then
    echo ""
    echo "WARNING: Not all services are healthy. Check logs with:"
    echo "  docker compose logs -f cortex-server"
    echo "  docker compose logs -f cortex-mcp"
    exit 1
fi
