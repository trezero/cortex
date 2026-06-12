"""Pydantic models for knowledge materialization."""

from datetime import datetime

from pydantic import BaseModel, Field


class MaterializationRequest(BaseModel):
    """Request to materialize knowledge for a topic into a project repository."""

    topic: str = Field(description="Topic to materialize")
    project_id: str = Field(description="Cortex project ID")
    project_path: str = Field(description="Filesystem path to project repo")
    agent_context: str | None = Field(default=None, description="Additional context from the requesting agent")


class MaterializationResult(BaseModel):
    """Result of a materialization operation."""

    success: bool
    file_path: str | None = None
    filename: str | None = None
    word_count: int = 0
    summary: str | None = None
    materialization_id: str | None = None
    reason: str | None = None


class MaterializationRecord(BaseModel):
    """Database record for a materialized knowledge document."""

    id: str
    project_id: str
    project_path: str
    topic: str
    filename: str
    file_path: str
    source_ids: list[str] = []
    original_urls: list[str] = []
    synthesis_model: str | None = None
    word_count: int = 0
    status: str = "active"
    access_count: int = 0
    last_accessed_at: datetime | None = None
    materialized_at: datetime
    updated_at: datetime
    metadata: dict = {}
