"""MCP tools for knowledge materialization."""

import json
import logging
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)


def register_materialization_tools(mcp: FastMCP):
    """Register all materialization tools with the MCP server."""

    @mcp.tool()
    async def materialize_knowledge(ctx: Context, topic: str, project_id: str, project_path: str) -> str:
        """Materialize knowledge from the Vector DB into a local project repo.
        Searches the RAG knowledge base, synthesizes results into Markdown,
        and writes to .cortex/knowledge/ directory.

        Args:
            topic: The knowledge topic to materialize
            project_id: The Cortex project ID
            project_path: Filesystem path to the project repo
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(120.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    urljoin(api_url, "/api/materialization/execute"),
                    json={"topic": topic, "project_id": project_id, "project_path": project_path},
                )
                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                else:
                    return json.dumps(
                        {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}, indent=2
                    )
        except Exception as e:
            logger.error(f"Error materializing knowledge: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    async def find_materializations(
        ctx: Context,
        project_id: str | None = None,
        status: str | None = None,
        materialization_id: str | None = None,
    ) -> str:
        """Find materialization history records.

        Args:
            project_id: Filter by project ID
            status: Filter by status (active, stale, archived)
            materialization_id: Get a specific record by ID
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                if materialization_id:
                    response = await client.get(urljoin(api_url, f"/api/materialization/{materialization_id}"))
                else:
                    params = {}
                    if project_id:
                        params["project_id"] = project_id
                    if status:
                        params["status"] = status
                    response = await client.get(urljoin(api_url, "/api/materialization/history"), params=params)

                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                else:
                    return json.dumps(
                        {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}, indent=2
                    )
        except Exception as e:
            logger.error(f"Error finding materializations: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    async def manage_materialization(ctx: Context, action: str, materialization_id: str) -> str:
        """Manage materialization records.

        Args:
            action: One of "mark_accessed", "mark_stale", "archive", "delete"
            materialization_id: The materialization record ID
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "mark_accessed":
                    response = await client.put(
                        urljoin(api_url, f"/api/materialization/{materialization_id}/access")
                    )
                elif action in ("mark_stale", "archive"):
                    status = "stale" if action == "mark_stale" else "archived"
                    response = await client.put(
                        urljoin(api_url, f"/api/materialization/{materialization_id}/status"),
                        params={"status": status},
                    )
                elif action == "delete":
                    response = await client.delete(
                        urljoin(api_url, f"/api/materialization/{materialization_id}")
                    )
                else:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Invalid action: {action}. Use mark_accessed, mark_stale, archive, or delete.",
                        },
                        indent=2,
                    )

                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                else:
                    return json.dumps(
                        {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}, indent=2
                    )
        except Exception as e:
            logger.error(f"Error managing materialization: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    logger.info("Materialization tools registered (HTTP-based)")
