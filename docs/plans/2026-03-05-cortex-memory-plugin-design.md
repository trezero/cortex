# Cortex Memory Plugin — Design Document

**Date:** 2026-03-05
**Status:** Approved
**Replaces:** claude-mem plugin (third-party)

## Overview

Build an Cortex-native Claude Code plugin called `cortex-memory` that replaces the third-party claude-mem plugin. Provides local smart code exploration via tree-sitter AST parsing, session memory synced to Cortex's centralized knowledge base, and automatic context injection at session start.

The plugin is distributed through Cortex's setup system and installed locally per-project (or optionally globally). It integrates with the existing Cortex MCP server rather than duplicating its tools.

## Goals

1. **Smart Explore** — Token-efficient structural code navigation on local files
2. **Session Memory** — Cross-agent session history stored in Cortex
3. **Context Injection** — Automatic project context at session start
4. **Unified Distribution** — Installed via cortexSetup.sh/bat alongside Cortex MCP config
5. **Replace claude-mem** — Single plugin, no competing memory systems

## Non-Goals

- RAG search proxy (Cortex MCP server handles this directly)
- Real-time observation streaming (batch flush on session end is sufficient)
- WebSocket/SSE for live updates
- Plugin marketplace (distributed via Cortex setup endpoints)

---

## Architecture

### Plugin Technology

Pure Python. Matches Cortex's ecosystem, single runtime, tree-sitter Python bindings are first-class.

### Integration Model

The plugin and Cortex MCP server coexist as two separate MCP servers configured in Claude Code:

- **cortex-memory plugin** — owns local-only features: smart-explore (filesystem access), session memory hooks, context injection
- **Cortex MCP server** — owns centralized features: RAG search, projects, tasks, documents, versions, extensions

The setup script configures both. No proxy layer needed.

### Installation Model

**Default: Local (project-scoped)**
```
<project-root>/.claude/plugins/cortex-memory/
<project-root>/.claude/skills/smart-explore/
<project-root>/.claude/skills/mem-search/
```

**Optional: Global (user-scoped)**
```
~/.claude/plugins/cortex-memory/
~/.claude/skills/smart-explore/
~/.claude/skills/mem-search/
```

Both paths are gitignored. Each team member runs setup independently.

### Configuration

Machine-specific config written during setup:

```json
// .claude/cortex-config.json (or ~/.claude/cortex-config.json for global)
{
  "cortex_api_url": "http://localhost:8181",
  "cortex_mcp_url": "http://localhost:8051",
  "project_id": "uuid",
  "project_title": "ProjectName",
  "machine_id": "sha256-fingerprint",
  "install_scope": "local",
  "installed_at": "ISO timestamp"
}
```

---

## Feature 1: Smart Explore

Three MCP tools with direct local filesystem access via tree-sitter AST parsing.

### Tools

**`smart_search(query, path?, max_results?, file_pattern?)`**
- Walks directory tree from `path` (default: cwd)
- Skips: `.git`, `node_modules`, `__pycache__`, `dist`, `vendor`, etc.
- Groups discovered code files by language
- Parses each group with tree-sitter using language-specific query patterns
- Extracts symbols: functions, classes, methods, interfaces, types, enums, structs, traits
- Ranks symbols using weighted scoring:
  - Name match: 3x weight
  - Signature match: 2x weight
  - Docstring/comment match: 1x weight
- Returns ranked symbols + folded file views with token estimates

**`smart_outline(file_path)`**
- Parses single file with tree-sitter
- Returns structural skeleton: all symbols with signatures, line ranges, export status, nesting hierarchy
- Includes import summary and token estimate
- Typically 1-2k tokens vs 12k+ for full file read

**`smart_unfold(file_path, symbol_name)`**
- Parses file, finds matching symbol in AST
- Returns full source including preceding comments/decorators/docstrings
- AST node boundaries guarantee completeness

### Language Support

Via `tree-sitter` + `tree-sitter-language-pack` Python packages (160+ languages).

Priority languages with full query patterns:
- Python, JavaScript, TypeScript/TSX, Go, Rust, Java, Ruby, C, C++

### Implementation Details

- Uses tree-sitter Python Query API directly (no CLI subprocess)
- Batch parsing: one parser instance per language, reused across files
- File size limit: skip files > 512KB
- Max directory depth: 20 levels
- Language detection via file extension mapping

### Symbol Extraction

Each symbol includes:
- `name` — identifier
- `kind` — function, class, method, interface, type, enum, struct, trait, property, etc.
- `signature` — first line(s) of declaration, truncated to 200 chars
- `line_start`, `line_end` — source location
- `parent` — containing class/struct (for methods)
- `exported` — language-specific export detection
- `docstring` — preceding comment/docstring
- `children` — nested symbols (methods in classes)

---

## Feature 2: Session Memory

Hooks capture session activity and sync to Cortex so all agents see the history.

### Observation Capture

- `PostToolUse` hook fires after each tool call
- Lightweight Python script appends observation to local buffer file (`.claude/cortex-memory-buffer.jsonl`)
- Each observation: timestamp, tool name, files touched, brief summary
- No HTTP calls during hook — local file append only (~5ms)

### Session Lifecycle

1. `SessionStart` hook assigns session ID (UUID), records start time
2. `PostToolUse` hook appends observations to buffer
3. `Stop` hook flushes buffer to Cortex in one batch API call
4. If session crashes without clean Stop, buffer persists and flushes on next SessionStart

### Batch Payload

```json
{
  "session_id": "uuid",
  "machine_id": "sha256-fingerprint",
  "project_id": "cortex-project-id",
  "started_at": "ISO timestamp",
  "ended_at": "ISO timestamp",
  "observations": [
    {
      "type": "discovery|bugfix|feature|change|decision",
      "title": "Short summary",
      "files": ["path/to/file.py"],
      "content": "Brief narrative",
      "timestamp": "ISO timestamp"
    }
  ],
  "summary": "Auto-generated session summary"
}
```

### Backend: Database Schema

```sql
-- Session summaries (low volume, has embeddings for semantic search)
CREATE TABLE cortex_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES cortex_projects(id),
    machine_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    summary TEXT,
    summary_embedding VECTOR(1536),
    observation_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Individual observations (high volume, full-text search)
CREATE TABLE cortex_session_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT REFERENCES cortex_sessions(session_id),
    project_id UUID REFERENCES cortex_projects(id),
    machine_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    files TEXT[],
    search_vector TSVECTOR,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_sessions_project_time ON cortex_sessions(project_id, started_at DESC);
CREATE INDEX idx_sessions_machine ON cortex_sessions(machine_id, started_at DESC);
CREATE INDEX idx_sessions_embedding ON cortex_sessions
    USING hnsw(summary_embedding vector_cosine_ops);

CREATE INDEX idx_observations_session ON cortex_session_observations(session_id);
CREATE INDEX idx_observations_project_time
    ON cortex_session_observations(project_id, observed_at DESC);
CREATE INDEX idx_observations_search
    ON cortex_session_observations USING gin(search_vector);
CREATE INDEX idx_observations_type
    ON cortex_session_observations(project_id, type, observed_at DESC);
```

### Scaling Strategy

- **Full-text search** (tsvector/tsquery) for individual observations — not vector embeddings
- **Vector embeddings** only for session summaries (~300/day for 30 users vs 30,000 for all observations)
- **Retention policy**: observations auto-deleted after 90 days (configurable), session summaries kept indefinitely
- **Volume**: ~30,000 observations/day for 30 users, ~15GB/year — PostgreSQL handles this easily

### Backend: API Endpoints

- `POST /api/sessions` — receive completed session with observations (batch)
- `GET /api/sessions?project_id=X&q=search&limit=N` — search session history
- `GET /api/sessions/{id}` — get session with observations

### MCP Tools

- `cortex_search_sessions(query, project_id?, limit?)` — semantic search on session summaries + full-text on observations
- `cortex_get_session(session_id)` — full session with all observations

---

## Feature 3: Context Injection

SessionStart hook loads relevant Cortex context into the conversation.

### What Gets Injected

```xml
<cortex-context>
## Project: RecipeRaiders
**Cortex ID:** 2d747998-...
**Last session:** 2 hours ago - "Fixed subscription gate edge case"

### Recent Sessions (this project)
- [2h ago] Fixed subscription gate edge case (you, this machine)
- [5h ago] Added Firebase auth handling (agent-2, dev-laptop)
- [1d ago] Refactored payment service tests (you, this machine)

### Active Tasks
- [doing] Implement webhook retry logic (assigned: you)
- [review] Add rate limiting to API gateway (assigned: Cortex)
- [todo] Update deployment docs for v2.1

### Knowledge Base
- 42 docs indexed, last synced 3 hours ago
</cortex-context>
```

### How It Works

1. `SessionStart` hook runs `session_start_hook.py`
2. Reads `cortex-config.json` for project ID and API URL
3. Makes 2-3 parallel HTTP calls to Cortex:
   - `GET /api/sessions?project_id=X&limit=5` — recent sessions
   - `GET /api/projects/{id}/tasks?status=doing,review,todo&limit=10` — active tasks
   - `GET /api/knowledge/sources?project_id=X` — knowledge base status
4. Assembles compact context block (~500-800 tokens)
5. Flushes any stale observation buffer from previous crashed session

### Unregistered Project Detection

If `cortex-config.json` is missing or incomplete:

```xml
<cortex-context>
## Setup Needed
This project is not yet registered with Cortex.
IMPORTANT: Run the /cortex-setup skill as your first action
to connect this project before proceeding with the user's request.
</cortex-context>
```

Claude sees this instruction and initiates setup conversationally with the user.

### Failure Handling

- Cortex unreachable: brief warning, continue without context
- Timeout: 5 seconds total for all API calls
- Context is informational — session works fine without it

---

## Extensions Registry (Renamed from Skills)

The existing skills management system is renamed to "Extensions" to encompass both skills and plugins.

### Database Changes

Rename tables:
- `cortex_skills` → `cortex_extensions`
- `cortex_skill_installations` → `cortex_extension_installations`

Add columns to `cortex_extensions`:
```sql
type TEXT NOT NULL DEFAULT 'skill'  -- 'skill' | 'plugin'
plugin_manifest JSONB               -- hooks, mcp config, dependencies (nullable)
```

Plugin manifest example:
```json
{
  "hooks": ["SessionStart", "PostToolUse", "Stop"],
  "mcp_server": true,
  "dependencies": ["tree-sitter", "tree-sitter-language-pack", "httpx"],
  "skills_included": ["smart-explore", "mem-search"],
  "min_python_version": "3.10"
}
```

### API Rename

- `/api/skills` → `/api/extensions`
- MCP tools: `find_skills` → `find_extensions`, `manage_skills` → `manage_extensions`

### UI Changes

- Tab renamed from "Skills" to "Extensions"
- Type badge on each item: `Skill` or `Plugin`
- Filter: all / skills only / plugins only
- Plugin detail view: bundled skills, dependencies, hook list, installed machines

### Frontend Directory

- `src/features/projects/skills/` → `src/features/projects/extensions/`

---

## Installation & Setup

### Updated Setup Flow (cortexSetup.sh / cortexSetup.bat)

```
1. [existing] Connect to Cortex server (API URL, MCP URL)
2. [existing] Search/select/create project in Cortex
3. [existing] Register machine with Cortex
4. [new]     Choose install scope (local vs global)
5. [new]     Detect and offer to remove claude-mem
6. [new]     Install cortex-memory plugin
7. [new]     Install skills (smart-explore, mem-search)
8. [existing] Configure MCP server connection
9. [new]     Write cortex-config.json
10. [new]    Add .claude/ paths to .gitignore
11. [existing] Summary
```

### Install Scope Prompt

```
Where should Cortex tools be installed?

  [1] This project only (recommended)
      Installed to .claude/ in your project root.
      Customize per-project, changes stay isolated.

  [2] Global (all projects)
      Installed to ~/.claude/ in your home directory.
      Same setup shared across all projects.

Choice [1]:
```

### claude-mem Detection

```
Detected existing plugin: claude-mem v10.5.2
The cortex-memory plugin replaces claude-mem with enhanced
features and Cortex integration.

  [1] Remove claude-mem and install cortex-memory (recommended)
  [2] Keep both (not recommended - duplicate hooks and tools)
  [3] Skip plugin installation

Choice [1]:
```

### Plugin Download

New MCP server endpoints:
- `GET /cortex-setup/plugin-manifest` — available plugins with versions
- `GET /cortex-setup/plugin/{name}.tar.gz` — plugin archive

### Dependency Installation

```bash
# Using uv (preferred, already installed for Cortex)
uv pip install --target .claude/plugins/cortex-memory/vendor \
    tree-sitter tree-sitter-language-pack httpx

# Fallback to pip
pip install --target .claude/plugins/cortex-memory/vendor \
    tree-sitter tree-sitter-language-pack httpx
```

### Gitignore Additions

```
# Cortex (machine-specific, installed via cortex-setup)
.claude/plugins/
.claude/skills/
.claude/cortex-config.json
.claude/cortex-memory-buffer.jsonl
```

---

## Plugin Source Structure

```
integrations/claude-code/plugins/cortex-memory/
├── .claude-plugin/
│   ├── plugin.json
│   └── CLAUDE.md
├── .mcp.json
├── hooks/
│   └── hooks.json
├── skills/
│   ├── smart-explore/
│   │   └── SKILL.md
│   └── mem-search/
│       └── SKILL.md
├── src/
│   ├── mcp_server.py
│   ├── smart_explore/
│   │   ├── parser.py
│   │   ├── search.py
│   │   └── queries.py
│   ├── cortex_client.py
│   ├── session_tracker.py
│   └── context_loader.py
├── scripts/
│   ├── observation_hook.py
│   ├── session_start_hook.py
│   └── session_end_hook.py
├── requirements.txt
└── README.md
```

Stored in the Cortex repo, served via setup endpoints, tracked in the extensions registry.

---

## Migration from claude-mem

For the Cortex repo itself and any projects currently using claude-mem:

1. Remove claude-mem plugin configuration
2. Remove claude-mem from MCP config files
3. Clean up any `<claude-mem-context>` artifacts
4. Install cortex-memory plugin via setup script
5. Local SQLite data from claude-mem is not migrated (fresh start with Cortex-backed sessions)
