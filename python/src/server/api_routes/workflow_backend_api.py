"""Backend registration, heartbeat, and callback endpoints.

Handles remote-agent registration and processes execution state
callbacks from registered backends.
"""

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field

from ..config.logfire_config import get_logger
from ..services.workflow.backend_service import BackendService
from ..services.workflow.hitl_router import HITLRouter
from ..services.workflow.state_service import StateService
from ..services.workflow.workflow_models import (
    ApprovalRequestCallback,
    NodeProgressCallback,
    NodeStateCallback,
    RunCompleteCallback,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflow-backends"])

# Singleton state service for SSE fan-out (shared across requests)
_state_service: StateService | None = None

# Singleton HITL router for approval dispatch (shared across requests)
_hitl_router: HITLRouter | None = None


def get_state_service() -> StateService:
    global _state_service
    if _state_service is None:
        _state_service = StateService()
    return _state_service


def get_hitl_router() -> HITLRouter:
    global _hitl_router
    if _hitl_router is None:
        _hitl_router = HITLRouter(get_state_service())
    return _hitl_router


# -- Auth dependency for callback endpoints --

async def verify_backend_token(authorization: str | None = Header(None)) -> str:
    """Verify Bearer token and return backend_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ")
    service = BackendService()
    success, result = service.verify_token(token)
    if not success:
        raise HTTPException(status_code=401, detail="Invalid backend token")
    return result["backend_id"]


# -- Registration & health --

class RegisterBackendRequest(BaseModel):
    name: str = Field(..., description="Unique backend name")
    base_url: str = Field(..., description="Remote-agent base URL")
    project_id: str | None = Field(None, description="Scope to a specific project")


@router.post("/backends/register", status_code=http_status.HTTP_201_CREATED)
async def register_backend(request: RegisterBackendRequest):
    try:
        service = BackendService()
        success, result = service.register_backend(
            name=request.name,
            base_url=request.base_url,
            project_id=request.project_id,
        )
        if not success:
            raise HTTPException(status_code=400, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering backend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/backends/{backend_id}/heartbeat")
async def heartbeat(backend_id: str, _backend_id: str = Depends(verify_backend_token)):
    try:
        service = BackendService()
        success, result = service.record_heartbeat(backend_id)
        if not success:
            raise HTTPException(status_code=404, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Heartbeat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/backends")
async def list_backends():
    try:
        service = BackendService()
        success, result = service.list_backends()
        if not success:
            raise HTTPException(status_code=500, detail=result)
        return result["backends"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing backends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete("/backends/{backend_id}")
async def deregister_backend(backend_id: str):
    try:
        service = BackendService()
        success, result = service.deregister_backend(backend_id)
        if not success:
            raise HTTPException(status_code=404, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deregistering backend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


# -- Callback endpoints (remote-agent -> Cortex) --

@router.post("/nodes/{node_id}/state")
async def node_state_callback(
    node_id: str,
    callback: NodeStateCallback,
    _backend_id: str = Depends(verify_backend_token),
):
    state_service = get_state_service()
    success, result = await state_service.process_node_state(
        node_id=node_id,
        state=callback.state,
        output=callback.output,
        error=callback.error,
        session_id=callback.session_id,
        duration_seconds=callback.duration_seconds,
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)
    return {"accepted": True}


@router.post("/nodes/{node_id}/progress")
async def node_progress_callback(
    node_id: str,
    callback: NodeProgressCallback,
    _backend_id: str = Depends(verify_backend_token),
):
    state_service = get_state_service()
    success, result = await state_service.process_node_progress(node_id, callback.message)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    return {"accepted": True}


@router.post("/approvals/request")
async def approval_request_callback(
    callback: ApprovalRequestCallback,
    _backend_id: str = Depends(verify_backend_token),
):
    """Received when the remote-agent hits a node with approval.required: true.
    Updates node state to waiting_approval, then delegates to HITLRouter
    for record creation, A2UI payload generation, and channel dispatch."""
    state_service = get_state_service()

    # Update node state to waiting_approval
    success, result = await state_service.process_node_state(
        node_id=callback.workflow_node_id,
        state="waiting_approval",
        output=callback.node_output,
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)

    # Delegate to HITLRouter for approval record creation and channel dispatch
    hitl_router = get_hitl_router()
    success, result = await hitl_router.handle_approval_request(
        workflow_run_id=callback.workflow_run_id,
        workflow_node_id=callback.workflow_node_id,
        yaml_node_id=callback.yaml_node_id,
        approval_type=callback.approval_type,
        node_output=callback.node_output,
        channels=callback.channels,
    )
    if not success:
        logger.error(f"HITLRouter failed to handle approval request: {result}")

    return {"accepted": True}


@router.post("/runs/{run_id}/complete")
async def run_complete_callback(
    run_id: str,
    callback: RunCompleteCallback,
    _backend_id: str = Depends(verify_backend_token),
):
    state_service = get_state_service()
    success, result = await state_service.process_run_complete(
        run_id=run_id,
        status=callback.status,
        summary=callback.summary,
        node_outputs=callback.node_outputs,
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)
    return {"accepted": True}
