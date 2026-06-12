# MCP RAG Source Ingestion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `manage_rag_source` and `rag_check_progress` MCP tools to enable inline document ingestion, URL crawling, source sync, and deletion through the MCP interface.

**Architecture:** Two new MCP tools call new/existing API endpoints via HTTP. The inline ingestion endpoint accepts a batch of documents, chunks them using the existing 5000-char pipeline, embeds them asynchronously, and reports progress via the existing ProgressTracker. Project scoping uses the metadata JSONB column on `cortex_sources`.

**Tech Stack:** Python 3.12, FastAPI, FastMCP, httpx, Supabase, existing embedding pipeline

**Design doc:** `docs/plans/2026-03-01-mcp-rag-ingestion-design.md`

---

### Task 1: Add `POST /api/knowledge/ingest-inline` Pydantic Models

**Files:**
- Modify: `python/src/server/api_routes/knowledge_api.py` (after `RagQueryRequest` at line ~180)

**Step 1: Add request model**

Add after the `RagQueryRequest` class (line ~180):

```python
class InlineDocument(BaseModel):
    """A single document to ingest inline."""
    title: str
    content: str
    path: str | None = None


class InlineIngestRequest(BaseModel):
    """Request to ingest a batch of inline documents."""
    title: str  # Source title
    documents: list[InlineDocument]
    tags: list[str] = []
    project_id: str | None = None
    knowledge_type: str = "technical"
    extract_code_examples: bool = True
```

**Step 2: Commit**

```bash
git add python/src/server/api_routes/knowledge_api.py
git commit -m "feat: add Pydantic models for inline document ingestion"
```

---

### Task 2: Add `POST /api/knowledge/ingest-inline` Endpoint

**Files:**
- Modify: `python/src/server/api_routes/knowledge_api.py` (add endpoint after the upload endpoint, around line ~972)

**Step 1: Add the endpoint and its background task**

Add the background task function and endpoint. The endpoint:
1. Validates the request (non-empty documents, non-empty content)
2. Validates embedding provider API key (reuse `_validate_provider_api_key`)
3. Generates `source_id` from `sha256(title + "-" + iso_timestamp)[:16]`
4. Generates `progress_id` (UUID)
5. Initializes ProgressTracker
6. Spawns background task
7. Returns immediately with `{success, progressId, sourceId, estimatedSeconds}`

Add these imports at the top of the file (some may already exist):
```python
import hashlib
from datetime import datetime, timezone
```

Add the endpoint function:

```python
@router.post("/knowledge/ingest-inline")
async def ingest_inline_documents(request: InlineIngestRequest):
    """Ingest a batch of inline documents into the knowledge base."""
    # Validate request
    if not request.documents:
        raise HTTPException(status_code=422, detail="At least one document is required")

    # Filter out empty documents
    valid_docs = [doc for doc in request.documents if doc.content and doc.content.strip()]
    if not valid_docs:
        raise HTTPException(status_code=422, detail="All documents have empty content")

    # Validate API key
    await _validate_provider_api_key()

    # Generate source_id from title + timestamp
    timestamp = datetime.now(timezone.utc).isoformat()
    source_id = hashlib.sha256(f"{request.title}-{timestamp}".encode()).hexdigest()[:16]

    # Generate progress_id
    progress_id = str(uuid.uuid4())

    # Estimate completion time (~1 second per document for embedding)
    estimated_seconds = max(10, len(valid_docs) * 1)

    # Initialize progress tracker
    from ..utils.progress.progress_tracker import ProgressTracker
    tracker = ProgressTracker(progress_id, operation_type="inline_ingest")
    await tracker.start({
        "source_id": source_id,
        "title": request.title,
        "total_documents": len(valid_docs),
        "status": "starting",
    })

    # Spawn background task
    task = asyncio.create_task(
        _perform_inline_ingest(
            progress_id=progress_id,
            source_id=source_id,
            request=request,
            valid_docs=valid_docs,
            tracker=tracker,
        )
    )
    active_crawl_tasks[progress_id] = task

    return {
        "success": True,
        "progressId": progress_id,
        "sourceId": source_id,
        "estimatedSeconds": estimated_seconds,
    }
```

**Step 2: Add the background task function**

Add above the endpoint (or near `_perform_crawl_with_progress`):

```python
async def _perform_inline_ingest(
    progress_id: str,
    source_id: str,
    request: InlineIngestRequest,
    valid_docs: list[InlineDocument],
    tracker,
):
    """Perform inline document ingestion with progress tracking."""
    async with crawl_semaphore:
        try:
            supabase_client = get_supabase_client()
            total_docs = len(valid_docs)

            await tracker.update(
                status="processing",
                progress=5,
                log=f"Processing {total_docs} documents",
            )

            # Build crawl_results in the format DocumentStorageOperations expects
            crawl_results = []
            doc_failures = []

            for i, doc in enumerate(valid_docs):
                content = doc.content.strip()
                if not content:
                    doc_failures.append({"title": doc.title, "error": "empty content"})
                    continue

                # Create a synthetic URL for this document using path or title
                doc_path = doc.path or doc.title
                synthetic_url = f"inline://{source_id}/{doc_path}"

                crawl_results.append({
                    "url": synthetic_url,
                    "markdown": content,
                    "title": doc.title,
                    "description": "",
                })

                doc_progress = int(5 + (i + 1) / total_docs * 15)  # 5-20%
                await tracker.update(
                    status="processing",
                    progress=doc_progress,
                    log=f"Prepared document {i + 1}/{total_docs}: {doc.title}",
                )

            if not crawl_results:
                await tracker.error("All documents failed validation")
                return

            # Use DocumentStorageOperations to chunk, embed, and store
            from ..services.crawling.document_storage_operations import DocumentStorageOperations
            storage_ops = DocumentStorageOperations(supabase_client)

            # Build the request dict matching what process_and_store_documents expects
            request_dict = {
                "knowledge_type": request.knowledge_type,
                "tags": request.tags or [],
                "extract_code_examples": request.extract_code_examples,
                "generate_summary": False,  # Skip AI summary for inline docs
            }

            # Add project_id to metadata if provided
            if request.project_id:
                request_dict["project_id"] = request.project_id

            async def storage_progress_callback(status, progress, message, **kwargs):
                # Map storage progress from 20-90%
                mapped_progress = int(20 + progress * 0.7)
                await tracker.update(
                    status=status,
                    progress=mapped_progress,
                    log=message,
                )

            result = await storage_ops.process_and_store_documents(
                crawl_results=crawl_results,
                request=request_dict,
                crawl_type="inline",
                original_source_id=source_id,
                progress_callback=storage_progress_callback,
                source_url=f"inline://{source_id}",
                source_display_name=request.title,
            )

            # Update source metadata with project_id and source_type
            try:
                existing = supabase_client.table("cortex_sources").select("metadata").eq(
                    "source_id", source_id
                ).execute()
                if existing.data:
                    metadata = existing.data[0].get("metadata", {}) or {}
                    metadata["source_type"] = "inline"
                    metadata["ingestion_method"] = "mcp_inline"
                    if request.project_id:
                        metadata["project_id"] = request.project_id
                    supabase_client.table("cortex_sources").update(
                        {"metadata": metadata}
                    ).eq("source_id", source_id).execute()
            except Exception as e:
                logger.warning(f"Failed to update source metadata: {e}")

            chunks_stored = result.get("chunks_stored", 0)
            code_examples_stored = result.get("code_examples_count", 0)

            await tracker.complete({
                "source_id": source_id,
                "ingested": len(crawl_results),
                "failed": len(doc_failures),
                "failures": doc_failures,
                "chunks_stored": chunks_stored,
                "code_examples_stored": code_examples_stored,
            })

        except asyncio.CancelledError:
            logger.info(f"Inline ingest cancelled | progress_id={progress_id}")
            raise
        except Exception as e:
            error_message = f"Inline ingestion failed: {str(e)}"
            logger.error(f"Inline ingest error | progress_id={progress_id} | error={error_message}", exc_info=True)
            try:
                await tracker.error(error_message)
            except Exception:
                pass
        finally:
            if progress_id in active_crawl_tasks:
                del active_crawl_tasks[progress_id]
```

**Step 3: Commit**

```bash
git add python/src/server/api_routes/knowledge_api.py
git commit -m "feat: add POST /api/knowledge/ingest-inline endpoint with async processing"
```

---

### Task 3: Add `project_id` Filtering to RAG Query

**Files:**
- Modify: `python/src/server/api_routes/knowledge_api.py` (line ~176, `RagQueryRequest`)
- Modify: `python/src/server/services/search/rag_service.py` (line ~244, `perform_rag_query`)

**Step 1: Add `project_id` to `RagQueryRequest`**

In `knowledge_api.py`, modify `RagQueryRequest` (line ~176):

```python
class RagQueryRequest(BaseModel):
    query: str
    source: str | None = None
    project_id: str | None = None  # NEW: filter by project
    match_count: int = 5
    return_mode: str = "chunks"  # "chunks" or "pages"
```

**Step 2: Update the RAG query endpoint to resolve project_id to source_ids**

In `knowledge_api.py`, modify `perform_rag_query` (line ~1109). After the query validation (line ~1117) and before the RAGService call (line ~1121), add project_id resolution:

```python
    # Resolve project_id to source filter
    source_filter = request.source
    if request.project_id and not source_filter:
        try:
            project_sources = get_supabase_client().table("cortex_sources").select(
                "source_id"
            ).filter(
                "metadata->>project_id", "eq", request.project_id
            ).execute()
            if project_sources.data:
                # Use comma-separated source_ids for multi-source filtering
                source_filter = ",".join(s["source_id"] for s in project_sources.data)
        except Exception as e:
            logger.warning(f"Failed to resolve project_id to sources: {e}")
```

Then pass `source_filter` instead of `request.source` to `search_service.perform_rag_query()`.

**Step 3: Update RAGService to handle multiple source_ids**

In `rag_service.py`, modify `perform_rag_query` (line ~244). Update the filter_metadata construction (line ~271):

```python
# Build filter metadata
if source:
    if "," in source:
        # Multiple source_ids (from project_id resolution)
        filter_metadata = {"source_ids": source.split(",")}
    else:
        filter_metadata = {"source": source}
else:
    filter_metadata = None
```

Then update `search_documents` (the base search strategy) to handle the `source_ids` key with an IN clause. Check how `filter_metadata` is currently consumed in the base search strategy and add the multi-source case.

**Step 4: Do the same for `search_code_examples`**

Apply the same `project_id` resolution pattern to the `/rag/code-examples` endpoint (line ~1146) and `search_code_examples_service` method (line ~380).

**Step 5: Commit**

```bash
git add python/src/server/api_routes/knowledge_api.py python/src/server/services/search/rag_service.py
git commit -m "feat: add project_id filtering to RAG search endpoints"
```

---

### Task 4: Add `manage_rag_source` MCP Tool

**Files:**
- Modify: `python/src/mcp_server/features/rag/rag_tools.py` (add after existing tools, before the log statement at line ~361)

**Step 1: Add the `manage_rag_source` tool**

Add inside `register_rag_tools()`, after the last existing tool (`rag_read_full_page`):

```python
    @mcp.tool()
    async def manage_rag_source(
        ctx: Context,
        action: str,
        title: str | None = None,
        source_type: str | None = None,
        documents: str | None = None,
        url: str | None = None,
        tags: list[str] | None = None,
        project_id: str | None = None,
        knowledge_type: str = "technical",
        extract_code_examples: bool = True,
        source_id: str | None = None,
        force: bool = False,
    ) -> str:
        """
        Manage RAG knowledge base sources (consolidated: add/sync/delete).

        Args:
            action: "add" | "sync" | "delete"
            title: Source title (required for add)
            source_type: "inline" | "url" (required for add)
            documents: JSON string of documents for inline mode.
                Format: [{"title": "file.md", "content": "# Markdown...", "path": "docs/file.md"}]
                Each document must have "title" and "content". "path" is optional.
                Example: '[{"title": "auth.md", "content": "# Auth\\n## Overview\\n..."}]'
            url: URL to crawl (required for add with source_type="url")
            tags: Tags for categorization, e.g. ["project-name", "docs"]
            project_id: Associate source with an Cortex project for scoped searches
            knowledge_type: Classification (default: "technical")
            extract_code_examples: Extract and index code blocks (default: true)
            source_id: Source ID for sync/delete (from rag_get_available_sources)
            force: For sync: re-chunk everything (true) vs only changed (false)

        Workflow:
            1. Add source: manage_rag_source(action="add", title="My Docs", source_type="inline", documents='[...]')
            2. Poll progress: rag_check_progress(progress_id="...") until status="completed"
            3. Search: rag_search_knowledge_base(query="...", project_id="...")
            4. Update later: manage_rag_source(action="sync", source_id="...")
            5. Remove: manage_rag_source(action="delete", source_id="...")

        IMPORTANT: Use "add" once per document set. Use "sync" to update.
        Calling "add" repeatedly creates duplicate sources.

        Returns:
            JSON with {success, progress_id?, source_id?, estimated_seconds?, message?}
        """
        try:
            api_url = get_api_url()
            from src.mcp_server.utils.timeout_config import get_default_timeout, get_polling_timeout
            timeout = get_default_timeout()

            if action == "add":
                if not title:
                    return MCPErrorFormatter.format_error(
                        "validation_error", "title is required for add action"
                    )
                if not source_type or source_type not in ("inline", "url"):
                    return MCPErrorFormatter.format_error(
                        "validation_error", 'source_type must be "inline" or "url"'
                    )

                if source_type == "inline":
                    if not documents:
                        return MCPErrorFormatter.format_error(
                            "validation_error",
                            "documents is required for inline mode. "
                            'Format: \'[{"title": "file.md", "content": "# Content..."}]\''
                        )
                    try:
                        docs_list = json.loads(documents)
                        if not isinstance(docs_list, list) or not docs_list:
                            return MCPErrorFormatter.format_error(
                                "validation_error", "documents must be a non-empty JSON array"
                            )
                    except json.JSONDecodeError as e:
                        return MCPErrorFormatter.format_error(
                            "validation_error", f"Invalid JSON in documents parameter: {e}"
                        )

                    async with httpx.AsyncClient(timeout=get_polling_timeout()) as client:
                        response = await client.post(
                            urljoin(api_url, "/api/knowledge/ingest-inline"),
                            json={
                                "title": title,
                                "documents": docs_list,
                                "tags": tags or [],
                                "project_id": project_id,
                                "knowledge_type": knowledge_type,
                                "extract_code_examples": extract_code_examples,
                            },
                        )
                        if response.status_code == 200:
                            data = response.json()
                            return json.dumps({
                                "success": True,
                                "progress_id": data.get("progressId"),
                                "source_id": data.get("sourceId"),
                                "estimated_seconds": data.get("estimatedSeconds"),
                                "message": f"Ingestion started for '{title}'. "
                                           f"Poll rag_check_progress(progress_id='{data.get('progressId')}') for status.",
                            })
                        else:
                            return MCPErrorFormatter.from_http_error(response, "inline ingestion")

                elif source_type == "url":
                    if not url:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "url is required for url mode"
                        )
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            urljoin(api_url, "/api/knowledge-items/crawl"),
                            json={
                                "url": url,
                                "knowledge_type": knowledge_type,
                                "tags": tags or [],
                                "extract_code_examples": extract_code_examples,
                            },
                        )
                        if response.status_code == 200:
                            data = response.json()
                            return json.dumps({
                                "success": True,
                                "progress_id": data.get("progressId"),
                                "source_id": data.get("sourceId"),
                                "estimated_seconds": data.get("estimatedSeconds"),
                                "message": f"Crawl started for '{url}'. "
                                           f"Poll rag_check_progress(progress_id='{data.get('progressId')}') for status.",
                            })
                        else:
                            return MCPErrorFormatter.from_http_error(response, "url crawl")

            elif action == "sync":
                if not source_id:
                    return MCPErrorFormatter.format_error(
                        "validation_error",
                        "source_id is required for sync action. Get it from rag_get_available_sources()."
                    )
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        urljoin(api_url, f"/api/knowledge-items/{source_id}/refresh"),
                        json={"force": force},
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return json.dumps({
                            "success": True,
                            "progress_id": data.get("progressId"),
                            "estimated_seconds": data.get("estimatedSeconds"),
                            "message": f"Sync started for source '{source_id}'. "
                                       f"Poll rag_check_progress(progress_id='{data.get('progressId')}') for status.",
                        })
                    else:
                        return MCPErrorFormatter.from_http_error(response, "sync source")

            elif action == "delete":
                if not source_id:
                    return MCPErrorFormatter.format_error(
                        "validation_error",
                        "source_id is required for delete action. Get it from rag_get_available_sources()."
                    )
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.delete(
                        urljoin(api_url, f"/api/sources/{source_id}"),
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return json.dumps({
                            "success": True,
                            "message": data.get("message", f"Source {source_id} deleted"),
                        })
                    else:
                        return MCPErrorFormatter.from_http_error(response, "delete source")

            else:
                return MCPErrorFormatter.format_error(
                    "validation_error",
                    f'Invalid action "{action}". Must be "add", "sync", or "delete".'
                )

        except httpx.RequestError as e:
            return MCPErrorFormatter.from_exception(e, f"manage_rag_source ({action})")
        except Exception as e:
            logger.error(f"Error in manage_rag_source: {e}", exc_info=True)
            return MCPErrorFormatter.from_exception(e, f"manage_rag_source ({action})")
```

**Step 2: Add `MCPErrorFormatter` import**

At the top of `rag_tools.py`, add (if not already present):

```python
from src.mcp_server.utils.error_handling import MCPErrorFormatter
```

**Step 3: Commit**

```bash
git add python/src/mcp_server/features/rag/rag_tools.py
git commit -m "feat: add manage_rag_source MCP tool with add/sync/delete actions"
```

---

### Task 5: Add `rag_check_progress` MCP Tool

**Files:**
- Modify: `python/src/mcp_server/features/rag/rag_tools.py` (add after `manage_rag_source`)

**Step 1: Add the tool**

Add inside `register_rag_tools()`, after `manage_rag_source`:

```python
    @mcp.tool()
    async def rag_check_progress(
        ctx: Context,
        progress_id: str,
    ) -> str:
        """
        Check progress of an async RAG operation (ingestion, sync, or crawl).

        Args:
            progress_id: The progress ID returned by manage_rag_source

        Returns:
            JSON with {success, status, progress, documents_processed, documents_total,
                       estimated_remaining_seconds, results?}

            Status values: "starting", "processing", "document_storage", "completed", "failed", "error"

            When status is "completed", results contains:
            {source_id, ingested, failed, failures, chunks_stored, code_examples_stored}
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    urljoin(api_url, f"/api/crawl-progress/{progress_id}")
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "unknown")
                    progress = data.get("progress", 0)

                    result = {
                        "success": True,
                        "status": status,
                        "progress": progress,
                        "documents_processed": data.get("processed_pages", 0),
                        "documents_total": data.get("total_pages", 0),
                        "log": data.get("log", ""),
                    }

                    # Add estimated remaining time
                    if status not in ("completed", "failed", "error", "cancelled"):
                        if progress > 0:
                            # Rough estimate based on progress
                            elapsed_ratio = progress / 100.0
                            if elapsed_ratio > 0.1:
                                result["estimated_remaining_seconds"] = int(
                                    (1.0 - elapsed_ratio) / elapsed_ratio * 10
                                )

                    # Include completion results if done
                    if status == "completed":
                        result["results"] = data.get("result", data.get("results", {}))

                    if status in ("failed", "error"):
                        result["error"] = data.get("error", "Unknown error")

                    return json.dumps(result, indent=2)

                elif response.status_code == 404:
                    return MCPErrorFormatter.format_error(
                        "not_found",
                        f"No operation found with progress_id '{progress_id}'",
                        suggestion="The operation may have completed and been cleaned up. "
                                   "Progress data is kept for ~30 seconds after completion.",
                    )
                else:
                    return MCPErrorFormatter.from_http_error(response, "check progress")

        except httpx.RequestError as e:
            return MCPErrorFormatter.from_exception(e, "check progress")
        except Exception as e:
            logger.error(f"Error checking progress: {e}", exc_info=True)
            return MCPErrorFormatter.from_exception(e, "check progress")
```

**Step 2: Commit**

```bash
git add python/src/mcp_server/features/rag/rag_tools.py
git commit -m "feat: add rag_check_progress MCP tool for async operation polling"
```

---

### Task 6: Add `project_id` to Search MCP Tools

**Files:**
- Modify: `python/src/mcp_server/features/rag/rag_tools.py` (lines ~78-152 for `rag_search_knowledge_base`, lines ~154-215 for `rag_search_code_examples`)

**Step 1: Update `rag_search_knowledge_base`**

Add `project_id: str | None = None` parameter after `source_id` (line ~82). Update the docstring to document it. In the request body construction (line ~119-123), add:

```python
if project_id:
    request_data["project_id"] = project_id
```

**Step 2: Update `rag_search_code_examples`**

Add `project_id: str | None = None` parameter after `source_id` (line ~156). Update the docstring. In the request body construction (line ~182-184), add:

```python
if project_id:
    request_data["project_id"] = project_id
```

**Step 3: Commit**

```bash
git add python/src/mcp_server/features/rag/rag_tools.py
git commit -m "feat: add project_id filtering to RAG search MCP tools"
```

---

### Task 7: Update MCP Server Instructions

**Files:**
- Modify: `python/src/mcp_server/mcp_server.py` (lines ~191-311, the `MCP_INSTRUCTIONS` string)

**Step 1: Add documentation for the new tools**

Add a new section to `MCP_INSTRUCTIONS` documenting:

1. **Source Management** — `manage_rag_source` with add/sync/delete actions
2. **Progress Tracking** — `rag_check_progress` for polling async operations
3. **Ingestion Workflow** — The recommended flow: add once → poll → search → sync for updates
4. **Project Scoping** — Using `project_id` to scope searches

Keep it concise — MCP instructions are included in every tool call.

**Step 2: Commit**

```bash
git add python/src/mcp_server/mcp_server.py
git commit -m "docs: update MCP server instructions with source management tools"
```

---

### Task 8: Handle `project_id` in Source Metadata During Storage

**Files:**
- Modify: `python/src/server/services/crawling/document_storage_operations.py` (line ~134, chunk metadata creation)
- Modify: `python/src/server/services/source_management_service.py` (source record creation, around the upsert pattern)

**Step 1: Pass project_id through to source metadata**

In `document_storage_operations.py`, in the `_create_source_records` method (or wherever source metadata is assembled), ensure `project_id` from the request dict is included in the metadata JSONB:

```python
metadata["project_id"] = request.get("project_id")
```

Check `_create_source_records` to see how metadata flows to `update_source_info()` in `source_management_service.py`. The `project_id` should be preserved in the metadata dict that gets upserted to `cortex_sources`.

**Step 2: Commit**

```bash
git add python/src/server/services/crawling/document_storage_operations.py python/src/server/services/source_management_service.py
git commit -m "feat: preserve project_id in source metadata during storage"
```

---

### Task 9: Handle Multi-Source Filtering in Base Search Strategy

**Files:**
- Modify: `python/src/server/services/search/rag_service.py` (line ~271)
- Potentially modify: `python/src/server/services/search/base_search_strategy.py` (wherever `filter_metadata` is consumed to build the SQL query)

**Step 1: Investigate how filter_metadata is consumed**

Read `base_search_strategy.py` to find where `filter_metadata["source"]` is used in the SQL query. Add handling for `filter_metadata["source_ids"]` (a list) using an IN clause.

The pattern should be:
- `filter_metadata = {"source": "single_id"}` → existing behavior (WHERE source_id = ?)
- `filter_metadata = {"source_ids": ["id1", "id2"]}` → new behavior (WHERE source_id IN (?))

**Step 2: Commit**

```bash
git add python/src/server/services/search/base_search_strategy.py python/src/server/services/search/rag_service.py
git commit -m "feat: support multi-source filtering in vector search for project scoping"
```

---

### Task 10: Write Tests for Inline Ingestion Endpoint

**Files:**
- Create: `python/tests/test_inline_ingestion.py`

**Step 1: Write tests**

```python
"""Tests for the inline document ingestion endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from python.src.server.api_routes.knowledge_api import InlineIngestRequest, InlineDocument


class TestInlineIngestRequest:
    """Test the Pydantic request model."""

    def test_valid_request(self):
        req = InlineIngestRequest(
            title="Test Docs",
            documents=[InlineDocument(title="test.md", content="# Test")],
        )
        assert req.title == "Test Docs"
        assert len(req.documents) == 1
        assert req.knowledge_type == "technical"
        assert req.extract_code_examples is True

    def test_with_project_id(self):
        req = InlineIngestRequest(
            title="Test Docs",
            documents=[InlineDocument(title="test.md", content="# Test")],
            project_id="proj-123",
            tags=["test"],
        )
        assert req.project_id == "proj-123"
        assert req.tags == ["test"]

    def test_document_with_path(self):
        doc = InlineDocument(
            title="auth.md",
            content="# Auth",
            path="docs/architecture/auth.md",
        )
        assert doc.path == "docs/architecture/auth.md"

    def test_document_without_path(self):
        doc = InlineDocument(title="auth.md", content="# Auth")
        assert doc.path is None
```

**Step 2: Run tests**

```bash
cd python && uv run pytest tests/test_inline_ingestion.py -v
```

**Step 3: Commit**

```bash
git add python/tests/test_inline_ingestion.py
git commit -m "test: add tests for inline document ingestion models"
```

---

### Task 11: Write Tests for MCP Tool Validation

**Files:**
- Create: `python/tests/mcp_server/test_rag_manage_source.py`

**Step 1: Write validation tests for manage_rag_source**

Test the input validation logic:
- Missing title for add action → error
- Missing source_type for add → error
- Invalid source_type → error
- Missing documents for inline → error
- Invalid JSON in documents → error
- Missing source_id for sync → error
- Missing source_id for delete → error
- Invalid action → error

Mock httpx responses for success cases.

**Step 2: Run tests**

```bash
cd python && uv run pytest tests/mcp_server/test_rag_manage_source.py -v
```

**Step 3: Commit**

```bash
git add python/tests/mcp_server/test_rag_manage_source.py
git commit -m "test: add validation tests for manage_rag_source MCP tool"
```

---

### Task 12: Integration Smoke Test

**Step 1: Start the backend services**

```bash
docker compose --profile backend up -d
```

**Step 2: Test the ingest-inline endpoint directly**

```bash
curl -X POST http://localhost:8181/api/knowledge/ingest-inline \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Ingestion",
    "documents": [
      {"title": "test.md", "content": "# Test Document\n\nThis is a test document for inline ingestion.\n\n## Section 1\n\nSome content here.", "path": "docs/test.md"}
    ],
    "tags": ["test"],
    "knowledge_type": "technical"
  }'
```

Expected: `{"success": true, "progressId": "...", "sourceId": "...", "estimatedSeconds": 10}`

**Step 3: Poll progress**

```bash
curl http://localhost:8181/api/crawl-progress/{progressId}
```

Expected: Eventually returns `{"status": "completed", ...}`

**Step 4: Verify source appears in available sources**

```bash
curl http://localhost:8181/api/rag/sources
```

Expected: New source with title "Test Ingestion" appears in the list.

**Step 5: Clean up**

```bash
curl -X DELETE http://localhost:8181/api/sources/{sourceId}
```

**Step 6: Commit any fixes from smoke testing**

```bash
git add -A && git commit -m "fix: address issues found during integration smoke test"
```

---

## File Reference

| File | Lines | What's There |
|------|-------|-------------|
| `python/src/mcp_server/features/rag/rag_tools.py` | 38-361 | All RAG MCP tools, `register_rag_tools()` |
| `python/src/mcp_server/mcp_server.py` | 191-311 | MCP instructions; 429-441 module registration |
| `python/src/server/api_routes/knowledge_api.py` | 147-165 | `KnowledgeItemRequest` model |
| `python/src/server/api_routes/knowledge_api.py` | 176-180 | `RagQueryRequest` model |
| `python/src/server/api_routes/knowledge_api.py` | 731-804 | Crawl endpoint |
| `python/src/server/api_routes/knowledge_api.py` | 807-891 | `_perform_crawl_with_progress` (pattern to follow) |
| `python/src/server/api_routes/knowledge_api.py` | 1109-1143 | RAG query endpoint |
| `python/src/server/api_routes/knowledge_api.py` | 1207-1239 | Delete source endpoint |
| `python/src/server/services/crawling/document_storage_operations.py` | 21-215 | `DocumentStorageOperations` class |
| `python/src/server/services/storage/document_storage_service.py` | 16-418 | `add_documents_to_supabase()` |
| `python/src/server/services/storage/base_storage_service.py` | 39-120 | `smart_chunk_text()` chunking logic |
| `python/src/server/services/search/rag_service.py` | 244-378 | `perform_rag_query()` with source filtering |
| `python/src/server/services/source_management_service.py` | 214-359 | `update_source_info()` upsert pattern |
| `python/src/mcp_server/utils/error_handling.py` | all | `MCPErrorFormatter` |
| `python/src/mcp_server/utils/timeout_config.py` | all | Timeout configuration |
