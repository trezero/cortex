"""Pydantic models for the Workflows 2.0 Control Plane.

These models are shared across workflow services and API routes.
They define the data contracts for dispatch, callbacks, and state tracking.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# -- Enums as Literal types (matches database CHECK-less TEXT columns) --

NodeState = Literal[
    "pending",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "skipped",
    "cancelled",
]

RunStatus = Literal[
    "pending",
    "dispatched",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
]

BackendStatus = Literal["healthy", "unhealthy", "disconnected"]


# -- Dispatch payload (Cortex → remote-agent) --

class DispatchPayload(BaseModel):
    """Sent to the remote-agent to start a workflow execution."""
    workflow_run_id: str
    yaml_content: str
    trigger_context: dict[str, Any] = Field(default_factory=dict)
    node_id_map: dict[str, str] = Field(
        default_factory=dict,
        description="Maps YAML node IDs to Cortex DB UUIDs",
    )
    callback_url: str = Field(description="Base URL for state callbacks back to Cortex")


class ResumePayload(BaseModel):
    """Sent to the remote-agent to resume after HITL approval."""
    yaml_node_id: str
    decision: Literal["approved", "rejected"]
    comment: str | None = None


# -- Callback payloads (remote-agent → Cortex) --

class NodeStateCallback(BaseModel):
    """Received from the remote-agent when a node changes state."""
    state: NodeState
    output: str | None = None
    error: str | None = None
    session_id: str | None = None
    duration_seconds: float | None = None


class NodeProgressCallback(BaseModel):
    """Received from the remote-agent for execution progress updates."""
    message: str


class ApprovalRequestCallback(BaseModel):
    """Received from the remote-agent when a node hits an approval gate."""
    workflow_run_id: str
    workflow_node_id: str = Field(description="Cortex DB UUID for the workflow_nodes row")
    yaml_node_id: str = Field(description="Human-readable YAML node ID")
    approval_type: str
    node_output: str
    channels: list[str] = Field(default_factory=lambda: ["ui"])


class RunCompleteCallback(BaseModel):
    """Received from the remote-agent when the entire workflow finishes."""
    status: Literal["completed", "failed", "cancelled"]
    summary: str | None = None
    node_outputs: dict[str, str] = Field(
        default_factory=dict,
        description="Map of YAML node ID → final output for key nodes",
    )


# -- Database row models (for service return values) --

class WorkflowDefinitionRow(BaseModel):
    """Represents a row from the workflow_definitions table."""
    id: str
    name: str
    description: str | None = None
    project_id: str | None = None
    yaml_content: str
    parsed_definition: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    is_latest: bool = True
    tags: list[str] = Field(default_factory=list)
    origin: str = "user"
    created_at: str | None = None
    deleted_at: str | None = None


class WorkflowRunRow(BaseModel):
    """Represents a row from the workflow_runs table."""
    id: str
    definition_id: str
    project_id: str | None = None
    backend_id: str | None = None
    status: RunStatus = "pending"
    triggered_by: str | None = None
    trigger_context: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class WorkflowNodeRow(BaseModel):
    """Represents a row from the workflow_nodes table."""
    id: str
    workflow_run_id: str
    node_id: str  # YAML node ID
    state: NodeState = "pending"
    output: str | None = None
    error: str | None = None
    session_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ExecutionBackendRow(BaseModel):
    """Represents a row from the execution_backends table."""
    id: str
    name: str
    base_url: str
    project_id: str | None = None
    status: BackendStatus = "healthy"
    last_heartbeat_at: str | None = None
    registered_at: str | None = None
