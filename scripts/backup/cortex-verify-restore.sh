#!/usr/bin/env bash
# cortex-verify-restore.sh — Lightweight restore-readiness checker for the backup server
# Verifies that the backup server can accept an Cortex-only restore into its existing Supabase.
#
# Usage: ./cortex-verify-restore.sh

set -euo pipefail

BACKUP_BASE="$HOME/cortex-backups"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_DIR="${CORTEX_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DB_CONTAINER="supabase-db"

PASS=0
FAIL=0
WARN=0

check() {
    local label="$1"
    local result="$2"
    if [[ "$result" == "PASS" ]]; then
        echo "  [PASS] $label"
        PASS=$((PASS + 1))
    elif [[ "$result" == "WARN" ]]; then
        echo "  [WARN] $label"
        WARN=$((WARN + 1))
    else
        echo "  [FAIL] $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo " Cortex Restore Readiness Check"
echo "============================================"
echo ""

# 1. Check latest symlink and backup contents
echo "Backup:"
if [[ -L "$BACKUP_BASE/latest" ]]; then
    LATEST=$(readlink -f "$BACKUP_BASE/latest")
    LATEST_NAME=$(basename "$LATEST")
    check "'latest' symlink exists -> $LATEST_NAME" "PASS"

    [[ -f "$LATEST/cortex.dump" ]] && check "cortex.dump present" "PASS" || check "cortex.dump present" "FAIL"
    [[ -f "$LATEST/env/cortex.env" ]] && check "cortex.env present" "PASS" || check "cortex.env present" "FAIL"

    if [[ -f "$LATEST/cortex.dump" ]]; then
        DUMP_SIZE=$(stat -c%s "$LATEST/cortex.dump")
        DUMP_SIZE_MB=$((DUMP_SIZE / 1024 / 1024))
        if [[ "$DUMP_SIZE" -gt 0 ]]; then
            check "cortex.dump size: ${DUMP_SIZE_MB} MB" "PASS"
        else
            check "cortex.dump is empty!" "FAIL"
        fi
    fi

    # Backup age
    BACKUP_DATE="${LATEST_NAME:0:10} ${LATEST_NAME:11:2}:${LATEST_NAME:13:2}:${LATEST_NAME:15:2}"
    BACKUP_EPOCH=$(date -d "$BACKUP_DATE" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    AGE_HOURS=$(( (NOW_EPOCH - BACKUP_EPOCH) / 3600 ))
    if [[ "$AGE_HOURS" -le 12 ]]; then
        check "Backup age: ${AGE_HOURS}h (within 12h)" "PASS"
    else
        check "Backup age: ${AGE_HOURS}h (STALE — exceeds 12h)" "WARN"
    fi
else
    check "'latest' symlink exists" "FAIL"
fi

echo ""

# 2. Check Cortex repo
echo "Repository:"
if [[ -d "$CORTEX_DIR/.git" ]]; then
    CORTEX_BRANCH=$(cd "$CORTEX_DIR" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    check "Cortex repo exists (branch: $CORTEX_BRANCH)" "PASS"
else
    check "Cortex repo at $CORTEX_DIR" "FAIL"
fi

echo ""

# 3. Docker and Supabase
echo "Docker & Supabase:"
if docker info > /dev/null 2>&1; then
    check "Docker daemon running" "PASS"
else
    check "Docker daemon running" "FAIL"
fi

STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$DB_CONTAINER" 2>/dev/null || echo "not_found")
if [[ "$STATUS" == "healthy" ]]; then
    check "$DB_CONTAINER is healthy" "PASS"
elif [[ "$STATUS" == "not_found" ]]; then
    check "$DB_CONTAINER is running (not found — start Supabase first)" "FAIL"
else
    check "$DB_CONTAINER is healthy (status: $STATUS)" "WARN"
fi

# Check pgvector extension
if [[ "$STATUS" == "healthy" ]]; then
    HAS_VECTOR=$(docker exec "$DB_CONTAINER" psql -U postgres -d postgres -t -A -c \
        "SELECT 1 FROM pg_extension WHERE extname='vector';" 2>/dev/null || echo "0")
    if [[ "$HAS_VECTOR" == "1" ]]; then
        check "pgvector extension available" "PASS"
    else
        check "pgvector extension (not enabled — restore script will create it)" "WARN"
    fi
fi

echo ""

# 4. Dump validation
echo "Dump validation:"
if [[ -L "$BACKUP_BASE/latest" && -f "$(readlink -f "$BACKUP_BASE/latest")/cortex.dump" ]]; then
    DUMP_PATH="$(readlink -f "$BACKUP_BASE/latest")/cortex.dump"
    if command -v pg_restore > /dev/null 2>&1; then
        if pg_restore --list "$DUMP_PATH" > /dev/null 2>&1; then
            TOC_COUNT=$(pg_restore --list "$DUMP_PATH" 2>/dev/null | grep -c "TABLE DATA" || true)
            check "pg_restore --list: valid ($TOC_COUNT table data entries)" "PASS"
        else
            check "pg_restore --list: failed" "FAIL"
        fi
    elif [[ "$STATUS" == "healthy" ]]; then
        if docker exec -i "$DB_CONTAINER" pg_restore --list < "$DUMP_PATH" > /dev/null 2>&1; then
            TOC_COUNT=$(docker exec -i "$DB_CONTAINER" pg_restore --list < "$DUMP_PATH" 2>/dev/null | grep -c "TABLE DATA" || true)
            check "pg_restore --list: valid ($TOC_COUNT table data entries, via docker)" "PASS"
        else
            check "pg_restore --list: failed (via docker)" "FAIL"
        fi
    else
        check "pg_restore --list: skipped (no pg_restore and no running DB)" "WARN"
    fi
else
    check "pg_restore --list: skipped (no dump found)" "FAIL"
fi

echo ""

# 5. Disk space
echo "Disk space:"
AVAIL_KB=$(df --output=avail "$HOME" | tail -1 | tr -d ' ')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [[ "$AVAIL_GB" -ge 10 ]]; then
    check "Available: ${AVAIL_GB} GB" "PASS"
else
    check "Available: ${AVAIL_GB} GB (low)" "WARN"
fi

# Summary
echo ""
echo "============================================"
if [[ "$FAIL" -eq 0 ]]; then
    echo " Restore-ready: YES ($PASS passed, $WARN warnings)"
else
    echo " Restore-ready: NO ($FAIL failures, $PASS passed, $WARN warnings)"
fi
echo "============================================"

exit "$FAIL"
