"""Workflow dispatch service.

Creates workflow run and node records in Supabase, then POSTs
the YAML payload to the resolved remote-agent backend.
"""

from typing import Any

import httpx
import yaml

from src.server.utils import get_supabase_client

from ...config.logfire_config import get_logger

logger = get_logger(__name__)

# Timeout for the dispatch POST (remote-agent just queues the job, should be fast)
DISPATCH_TIMEOUT = 30.0


class DispatchService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def create_run(
        self,
        definition_id: str,
        project_id: str | None,
        backend_id: str,
        triggered_by: str | None = None,
        trigger_context: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Create a workflow_runs record."""
        try:
            data = {
                "definition_id": definition_id,
                "backend_id": backend_id,
                "status": "pending",
            }
            if project_id:
                data["project_id"] = project_id
            if triggered_by:
                data["triggered_by"] = triggered_by
            if trigger_context:
                data["trigger_context"] = trigger_context

            response = self.supabase_client.table("workflow_runs").insert(data).execute()
            if not response.data:
                return False, {"error": "Failed to create workflow run"}

            return True, {"run": response.data[0]}
        except Exception as e:
            logger.error(f"Error creating workflow run: {e}")
            return False, {"error": f"Failed to create run: {str(e)}"}

    def create_nodes_for_run(
        self,
        workflow_run_id: str,
        yaml_content: str,
    ) -> tuple[bool, dict[str, Any]]:
        """Parse YAML node IDs and create workflow_nodes records.

        Returns a node_id_map: {yaml_node_id: cortex_db_uuid}
        """
        try:
            parsed = yaml.safe_load(yaml_content)
            nodes = parsed.get("nodes", [])

            if not nodes:
                return False, {"error": "YAML contains no nodes"}

            node_records = [
                {"workflow_run_id": workflow_run_id, "node_id": node["id"], "state": "pending"}
                for node in nodes
            ]

            response = self.supabase_client.table("workflow_nodes").insert(node_records).execute()
            if not response.data:
                return False, {"error": "Failed to create node records"}

            node_id_map = {row["node_id"]: row["id"] for row in response.data}
            return True, {"node_id_map": node_id_map, "node_count": len(node_id_map)}
        except Exception as e:
            logger.error(f"Error creating nodes for run {workflow_run_id}: {e}")
            return False, {"error": f"Failed to create nodes: {str(e)}"}

    async def dispatch_to_backend(
        self,
        workflow_run_id: str,
        yaml_content: str,
        backend: dict[str, Any],
        node_id_map: dict[str, str],
        trigger_context: dict[str, Any],
        callback_url: str,
    ) -> tuple[bool, dict[str, Any]]:
        """POST the workflow payload to the remote-agent for execution."""
        url = f"{backend['base_url']}/api/cortex/workflows/execute"
        payload = {
            "workflow_run_id": workflow_run_id,
            "yaml_content": yaml_content,
            "trigger_context": trigger_context,
            "node_id_map": node_id_map,
            "callback_url": callback_url,
        }

        try:
            async with httpx.AsyncClient(timeout=DISPATCH_TIMEOUT) as client:
                response = await client.post(url, json=payload)

            if response.status_code >= 400:
                error_detail = response.text[:500]
                logger.error(f"Backend rejected dispatch: {response.status_code} — {error_detail}")
                self.supabase_client.table("workflow_runs").update(
                    {"status": "failed"}
                ).eq("id", workflow_run_id).execute()
                return False, {"error": f"Backend returned {response.status_code}: {error_detail}"}

            self.supabase_client.table("workflow_runs").update(
                {"status": "dispatched"}
            ).eq("id", workflow_run_id).execute()

            logger.info(f"Workflow {workflow_run_id} dispatched to {backend['name']} ({url})")
            return True, {"dispatched": True, "backend_id": backend["id"]}
        except httpx.TimeoutException:
            logger.error(f"Timeout dispatching to {url}")
            self.supabase_client.table("workflow_runs").update(
                {"status": "failed"}
            ).eq("id", workflow_run_id).execute()
            return False, {"error": f"Timeout connecting to backend at {backend['base_url']}"}
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to backend at {url}: {e}")
            self.supabase_client.table("workflow_runs").update(
                {"status": "failed"}
            ).eq("id", workflow_run_id).execute()
            return False, {"error": f"Cannot connect to backend at {backend['base_url']}: {str(e)}"}
        except Exception as e:
            logger.error(f"Error dispatching workflow: {e}", exc_info=True)
            return False, {"error": f"Dispatch failed: {str(e)}"}

    async def cancel_run(
        self,
        workflow_run_id: str,
        backend: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """Send a cancel signal to the remote-agent and update run status."""
        url = f"{backend['base_url']}/api/cortex/workflows/{workflow_run_id}/cancel"
        try:
            async with httpx.AsyncClient(timeout=DISPATCH_TIMEOUT) as client:
                response = await client.post(url)

            self.supabase_client.table("workflow_runs").update(
                {"status": "cancelled"}
            ).eq("id", workflow_run_id).execute()

            for state in ("pending", "running"):
                self.supabase_client.table("workflow_nodes").update(
                    {"state": "cancelled"}
                ).eq("workflow_run_id", workflow_run_id).eq("state", state).execute()

            logger.info(f"Workflow {workflow_run_id} cancelled")
            return True, {"cancelled": True}
        except Exception as e:
            logger.error(f"Error cancelling workflow {workflow_run_id}: {e}")
            self.supabase_client.table("workflow_runs").update(
                {"status": "cancelled"}
            ).eq("id", workflow_run_id).execute()
            return True, {"cancelled": True, "warning": f"Backend notification failed: {str(e)}"}
