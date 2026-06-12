# MCP RAG Source Ingestion Design

## Problem

Cortex's MCP server exposes 5 read-only RAG tools for searching knowledge bases. There is no MCP tool to add, sync, or delete sources. Users must add sources through the web UI or API, which breaks the workflow when using Claude Code as the primary interface.

## Solution

Add two new MCP tools (`manage_rag_source` and `rag_check_progress`) that enable MCP clients to ingest local project documentation, sync existing sources, and delete sources — all through the existing MCP interface.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Ingestion mode | Inline content + URL | Inline works across machines (MCP client reads files locally, sends content). URL reuses existing crawl pipeline. Directory mode skipped — unreliable across network boundaries. |
| Chunk size | Existing 5000-char pipeline | Keeps all sources consistent. Existing RAG search is tuned for this size. |
| Project scoping | `metadata` JSONB column | No database migration needed. Queryable via `metadata->>'project_id'`. Consistent with how tags/knowledge_type are stored. |
| Batch mode | Batch of documents per call | Primary use case is ingesting entire doc directories (20-40+ files). Single-doc-per-call wastes agentic turns and context window. Per-document status reporting handles partial failures. |
| Sync vs async | Async with progress_id | Batch embedding regularly exceeds 30 seconds. Async prevents timeout failures and lets work complete if the session disconnects. Reuses existing ProgressTracker infrastructure. |
| Tool pattern | Consolidated `manage_rag_source` | Follows existing `find_*/manage_*` convention (manage_project, manage_task, manage_document). Two tools instead of four. |
| Header preservation | Already handled | Existing chunking pipeline extracts markdown headers via regex and stores as `headers` metadata on each chunk. No changes needed. |

## MCP Tools

### `manage_rag_source`

Consolidated source management with 3 actions: `add`, `sync`, `delete`.

```python
@mcp.tool()
async def manage_rag_source(
    ctx: Context,
    action: str,                          # "add" | "sync" | "delete"
    # For "add" action:
    title: str | None = None,             # Source title (required for add)
    source_type: str | None = None,       # "inline" | "url" (required for add)
    documents: str | None = None,         # JSON string of [{title, content, path?}] for inline
    url: str | None = None,               # For url mode — triggers existing crawl pipeline
    tags: list[str] | None = None,        # e.g. ["RecipeRaiders", "docs"]
    project_id: str | None = None,        # Stored in source metadata JSONB
    knowledge_type: str = "technical",    # Knowledge classification
    extract_code_examples: bool = True,   # Extract and index code blocks
    # For "sync" action:
    source_id: str | None = None,         # Required for sync/delete
    force: bool = False,                  # Re-chunk everything vs incremental
    # For "delete" action:
    # source_id required (same param as sync)
) -> str:
```

**Action: "add" with source_type="inline"**

Accepts a batch of documents as a JSON string. Each document has:
- `title` (required): Filename or section title, e.g. `"userLogic.md"`
- `content` (required): Full markdown content
- `path` (optional): Original file path for reference, e.g. `"docs/architecture/platform/userLogic.md"`

Example `documents` parameter:
```json
[
  {"title": "userLogic.md", "content": "# User Logic\n\n## Overview\n...", "path": "docs/architecture/platform/userLogic.md"},
  {"title": "subscriptions.md", "content": "# Subscriptions\n...", "path": "docs/architecture/subscriptions.md"}
]
```

Returns: `{success, progress_id, source_id, estimated_seconds}`

**Action: "add" with source_type="url"**

Triggers the existing crawl pipeline. The `url` parameter is required.

Returns: `{success, progress_id, source_id, estimated_seconds}`

**Action: "sync"**

Re-ingests an existing source. The `source_id` parameter is required (from `rag_get_available_sources()`).
- `force=False` (default): Only re-embeds if content has changed
- `force=True`: Re-chunks and re-embeds everything

Returns: `{success, progress_id, estimated_seconds}`

**Action: "delete"**

Removes a source and all its associated documents, chunks, embeddings, and code examples. The `source_id` parameter is required.

Returns: `{success, message}`

### `rag_check_progress`

Polls progress for async operations started by `manage_rag_source`.

```python
@mcp.tool()
async def rag_check_progress(
    ctx: Context,
    progress_id: str,                     # From manage_rag_source response
) -> str:
```

Returns:
```json
{
  "success": true,
  "status": "processing",
  "progress": 65,
  "documents_processed": 28,
  "documents_total": 42,
  "estimated_remaining_seconds": 15,
  "results": null
}
```

Terminal states include a `results` array with per-document status:
```json
{
  "success": true,
  "status": "completed",
  "progress": 100,
  "documents_processed": 42,
  "documents_total": 42,
  "results": {
    "source_id": "a3f2e1b4c5d67890",
    "ingested": 41,
    "failed": 1,
    "failures": [{"title": "broken.md", "error": "empty content"}],
    "chunks_stored": 287,
    "code_examples_stored": 34
  }
}
```

### Enhanced: `rag_search_knowledge_base` and `rag_search_code_examples`

Add optional `project_id` parameter to both existing tools:

```python
async def rag_search_knowledge_base(
    ctx: Context,
    query: str,
    source_id: str | None = None,         # Existing — filter by specific source
    project_id: str | None = None,        # NEW — filter by project (all sources tagged to project)
    match_count: int = 5,
    return_mode: str = "pages"
) -> str:
```

When `project_id` is provided:
1. Query `cortex_sources` where `metadata->>'project_id' = ?` to collect source_ids
2. Pass source_ids as IN clause to the vector search
3. Single query, no N+1

## Backend API

### New Endpoint: `POST /api/knowledge/ingest-inline`

Request body:
```json
{
  "title": "RecipeRaiders Documentation",
  "documents": [
    {"title": "userLogic.md", "content": "# User Logic\n...", "path": "docs/architecture/platform/userLogic.md"},
    {"title": "subscriptions.md", "content": "# Subscriptions\n...", "path": "docs/architecture/subscriptions.md"}
  ],
  "tags": ["RecipeRaiders", "docs"],
  "project_id": "proj-abc123",
  "knowledge_type": "technical",
  "extract_code_examples": true
}
```

Response:
```json
{
  "success": true,
  "progressId": "uuid-here",
  "sourceId": "a3f2e1b4c5d67890",
  "estimatedSeconds": 45
}
```

Processing pipeline (async, background task):
1. Generate `source_id` from `sha256(title + "-" + iso_timestamp)[:16]`
2. Create source record in `cortex_sources` with `project_id` in metadata JSONB
3. For each document:
   a. Create page record in `cortex_page_metadata` (full content, section title from doc title)
   b. Chunk content using existing `smart_chunk_text_async()` (5000 chars)
   c. Track per-document status
4. Batch embed all chunks using existing embedding pipeline
5. Optionally extract and embed code examples
6. Update progress throughout via existing ProgressTracker

### Modified Endpoint: `POST /api/rag/query`

Add optional `project_id` to the request body. When provided:
1. Query `cortex_sources` for matching `metadata->>'project_id'`
2. Collect source_ids
3. Filter vector search results to those source_ids

## Source ID Generation

For inline sources (no URL to hash from):
- `sha256(title + "-" + iso_timestamp)[:16]`
- Same 16-char hex format as URL-based sources
- Stored with `source_type: "inline"` in metadata

**Duplicate prevention**: Each `manage_rag_source(action="add")` creates a new source. To update existing docs, use `action="sync"` with the `source_id` from the original add. MCP tool documentation will clearly state this workflow:
> Use "add" once per doc set, then "sync" for updates. Calling "add" repeatedly creates duplicate sources.

## Data Flow

```
Claude Code session on RecipeRaiders project
  │
  │  1. Read local .md files (42 files from docs/)
  │  2. Build documents array
  │
  ▼
manage_rag_source(action="add", source_type="inline",
    title="RecipeRaiders Documentation",
    documents='[{"title": "userLogic.md", "content": "...", "path": "docs/..."}]',
    tags=["RecipeRaiders"], project_id="proj-abc123")
  │
  │  HTTP POST → /api/knowledge/ingest-inline
  │  Returns {progress_id, source_id, estimated_seconds}
  │
  ▼
rag_check_progress(progress_id)  // Poll until status="completed"
  │
  │  Returns per-document status + final counts
  │
  ▼
rag_search_knowledge_base(query="subscription gates",
    project_id="proj-abc123")
  │
  │  Searches only RecipeRaiders sources
  │  Returns relevant chunks with headers metadata
  │
  ▼
Later: rag_sync_source after docs are updated
  manage_rag_source(action="sync", source_id="a3f2e1b4c5d67890")
```

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `python/src/mcp_server/features/rag/rag_tools.py` | Modified | Add `manage_rag_source` and `rag_check_progress` tools. Add `project_id` param to search tools. |
| `python/src/server/api_routes/knowledge_api.py` | Modified | Add `POST /api/knowledge/ingest-inline` endpoint. Add `project_id` support to RAG query endpoint. |
| `python/src/server/services/storage/document_storage_service.py` | Modified | Add `ingest_inline_documents()` method that accepts document batch, reuses existing chunk/embed pipeline. |
| `python/src/mcp_server/mcp_server.py` | Modified | Update MCP server instructions to document new tools and ingestion workflow. |
| `python/src/server/services/search/rag_service.py` | Modified | Add `project_id` filtering — collect source_ids from metadata, pass as IN clause to vector search. |

## Not In Scope

- Directory mode (server reading local filesystem paths) — unreliable across network boundaries
- Configurable chunk sizes — use existing 5000-char pipeline for consistency
- Database migration for `project_id` column — use existing metadata JSONB
- WebSocket progress streaming — use existing HTTP polling with ProgressTracker
- Frontend UI for inline ingestion — MCP-only feature for now
