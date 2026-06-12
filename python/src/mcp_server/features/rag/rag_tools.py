"""
RAG Module for Cortex MCP Server (HTTP-based version)

This module provides tools for:
- RAG query and search
- Source management
- Code example extraction and search

This version uses HTTP calls to the server service instead of importing
service modules directly, enabling true microservices architecture.
"""

import json
import logging
import os
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

# Import service discovery for HTTP communication
from src.server.config.service_discovery import get_api_url
from src.mcp_server.utils.error_handling import MCPErrorFormatter

logger = logging.getLogger(__name__)


def get_setting(key: str, default: str = "false") -> str:
    """Get a setting from environment variable."""
    return os.getenv(key, default)


def get_bool_setting(key: str, default: bool = False) -> bool:
    """Get a boolean setting from environment variable."""
    value = get_setting(key, "false" if not default else "true")
    return value.lower() in ("true", "1", "yes", "on")


def register_rag_tools(mcp: FastMCP):
    """Register all RAG tools with the MCP server."""

    @mcp.tool()
    async def rag_get_available_sources(ctx: Context) -> str:
        """
        Get list of available sources in the knowledge base.

        Returns:
            JSON string with structure:
            - success: bool - Operation success status
            - sources: list[dict] - Array of source objects
            - count: int - Number of sources
            - error: str - Error description if success=false
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(urljoin(api_url, "/api/rag/sources"))

                if response.status_code == 200:
                    result = response.json()
                    sources = result.get("sources", [])

                    return json.dumps(
                        {"success": True, "sources": sources, "count": len(sources)}, indent=2
                    )
                else:
                    error_detail = response.text
                    return json.dumps(
                        {"success": False, "error": f"HTTP {response.status_code}: {error_detail}"},
                        indent=2,
                    )

        except Exception as e:
            logger.error(f"Error getting sources: {e}")
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    async def rag_search_knowledge_base(
        ctx: Context,
        query: str,
        source_id: str | None = None,
        project_id: str | None = None,
        include_parent: bool = True,
        match_count: int = 5,
        return_mode: str = "pages"
    ) -> str:
        """
        Search knowledge base for relevant content using RAG.

        Args:
            query: Search query - Keep it SHORT and FOCUSED (2-5 keywords).
                   Good: "vector search", "authentication JWT", "React hooks"
                   Bad: "how to implement user authentication with JWT tokens in React with TypeScript and handle refresh tokens"
            source_id: Optional source ID filter from rag_get_available_sources().
                      This is the 'id' field from available sources, NOT a URL or domain name.
                      Example: "src_1234abcd" not "docs.anthropic.com"
            project_id: Optional project ID to scope search to sources associated with a project
            include_parent: Include parent project's sources in search (default: true).
                           When true, if the project has a parent, its sources are also searched.
            match_count: Max results (default: 5)
            return_mode: "pages" (default, full pages with metadata) or "chunks" (raw text chunks)

        Returns:
            JSON string with structure:
            - success: bool - Operation success status
            - results: list[dict] - Array of pages/chunks with content and metadata
                      Pages include: page_id, url, title, preview, word_count, chunk_matches
                      Chunks include: content, metadata, similarity
            - return_mode: str - Mode used ("pages" or "chunks")
            - reranked: bool - Whether results were reranked
            - error: str|null - Error description if success=false

        Note: Use "pages" mode for better context (recommended), or "chunks" for raw granular results.
        After getting pages, use rag_read_full_page() to retrieve complete page content.
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                request_data = {
                    "query": query,
                    "match_count": match_count,
                    "return_mode": return_mode,
                    "include_parent": include_parent,
                }
                if source_id:
                    request_data["source"] = source_id
                if project_id:
                    request_data["project_id"] = project_id

                response = await client.post(urljoin(api_url, "/api/rag/query"), json=request_data)

                if response.status_code == 200:
                    result = response.json()
                    return json.dumps(
                        {
                            "success": True,
                            "results": result.get("results", []),
                            "return_mode": result.get("return_mode", return_mode),
                            "reranked": result.get("reranked", False),
                            "error": None,
                        },
                        indent=2,
                    )
                else:
                    error_detail = response.text
                    return json.dumps(
                        {
                            "success": False,
                            "results": [],
                            "error": f"HTTP {response.status_code}: {error_detail}",
                        },
                        indent=2,
                    )

        except Exception as e:
            logger.error(f"Error performing RAG query: {e}")
            return json.dumps({"success": False, "results": [], "error": str(e)}, indent=2)

    @mcp.tool()
    async def rag_search_code_examples(
        ctx: Context,
        query: str,
        source_id: str | None = None,
        project_id: str | None = None,
        include_parent: bool = True,
        match_count: int = 5,
    ) -> str:
        """
        Search for relevant code examples in the knowledge base.

        Args:
            query: Search query - Keep it SHORT and FOCUSED (2-5 keywords).
                   Good: "React useState", "FastAPI middleware", "vector pgvector"
                   Bad: "React hooks useState useEffect useContext useReducer useMemo useCallback"
            source_id: Optional source ID filter from rag_get_available_sources().
                      This is the 'id' field from available sources, NOT a URL or domain name.
                      Example: "src_1234abcd" not "docs.anthropic.com"
            project_id: Optional project ID to scope search to sources associated with a project
            include_parent: Include parent project's sources in search (default: true)
            match_count: Max results (default: 5)

        Returns:
            JSON string with structure:
            - success: bool - Operation success status
            - results: list[dict] - Array of code examples with content and summaries
            - reranked: bool - Whether results were reranked
            - error: str|null - Error description if success=false
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                request_data = {
                    "query": query,
                    "match_count": match_count,
                    "include_parent": include_parent,
                }
                if source_id:
                    request_data["source"] = source_id
                if project_id:
                    request_data["project_id"] = project_id

                # Call the dedicated code examples endpoint
                response = await client.post(
                    urljoin(api_url, "/api/rag/code-examples"), json=request_data
                )

                if response.status_code == 200:
                    result = response.json()
                    return json.dumps(
                        {
                            "success": True,
                            "results": result.get("results", []),
                            "reranked": result.get("reranked", False),
                            "error": None,
                        },
                        indent=2,
                    )
                else:
                    error_detail = response.text
                    return json.dumps(
                        {
                            "success": False,
                            "results": [],
                            "error": f"HTTP {response.status_code}: {error_detail}",
                        },
                        indent=2,
                    )

        except Exception as e:
            logger.error(f"Error searching code examples: {e}")
            return json.dumps({"success": False, "results": [], "error": str(e)}, indent=2)

    @mcp.tool()
    async def rag_list_pages_for_source(
        ctx: Context, source_id: str, section: str | None = None
    ) -> str:
        """
        List all pages for a given knowledge source.

        Use this after rag_get_available_sources() to see all pages in a source.
        Useful for browsing documentation structure or finding specific pages.

        Args:
            source_id: Source ID from rag_get_available_sources() (e.g., "src_1234abcd")
            section: Optional filter for llms-full.txt section title (e.g., "# Core Concepts")

        Returns:
            JSON string with structure:
            - success: bool - Operation success status
            - pages: list[dict] - Array of page objects with id, url, section_title, word_count
            - total: int - Total number of pages
            - source_id: str - The source ID that was queried
            - error: str|null - Error description if success=false

        Example workflow:
            1. Call rag_get_available_sources() to get source_id
            2. Call rag_list_pages_for_source(source_id) to see all pages
            3. Call rag_read_full_page(page_id) to read specific pages
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                params = {"source_id": source_id}
                if section:
                    params["section"] = section

                response = await client.get(
                    urljoin(api_url, "/api/pages"),
                    params=params
                )

                if response.status_code == 200:
                    result = response.json()
                    return json.dumps(
                        {
                            "success": True,
                            "pages": result.get("pages", []),
                            "total": result.get("total", 0),
                            "source_id": result.get("source_id", source_id),
                            "error": None,
                        },
                        indent=2,
                    )
                else:
                    error_detail = response.text
                    return json.dumps(
                        {
                            "success": False,
                            "pages": [],
                            "total": 0,
                            "source_id": source_id,
                            "error": f"HTTP {response.status_code}: {error_detail}",
                        },
                        indent=2,
                    )

        except Exception as e:
            logger.error(f"Error listing pages for source {source_id}: {e}")
            return json.dumps(
                {
                    "success": False,
                    "pages": [],
                    "total": 0,
                    "source_id": source_id,
                    "error": str(e)
                },
                indent=2
            )

    @mcp.tool()
    async def rag_read_full_page(
        ctx: Context, page_id: str | None = None, url: str | None = None
    ) -> str:
        """
        Retrieve full page content from knowledge base.
        Use this to get complete page content after RAG search.

        Args:
            page_id: Page UUID from search results (e.g., "550e8400-e29b-41d4-a716-446655440000")
            url: Page URL (e.g., "https://docs.example.com/getting-started")

        Note: Provide EITHER page_id OR url, not both.

        Returns:
            JSON string with structure:
            - success: bool
            - page: dict with full_content, title, url, metadata
            - error: str|null
        """
        try:
            if not page_id and not url:
                return json.dumps(
                    {"success": False, "error": "Must provide either page_id or url"},
                    indent=2
                )

            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                if page_id:
                    response = await client.get(urljoin(api_url, f"/api/pages/{page_id}"))
                else:
                    response = await client.get(
                        urljoin(api_url, "/api/pages/by-url"),
                        params={"url": url}
                    )

                if response.status_code == 200:
                    page_data = response.json()
                    return json.dumps(
                        {
                            "success": True,
                            "page": page_data,
                            "error": None,
                        },
                        indent=2,
                    )
                else:
                    error_detail = response.text
                    return json.dumps(
                        {
                            "success": False,
                            "page": None,
                            "error": f"HTTP {response.status_code}: {error_detail}",
                        },
                        indent=2,
                    )

        except Exception as e:
            logger.error(f"Error reading page: {e}")
            return json.dumps({"success": False, "page": None, "error": str(e)}, indent=2)

    @mcp.tool()
    async def manage_rag_source(
        ctx: Context,
        action: str,
        title: str | None = None,
        source_type: str | None = None,
        documents: str | list | None = None,
        url: str | None = None,
        tags: list[str] | None = None,
        project_id: str | None = None,
        knowledge_type: str = "technical",
        extract_code_examples: bool = True,
        source_id: str | None = None,
        force: bool = False,
    ) -> str:
        """
        Manage RAG knowledge base sources (consolidated: add/append/sync/delete).

        Args:
            action: "add" | "append" | "sync" | "delete"
            title: Source title (required for add)
            source_type: "inline" | "url" (required for add)
            documents: List of documents for inline/append mode (also accepts JSON string).
                Format: [{"title": "file.md", "content": "# Markdown...", "path": "docs/file.md"}]
                Each document must have "title" and "content". "path" is optional.
            url: URL to crawl (required for add with source_type="url")
            tags: Tags for categorization, e.g. ["project-name", "docs"]
            project_id: Associate source with an Cortex project for scoped searches
            knowledge_type: Classification (default: "technical")
            extract_code_examples: Extract and index code blocks (default: true)
            source_id: Source ID for append/sync/delete (from rag_get_available_sources)
            force: For sync: re-chunk everything (true) vs only changed (false)

        Workflow:
            1. Add source: manage_rag_source(action="add", title="My Docs", source_type="inline", documents='[...]')
            2. Poll progress: rag_check_progress(progress_id="...") until status="completed"
            3. Search: rag_search_knowledge_base(query="...", project_id="...")
            4. Append docs: manage_rag_source(action="append", source_id="...", documents='[...]')
            5. Full sync: manage_rag_source(action="sync", source_id="...", documents='[...]')
            6. Remove: manage_rag_source(action="delete", source_id="...")

        IMPORTANT: When project_id is provided with action="add", the source_id is deterministic
        (based on project_id + title). Calling "add" again with the same title and project_id
        will update the existing source instead of creating a duplicate.

        For append: adds new documents to an existing source without removing anything.
        For sync: pass documents to re-ingest inline content, or omit documents to re-crawl a URL source.

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
                            'Format: [{"title": "file.md", "content": "# Content..."}]'
                        )
                    # Handle both list (from MCP transport auto-deserialization) and JSON string
                    if isinstance(documents, list):
                        docs_list = documents
                    elif isinstance(documents, str):
                        try:
                            docs_list = json.loads(documents)
                        except json.JSONDecodeError as e:
                            return MCPErrorFormatter.format_error(
                                "validation_error", f"Invalid JSON in documents parameter: {e}"
                            )
                    else:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "documents must be a list or JSON string"
                        )
                    if not isinstance(docs_list, list) or not docs_list:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "documents must be a non-empty array"
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
                        payload = {
                            "url": url,
                            "knowledge_type": knowledge_type,
                            "tags": tags or [],
                            "extract_code_examples": extract_code_examples,
                        }
                        if project_id:
                            payload["project_id"] = project_id
                        response = await client.post(
                            urljoin(api_url, "/api/knowledge-items/crawl"),
                            json=payload,
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

            elif action == "append":
                if not source_id:
                    return MCPErrorFormatter.format_error(
                        "validation_error",
                        "source_id is required for append action. Get it from rag_get_available_sources()."
                    )
                if not documents:
                    return MCPErrorFormatter.format_error(
                        "validation_error",
                        "documents is required for append action. "
                        'Format: [{"title": "file.md", "content": "# Content..."}]'
                    )
                # Handle both list and JSON string
                if isinstance(documents, list):
                    docs_list = documents
                elif isinstance(documents, str):
                    try:
                        docs_list = json.loads(documents)
                    except json.JSONDecodeError as e:
                        return MCPErrorFormatter.format_error(
                            "validation_error", f"Invalid JSON in documents parameter: {e}"
                        )
                else:
                    return MCPErrorFormatter.format_error(
                        "validation_error", "documents must be a list or JSON string"
                    )
                if not isinstance(docs_list, list) or not docs_list:
                    return MCPErrorFormatter.format_error(
                        "validation_error", "documents must be a non-empty array"
                    )

                async with httpx.AsyncClient(timeout=get_polling_timeout()) as client:
                    response = await client.post(
                        urljoin(api_url, "/api/knowledge/append-inline"),
                        json={
                            "source_id": source_id,
                            "documents": docs_list,
                            "knowledge_type": knowledge_type,
                            "extract_code_examples": extract_code_examples,
                        },
                    )
                    if response.status_code == 200:
                        data = response.json()
                        result = {
                            "success": True,
                            "progress_id": data.get("progressId"),
                            "source_id": data.get("sourceId"),
                            "estimated_seconds": data.get("estimatedSeconds"),
                            "documents_to_append": data.get("documentsToAppend", 0),
                            "duplicates_detected": data.get("duplicatesDetected", 0),
                            "message": (
                                f"Appending {data.get('documentsToAppend', 0)} document(s) to source '{source_id}'. "
                                f"Poll rag_check_progress(progress_id='{data.get('progressId')}') for status."
                            ),
                        }
                        if data.get("duplicateTitles"):
                            result["duplicate_titles"] = data["duplicateTitles"]
                            result["message"] += (
                                f" Note: {data.get('duplicatesDetected', 0)} document(s) already exist "
                                f"and will be updated in place."
                            )
                        return json.dumps(result, indent=2)
                    else:
                        return MCPErrorFormatter.from_http_error(response, "append documents")

            elif action == "sync":
                if not source_id:
                    return MCPErrorFormatter.format_error(
                        "validation_error",
                        "source_id is required for sync action. Get it from rag_get_available_sources()."
                    )

                if documents:
                    # Inline sync path: re-ingest documents under the same source_id
                    if isinstance(documents, list):
                        docs_list = documents
                    elif isinstance(documents, str):
                        try:
                            docs_list = json.loads(documents)
                        except json.JSONDecodeError as e:
                            return MCPErrorFormatter.format_error(
                                "validation_error", f"Invalid JSON in documents parameter: {e}"
                            )
                    else:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "documents must be a list or JSON string"
                        )
                    if not isinstance(docs_list, list) or not docs_list:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "documents must be a non-empty array"
                        )

                    async with httpx.AsyncClient(timeout=get_polling_timeout()) as client:
                        response = await client.post(
                            urljoin(api_url, "/api/knowledge/sync-inline"),
                            json={
                                "source_id": source_id,
                                "documents": docs_list,
                                "knowledge_type": knowledge_type,
                                "extract_code_examples": extract_code_examples,
                            },
                        )
                        if response.status_code == 200:
                            data = response.json()
                            result = {
                                "success": True,
                                "progress_id": data.get("progressId"),
                                "source_id": data.get("sourceId"),
                                "estimated_seconds": data.get("estimatedSeconds"),
                                "documents_to_process": data.get("documentsToProcess", 0),
                                "documents_skipped": data.get("documentsSkipped", 0),
                            }
                            # Include sync diff if incremental sync was used
                            if data.get("syncDiff"):
                                result["sync_diff"] = data["syncDiff"]
                            if data.get("progressId"):
                                result["message"] = (
                                    f"Inline sync started for source '{source_id}'. "
                                    f"Poll rag_check_progress(progress_id='{data.get('progressId')}') for status."
                                )
                            else:
                                result["message"] = data.get("message", "Sync complete — no changes detected.")
                            return json.dumps(result, indent=2)
                        else:
                            return MCPErrorFormatter.from_http_error(response, "inline sync")
                else:
                    # URL sync path: re-crawl the source's URL
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
                    f'Invalid action "{action}". Must be "add", "append", "sync", or "delete".'
                )

        except httpx.RequestError as e:
            return MCPErrorFormatter.from_exception(e, f"manage_rag_source ({action})")
        except Exception as e:
            logger.error(f"Error in manage_rag_source: {e}", exc_info=True)
            return MCPErrorFormatter.from_exception(e, f"manage_rag_source ({action})")

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
            JSON with {success, status, progress, documents_processed, documents_total, results?}

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

    # Log successful registration
    logger.info("✓ RAG tools registered (HTTP-based version)")
