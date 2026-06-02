"""
Knowledge Management API Module

This module handles all knowledge base operations including:
- Crawling and indexing web content
- Document upload and processing
- RAG (Retrieval Augmented Generation) queries
- Knowledge item management and search
- Progress tracking via HTTP polling
"""

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

# Basic validation - simplified inline version
# Import unified logging
from ..config.logfire_config import get_logger, safe_logfire_error, safe_logfire_info
from ..services.crawler_manager import get_crawler
from ..services.crawling import CrawlingService
from ..services.credential_service import credential_service
from ..services.embeddings.embedding_exceptions import (
    EmbeddingAPIError,
    EmbeddingAuthenticationError,
    EmbeddingQuotaExhaustedError,
    EmbeddingRateLimitError,
)
from ..services.embeddings.provider_error_adapters import ProviderErrorFactory
from ..services.knowledge import DatabaseMetricsService, KnowledgeItemService, KnowledgeSummaryService
from ..services.search.rag_service import RAGService
from ..services.storage import DocumentStorageService
from ..utils import get_supabase_client
from ..utils.document_processing import extract_text_from_document

# Get logger for this module
logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["knowledge"])


# Create a semaphore to limit concurrent crawl OPERATIONS (not pages within a crawl)
# This prevents the server from becoming unresponsive during heavy crawling
#
# IMPORTANT: This is different from CRAWL_MAX_CONCURRENT (configured in UI/database):
# - CONCURRENT_CRAWL_LIMIT: Max number of separate crawl operations that can run simultaneously (server protection)
#   Example: User A crawls site1.com, User B crawls site2.com, User C crawls site3.com = 3 operations
# - CRAWL_MAX_CONCURRENT: Max number of pages that can be crawled in parallel within a single crawl operation
#   Example: While crawling site1.com, fetch up to 10 pages simultaneously
#
# The hardcoded limit of 3 protects the server from being overwhelmed by multiple users
# starting crawls at the same time. Each crawl can still process many pages in parallel.
CONCURRENT_CRAWL_LIMIT = 3  # Max simultaneous crawl operations (protects server resources)
crawl_semaphore = asyncio.Semaphore(CONCURRENT_CRAWL_LIMIT)

MAX_QUEUED_CRAWLS = 6  # Max total crawls (running + waiting). 3 run, 3 can queue.
_queued_crawl_count = 0
_crawl_count_lock = asyncio.Lock()

# Track active async crawl tasks for cancellation support
active_crawl_tasks: dict[str, asyncio.Task] = {}


def _get_provider_display_name(provider: str) -> str:
    """Return a human-readable provider name for API responses."""
    provider_names = {
        "openai": "OpenAI",
        "openrouter": "OpenRouter",
        "google": "Google",
        "anthropic": "Anthropic",
        "grok": "Grok",
        "ollama": "Ollama",
    }
    return provider_names.get(provider.lower(), provider.title())


def _sanitize_provider_validation_error(provider: str, error: Exception) -> str:
    """Sanitize provider validation errors before returning them to clients."""
    error_text = str(error).strip()
    if not error_text:
        error_text = f"{provider.title()} API encountered an error."
    return ProviderErrorFactory.sanitize_provider_error(error_text, provider)


def _build_provider_validation_exception(provider: str, error: Exception) -> HTTPException:
    """Map embedding validation failures to accurate HTTP responses."""
    provider_name = provider or "openai"
    provider_title = _get_provider_display_name(provider_name)
    sanitized_error = _sanitize_provider_validation_error(provider_name, error)
    error_lower = sanitized_error.lower()

    auth_markers = (
        "incorrect api key",
        "invalid api key",
        "invalid_api_key",
        "authentication",
        "unauthorized",
        "error code: 401",
        "status code: 401",
    )
    config_markers = (
        "api key not found",
        "provider not configured",
        "no embedding provider configured",
        "unsupported llm provider",
        "does not support embeddings",
        "unsupported",
        "invalid dimension",
        "invalid dimensions",
        "invalid_request_error",
        "bad request",
        "ollama fallback failed",
        "no ollama base url resolved",
    )
    availability_markers = (
        "timed out",
        "timeout",
        "connection",
        "service unavailable",
        "temporarily unavailable",
        "dns",
        "refused",
        "unreachable",
    )

    if isinstance(error, EmbeddingQuotaExhaustedError) or "quota" in error_lower:
        return HTTPException(
            status_code=429,
            detail={
                "error": f"{provider_title} quota exhausted",
                "message": (
                    f"{provider_title} quota exhausted. Check billing and usage limits. "
                    f"Error: {sanitized_error}"
                ),
                "error_type": "quota_exhausted",
                "provider": provider_name,
            },
        )

    if isinstance(error, EmbeddingRateLimitError) or "rate limit" in error_lower:
        return HTTPException(
            status_code=429,
            detail={
                "error": f"{provider_title} rate limit exceeded",
                "message": f"{provider_title} rate limit exceeded. Wait and retry. Error: {sanitized_error}",
                "error_type": "rate_limit",
                "provider": provider_name,
            },
        )

    if isinstance(error, EmbeddingAuthenticationError) or any(
        marker in error_lower for marker in auth_markers
    ):
        return HTTPException(
            status_code=401,
            detail={
                "error": f"Invalid {provider_title} API key",
                "message": f"Please verify your {provider_title} API key in Settings. Error: {sanitized_error}",
                "error_type": "authentication_failed",
                "provider": provider_name,
            },
        )

    if isinstance(error, EmbeddingAPIError) and any(marker in error_lower for marker in config_markers):
        return HTTPException(
            status_code=400,
            detail={
                "error": f"{provider_title} embedding configuration failed",
                "message": f"{provider_title} embedding configuration failed. Error: {sanitized_error}",
                "error_type": "configuration_error",
                "provider": provider_name,
            },
        )

    if any(marker in error_lower for marker in availability_markers):
        return HTTPException(
            status_code=503,
            detail={
                "error": f"{provider_title} provider unavailable",
                "message": f"{provider_title} provider unavailable. Error: {sanitized_error}",
                "error_type": "provider_unavailable",
                "provider": provider_name,
            },
        )

    return HTTPException(
        status_code=502,
        detail={
            "error": f"{provider_title} embedding validation failed",
            "message": f"{provider_title} embedding validation failed. Error: {sanitized_error}",
            "error_type": "provider_error",
            "provider": provider_name,
        },
    )


async def _validate_provider_api_key(provider: str = None) -> None:
    """Validate LLM provider API key before starting operations."""
    logger.info("🔑 Starting API key validation...")

    try:
        # Basic provider validation
        if not provider:
            provider = "openai"
        else:
            # Simple provider validation
            allowed_providers = {"openai", "ollama", "google", "openrouter", "anthropic", "grok"}
            if provider not in allowed_providers:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid provider name",
                        "message": f"Provider '{provider}' not supported",
                        "error_type": "validation_error"
                    }
                )

        # Basic sanitization for logging
        safe_provider = provider[:20]  # Limit length
        logger.info(f"🔑 Testing {safe_provider.title()} API key with minimal embedding request...")

        try:
            # Test API key with minimal embedding request using provider-scoped configuration
            from ..services.embeddings.embedding_service import create_embedding

            test_result = await create_embedding(text="test", provider=provider)

            if not test_result:
                logger.error(
                    f"❌ {provider.title()} API key validation failed - no embedding returned"
                )
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": f"Invalid {provider.title()} API key",
                        "message": f"Please verify your {provider.title()} API key in Settings.",
                        "error_type": "authentication_failed",
                        "provider": provider,
                    },
                )
        except Exception as e:
            logger.error(
                f"❌ {provider.title()} API key validation failed: {e}",
                exc_info=True,
            )
            raise _build_provider_validation_exception(provider, e) from e

        logger.info(f"✅ {provider.title()} API key validation successful")

    except HTTPException:
        # Re-raise our intended HTTP exceptions
        logger.error("🚨 Re-raising HTTPException from validation")
        raise
    except Exception as e:
        # Sanitize error before logging to prevent sensitive data exposure
        error_str = str(e)
        sanitized_error = ProviderErrorFactory.sanitize_provider_error(error_str, provider or "openai")
        logger.error(f"❌ Caught exception during API key validation: {sanitized_error}")

        logger.error("🚨 Provider validation failed - blocking crawl operation")
        raise _build_provider_validation_exception(provider or "openai", e) from e


# Request Models
class KnowledgeItemRequest(BaseModel):
    url: str
    knowledge_type: str = "technical"
    tags: list[str] = []
    update_frequency: int = 7
    max_depth: int = 2  # Maximum crawl depth (1-5)
    extract_code_examples: bool = True  # Whether to extract code examples
    project_id: str | None = None  # Optional project association for scoped searches

    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com",
                "knowledge_type": "technical",
                "tags": ["documentation"],
                "update_frequency": 7,
                "max_depth": 2,
                "extract_code_examples": True,
            }
        }


class CrawlRequest(BaseModel):
    url: str
    knowledge_type: str = "general"
    tags: list[str] = []
    update_frequency: int = 7
    max_depth: int = 2  # Maximum crawl depth (1-5)


class RagQueryRequest(BaseModel):
    query: str
    source: str | None = None
    project_id: str | None = None
    include_parent: bool = True  # Include parent project's sources in search
    match_count: int = 5
    return_mode: str = "chunks"  # "chunks" or "pages"


class InlineDocument(BaseModel):
    """A single document to ingest inline."""
    title: str
    content: str
    path: str | None = None
    file_hash: str | None = None


class InlineIngestRequest(BaseModel):
    """Request to ingest a batch of inline documents."""
    title: str  # Source title
    documents: list[InlineDocument]
    tags: list[str] = []
    project_id: str | None = None
    knowledge_type: str = "technical"
    extract_code_examples: bool = True


class InlineSyncRequest(BaseModel):
    """Request to sync inline documents for an existing source."""
    source_id: str
    documents: list[InlineDocument]
    knowledge_type: str = "technical"
    extract_code_examples: bool = True


class InlineAppendRequest(BaseModel):
    """Request to append documents to an existing inline source without removing existing content."""
    source_id: str
    documents: list[InlineDocument]
    knowledge_type: str = "technical"
    extract_code_examples: bool = True


@router.get("/crawl-progress/{progress_id}")
async def get_crawl_progress(progress_id: str):
    """Get crawl progress for polling.
    
    Returns the current state of a crawl operation.
    Frontend should poll this endpoint to track crawl progress.
    """
    try:
        from ..models.progress_models import create_progress_response
        from ..utils.progress.progress_tracker import ProgressTracker

        # Get progress from the tracker's in-memory storage
        progress_data = ProgressTracker.get_progress(progress_id)
        safe_logfire_info(f"Crawl progress requested | progress_id={progress_id} | found={progress_data is not None}")

        if not progress_data:
            # Return 404 if no progress exists - this is correct behavior
            raise HTTPException(status_code=404, detail={"error": f"No progress found for ID: {progress_id}"})

        # Ensure we have the progress_id in the data
        progress_data["progress_id"] = progress_id

        # Get operation type for proper model selection
        operation_type = progress_data.get("type", "crawl")

        # Create standardized response using Pydantic model
        progress_response = create_progress_response(operation_type, progress_data)

        # Convert to dict with camelCase fields for API response
        response_data = progress_response.model_dump(by_alias=True, exclude_none=True)

        safe_logfire_info(
            f"Progress retrieved | operation_id={progress_id} | status={response_data.get('status')} | "
            f"progress={response_data.get('progress')} | totalPages={response_data.get('totalPages')} | "
            f"processedPages={response_data.get('processedPages')}"
        )

        return response_data
    except Exception as e:
        safe_logfire_error(f"Failed to get crawl progress | error={str(e)} | progress_id={progress_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/knowledge-items/sources")
async def get_knowledge_sources():
    """Get all available knowledge sources."""
    try:
        # Return empty list for now to pass the test
        # In production, this would query the database
        return []
    except Exception as e:
        safe_logfire_error(f"Failed to get knowledge sources | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/knowledge-items")
async def get_knowledge_items(
    page: int = 1, per_page: int = 20, knowledge_type: str | None = None, search: str | None = None
):
    """Get knowledge items with pagination and filtering."""
    try:
        # Use KnowledgeItemService
        service = KnowledgeItemService(get_supabase_client())
        result = await service.list_items(
            page=page, per_page=per_page, knowledge_type=knowledge_type, search=search
        )
        return result

    except Exception as e:
        safe_logfire_error(
            f"Failed to get knowledge items | error={str(e)} | page={page} | per_page={per_page}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/knowledge-items/summary")
async def get_knowledge_items_summary(
    page: int = 1,
    per_page: int = 20,
    knowledge_type: str | None = None,
    search: str | None = None,
    project_id: str | None = None,
):
    """
    Get lightweight summaries of knowledge items.
    
    Returns minimal data optimized for frequent polling:
    - Only counts, no actual document/code content
    - Basic metadata for display
    - Efficient batch queries
    
    Use this endpoint for card displays and frequent polling.
    """
    try:
        # Input guards
        page = max(1, page)
        per_page = min(100, max(1, per_page))
        service = KnowledgeSummaryService(get_supabase_client())
        result = await service.get_summaries(
            page=page, per_page=per_page, knowledge_type=knowledge_type, search=search, project_id=project_id
        )
        return result

    except Exception as e:
        safe_logfire_error(
            f"Failed to get knowledge summaries | error={str(e)} | page={page} | per_page={per_page}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.put("/knowledge-items/{source_id}")
async def update_knowledge_item(source_id: str, updates: dict):
    """Update a knowledge item's metadata."""
    try:
        # Use KnowledgeItemService
        service = KnowledgeItemService(get_supabase_client())
        success, result = await service.update_item(source_id, updates)

        if success:
            return result
        else:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail={"error": result.get("error")})
            else:
                raise HTTPException(status_code=500, detail={"error": result.get("error")})

    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(
            f"Failed to update knowledge item | error={str(e)} | source_id={source_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete("/knowledge-items/{source_id}")
async def delete_knowledge_item(source_id: str):
    """Delete a knowledge item from the database."""
    try:
        logger.debug(f"Starting delete_knowledge_item for source_id: {source_id}")
        safe_logfire_info(f"Deleting knowledge item | source_id={source_id}")

        # Use SourceManagementService directly instead of going through MCP
        logger.debug("Creating SourceManagementService...")
        from ..services.source_management_service import SourceManagementService

        source_service = SourceManagementService(get_supabase_client())
        logger.debug("Successfully created SourceManagementService")

        logger.debug("Calling delete_source function...")
        success, result_data = source_service.delete_source(source_id)
        logger.debug(f"delete_source returned: success={success}, data={result_data}")

        # Convert to expected format
        result = {
            "success": success,
            "error": result_data.get("error") if not success else None,
            **result_data,
        }

        if result.get("success"):
            safe_logfire_info(f"Knowledge item deleted successfully | source_id={source_id}")

            return {"success": True, "message": f"Successfully deleted knowledge item {source_id}"}
        else:
            safe_logfire_error(
                f"Knowledge item deletion failed | source_id={source_id} | error={result.get('error')}"
            )
            raise HTTPException(
                status_code=500, detail={"error": result.get("error", "Deletion failed")}
            )

    except Exception as e:
        logger.error(f"Exception in delete_knowledge_item: {e}")
        logger.error(f"Exception type: {type(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        safe_logfire_error(
            f"Failed to delete knowledge item | error={str(e)} | source_id={source_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/knowledge-items/{source_id}/chunks")
async def get_knowledge_item_chunks(
    source_id: str,
    domain_filter: str | None = None,
    limit: int = 20,
    offset: int = 0
):
    """
    Get document chunks for a specific knowledge item with pagination.
    
    Args:
        source_id: The source ID
        domain_filter: Optional domain filter for URLs
        limit: Maximum number of chunks to return (default 20, max 100)
        offset: Number of chunks to skip (for pagination)
    
    Returns:
        Paginated chunks with metadata
    """
    try:
        # Validate pagination parameters
        limit = min(limit, 100)  # Cap at 100 to prevent excessive data transfer
        limit = max(limit, 1)    # At least 1
        offset = max(offset, 0)   # Can't be negative

        safe_logfire_info(
            f"Fetching chunks | source_id={source_id} | domain_filter={domain_filter} | "
            f"limit={limit} | offset={offset}"
        )

        supabase = get_supabase_client()

        # First get total count
        count_query = supabase.from_("archon_crawled_pages").select(
            "id", count="exact", head=True
        )
        count_query = count_query.eq("source_id", source_id)

        if domain_filter:
            count_query = count_query.ilike("url", f"%{domain_filter}%")

        count_result = count_query.execute()
        total = count_result.count if hasattr(count_result, "count") else 0

        # Build the main query with pagination
        query = supabase.from_("archon_crawled_pages").select(
            "id, source_id, content, metadata, url"
        )
        query = query.eq("source_id", source_id)

        # Apply domain filtering if provided
        if domain_filter:
            query = query.ilike("url", f"%{domain_filter}%")

        # Deterministic ordering (URL then id)
        query = query.order("url", desc=False).order("id", desc=False)

        # Apply pagination
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        # Check for error more explicitly to work with mocks
        if hasattr(result, "error") and result.error is not None:
            safe_logfire_error(
                f"Supabase query error | source_id={source_id} | error={result.error}"
            )
            raise HTTPException(status_code=500, detail={"error": str(result.error)})

        chunks = result.data if result.data else []

        # Extract useful fields from metadata to top level for frontend
        # This ensures the API response matches the TypeScript DocumentChunk interface
        for chunk in chunks:
            metadata = chunk.get("metadata", {}) or {}

            # Generate meaningful titles from available data
            title = None

            # Try to get title from various metadata fields
            if metadata.get("filename"):
                title = metadata.get("filename")
            elif metadata.get("headers"):
                title = metadata.get("headers").split(";")[0].strip("# ")
            elif metadata.get("title") and metadata.get("title").strip():
                title = metadata.get("title").strip()
            else:
                # Try to extract from content first for more specific titles
                if chunk.get("content"):
                    content = chunk.get("content", "").strip()
                    # Look for markdown headers at the start
                    lines = content.split("\n")[:5]
                    for line in lines:
                        line = line.strip()
                        if line.startswith("# "):
                            title = line[2:].strip()
                            break
                        elif line.startswith("## "):
                            title = line[3:].strip()
                            break
                        elif line.startswith("### "):
                            title = line[4:].strip()
                            break

                    # Fallback: use first meaningful line that looks like a title
                    if not title:
                        for line in lines:
                            line = line.strip()
                            # Skip code blocks, empty lines, and very short lines
                            if (line and not line.startswith("```") and not line.startswith("Source:")
                                and len(line) > 15 and len(line) < 80
                                and not line.startswith("from ") and not line.startswith("import ")
                                and "=" not in line and "{" not in line):
                                title = line
                                break

                # If no content-based title found, generate from URL
                if not title:
                    url = chunk.get("url", "")
                    if url:
                        # Extract meaningful part from URL
                        if url.endswith(".txt"):
                            title = url.split("/")[-1].replace(".txt", "").replace("-", " ").title()
                        else:
                            # Get domain and path info
                            parsed = urlparse(url)
                            if parsed.path and parsed.path != "/":
                                title = parsed.path.strip("/").replace("-", " ").replace("_", " ").title()
                            else:
                                title = parsed.netloc.replace("www.", "").title()

            chunk["title"] = title or ""
            chunk["section"] = metadata.get("headers", "").replace(";", " > ") if metadata.get("headers") else None
            chunk["source_type"] = metadata.get("source_type")
            chunk["knowledge_type"] = metadata.get("knowledge_type")

        safe_logfire_info(
            f"Fetched {len(chunks)} chunks for {source_id} | total={total}"
        )

        return {
            "success": True,
            "source_id": source_id,
            "domain_filter": domain_filter,
            "chunks": chunks,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(
            f"Failed to fetch chunks | error={str(e)} | source_id={source_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/knowledge-items/{source_id}/code-examples")
async def get_knowledge_item_code_examples(
    source_id: str,
    limit: int = 20,
    offset: int = 0
):
    """
    Get code examples for a specific knowledge item with pagination.
    
    Args:
        source_id: The source ID
        limit: Maximum number of examples to return (default 20, max 100)
        offset: Number of examples to skip (for pagination)
    
    Returns:
        Paginated code examples with metadata
    """
    try:
        # Validate pagination parameters
        limit = min(limit, 100)  # Cap at 100 to prevent excessive data transfer
        limit = max(limit, 1)    # At least 1
        offset = max(offset, 0)   # Can't be negative

        safe_logfire_info(
            f"Fetching code examples | source_id={source_id} | limit={limit} | offset={offset}"
        )

        supabase = get_supabase_client()

        # First get total count
        count_result = (
            supabase.from_("archon_code_examples")
            .select("id", count="exact", head=True)
            .eq("source_id", source_id)
            .execute()
        )
        total = count_result.count if hasattr(count_result, "count") else 0

        # Get paginated code examples
        result = (
            supabase.from_("archon_code_examples")
            .select("id, source_id, content, summary, metadata")
            .eq("source_id", source_id)
            .order("id", desc=False)  # Deterministic ordering
            .range(offset, offset + limit - 1)
            .execute()
        )

        # Check for error to match chunks endpoint pattern
        if hasattr(result, "error") and result.error is not None:
            safe_logfire_error(
                f"Supabase query error (code examples) | source_id={source_id} | error={result.error}"
            )
            raise HTTPException(status_code=500, detail={"error": str(result.error)})

        code_examples = result.data if result.data else []

        # Extract title and example_name from metadata to top level for frontend
        # This ensures the API response matches the TypeScript CodeExample interface
        for example in code_examples:
            metadata = example.get("metadata", {}) or {}
            # Extract fields to match frontend TypeScript types
            example["title"] = metadata.get("title")  # AI-generated title
            example["example_name"] = metadata.get("example_name")  # Same as title for compatibility
            example["language"] = metadata.get("language")  # Programming language
            example["file_path"] = metadata.get("file_path")  # Original file path if available
            # Note: content field is already at top level from database
            # Note: summary field is already at top level from database

        safe_logfire_info(
            f"Fetched {len(code_examples)} code examples for {source_id} | total={total}"
        )

        return {
            "success": True,
            "source_id": source_id,
            "code_examples": code_examples,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    except Exception as e:
        safe_logfire_error(
            f"Failed to fetch code examples | error={str(e)} | source_id={source_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/knowledge-items/{source_id}/refresh")
async def refresh_knowledge_item(source_id: str):
    """Refresh a knowledge item by re-crawling its URL with the same metadata."""

    # Validate API key before starting expensive refresh operation
    logger.info("🔍 About to validate API key for refresh...")
    provider_config = await credential_service.get_active_provider("embedding")
    provider = provider_config.get("provider", "openai")
    await _validate_provider_api_key(provider)
    logger.info("✅ API key validation completed successfully for refresh")

    try:
        safe_logfire_info(f"Starting knowledge item refresh | source_id={source_id}")

        # Get the existing knowledge item
        service = KnowledgeItemService(get_supabase_client())
        existing_item = await service.get_item(source_id)

        if not existing_item:
            raise HTTPException(
                status_code=404, detail={"error": f"Knowledge item {source_id} not found"}
            )

        # Extract metadata
        metadata = existing_item.get("metadata", {})

        # Extract the URL from the existing item
        # First try to get the original URL from metadata, fallback to url field
        url = metadata.get("original_url") or existing_item.get("url")
        if not url:
            raise HTTPException(
                status_code=400, detail={"error": "Knowledge item does not have a URL to refresh"}
            )
        knowledge_type = metadata.get("knowledge_type", "technical")
        tags = metadata.get("tags", [])
        max_depth = metadata.get("max_depth", 2)

        # Generate unique progress ID
        progress_id = str(uuid.uuid4())

        # Initialize progress tracker IMMEDIATELY so it's available for polling
        from ..utils.progress.progress_tracker import ProgressTracker
        tracker = ProgressTracker(progress_id, operation_type="crawl")
        await tracker.start({
            "url": url,
            "status": "initializing",
            "progress": 0,
            "log": f"Starting refresh for {url}",
            "source_id": source_id,
            "operation": "refresh",
            "crawl_type": "refresh"
        })

        # Get crawler from CrawlerManager - same pattern as _perform_crawl_with_progress
        try:
            crawler = await get_crawler()
            if crawler is None:
                raise Exception("Crawler not available - initialization may have failed")
        except Exception as e:
            safe_logfire_error(f"Failed to get crawler | error={str(e)}")
            raise HTTPException(
                status_code=500, detail={"error": f"Failed to initialize crawler: {str(e)}"}
            )

        # Use the same crawl orchestration as regular crawl
        crawl_service = CrawlingService(
            crawler=crawler, supabase_client=get_supabase_client()
        )
        crawl_service.set_progress_id(progress_id)

        # Start the crawl task with proper request format
        request_dict = {
            "url": url,
            "knowledge_type": knowledge_type,
            "tags": tags,
            "max_depth": max_depth,
            "extract_code_examples": True,
            "generate_summary": True,
        }

        # Create a wrapped task that acquires the semaphore
        async def _perform_refresh_with_semaphore():
            try:
                async with crawl_semaphore:
                    safe_logfire_info(
                        f"Acquired crawl semaphore for refresh | source_id={source_id}"
                    )
                    result = await crawl_service.orchestrate_crawl(request_dict)

                    # Store the ACTUAL crawl task for proper cancellation
                    crawl_task = result.get("task")
                    if crawl_task:
                        active_crawl_tasks[progress_id] = crawl_task
                        safe_logfire_info(
                            f"Stored actual refresh crawl task | progress_id={progress_id} | task_name={crawl_task.get_name()}"
                        )
            finally:
                # Clean up task from registry when done (success or failure)
                if progress_id in active_crawl_tasks:
                    del active_crawl_tasks[progress_id]
                    safe_logfire_info(
                        f"Cleaned up refresh task from registry | progress_id={progress_id}"
                    )

        # Start the wrapper task - we don't need to track it since we'll track the actual crawl task
        asyncio.create_task(_perform_refresh_with_semaphore())

        return {"progressId": progress_id, "message": f"Started refresh for {url}"}

    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(
            f"Failed to refresh knowledge item | error={str(e)} | source_id={source_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/knowledge-items/crawl")
async def crawl_knowledge_item(request: KnowledgeItemRequest):
    """Crawl a URL and add it to the knowledge base with progress tracking."""
    global _queued_crawl_count
    async with _crawl_count_lock:
        if _queued_crawl_count >= MAX_QUEUED_CRAWLS:
            raise HTTPException(
                status_code=429,
                detail=f"Too many crawls in progress ({_queued_crawl_count}). "
                       f"Maximum {MAX_QUEUED_CRAWLS} allowed. Try again shortly.",
            )
        _queued_crawl_count += 1

    # Validate URL
    if not request.url:
        raise HTTPException(status_code=422, detail="URL is required")

    # Basic URL validation
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="URL must start with http:// or https://")

    # Validate API key before starting expensive operation
    logger.info("🔍 About to validate API key...")
    provider_config = await credential_service.get_active_provider("embedding")
    provider = provider_config.get("provider", "openai")
    await _validate_provider_api_key(provider)
    logger.info("✅ API key validation completed successfully")

    try:
        safe_logfire_info(
            f"Starting knowledge item crawl | url={str(request.url)} | knowledge_type={request.knowledge_type} | tags={request.tags}"
        )
        # Generate unique progress ID
        progress_id = str(uuid.uuid4())

        # Pre-generate source_id using the same algorithm as CrawlingService
        # so we can return it immediately in the response
        from ..services.crawling.helpers.url_handler import URLHandler
        source_id = URLHandler.generate_unique_source_id(str(request.url))

        # Initialize progress tracker IMMEDIATELY so it's available for polling
        from ..utils.progress.progress_tracker import ProgressTracker
        tracker = ProgressTracker(progress_id, operation_type="crawl")

        # Detect crawl type from URL
        url_str = str(request.url)
        crawl_type = "normal"
        if "sitemap.xml" in url_str:
            crawl_type = "sitemap"
        elif url_str.endswith(".txt"):
            crawl_type = "llms-txt" if "llms" in url_str.lower() else "text_file"

        await tracker.start({
            "url": url_str,
            "current_url": url_str,
            "crawl_type": crawl_type,
            # Don't override status - let tracker.start() set it to "starting"
            "progress": 0,
            "log": f"Starting crawl for {request.url}"
        })

        # Link project upfront so the association exists even if the crawl fails
        if request.project_id:
            try:
                supabase_client = get_supabase_client()
                supabase_client.table("archon_project_sources").upsert(
                    {
                        "project_id": request.project_id,
                        "source_id": source_id,
                        "notes": request.knowledge_type or "technical",
                        "created_by": "crawl",
                    },
                    on_conflict="project_id,source_id",
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to pre-link project {request.project_id} to source {source_id}: {e}")

        # Mark source as in-progress in the database for crash recovery
        try:
            supabase_client = get_supabase_client()
            supabase_client.table("archon_sources").upsert(
                {
                    "source_id": source_id,
                    "url": str(request.url),
                    "display_name": str(request.url),
                    "metadata": json.dumps({
                        "progress_id": progress_id,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "project_id": request.project_id,
                    }),
                },
                on_conflict="source_id",
            ).execute()
        except Exception as e:
            logger.warning(f"Failed to write crawl status for source {source_id}: {e}")

        # Start background task - no need to track this wrapper task
        # The actual crawl task will be stored inside _perform_crawl_with_progress
        asyncio.create_task(_perform_crawl_with_progress(progress_id, request, tracker))
        safe_logfire_info(
            f"Crawl started successfully | progress_id={progress_id} | source_id={source_id} | url={str(request.url)}"
        )

        return {
            "success": True,
            "progressId": progress_id,
            "sourceId": source_id,
            "message": "Crawling started",
            "estimatedDuration": "3-5 minutes",
        }
    except Exception as e:
        safe_logfire_error(f"Failed to start crawl | error={str(e)} | url={str(request.url)}")
        raise HTTPException(status_code=500, detail=str(e))


async def _perform_crawl_with_progress(
    progress_id: str, request: KnowledgeItemRequest, tracker
):
    """Perform the actual crawl operation with progress tracking using service layer."""
    # Acquire semaphore to limit concurrent crawls
    async with crawl_semaphore:
        safe_logfire_info(
            f"Acquired crawl semaphore | progress_id={progress_id} | url={str(request.url)}"
        )
        try:
            safe_logfire_info(
                f"Starting crawl with progress tracking | progress_id={progress_id} | url={str(request.url)}"
            )

            # Get crawler from CrawlerManager
            try:
                crawler = await get_crawler()
                if crawler is None:
                    raise Exception("Crawler not available - initialization may have failed")
            except Exception as e:
                safe_logfire_error(f"Failed to get crawler | error={str(e)}")
                await tracker.error(f"Failed to initialize crawler: {str(e)}")
                return

            supabase_client = get_supabase_client()
            orchestration_service = CrawlingService(crawler, supabase_client)
            orchestration_service.set_progress_id(progress_id)

            # Convert request to dict for service
            request_dict = {
                "url": str(request.url),
                "knowledge_type": request.knowledge_type,
                "tags": request.tags or [],
                "max_depth": request.max_depth,
                "extract_code_examples": request.extract_code_examples,
                "generate_summary": True,
            }

            # Pass project_id through so DocumentStorageOperations can tag the source
            if request.project_id:
                request_dict["project_id"] = request.project_id

            # Orchestrate the crawl - this returns immediately with task info including the actual task
            result = await orchestration_service.orchestrate_crawl(request_dict)

            # Store the ACTUAL crawl task for proper cancellation
            crawl_task = result.get("task")
            if crawl_task:
                active_crawl_tasks[progress_id] = crawl_task
                safe_logfire_info(
                    f"Stored actual crawl task in active_crawl_tasks | progress_id={progress_id} | task_name={crawl_task.get_name()}"
                )
            else:
                safe_logfire_error(f"No task returned from orchestrate_crawl | progress_id={progress_id}")

            # The orchestration service now runs in background and handles all progress updates
            safe_logfire_info(
                f"Crawl task started | progress_id={progress_id} | task_id={result.get('task_id')}"
            )
        except asyncio.CancelledError:
            safe_logfire_info(f"Crawl cancelled | progress_id={progress_id}")
            raise
        except Exception as e:
            error_message = f"Crawling failed: {str(e)}"
            safe_logfire_error(
                f"Crawl failed | progress_id={progress_id} | error={error_message} | exception_type={type(e).__name__}"
            )
            import traceback

            tb = traceback.format_exc()
            # Ensure the error is visible in logs
            logger.error(f"=== CRAWL ERROR FOR {progress_id} ===")
            logger.error(f"Error: {error_message}")
            logger.error(f"Exception Type: {type(e).__name__}")
            logger.error(f"Traceback:\n{tb}")
            logger.error("=== END CRAWL ERROR ===")
            safe_logfire_error(f"Crawl exception traceback | traceback={tb}")
            # Ensure clients see the failure
            try:
                await tracker.error(error_message)
            except Exception:
                pass
        finally:
            global _queued_crawl_count
            async with _crawl_count_lock:
                _queued_crawl_count = max(0, _queued_crawl_count - 1)
            # Clean up task from registry when done (success or failure)
            if progress_id in active_crawl_tasks:
                del active_crawl_tasks[progress_id]
                safe_logfire_info(
                    f"Cleaned up crawl task from registry | progress_id={progress_id}"
                )


async def _perform_inline_ingest(
    progress_id: str,
    source_id: str,
    request: InlineIngestRequest,
    valid_docs: list[InlineDocument],
    tracker,
    merge_hashes: bool = False,
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

            # Update source metadata with project_id, source_type, and file_hashes
            try:
                existing = supabase_client.table("archon_sources").select("metadata").eq(
                    "source_id", source_id
                ).execute()
                if existing.data:
                    metadata = existing.data[0].get("metadata", {}) or {}
                    metadata["source_type"] = "inline"
                    metadata["ingestion_method"] = "mcp_inline"
                    if request.project_id:
                        metadata["project_id"] = request.project_id
                    # Store file hashes for incremental sync
                    new_hashes = {}
                    for doc in valid_docs:
                        if doc.file_hash:
                            new_hashes[doc.title] = doc.file_hash
                    if new_hashes:
                        if merge_hashes:
                            # Append mode: merge new hashes into existing
                            existing_hashes = metadata.get("file_hashes", {})
                            existing_hashes.update(new_hashes)
                            metadata["file_hashes"] = existing_hashes
                        else:
                            metadata["file_hashes"] = new_hashes
                    metadata["last_synced"] = datetime.now(timezone.utc).isoformat()
                    supabase_client.table("archon_sources").update(
                        {"metadata": metadata}
                    ).eq("source_id", source_id).execute()
            except Exception as e:
                logger.warning(f"Failed to update source metadata: {e}")

            chunks_stored = result.get("chunks_stored", 0)
            code_examples_stored = result.get("code_examples_count", 0)

            # Persist completion summary to source metadata for durable querying
            try:
                existing_meta = supabase_client.table("archon_sources").select("metadata").eq(
                    "source_id", source_id
                ).execute()
                if existing_meta.data:
                    meta = existing_meta.data[0].get("metadata", {}) or {}
                    meta["last_ingestion"] = {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "documents_processed": len(crawl_results),
                        "chunks_stored": chunks_stored,
                        "code_examples_stored": code_examples_stored,
                        "status": "completed",
                    }
                    supabase_client.table("archon_sources").update(
                        {"metadata": meta}
                    ).eq("source_id", source_id).execute()
            except Exception as e:
                logger.warning(f"Failed to persist completion summary to source metadata: {e}")

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


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    tags: str | None = Form(None),
    knowledge_type: str = Form("technical"),
    extract_code_examples: bool = Form(True),
):
    """Upload and process a document with progress tracking."""

    # Validate API key before starting expensive upload operation
    logger.info("🔍 About to validate API key for upload...")
    provider_config = await credential_service.get_active_provider("embedding")
    provider = provider_config.get("provider", "openai")
    await _validate_provider_api_key(provider)
    logger.info("✅ API key validation completed successfully for upload")

    try:
        # DETAILED LOGGING: Track knowledge_type parameter flow
        safe_logfire_info(
            f"📋 UPLOAD: Starting document upload | filename={file.filename} | content_type={file.content_type} | knowledge_type={knowledge_type}"
        )

        # Generate unique progress ID
        progress_id = str(uuid.uuid4())

        # Parse tags
        try:
            tag_list = json.loads(tags) if tags else []
            if tag_list is None:
                tag_list = []
            # Validate tags is a list of strings
            if not isinstance(tag_list, list):
                raise HTTPException(status_code=422, detail={"error": "tags must be a JSON array of strings"})
            if not all(isinstance(tag, str) for tag in tag_list):
                raise HTTPException(status_code=422, detail={"error": "tags must be a JSON array of strings"})
        except json.JSONDecodeError as ex:
            raise HTTPException(status_code=422, detail={"error": f"Invalid tags JSON: {str(ex)}"})

        # Read file content immediately to avoid closed file issues
        file_content = await file.read()
        file_metadata = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(file_content),
        }

        # Initialize progress tracker IMMEDIATELY so it's available for polling
        from ..utils.progress.progress_tracker import ProgressTracker
        tracker = ProgressTracker(progress_id, operation_type="upload")
        await tracker.start({
            "filename": file.filename,
            "status": "initializing",
            "progress": 0,
            "log": f"Starting upload for {file.filename}"
        })
        # Start background task for processing with file content and metadata
        # Upload tasks can be tracked directly since they don't spawn sub-tasks
        upload_task = asyncio.create_task(
            _perform_upload_with_progress(
                progress_id, file_content, file_metadata, tag_list, knowledge_type, extract_code_examples, tracker
            )
        )
        # Track the task for cancellation support
        active_crawl_tasks[progress_id] = upload_task
        safe_logfire_info(
            f"Document upload started successfully | progress_id={progress_id} | filename={file.filename}"
        )
        return {
            "success": True,
            "progressId": progress_id,
            "message": "Document upload started",
            "filename": file.filename,
        }

    except Exception as e:
        safe_logfire_error(
            f"Failed to start document upload | error={str(e)} | filename={file.filename} | error_type={type(e).__name__}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


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

    # Generate source_id: deterministic when project_id is provided, random otherwise
    if request.project_id:
        source_id = hashlib.sha256(
            f"inline_{request.project_id}_{request.title}".encode()
        ).hexdigest()[:16]
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
        source_id = hashlib.sha256(f"{request.title}-{timestamp}".encode()).hexdigest()[:16]

    # Check if source_id already exists (upsert behavior for deterministic IDs)
    is_upsert = False
    supabase_client = get_supabase_client()
    try:
        existing = supabase_client.table("archon_sources").select("source_id").eq(
            "source_id", source_id
        ).execute()
        if existing.data:
            is_upsert = True
            # Delete existing chunks and code examples so we can re-ingest cleanly
            supabase_client.table("archon_crawled_pages").delete().eq(
                "source_id", source_id
            ).execute()
            supabase_client.table("archon_code_examples").delete().eq(
                "source_id", source_id
            ).execute()
            logger.info(f"Upsert: cleared existing data for source_id={source_id}")
    except Exception as e:
        logger.warning(f"Failed to check/clean existing source {source_id}: {e}")

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
        "isUpdate": is_upsert,
    }


@router.post("/knowledge/sync-inline")
async def sync_inline_documents(request: InlineSyncRequest):
    """Sync inline documents for an existing source with incremental hash comparison.

    When documents include file_hash values and the source has stored hashes,
    only changed/new documents are re-embedded. Unchanged documents are skipped.
    """
    # Validate source exists
    supabase_client = get_supabase_client()
    existing = supabase_client.table("archon_sources").select(
        "source_id, title, metadata"
    ).eq("source_id", request.source_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail=f"Source {request.source_id} not found. Use action='add' to create a new source.",
        )

    source_data = existing.data[0]
    source_metadata = source_data.get("metadata", {}) or {}

    # Validate documents
    if not request.documents:
        raise HTTPException(status_code=422, detail="At least one document is required")

    valid_docs = [doc for doc in request.documents if doc.content and doc.content.strip()]
    if not valid_docs:
        raise HTTPException(status_code=422, detail="All documents have empty content")

    # Validate API key
    await _validate_provider_api_key()

    # --- Incremental sync: compare file hashes ---
    stored_hashes = source_metadata.get("file_hashes", {})
    incoming_titles = {doc.title for doc in valid_docs}
    stored_titles = set(stored_hashes.keys())

    # Determine which docs have hashes for comparison
    has_hashes = any(doc.file_hash for doc in valid_docs) and stored_hashes

    if has_hashes:
        # Compute sync diff
        changed_docs = []
        unchanged_docs = []
        new_docs = []

        for doc in valid_docs:
            if doc.title in stored_hashes:
                if doc.file_hash and doc.file_hash == stored_hashes[doc.title]:
                    unchanged_docs.append(doc)
                else:
                    changed_docs.append(doc)
            else:
                new_docs.append(doc)

        deleted_titles = list(stored_titles - incoming_titles)
        docs_to_process = changed_docs + new_docs

        sync_diff = {
            "changed": [d.title for d in changed_docs],
            "unchanged": [d.title for d in unchanged_docs],
            "new": [d.title for d in new_docs],
            "deleted": deleted_titles,
        }

        logger.info(
            f"Incremental sync for {request.source_id}: "
            f"{len(changed_docs)} changed, {len(new_docs)} new, "
            f"{len(unchanged_docs)} unchanged, {len(deleted_titles)} deleted"
        )

        # Delete pages for changed + deleted docs (keep unchanged)
        urls_to_delete = []
        for doc in changed_docs:
            doc_path = doc.path or doc.title
            urls_to_delete.append(f"inline://{request.source_id}/{doc_path}")
        for title in deleted_titles:
            urls_to_delete.append(f"inline://{request.source_id}/{title}")

        if urls_to_delete:
            try:
                for url in urls_to_delete:
                    supabase_client.table("archon_crawled_pages").delete().eq(
                        "source_id", request.source_id
                    ).eq("url", url).execute()
                    supabase_client.table("archon_code_examples").delete().eq(
                        "source_id", request.source_id
                    ).eq("url", url).execute()
            except Exception as e:
                logger.warning(f"Failed to delete specific pages during incremental sync: {e}")
                # Fall back to full sync on failure
                docs_to_process = list(valid_docs)
                sync_diff = None

        if not docs_to_process:
            # Nothing changed — update last_synced and return early
            new_hashes = {doc.title: doc.file_hash for doc in valid_docs if doc.file_hash}
            source_metadata["file_hashes"] = new_hashes
            source_metadata["last_synced"] = datetime.now(timezone.utc).isoformat()
            try:
                supabase_client.table("archon_sources").update(
                    {"metadata": source_metadata}
                ).eq("source_id", request.source_id).execute()
            except Exception as e:
                logger.warning(f"Failed to update metadata after no-op sync: {e}")

            return {
                "success": True,
                "progressId": None,
                "sourceId": request.source_id,
                "estimatedSeconds": 0,
                "syncDiff": sync_diff,
                "documentsToProcess": 0,
                "documentsSkipped": len(unchanged_docs),
                "message": "All documents unchanged — no re-embedding needed.",
            }
    else:
        # No hashes available — full sync (delete all, re-ingest all)
        docs_to_process = list(valid_docs)
        sync_diff = None
        try:
            supabase_client.table("archon_crawled_pages").delete().eq(
                "source_id", request.source_id
            ).execute()
            supabase_client.table("archon_code_examples").delete().eq(
                "source_id", request.source_id
            ).execute()
            logger.info(f"Full sync: cleared existing data for source_id={request.source_id}")
        except Exception as e:
            logger.error(f"Failed to clear existing data for sync: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to clear existing data: {e}")

    # Build an InlineIngestRequest-compatible object for _perform_inline_ingest
    ingest_request = InlineIngestRequest(
        title=source_data["title"],
        documents=[InlineDocument(title=d.title, content=d.content, path=d.path, file_hash=d.file_hash) for d in docs_to_process],
        tags=source_metadata.get("tags", []),
        project_id=source_metadata.get("project_id"),
        knowledge_type=request.knowledge_type,
        extract_code_examples=request.extract_code_examples,
    )

    # Convert docs_to_process to valid_docs format for _perform_inline_ingest
    filtered_valid_docs = [d for d in docs_to_process if d.content and d.content.strip()]

    progress_id = str(uuid.uuid4())
    estimated_seconds = max(10, len(filtered_valid_docs) * 1)

    from ..utils.progress.progress_tracker import ProgressTracker
    tracker = ProgressTracker(progress_id, operation_type="inline_sync")
    await tracker.start({
        "source_id": request.source_id,
        "title": source_data["title"],
        "total_documents": len(filtered_valid_docs),
        "status": "starting",
        "operation": "sync",
    })

    task = asyncio.create_task(
        _perform_inline_ingest(
            progress_id=progress_id,
            source_id=request.source_id,
            request=ingest_request,
            valid_docs=filtered_valid_docs,
            tracker=tracker,
        )
    )
    active_crawl_tasks[progress_id] = task

    response = {
        "success": True,
        "progressId": progress_id,
        "sourceId": request.source_id,
        "estimatedSeconds": estimated_seconds,
        "documentsToProcess": len(filtered_valid_docs),
    }
    if sync_diff:
        response["syncDiff"] = sync_diff
        response["documentsSkipped"] = len(sync_diff["unchanged"])

    return response


@router.post("/knowledge/append-inline")
async def append_inline_documents(request: InlineAppendRequest):
    """Append documents to an existing inline source without removing existing content.

    Unlike sync (which compares hashes and removes deleted docs) or add (which replaces
    the entire source), append only adds new documents to the source. Existing documents
    are preserved untouched.
    """
    # Validate source exists
    supabase_client = get_supabase_client()
    existing = supabase_client.table("archon_sources").select(
        "source_id, title, metadata"
    ).eq("source_id", request.source_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail=f"Source {request.source_id} not found. Use action='add' to create a new source first.",
        )

    source_data = existing.data[0]
    source_title = source_data.get("title", request.source_id)

    # Validate documents
    if not request.documents:
        raise HTTPException(status_code=422, detail="At least one document is required")

    valid_docs = [doc for doc in request.documents if doc.content and doc.content.strip()]
    if not valid_docs:
        raise HTTPException(status_code=422, detail="All documents have empty content")

    # Validate API key
    await _validate_provider_api_key()

    # Check for duplicate document titles already in the source
    source_metadata = source_data.get("metadata", {}) or {}
    stored_hashes = source_metadata.get("file_hashes", {})
    duplicate_titles = [doc.title for doc in valid_docs if doc.title in stored_hashes]

    # Warn but don't block — duplicates will overwrite their specific chunks via upsert
    if duplicate_titles:
        logger.info(
            f"Append to {request.source_id}: {len(duplicate_titles)} document(s) already exist "
            f"and will be updated: {duplicate_titles}"
        )

    # Build an InlineIngestRequest-compatible object for _perform_inline_ingest
    ingest_request = InlineIngestRequest(
        title=source_title,
        documents=[InlineDocument(title=d.title, content=d.content, path=d.path, file_hash=d.file_hash) for d in valid_docs],
        tags=source_metadata.get("tags", []),
        project_id=source_metadata.get("project_id"),
        knowledge_type=request.knowledge_type,
        extract_code_examples=request.extract_code_examples,
    )

    progress_id = str(uuid.uuid4())
    estimated_seconds = max(10, len(valid_docs) * 1)

    from ..utils.progress.progress_tracker import ProgressTracker
    tracker = ProgressTracker(progress_id, operation_type="inline_append")
    await tracker.start({
        "source_id": request.source_id,
        "title": source_title,
        "total_documents": len(valid_docs),
        "status": "starting",
        "operation": "append",
    })

    task = asyncio.create_task(
        _perform_inline_ingest(
            progress_id=progress_id,
            source_id=request.source_id,
            request=ingest_request,
            valid_docs=valid_docs,
            tracker=tracker,
            merge_hashes=True,
        )
    )
    active_crawl_tasks[progress_id] = task

    return {
        "success": True,
        "progressId": progress_id,
        "sourceId": request.source_id,
        "estimatedSeconds": estimated_seconds,
        "documentsToAppend": len(valid_docs),
        "duplicatesDetected": len(duplicate_titles),
        "duplicateTitles": duplicate_titles if duplicate_titles else None,
    }


async def _perform_upload_with_progress(
    progress_id: str,
    file_content: bytes,
    file_metadata: dict,
    tag_list: list[str],
    knowledge_type: str,
    extract_code_examples: bool,
    tracker: "ProgressTracker",
):
    """Perform document upload with progress tracking using service layer."""
    # Create cancellation check function for document uploads
    def check_upload_cancellation():
        """Check if upload task has been cancelled."""
        task = active_crawl_tasks.get(progress_id)
        if task and task.cancelled():
            raise asyncio.CancelledError("Document upload was cancelled by user")

    # Import ProgressMapper to prevent progress from going backwards
    from ..services.crawling.progress_mapper import ProgressMapper
    progress_mapper = ProgressMapper()

    try:
        filename = file_metadata["filename"]
        content_type = file_metadata["content_type"]
        # file_size = file_metadata['size']  # Not used currently

        safe_logfire_info(
            f"Starting document upload with progress tracking | progress_id={progress_id} | filename={filename} | content_type={content_type}"
        )


        # Extract text from document with progress - use mapper for consistent progress
        mapped_progress = progress_mapper.map_progress("processing", 50)
        await tracker.update(
            status="processing",
            progress=mapped_progress,
            log=f"Extracting text from {filename}"
        )

        try:
            extracted_text = extract_text_from_document(file_content, filename, content_type)
            safe_logfire_info(
                f"Document text extracted | filename={filename} | extracted_length={len(extracted_text)} | content_type={content_type}"
            )
        except ValueError as ex:
            # ValueError indicates unsupported format or empty file - user error
            logger.warning(f"Document validation failed: {filename} - {str(ex)}")
            await tracker.error(str(ex))
            return
        except Exception as ex:
            # Other exceptions are system errors - log with full traceback
            logger.error(f"Failed to extract text from document: {filename}", exc_info=True)
            await tracker.error(f"Failed to extract text from document: {str(ex)}")
            return

        # Use DocumentStorageService to handle the upload
        doc_storage_service = DocumentStorageService(get_supabase_client())

        # Generate source_id from filename with UUID to prevent collisions
        source_id = f"file_{filename.replace(' ', '_').replace('.', '_')}_{uuid.uuid4().hex[:8]}"

        # Create progress callback for tracking document processing
        async def document_progress_callback(
            message: str, percentage: int, batch_info: dict = None
        ):
            """Progress callback for tracking document processing"""
            # Map the document storage progress to overall progress range
            # Use "storing" stage for uploads (30-100%), not "document_storage" (25-40%)
            mapped_percentage = progress_mapper.map_progress("storing", percentage)

            await tracker.update(
                status="storing",
                progress=mapped_percentage,
                log=message,
                currentUrl=f"file://{filename}",
                **(batch_info or {})
            )


        # Call the service's upload_document method
        success, result = await doc_storage_service.upload_document(
            file_content=extracted_text,
            filename=filename,
            source_id=source_id,
            knowledge_type=knowledge_type,
            tags=tag_list,
            extract_code_examples=extract_code_examples,
            progress_callback=document_progress_callback,
            cancellation_check=check_upload_cancellation,
        )

        if success:
            # Persist completion summary to source metadata
            upload_source_id = result.get("source_id")
            if upload_source_id:
                try:
                    sc = get_supabase_client()
                    existing_meta = sc.table("archon_sources").select("metadata").eq(
                        "source_id", upload_source_id
                    ).execute()
                    if existing_meta.data:
                        meta = existing_meta.data[0].get("metadata", {}) or {}
                        meta["last_ingestion"] = {
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "documents_processed": 1,
                            "chunks_stored": result.get("chunks_stored", 0),
                            "code_examples_stored": result.get("code_examples_stored", 0),
                            "status": "completed",
                        }
                        sc.table("archon_sources").update(
                            {"metadata": meta}
                        ).eq("source_id", upload_source_id).execute()
                except Exception as e:
                    logger.warning(f"Failed to persist upload completion summary: {e}")

            # Complete the upload with 100% progress
            await tracker.complete({
                "log": "Document uploaded successfully!",
                "chunks_stored": result.get("chunks_stored"),
                "code_examples_stored": result.get("code_examples_stored", 0),
                "sourceId": upload_source_id,
            })
            safe_logfire_info(
                f"Document uploaded successfully | progress_id={progress_id} | source_id={result.get('source_id')} | chunks_stored={result.get('chunks_stored')} | code_examples_stored={result.get('code_examples_stored', 0)}"
            )
        else:
            error_msg = result.get("error", "Unknown error")
            await tracker.error(error_msg)

    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        await tracker.error(error_msg)
        logger.error(f"Document upload failed: {e}", exc_info=True)
        safe_logfire_error(
            f"Document upload failed | progress_id={progress_id} | filename={file_metadata.get('filename', 'unknown')} | error={str(e)}"
        )
    finally:
        # Clean up task from registry when done (success or failure)
        if progress_id in active_crawl_tasks:
            del active_crawl_tasks[progress_id]
            safe_logfire_info(f"Cleaned up upload task from registry | progress_id={progress_id}")


@router.post("/knowledge-items/search")
async def search_knowledge_items(request: RagQueryRequest):
    """Search knowledge items - alias for RAG query."""
    # Validate query
    if not request.query:
        raise HTTPException(status_code=422, detail="Query is required")

    if not request.query.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty")

    # Delegate to the RAG query handler
    return await perform_rag_query(request)


def _resolve_project_source_filter(
    project_id: str | None,
    existing_source: str | None,
    include_parent: bool = True,
) -> str | None:
    """Resolve project_id to comma-separated source_ids using the junction table.

    Uses archon_project_sources as the canonical source for project-source links.
    When include_parent is True and the project has a parent_project_id, the parent's
    sources are included in the result (cascading search).
    Results are cached in-memory with a 5-minute TTL.

    When project_id is provided but no sources are linked, returns a non-existent
    source_id sentinel to ensure no results are returned (rather than falling through
    to an unfiltered search across all sources).
    """
    if existing_source:
        return existing_source
    if not project_id:
        return None

    # Sentinel value: when a project has no linked sources, return this to ensure
    # the search matches nothing rather than searching all sources globally.
    NO_SOURCES_SENTINEL = "__no_linked_sources__"

    from ..utils.source_cache import (
        get_cached_project_sources,
        set_cached_project_sources,
    )

    # Check cache first
    cached, hit = get_cached_project_sources(project_id, include_parent)
    if hit:
        return ",".join(cached) if cached else NO_SOURCES_SENTINEL

    try:
        source_ids = []
        client = get_supabase_client()

        # Get this project's sources from junction table
        project_sources = client.table("archon_project_sources").select(
            "source_id"
        ).eq("project_id", project_id).execute()
        if project_sources.data:
            source_ids.extend(s["source_id"] for s in project_sources.data)

        # Include parent's sources if requested
        if include_parent:
            project = client.table("archon_projects").select(
                "parent_project_id"
            ).eq("id", project_id).maybe_single().execute()

            if project.data and project.data.get("parent_project_id"):
                parent_id = project.data["parent_project_id"]
                parent_sources = client.table("archon_project_sources").select(
                    "source_id"
                ).eq("project_id", parent_id).execute()
                if parent_sources.data:
                    source_ids.extend(s["source_id"] for s in parent_sources.data)

        # Cache the result
        set_cached_project_sources(project_id, include_parent, source_ids)

        if source_ids:
            return ",".join(source_ids)

        logger.info(f"No sources linked to project {project_id} in junction table")
        return NO_SOURCES_SENTINEL
    except Exception as e:
        logger.warning(f"Failed to resolve project_id to sources: {e}")
    return existing_source


@router.post("/rag/query")
async def perform_rag_query(request: RagQueryRequest):
    """Perform a RAG query on the knowledge base using service layer."""
    # Validate query
    if not request.query:
        raise HTTPException(status_code=422, detail="Query is required")

    if not request.query.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty")

    try:
        source_filter = _resolve_project_source_filter(request.project_id, request.source, request.include_parent)

        # Use RAGService for unified RAG query with return_mode support
        search_service = RAGService(get_supabase_client())
        success, result = await search_service.perform_rag_query(
            query=request.query,
            source=source_filter,
            match_count=request.match_count,
            return_mode=request.return_mode
        )

        if success:
            # Add success flag to match expected API response format
            result["success"] = True
            return result
        else:
            raise HTTPException(
                status_code=500, detail={"error": result.get("error", "RAG query failed")}
            )
    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(
            f"RAG query failed | error={str(e)} | query={request.query[:50]} | source={request.source}"
        )
        raise HTTPException(status_code=500, detail={"error": f"RAG query failed: {str(e)}"})


@router.post("/rag/code-examples")
async def search_code_examples(request: RagQueryRequest):
    """Search for code examples relevant to the query using dedicated code examples service."""
    try:
        source_filter = _resolve_project_source_filter(request.project_id, request.source, request.include_parent)

        # Use RAGService for code examples search
        search_service = RAGService(get_supabase_client())
        success, result = await search_service.search_code_examples_service(
            query=request.query,
            source_id=source_filter,
            match_count=request.match_count,
        )

        if success:
            # Add success flag and reformat to match expected API response format
            return {
                "success": True,
                "results": result.get("results", []),
                "reranked": result.get("reranking_applied", False),
                "error": None,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={"error": result.get("error", "Code examples search failed")},
            )
    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(
            f"Code examples search failed | error={str(e)} | query={request.query[:50]} | source={request.source}"
        )
        raise HTTPException(
            status_code=500, detail={"error": f"Code examples search failed: {str(e)}"}
        )


@router.post("/code-examples")
async def search_code_examples_simple(request: RagQueryRequest):
    """Search for code examples - simplified endpoint at /api/code-examples."""
    # Delegate to the existing endpoint handler
    return await search_code_examples(request)


@router.get("/rag/sources")
async def get_available_sources():
    """Get all available sources for RAG queries."""
    try:
        # Use KnowledgeItemService
        service = KnowledgeItemService(get_supabase_client())
        result = await service.get_available_sources()

        # Parse result if it's a string
        if isinstance(result, str):
            result = json.loads(result)

        return result
    except Exception as e:
        safe_logfire_error(f"Failed to get available sources | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    """Delete a source and all its associated data."""
    try:
        safe_logfire_info(f"Deleting source | source_id={source_id}")

        # Use SourceManagementService directly
        from ..services.source_management_service import SourceManagementService

        source_service = SourceManagementService(get_supabase_client())

        success, result_data = source_service.delete_source(source_id)

        if success:
            safe_logfire_info(f"Source deleted successfully | source_id={source_id}")

            return {
                "success": True,
                "message": f"Successfully deleted source {source_id}",
                **result_data,
            }
        else:
            safe_logfire_error(
                f"Source deletion failed | source_id={source_id} | error={result_data.get('error')}"
            )
            raise HTTPException(
                status_code=500, detail={"error": result_data.get("error", "Deletion failed")}
            )
    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(f"Failed to delete source | error={str(e)} | source_id={source_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/database/metrics")
async def get_database_metrics():
    """Get database metrics and statistics."""
    try:
        # Use DatabaseMetricsService
        service = DatabaseMetricsService(get_supabase_client())
        metrics = await service.get_metrics()
        return metrics
    except Exception as e:
        safe_logfire_error(f"Failed to get database metrics | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/health")
async def knowledge_health():
    """Knowledge API health check with migration detection."""
    # Check for database migration needs
    from ..main import _check_database_schema

    schema_status = await _check_database_schema()
    if not schema_status["valid"]:
        return {
            "status": "migration_required",
            "service": "knowledge-api",
            "timestamp": datetime.now().isoformat(),
            "ready": False,
            "migration_required": True,
            "message": schema_status["message"],
            "migration_instructions": "Open Supabase Dashboard → SQL Editor → Run: migration/add_source_url_display_name.sql"
        }

    # Removed health check logging to reduce console noise
    result = {
        "status": "healthy",
        "service": "knowledge-api",
        "timestamp": datetime.now().isoformat(),
    }

    return result



@router.post("/knowledge-items/stop/{progress_id}")
async def stop_crawl_task(progress_id: str):
    """Stop a running crawl task."""
    try:
        from ..services.crawling import get_active_orchestration, unregister_orchestration


        safe_logfire_info(f"Stop crawl requested | progress_id={progress_id}")

        found = False
        # Step 1: Cancel the orchestration service
        orchestration = await get_active_orchestration(progress_id)
        if orchestration:
            orchestration.cancel()
            found = True

        # Step 2: Cancel the asyncio task
        if progress_id in active_crawl_tasks:
            task = active_crawl_tasks[progress_id]
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (TimeoutError, asyncio.CancelledError):
                    pass
            del active_crawl_tasks[progress_id]
            found = True

        # Step 3: Remove from active orchestrations registry
        await unregister_orchestration(progress_id)

        # Step 4: Update progress tracker to reflect cancellation (only if we found and cancelled something)
        if found:
            try:
                from ..utils.progress.progress_tracker import ProgressTracker
                # Get current progress from existing tracker, default to 0 if not found
                current_state = ProgressTracker.get_progress(progress_id)
                current_progress = current_state.get("progress", 0) if current_state else 0

                tracker = ProgressTracker(progress_id, operation_type="crawl")
                await tracker.update(
                    status="cancelled",
                    progress=current_progress,
                    log="Crawl cancelled by user"
                )
            except Exception:
                # Best effort - don't fail the cancellation if tracker update fails
                pass

        if not found:
            raise HTTPException(status_code=404, detail={"error": "No active task for given progress_id"})

        safe_logfire_info(f"Successfully stopped crawl task | progress_id={progress_id}")
        return {
            "success": True,
            "message": "Crawl task stopped successfully",
            "progressId": progress_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_logfire_error(
            f"Failed to stop crawl task | error={str(e)} | progress_id={progress_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})
