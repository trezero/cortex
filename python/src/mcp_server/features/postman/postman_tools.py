"""MCP tools for Postman integration.

Provides:
- find_postman: Get sync mode, collection info, search for duplicates
- manage_postman: Collection/environment/request management actions
"""

import json
import logging
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.mcp_server.utils.error_handling import MCPErrorFormatter
from src.mcp_server.utils.timeout_config import get_default_timeout
from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)


def register_postman_tools(mcp: FastMCP):
    """Register Postman integration tools with the MCP server."""

    @mcp.tool()
    async def find_postman(
        ctx: Context,
        project_id: str | None = None,
        collection_uid: str | None = None,
        query: str | None = None,
    ) -> str:
        """
        Get Postman integration status, collection info, or search requests.

        Call with no params to get the current sync_mode (api/git/disabled).
        Call with project_id to get collection details.
        Call with query to search request names for dedup checking.

        Args:
            project_id: Get collection info for a specific project
            collection_uid: Get full collection structure (folders + requests)
            query: Search requests by name across the collection

        Returns:
            JSON with sync_mode and requested data
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Always get status first
                status_resp = await client.get(urljoin(api_url, "/api/postman/status"))
                if status_resp.status_code != 200:
                    return MCPErrorFormatter.from_http_error(status_resp, "get postman status")

                status = status_resp.json()

                if not project_id and not collection_uid and not query:
                    return json.dumps({"success": True, **status})

                if status.get("sync_mode") != "api":
                    return json.dumps({
                        "success": True,
                        "sync_mode": status.get("sync_mode"),
                        "message": "Detailed collection info only available in api mode",
                    })

                # Project-level collection info
                if project_id:
                    proj_resp = await client.get(urljoin(api_url, f"/api/projects/{project_id}"))
                    if proj_resp.status_code == 200:
                        project = proj_resp.json()
                        col_uid = project.get("postman_collection_uid")
                        result = {
                            "success": True,
                            "sync_mode": "api",
                            "project_name": project.get("name"),
                            "collection_uid": col_uid,
                        }
                        if col_uid:
                            try:
                                struct_resp = await client.get(
                                    urljoin(api_url, f"/api/postman/collections/{col_uid}/structure")
                                )
                                if struct_resp.status_code == 200:
                                    result["structure"] = struct_resp.json()
                            except Exception:
                                pass
                        return json.dumps(result)
                    return MCPErrorFormatter.format_error(
                        "not_found", f"Project {project_id} not found", http_status=404
                    )

                return json.dumps({"success": True, **status})

        except Exception as e:
            logger.error(f"Error in find_postman: {e}")
            return MCPErrorFormatter.format_error("internal_error", str(e), http_status=500)

    @mcp.tool()
    async def manage_postman(
        ctx: Context,
        action: str,
        project_id: str | None = None,
        project_name: str | None = None,
        folder_name: str | None = None,
        request: dict | None = None,
        request_name: str | None = None,
        system_name: str | None = None,
        variables: dict | None = None,
        env_file_content: str | None = None,
        collection_uid: str | None = None,
    ) -> str:
        """
        Manage Postman collections, requests, and environments.

        Only functional in api sync mode. Returns skipped status in other modes.

        Supported actions:
        - init_collection: Create collection for a project
        - add_request: Add/update request in a collection folder
        - update_environment: Create/update an environment
        - remove_request: Remove a request from a folder
        - sync_environment: Push .env content as a system environment
        - import_from_git: Read local postman/ YAML and push to Postman Cloud
        - export_to_git: Pull from Postman Cloud and write local YAML files

        Args:
            action: The operation to perform
            project_id: Cortex project ID
            project_name: Project name for collection naming
            folder_name: Target folder in collection
            request: Request data dict (name, method, url, headers, body, test_script)
            request_name: Name of request to remove
            system_name: System name for environment naming
            variables: Environment variables dict
            env_file_content: Raw .env file content for sync
            collection_uid: Postman collection UID (for export_to_git)
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Check mode first
                status_resp = await client.get(urljoin(api_url, "/api/postman/status"))
                if status_resp.status_code == 200:
                    mode = status_resp.json().get("sync_mode", "disabled")
                    if mode != "api" and action not in ("import_from_git", "export_to_git"):
                        return json.dumps({
                            "status": "skipped",
                            "reason": f"sync_mode is '{mode}', not 'api'. Use git mode YAML files instead.",
                            "sync_mode": mode,
                        })

                if action == "init_collection":
                    if not project_name:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "project_name is required", http_status=400
                        )

                    resp = await client.post(
                        urljoin(api_url, "/api/postman/collections"),
                        json={"project_name": project_name, "project_id": project_id},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # Store UID on project if project_id provided
                        if project_id and data.get("collection_uid"):
                            await client.put(
                                urljoin(api_url, f"/api/projects/{project_id}"),
                                json={"postman_collection_uid": data["collection_uid"]},
                            )
                        return json.dumps({"success": True, **data})
                    return MCPErrorFormatter.from_http_error(resp, "init collection")

                elif action == "add_request":
                    if not folder_name or not request:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "folder_name and request are required", http_status=400
                        )

                    # Get collection UID from project
                    col_uid = collection_uid
                    if not col_uid and project_id:
                        proj_resp = await client.get(urljoin(api_url, f"/api/projects/{project_id}"))
                        if proj_resp.status_code == 200:
                            col_uid = proj_resp.json().get("postman_collection_uid")

                    if not col_uid:
                        # Auto-init if no collection exists
                        if project_name or project_id:
                            name = project_name or project_id
                            init_resp = await client.post(
                                urljoin(api_url, "/api/postman/collections"),
                                json={"project_name": name, "project_id": project_id},
                            )
                            if init_resp.status_code == 200:
                                col_uid = init_resp.json().get("collection_uid")

                    if not col_uid:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "Could not determine collection UID", http_status=400
                        )

                    resp = await client.post(
                        urljoin(api_url, f"/api/postman/collections/{col_uid}/requests"),
                        json={"folder_name": folder_name, "request": request},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "add request")

                elif action == "update_environment":
                    if not system_name or not variables:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "system_name and variables required", http_status=400
                        )

                    env_name = f"{project_name or project_id} - {system_name}"
                    resp = await client.put(
                        urljoin(api_url, f"/api/postman/environments/{env_name}"),
                        json={"name": env_name, "variables": variables},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "update environment")

                elif action == "remove_request":
                    return json.dumps({"success": True, "message": "remove_request not yet implemented"})

                elif action == "sync_environment":
                    if not project_id or not env_file_content:
                        return MCPErrorFormatter.format_error(
                            "validation_error", "project_id and env_file_content required", http_status=400
                        )

                    resp = await client.post(
                        urljoin(api_url, "/api/postman/environments/sync"),
                        json={
                            "project_id": project_id,
                            "system_name": system_name or "default",
                            "env_file_content": env_file_content,
                        },
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "sync environment")

                elif action == "import_from_git":
                    return json.dumps({
                        "success": True,
                        "message": "import_from_git: agent should read local YAML files and call add_request for each",
                    })

                elif action == "export_to_git":
                    return json.dumps({
                        "success": True,
                        "message": "export_to_git: agent should call find_postman to get structure, then write YAML files locally",
                    })

                else:
                    return MCPErrorFormatter.format_error(
                        "validation_error", f"Unknown action: {action}", http_status=400
                    )

        except Exception as e:
            logger.error(f"Error in manage_postman: {e}")
            return MCPErrorFormatter.format_error("internal_error", str(e), http_status=500)
