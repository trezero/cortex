"""Session memory tools for Cortex MCP Server.

Provides two MCP tools:
- cortex_search_sessions: Full-text search across session history
- cortex_get_session: Retrieve a specific session with all observations
"""

import json
import logging
from urllib.parse import urlencode, urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.mcp_server.utils.error_handling import MCPErrorFormatter
from src.mcp_server.utils.timeout_config import get_default_timeout
from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)


def register_session_tools(mcp: FastMCP):
    """Register session memory tools with the MCP server."""

    @mcp.tool()
    async def cortex_search_sessions(
        ctx: Context,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
    ) -> str:
        """Search session history across agents and machines.

        Performs full-text search across session observations to find
        past work, decisions, and context from previous sessions.

        Args:
            query: Search terms to find in session observations
            project_id: Limit search to a specific Cortex project
            limit: Maximum number of results to return (default: 10)

        Returns:
            JSON with matching sessions and their summaries
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            params: dict = {"q": query, "limit": limit}
            if project_id:
                params["project_id"] = project_id

            url = urljoin(api_url, f"/api/sessions?{urlencode(params)}")

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                sessions = data.get("sessions", [])
                return json.dumps({"success": True, "sessions": sessions, "count": len(sessions)})

            return json.dumps({"success": False, "error": f"API error {response.status_code}: {response.text}"})

        except Exception as e:
            logger.error("cortex_search_sessions failed", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})

    @mcp.tool()
    async def cortex_get_session(
        ctx: Context,
        session_id: str,
    ) -> str:
        """Get a specific session with all its observations.

        Retrieves the full session record including all observations
        recorded during that session.

        Args:
            session_id: The unique session identifier

        Returns:
            JSON with the session record and its observations
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            url = urljoin(api_url, f"/api/sessions/{session_id}")

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                return json.dumps({
                    "success": True,
                    "session": data.get("session"),
                    "observations": data.get("observations", []),
                })

            if response.status_code == 404:
                return json.dumps({"success": False, "error": f"Session '{session_id}' not found"})

            return json.dumps({"success": False, "error": f"API error {response.status_code}: {response.text}"})

        except Exception as e:
            logger.error("cortex_get_session failed", session_id=session_id, exc_info=True)
            return json.dumps({"success": False, "error": str(e)})
