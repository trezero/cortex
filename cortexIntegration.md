# Cortex MCP Integration Guide for Coding Agents

## What This Does

Cortex is a knowledge management system with a RAG (Retrieval-Augmented Generation) pipeline. It exposes MCP tools that let coding agents:

1. **Ingest project documentation** into a vector store (markdown files, code patterns, architecture docs)
2. **Search semantically** across ingested docs instead of bulk-reading entire files
3. **Scope searches by project** so different repos' docs don't pollute each other

This replaces the pattern of reading 40+ documentation files per session with targeted semantic search that returns only relevant chunks.

## Connecting to Cortex

### MCP Server Details

- **Transport**: `streamable-http`
- **Default port**: `8051`
- **URL**: `http://<cortex-host>:8051/mcp`

### Claude Code Configuration

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

Replace `localhost` with the Cortex server's hostname/IP if running on a different machine.

### Cursor / Windsurf Configuration

Add to your MCP settings:

```json
{
  "cortex": {
    "url": "http://localhost:8051/mcp",
    "transport": "streamable-http"
  }
}
```

---

## Available Tools

| Tool | Purpose |
|------|---------|
| `manage_rag_source` | Add, sync, or delete knowledge sources |
| `rag_check_progress` | Poll async ingestion/sync progress |
| `rag_search_knowledge_base` | Semantic search across documentation |
| `rag_search_code_examples` | Search for code snippets |
| `rag_get_available_sources` | List all knowledge sources |
| `rag_list_pages_for_source` | Browse pages within a source |
| `rag_read_full_page` | Read complete page content |

---

## Workflow 1: Ingest Local Project Docs

This is the primary use case. Your coding agent reads local markdown files and sends their content to Cortex for embedding.

### Step 1: Read local files and build the documents payload

The agent reads `.md` files from the project and constructs a JSON array:

```json
[
  {
    "title": "userLogic.md",
    "content": "# User Logic\n\n## Overview\nHandles user authentication...",
    "path": "docs/architecture/platform/userLogic.md"
  },
  {
    "title": "subscriptions.md",
    "content": "# Subscriptions\n\n## Subscription Gates\n...",
    "path": "docs/architecture/subscriptions.md"
  }
]
```

Each document requires `title` (string) and `content` (string). The `path` field is optional — it's stored as metadata for reference but not used for retrieval.

### Step 2: Call `manage_rag_source` to ingest

```
manage_rag_source(
    action="add",
    source_type="inline",
    title="RecipeRaiders Documentation",
    documents='[{"title": "userLogic.md", "content": "# User Logic\n...", "path": "docs/architecture/platform/userLogic.md"}, ...]',
    tags=["RecipeRaiders", "docs"],
    project_id="proj-abc123",
    knowledge_type="technical",
    extract_code_examples=true
)
```

**Parameters:**
- `action`: Must be `"add"`
- `source_type`: Must be `"inline"` for local files
- `title`: A human-readable name for this source
- `documents`: A **list of document objects** or a **JSON string**. Most MCP clients auto-serialize, so passing a native list works. A JSON string is also accepted and will be parsed server-side
- `tags`: Optional list of tags for categorization
- `project_id`: Optional — associates this source with an Cortex project so searches can be scoped
- `knowledge_type`: Defaults to `"technical"`. Any string is accepted
- `extract_code_examples`: Defaults to `true`. Set `false` to skip code block extraction

**Response:**
```json
{
  "success": true,
  "progress_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_id": "a3f2e1b4c5d67890",
  "estimated_seconds": 42,
  "message": "Ingestion started for 'RecipeRaiders Documentation'. Poll rag_check_progress(progress_id='550e8400-...') for status."
}
```

Save `progress_id` and `source_id` from this response.

### Step 3: Poll for completion

Embedding is async. Poll until `status` is `"completed"`:

```
rag_check_progress(progress_id="550e8400-e29b-41d4-a716-446655440000")
```

**In-progress response:**
```json
{
  "success": true,
  "status": "processing",
  "progress": 45,
  "documents_processed": 19,
  "documents_total": 42,
  "log": "Storing batch 3/8"
}
```

**Completed response:**
```json
{
  "success": true,
  "status": "completed",
  "progress": 100,
  "documents_processed": 42,
  "documents_total": 42,
  "log": "Completed",
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

**Status values:** `"starting"` | `"processing"` | `"document_storage"` | `"completed"` | `"failed"` | `"error"`

Poll every 3-5 seconds. Progress data is cleaned up ~30 seconds after completion — if you get a 404, the operation already finished.

### Step 4: Search the ingested docs

```
rag_search_knowledge_base(
    query="subscription gates",
    project_id="proj-abc123",
    match_count=5,
    return_mode="pages"
)
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "page_id": "uuid-here",
      "url": "inline://a3f2e1b4c5d67890/docs/architecture/subscriptions.md",
      "title": "subscriptions.md",
      "preview": "## Subscription Gates\n\nSubscription gates control access to premium features...",
      "word_count": 1250,
      "chunk_matches": 3
    }
  ],
  "return_mode": "pages"
}
```

### Step 5: Read full page content if needed

```
rag_read_full_page(page_id="uuid-here")
```

Returns the complete document content.

---

## Workflow 2: Ingest a URL

For public documentation sites:

```
manage_rag_source(
    action="add",
    source_type="url",
    title="FastAPI Docs",
    url="https://fastapi.tiangolo.com",
    tags=["fastapi", "reference"],
    project_id="proj-abc123"
)
```

This triggers Cortex's web crawler. The response includes `progress_id` — poll the same way as inline ingestion.

---

## Workflow 3: Update Docs After Changes

When project docs are updated, **do not call `add` again** — that creates a duplicate source. Use `sync`:

```
manage_rag_source(
    action="sync",
    source_id="a3f2e1b4c5d67890",
    force=false
)
```

- `force=false` (default): Only re-embeds changed content
- `force=true`: Re-chunks and re-embeds everything

Get the `source_id` from the original `add` response, or look it up:

```
rag_get_available_sources()
```

**Note:** Sync for inline sources re-uses the existing crawl/refresh pipeline. For inline sources that need content updates, the most reliable approach is to delete and re-add.

---

## Workflow 4: Remove a Source

```
manage_rag_source(
    action="delete",
    source_id="a3f2e1b4c5d67890"
)
```

Deletes the source and all associated documents, chunks, embeddings, and code examples.

---

## Workflow 5: Search Code Examples

Cortex extracts and indexes code blocks from ingested documentation:

```
rag_search_code_examples(
    query="React useState",
    project_id="proj-abc123",
    match_count=5
)
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "language": "typescript",
      "code": "const [count, setCount] = useState(0);\n...",
      "summary": "React useState hook for managing component state",
      "relevance": 0.92
    }
  ]
}
```

---

## Workflow 6: Browse Documentation Structure

Instead of searching, browse the page structure of a source:

```
rag_get_available_sources()
→ pick source_id

rag_list_pages_for_source(source_id="a3f2e1b4c5d67890")
→ see all pages with titles and word counts

rag_read_full_page(page_id="uuid-from-list")
→ read complete page
```

---

## Complete Tool Reference

### manage_rag_source

| Parameter | Type | Default | When Required |
|-----------|------|---------|---------------|
| `action` | `str` | — | Always. `"add"` / `"sync"` / `"delete"` |
| `title` | `str` | `None` | `action="add"` |
| `source_type` | `str` | `None` | `action="add"`. `"inline"` / `"url"` |
| `documents` | `list` or `str` | `None` | `action="add"` + `source_type="inline"`. List or JSON string |
| `url` | `str` | `None` | `action="add"` + `source_type="url"` |
| `tags` | `list[str]` | `None` | Never |
| `project_id` | `str` | `None` | Never |
| `knowledge_type` | `str` | `"technical"` | Never |
| `extract_code_examples` | `bool` | `true` | Never |
| `source_id` | `str` | `None` | `action="sync"` or `action="delete"` |
| `force` | `bool` | `false` | Never |

### rag_check_progress

| Parameter | Type | Default | When Required |
|-----------|------|---------|---------------|
| `progress_id` | `str` | — | Always |

### rag_search_knowledge_base

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | — | 2-5 keyword search. Short and focused |
| `source_id` | `str` | `None` | Filter to one source |
| `project_id` | `str` | `None` | Filter to all sources in a project |
| `match_count` | `int` | `5` | Max results |
| `return_mode` | `str` | `"pages"` | `"pages"` (recommended) or `"chunks"` |

If both `source_id` and `project_id` are provided, `source_id` takes precedence.

### rag_search_code_examples

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | — | 2-5 keyword search |
| `source_id` | `str` | `None` | Filter to one source |
| `project_id` | `str` | `None` | Filter to all sources in a project |
| `match_count` | `int` | `5` | Max results |

### rag_get_available_sources

No parameters. Returns all sources with their IDs, titles, tags, and metadata.

### rag_list_pages_for_source

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_id` | `str` | — | From `rag_get_available_sources()` |
| `section` | `str` | `None` | Filter by section title |

### rag_read_full_page

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page_id` | `str` | `None` | UUID from search results or page listing |
| `url` | `str` | `None` | Page URL (alternative to page_id) |

Provide either `page_id` or `url`, not both.

---

## Search Tips

- **Keep queries short**: 2-5 keywords work best. `"subscription gates"` not `"how do subscription gates work in the payment system"`
- **Use project_id for scoping**: If you tagged sources with a project, use `project_id` to avoid cross-project noise
- **Use return_mode="pages" first**: Get an overview of matching pages, then read full content for the most relevant ones
- **Code search is separate**: Use `rag_search_code_examples` specifically for code snippets — it searches an index of extracted code blocks with AI-generated summaries

---

## Error Handling

All tools return JSON with `"success": true/false`. On failure:

```json
{
  "success": false,
  "error": {
    "type": "validation_error",
    "message": "title is required for add action",
    "suggestion": "..."
  }
}
```

Error types: `validation_error`, `not_found`, `http_error`, `connection_error`, `request_error`

Common issues:
- **Connection refused**: Cortex server not running. Start with `docker compose up -d`
- **API key validation failed**: Embedding provider (OpenAI/Ollama) not configured in Cortex settings
- **Progress not found (404)**: Operation completed >30s ago and was cleaned up. Check `rag_get_available_sources()` to verify the source was created

---

## Example: Full Session Integration

Here is a complete example of how a coding agent should integrate Cortex into a development session:

```
# 1. Check if project docs are already ingested
sources = rag_get_available_sources()
# Look for a source matching this project

# 2. If not found, ingest the docs
#    (Agent reads all .md files from docs/ directory first)
result = manage_rag_source(
    action="add",
    source_type="inline",
    title="MyProject Documentation",
    documents='[{"title": "auth.md", "content": "...", "path": "docs/auth.md"}, ...]',
    tags=["myproject"],
    project_id="proj-123"
)
progress_id = result.progress_id
source_id = result.source_id

# 3. Wait for ingestion to complete
while True:
    status = rag_check_progress(progress_id=progress_id)
    if status.status in ("completed", "failed", "error"):
        break
    # wait 3-5 seconds

# 4. During development, search instead of reading entire files
results = rag_search_knowledge_base(
    query="authentication middleware",
    project_id="proj-123"
)

# 5. Read full content of the most relevant page
page = rag_read_full_page(page_id=results[0].page_id)

# 6. Search for code patterns
code = rag_search_code_examples(
    query="JWT token validation",
    project_id="proj-123"
)
```

---

## Key Constraints

- **documents parameter accepts both a native list and a JSON string**. Most MCP transports auto-deserialize JSON strings to native types, so passing a list directly works. A JSON string is also accepted as a fallback
- **source_id is a 16-character hex hash**, not a URL. Always get it from `rag_get_available_sources()` or the `manage_rag_source(action="add")` response
- **Ingestion is async**. The `manage_rag_source(action="add")` call returns immediately. You must poll `rag_check_progress` to know when it's done
- **One add per document set**. Use `sync` to update, not `add` again. Repeated `add` calls create duplicate sources
- **Chunking is 5000 characters**. Documents are split into ~5000-char chunks with markdown header preservation. You don't control chunk size
- **Progress data expires**. Results from `rag_check_progress` are cleaned up ~30 seconds after the operation completes
