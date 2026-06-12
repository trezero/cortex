"""
Base Search Strategy

Implements the foundational vector similarity search that all other strategies build upon.
This is the core semantic search functionality.
"""

from typing import Any

from supabase import Client

from ...config.logfire_config import get_logger, safe_span

logger = get_logger(__name__)

# Fixed similarity threshold for vector results
SIMILARITY_THRESHOLD = 0.05


class BaseSearchStrategy:
    """Base strategy implementing fundamental vector similarity search"""

    def __init__(self, supabase_client: Client):
        """Initialize with database client"""
        self.supabase_client = supabase_client

    async def vector_search(
        self,
        query_embedding: list[float],
        match_count: int,
        filter_metadata: dict | None = None,
        table_rpc: str = "match_cortex_crawled_pages",
    ) -> list[dict[str, Any]]:
        """
        Perform basic vector similarity search.

        This is the foundational semantic search that all strategies use.

        Args:
            query_embedding: The embedding vector for the query
            match_count: Number of results to return
            filter_metadata: Optional metadata filters. Supports:
                - {"source": "single_source_id"} for single source filtering
                - {"source_ids": ["id1", "id2"]} for multi-source filtering
            table_rpc: The RPC function to call (match_cortex_crawled_pages or match_cortex_code_examples)

        Returns:
            List of matching documents with similarity scores
        """
        with safe_span("base_vector_search", table=table_rpc, match_count=match_count) as span:
            try:
                # Check for multi-source filtering
                source_ids_filter = None
                if filter_metadata and "source_ids" in filter_metadata:
                    source_ids_filter = filter_metadata["source_ids"]
                    # Remove source_ids from filter_metadata to avoid passing it to RPC
                    filter_metadata = {k: v for k, v in filter_metadata.items() if k != "source_ids"}

                # Build RPC parameters
                rpc_params = {"query_embedding": query_embedding, "match_count": match_count}

                # Add filter parameters
                if filter_metadata:
                    if "source" in filter_metadata:
                        rpc_params["source_filter"] = filter_metadata["source"]
                        rpc_params["filter"] = {}
                    else:
                        rpc_params["filter"] = filter_metadata
                else:
                    rpc_params["filter"] = {}

                # For multi-source filtering, request more results since we'll filter in Python
                if source_ids_filter:
                    rpc_params["match_count"] = match_count * 5

                # Execute search
                response = self.supabase_client.rpc(table_rpc, rpc_params).execute()

                # Filter by similarity threshold and optionally by source_ids
                filtered_results = []
                if response.data:
                    for result in response.data:
                        similarity = float(result.get("similarity", 0.0))
                        if similarity < SIMILARITY_THRESHOLD:
                            continue
                        # Apply multi-source filter if specified
                        if source_ids_filter and result.get("source_id") not in source_ids_filter:
                            continue
                        filtered_results.append(result)

                # Trim to requested match_count after filtering
                if source_ids_filter and len(filtered_results) > match_count:
                    filtered_results = filtered_results[:match_count]

                span.set_attribute("results_found", len(filtered_results))
                span.set_attribute(
                    "results_filtered",
                    len(response.data) - len(filtered_results) if response.data else 0,
                )

                return filtered_results

            except Exception as e:
                logger.error(f"Vector search failed: {e}")
                span.set_attribute("error", str(e))
                return []
