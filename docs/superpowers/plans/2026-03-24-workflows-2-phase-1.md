# Workflows 2.0 Phase 1: Control Plane Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cortex can dispatch a YAML workflow definition to a remote-coding-agent instance, track execution state via REST callbacks, and stream live updates to the UI via SSE.

**Architecture:** Cortex acts as a Control Plane — it stores workflow definitions, dispatches them to registered remote-agent backends, mirrors node execution state from REST callbacks, and pushes live updates to UI clients via SSE. No DAG evaluation, condition parsing, or node scheduling happens in Cortex. The remote-agent's existing TypeScript DAG executor handles all execution.

**Tech Stack:** Python 3.12, FastAPI, Supabase (PostgreSQL), httpx (async HTTP), sse-starlette, pyyaml, React 18, TanStack Query v5, EventSource API

**Spec:** `docs/superpowers/specs/2026-03-24-workflows-2-orchestration-engine-design.md`

---

## File Structure

### Files to Create

```
migration/0.1.0/
├── 027_workflow_definitions.sql
├── 028_workflow_commands.sql
├── 029_workflow_runs.sql
├── 030_workflow_nodes.sql
├── 031_approval_requests.sql
└── 032_execution_backends.sql

python/src/server/services/workflow/
├── __init__.py
├── workflow_models.py          # Pydantic models shared across services + routes
├── backend_service.py          # Backend registration, heartbeat, routing
├── definition_service.py       # Workflow definition CRUD, YAML validation, versioning
├── dispatch_service.py         # Create runs, create nodes, POST to remote-agent
└── state_service.py            # Process callbacks, update DB, SSE event fan-out

python/src/server/api_routes/
├── workflow_api.py             # Run management + SSE stream endpoint
├── workflow_backend_api.py     # Registration, heartbeat, callback endpoints
├── workflow_approval_api.py    # Approval CRUD + resolve (stub for Phase 2)
└── workflow_definition_api.py  # Definition CRUD + export

python/tests/server/services/workflow/
├── __init__.py
├── test_workflow_models.py
├── test_backend_service.py
├── test_definition_service.py
├── test_dispatch_service.py
└── test_state_service.py

cortex-ui/src/features/workflows/
├── types/index.ts
├── services/workflowService.ts
├── hooks/useWorkflowQueries.ts
└── components/
    ├── WorkflowRunView.tsx
    └── WorkflowRunCard.tsx
```

### Files to Modify

```
python/pyproject.toml                    # Add sse-starlette to server group
python/src/server/main.py               # Register 4 new routers
```

---

## Conventions Reference

These patterns are derived from the existing codebase. Follow them exactly.

**Service classes:**
```python
from src.server.utils import get_supabase_client
from ...config.logfire_config import get_logger

logger = get_logger(__name__)

class MyService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def my_method(self, ...) -> tuple[bool, dict[str, Any]]:
        try:
            # ... supabase operations ...
            return True, {"key": value}
        except Exception as e:
            logger.error(f"Error doing X: {e}")
            return False, {"error": f"...: {str(e)}"}
```

**API routes:**
```python
from fastapi import APIRouter, Header, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from ..config.logfire_config import get_logger
from ..utils import get_supabase_client
from ..utils.etag_utils import check_etag, generate_etag

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["my-feature"])

class CreateRequest(BaseModel):
    field: str = Field(..., description="...")

@router.post("/resource", status_code=http_status.HTTP_201_CREATED)
async def create_resource(request: CreateRequest):
    try:
        service = MyService()
        success, result = service.create(request.field)
        if not success:
            raise HTTPException(status_code=400, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating resource: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})
```

**Migration SQL:**
```sql
-- Migration NNN: Description
-- Creates table_name table

CREATE TABLE IF NOT EXISTS table_name (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_table_name_field
  ON table_name (field)
  WHERE deleted_at IS NULL;
```

**Frontend service:**
```typescript
import { callAPIWithETag } from "../../shared/api/apiClient";

export const myService = {
  async list(): Promise<Item[]> {
    return callAPIWithETag<Item[]>("/api/resource");
  },
};
```

**Frontend query hooks:**
```typescript
import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { useSmartPolling } from "@/features/ui/hooks/useSmartPolling";

export const myKeys = {
  all: ["my-resource"] as const,
  lists: () => [...myKeys.all, "list"] as const,
  detail: (id: string) => [...myKeys.all, "detail", id] as const,
};
```

---

## Task 1: Database Migrations

**Files:**
- Create: `migration/0.1.0/027_workflow_definitions.sql`
- Create: `migration/0.1.0/028_workflow_commands.sql`
- Create: `migration/0.1.0/029_workflow_runs.sql`
- Create: `migration/0.1.0/030_workflow_nodes.sql`
- Create: `migration/0.1.0/031_approval_requests.sql`
- Create: `migration/0.1.0/032_execution_backends.sql`

- [ ] **Step 1: Write migration 027 — workflow_definitions**

```sql
-- Migration 027: Workflow definitions
-- Stores canonical YAML workflow definitions with versioning

CREATE TABLE IF NOT EXISTS workflow_definitions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  yaml_content TEXT NOT NULL,
  parsed_definition JSONB DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1,
  is_latest BOOLEAN NOT NULL DEFAULT true,
  tags TEXT[] DEFAULT '{}',
  origin TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_definitions_name_project_version
  ON workflow_definitions (name, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid), version)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_project
  ON workflow_definitions (project_id)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_latest
  ON workflow_definitions (is_latest)
  WHERE is_latest = true AND deleted_at IS NULL;
```

- [ ] **Step 2: Write migration 028 — workflow_commands**

```sql
-- Migration 028: Workflow commands
-- Stores prompt templates referenced by workflow nodes

CREATE TABLE IF NOT EXISTS workflow_commands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  prompt_template TEXT NOT NULL,
  variables JSONB DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1,
  is_latest BOOLEAN NOT NULL DEFAULT true,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_commands_name_project_version
  ON workflow_commands (name, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid), version)
  WHERE deleted_at IS NULL;
```

- [ ] **Step 3: Write migration 029 — workflow_runs**

```sql
-- Migration 029: Workflow runs
-- Tracks individual executions of workflow definitions

CREATE TABLE IF NOT EXISTS workflow_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  backend_id UUID,
  status TEXT NOT NULL DEFAULT 'pending',
  triggered_by TEXT,
  trigger_context JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
  ON workflow_runs (status);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_project_status
  ON workflow_runs (project_id, status)
  WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_definition
  ON workflow_runs (definition_id);
```

- [ ] **Step 4: Write migration 030 — workflow_nodes**

```sql
-- Migration 030: Workflow nodes
-- Mirrors node execution state reported by the remote-agent

CREATE TABLE IF NOT EXISTS workflow_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  output TEXT,
  error TEXT,
  session_id TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workflow_nodes_run_state
  ON workflow_nodes (workflow_run_id, state);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_nodes_run_node
  ON workflow_nodes (workflow_run_id, node_id);
```

- [ ] **Step 5: Write migration 031 — approval_requests**

```sql
-- Migration 031: Approval requests
-- HITL approval gates for workflow nodes (used in Phase 2, schema created now)

CREATE TABLE IF NOT EXISTS approval_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  workflow_node_id UUID NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
  yaml_node_id TEXT NOT NULL,
  approval_type TEXT NOT NULL,
  payload JSONB DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',
  channels_notified TEXT[] DEFAULT '{}',
  resolved_by TEXT,
  resolved_via TEXT,
  resolved_comment TEXT,
  telegram_message_id TEXT,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_status
  ON approval_requests (status);

CREATE INDEX IF NOT EXISTS idx_approval_requests_run
  ON approval_requests (workflow_run_id);
```

- [ ] **Step 6: Write migration 032 — execution_backends**

```sql
-- Migration 032: Execution backends
-- Routing table for remote-agent instances

CREATE TABLE IF NOT EXISTS execution_backends (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  base_url TEXT NOT NULL,
  auth_token_hash TEXT NOT NULL,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'healthy',
  last_heartbeat_at TIMESTAMPTZ,
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_execution_backends_project
  ON execution_backends (project_id);
```

- [ ] **Step 7: Run all 6 migrations against Supabase**

Open Supabase SQL editor and run migrations 027 through 032 in order.

Run: Verify tables exist:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN (
  'workflow_definitions', 'workflow_commands', 'workflow_runs',
  'workflow_nodes', 'approval_requests', 'execution_backends'
);
```
Expected: 6 rows returned.

- [ ] **Step 8: Commit**

```bash
git add migration/0.1.0/027_workflow_definitions.sql migration/0.1.0/028_workflow_commands.sql migration/0.1.0/029_workflow_runs.sql migration/0.1.0/030_workflow_nodes.sql migration/0.1.0/031_approval_requests.sql migration/0.1.0/032_execution_backends.sql
git commit -m "feat(workflows): add database migrations 027-032 for Workflows 2.0"
```

---

## Task 2: Pydantic Models

**Files:**
- Create: `python/src/server/services/workflow/__init__.py`
- Create: `python/src/server/services/workflow/workflow_models.py`
- Test: `python/tests/server/services/workflow/test_workflow_models.py`

- [ ] **Step 1: Create the workflow service package**

Create `python/src/server/services/workflow/__init__.py`:
```python
"""Workflow orchestration services for the Cortex Control Plane."""
```

Create `python/tests/server/services/workflow/__init__.py`:
```python
```

- [ ] **Step 2: Write the failing test for workflow models**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_workflow_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.server.services.workflow.workflow_models'`

- [ ] **Step 4: Implement workflow_models.py**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_workflow_models.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add python/src/server/services/workflow/__init__.py python/src/server/services/workflow/workflow_models.py python/tests/server/services/workflow/__init__.py python/tests/server/services/workflow/test_workflow_models.py
git commit -m "feat(workflows): add Pydantic models for Workflows 2.0 Control Plane"
```

---

## Task 3: Backend Service

**Files:**
- Create: `python/src/server/services/workflow/backend_service.py`
- Test: `python/tests/server/services/workflow/test_backend_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for BackendService."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from src.server.services.workflow.backend_service import BackendService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return BackendService(supabase_client=mock_supabase)


class TestRegisterBackend:
    def test_register_returns_token(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "be_abc", "name": "test-agent", "base_url": "http://agent:3000"}
        ]
        success, result = service.register_backend(
            name="test-agent",
            base_url="http://agent:3000",
            project_id=None,
        )
        assert success is True
        assert "backend_id" in result
        assert "auth_token" in result
        assert len(result["auth_token"]) > 20

    def test_register_stores_hashed_token(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "be_abc", "name": "test-agent", "base_url": "http://agent:3000"}
        ]
        service.register_backend(name="test-agent", base_url="http://agent:3000")
        insert_call = mock_supabase.table.return_value.insert.call_args[0][0]
        assert "auth_token_hash" in insert_call
        assert insert_call["auth_token_hash"] != insert_call.get("auth_token", "")


class TestVerifyToken:
    def test_valid_token(self, service, mock_supabase):
        token = "test_token_123"
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "be_abc", "auth_token_hash": token_hash, "status": "healthy"}
        ]
        success, result = service.verify_token(token)
        assert success is True
        assert result["backend_id"] == "be_abc"

    def test_invalid_token(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        success, result = service.verify_token("bad_token")
        assert success is False


class TestHeartbeat:
    def test_record_heartbeat(self, service, mock_supabase):
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"id": "be_abc", "status": "healthy"}
        ]
        success, result = service.record_heartbeat("be_abc")
        assert success is True


class TestResolveBackend:
    def test_resolve_by_project(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "be_abc", "base_url": "http://agent:3000", "status": "healthy"}
        ]
        success, result = service.resolve_backend_for_project("proj_xyz")
        assert success is True
        assert result["backend"]["id"] == "be_abc"

    def test_resolve_default_when_no_project_match(self, service, mock_supabase):
        # First call: no project-specific backend
        # Second call: default backend (project_id IS NULL)
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.select.return_value.is_.return_value.eq.return_value.execute.return_value.data = [
            {"id": "be_default", "base_url": "http://default:3000", "status": "healthy"}
        ]
        success, result = service.resolve_backend_for_project("proj_xyz")
        assert success is True
        assert result["backend"]["id"] == "be_default"

    def test_no_backends_returns_error(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.select.return_value.is_.return_value.eq.return_value.execute.return_value.data = []
        success, result = service.resolve_backend_for_project("proj_xyz")
        assert success is False
        assert "error" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_backend_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement backend_service.py**

```python
"""Backend registration, heartbeat, and routing service.

Manages the execution_backends table — a routing table that maps
remote-agent instances to projects for workflow dispatch.
"""

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from src.server.utils import get_supabase_client

from ...config.logfire_config import get_logger

logger = get_logger(__name__)


class BackendService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def register_backend(
        self,
        name: str,
        base_url: str,
        project_id: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Register a remote-agent instance. Returns a one-time auth token."""
        try:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()

            data = {
                "name": name,
                "base_url": base_url.rstrip("/"),
                "auth_token_hash": token_hash,
                "status": "healthy",
                "last_heartbeat_at": datetime.now(UTC).isoformat(),
                "registered_at": datetime.now(UTC).isoformat(),
            }
            if project_id:
                data["project_id"] = project_id

            response = self.supabase_client.table("execution_backends").insert(data).execute()

            if not response.data:
                return False, {"error": "Failed to register backend — database returned no data"}

            backend = response.data[0]
            logger.info(f"Backend registered: {name} ({backend['id']})")

            return True, {
                "backend_id": backend["id"],
                "auth_token": token,
            }
        except Exception as e:
            logger.error(f"Error registering backend: {e}")
            return False, {"error": f"Failed to register backend: {str(e)}"}

    def verify_token(self, token: str) -> tuple[bool, dict[str, Any]]:
        """Verify a Bearer token against registered backends."""
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            response = (
                self.supabase_client.table("execution_backends")
                .select("id, name, status, auth_token_hash")
                .eq("auth_token_hash", token_hash)
                .execute()
            )

            if not response.data:
                return False, {"error": "Invalid or unknown backend token"}

            backend = response.data[0]
            return True, {"backend_id": backend["id"], "backend_name": backend["name"]}
        except Exception as e:
            logger.error(f"Error verifying backend token: {e}")
            return False, {"error": f"Token verification failed: {str(e)}"}

    def record_heartbeat(self, backend_id: str) -> tuple[bool, dict[str, Any]]:
        """Update heartbeat timestamp and set status to healthy."""
        try:
            response = (
                self.supabase_client.table("execution_backends")
                .update({
                    "last_heartbeat_at": datetime.now(UTC).isoformat(),
                    "status": "healthy",
                })
                .eq("id", backend_id)
                .execute()
            )

            if not response.data:
                return False, {"error": f"Backend {backend_id} not found"}

            return True, {"backend_id": backend_id, "status": "healthy"}
        except Exception as e:
            logger.error(f"Error recording heartbeat for {backend_id}: {e}")
            return False, {"error": f"Heartbeat failed: {str(e)}"}

    def resolve_backend_for_project(self, project_id: str | None = None) -> tuple[bool, dict[str, Any]]:
        """Find the best backend for a given project.

        Resolution order:
        1. Backend registered for this specific project_id
        2. Default backend (project_id IS NULL)
        3. Error if no backends available
        """
        try:
            # Try project-specific backend first
            if project_id:
                response = (
                    self.supabase_client.table("execution_backends")
                    .select("*")
                    .eq("project_id", project_id)
                    .eq("status", "healthy")
                    .execute()
                )
                if response.data:
                    return True, {"backend": response.data[0]}

            # Fall back to default backend (no project_id)
            response = (
                self.supabase_client.table("execution_backends")
                .select("*")
                .is_("project_id", "null")
                .eq("status", "healthy")
                .execute()
            )
            if response.data:
                return True, {"backend": response.data[0]}

            return False, {"error": "No healthy execution backends available. Register a remote-agent first."}
        except Exception as e:
            logger.error(f"Error resolving backend for project {project_id}: {e}")
            return False, {"error": f"Backend resolution failed: {str(e)}"}

    def list_backends(self) -> tuple[bool, dict[str, Any]]:
        """List all registered backends."""
        try:
            response = self.supabase_client.table("execution_backends").select("*").execute()
            return True, {"backends": response.data or []}
        except Exception as e:
            logger.error(f"Error listing backends: {e}")
            return False, {"error": f"Failed to list backends: {str(e)}"}

    def deregister_backend(self, backend_id: str) -> tuple[bool, dict[str, Any]]:
        """Remove a backend from the routing table."""
        try:
            response = (
                self.supabase_client.table("execution_backends")
                .delete()
                .eq("id", backend_id)
                .execute()
            )
            if not response.data:
                return False, {"error": f"Backend {backend_id} not found"}

            logger.info(f"Backend deregistered: {backend_id}")
            return True, {"deleted": backend_id}
        except Exception as e:
            logger.error(f"Error deregistering backend {backend_id}: {e}")
            return False, {"error": f"Failed to deregister: {str(e)}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_backend_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/workflow/backend_service.py python/tests/server/services/workflow/test_backend_service.py
git commit -m "feat(workflows): add BackendService for remote-agent registration and routing"
```

---

## Task 4: Definition Service

**Files:**
- Create: `python/src/server/services/workflow/definition_service.py`
- Test: `python/tests/server/services/workflow/test_definition_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for DefinitionService."""

from unittest.mock import MagicMock

import pytest

from src.server.services.workflow.definition_service import DefinitionService


SAMPLE_YAML = """name: test-workflow
description: A test workflow
provider: claude
model: sonnet

nodes:
  - id: step-one
    command: create-branch
    context: fresh

  - id: step-two
    command: planning
    depends_on: [step-one]
"""


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return DefinitionService(supabase_client=mock_supabase)


class TestCreateDefinition:
    def test_create_stores_yaml_and_parsed(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "def_1", "name": "test-workflow", "version": 1}
        ]
        success, result = service.create_definition(
            name="test-workflow",
            yaml_content=SAMPLE_YAML,
            description="A test workflow",
        )
        assert success is True
        insert_data = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_data["name"] == "test-workflow"
        assert insert_data["yaml_content"] == SAMPLE_YAML
        assert "nodes" in insert_data["parsed_definition"]

    def test_create_rejects_invalid_yaml(self, service):
        success, result = service.create_definition(
            name="bad",
            yaml_content="not: valid: yaml: {{{{",
        )
        assert success is False
        assert "error" in result


class TestValidateYaml:
    def test_valid_yaml_with_nodes(self, service):
        success, result = service.validate_yaml(SAMPLE_YAML)
        assert success is True
        assert len(result["node_ids"]) == 2
        assert "step-one" in result["node_ids"]

    def test_missing_nodes_key(self, service):
        success, result = service.validate_yaml("name: test\ndescription: no nodes")
        assert success is False
        assert "nodes" in result["error"].lower()

    def test_duplicate_node_ids(self, service):
        yaml = "name: test\nnodes:\n  - id: dupe\n    command: a\n  - id: dupe\n    command: b"
        success, result = service.validate_yaml(yaml)
        assert success is False
        assert "duplicate" in result["error"].lower()

    def test_missing_node_id(self, service):
        yaml = "name: test\nnodes:\n  - command: a"
        success, result = service.validate_yaml(yaml)
        assert success is False


class TestListDefinitions:
    def test_list_returns_latest(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.execute.return_value.data = [
            {"id": "def_1", "name": "wf-1", "version": 1},
        ]
        success, result = service.list_definitions()
        assert success is True
        assert len(result["definitions"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_definition_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement definition_service.py**

```python
"""Workflow definition CRUD, YAML validation, and versioning.

Stores canonical YAML definitions in Supabase. Validates structure
(node IDs, depends_on references) but does NOT interpret execution
semantics — that is the remote-agent's responsibility.
"""

from typing import Any

import yaml

from src.server.utils import get_supabase_client

from ...config.logfire_config import get_logger

logger = get_logger(__name__)


class DefinitionService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def validate_yaml(self, yaml_content: str) -> tuple[bool, dict[str, Any]]:
        """Validate YAML structure. Returns node_ids on success."""
        try:
            parsed = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return False, {"error": f"Invalid YAML syntax: {str(e)}"}

        if not isinstance(parsed, dict):
            return False, {"error": "YAML must be a mapping at the top level"}

        nodes = parsed.get("nodes")
        if not nodes or not isinstance(nodes, list):
            return False, {"error": "YAML must contain a 'nodes' list with at least one node"}

        node_ids = []
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                return False, {"error": f"Node at index {i} must be a mapping"}
            node_id = node.get("id")
            if not node_id:
                return False, {"error": f"Node at index {i} is missing required 'id' field"}
            node_ids.append(node_id)

        if len(node_ids) != len(set(node_ids)):
            dupes = [nid for nid in node_ids if node_ids.count(nid) > 1]
            return False, {"error": f"Duplicate node IDs: {list(set(dupes))}"}

        # Validate depends_on references
        node_id_set = set(node_ids)
        for node in nodes:
            deps = node.get("depends_on", [])
            for dep in deps:
                if dep not in node_id_set:
                    return False, {"error": f"Node '{node['id']}' depends on unknown node '{dep}'"}

        return True, {"parsed": parsed, "node_ids": node_ids}

    def create_definition(
        self,
        name: str,
        yaml_content: str,
        description: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        origin: str = "user",
    ) -> tuple[bool, dict[str, Any]]:
        """Create a new workflow definition. Validates YAML before storing."""
        valid, validation_result = self.validate_yaml(yaml_content)
        if not valid:
            return False, validation_result

        try:
            data = {
                "name": name,
                "yaml_content": yaml_content,
                "parsed_definition": validation_result["parsed"],
                "version": 1,
                "is_latest": True,
                "origin": origin,
            }
            if description:
                data["description"] = description
            if project_id:
                data["project_id"] = project_id
            if tags:
                data["tags"] = tags

            response = self.supabase_client.table("workflow_definitions").insert(data).execute()

            if not response.data:
                return False, {"error": "Failed to create definition — database returned no data"}

            definition = response.data[0]
            logger.info(f"Workflow definition created: {name} ({definition['id']})")
            return True, {"definition": definition}
        except Exception as e:
            logger.error(f"Error creating definition: {e}")
            return False, {"error": f"Failed to create definition: {str(e)}"}

    def get_definition(self, definition_id: str) -> tuple[bool, dict[str, Any]]:
        """Get a single workflow definition by ID."""
        try:
            response = (
                self.supabase_client.table("workflow_definitions")
                .select("*")
                .eq("id", definition_id)
                .is_("deleted_at", "null")
                .execute()
            )
            if not response.data:
                return False, {"error": f"Definition {definition_id} not found"}
            return True, {"definition": response.data[0]}
        except Exception as e:
            logger.error(f"Error getting definition {definition_id}: {e}")
            return False, {"error": f"Failed to get definition: {str(e)}"}

    def list_definitions(self, project_id: str | None = None) -> tuple[bool, dict[str, Any]]:
        """List latest versions of all definitions."""
        try:
            query = (
                self.supabase_client.table("workflow_definitions")
                .select("*")
                .eq("is_latest", True)
                .is_("deleted_at", "null")
            )
            if project_id:
                query = query.eq("project_id", project_id)
            response = query.order("created_at", desc=True).execute()
            return True, {"definitions": response.data or []}
        except Exception as e:
            logger.error(f"Error listing definitions: {e}")
            return False, {"error": f"Failed to list definitions: {str(e)}"}

    def update_definition(
        self,
        definition_id: str,
        yaml_content: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Update a definition by creating a new version."""
        try:
            # Get current version
            success, result = self.get_definition(definition_id)
            if not success:
                return success, result

            current = result["definition"]

            # Use new YAML or keep current
            new_yaml = yaml_content or current["yaml_content"]
            if yaml_content:
                valid, validation_result = self.validate_yaml(yaml_content)
                if not valid:
                    return False, validation_result

            # Mark old version as not latest
            self.supabase_client.table("workflow_definitions").update(
                {"is_latest": False}
            ).eq("name", current["name"]).eq("is_latest", True).execute()

            # Create new version
            new_data = {
                "name": current["name"],
                "description": description or current.get("description"),
                "project_id": current.get("project_id"),
                "yaml_content": new_yaml,
                "parsed_definition": yaml.safe_load(new_yaml) if yaml_content else current.get("parsed_definition", {}),
                "version": current["version"] + 1,
                "is_latest": True,
                "tags": tags or current.get("tags", []),
                "origin": current.get("origin", "user"),
            }

            response = self.supabase_client.table("workflow_definitions").insert(new_data).execute()
            if not response.data:
                return False, {"error": "Failed to create new version"}

            logger.info(f"Definition updated: {current['name']} v{new_data['version']}")
            return True, {"definition": response.data[0]}
        except Exception as e:
            logger.error(f"Error updating definition {definition_id}: {e}")
            return False, {"error": f"Failed to update definition: {str(e)}"}

    def delete_definition(self, definition_id: str) -> tuple[bool, dict[str, Any]]:
        """Soft-delete a definition."""
        try:
            from datetime import UTC, datetime

            response = (
                self.supabase_client.table("workflow_definitions")
                .update({"deleted_at": datetime.now(UTC).isoformat(), "is_latest": False})
                .eq("id", definition_id)
                .execute()
            )
            if not response.data:
                return False, {"error": f"Definition {definition_id} not found"}
            return True, {"deleted": definition_id}
        except Exception as e:
            logger.error(f"Error deleting definition {definition_id}: {e}")
            return False, {"error": f"Failed to delete definition: {str(e)}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_definition_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/workflow/definition_service.py python/tests/server/services/workflow/test_definition_service.py
git commit -m "feat(workflows): add DefinitionService for YAML workflow CRUD and validation"
```

---

## Task 5: State Service (SSE Fan-Out)

**Files:**
- Create: `python/src/server/services/workflow/state_service.py`
- Test: `python/tests/server/services/workflow/test_state_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for StateService."""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.server.services.workflow.state_service import StateService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return StateService(supabase_client=mock_supabase)


class TestProcessNodeState:
    @pytest.mark.asyncio
    async def test_update_node_to_running(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "n1", "workflow_run_id": "wr1", "node_id": "step-one", "state": "pending"}
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"id": "n1", "state": "running"}
        ]
        success, result = await service.process_node_state(
            node_id="n1", state="running", output=None, session_id=None, duration_seconds=None,
        )
        assert success is True

    @pytest.mark.asyncio
    async def test_completed_node_stores_output(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "n1", "workflow_run_id": "wr1", "node_id": "step-one", "state": "running"}
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"id": "n1", "state": "completed", "output": "feat/branch"}
        ]
        success, result = await service.process_node_state(
            node_id="n1", state="completed", output="feat/branch", session_id="sess_1", duration_seconds=12.5,
        )
        assert success is True
        update_data = mock_supabase.table.return_value.update.call_args[0][0]
        assert update_data["output"] == "feat/branch"
        assert update_data["session_id"] == "sess_1"


class TestSSESubscription:
    def test_subscribe_creates_queue(self, service):
        queue = service.subscribe_to_run("wr1")
        assert isinstance(queue, asyncio.Queue)

    def test_unsubscribe_removes_queue(self, service):
        queue = service.subscribe_to_run("wr1")
        service.unsubscribe_from_run("wr1", queue)
        assert "wr1" not in service._sse_queues or queue not in service._sse_queues.get("wr1", [])

    @pytest.mark.asyncio
    async def test_fire_event_reaches_subscriber(self, service):
        queue = service.subscribe_to_run("wr1")
        await service.fire_sse_event("wr1", "node_state_changed", {"node_id": "n1", "state": "running"})
        event = queue.get_nowait()
        assert event["type"] == "node_state_changed"
        assert event["data"]["node_id"] == "n1"

    @pytest.mark.asyncio
    async def test_fire_event_no_subscribers_is_safe(self, service):
        # Should not raise
        await service.fire_sse_event("nonexistent", "test", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_state_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement state_service.py**

```python
"""State tracking service for workflow execution.

Processes REST callbacks from the remote-agent, updates Supabase,
and fans out SSE events to subscribed UI clients.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from src.server.utils import get_supabase_client

from ...config.logfire_config import get_logger

logger = get_logger(__name__)


class StateService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()
        self._sse_queues: dict[str, list[asyncio.Queue]] = {}

    # -- SSE subscription management --

    def subscribe_to_run(self, run_id: str) -> asyncio.Queue:
        """Create a queue for SSE events for a specific workflow run."""
        queue: asyncio.Queue = asyncio.Queue()
        if run_id not in self._sse_queues:
            self._sse_queues[run_id] = []
        self._sse_queues[run_id].append(queue)
        logger.info(f"SSE subscriber added for run {run_id} (total: {len(self._sse_queues[run_id])})")
        return queue

    def unsubscribe_from_run(self, run_id: str, queue: asyncio.Queue) -> None:
        """Remove a queue when the SSE client disconnects."""
        if run_id in self._sse_queues:
            try:
                self._sse_queues[run_id].remove(queue)
            except ValueError:
                pass
            if not self._sse_queues[run_id]:
                del self._sse_queues[run_id]
            logger.info(f"SSE subscriber removed for run {run_id}")

    async def fire_sse_event(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        """Push an event to all subscribers for a given run."""
        queues = self._sse_queues.get(run_id, [])
        event = {"type": event_type, "data": data}
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"SSE queue full for run {run_id}, dropping event")

    # -- Callback processing --

    async def process_node_state(
        self,
        node_id: str,
        state: str,
        output: str | None,
        error: str | None = None,
        session_id: str | None = None,
        duration_seconds: float | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Process a node state callback from the remote-agent."""
        try:
            # Get current node to find run_id and previous state
            node_response = (
                self.supabase_client.table("workflow_nodes")
                .select("id, workflow_run_id, node_id, state")
                .eq("id", node_id)
                .execute()
            )
            if not node_response.data:
                return False, {"error": f"Node {node_id} not found"}

            node = node_response.data[0]
            previous_state = node["state"]
            run_id = node["workflow_run_id"]

            # Build update payload
            update_data: dict[str, Any] = {"state": state}
            if output is not None:
                update_data["output"] = output
            if error is not None:
                update_data["error"] = error
            if session_id is not None:
                update_data["session_id"] = session_id
            if state == "running" and not node.get("started_at"):
                update_data["started_at"] = datetime.now(UTC).isoformat()
            if state in ("completed", "failed", "skipped", "cancelled"):
                update_data["completed_at"] = datetime.now(UTC).isoformat()

            # Update node
            self.supabase_client.table("workflow_nodes").update(update_data).eq("id", node_id).execute()

            # Update run status based on node states
            await self._update_run_status(run_id)

            # Fire SSE event
            await self.fire_sse_event(run_id, "node_state_changed", {
                "node_id": node_id,
                "yaml_node_id": node["node_id"],
                "previous_state": previous_state,
                "new_state": state,
                "output": output,
            })

            return True, {"node_id": node_id, "state": state}
        except Exception as e:
            logger.error(f"Error processing node state for {node_id}: {e}", exc_info=True)
            return False, {"error": f"Failed to process node state: {str(e)}"}

    async def process_node_progress(self, node_id: str, message: str) -> tuple[bool, dict[str, Any]]:
        """Process a progress update from the remote-agent."""
        try:
            node_response = (
                self.supabase_client.table("workflow_nodes")
                .select("id, workflow_run_id, node_id")
                .eq("id", node_id)
                .execute()
            )
            if not node_response.data:
                return False, {"error": f"Node {node_id} not found"}

            node = node_response.data[0]
            await self.fire_sse_event(node["workflow_run_id"], "node_progress", {
                "node_id": node_id,
                "yaml_node_id": node["node_id"],
                "message": message,
            })
            return True, {"accepted": True}
        except Exception as e:
            logger.error(f"Error processing progress for {node_id}: {e}")
            return False, {"error": str(e)}

    async def process_run_complete(
        self,
        run_id: str,
        status: str,
        summary: str | None = None,
        node_outputs: dict[str, str] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Process a workflow completion callback."""
        try:
            update_data: dict[str, Any] = {
                "status": status,
                "completed_at": datetime.now(UTC).isoformat(),
            }
            if summary:
                update_data["trigger_context"] = (
                    self.supabase_client.table("workflow_runs")
                    .select("trigger_context")
                    .eq("id", run_id)
                    .execute()
                    .data[0].get("trigger_context", {})
                )
                update_data["trigger_context"]["summary"] = summary

            self.supabase_client.table("workflow_runs").update(update_data).eq("id", run_id).execute()

            await self.fire_sse_event(run_id, "run_status_changed", {
                "status": status,
                "summary": summary,
            })

            return True, {"run_id": run_id, "status": status}
        except Exception as e:
            logger.error(f"Error processing run completion for {run_id}: {e}", exc_info=True)
            return False, {"error": str(e)}

    async def _update_run_status(self, run_id: str) -> None:
        """Derive run status from the aggregate state of all nodes."""
        try:
            nodes_response = (
                self.supabase_client.table("workflow_nodes")
                .select("state")
                .eq("workflow_run_id", run_id)
                .execute()
            )
            if not nodes_response.data:
                return

            states = [n["state"] for n in nodes_response.data]

            # Determine run status from node states
            if any(s == "waiting_approval" for s in states):
                new_status = "paused"
            elif any(s == "running" for s in states):
                new_status = "running"
            elif all(s in ("completed", "skipped") for s in states):
                new_status = "completed"
            elif any(s == "failed" for s in states) and not any(s in ("running", "pending") for s in states):
                new_status = "failed"
            elif any(s == "cancelled" for s in states):
                new_status = "cancelled"
            else:
                return  # No status change needed

            # Get current status to check if changed
            run_response = (
                self.supabase_client.table("workflow_runs")
                .select("status")
                .eq("id", run_id)
                .execute()
            )
            if run_response.data and run_response.data[0]["status"] != new_status:
                previous = run_response.data[0]["status"]
                update_data: dict[str, Any] = {"status": new_status}
                if new_status == "running" and previous in ("pending", "dispatched"):
                    update_data["started_at"] = datetime.now(UTC).isoformat()
                if new_status in ("completed", "failed", "cancelled"):
                    update_data["completed_at"] = datetime.now(UTC).isoformat()

                self.supabase_client.table("workflow_runs").update(update_data).eq("id", run_id).execute()

                await self.fire_sse_event(run_id, "run_status_changed", {
                    "status": new_status,
                    "previous_status": previous,
                })
        except Exception as e:
            logger.error(f"Error updating run status for {run_id}: {e}", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_state_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/workflow/state_service.py python/tests/server/services/workflow/test_state_service.py
git commit -m "feat(workflows): add StateService for callback processing and SSE fan-out"
```

---

## Task 6: Dispatch Service

**Files:**
- Create: `python/src/server/services/workflow/dispatch_service.py`
- Test: `python/tests/server/services/workflow/test_dispatch_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for DispatchService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.workflow.dispatch_service import DispatchService


SAMPLE_YAML = """name: test-workflow
nodes:
  - id: step-one
    command: create-branch
  - id: step-two
    command: planning
    depends_on: [step-one]
"""


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return DispatchService(supabase_client=mock_supabase)


class TestCreateRun:
    def test_creates_run_record(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "wr_1", "status": "pending", "definition_id": "def_1"}
        ]
        success, result = service.create_run(
            definition_id="def_1",
            project_id="proj_1",
            backend_id="be_1",
            triggered_by="user",
            trigger_context={"user_request": "test"},
        )
        assert success is True
        assert result["run"]["id"] == "wr_1"


class TestCreateNodes:
    def test_creates_node_records_and_returns_map(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "n1", "node_id": "step-one"},
            {"id": "n2", "node_id": "step-two"},
        ]
        success, result = service.create_nodes_for_run("wr_1", SAMPLE_YAML)
        assert success is True
        assert "step-one" in result["node_id_map"]
        assert "step-two" in result["node_id_map"]
        assert len(result["node_id_map"]) == 2


class TestDispatchToBackend:
    @pytest.mark.asyncio
    async def test_posts_to_backend_url(self, service):
        backend = {"id": "be_1", "base_url": "http://agent:3000", "auth_token_hash": "x"}
        with patch("src.server.services.workflow.dispatch_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = MagicMock(status_code=200, json=lambda: {"accepted": True})
            mock_client_cls.return_value = mock_client

            success, result = await service.dispatch_to_backend(
                workflow_run_id="wr_1",
                yaml_content=SAMPLE_YAML,
                backend=backend,
                node_id_map={"step-one": "n1", "step-two": "n2"},
                trigger_context={"user_request": "test"},
                callback_url="http://cortex:8181/api/workflows",
            )
            assert success is True
            mock_client.post.assert_called_once()
            call_url = mock_client.post.call_args[0][0]
            assert "cortex/workflows/execute" in call_url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_dispatch_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement dispatch_service.py**

```python
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
                # Mark run as failed
                self.supabase_client.table("workflow_runs").update(
                    {"status": "failed"}
                ).eq("id", workflow_run_id).execute()
                return False, {"error": f"Backend returned {response.status_code}: {error_detail}"}

            # Mark run as dispatched
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

            # Mark run as cancelled regardless of backend response
            self.supabase_client.table("workflow_runs").update(
                {"status": "cancelled"}
            ).eq("id", workflow_run_id).execute()

            # Mark all pending/running nodes as cancelled
            for state in ("pending", "running"):
                self.supabase_client.table("workflow_nodes").update(
                    {"state": "cancelled"}
                ).eq("workflow_run_id", workflow_run_id).eq("state", state).execute()

            logger.info(f"Workflow {workflow_run_id} cancelled")
            return True, {"cancelled": True}
        except Exception as e:
            logger.error(f"Error cancelling workflow {workflow_run_id}: {e}")
            # Still mark as cancelled locally even if backend is unreachable
            self.supabase_client.table("workflow_runs").update(
                {"status": "cancelled"}
            ).eq("id", workflow_run_id).execute()
            return True, {"cancelled": True, "warning": f"Backend notification failed: {str(e)}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/test_dispatch_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/workflow/dispatch_service.py python/tests/server/services/workflow/test_dispatch_service.py
git commit -m "feat(workflows): add DispatchService for workflow dispatch to remote-agent"
```

---

## Task 7: API Routes + SSE Stream

**Files:**
- Modify: `python/pyproject.toml` (add sse-starlette to server group)
- Create: `python/src/server/api_routes/workflow_definition_api.py`
- Create: `python/src/server/api_routes/workflow_backend_api.py`
- Create: `python/src/server/api_routes/workflow_approval_api.py`
- Create: `python/src/server/api_routes/workflow_api.py`
- Modify: `python/src/server/main.py` (register routers)

- [ ] **Step 1: Add sse-starlette to server dependency group**

In `python/pyproject.toml`, add `"sse-starlette>=2.3.3"` to the `server` dependency group (after the `"logfire>=0.30.0"` line).

- [ ] **Step 2: Run `uv sync --group server` to install the dependency**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv sync --group server`
Expected: sse-starlette installed successfully

- [ ] **Step 3: Create workflow_definition_api.py**

```python
"""Workflow definition management endpoints.

CRUD operations for YAML workflow definitions stored in Supabase.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field

from ..config.logfire_config import get_logger
from ..services.workflow.definition_service import DefinitionService
from ..utils.etag_utils import check_etag, generate_etag

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflow-definitions"])


class CreateDefinitionRequest(BaseModel):
    name: str = Field(..., description="Workflow name")
    yaml_content: str = Field(..., description="YAML workflow definition")
    description: str | None = Field(None, description="Human-readable description")
    project_id: str | None = Field(None, description="Scope to a specific project")
    tags: list[str] | None = Field(None, description="Searchable tags")


class UpdateDefinitionRequest(BaseModel):
    yaml_content: str | None = Field(None, description="Updated YAML content")
    description: str | None = Field(None, description="Updated description")
    tags: list[str] | None = Field(None, description="Updated tags")


@router.get("/definitions")
async def list_definitions(
    project_id: str | None = None,
    if_none_match: str | None = Header(None),
):
    try:
        service = DefinitionService()
        success, result = service.list_definitions(project_id=project_id)
        if not success:
            raise HTTPException(status_code=500, detail=result)

        etag = generate_etag(result["definitions"])
        if check_etag(if_none_match, etag):
            from fastapi.responses import Response as RawResponse
            return RawResponse(status_code=304)

        from fastapi.responses import JSONResponse
        response = JSONResponse(content=result["definitions"])
        response.headers["ETag"] = etag
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing definitions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/definitions", status_code=http_status.HTTP_201_CREATED)
async def create_definition(request: CreateDefinitionRequest):
    try:
        service = DefinitionService()
        success, result = service.create_definition(
            name=request.name,
            yaml_content=request.yaml_content,
            description=request.description,
            project_id=request.project_id,
            tags=request.tags,
        )
        if not success:
            raise HTTPException(status_code=400, detail=result)
        return result["definition"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating definition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/definitions/{definition_id}")
async def get_definition(definition_id: str):
    try:
        service = DefinitionService()
        success, result = service.get_definition(definition_id)
        if not success:
            raise HTTPException(status_code=404, detail=result)
        return result["definition"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting definition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.put("/definitions/{definition_id}")
async def update_definition(definition_id: str, request: UpdateDefinitionRequest):
    try:
        service = DefinitionService()
        success, result = service.update_definition(
            definition_id=definition_id,
            yaml_content=request.yaml_content,
            description=request.description,
            tags=request.tags,
        )
        if not success:
            raise HTTPException(status_code=400, detail=result)
        return result["definition"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating definition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete("/definitions/{definition_id}")
async def delete_definition(definition_id: str):
    try:
        service = DefinitionService()
        success, result = service.delete_definition(definition_id)
        if not success:
            raise HTTPException(status_code=404, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting definition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/definitions/{definition_id}/export")
async def export_definition(definition_id: str):
    """Export a definition as a downloadable YAML file."""
    try:
        service = DefinitionService()
        success, result = service.get_definition(definition_id)
        if not success:
            raise HTTPException(status_code=404, detail=result)

        from fastapi.responses import Response
        definition = result["definition"]
        return Response(
            content=definition["yaml_content"],
            media_type="application/x-yaml",
            headers={"Content-Disposition": f'attachment; filename="{definition["name"]}.yaml"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting definition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})
```

- [ ] **Step 4: Create workflow_backend_api.py**

```python
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


def get_state_service() -> StateService:
    global _state_service
    if _state_service is None:
        _state_service = StateService()
    return _state_service


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


# -- Callback endpoints (remote-agent → Cortex) --

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
    Creates an approval_request record and fires SSE event.
    Full HITL handling (A2UI, Telegram) is Phase 2 scope — this is the stub."""
    state_service = get_state_service()

    # Update node state to waiting_approval
    success, result = await state_service.process_node_state(
        node_id=callback.workflow_node_id,
        state="waiting_approval",
        output=callback.node_output,
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)

    # Create approval_request record (stub for Phase 2 — stores raw output, no A2UI yet)
    try:
        from ..utils import get_supabase_client
        client = get_supabase_client()
        client.table("approval_requests").insert({
            "workflow_run_id": callback.workflow_run_id,
            "workflow_node_id": callback.workflow_node_id,
            "yaml_node_id": callback.yaml_node_id,
            "approval_type": callback.approval_type,
            "payload": {"raw_output": callback.node_output},
            "status": "pending",
            "channels_notified": callback.channels,
        }).execute()
    except Exception as e:
        logger.error(f"Error creating approval request: {e}", exc_info=True)

    # Fire SSE event
    await state_service.fire_sse_event(callback.workflow_run_id, "approval_requested", {
        "node_id": callback.workflow_node_id,
        "yaml_node_id": callback.yaml_node_id,
        "approval_type": callback.approval_type,
    })

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
```

- [ ] **Step 5: Create workflow_approval_api.py (Phase 2 stub)**

```python
"""Approval management endpoints.

Stub for Phase 1 — full HITL with A2UI rendering and Telegram
integration ships in Phase 2.
"""

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
    """Resolve an approval. Phase 1: updates DB only.
    Phase 2 will add: resume signal to remote-agent, Telegram message edit, A2UI."""
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
        from .workflow_backend_api import get_state_service
        state_service = get_state_service()
        node_state = "completed" if request.decision == "approved" else "failed"
        await state_service.process_node_state(
            node_id=approval["workflow_node_id"],
            state=node_state,
            output=f"Approval {request.decision}" + (f": {request.comment}" if request.comment else ""),
        )

        # Fire SSE event for approval resolution
        await state_service.fire_sse_event(approval["workflow_run_id"], "approval_resolved", {
            "approval_id": approval_id,
            "decision": request.decision,
            "resolved_by": request.resolved_by or "user",
            "resolved_via": "ui",
        })

        # TODO Phase 2: Send resume signal to remote-agent
        # TODO Phase 2: Edit Telegram message with resolution status

        return {"resolved": True, "decision": request.decision}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})
```

- [ ] **Step 6: Create workflow_api.py (run management + SSE)**

```python
"""Workflow run management and SSE event stream.

Creates and manages workflow runs. The SSE endpoint provides
live state updates to UI clients.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..config.logfire_config import get_logger
from ..services.workflow.backend_service import BackendService
from ..services.workflow.definition_service import DefinitionService
from ..services.workflow.dispatch_service import DispatchService
from ..utils import get_supabase_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# Import singleton state service from backend API (shared SSE queues)
from .workflow_backend_api import get_state_service


class CreateRunRequest(BaseModel):
    definition_id: str = Field(..., description="Workflow definition to execute")
    project_id: str | None = Field(None, description="Project context")
    backend_id: str | None = Field(None, description="Specific backend to use (auto-resolved if omitted)")
    trigger_context: dict | None = Field(None, description="Context passed to the remote-agent")


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_run(request: CreateRunRequest, req: Request):
    """Create and dispatch a workflow run."""
    try:
        # 1. Load definition
        def_service = DefinitionService()
        success, def_result = def_service.get_definition(request.definition_id)
        if not success:
            raise HTTPException(status_code=404, detail=def_result)
        definition = def_result["definition"]

        # 2. Resolve backend
        backend_service = BackendService()
        if request.backend_id:
            # Use specified backend
            client = get_supabase_client()
            be_response = client.table("execution_backends").select("*").eq("id", request.backend_id).execute()
            if not be_response.data:
                raise HTTPException(status_code=404, detail={"error": f"Backend {request.backend_id} not found"})
            backend = be_response.data[0]
        else:
            success, be_result = backend_service.resolve_backend_for_project(request.project_id)
            if not success:
                raise HTTPException(status_code=400, detail=be_result)
            backend = be_result["backend"]

        # 3. Create run record
        dispatch_service = DispatchService()
        success, run_result = dispatch_service.create_run(
            definition_id=request.definition_id,
            project_id=request.project_id,
            backend_id=backend["id"],
            triggered_by="ui",
            trigger_context=request.trigger_context or {},
        )
        if not success:
            raise HTTPException(status_code=500, detail=run_result)
        run = run_result["run"]

        # 4. Create node records
        success, node_result = dispatch_service.create_nodes_for_run(
            run["id"], definition["yaml_content"],
        )
        if not success:
            raise HTTPException(status_code=500, detail=node_result)

        # 5. Dispatch to backend
        callback_url = str(req.base_url).rstrip("/") + "/api/workflows"
        success, dispatch_result = await dispatch_service.dispatch_to_backend(
            workflow_run_id=run["id"],
            yaml_content=definition["yaml_content"],
            backend=backend,
            node_id_map=node_result["node_id_map"],
            trigger_context=request.trigger_context or {},
            callback_url=callback_url,
        )
        if not success:
            raise HTTPException(status_code=502, detail=dispatch_result)

        return {
            "run_id": run["id"],
            "status": "dispatched",
            "backend": backend["name"],
            "node_count": node_result["node_count"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workflow run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("")
async def list_runs(
    status: str | None = None,
    project_id: str | None = None,
):
    try:
        client = get_supabase_client()
        query = client.table("workflow_runs").select("*")
        if status:
            query = query.eq("status", status)
        if project_id:
            query = query.eq("project_id", project_id)
        response = query.order("created_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Error listing runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/{run_id}")
async def get_run(run_id: str):
    try:
        client = get_supabase_client()
        run_response = client.table("workflow_runs").select("*").eq("id", run_id).execute()
        if not run_response.data:
            raise HTTPException(status_code=404, detail={"error": "Run not found"})

        nodes_response = client.table("workflow_nodes").select("*").eq("workflow_run_id", run_id).execute()

        return {
            "run": run_response.data[0],
            "nodes": nodes_response.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str):
    try:
        client = get_supabase_client()
        run_response = client.table("workflow_runs").select("*, execution_backends(*)").eq("id", run_id).execute()
        if not run_response.data:
            raise HTTPException(status_code=404, detail={"error": "Run not found"})

        run = run_response.data[0]
        if run["status"] in ("completed", "failed", "cancelled"):
            raise HTTPException(status_code=400, detail={"error": f"Run is already {run['status']}"})

        # Get backend info for cancel signal
        backend_response = client.table("execution_backends").select("*").eq("id", run["backend_id"]).execute()
        backend = backend_response.data[0] if backend_response.data else {"base_url": "http://unknown", "name": "unknown"}

        dispatch_service = DispatchService()
        success, result = await dispatch_service.cancel_run(run_id, backend)
        if not success:
            raise HTTPException(status_code=500, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/{run_id}/events")
async def stream_run_events(run_id: str):
    """SSE stream for live workflow execution updates."""
    state_service = get_state_service()

    async def event_generator():
        queue = state_service.subscribe_to_run(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": event["type"],
                        "data": json.dumps(event["data"]),
                    }
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        except asyncio.CancelledError:
            pass
        finally:
            state_service.unsubscribe_from_run(run_id, queue)

    return EventSourceResponse(event_generator())
```

- [ ] **Step 7: Register all 4 routers in main.py**

Add these imports after the existing router imports (around line 39 in `python/src/server/main.py`):

```python
from .api_routes.workflow_api import router as workflow_router
from .api_routes.workflow_approval_api import router as workflow_approval_router
from .api_routes.workflow_backend_api import router as workflow_backend_router
from .api_routes.workflow_definition_api import router as workflow_definition_router
```

Add these lines after the existing `app.include_router(...)` calls (around line 252):

```python
app.include_router(workflow_router)
app.include_router(workflow_approval_router)
app.include_router(workflow_backend_router)
app.include_router(workflow_definition_router)
```

- [ ] **Step 8: Verify server starts**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run python -c "from src.server.api_routes.workflow_api import router; print('OK')"`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add python/pyproject.toml python/src/server/api_routes/workflow_api.py python/src/server/api_routes/workflow_approval_api.py python/src/server/api_routes/workflow_backend_api.py python/src/server/api_routes/workflow_definition_api.py python/src/server/main.py
git commit -m "feat(workflows): add API routes for workflow management, backends, approvals, and SSE"
```

---

## Task 8: Frontend Scaffolding

**Files:**
- Create: `cortex-ui/src/features/workflows/types/index.ts`
- Create: `cortex-ui/src/features/workflows/services/workflowService.ts`
- Create: `cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts`

- [ ] **Step 1: Create TypeScript types**

```typescript
// cortex-ui/src/features/workflows/types/index.ts

export type RunStatus = "pending" | "dispatched" | "running" | "paused" | "completed" | "failed" | "cancelled";
export type NodeState = "pending" | "running" | "waiting_approval" | "completed" | "failed" | "skipped" | "cancelled";

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  yaml_content: string;
  parsed_definition: Record<string, unknown>;
  version: number;
  is_latest: boolean;
  tags: string[];
  origin: string;
  created_at: string;
  deleted_at: string | null;
}

export interface WorkflowRun {
  id: string;
  definition_id: string;
  project_id: string | null;
  backend_id: string | null;
  status: RunStatus;
  triggered_by: string | null;
  trigger_context: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface WorkflowNode {
  id: string;
  workflow_run_id: string;
  node_id: string;
  state: NodeState;
  output: string | null;
  error: string | null;
  session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ExecutionBackend {
  id: string;
  name: string;
  base_url: string;
  project_id: string | null;
  status: "healthy" | "unhealthy" | "disconnected";
  last_heartbeat_at: string | null;
  registered_at: string;
}

export interface WorkflowRunDetail {
  run: WorkflowRun;
  nodes: WorkflowNode[];
}

export interface CreateRunRequest {
  definition_id: string;
  project_id?: string;
  backend_id?: string;
  trigger_context?: Record<string, unknown>;
}

export interface CreateDefinitionRequest {
  name: string;
  yaml_content: string;
  description?: string;
  project_id?: string;
  tags?: string[];
}

// SSE event types
export interface WorkflowSSEEvent {
  type: "node_state_changed" | "run_status_changed" | "approval_requested" | "approval_resolved" | "node_progress";
  data: Record<string, unknown>;
}
```

- [ ] **Step 2: Create workflow service**

```typescript
// cortex-ui/src/features/workflows/services/workflowService.ts

import { callAPIWithETag } from "../../shared/api/apiClient";
import type {
  CreateDefinitionRequest,
  CreateRunRequest,
  ExecutionBackend,
  WorkflowDefinition,
  WorkflowRun,
  WorkflowRunDetail,
} from "../types";

export const workflowService = {
  // -- Definitions --
  async listDefinitions(projectId?: string): Promise<WorkflowDefinition[]> {
    const params = projectId ? `?project_id=${projectId}` : "";
    return callAPIWithETag<WorkflowDefinition[]>(`/api/workflows/definitions${params}`);
  },

  async getDefinition(id: string): Promise<WorkflowDefinition> {
    return callAPIWithETag<WorkflowDefinition>(`/api/workflows/definitions/${id}`);
  },

  async createDefinition(data: CreateDefinitionRequest): Promise<WorkflowDefinition> {
    return callAPIWithETag<WorkflowDefinition>("/api/workflows/definitions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async deleteDefinition(id: string): Promise<void> {
    await callAPIWithETag(`/api/workflows/definitions/${id}`, { method: "DELETE" });
  },

  // -- Runs --
  async listRuns(status?: string, projectId?: string): Promise<WorkflowRun[]> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (projectId) params.set("project_id", projectId);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return callAPIWithETag<WorkflowRun[]>(`/api/workflows${qs}`);
  },

  async getRun(runId: string): Promise<WorkflowRunDetail> {
    return callAPIWithETag<WorkflowRunDetail>(`/api/workflows/${runId}`);
  },

  async createRun(data: CreateRunRequest): Promise<{ run_id: string; status: string }> {
    return callAPIWithETag<{ run_id: string; status: string }>("/api/workflows", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async cancelRun(runId: string): Promise<void> {
    await callAPIWithETag(`/api/workflows/${runId}/cancel`, { method: "POST" });
  },

  // -- Backends --
  async listBackends(): Promise<ExecutionBackend[]> {
    return callAPIWithETag<ExecutionBackend[]>("/api/workflows/backends");
  },
};
```

- [ ] **Step 3: Create query hooks**

```typescript
// cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { useSmartPolling } from "@/features/ui/hooks/useSmartPolling";

import { workflowService } from "../services/workflowService";
import type { CreateDefinitionRequest, CreateRunRequest } from "../types";

export const workflowKeys = {
  all: ["workflows"] as const,
  definitions: () => [...workflowKeys.all, "definitions"] as const,
  definitionDetail: (id: string) => [...workflowKeys.all, "definitions", id] as const,
  runs: () => [...workflowKeys.all, "runs"] as const,
  runDetail: (id: string) => [...workflowKeys.all, "runs", id] as const,
  backends: () => [...workflowKeys.all, "backends"] as const,
};

// -- Definition hooks --

export function useWorkflowDefinitions(projectId?: string) {
  return useQuery({
    queryKey: workflowKeys.definitions(),
    queryFn: () => workflowService.listDefinitions(projectId),
    staleTime: STALE_TIMES.normal,
  });
}

export function useWorkflowDefinition(id: string | undefined) {
  return useQuery({
    queryKey: id ? workflowKeys.definitionDetail(id) : DISABLED_QUERY_KEY,
    queryFn: () => (id ? workflowService.getDefinition(id) : Promise.reject("No ID")),
    enabled: !!id,
    staleTime: STALE_TIMES.normal,
  });
}

export function useCreateDefinition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDefinitionRequest) => workflowService.createDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.definitions() });
    },
  });
}

// -- Run hooks --

export function useWorkflowRuns(status?: string, projectId?: string) {
  const { refetchInterval } = useSmartPolling(5000);
  return useQuery({
    queryKey: workflowKeys.runs(),
    queryFn: () => workflowService.listRuns(status, projectId),
    refetchInterval,
    staleTime: STALE_TIMES.frequent,
  });
}

export function useWorkflowRun(runId: string | undefined) {
  const { refetchInterval } = useSmartPolling(3000);
  return useQuery({
    queryKey: runId ? workflowKeys.runDetail(runId) : DISABLED_QUERY_KEY,
    queryFn: () => (runId ? workflowService.getRun(runId) : Promise.reject("No ID")),
    enabled: !!runId,
    refetchInterval,
    staleTime: STALE_TIMES.realtime,
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRunRequest) => workflowService.createRun(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

export function useCancelRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => workflowService.cancelRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}

// -- Backend hooks --

export function useExecutionBackends() {
  return useQuery({
    queryKey: workflowKeys.backends(),
    queryFn: () => workflowService.listBackends(),
    staleTime: STALE_TIMES.normal,
  });
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/workflows" | head -20`
Expected: No errors (or only errors from files not yet created, not from these 3 files)

- [ ] **Step 5: Commit**

```bash
git add cortex-ui/src/features/workflows/types/index.ts cortex-ui/src/features/workflows/services/workflowService.ts cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts
git commit -m "feat(workflows): add frontend types, service, and TanStack Query hooks"
```

---

## Task 9: Run All Tests + Final Verification

- [ ] **Step 1: Run all workflow tests**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/workflow/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify backend starts with new routes**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && timeout 5 uv run python -m src.server.main 2>&1 || true`
Expected: Server starts without import errors (will fail on missing env vars — that's OK, we just need no import crashes)

- [ ] **Step 3: Verify frontend compiles**

Run: `cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/workflows" | head -20`
Expected: No TypeScript errors in workflows feature

- [ ] **Step 4: Final commit (if any loose changes)**

```bash
git status
# If clean, skip. Otherwise:
git add -A && git commit -m "chore(workflows): Phase 1 cleanup"
```

---

## Propagation Steps

After implementation, to see changes on a running system:

| What Changed | How to Propagate |
|---|---|
| Database migrations (027-032) | Run each `.sql` file in Supabase SQL editor |
| `python/pyproject.toml` | `docker compose up --build -d` (rebuild container) |
| Backend Python files | `docker compose restart cortex-server` |
| Frontend TypeScript files | Auto-reloads if `npm run dev` is running |
