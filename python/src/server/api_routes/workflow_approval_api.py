"""Approval management endpoints.

Handles listing, retrieving, and resolving approval requests.
Resolution sends a resume signal to the remote-agent backend
and notifies channels via the HITLRouter.
"""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config.logfire_config import get_logger
from ..utils import get_supabase_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflow-approvals"])


class ResolveApprovalRequest(BaseModel):
    decision: str = Field(..., description="'approved' or 'rejected'")
    comment: str | None = Field(None, description="Optional comment")
    resolved_by: str | None = Field(None, description="Who resolved")


@router.get("/approvals")
async def list_approvals(status: str | None = "pending"):
    try:
        client = get_supabase_client()
        query = client.table("approval_requests").select("*")
        if status:
            query = query.eq("status", status)
        response = query.order("created_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Error listing approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str):
    try:
        client = get_supabase_client()
        response = client.table("approval_requests").select("*").eq("id", approval_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail={"error": "Approval not found"})
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, request: ResolveApprovalRequest):
    """Resolve an approval: updates DB, transitions node state,
    sends resume signal to the remote-agent backend, and notifies
    channels via HITLRouter."""
    try:
        client = get_supabase_client()
        from datetime import UTC, datetime

        response = client.table("approval_requests").update({
            "status": request.decision,
            "resolved_by": request.resolved_by or "user",
            "resolved_via": "ui",
            "resolved_comment": request.comment,
            "resolved_at": datetime.now(UTC).isoformat(),
        }).eq("id", approval_id).eq("status", "pending").execute()

        if not response.data:
            raise HTTPException(status_code=404, detail={"error": "Approval not found or already resolved"})

        approval = response.data[0]

        # Update the workflow node state based on decision
        from .workflow_backend_api import get_hitl_router, get_state_service
        state_service = get_state_service()
        node_state = "completed" if request.decision == "approved" else "failed"
        await state_service.process_node_state(
            node_id=approval["workflow_node_id"],
            state=node_state,
            output=f"Approval {request.decision}" + (f": {request.comment}" if request.comment else ""),
        )

        # Send resume signal to the remote-agent backend
        run_id = approval["workflow_run_id"]
        run_response = client.table("workflow_runs").select("backend_id").eq("id", run_id).execute()
        if run_response.data:
            backend_id = run_response.data[0]["backend_id"]
            backend_response = (
                client.table("execution_backends").select("base_url").eq("id", backend_id).execute()
            )
            if backend_response.data:
                base_url = backend_response.data[0]["base_url"]
                try:
                    async with httpx.AsyncClient(timeout=10.0) as http_client:
                        await http_client.post(
                            f"{base_url}/api/cortex/workflows/{run_id}/resume",
                            json={"approval_id": approval_id, "decision": request.decision},
                        )
                except httpx.HTTPError as http_err:
                    logger.error(f"Failed to send resume signal to {base_url}: {http_err}", exc_info=True)

        # Notify channels of the resolution via HITLRouter
        hitl_router = get_hitl_router()
        await hitl_router.handle_resolution(
            approval_id=approval_id,
            decision=request.decision,
            resolved_by=request.resolved_by or "user",
        )

        return {"resolved": True, "decision": request.decision}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})
