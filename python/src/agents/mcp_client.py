"""
MCP Client for Agents

This lightweight client allows PydanticAI agents to call MCP tools via the
MCP Streamable HTTP protocol. Agents use this client to access all data
operations through the MCP protocol instead of direct database access or
service imports.
"""

import json
import logging
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


def _resolve_mcp_url() -> str:
    """Resolve the MCP server URL from service discovery or environment."""
    try:
        from ..server.config.service_discovery import get_mcp_url

        base = get_mcp_url()
    except ImportError:
        mcp_port = os.getenv("CORTEX_MCP_PORT", "8051")
        if os.getenv("DOCKER_CONTAINER") or os.path.exists("/.dockerenv"):
            base = f"http://cortex-mcp:{mcp_port}"
        else:
            base = f"http://localhost:{mcp_port}"

    # The MCP Streamable HTTP endpoint is at /mcp
    return f"{base}/mcp"


class MCPClient:
    """Client for calling MCP tools via the Streamable HTTP transport."""

    def __init__(self, mcp_url: str | None = None):
        self.mcp_url = mcp_url or _resolve_mcp_url()
        logger.info(f"MCP Client initialized with URL: {self.mcp_url}")

    async def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """
        Call an MCP tool via the Streamable HTTP transport.

        Opens a short-lived session per call. The overhead is minimal for
        chat-frequency interactions and avoids stale-session issues.
        """
        try:
            async with streamablehttp_client(url=self.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=kwargs)

            # Extract text content from the MCP CallToolResult
            if hasattr(result, "content") and result.content:
                texts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                combined = "\n".join(texts)
                # Try to parse as JSON; return dict if possible
                try:
                    return json.loads(combined)
                except (json.JSONDecodeError, TypeError):
                    return {"result": combined}
            return {}

        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name}: {e}")
            raise Exception(f"Failed to call MCP tool: {e}")

    # Convenience methods for common MCP tools

    async def perform_rag_query(self, query: str, source: str = None, match_count: int = 5) -> str:
        """Perform a RAG query through MCP."""
        result = await self.call_tool(
            "perform_rag_query", query=query, source=source, match_count=match_count
        )
        return json.dumps(result) if isinstance(result, dict) else str(result)

    async def get_available_sources(self) -> str:
        """Get available sources through MCP."""
        result = await self.call_tool("get_available_sources")
        return json.dumps(result) if isinstance(result, dict) else str(result)

    async def search_code_examples(
        self, query: str, source_id: str = None, match_count: int = 5
    ) -> str:
        """Search code examples through MCP."""
        result = await self.call_tool(
            "search_code_examples", query=query, source_id=source_id, match_count=match_count
        )
        return json.dumps(result) if isinstance(result, dict) else str(result)

    async def manage_project(self, action: str, **kwargs) -> str:
        """Manage projects through MCP."""
        result = await self.call_tool("manage_project", action=action, **kwargs)
        return json.dumps(result) if isinstance(result, dict) else str(result)

    async def manage_document(self, action: str, project_id: str, **kwargs) -> str:
        """Manage documents through MCP."""
        result = await self.call_tool(
            "manage_document", action=action, project_id=project_id, **kwargs
        )
        return json.dumps(result) if isinstance(result, dict) else str(result)

    async def manage_task(self, action: str, project_id: str, **kwargs) -> str:
        """Manage tasks through MCP."""
        result = await self.call_tool("manage_task", action=action, project_id=project_id, **kwargs)
        return json.dumps(result) if isinstance(result, dict) else str(result)


# Global MCP client instance (created on first use)
_mcp_client: MCPClient | None = None


async def get_mcp_client() -> MCPClient:
    """
    Get or create the global MCP client instance.

    Returns:
        MCPClient instance
    """
    global _mcp_client

    if _mcp_client is None:
        _mcp_client = MCPClient()

    return _mcp_client
