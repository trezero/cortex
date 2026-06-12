"""Auto-research API endpoints for Cortex.

Handles:
- Listing available eval suites
- Starting, monitoring, and cancelling optimization jobs
- Applying winning payloads back to target files
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config.logfire_config import get_logger
from ..services.auto_research import EvalSuiteLoader
from ..services.auto_research_service import AutoResearchService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auto-research", tags=["auto-research"])


# ── Request models ────────────────────────────────────────────────────────────


class StartOptimizationRequest(BaseModel):
    eval_suite_id: str
    max_iterations: int
    model: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/suites")
async def list_suites() -> dict[str, Any]:
    """List all available eval suites."""
    loader = EvalSuiteLoader()
    suites = loader.list_suites()
    return {"success": True, "suites": [s.model_dump() for s in suites]}


@router.post("/start")
async def start_optimization(req: StartOptimizationRequest) -> dict[str, Any]:
    """Start an optimization job for the given eval suite."""
    service = AutoResearchService()
    try:
        job_id, progress_id = await service.start_optimization(
            eval_suite_id=req.eval_suite_id,
            max_iterations=req.max_iterations,
            model=req.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"success": True, "job_id": job_id, "progress_id": progress_id}


@router.get("/jobs")
async def list_jobs() -> dict[str, Any]:
    """List all optimization jobs ordered by creation date (newest first)."""
    service = AutoResearchService()
    jobs = await service.list_jobs()
    return {"success": True, "jobs": [j.model_dump() for j in jobs]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Get a job with its full iteration history."""
    service = AutoResearchService()
    try:
        job = await service.get_job(job_id)
    except Exception:
        # Supabase raises when .single() finds no rows
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found") from None
    return {"success": True, "job": job.model_dump()}


@router.post("/jobs/{job_id}/apply")
async def apply_job_result(job_id: str) -> dict[str, Any]:
    """Apply the winning payload from a completed job back to the target file."""
    service = AutoResearchService()
    try:
        file_path = await service.apply_result(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "file_path": file_path}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel a running optimization job."""
    service = AutoResearchService()
    await service.cancel_job(job_id)
    return {"success": True}
