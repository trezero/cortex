"""Session memory API endpoints for Cortex.

Handles:
- Session creation (batch: session row + observations)
- Session listing with optional project/machine filters
- Full-text search across session observations
- Single session retrieval with all observations
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config.logfire_config import get_logger
from ..services.sessions import SessionService

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])


# ── Request models ────────────────────────────────────────────────────────────


class ObservationRequest(BaseModel):
    type: str = "general"
    title: str
    content: str | None = None
    files: list[str] = []
    timestamp: str | None = None


class CreateSessionRequest(BaseModel):
    session_id: str
    machine_id: str
    project_id: str | None = None
    started_at: str
    ended_at: str | None = None
    summary: str | None = None
    observations: list[ObservationRequest] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    """Create a session with its observations in a single batch."""
    service = SessionService()
    observations = [obs.model_dump() for obs in req.observations] if req.observations else None

    success, result = service.create_session(
        session_id=req.session_id,
        machine_id=req.machine_id,
        project_id=req.project_id,
        started_at=req.started_at,
        ended_at=req.ended_at,
        summary=req.summary,
        observations=observations,
    )

    if not success:
        raise HTTPException(status_code=422, detail=result.get("error", "Failed to create session"))

    return result


@router.get("/sessions")
async def list_or_search_sessions(
    project_id: str | None = Query(default=None),
    machine_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """List or search sessions.

    When `q` is provided, performs full-text search across observations.
    Otherwise lists sessions ordered by recency with optional filters.
    """
    service = SessionService()

    if q:
        success, result = service.search_sessions(query=q, project_id=project_id, limit=limit)
        if not success:
            raise HTTPException(status_code=500, detail=result.get("error", "Search failed"))
        return result

    success, result = service.list_sessions(project_id=project_id, machine_id=machine_id, limit=limit)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to list sessions"))
    return result


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """Get a single session with all its observations."""
    service = SessionService()
    success, result = service.get_session(session_id)

    if not success:
        error = result.get("error", "")
        status = 404 if "not found" in error.lower() else 500
        raise HTTPException(status_code=status, detail=error)

    return result
