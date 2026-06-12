#!/usr/bin/env bash
# cortex-backup.sh — Scheduled + on-demand backup of Cortex-specific data
# Only backs up cortex_* tables (not the full database) plus env and Claude state.
#
# Usage:
#   ./cortex-backup.sh              # Standard backup
#   ./cortex-backup.sh --tag "reason"  # Tagged backup (exempt from rotation)

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────
REMOTE_HOST="winadmin@172.16.1.222"
REMOTE_BACKUP_DIR="~/cortex-backups"
LOCAL_BACKUP_DIR="$HOME/cortex-backups"
LOG_FILE="$LOCAL_BACKUP_DIR/backup.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_SUPABASE_DIR="/home/winadmin/projects/localSupabase"
GLOBAL_CLAUDE_DIR="/home/winadmin/.claude"
# Claude Code project memory uses the absolute path with slashes replaced by dashes
CORTEX_PATH_SLUG="$(echo "$CORTEX_DIR" | sed 's|^/||; s|/|-|g')"
MEMORY_DIR="$GLOBAL_CLAUDE_DIR/projects/-${CORTEX_PATH_SLUG}/memory"
DB_CONTAINER="supabase-db"
RETENTION_COUNT=28
STALE_THRESHOLD_HOURS=12
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)

# ──────────────────────────────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────────────────────────────
TAG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            TAG="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -n "$TAG" ]]; then
    SAFE_TAG=$(echo "$TAG" | tr ' /' '-' | tr -cd '[:alnum:]-_')
    BACKUP_NAME="${TIMESTAMP}_${SAFE_TAG}"
else
    BACKUP_NAME="$TIMESTAMP"
fi

BACKUP_DIR="$LOCAL_BACKUP_DIR/$BACKUP_NAME"

# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────
mkdir -p "$LOCAL_BACKUP_DIR"
chmod 700 "$LOCAL_BACKUP_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1"
    echo "$msg" | tee -a "$LOG_FILE" >&2
}

log "========== Backup started: $BACKUP_NAME =========="
[[ -n "$TAG" ]] && log "Tagged backup: $TAG (exempt from rotation)"

# ──────────────────────────────────────────────────────────────────────
# Step 1: Dump only cortex_* tables (Cortex-specific, not full database)
# ──────────────────────────────────────────────────────────────────────
log "Step 1: Dumping cortex_* tables..."
mkdir -p "$BACKUP_DIR"

# Discover all cortex_* tables dynamically so new tables are picked up automatically
CORTEX_TABLES=$(docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c \
    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'cortex_%' ORDER BY tablename;")

TABLE_COUNT=$(echo "$CORTEX_TABLES" | wc -l)
log "  Found $TABLE_COUNT cortex_* tables"

# Build pg_dump -t flags for each table
DUMP_FLAGS=""
while IFS= read -r table; do
    [[ -z "$table" ]] && continue
    DUMP_FLAGS="$DUMP_FLAGS -t public.$table"
done <<< "$CORTEX_TABLES"

if ! docker exec "$DB_CONTAINER" pg_dump -U postgres -Fc -d postgres $DUMP_FLAGS > "$BACKUP_DIR/cortex.dump" 2>>"$LOG_FILE"; then
    log_error "pg_dump failed"
    exit 1
fi

DUMP_SIZE=$(stat -c%s "$BACKUP_DIR/cortex.dump")
DUMP_SIZE_MB=$((DUMP_SIZE / 1024 / 1024))
log "  cortex.dump: ${DUMP_SIZE_MB} MB ($DUMP_SIZE bytes)"

if [[ "$DUMP_SIZE" -eq 0 ]]; then
    log_error "cortex.dump is empty — aborting"
    exit 1
fi

# Dump prerequisites: custom enum types and required extensions
# pg_dump -t doesn't capture types that tables depend on, so we extract them separately
log "  Dumping pre-restore prerequisites (custom types, extensions)..."
docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c "
    SELECT 'CREATE EXTENSION IF NOT EXISTS ' || quote_ident(extname) || ' SCHEMA extensions;'
    FROM pg_extension
    WHERE extname IN ('vector', 'pg_trgm', 'pgcrypto')
    ORDER BY extname;
" > "$BACKUP_DIR/pre-restore.sql" 2>>"$LOG_FILE"

# Dump custom enum types used by cortex tables
docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c "
    SELECT pg_catalog.pg_get_typedef(t.oid)
    FROM pg_type t
    JOIN pg_namespace n ON t.typnamespace = n.oid
    WHERE n.nspname = 'public'
      AND t.typtype = 'e'
      AND t.typname IN ('task_status', 'task_priority')
    ORDER BY t.typname;
" >> /dev/null 2>&1 || true

# pg_get_typedef doesn't exist in PG15, so dump enums manually
docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c "
    SELECT 'DO \$\$ BEGIN CREATE TYPE ' || quote_ident(t.typname) || ' AS ENUM (' ||
           string_agg(quote_literal(e.enumlabel), ', ' ORDER BY e.enumsortorder) ||
           '); EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;'
    FROM pg_type t
    JOIN pg_namespace n ON t.typnamespace = n.oid
    JOIN pg_enum e ON e.enumtypid = t.oid
    WHERE n.nspname = 'public'
      AND t.typtype = 'e'
      AND t.typname IN ('task_status', 'task_priority')
    GROUP BY t.typname
    ORDER BY t.typname;
" >> "$BACKUP_DIR/pre-restore.sql" 2>>"$LOG_FILE"

PRE_LINES=$(wc -l < "$BACKUP_DIR/pre-restore.sql")
log "  pre-restore.sql: $PRE_LINES statements"

# ──────────────────────────────────────────────────────────────────────
# Step 2: Collect env files and Claude state
# ──────────────────────────────────────────────────────────────────────
log "Step 2: Collecting env files and Claude state..."

# Env files — backed up for reference and Cortex recovery
mkdir -p "$BACKUP_DIR/env"
cp "$CORTEX_DIR/.env" "$BACKUP_DIR/env/cortex.env"
cp "$LOCAL_SUPABASE_DIR/.env" "$BACKUP_DIR/env/localsupabase.env"
[[ -f "$CORTEX_DIR/postmanSkill/.env" ]] && cp "$CORTEX_DIR/postmanSkill/.env" "$BACKUP_DIR/env/postmanskill.env"
log "  env files: $(ls "$BACKUP_DIR/env/" | wc -l) files collected"

# Claude state — project level
CLAUDE_STATE_DIR="$BACKUP_DIR/claude-state"
mkdir -p "$CLAUDE_STATE_DIR"

for f in cortex-state.json cortex-config.json cortex-memory-buffer.jsonl settings.local.json; do
    [[ -f "$CORTEX_DIR/.claude/$f" ]] && cp "$CORTEX_DIR/.claude/$f" "$CLAUDE_STATE_DIR/"
done

# Claude state — directories (skills, commands, agents, plugins excluding .venv)
for d in skills commands agents; do
    if [[ -d "$CORTEX_DIR/.claude/$d" ]]; then
        cp -r "$CORTEX_DIR/.claude/$d" "$CLAUDE_STATE_DIR/"
    fi
done

if [[ -d "$CORTEX_DIR/.claude/plugins" ]]; then
    mkdir -p "$CLAUDE_STATE_DIR/plugins"
    rsync -a --exclude='.venv' "$CORTEX_DIR/.claude/plugins/" "$CLAUDE_STATE_DIR/plugins/"
fi

# Claude state — global settings
if [[ -f "$GLOBAL_CLAUDE_DIR/settings.json" ]]; then
    cp "$GLOBAL_CLAUDE_DIR/settings.json" "$CLAUDE_STATE_DIR/global-settings.json"
fi

# Claude state — auto-memory
if [[ -d "$MEMORY_DIR" ]]; then
    cp -r "$MEMORY_DIR" "$CLAUDE_STATE_DIR/memory"
fi

CLAUDE_FILES=$(find "$CLAUDE_STATE_DIR" -type f | wc -l)
log "  claude-state: $CLAUDE_FILES files collected"

# ──────────────────────────────────────────────────────────────────────
# Step 3: Verify backup integrity
# ──────────────────────────────────────────────────────────────────────
log "Step 3: Verifying backup integrity..."

# 3a. pg_restore --list on the dump
TOC_OUTPUT=$(docker exec -i "$DB_CONTAINER" pg_restore --list < "$BACKUP_DIR/cortex.dump" 2>>"$LOG_FILE")
if [[ $? -eq 0 ]]; then
    TOC_COUNT=$(echo "$TOC_OUTPUT" | grep -c "TABLE DATA" || true)
    log "  pg_restore --list: PASS (valid archive, $TOC_COUNT table data entries)"
else
    log_error "pg_restore --list failed — dump may be corrupt"
    exit 1
fi

# 3b. File completeness checks
MISSING=""
[[ ! -s "$BACKUP_DIR/env/cortex.env" ]] && MISSING="$MISSING cortex.env"
[[ ! -s "$BACKUP_DIR/env/localsupabase.env" ]] && MISSING="$MISSING localsupabase.env"
[[ ! -s "$CLAUDE_STATE_DIR/cortex-state.json" ]] && MISSING="$MISSING cortex-state.json"

if [[ -n "$MISSING" ]]; then
    log_error "Missing or empty critical files:$MISSING"
    exit 1
fi
log "  File completeness: PASS"

# 3c. Size sanity vs previous backup
PREV_DUMP=$(find "$LOCAL_BACKUP_DIR" -maxdepth 2 -name "cortex.dump" -not -path "*/$BACKUP_NAME/*" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | awk '{print $2}')
if [[ -n "$PREV_DUMP" && -f "$PREV_DUMP" ]]; then
    PREV_SIZE=$(stat -c%s "$PREV_DUMP")
    if [[ "$PREV_SIZE" -gt 0 ]]; then
        RATIO=$((DUMP_SIZE * 100 / PREV_SIZE))
        if [[ "$RATIO" -lt 80 ]]; then
            log "  WARNING: Dump is ${RATIO}% of previous size ($DUMP_SIZE vs $PREV_SIZE bytes)"
        else
            log "  Size sanity: PASS (${RATIO}% of previous)"
        fi
    fi
else
    log "  Size sanity: SKIP (no previous backup to compare)"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 4: rsync to backup server
# ──────────────────────────────────────────────────────────────────────
log "Step 4: Syncing to $REMOTE_HOST..."

ssh "$REMOTE_HOST" "mkdir -p $REMOTE_BACKUP_DIR && chmod 700 $REMOTE_BACKUP_DIR"

if ! rsync -az --info=progress2 "$BACKUP_DIR/" "$REMOTE_HOST:$REMOTE_BACKUP_DIR/$BACKUP_NAME/" 2>>"$LOG_FILE"; then
    log_error "rsync to $REMOTE_HOST failed"
    exit 1
fi
log "  rsync: complete"

# Update "latest" symlink on remote
ssh "$REMOTE_HOST" "cd $REMOTE_BACKUP_DIR && rm -f latest && ln -s $BACKUP_NAME latest"
log "  latest -> $BACKUP_NAME"

# Sync backup.log to remote
rsync -az "$LOG_FILE" "$REMOTE_HOST:$REMOTE_BACKUP_DIR/backup.log" 2>/dev/null || true

# ──────────────────────────────────────────────────────────────────────
# Step 5: Update repos on backup server
# ──────────────────────────────────────────────────────────────────────
log "Step 5: Updating repos on backup server..."

ssh "$REMOTE_HOST" "cd ~/projects/Cortex && git pull --ff-only 2>&1 || echo 'git pull Cortex failed (non-fatal)'" 2>>"$LOG_FILE" | while read -r line; do log "  Cortex: $line"; done

ssh "$REMOTE_HOST" "cd ~/projects/localSupabase && git pull --ff-only 2>&1 || echo 'git pull localSupabase failed (non-fatal)'" 2>>"$LOG_FILE" | while read -r line; do log "  localSupabase: $line"; done

# ──────────────────────────────────────────────────────────────────────
# Step 6: Rotate old backups (keep last RETENTION_COUNT, skip tagged)
# ──────────────────────────────────────────────────────────────────────
log "Step 6: Rotating old backups (keep $RETENTION_COUNT, skip tagged)..."

rotate_backups() {
    local dir="$1"
    local host="$2"  # empty for local, "user@host" for remote

    local cmd
    if [[ -n "$host" ]]; then
        cmd="ssh $host"
    else
        cmd="bash -c"
    fi

    # List only untagged backup dirs (exactly YYYY-MM-DD_HHMMSS, 17 chars)
    local backups
    backups=$($cmd "ls -1d $dir/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]/ 2>/dev/null | sort -r" || true)

    local count=0
    local removed=0
    while IFS= read -r backup_path; do
        [[ -z "$backup_path" ]] && continue
        count=$((count + 1))
        if [[ "$count" -gt "$RETENTION_COUNT" ]]; then
            $cmd "rm -rf '$backup_path'" 2>/dev/null
            removed=$((removed + 1))
        fi
    done <<< "$backups"

    echo "$removed"
}

LOCAL_REMOVED=$(rotate_backups "$LOCAL_BACKUP_DIR" "")
REMOTE_REMOVED=$(rotate_backups "$REMOTE_BACKUP_DIR" "$REMOTE_HOST")
log "  Removed: $LOCAL_REMOVED local, $REMOTE_REMOVED remote"

# ──────────────────────────────────────────────────────────────────────
# Step 7: Staleness check and final summary
# ──────────────────────────────────────────────────────────────────────
NEWEST_REMOTE=$(ssh "$REMOTE_HOST" "ls -1d $REMOTE_BACKUP_DIR/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]/ 2>/dev/null | sort -r | head -1" || true)
if [[ -n "$NEWEST_REMOTE" ]]; then
    NEWEST_NAME=$(basename "$NEWEST_REMOTE")
    NEWEST_DATE="${NEWEST_NAME:0:10} ${NEWEST_NAME:11:2}:${NEWEST_NAME:13:2}:${NEWEST_NAME:15:2}"
    NEWEST_EPOCH=$(date -d "$NEWEST_DATE" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    AGE_HOURS=$(( (NOW_EPOCH - NEWEST_EPOCH) / 3600 ))

    if [[ "$AGE_HOURS" -ge "$STALE_THRESHOLD_HOURS" ]]; then
        log "STALE_BACKUP_WARNING: Newest remote backup is ${AGE_HOURS}h old (threshold: ${STALE_THRESHOLD_HOURS}h)"
    fi
fi

TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | awk '{print $1}')
log "========== Backup complete: $BACKUP_NAME ($TOTAL_SIZE) =========="
