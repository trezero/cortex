"""MCP tool for LeaveOff Point management."""

import json
import logging
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)


def register_leaveoff_tools(mcp: FastMCP):
    """Register LeaveOff Point tools with the MCP server."""

    @mcp.tool()
    async def manage_leaveoff_point(
        ctx: Context,
        action: str,
        project_id: str,
        content: str | None = None,
        next_steps: list[str] | None = None,
        component: str | None = None,
        references: list[str] | None = None,
        machine_id: str | None = None,
        system_name: str | None = None,
        git_clean: bool | None = None,
        last_session_id: str | None = None,
        metadata: dict | None = None,
        project_path: str | None = None,
    ) -> str:
        """Manage the LeaveOff Point for a project. A LeaveOff Point captures where work
        was left off so the next session can resume seamlessly.

        IMPORTANT: This tool should be called during session termination (when the user
        says goodbye, ends the conversation, or wraps up work). Follow the 90% rule:
        once approximately 90% of the session context window has been consumed, proactively
        write a LeaveOff Point before the context is lost.

        Each project has exactly one LeaveOff Point that is overwritten on each update.

        Args:
            action: One of "update", "get", or "delete".
                - "update": Create or overwrite the LeaveOff Point. Requires content and next_steps.
                - "get": Retrieve the current LeaveOff Point for the project.
                - "delete": Remove the LeaveOff Point for the project.
            project_id: The Cortex project ID.
            content: (update only) Summary of current work state and what was accomplished.
            next_steps: (update only) Ordered list of actionable next steps for the next session.
            component: (update only) The component or area of the codebase being worked on.
            references: (update only) List of relevant file paths, URLs, or identifiers.
            machine_id: (update only) Identifier for the machine where work was performed.
            system_name: (update only) Human-readable name of the machine (e.g. "MacBookPro_M1").
            git_clean: (update only) Whether all changes are committed. False means uncommitted changes exist.
            last_session_id: (update only) The session ID from the ending session.
            metadata: (update only) Additional key-value data for context.
            project_path: (update only) Filesystem path to the project repository.
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)
            url = urljoin(api_url, f"/api/projects/{project_id}/leaveoff")

            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "update":
                    if not content or not next_steps:
                        return json.dumps(
                            {
                                "success": False,
                                "error": "Both 'content' and 'next_steps' are required for the 'update' action.",
                            },
                            indent=2,
                        )
                    body: dict = {
                        "content": content,
                        "next_steps": next_steps,
                    }
                    if component is not None:
                        body["component"] = component
                    if references is not None:
                        body["references"] = references
                    if machine_id is not None:
                        body["machine_id"] = machine_id
                    if system_name is not None:
                        body["system_name"] = system_name
                    if git_clean is not None:
                        body["git_clean"] = git_clean
                    if last_session_id is not None:
                        body["last_session_id"] = last_session_id
                    if metadata is not None:
                        body["metadata"] = metadata
                    if project_path is not None:
                        body["project_path"] = project_path

                    response = await client.put(url, json=body)

                elif action == "get":
                    response = await client.get(url)

                elif action == "delete":
                    response = await client.delete(url)

                else:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Invalid action: {action}. Use 'update', 'get', or 'delete'.",
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
            logger.error(f"Error managing leaveoff point: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    logger.info("LeaveOff Point tools registered (HTTP-based)")
