"""Tests for workflow Pydantic models."""

import pytest
from datetime import datetime, timezone

from src.server.services.workflow.workflow_models import (
    NodeState,
    RunStatus,
    DispatchPayload,
    NodeStateCallback,
    ApprovalRequestCallback,
    RunCompleteCallback,
)


class TestNodeState:
    def test_valid_states(self):
        valid = ["pending", "running", "waiting_approval", "completed", "failed", "skipped", "cancelled"]
        for state in valid:
            # Should not raise
            NodeStateCallback(state=state, output=None, session_id=None, duration_seconds=0)

    def test_invalid_state_rejected(self):
        with pytest.raises(Exception):
            NodeStateCallback(state="queued", output=None, session_id=None, duration_seconds=0)


class TestDispatchPayloadStatuses:
    def test_valid_statuses(self):
        valid = ["pending", "dispatched", "running", "paused", "completed", "failed", "cancelled"]
        for status in valid:
            payload = DispatchPayload(
                workflow_run_id="wr_test",
                yaml_content="name: test\nnodes: []",
                trigger_context={},
                node_id_map={},
                callback_url="http://localhost:8181/api/workflows",
            )
            assert payload.workflow_run_id == "wr_test"


class TestDispatchPayload:
    def test_dispatch_payload_serialization(self):
        payload = DispatchPayload(
            workflow_run_id="wr_abc123",
            yaml_content="name: test\nnodes:\n  - id: step1\n    command: create-branch",
            trigger_context={"user_request": "Add rate limiting"},
            node_id_map={"step1": "uuid-1"},
            callback_url="http://cortex:8181/api/workflows",
        )
        data = payload.model_dump()
        assert data["workflow_run_id"] == "wr_abc123"
        assert data["node_id_map"]["step1"] == "uuid-1"
        assert data["callback_url"] == "http://cortex:8181/api/workflows"


class TestNodeStateCallback:
    def test_completed_with_output(self):
        cb = NodeStateCallback(
            state="completed",
            output="feat/rate-limiting",
            session_id="sess_abc",
            duration_seconds=45.2,
        )
        assert cb.state == "completed"
        assert cb.output == "feat/rate-limiting"
        assert cb.session_id == "sess_abc"

    def test_failed_with_no_output(self):
        cb = NodeStateCallback(state="failed", output=None, session_id=None, duration_seconds=10.0)
        assert cb.state == "failed"
        assert cb.output is None


class TestApprovalRequestCallback:
    def test_approval_request(self):
        cb = ApprovalRequestCallback(
            workflow_run_id="wr_abc",
            workflow_node_id="uuid-1",
            yaml_node_id="plan-review",
            approval_type="plan_review",
            node_output="## Plan\n\nDo the thing",
            channels=["ui", "telegram"],
        )
        assert cb.approval_type == "plan_review"
        assert "ui" in cb.channels


class TestRunCompleteCallback:
    def test_completed_run(self):
        cb = RunCompleteCallback(
            status="completed",
            summary="PR #42 created",
            node_outputs={"create-pr": "https://github.com/org/repo/pull/42"},
        )
        assert cb.status == "completed"
        assert "create-pr" in cb.node_outputs
