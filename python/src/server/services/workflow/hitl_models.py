"""HITL models and channel protocol."""

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ApprovalContext(BaseModel):
    """Context passed to channels when dispatching an approval."""

    approval_id: str
    workflow_run_id: str
    workflow_node_id: str
    yaml_node_id: str
    approval_type: str
    node_output: str
    a2ui_payload: list[dict[str, Any]] | None = None
    channels: list[str] = Field(default_factory=lambda: ["ui"])
    project_name: str | None = None
    cortex_url: str | None = None


class ApprovalChannel(Protocol):
    """Protocol for HITL approval channels. Channels implement send-side only."""

    async def send_approval_request(self, context: ApprovalContext) -> None: ...

    async def notify_resolution(
        self, context: ApprovalContext, decision: str, resolved_by: str
    ) -> None: ...
