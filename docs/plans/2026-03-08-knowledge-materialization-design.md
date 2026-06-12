# Knowledge Materialization Design

**Date**: 2026-03-08
**Status**: Approved
**Approach**: Service Pipeline (Approach 2)

## Overview

Enable Cortex agents to autonomously identify gaps in local repository context, query the global Vector DB/RAG archive, and materialize relevant information into permanent, version-controlled Markdown documentation within the project's `.cortex/` directory.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger model | Agent-initiated (autonomous) | Agents detect gaps during natural workflow |
| File location | Per-project repo (`.cortex/knowledge/`) | Immediate local benefit, version-controlled |
| Agent scope | Protocol in codebase-analyst + MCP tool for all agents | Hard-coded escalation + opportunistic use |
| Synthesis | PydanticAI SynthesizerAgent | Consistent with existing agent architecture |
| Promotion threshold | Agent judgment (no numeric cutoff) | Leverages LLM reasoning over arbitrary scores |
| Materialization frequency | Eager | Materialize every time useful remote knowledge found |
| Self-cleaning | Database tracking (`materialization_history` table) | Robust, supports UI, cross-project analytics |
| UI scope | Full integration (logs, knowledge filter, toasts) | Complete user visibility |

## 1. Database Schema

### New table: `cortex_materialization_history`

```sql
CREATE TABLE cortex_materialization_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    project_path TEXT NOT NULL,
    topic TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    source_ids TEXT[] DEFAULT '{}',
    original_urls TEXT[] DEFAULT '{}',
    synthesis_model TEXT,
    word_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',  -- pending | active | stale | archived
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    materialized_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_mat_history_project ON cortex_materialization_history(project_id);
CREATE INDEX idx_mat_history_status ON cortex_materialization_history(status);
CREATE INDEX idx_mat_history_topic ON cortex_materialization_history(topic);
```

Migration: `018_add_materialization_history.sql`

## 2. Service Pipeline

### MaterializationService (`python/src/server/services/knowledge/materialization_service.py`)

Orchestrator coordinating the full pipeline:

1. Receives `(topic, project_id, project_path, agent_context?)`
2. Checks `materialization_history` — skip if topic already materialized and `active`
3. Calls RAG search via existing `RAGService`
4. Passes chunks to `SynthesizerAgent`
5. Calls `IndexerService` to write file and update index
6. Logs to `materialization_history` table
7. Creates progress entry in `cortex_progress`
8. Returns `{success, file_path, filename, word_count}`

Key methods:
- `async materialize(topic, project_id, project_path, progress_id?) -> MaterializationResult`
- `async check_existing(topic, project_id) -> MaterializationRecord | None`
- `async mark_accessed(materialization_id) -> None`
- `async mark_stale(materialization_id) -> None`
- `async list_materializations(project_id?, status?) -> list[MaterializationRecord]`

### SynthesizerAgent (`python/src/agents/synthesizer_agent.py`)

PydanticAI agent that turns raw chunks into cohesive Markdown:

- Input: `SynthesizerDeps(topic, chunks: list[ChunkData], source_metadata: list[SourceInfo])`
- Output: `SynthesizedDocument(title, content, summary, source_urls, word_count)`
- System prompt instructs:
  - Produce clean Markdown with YAML frontmatter
  - Deduplicate overlapping chunk content
  - Organize logically with headers
  - Include source attribution
  - Keep it concise
- Uses configured `MODEL_CHOICE` from settings

### IndexerService (`python/src/server/services/knowledge/indexer_service.py`)

File writer and index maintainer:

- `async write_materialized_file(project_path, filename, content) -> str`
- `async update_index(project_path) -> None`
- `async remove_file(project_path, filename) -> None`

Writes to `{project_path}/.cortex/knowledge/{filename}`, creates directories if needed. Regenerates `.cortex/index.md` on every write/remove.

## 3. API Endpoints

### REST API (`python/src/server/api_routes/materialization_api.py`)

```
POST   /api/materialization/execute          — Kick off async materialization
GET    /api/materialization/history           — List with filters (project_id, status, page, per_page)
GET    /api/materialization/{id}              — Single record
PUT    /api/materialization/{id}/access       — Bump access_count and last_accessed_at
PUT    /api/materialization/{id}/status       — Update status (active/stale/archived)
DELETE /api/materialization/{id}              — Remove record, delete file, update index
GET    /api/materialization/progress/{id}     — Reuses cortex_progress polling
```

### MCP Tools (`python/src/mcp_server/features/materialization/materialization_tools.py`)

Following `find_*` / `manage_*` convention:

- **`materialize_knowledge`** — primary tool agents call
  - Input: `topic, project_id, project_path`
  - Calls `POST /api/materialization/execute`, polls progress
  - Returns: `{success, file_path, filename, summary, word_count}`

- **`find_materializations`** — query history
  - Input: `project_id?, status?, materialization_id?`
  - Returns list or single record

- **`manage_materialization`** — status changes
  - Input: `action: "mark_accessed" | "mark_stale" | "archive" | "delete", materialization_id`
  - Returns: `{success, message}`

## 4. Agent Prompt Update

### Codebase-Analyst Context Escalation Protocol

Added to `.claude/agents/codebase-analyst.md`:

```markdown
## Context Escalation Protocol

Before analyzing a topic:
1. Check .cortex/index.md and local project files for existing context
2. If the topic is missing or the local docs are insufficient:
   - Call materialize_knowledge with the topic and project details
   - Wait for materialization to complete
   - Read the newly created file
3. Continue analysis with the enriched local context
```

## 5. Frontend Integration

### KnowledgeView — "Materialized" filter

- New filter in `KnowledgeHeader.tsx` alongside knowledge_type filters
- `KnowledgeCard.tsx` gets "AI Materialized" badge
- Sub-feature: `features/knowledge/materialization/`
  - `useMaterializationQueries.ts` with `materializationKeys` factory
  - `materializationService.ts` wrapping REST endpoints

### ExecutionLogs — KNOWLEDGE_PROMOTION log type

- New log event type for materialization operations
- Progress entries appear in active operations list via `cortex_progress`
- Log entries: "Materializing: {topic} -> {project}/.cortex/knowledge/{filename}"

### Toast notifications

- On complete: "Cortex materialized '{topic}' to {project}/.cortex/knowledge/{filename}"
- On failure: "Failed to materialize '{topic}': {error}"
- Triggered by polling progress state transitions

### Data flow

```
useMaterializationQueries.ts
  -> materializationService.ts
    -> GET /api/materialization/history
    -> GET /api/materialization/progress/{id}
  -> STALE_TIMES.normal (30s) for history
  -> STALE_TIMES.frequent (5s) for active progress
```

## 6. File Format & Structure

### Materialized file format

```markdown
---
cortex_source: vector_archive
materialized_at: 2026-03-08T14:30:00Z
topic: "Auth Middleware Logic"
source_urls:
  - https://docs.external-api.com/v2/auth
source_ids:
  - abc123def456
synthesis_model: gpt-4.1-nano
materialization_id: 550e8400-e29b-41d4-a716-446655440000
---

# Auth Middleware Logic

[Synthesized content]

## Sources

- [External API Auth Docs](https://docs.external-api.com/v2/auth)
```

### Filename generation

Slugified from topic: "Auth Middleware Logic" -> `auth-middleware-logic.md`. Collision handling: append `-2`, `-3`.

### Directory structure

```
project-repo/
└── .cortex/
    ├── index.md
    └── knowledge/
        ├── auth-middleware-logic.md
        └── database-sharding.md
```

Both `index.md` and knowledge files are version-controlled.

## 7. End-to-End Flow

```
1. Agent reads .cortex/index.md -> topic not listed
2. Agent calls materialize_knowledge(topic, project_id, project_path)
3. MCP tool -> POST /api/materialization/execute
4. MaterializationService:
   a. Checks materialization_history -> no existing or pending record
   b. Creates pending record as concurrency claim
   c. Creates cortex_progress entry
   d. Calls RAGService.search_documents(topic)
   e. Filters chunks (min 50 chars to skip navigation fragments)
   f. Passes chunks to SynthesizerAgent
   g. SynthesizerAgent produces Markdown with frontmatter
   h. IndexerService writes file and regenerates index
   i. Updates pending record to active with final data
   j. Progress -> "completed"
5. MCP tool returns {success, file_path}
6. Agent reads new file, continues with enriched context
7. Frontend: toast, progress log, KnowledgeView updated
```

### Error cases

- **No relevant results**: Returns `{success: false, reason: "no_relevant_content"}`. Pending record deleted. No file.
- **All chunks too short**: After min-length filtering, no usable content. Same as no results.
- **Synthesis fails**: Pending record deleted. Progress marked `failed`. Agent falls back to raw search.
- **File write fails**: Pending record deleted. Progress marked `failed`.
- **Already materialized (active)**: Returns existing record. Bumps `access_count`.
- **Already pending (concurrent run)**: Returns early — another agent is already materializing this topic.

### Concurrency safety

The `pending` status acts as a lightweight claim. `check_existing` checks for both `active` and `pending` records, so concurrent agents for the same topic+project will see the pending record and skip. On failure, the pending record is deleted so retries can proceed.

### Chunk quality filtering

Before synthesis, chunks shorter than 50 characters are filtered out. This removes navigation fragments, breadcrumbs, and header-only chunks that would dilute synthesis quality.
