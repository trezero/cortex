# Cortex Backup & Restore Design

**Date:** 2026-03-18
**Status:** Approved
**Approach:** Hybrid — scheduled pg_dump + rsync + pre-staged recovery environment

## Problem

Cortex runs entirely on a single machine (WIN-AI-PC, WSL2 Ubuntu 22.04) with a local
self-hosted Supabase instance. If the server goes down and its data is lost, all knowledge
base content, projects, tasks, sessions, settings, and embeddings are gone. There is
currently no backup mechanism.

## Goals

- **RPO (Recovery Point Objective):** 6 hours maximum data loss
- **RTO (Recovery Time Objective):** ~10 minutes to fully operational on backup server
- **Backup server:** `172.16.1.222` (Ubuntu 22.04, Docker installed, 154 GB free, ~86 MB/s network link)

## Data Inventory

### Tier 1 — Critical (data loss = start over)

| Data | Size | Location |
|------|------|----------|
| PostgreSQL (all 12 schemas — see note below) | 1.1 GB logical, **353 MB** compressed dump | `supabase-db` Docker container |
| PostgreSQL roles (via `pg_dumpall --globals-only`) | ~5 KB | `supabase-db` Docker container |
| Cortex `.env` | ~3 KB | `/home/winadmin/projects/Trinity/cortex/.env` |
| localSupabase `.env` | ~4 KB | `/home/winadmin/projects/localSupabase/.env` |

The database contains 23 `cortex_*` tables (1 GB of which is `cortex_crawled_pages` with
vector embeddings), plus ~20 non-Cortex public tables (memecoin, brand_settings, etc.),
auth schema, and Supabase system schemas.

**Only `cortex_*` tables are backed up** via `pg_dump -Fc -t 'public.cortex_*'`. Non-Cortex
tables, auth schema, and Supabase system schemas are NOT backed up — they belong to each
machine's own Supabase instance. Verified via test dump on 2026-03-18 (352 MB).

**Pre-restore prerequisites** are captured in `pre-restore.sql`: required extensions
(`vector`, `pg_trgm`, `pgcrypto`) and custom enum types (`task_status`, `task_priority`).
These must be applied before `pg_restore`.

**Roles** are NOT backed up separately. The `pg_restore` uses `--no-owner --no-privileges`
to skip ownership and permission assignments, avoiding "must be member of role" errors
when restoring into a Supabase instance with different role configurations.

### Tier 2 — Important (loss = inconvenience, manual re-setup)

| Data | Size | Location |
|------|------|----------|
| `cortex-state.json` | <1 KB | `/home/winadmin/projects/Trinity/cortex/.claude/` |
| `cortex-config.json` | <1 KB | `/home/winadmin/projects/Trinity/cortex/.claude/` |
| `cortex-memory-buffer.jsonl` | ~240 KB | `/home/winadmin/projects/Trinity/cortex/.claude/` |
| `settings.local.json` | <1 KB | `/home/winadmin/projects/Trinity/cortex/.claude/` |
| `skills/` directory | ~212 KB | `/home/winadmin/projects/Trinity/cortex/.claude/skills/` |
| `commands/` directory | ~132 KB | `/home/winadmin/projects/Trinity/cortex/.claude/commands/` |
| `agents/` directory | ~16 KB | `/home/winadmin/projects/Trinity/cortex/.claude/agents/` |
| `plugins/` directory (excl. `.venv`) | ~264 KB | `/home/winadmin/projects/Trinity/cortex/.claude/plugins/` |
| `postmanSkill/.env` | <1 KB | `/home/winadmin/projects/Trinity/cortex/postmanSkill/.env` |
| Global `settings.json` | ~1 KB | `/home/winadmin/.claude/settings.json` |
| Auto-memory `.md` files | ~50 KB | `/home/winadmin/.claude/projects/-home-winadmin-projects-cortex/memory/` |

### Tier 3 — Pre-staged on backup server (enables fast recovery)

| Data | Purpose |
|------|---------|
| Cortex repo (`git pull` each cycle) | Code, migrations, docker-compose |
| localSupabase repo (`git pull` each cycle) | Supabase docker-compose and config |

### Not Backed Up (verified empty or unnecessary)

- Cortex Docker volumes (`cortex-server-data`, `cortex-mcp-data`, `cortex-ui-data`) — confirmed 4 KB each, empty
- Supabase Storage — confirmed 0 buckets, 0 objects
- Global `.claude/` session logs (73 MB of JSONL) — ephemeral, not worth the space
- Supabase `db-config` volume — default PostgreSQL config, recreated on startup
- `.claude/plugins/*/.venv/` — Python virtual environments, regenerated from `requirements.txt`
- `.claude/worktrees/` — git worktree metadata, ephemeral

## Architecture

### Backup Flow (runs on source machine)

```
cortex-backup.sh (cron every 6 hours, or manual)
    │
    ├─ 1. pg_dump -Fc -t 'public.cortex_*' via docker exec supabase-db
    │     only cortex_* tables, compressed (~352 MB)
    │     → ~/cortex-backups/TIMESTAMP/cortex.dump
    │     + pre-restore.sql (extensions + custom enum types)
    │
    ├─ 2. Collect Tier 1 + Tier 2 files
    │     → ~/cortex-backups/TIMESTAMP/env/
    │     → ~/cortex-backups/TIMESTAMP/claude-state/
    │
    ├─ 3. Verify backup integrity
    │     - pg_restore --list (valid archive)
    │     - file completeness check
    │     - size sanity vs previous backup
    │
    ├─ 4. rsync -az to 172.16.1.222:~/cortex-backups/
    │     update "latest" symlink on remote
    │
    ├─ 5. Remote: git pull Cortex + localSupabase repos
    │
    ├─ 6. Rotate: keep last 28 backups, prune older
    │     (tagged backups exempt from rotation)
    │
    └─ 7. Log result to backup.log
```

### Restore Flow (runs on backup server)

```
cortex-restore.sh [backup_name]  (defaults to "latest")
    │
    ├─ 1. Validate backup exists, dump + roles.sql present, env files present
    │
    ├─ 2. Place Cortex .env files (NOT localSupabase — it has its own config)
    │     cortex.env → $CORTEX_DIR/.env
    │     postmanskill.env → $CORTEX_DIR/postmanSkill/.env
    │
    ├─ 3. Restore Claude state
    │     Project-level → $CORTEX_DIR/.claude/
    │     Plugins (excl .venv) → $CORTEX_DIR/.claude/plugins/
    │     Global settings → /home/winadmin/.claude/settings.json
    │     Memory → /home/winadmin/.claude/projects/.../memory/
    │
    ├─ 4. Verify Supabase is running (do NOT start/restart — it has its own data)
    │     Confirm supabase-db is healthy
    │     Ensure pgvector extension is available
    │
    ├─ 5. Restore cortex_* tables
    │     Run pre-restore.sql (extensions + custom enum types)
    │     docker cp cortex.dump supabase-db:/tmp/cortex.dump
    │     docker exec supabase-db pg_restore \
    │       -U postgres -d postgres --clean --if-exists \
    │       --no-owner --no-privileges /tmp/cortex.dump
    │     docker exec supabase-db rm /tmp/cortex.dump
    │     (Only cortex_* tables are dropped/recreated. All other tables untouched.)
    │
    ├─ 7. Start Cortex
    │     cd $CORTEX_DIR && docker compose up -d
    │
    ├─ 8. Health check
    │     curl localhost:8181/health
    │     curl localhost:8051/health
    │
    └─ 9. Print summary (timestamp, DB size, services status)

$CORTEX_DIR defaults to /home/winadmin/projects/Cortex on the backup server.
Configurable via CORTEX_DIR env var to handle path differences between machines.
```

## Directory Layout

### Source machine (local staging before rsync)

```
~/cortex-backups/
├── backup.log
└── YYYY-MM-DD_HHMMSS/
    ├── cortex.dump           (~352 MB, cortex_* tables only)
    ├── pre-restore.sql       (extensions + custom types)
    ├── env/
    │   ├── cortex.env
    │   ├── localsupabase.env
    │   └── postmanskill.env
    └── claude-state/
        ├── cortex-state.json
        ├── cortex-config.json
        ├── cortex-memory-buffer.jsonl
        ├── settings.local.json
        ├── global-settings.json
        ├── skills/
        ├── commands/
        ├── agents/
        ├── plugins/          (excl. .venv/)
        └── memory/
```

### Backup server

```
~/cortex-backups/
├── backup.log
├── latest -> YYYY-MM-DD_HHMMSS/   (symlink)
├── YYYY-MM-DD_HHMMSS/
│   └── (same structure as above)
├── YYYY-MM-DD_HHMMSS_pre-migration/  (tagged, exempt from rotation)
│   └── ...

~/projects/
├── Cortex/           (git pull each backup cycle)
└── localSupabase/    (git pull each backup cycle)
```

## Backup Schedule & Retention

- **Frequency:** Every 6 hours via cron (`0 0,6,12,18 * * *`)
- **Retention:** Last 28 backups (7 days)
- **Tagged backups:** Created with `--tag "reason"`, exempt from rotation, manually deleted
- **Estimated storage:** ~353 MB/backup × 28 = ~10 GB (well within 154 GB available)

## On-Demand Backup

```bash
# Standard manual backup
./scripts/backup/cortex-backup.sh

# Tagged backup (exempt from rotation)
./scripts/backup/cortex-backup.sh --tag "pre-migration"
```

## Verification

### Built into backup script (every run)

1. `pg_restore --list` on the dump — confirms valid archive format
2. File completeness — both `.env` files and `cortex-state.json` present and non-empty
3. Size sanity — warns if dump is <80% of previous backup size or zero bytes

### Restore readiness check (manual, run on backup server)

`scripts/backup/cortex-verify-restore.sh`:
1. Confirms `latest` symlink points to a valid backup
2. Confirms both repos are up to date
3. Confirms Docker is running
4. Dry-runs `pg_restore --list` on latest dump
5. Reports: "Restore-ready: YES/NO"

## Edge Cases

### host.docker.internal differences

The Cortex `.env` references `host.docker.internal` for `SUPABASE_URL`. Docker Desktop
(WSL2) and native Docker (Ubuntu) may resolve this differently. The restore script checks
this and warns if adjustment is needed.

### Unflushed memory buffer

`cortex-memory-buffer.jsonl` may contain session observations not yet flushed to the
database. The backup captures the file state at backup time; any observations added after
the backup but before a crash would be lost (acceptable given the 6-hour RPO).

### Non-Cortex tables

The full `pg_dump` captures all schemas including non-Cortex tables (memecoin,
brand_settings, etc.). This is intentional — it's a full instance backup, not selective.

### Path casing: `cortex` vs `Cortex`

The source machine uses lowercase `/home/winadmin/projects/Trinity/cortex/`. The backup server's
existing clone uses uppercase `/home/winadmin/projects/Cortex/` (matching the GitHub repo
name). The restore script uses `$CORTEX_DIR` to abstract this. Claude Code's auto-memory
directory encodes the project path, so memory files backed up from the source machine will
only be found if the project path matches. The restore script places them at the
source-machine-encoded path regardless of the actual project directory.

### localSupabase .env ordering is critical

The localSupabase `.env` contains `VAULT_ENC_KEY` used by pgsodium for column-level
encryption. If Supabase initializes with a different key, vault-encrypted data becomes
unrecoverable. The restore script MUST place the `.env` file before running
`docker compose up -d` for Supabase. The restore flow (step 2 before step 4) enforces this.

### PostgreSQL data directory mount differences

On WSL2/Docker Desktop, the PostgreSQL data directory (`volumes/db/data/`) is redirected
through Docker Desktop's internal bind mount mechanism. On native Ubuntu (the backup
server), it is a direct bind mount. This means after `docker compose up -d` on the backup
server, the `volumes/db/data/` directory will be populated directly on disk. The
`pg_restore` overwrites the database contents regardless of mount type.

### Backup staleness detection

If the cron job fails silently, the RPO could be exceeded without anyone knowing. The
backup script checks the age of the most recent remote backup after each run. If the
newest backup is >12 hours old (2× the RPO), it logs a `STALE_BACKUP_WARNING`. A future
enhancement could send this alert via webhook or email.

### Backup directory permissions

The backup directory contains `.env` files with secrets (Supabase service keys, vault
encryption key, API keys). The backup script sets `chmod 700` on `~/cortex-backups/` on
both machines to restrict access to the owning user. rsync runs over SSH using the
existing key-based authentication between the two machines.

## Files to Create

| File | Purpose |
|------|---------|
| `scripts/backup/cortex-backup.sh` | Backup script (cron + manual) |
| `scripts/backup/cortex-restore.sh` | One-command restore on backup server |
| `scripts/backup/cortex-verify-restore.sh` | Restore readiness verification |

## Recovery Timeline

| Step | Duration |
|------|----------|
| SSH to backup server | ~1 min |
| Run `cortex-restore.sh` | ~1 min (file copies) |
| Supabase startup + healthy | ~2 min |
| Database restore | ~2-3 min |
| Cortex containers start | ~1 min |
| Health checks pass | ~1 min |
| **Total** | **~8-10 min** |
