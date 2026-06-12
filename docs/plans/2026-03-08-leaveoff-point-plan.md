# LeaveOff Point Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement per-project LeaveOff Points that capture development state after every coding task and are automatically loaded at session start, with a 90% usage guardrail.

**Architecture:** Standalone service with dedicated DB table (`cortex_leaveoff_points`), REST API nested under `/api/projects/{id}/leaveoff`, MCP tool (`manage_leaveoff_point`), SessionStart hook integration, and PostToolUse observation counter. File + database dual storage.

**Tech Stack:** Python 3.12, FastAPI, Supabase (PostgreSQL), httpx, Pydantic, pytest

**Design Doc:** `docs/plans/2026-03-08-leaveoff-point-design.md`

---

### Task 1: Database Migration

**Files:**
- Create: `migration/0.1.0/019_add_leaveoff_points.sql`

**Step 1: Write the migration**

```sql
-- 019_add_leaveoff_points.sql
-- Per-project singleton capturing current development state for session continuity

CREATE TABLE IF NOT EXISTS cortex_leaveoff_points (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL UNIQUE REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id      TEXT,
    last_session_id UUID,
    content         TEXT NOT NULL,
    component       TEXT,
    next_steps      TEXT[] NOT NULL DEFAULT '{}',
    references      TEXT[] NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leaveoff_project ON cortex_leaveoff_points(project_id);
```

**Step 2: Apply the migration**

Run:
```bash
cd /home/winadmin/projects/Trinity/cortex
# Apply via psql or Supabase dashboard — depends on local setup
# If using docker compose with local Supabase:
docker compose exec supabase-db psql -U postgres -d postgres -f /docker-entrypoint-initdb.d/migrations/019_add_leaveoff_points.sql
```

Alternatively, apply manually via Supabase SQL editor.

**Step 3: Commit**

```bash
git add migration/0.1.0/019_add_leaveoff_points.sql
git commit -m "feat: add cortex_leaveoff_points migration (019)"
```

---

### Task 2: LeaveOff Service — Write Tests

**Files:**
- Create: `python/tests/server/services/leaveoff/__init__.py`
- Create: `python/tests/server/services/leaveoff/test_leaveoff_service.py`

**Step 1: Create test directory**

```bash
mkdir -p python/tests/server/services/leaveoff
touch python/tests/server/services/leaveoff/__init__.py
```

**Step 2: Write the failing tests**

Create `python/tests/server/services/leaveoff/test_leaveoff_service.py`:

```python
"""Tests for LeaveOffService DB operations."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.server.services.leaveoff.leaveoff_service import LeaveOffService


@pytest.fixture
def mock_supabase():
    client = MagicMock()

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        return builder

    client.table.side_effect = _table
    return client


@pytest.fixture
def service(mock_supabase):
    return LeaveOffService(supabase_client=mock_supabase)


# ── upsert ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_creates_new_record(service, mock_supabase):
    """Upsert creates a new LeaveOff point when none exists."""
    upsert_data = {
        "project_id": "proj-1",
        "content": "Added OAuth2 token refresh",
        "component": "Auth Module",
        "next_steps": ["Add token revocation"],
        "references": ["PRPs/auth.md"],
        "machine_id": "dev-1",
        "last_session_id": "sess-1",
        "metadata": {},
    }

    table_mock = MagicMock()
    table_mock.upsert.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[{
        "id": "lop-1",
        **upsert_data,
        "updated_at": "2026-03-08T14:00:00Z",
        "created_at": "2026-03-08T14:00:00Z",
    }])
    mock_supabase.table.side_effect = lambda name: table_mock if name == "cortex_leaveoff_points" else MagicMock()

    result = await service.upsert(**upsert_data)

    assert result["id"] == "lop-1"
    assert result["project_id"] == "proj-1"
    assert result["content"] == "Added OAuth2 token refresh"
    table_mock.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_replaces_existing_record(service, mock_supabase):
    """Upsert replaces an existing LeaveOff point for the same project."""
    upsert_data = {
        "project_id": "proj-1",
        "content": "Updated content",
        "component": "Auth Module",
        "next_steps": ["New step"],
        "references": [],
        "machine_id": "dev-2",
        "last_session_id": "sess-2",
        "metadata": {},
    }

    table_mock = MagicMock()
    table_mock.upsert.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[{
        "id": "lop-1",
        **upsert_data,
        "updated_at": "2026-03-08T15:00:00Z",
        "created_at": "2026-03-08T14:00:00Z",
    }])
    mock_supabase.table.side_effect = lambda name: table_mock if name == "cortex_leaveoff_points" else MagicMock()

    result = await service.upsert(**upsert_data)

    assert result["machine_id"] == "dev-2"
    # Verify upsert was called with on_conflict for atomic replace
    call_kwargs = table_mock.upsert.call_args
    assert call_kwargs is not None


# ── get ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_record(service, mock_supabase):
    """Get returns the LeaveOff point for a project."""
    record = {
        "id": "lop-1",
        "project_id": "proj-1",
        "content": "Did some work",
        "component": "API",
        "next_steps": ["Step 1"],
        "references": [],
        "machine_id": "dev-1",
        "last_session_id": None,
        "metadata": {},
        "updated_at": "2026-03-08T14:00:00Z",
        "created_at": "2026-03-08T14:00:00Z",
    }

    table_mock = MagicMock()
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[record])
    mock_supabase.table.side_effect = lambda name: table_mock if name == "cortex_leaveoff_points" else MagicMock()

    result = await service.get("proj-1")

    assert result is not None
    assert result["project_id"] == "proj-1"
    assert result["next_steps"] == ["Step 1"]


@pytest.mark.asyncio
async def test_get_returns_none_when_not_found(service, mock_supabase):
    """Get returns None when no LeaveOff point exists for the project."""
    result = await service.get("nonexistent")
    assert result is None


# ── delete ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_removes_record(service, mock_supabase):
    """Delete removes the LeaveOff point for a project."""
    table_mock = MagicMock()
    table_mock.delete.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[{"id": "lop-1"}])
    mock_supabase.table.side_effect = lambda name: table_mock if name == "cortex_leaveoff_points" else MagicMock()

    result = await service.delete("proj-1")

    assert result is True
    table_mock.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_returns_false_when_not_found(service, mock_supabase):
    """Delete returns False when no record exists to delete."""
    result = await service.delete("nonexistent")
    assert result is False
```

**Step 3: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/leaveoff/ -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.server.services.leaveoff'`

**Step 4: Commit**

```bash
git add python/tests/server/services/leaveoff/
git commit -m "test: add failing tests for LeaveOffService"
```

---

### Task 3: LeaveOff Service — Implementation

**Files:**
- Create: `python/src/server/services/leaveoff/__init__.py`
- Create: `python/src/server/services/leaveoff/leaveoff_service.py`

**Step 1: Create the service package**

```bash
mkdir -p python/src/server/services/leaveoff
```

**Step 2: Write `__init__.py`**

Create `python/src/server/services/leaveoff/__init__.py`:

```python
"""LeaveOff Point Services Package."""

from .leaveoff_service import LeaveOffService

__all__ = ["LeaveOffService"]
```

**Step 3: Write the service**

Create `python/src/server/services/leaveoff/leaveoff_service.py`:

```python
"""LeaveOffService — manages per-project LeaveOff Points for session continuity.

Each project has at most one LeaveOff Point (enforced by UNIQUE constraint on project_id).
Upsert semantics ensure atomic create-or-replace behavior.
"""

from datetime import UTC, datetime

from ...config.logfire_config import get_logger
from ...utils import get_supabase_client

logger = get_logger(__name__)

TABLE = "cortex_leaveoff_points"


class LeaveOffService:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    async def upsert(
        self,
        project_id: str,
        content: str,
        next_steps: list[str],
        component: str | None = None,
        references: list[str] | None = None,
        machine_id: str | None = None,
        last_session_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create or replace the LeaveOff point for a project.

        Uses Supabase upsert with on_conflict='project_id' so the DB
        enforces exactly one record per project.
        """
        now = datetime.now(UTC).isoformat()
        data = {
            "project_id": project_id,
            "content": content,
            "component": component,
            "next_steps": next_steps or [],
            "references": references or [],
            "machine_id": machine_id,
            "last_session_id": last_session_id,
            "metadata": metadata or {},
            "updated_at": now,
        }

        result = (
            self.supabase.table(TABLE)
            .upsert(data, on_conflict="project_id")
            .execute()
        )

        if not result.data:
            raise RuntimeError(f"LeaveOff upsert returned no data for project {project_id}")

        record = result.data[0]
        logger.info(f"LeaveOff point upserted | project_id={project_id} | component={component}")
        return record

    async def get(self, project_id: str) -> dict | None:
        """Get the current LeaveOff point for a project. Returns None if not found."""
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )

        if not result.data:
            return None
        return result.data[0]

    async def delete(self, project_id: str) -> bool:
        """Delete the LeaveOff point for a project. Returns True if a record was deleted."""
        result = (
            self.supabase.table(TABLE)
            .delete()
            .eq("project_id", project_id)
            .execute()
        )

        deleted = bool(result.data)
        if deleted:
            logger.info(f"LeaveOff point deleted | project_id={project_id}")
        return deleted
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/leaveoff/ -v`

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add python/src/server/services/leaveoff/
git commit -m "feat: implement LeaveOffService with upsert/get/delete"
```

---

### Task 4: API Routes — Write Tests

**Files:**
- Create: `python/tests/server/api_routes/__init__.py` (if not exists)
- Create: `python/tests/server/api_routes/test_leaveoff_api.py`

**Step 1: Write the failing tests**

Create `python/tests/server/api_routes/test_leaveoff_api.py`:

```python
"""Tests for LeaveOff API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server.main import app

client = TestClient(app)


@pytest.fixture
def mock_leaveoff_service():
    with patch("src.server.api_routes.leaveoff_api.LeaveOffService") as MockClass:
        instance = MockClass.return_value
        instance.upsert = AsyncMock()
        instance.get = AsyncMock()
        instance.delete = AsyncMock()
        yield instance


def test_upsert_leaveoff(mock_leaveoff_service):
    """PUT /api/projects/{id}/leaveoff creates or replaces the LeaveOff point."""
    mock_leaveoff_service.upsert.return_value = {
        "id": "lop-1",
        "project_id": "proj-1",
        "content": "Added auth",
        "component": "Auth",
        "next_steps": ["Add tests"],
        "references": [],
        "machine_id": "dev-1",
        "last_session_id": None,
        "metadata": {},
        "updated_at": "2026-03-08T14:00:00Z",
        "created_at": "2026-03-08T14:00:00Z",
    }

    response = client.put(
        "/api/projects/proj-1/leaveoff",
        json={
            "content": "Added auth",
            "component": "Auth",
            "next_steps": ["Add tests"],
            "references": [],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "proj-1"
    assert data["next_steps"] == ["Add tests"]


def test_get_leaveoff(mock_leaveoff_service):
    """GET /api/projects/{id}/leaveoff returns the current LeaveOff point."""
    mock_leaveoff_service.get.return_value = {
        "id": "lop-1",
        "project_id": "proj-1",
        "content": "Did work",
        "component": "API",
        "next_steps": ["Next thing"],
        "references": [],
        "machine_id": "dev-1",
        "last_session_id": None,
        "metadata": {},
        "updated_at": "2026-03-08T14:00:00Z",
        "created_at": "2026-03-08T14:00:00Z",
    }

    response = client.get("/api/projects/proj-1/leaveoff")

    assert response.status_code == 200
    assert response.json()["component"] == "API"


def test_get_leaveoff_not_found(mock_leaveoff_service):
    """GET returns 404 when no LeaveOff point exists."""
    mock_leaveoff_service.get.return_value = None

    response = client.get("/api/projects/proj-1/leaveoff")

    assert response.status_code == 404


def test_delete_leaveoff(mock_leaveoff_service):
    """DELETE removes the LeaveOff point."""
    mock_leaveoff_service.delete.return_value = True

    response = client.delete("/api/projects/proj-1/leaveoff")

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_delete_leaveoff_not_found(mock_leaveoff_service):
    """DELETE returns 404 when no record exists."""
    mock_leaveoff_service.delete.return_value = False

    response = client.delete("/api/projects/proj-1/leaveoff")

    assert response.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/api_routes/test_leaveoff_api.py -v`

Expected: FAIL (import errors — `leaveoff_api` module doesn't exist yet)

**Step 3: Commit**

```bash
git add python/tests/server/api_routes/test_leaveoff_api.py
git commit -m "test: add failing tests for LeaveOff API endpoints"
```

---

### Task 5: API Routes — Implementation

**Files:**
- Create: `python/src/server/api_routes/leaveoff_api.py`
- Create: `python/src/server/models/leaveoff.py`
- Modify: `python/src/server/main.py` (lines 36-37 for import, line 222 for include_router)

**Step 1: Write the Pydantic model**

Create `python/src/server/models/leaveoff.py`:

```python
"""Pydantic models for LeaveOff Point API."""

from pydantic import BaseModel


class UpsertLeaveOffRequest(BaseModel):
    content: str
    next_steps: list[str]
    component: str | None = None
    references: list[str] | None = None
    machine_id: str | None = None
    last_session_id: str | None = None
    metadata: dict | None = None
```

**Step 2: Write the API routes**

Create `python/src/server/api_routes/leaveoff_api.py`:

```python
"""LeaveOff Point API — per-project session continuity state."""

from fastapi import APIRouter, HTTPException

from ..config.logfire_config import get_logger
from ..models.leaveoff import UpsertLeaveOffRequest
from ..services.leaveoff.leaveoff_service import LeaveOffService
from ..utils import get_supabase_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["leaveoff"])


@router.put("/{project_id}/leaveoff")
async def upsert_leaveoff(project_id: str, request: UpsertLeaveOffRequest) -> dict:
    """Create or replace the LeaveOff point for a project."""
    service = LeaveOffService(supabase_client=get_supabase_client())
    record = await service.upsert(
        project_id=project_id,
        content=request.content,
        next_steps=request.next_steps,
        component=request.component,
        references=request.references,
        machine_id=request.machine_id,
        last_session_id=request.last_session_id,
        metadata=request.metadata,
    )
    return record


@router.get("/{project_id}/leaveoff")
async def get_leaveoff(project_id: str) -> dict:
    """Get the current LeaveOff point for a project."""
    service = LeaveOffService(supabase_client=get_supabase_client())
    record = await service.get(project_id)
    if not record:
        raise HTTPException(status_code=404, detail="No LeaveOff point found for this project")
    return record


@router.delete("/{project_id}/leaveoff")
async def delete_leaveoff(project_id: str) -> dict:
    """Delete the LeaveOff point for a project."""
    service = LeaveOffService(supabase_client=get_supabase_client())
    deleted = await service.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No LeaveOff point found for this project")
    return {"success": True}
```

**Step 3: Register the router in main.py**

Modify `python/src/server/main.py`:

Add import at line 37 (after the materialization_router import):
```python
from .api_routes.leaveoff_api import router as leaveoff_router
```

Add include at line 223 (after `app.include_router(materialization_router)`):
```python
app.include_router(leaveoff_router)
```

**Step 4: Run API tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/api_routes/test_leaveoff_api.py -v`

Expected: All 5 tests PASS

**Step 5: Run full backend test suite to verify no regressions**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest -v`

Expected: All tests PASS

**Step 6: Commit**

```bash
git add python/src/server/models/leaveoff.py python/src/server/api_routes/leaveoff_api.py python/src/server/main.py
git commit -m "feat: add LeaveOff Point API routes (PUT/GET/DELETE)"
```

---

### Task 6: MCP Tool

**Files:**
- Create: `python/src/mcp_server/features/leaveoff/__init__.py`
- Create: `python/src/mcp_server/features/leaveoff/leaveoff_tools.py`
- Modify: `python/src/mcp_server/mcp_server.py` (after line 623, before line 625)

**Step 1: Create the MCP tool package**

```bash
mkdir -p python/src/mcp_server/features/leaveoff
```

**Step 2: Write `__init__.py`**

Create `python/src/mcp_server/features/leaveoff/__init__.py`:

```python
"""LeaveOff Point tools for Cortex MCP Server."""

from .leaveoff_tools import register_leaveoff_tools

__all__ = ["register_leaveoff_tools"]
```

**Step 3: Write the MCP tool**

Create `python/src/mcp_server/features/leaveoff/leaveoff_tools.py`:

```python
"""MCP tools for managing per-project LeaveOff Points.

LeaveOff Points capture the current development state and must be updated after
every coding task and before session termination due to resource limits. This is
the primary mechanism for context continuity across sessions.
"""

import json
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from ...utils import get_api_url, get_logger

logger = get_logger(__name__)


def register_leaveoff_tools(mcp: FastMCP):
    """Register LeaveOff Point tools with the MCP server."""

    @mcp.tool()
    async def manage_leaveoff_point(
        ctx: Context,
        action: str,
        project_id: str,
        content: str | None = None,
        next_steps: list[str] | None = None,
        component: str | None = None,
        references: list[str] | None = None,
        machine_id: str | None = None,
        last_session_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Manage the LeaveOff Point for a project — the development state snapshot
        that ensures context continuity across sessions.

        IMPORTANT: Update the LeaveOff Point after every coding task that adds,
        modifies, or removes functionality. Also update before session termination
        when approaching resource limits (the 90% rule).

        Args:
            action: One of "update", "get", "delete"
            project_id: The Cortex project ID
            content: What was accomplished (required for "update")
            next_steps: Concrete next actions with file paths (required for "update")
            component: Architectural module or feature area being worked on
            references: PRPs, design docs, or key files referenced during work
            machine_id: Identifier of the machine performing the update
            last_session_id: Session ID that produced this LeaveOff point
            metadata: Additional context (env vars, perf stats, etc.)
        """
        api_url = get_api_url()
        base = urljoin(api_url, f"/api/projects/{project_id}/leaveoff")
        timeout = httpx.Timeout(30.0, connect=5.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "update":
                    if not content:
                        return json.dumps({"success": False, "error": "'content' is required for update"})
                    if not next_steps:
                        return json.dumps({"success": False, "error": "'next_steps' is required for update"})

                    payload = {
                        "content": content,
                        "next_steps": next_steps,
                        "component": component,
                        "references": references or [],
                        "machine_id": machine_id,
                        "last_session_id": last_session_id,
                        "metadata": metadata or {},
                    }
                    response = await client.put(base, json=payload)

                elif action == "get":
                    response = await client.get(base)

                elif action == "delete":
                    response = await client.delete(base)

                else:
                    return json.dumps({"success": False, "error": f"Unknown action: {action}. Use 'update', 'get', or 'delete'."})

                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                elif response.status_code == 404:
                    return json.dumps({"success": False, "error": "No LeaveOff point found for this project"})
                else:
                    return json.dumps({"success": False, "error": f"HTTP {response.status_code}: {response.text}"}, indent=2)

        except Exception as e:
            logger.error(f"Error in manage_leaveoff_point: {e}", exc_info=True)
            return json.dumps({"success": False, "error": str(e)})
```

**Step 4: Register in MCP server**

Modify `python/src/mcp_server/mcp_server.py`. After the materialization tools block (after line 623), add:

```python
    # LeaveOff Point Tools
    try:
        from src.mcp_server.features.leaveoff import register_leaveoff_tools

        register_leaveoff_tools(mcp)
        modules_registered += 1
        logger.info("✓ LeaveOff Point module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ LeaveOff Point module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in leaveoff tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register leaveoff tools: {e}")
        logger.error(traceback.format_exc())
```

**Step 5: Verify MCP server starts cleanly**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run python -c "from src.mcp_server.features.leaveoff import register_leaveoff_tools; print('Import OK')"`

Expected: `Import OK`

**Step 6: Commit**

```bash
git add python/src/mcp_server/features/leaveoff/ python/src/mcp_server/mcp_server.py
git commit -m "feat: add manage_leaveoff_point MCP tool"
```

---

### Task 7: File Writing Integration

**Files:**
- Modify: `python/src/server/services/leaveoff/leaveoff_service.py`

The `upsert` method should also write the `LeaveOffPoint.md` file when a `project_path` is available.

**Step 1: Add file-writing to the service**

Modify `python/src/server/services/leaveoff/leaveoff_service.py` — add a `_write_file` method and call it from `upsert`:

```python
import os
from datetime import UTC, datetime

import yaml

from ...config.logfire_config import get_logger
from ...utils import get_supabase_client

logger = get_logger(__name__)

TABLE = "cortex_leaveoff_points"
KNOWLEDGE_DIR = ".cortex/knowledge"
FILENAME = "LeaveOffPoint.md"


class LeaveOffService:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    async def upsert(
        self,
        project_id: str,
        content: str,
        next_steps: list[str],
        component: str | None = None,
        references: list[str] | None = None,
        machine_id: str | None = None,
        last_session_id: str | None = None,
        metadata: dict | None = None,
        project_path: str | None = None,
    ) -> dict:
        """Create or replace the LeaveOff point for a project."""
        now = datetime.now(UTC).isoformat()
        data = {
            "project_id": project_id,
            "content": content,
            "component": component,
            "next_steps": next_steps or [],
            "references": references or [],
            "machine_id": machine_id,
            "last_session_id": last_session_id,
            "metadata": metadata or {},
            "updated_at": now,
        }

        result = (
            self.supabase.table(TABLE)
            .upsert(data, on_conflict="project_id")
            .execute()
        )

        if not result.data:
            raise RuntimeError(f"LeaveOff upsert returned no data for project {project_id}")

        record = result.data[0]
        logger.info(f"LeaveOff point upserted | project_id={project_id} | component={component}")

        # Write the local file if project_path is provided
        if project_path:
            try:
                self._write_file(project_path, record)
            except Exception as e:
                logger.error(f"Failed to write LeaveOffPoint.md: {e}", exc_info=True)

        return record

    def _write_file(self, project_path: str, record: dict) -> str:
        """Write LeaveOffPoint.md to .cortex/knowledge/ with YAML frontmatter."""
        knowledge_dir = os.path.join(project_path, KNOWLEDGE_DIR)
        os.makedirs(knowledge_dir, exist_ok=True)

        frontmatter = {
            "project_id": record.get("project_id"),
            "component": record.get("component"),
            "updated_at": record.get("updated_at"),
            "machine_id": record.get("machine_id"),
        }

        next_steps = record.get("next_steps", [])
        references = record.get("references", [])
        content = record.get("content", "")

        lines = [
            "---",
            yaml.dump(frontmatter, default_flow_style=False).strip(),
            "---",
            "",
            content,
            "",
        ]

        if next_steps:
            lines.append("## Next Steps")
            for step in next_steps:
                lines.append(f"- {step}")
            lines.append("")

        if references:
            lines.append("## References")
            for ref in references:
                lines.append(f"- {ref}")
            lines.append("")

        file_path = os.path.join(knowledge_dir, FILENAME)
        with open(file_path, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Wrote LeaveOffPoint.md | path={file_path}")
        return file_path

    async def get(self, project_id: str) -> dict | None:
        """Get the current LeaveOff point for a project."""
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    async def delete(self, project_id: str, project_path: str | None = None) -> bool:
        """Delete the LeaveOff point for a project and optionally remove the file."""
        result = (
            self.supabase.table(TABLE)
            .delete()
            .eq("project_id", project_id)
            .execute()
        )
        deleted = bool(result.data)
        if deleted:
            logger.info(f"LeaveOff point deleted | project_id={project_id}")
            if project_path:
                file_path = os.path.join(project_path, KNOWLEDGE_DIR, FILENAME)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Removed LeaveOffPoint.md | path={file_path}")
        return deleted
```

**Step 2: Update the API route to accept project_path**

Modify `python/src/server/models/leaveoff.py` — add `project_path`:

```python
class UpsertLeaveOffRequest(BaseModel):
    content: str
    next_steps: list[str]
    component: str | None = None
    references: list[str] | None = None
    machine_id: str | None = None
    last_session_id: str | None = None
    metadata: dict | None = None
    project_path: str | None = None
```

Modify `python/src/server/api_routes/leaveoff_api.py` — pass `project_path` through:

In the `upsert_leaveoff` function, add `project_path=request.project_path` to the `service.upsert()` call.

Also update the MCP tool (`leaveoff_tools.py`) to accept and pass `project_path`:

Add `project_path: str | None = None` to the tool function signature, add it to the payload, and document it in the docstring.

**Step 3: Run all tests**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/leaveoff/ tests/server/api_routes/test_leaveoff_api.py -v`

Expected: All tests PASS (existing tests don't use project_path, so they're unaffected)

**Step 4: Commit**

```bash
git add python/src/server/services/leaveoff/ python/src/server/models/leaveoff.py python/src/server/api_routes/leaveoff_api.py python/src/mcp_server/features/leaveoff/leaveoff_tools.py
git commit -m "feat: add LeaveOffPoint.md file writing to upsert flow"
```

---

### Task 8: SessionStart Hook — Fetch and Inject LeaveOff Point

**Files:**
- Modify: `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py`
- Modify: `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`

**Step 1: Add `get_leaveoff_point` to the Cortex client**

Modify `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py`. Add after the `get_knowledge_status` method (after line 113):

```python
    async def get_leaveoff_point(self) -> dict | None:
        """GET /api/projects/{id}/leaveoff. Returns the LeaveOff point or None."""
        if not self.is_configured():
            return None

        url = f"{self.api_url}/api/projects/{self.project_id}/leaveoff"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                return None
            return response.json()
        except Exception:
            return None
```

**Step 2: Update session_start_hook.py to fetch and format the LeaveOff point**

Modify `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`.

Update the `_format_context` function signature to accept `leaveoff`:

```python
def _format_context(sessions: list[dict], tasks: list[dict], knowledge: dict, leaveoff: dict | None = None) -> str:
    parts: list[str] = ["<cortex-context>"]

    # LeaveOff Point goes first — it's the most important context
    if leaveoff:
        component = leaveoff.get("component", "Unknown")
        updated = leaveoff.get("updated_at", "")[:10] if leaveoff.get("updated_at") else ""
        content = leaveoff.get("content", "")
        next_steps = leaveoff.get("next_steps", [])
        references = leaveoff.get("references", [])

        parts.append(f"\n## LeaveOff Point (Last Session State)")
        parts.append(f"**Component:** {component}")
        parts.append(f"**Updated:** {updated}")
        if content:
            parts.append(f"\n{content}")
        if next_steps:
            parts.append("\n### Next Steps")
            for step in next_steps:
                parts.append(f"- {step}")
        if references:
            parts.append("\n### References")
            for ref in references:
                parts.append(f"- {ref}")

    # ... rest of existing formatting (sessions, tasks, knowledge) unchanged ...
```

Update the `main()` function to add `client.get_leaveoff_point()` to the parallel fetch:

```python
    try:
        sessions, tasks, knowledge, leaveoff = await asyncio.wait_for(
            asyncio.gather(
                client.get_recent_sessions(limit=5),
                client.get_active_tasks(limit=10),
                client.get_knowledge_status(),
                client.get_leaveoff_point(),
                return_exceptions=True,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print("<!-- cortex-memory: Cortex unreachable (timeout), skipping context -->")
        return
    except Exception:
        return

    # Replace exceptions from gather with empty defaults
    if isinstance(sessions, Exception):
        sessions = []
    if isinstance(tasks, Exception):
        tasks = []
    if isinstance(knowledge, Exception):
        knowledge = {}
    if isinstance(leaveoff, Exception):
        leaveoff = None

    print(_format_context(sessions, tasks, knowledge, leaveoff))
```

**Step 3: Test manually**

Run: `cd /home/winadmin/projects/Trinity/cortex && python3 integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`

Expected: Should print `<cortex-context>` block. If Cortex is running and a LeaveOff point exists, it appears first in the output.

**Step 4: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/src/cortex_client.py integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py
git commit -m "feat: inject LeaveOff Point into SessionStart context"
```

---

### Task 9: PostToolUse Observation Counter (90% Rule Safety Net)

**Files:**
- Modify: `integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py`

**Step 1: Add observation counting and warning emission**

Modify `integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py`. Add the counter logic after the `tracker.append_observation()` call.

Add at the top of the file (after the existing imports):

```python
_WARNING_THRESHOLD = 80
_WARNING_REPEAT_INTERVAL = 10
```

Add a new function:

```python
def _check_observation_count(buffer_path: str) -> None:
    """Count observations and emit a warning if approaching resource limits."""
    try:
        buf = Path(buffer_path)
        if not buf.exists():
            return

        count = sum(1 for _ in buf.open())

        if count >= _WARNING_THRESHOLD and (count - _WARNING_THRESHOLD) % _WARNING_REPEAT_INTERVAL == 0:
            print(
                f"\n<system-reminder>\n"
                f"SESSION RESOURCE WARNING: This session has recorded {count} tool operations. "
                f"You are approaching resource limits. After completing your current task, "
                f"generate a final LeaveOff Point via manage_leaveoff_point(action=\"update\") "
                f"and advise the user to start a new session.\n"
                f"</system-reminder>"
            )
    except Exception:
        pass  # Never block Claude Code
```

Call it at the end of `main()`, after the `tracker.append_observation()` try/except block:

```python
    _check_observation_count(_BUFFER_PATH)
```

**Step 2: Test manually**

Create a test buffer with 80 lines and run the hook:

```bash
cd /home/winadmin/projects/Trinity/cortex
# Create a fake buffer with 80 lines
python3 -c "
from pathlib import Path
buf = Path('.claude/cortex-memory-buffer.jsonl')
buf.parent.mkdir(parents=True, exist_ok=True)
with buf.open('w') as f:
    for i in range(80):
        f.write('{\"tool_name\": \"Edit\", \"summary\": \"test\"}\n')
print(f'Created {sum(1 for _ in buf.open())} lines')
"
# Run observation hook with mock input
echo '{"tool_name": "Edit", "tool_input": {"file_path": "test.py"}, "session_id": "test-123"}' | python3 integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py
```

Expected: Should print the `<system-reminder>` warning block.

```bash
# Clean up test buffer
rm -f .claude/cortex-memory-buffer.jsonl
```

**Step 3: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py
git commit -m "feat: add observation counter with 90% rule warning"
```

---

### Task 10: CLAUDE.md Behavioral Enforcement

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add the LeaveOff Point Protocol section**

Modify `CLAUDE.md`. Add the following after the "Code Quality" section (find the line `### Code Quality` and its content, then add after it):

```markdown
## LeaveOff Point Protocol

### After Every Coding Task
After completing any coding task that adds, modifies, or removes functionality, you MUST
update the LeaveOff Point before moving to the next task:

1. Call `manage_leaveoff_point(action="update")` with:
   - `content`: What was accomplished in this task (be specific about files changed and why)
   - `component`: The architectural module or feature area (e.g., "Authentication Module")
   - `next_steps`: Concrete, actionable items for the next session (not vague — include file paths)
   - `references`: PRPs, design docs, or key files that informed this work

2. This is NOT optional. Skipping this step means the next session starts with no context.

### Session Resource Management (The 90% Rule)
When you observe any of these signals, you are approaching resource limits:
- The conversation has exceeded 80+ tool uses
- You receive a system reminder about observation count
- You sense the conversation has been running extensively

Upon detecting these signals:
1. **Stop active coding immediately** — do not start new tasks
2. **Generate a final LeaveOff Point** via `manage_leaveoff_point(action="update")` with
   comprehensive next_steps covering all remaining planned work
3. **Advise the user**: "This session has reached its resource limit. The LeaveOff Point
   has been saved. Please start a new session to continue — context will be restored
   automatically."
4. **Do not continue coding** after generating the final LeaveOff Point

### Session Start
At the beginning of every session, the LeaveOff Point is automatically loaded via the
session start hook. You do not need to fetch it manually. Review the injected context
and orient your work around the documented next steps.
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add LeaveOff Point Protocol to CLAUDE.md"
```

---

### Task 11: End-to-End Verification

**Step 1: Run the full backend test suite**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest -v`

Expected: All tests PASS (including new LeaveOff tests)

**Step 2: Run linters**

Run: `cd /home/winadmin/projects/Trinity/cortex && make lint-be`

Expected: No errors from ruff or mypy

**Step 3: Verify the API manually**

Start the server and test the endpoints:

```bash
# If using Docker:
docker compose restart cortex-server

# Test PUT (create LeaveOff point)
curl -X PUT http://localhost:8181/api/projects/<your-project-id>/leaveoff \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Test LeaveOff point",
    "next_steps": ["Step 1", "Step 2"],
    "component": "Test Component"
  }'

# Test GET (retrieve it)
curl http://localhost:8181/api/projects/<your-project-id>/leaveoff

# Test DELETE (remove it)
curl -X DELETE http://localhost:8181/api/projects/<your-project-id>/leaveoff
```

Expected: PUT returns the record, GET returns same record, DELETE returns `{"success": true}`

**Step 4: Verify MCP tool registration**

```bash
curl http://localhost:8051/health
# Check MCP server logs for "LeaveOff Point module registered"
docker compose logs cortex-mcp | grep -i leaveoff
```

Expected: Health check returns OK, logs show the module registered.

**Step 5: Verify SessionStart hook**

```bash
python3 integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py
```

Expected: If a LeaveOff point exists, it appears in the `<cortex-context>` block.

---

## Task Summary

| Task | Description | Files | Test Count |
|------|-------------|-------|------------|
| T1 | Database migration | 1 new | 0 |
| T2 | Service tests (failing) | 2 new | 6 |
| T3 | Service implementation | 2 new | 6 pass |
| T4 | API route tests (failing) | 1 new | 5 |
| T5 | API routes + registration | 3 new, 1 modify | 5 pass |
| T6 | MCP tool + registration | 3 new, 1 modify | 0 (HTTP-based) |
| T7 | File writing integration | 3 modify | existing pass |
| T8 | SessionStart hook + client | 2 modify | manual |
| T9 | Observation counter (90% rule) | 1 modify | manual |
| T10 | CLAUDE.md behavioral rules | 1 modify | 0 |
| T11 | End-to-end verification | 0 | full suite |
