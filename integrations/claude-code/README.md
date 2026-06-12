# Cortex — Claude Code Integration

Claude Code skills for managing knowledge and project ecosystems via Cortex's RAG knowledge base.

## Available Skills

- **`/cortex-memory`** — Ingest, search, and sync project documentation
- **`/link-to-project`** — Link repos to an Cortex project ecosystem (hierarchy, source linking, doc ingestion)

## What It Does

- **Ingest** project documentation into Cortex's vector store
- **Search** semantically across ingested docs (no more reading 40+ files per session)
- **Sync** when docs change (detect staleness, re-ingest)
- **Share** knowledge across projects (framework docs, tool patterns)
- **Coordinate** tasks across AI agents via Cortex's project management

## Prerequisites

1. **Cortex server** running and accessible (default: `http://localhost:8051/mcp`)
2. **Cortex MCP connection** configured in Claude Code
3. **Claude Code** installed

### Configure Cortex MCP Connection

Add to your project's `.mcp.json` or `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "cortex": {
      "type": "streamable-http",
      "url": "http://localhost:8051/mcp"
    }
  }
}
```

Replace `localhost` with the Cortex server's hostname/IP if it runs on a different machine.

## Installation

### 1. Install the skill

Copy the skills into Claude Code's global skills directory:

```bash
# From the Cortex repo
cp -r integrations/claude-code/skills/cortex-memory ~/.claude/skills/
cp -r integrations/claude-code/skills/cortex-link-project ~/.claude/skills/

# Or clone directly
mkdir -p ~/.claude/skills
cp -r /path/to/Cortex/integrations/claude-code/skills/cortex-memory ~/.claude/skills/
cp -r /path/to/Cortex/integrations/claude-code/skills/cortex-link-project ~/.claude/skills/
```

The skill is auto-discovered by Claude Code — no registration needed.

### 2. Add ambient behavior to CLAUDE.md

Append the ambient behavior snippet to your global Claude Code instructions:

```bash
cat integrations/claude-code/claude-md-snippet.md >> ~/.claude/CLAUDE.md
```

This tells Claude to:
- Show Cortex KB status at the start of every session
- Prefer Cortex search over raw file reads during work
- Remind you to sync when docs change

### 3. Verify

Start a new Claude Code session and type `/cortex-memory`. You should see the status overview.

## Usage

| Command | Purpose |
|---------|---------|
| `/cortex-memory` | Status overview + freshness check |
| `/cortex-memory ingest` | Ingest project docs (first time) |
| `/cortex-memory ingest docs/` | Ingest from specific directory |
| `/cortex-memory sync` | Re-ingest changed docs |
| `/cortex-memory search <query>` | Search project knowledge |
| `/cortex-memory search-all <query>` | Search all projects |
| `/cortex-memory shared add <url>` | Add shared cross-project knowledge |
| `/cortex-memory shared list` | List shared knowledge sources |
| `/cortex-memory tasks` | List project tasks |
| `/cortex-memory forget` | Remove project from Cortex |

### Quick Start

```
# 1. Ingest your project's documentation
/cortex-memory ingest

# 2. Search it
/cortex-memory search "authentication flow"

# 3. After making doc changes, sync
/cortex-memory sync
```

### What Gets Ingested

By default, `/cortex-memory ingest` discovers and ingests:
- All `.md` files in `docs/` (or user-specified directory)
- `CLAUDE.md` (project root + parent directory)
- `README.md`

### Session Start Status

With ambient behavior configured, every session shows a one-liner:

```
Cortex KB: RecipeRaiders — 44 docs, synced 2h ago, up to date
```

Or if docs have changed:
```
Cortex KB: RecipeRaiders — 44 docs, synced 2h ago, 3 files changed. Run /cortex-memory sync
```

## State Files

| File | Location | Purpose |
|------|----------|---------|
| `cortex-state.json` | `.claude/` (per-project, gitignored) | Project ID, source ID, file hashes |
| `cortex-global.json` | `~/.claude/` (global) | Shared knowledge project ID, sources |

## Architecture

```
Claude Code Session
    │
    ├── MEMORY.md (quick-ref index + Cortex IDs)
    ├── CLAUDE.md (project rules + ambient behavior)
    │
    └── Cortex MCP Server
        ├── Project RAG (full docs, code examples)
        ├── Shared KB (cross-project: Firebase, Next.js, etc.)
        └── Tasks (multi-agent coordination)
```

All Cortex data is shared across agents. When Claude Code ingests docs, Cursor, Windsurf, and other Claude instances can search them immediately.

## Troubleshooting

**"Cortex server is not reachable"**
- Check that Cortex is running: `curl http://localhost:8051/mcp`
- Verify MCP config in `.mcp.json`
- Run `/mcp` in Claude Code to reconnect

**"No Cortex state found"**
- Run `/cortex-memory ingest` to set up this project

**Source ID mismatch**
- Run `/cortex-memory forget` then `/cortex-memory ingest` to start fresh

**Ingestion seems stuck**
- Progress data expires ~30 seconds after completion
- Check `rag_get_available_sources()` to verify the source was created
