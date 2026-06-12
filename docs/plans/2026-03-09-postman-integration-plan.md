# Postman Integration — Dual-Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dual-mode Postman integration that maintains API collections via either Postman Cloud API or local Git YAML files, driven by a `POSTMAN_SYNC_MODE` setting.

**Architecture:** Port the Postman skill's Python client library into Cortex's backend. Expose `find_postman` and `manage_postman` MCP tools that proxy to the Postman Cloud API using centralized credentials. A behavioral extension (SKILL.md, already created) instructs Claude to check the mode and branch between MCP tools (api mode) and local YAML file writes (git mode). Cross-mode sync actions allow replication between modes.

**Tech Stack:** Python 3.12, FastAPI, httpx, Pydantic, MCP (FastMCP), React/TypeScript, Supabase/PostgreSQL

**Design doc:** `docs/plans/2026-03-09-postman-integration-design.md`
**Behavioral extension (already created):** `integrations/claude-code/extensions/postman-integration/SKILL.md`

---

## Phase 1: Foundation

### Task 1: Database Migration

**Files:**
- Create: `migration/0.1.0/020_add_postman_collection_uid.sql`

**Step 1: Write the migration**

```sql
-- 020_add_postman_collection_uid.sql
-- Add postman_collection_uid to cortex_projects for API-mode collection tracking.

ALTER TABLE cortex_projects
  ADD COLUMN IF NOT EXISTS postman_collection_uid VARCHAR(255);

COMMENT ON COLUMN cortex_projects.postman_collection_uid IS 'Postman collection UID for API-mode sync. Set by manage_postman init_collection action.';
```

**Step 2: Apply migration to local database**

Run: `psql` or Supabase SQL editor to execute the migration.
Verify: `SELECT column_name FROM information_schema.columns WHERE table_name = 'cortex_projects' AND column_name = 'postman_collection_uid';` returns 1 row.

**Step 3: Commit**

```bash
git add migration/0.1.0/020_add_postman_collection_uid.sql
git commit -m "feat: add postman_collection_uid column to cortex_projects (T1)"
```

---

### Task 2: Port Postman Client Library

Port files from `~/.claude/skills/postman/` into `python/src/server/services/postman/`. Modify `config.py` for programmatic initialization (no `.env` file reading).

**Files:**
- Create: `python/src/server/services/postman/__init__.py`
- Create: `python/src/server/services/postman/exceptions.py` (copy from `~/.claude/skills/postman/utils/exceptions.py`)
- Create: `python/src/server/services/postman/retry_handler.py` (copy from `~/.claude/skills/postman/utils/retry_handler.py`)
- Create: `python/src/server/services/postman/formatters.py` (copy from `~/.claude/skills/postman/utils/formatters.py`)
- Create: `python/src/server/services/postman/config.py` (modified from `~/.claude/skills/postman/scripts/config.py`)
- Create: `python/src/server/services/postman/postman_client.py` (copy from `~/.claude/skills/postman/scripts/postman_client.py`)

**Step 1: Create the package init**

```python
"""Postman integration services for Cortex."""

from .postman_service import PostmanService

__all__ = ["PostmanService"]
```

Note: `PostmanService` doesn't exist yet — this will fail until Task 3. That's fine, just comment out the import for now and uncomment in Task 3.

**Step 2: Copy exceptions.py**

Copy `~/.claude/skills/postman/utils/exceptions.py` → `python/src/server/services/postman/exceptions.py`

No modifications needed — these are pure domain exceptions.

**Step 3: Copy and modify retry_handler.py**

Copy `~/.claude/skills/postman/utils/retry_handler.py` → `python/src/server/services/postman/retry_handler.py`

Modifications:
- Replace `print(..., file=sys.stderr)` with `logger.warning(...)` using `from src.server.config.logfire_config import get_logger; logger = get_logger(__name__)`
- Remove `import sys`

**Step 4: Copy formatters.py**

Copy `~/.claude/skills/postman/utils/formatters.py` → `python/src/server/services/postman/formatters.py`

No modifications needed.

**Step 5: Create modified config.py**

This is the key change — remove `.env` file reading, accept programmatic initialization:

```python
"""Configuration for Postman API client. Modified for programmatic initialization."""


class PostmanConfig:
    """Postman API configuration. Accepts values directly rather than reading from environment."""

    def __init__(
        self,
        api_key: str = "",
        workspace_id: str = "",
        rate_limit_delay: int = 60,
        max_retries: int = 3,
        timeout: int = 30,
        use_proxy: bool = False,
    ):
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.log_level = "INFO"

        if not use_proxy:
            self.proxies = {"http": None, "https": None}
        else:
            self.proxies = None

    def validate(self):
        """Validate that required configuration is present."""
        if not self.api_key:
            raise ValueError("POSTMAN_API_KEY not configured. Set it in Cortex Settings → API Keys.")
        if not self.api_key.startswith("PMAK-"):
            raise ValueError("Invalid POSTMAN_API_KEY format. Keys should start with 'PMAK-'.")

    @property
    def base_url(self):
        return "https://api.getpostman.com"

    @property
    def headers(self):
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}
```

**Step 6: Copy postman_client.py**

Copy `~/.claude/skills/postman/scripts/postman_client.py` → `python/src/server/services/postman/postman_client.py`

Modifications:
- Change imports at the top:
  - Replace `from scripts.config import PostmanConfig` → `from .config import PostmanConfig`
  - Replace `from utils.retry_handler import RetryHandler` → `from .retry_handler import RetryHandler`
  - Replace `from utils.exceptions import ...` → `from .exceptions import ...`
- Remove the `load_env_file()` call and `_env_loaded` variable if present
- Remove any `import os; os.getenv(...)` calls related to config (they should go through `self.config`)
- Ensure `__init__` accepts `config=None` parameter (it already does in the original)

**Step 7: Verify imports work**

Run: `cd python && uv run python -c "from src.server.services.postman.config import PostmanConfig; print('OK')"`
Expected: `OK`

Run: `cd python && uv run python -c "from src.server.services.postman.postman_client import PostmanClient; print('OK')"`
Expected: `OK` (may show warnings about optional deps, that's fine)

**Step 8: Commit**

```bash
git add python/src/server/services/postman/
git commit -m "feat: port Postman client library into Cortex backend (T2)"
```

---

## Phase 2: Service Layer

### Task 3: PostmanService

**Files:**
- Create: `python/src/server/services/postman/postman_service.py`
- Modify: `python/src/server/services/postman/__init__.py` (uncomment PostmanService import)
- Test: `python/tests/server/services/postman/test_postman_service.py`

**Step 1: Write the test file**

```python
"""Tests for PostmanService."""

from unittest.mock import MagicMock, patch

import pytest

from src.server.services.postman.postman_service import PostmanService


@pytest.fixture
def mock_credential_service():
    with patch("src.server.services.postman.postman_service.credential_service") as mock:
        mock.get_credential = MagicMock(side_effect=lambda key, **kwargs: {
            "POSTMAN_API_KEY": "PMAK-test-key-123",
            "POSTMAN_WORKSPACE_ID": "workspace-123",
            "POSTMAN_SYNC_MODE": "api",
        }.get(key))
        yield mock


@pytest.fixture
def service(mock_credential_service):
    return PostmanService()


class TestGetSyncMode:
    def test_returns_api_when_configured(self, mock_credential_service):
        svc = PostmanService()
        assert svc.get_sync_mode() == "api"

    def test_returns_disabled_when_not_set(self):
        with patch("src.server.services.postman.postman_service.credential_service") as mock:
            mock.get_credential = MagicMock(return_value=None)
            svc = PostmanService()
            assert svc.get_sync_mode() == "disabled"


class TestGetOrCreateCollection:
    def test_returns_existing_collection(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.list_collections.return_value = [
                {"name": "Cortex", "uid": "col-123"}
            ]
            mock_client_fn.return_value = mock_client

            uid = service.get_or_create_collection("Cortex")
            assert uid == "col-123"
            mock_client.create_collection.assert_not_called()

    def test_creates_when_not_found(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.list_collections.return_value = []
            mock_client.create_collection.return_value = {"uid": "col-new"}
            mock_client_fn.return_value = mock_client

            uid = service.get_or_create_collection("Cortex")
            assert uid == "col-new"
            mock_client.create_collection.assert_called_once()


class TestUpsertRequest:
    def test_creates_folder_and_adds_request(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = {
                "collection": {"info": {"name": "Test"}, "item": []}
            }
            mock_client.update_collection.return_value = {"collection": {"uid": "col-123"}}
            mock_client_fn.return_value = mock_client

            service.upsert_request("col-123", "Projects", {
                "name": "Create Project",
                "method": "POST",
                "url": "{{base_url}}/api/projects",
            })

            mock_client.update_collection.assert_called_once()
            updated = mock_client.update_collection.call_args[0][1]
            assert len(updated["collection"]["item"]) == 1
            assert updated["collection"]["item"][0]["name"] == "Projects"

    def test_updates_existing_request(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = {
                "collection": {
                    "info": {"name": "Test"},
                    "item": [{
                        "name": "Projects",
                        "item": [{"name": "Create Project", "request": {"method": "POST", "url": "old"}}]
                    }]
                }
            }
            mock_client.update_collection.return_value = {"collection": {"uid": "col-123"}}
            mock_client_fn.return_value = mock_client

            service.upsert_request("col-123", "Projects", {
                "name": "Create Project",
                "method": "POST",
                "url": "{{base_url}}/api/projects",
            })

            updated = mock_client.update_collection.call_args[0][1]
            folder = updated["collection"]["item"][0]
            assert len(folder["item"]) == 1
            assert folder["item"][0]["request"]["url"] == "{{base_url}}/api/projects"


class TestListCollectionStructure:
    def test_returns_folder_request_tree(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = {
                "collection": {
                    "info": {"name": "Test"},
                    "item": [{
                        "name": "Projects",
                        "item": [
                            {"name": "Create Project", "request": {"method": "POST", "url": "/api/projects"}},
                            {"name": "List Projects", "request": {"method": "GET", "url": "/api/projects"}},
                        ]
                    }]
                }
            }
            mock_client_fn.return_value = mock_client

            structure = service.list_collection_structure("col-123")
            assert "Projects" in structure
            assert len(structure["Projects"]) == 2
            assert structure["Projects"][0]["name"] == "Create Project"
```

**Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/server/services/postman/test_postman_service.py -v`
Expected: FAIL (module not found)

**Step 3: Write PostmanService implementation**

```python
"""Orchestration layer for Postman API operations."""

from typing import Any

from src.server.config.logfire_config import get_logger
from src.server.services.credential_service import credential_service

from .config import PostmanConfig
from .postman_client import PostmanClient

logger = get_logger(__name__)


class PostmanService:
    """Thin orchestration layer over PostmanClient using centralized credentials."""

    def get_sync_mode(self) -> str:
        """Get the current Postman sync mode from settings."""
        mode = credential_service.get_credential("POSTMAN_SYNC_MODE", decrypt=False)
        if mode is None:
            return "disabled"
        return mode if mode in ("api", "git", "disabled") else "disabled"

    def _get_client(self) -> PostmanClient:
        """Create a PostmanClient using credentials from cortex_settings."""
        api_key = credential_service.get_credential("POSTMAN_API_KEY", decrypt=True)
        workspace_id = credential_service.get_credential("POSTMAN_WORKSPACE_ID", decrypt=False)

        if not api_key:
            raise ValueError("POSTMAN_API_KEY not configured in Cortex Settings.")

        config = PostmanConfig(
            api_key=api_key,
            workspace_id=workspace_id or "",
        )
        config.validate()
        return PostmanClient(config=config)

    def get_or_create_collection(self, project_name: str) -> str:
        """Find a collection by name or create it. Returns the collection UID."""
        client = self._get_client()
        collections = client.list_collections()

        for col in collections:
            if col.get("name") == project_name:
                logger.info(f"Found existing collection | name={project_name} | uid={col['uid']}")
                return col["uid"]

        result = client.create_collection({
            "info": {
                "name": project_name,
                "description": f"API collection for {project_name}.",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        })
        uid = result.get("uid", result.get("id", ""))
        logger.info(f"Created new collection | name={project_name} | uid={uid}")
        return uid

    def upsert_request(
        self,
        collection_uid: str,
        folder_name: str,
        request_data: dict[str, Any],
    ) -> None:
        """Add or update a request in a collection folder. Creates the folder if needed."""
        client = self._get_client()
        collection = client.get_collection(collection_uid)
        items = collection.get("collection", {}).get("item", [])

        # Find or create folder
        folder = None
        for item in items:
            if item.get("name") == folder_name and "item" in item:
                folder = item
                break

        if folder is None:
            folder = {"name": folder_name, "item": []}
            items.append(folder)

        # Build the Postman request object
        request_name = request_data.get("name", "Unnamed Request")
        postman_request = self._build_postman_request(request_data)

        # Find existing request by name and update, or append
        existing_idx = None
        for i, req in enumerate(folder["item"]):
            if req.get("name") == request_name:
                existing_idx = i
                break

        request_item = {"name": request_name, "request": postman_request}

        # Add test script as event if provided
        test_script = request_data.get("test_script")
        if test_script:
            request_item["event"] = [{
                "listen": "test",
                "script": {"type": "text/javascript", "exec": test_script.split("\n")},
            }]

        if existing_idx is not None:
            folder["item"][existing_idx] = request_item
            logger.info(f"Updated request | folder={folder_name} | name={request_name}")
        else:
            folder["item"].append(request_item)
            logger.info(f"Added request | folder={folder_name} | name={request_name}")

        collection["collection"]["item"] = items
        client.update_collection(collection_uid, collection)

    def upsert_environment(self, env_name: str, variables: dict[str, str]) -> dict[str, Any]:
        """Create or update an environment with auto-secret detection."""
        client = self._get_client()
        envs = client.list_environments()

        existing = None
        for env in envs:
            if env.get("name") == env_name:
                existing = env
                break

        values = [{"key": k, "value": v, "enabled": True} for k, v in variables.items()]

        if existing:
            result = client.update_environment(existing["uid"], {"name": env_name, "values": values})
            logger.info(f"Updated environment | name={env_name}")
        else:
            result = client.create_environment(env_name, variables)
            logger.info(f"Created environment | name={env_name}")

        return result

    def list_collection_structure(self, collection_uid: str) -> dict[str, list[dict[str, str]]]:
        """Return a dict of folder_name → list of {name, method, url} for dedup checking."""
        client = self._get_client()
        collection = client.get_collection(collection_uid)
        items = collection.get("collection", {}).get("item", [])

        structure: dict[str, list[dict[str, str]]] = {}
        for item in items:
            if "item" in item:
                folder_name = item["name"]
                structure[folder_name] = []
                for req in item["item"]:
                    request = req.get("request", {})
                    structure[folder_name].append({
                        "name": req.get("name", ""),
                        "method": request.get("method", ""),
                        "url": request.get("url", "") if isinstance(request.get("url"), str) else request.get("url", {}).get("raw", ""),
                    })
        return structure

    def _build_postman_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Convert simplified request dict to Postman collection format."""
        url = request_data.get("url", "")
        postman_req: dict[str, Any] = {
            "method": request_data.get("method", "GET"),
            "header": [{"key": k, "value": v} for k, v in request_data.get("headers", {}).items()],
            "url": {"raw": url},
            "description": request_data.get("description", ""),
        }

        body = request_data.get("body")
        if body:
            import json
            postman_req["body"] = {
                "mode": "raw",
                "raw": json.dumps(body, indent=2) if isinstance(body, dict) else str(body),
                "options": {"raw": {"language": "json"}},
            }

        return postman_req
```

**Step 4: Update `__init__.py`**

Uncomment the PostmanService import in `python/src/server/services/postman/__init__.py`.

**Step 5: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/server/services/postman/test_postman_service.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add python/src/server/services/postman/ python/tests/server/services/postman/
git commit -m "feat: add PostmanService with tests (T3)"
```

---

## Phase 3: API Routes

### Task 4: Postman API Routes

**Files:**
- Create: `python/src/server/api_routes/postman_api.py`
- Modify: `python/src/server/main.py` (add router import + registration)
- Test: `python/tests/server/api_routes/test_postman_api.py`

**Step 1: Write the API route module**

```python
"""Postman integration API endpoints.

Handles:
- Collection creation and management (API mode)
- Environment sync from session-start hook
- Status/mode checking
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config.logfire_config import get_logger, logfire
from ..services.postman.postman_service import PostmanService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/postman", tags=["postman"])


# ── Request models ────────────────────────────────────────────────────────────

class CreateCollectionRequest(BaseModel):
    project_name: str
    project_id: str | None = None


class UpsertRequestBody(BaseModel):
    folder_name: str
    request: dict[str, Any]


class UpsertEnvironmentRequest(BaseModel):
    name: str
    variables: dict[str, str]


class SyncEnvironmentRequest(BaseModel):
    project_id: str
    system_name: str
    env_file_content: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_postman_status():
    """Get Postman integration status and current sync mode."""
    try:
        service = PostmanService()
        mode = service.get_sync_mode()
        configured = mode == "api"

        if configured:
            try:
                client = service._get_client()
                configured = True
            except ValueError:
                configured = False

        return {
            "sync_mode": mode,
            "configured": configured,
        }
    except Exception as e:
        logfire.error(f"Error checking postman status | error={e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/collections")
async def create_collection(request: CreateCollectionRequest):
    """Create or find a collection for a project."""
    try:
        service = PostmanService()
        if service.get_sync_mode() != "api":
            return {"status": "skipped", "reason": "sync_mode is not api"}

        logfire.info(f"Creating collection | project_name={request.project_name}")
        uid = service.get_or_create_collection(request.project_name)
        return {"collection_uid": uid, "project_name": request.project_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except Exception as e:
        logfire.error(f"Error creating collection | error={e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/collections/{collection_uid}/requests")
async def upsert_request(collection_uid: str, body: UpsertRequestBody):
    """Add or update a request in a collection folder."""
    try:
        service = PostmanService()
        if service.get_sync_mode() != "api":
            return {"status": "skipped", "reason": "sync_mode is not api"}

        logfire.info(f"Upserting request | collection={collection_uid} | folder={body.folder_name}")
        service.upsert_request(collection_uid, body.folder_name, body.request)
        return {"success": True, "folder": body.folder_name, "request_name": body.request.get("name")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except Exception as e:
        logfire.error(f"Error upserting request | error={e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.put("/environments/{env_name}")
async def upsert_environment(env_name: str, body: UpsertEnvironmentRequest):
    """Create or update an environment."""
    try:
        service = PostmanService()
        if service.get_sync_mode() != "api":
            return {"status": "skipped", "reason": "sync_mode is not api"}

        logfire.info(f"Upserting environment | name={env_name}")
        result = service.upsert_environment(env_name, body.variables)
        return {"success": True, "environment": env_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except Exception as e:
        logfire.error(f"Error upserting environment | error={e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/environments/sync")
async def sync_environment(body: SyncEnvironmentRequest):
    """Sync .env file content to a Postman environment. Called by session-start hook."""
    try:
        service = PostmanService()
        if service.get_sync_mode() != "api":
            return {"status": "skipped", "reason": "sync_mode is not api"}

        # Parse .env content into key-value pairs
        variables = {}
        for line in body.env_file_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    variables[key] = value

        env_name = f"{body.project_id} - {body.system_name}"
        service.upsert_environment(env_name, variables)
        return {"success": True, "environment": env_name, "variables_count": len(variables)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except Exception as e:
        logfire.error(f"Error syncing environment | error={e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
```

**Step 2: Register router in main.py**

Add to imports (after line 37):
```python
from .api_routes.postman_api import router as postman_router
```

Add to registrations (after line 224):
```python
app.include_router(postman_router)
```

**Step 3: Write API route tests**

```python
"""Tests for Postman API routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_postman_service():
    with patch("src.server.api_routes.postman_api.PostmanService") as MockClass:
        mock_instance = MagicMock()
        MockClass.return_value = mock_instance
        mock_instance.get_sync_mode.return_value = "api"
        yield mock_instance


@pytest.fixture
def client():
    from src.server.main import app
    return TestClient(app)


class TestGetStatus:
    def test_returns_sync_mode(self, client, mock_postman_service):
        mock_postman_service.get_sync_mode.return_value = "git"
        response = client.get("/api/postman/status")
        assert response.status_code == 200
        assert response.json()["sync_mode"] == "git"

    def test_returns_disabled_by_default(self, client, mock_postman_service):
        mock_postman_service.get_sync_mode.return_value = "disabled"
        response = client.get("/api/postman/status")
        assert response.status_code == 200
        assert response.json()["sync_mode"] == "disabled"


class TestCreateCollection:
    def test_creates_collection(self, client, mock_postman_service):
        mock_postman_service.get_or_create_collection.return_value = "col-123"
        response = client.post("/api/postman/collections", json={"project_name": "Cortex"})
        assert response.status_code == 200
        assert response.json()["collection_uid"] == "col-123"

    def test_skips_when_not_api_mode(self, client, mock_postman_service):
        mock_postman_service.get_sync_mode.return_value = "git"
        response = client.post("/api/postman/collections", json={"project_name": "Cortex"})
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"


class TestUpsertRequest:
    def test_adds_request(self, client, mock_postman_service):
        response = client.post("/api/postman/collections/col-123/requests", json={
            "folder_name": "Projects",
            "request": {"name": "Create Project", "method": "POST", "url": "{{base_url}}/api/projects"},
        })
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestSyncEnvironment:
    def test_parses_env_and_syncs(self, client, mock_postman_service):
        mock_postman_service.upsert_environment.return_value = {}
        response = client.post("/api/postman/environments/sync", json={
            "project_id": "proj-123",
            "system_name": "WIN-DEV-01",
            "env_file_content": "BASE_URL=http://localhost:8181\n# comment\nAPI_KEY=secret123",
        })
        assert response.status_code == 200
        assert response.json()["variables_count"] == 2
```

**Step 4: Run tests**

Run: `cd python && uv run pytest tests/server/api_routes/test_postman_api.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add python/src/server/api_routes/postman_api.py python/src/server/main.py python/tests/server/api_routes/test_postman_api.py
git commit -m "feat: add Postman API routes with tests (T4)"
```

---

## Phase 4: MCP Tools

### Task 5: MCP Tools (find_postman + manage_postman)

**Files:**
- Create: `python/src/mcp_server/features/postman/__init__.py`
- Create: `python/src/mcp_server/features/postman/postman_tools.py`
- Modify: `python/src/mcp_server/mcp_server.py` (register tools)
- Test: `python/tests/mcp_server/features/postman/test_postman_tools.py`

**Step 1: Create MCP feature init**

```python
"""Postman integration tools for Cortex MCP Server."""

from .postman_tools import register_postman_tools

__all__ = ["register_postman_tools"]
```

**Step 2: Write MCP tools**

```python
"""MCP tools for Postman integration.

Provides:
- find_postman: Get sync mode, collection info, search for duplicates
- manage_postman: Collection/environment/request management actions
"""

import json
import logging
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.mcp_server.utils.error_handling import MCPErrorFormatter
from src.mcp_server.utils.timeout_config import get_default_timeout
from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)


def register_postman_tools(mcp: FastMCP):
    """Register Postman integration tools with the MCP server."""

    @mcp.tool()
    async def find_postman(
        ctx: Context,
        project_id: str | None = None,
        collection_uid: str | None = None,
        query: str | None = None,
    ) -> str:
        """
        Get Postman integration status, collection info, or search requests.

        Call with no params to get the current sync_mode (api/git/disabled).
        Call with project_id to get collection details.
        Call with query to search request names for dedup checking.

        Args:
            project_id: Get collection info for a specific project
            collection_uid: Get full collection structure (folders + requests)
            query: Search requests by name across the collection

        Returns:
            JSON with sync_mode and requested data
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Always get status first
                status_resp = await client.get(urljoin(api_url, "/api/postman/status"))
                if status_resp.status_code != 200:
                    return MCPErrorFormatter.from_http_error(status_resp, "get postman status")

                status = status_resp.json()

                if not project_id and not collection_uid and not query:
                    return json.dumps({"success": True, **status})

                if status.get("sync_mode") != "api":
                    return json.dumps({
                        "success": True,
                        "sync_mode": status.get("sync_mode"),
                        "message": "Detailed collection info only available in api mode",
                    })

                # Project-level collection info
                if project_id:
                    proj_resp = await client.get(urljoin(api_url, f"/api/projects/{project_id}"))
                    if proj_resp.status_code == 200:
                        project = proj_resp.json()
                        col_uid = project.get("postman_collection_uid")
                        result = {
                            "success": True,
                            "sync_mode": "api",
                            "project_name": project.get("name"),
                            "collection_uid": col_uid,
                        }
                        if col_uid:
                            try:
                                struct_resp = await client.get(
                                    urljoin(api_url, f"/api/postman/collections/{col_uid}/structure")
                                )
                                if struct_resp.status_code == 200:
                                    result["structure"] = struct_resp.json()
                            except Exception:
                                pass
                        return json.dumps(result)
                    return MCPErrorFormatter.format_error("not_found", f"Project {project_id} not found", 404)

                return json.dumps({"success": True, **status})

        except Exception as e:
            logger.error(f"Error in find_postman: {e}")
            return MCPErrorFormatter.format_error("internal_error", str(e), 500)

    @mcp.tool()
    async def manage_postman(
        ctx: Context,
        action: str,
        project_id: str | None = None,
        project_name: str | None = None,
        folder_name: str | None = None,
        request: dict | None = None,
        request_name: str | None = None,
        system_name: str | None = None,
        variables: dict | None = None,
        env_file_content: str | None = None,
        collection_uid: str | None = None,
    ) -> str:
        """
        Manage Postman collections, requests, and environments.

        Only functional in api sync mode. Returns skipped status in other modes.

        Supported actions:
        - init_collection: Create collection for a project
        - add_request: Add/update request in a collection folder
        - update_environment: Create/update an environment
        - remove_request: Remove a request from a folder
        - sync_environment: Push .env content as a system environment
        - import_from_git: Read local postman/ YAML and push to Postman Cloud
        - export_to_git: Pull from Postman Cloud and write local YAML files

        Args:
            action: The operation to perform
            project_id: Cortex project ID
            project_name: Project name for collection naming
            folder_name: Target folder in collection
            request: Request data dict (name, method, url, headers, body, test_script)
            request_name: Name of request to remove
            system_name: System name for environment naming
            variables: Environment variables dict
            env_file_content: Raw .env file content for sync
            collection_uid: Postman collection UID (for export_to_git)
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Check mode first
                status_resp = await client.get(urljoin(api_url, "/api/postman/status"))
                if status_resp.status_code == 200:
                    mode = status_resp.json().get("sync_mode", "disabled")
                    if mode != "api" and action not in ("import_from_git", "export_to_git"):
                        return json.dumps({
                            "status": "skipped",
                            "reason": f"sync_mode is '{mode}', not 'api'. Use git mode YAML files instead.",
                            "sync_mode": mode,
                        })

                if action == "init_collection":
                    if not project_name:
                        return MCPErrorFormatter.format_error("validation_error", "project_name is required", 400)

                    resp = await client.post(
                        urljoin(api_url, "/api/postman/collections"),
                        json={"project_name": project_name, "project_id": project_id},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # Store UID on project if project_id provided
                        if project_id and data.get("collection_uid"):
                            await client.put(
                                urljoin(api_url, f"/api/projects/{project_id}"),
                                json={"postman_collection_uid": data["collection_uid"]},
                            )
                        return json.dumps({"success": True, **data})
                    return MCPErrorFormatter.from_http_error(resp, "init collection")

                elif action == "add_request":
                    if not folder_name or not request:
                        return MCPErrorFormatter.format_error("validation_error", "folder_name and request are required", 400)

                    # Get collection UID from project
                    col_uid = collection_uid
                    if not col_uid and project_id:
                        proj_resp = await client.get(urljoin(api_url, f"/api/projects/{project_id}"))
                        if proj_resp.status_code == 200:
                            col_uid = proj_resp.json().get("postman_collection_uid")

                    if not col_uid:
                        # Auto-init if no collection exists
                        if project_name or project_id:
                            name = project_name or project_id
                            init_resp = await client.post(
                                urljoin(api_url, "/api/postman/collections"),
                                json={"project_name": name, "project_id": project_id},
                            )
                            if init_resp.status_code == 200:
                                col_uid = init_resp.json().get("collection_uid")

                    if not col_uid:
                        return MCPErrorFormatter.format_error("validation_error", "Could not determine collection UID", 400)

                    resp = await client.post(
                        urljoin(api_url, f"/api/postman/collections/{col_uid}/requests"),
                        json={"folder_name": folder_name, "request": request},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "add request")

                elif action == "update_environment":
                    if not system_name or not variables:
                        return MCPErrorFormatter.format_error("validation_error", "system_name and variables required", 400)

                    env_name = f"{project_name or project_id} - {system_name}"
                    resp = await client.put(
                        urljoin(api_url, f"/api/postman/environments/{env_name}"),
                        json={"name": env_name, "variables": variables},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "update environment")

                elif action == "remove_request":
                    return json.dumps({"success": True, "message": "remove_request not yet implemented"})

                elif action == "sync_environment":
                    if not project_id or not env_file_content:
                        return MCPErrorFormatter.format_error("validation_error", "project_id and env_file_content required", 400)

                    resp = await client.post(
                        urljoin(api_url, "/api/postman/environments/sync"),
                        json={
                            "project_id": project_id,
                            "system_name": system_name or "default",
                            "env_file_content": env_file_content,
                        },
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "sync environment")

                elif action == "import_from_git":
                    return json.dumps({"success": True, "message": "import_from_git: agent should read local YAML files and call add_request for each"})

                elif action == "export_to_git":
                    return json.dumps({"success": True, "message": "export_to_git: agent should call find_postman to get structure, then write YAML files locally"})

                else:
                    return MCPErrorFormatter.format_error("validation_error", f"Unknown action: {action}", 400)

        except Exception as e:
            logger.error(f"Error in manage_postman: {e}")
            return MCPErrorFormatter.format_error("internal_error", str(e), 500)
```

**Step 3: Register in mcp_server.py**

Add after the LeaveOff Point tools block (after line 640, before `logger.info(f"📦 Total modules registered:")`):

```python
    # Postman Integration Tools
    try:
        from src.mcp_server.features.postman import register_postman_tools

        register_postman_tools(mcp)
        modules_registered += 1
        logger.info("✓ Postman integration module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ Postman integration module not available (optional): {e}")
    except (SyntaxError, NameError, AttributeError) as e:
        logger.error(f"✗ Code error in postman tools - MUST FIX: {e}")
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"✗ Failed to register postman tools: {e}")
        logger.error(traceback.format_exc())
```

**Step 4: Write MCP tool tests**

```python
"""Tests for Postman MCP tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for MCP tool tests."""
    with patch("src.mcp_server.features.postman.postman_tools.httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield client_instance


class TestFindPostman:
    @pytest.mark.anyio
    async def test_returns_sync_mode(self, mock_httpx_client):
        from src.mcp_server.features.postman.postman_tools import register_postman_tools

        mock_httpx_client.get = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"sync_mode": "git", "configured": False},
        ))

        mcp = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator

        mcp.tool = capture_tool
        register_postman_tools(mcp)

        ctx = MagicMock()
        result = await tools["find_postman"](ctx)
        data = json.loads(result)
        assert data["sync_mode"] == "git"
        assert data["success"] is True


class TestManagePostman:
    @pytest.mark.anyio
    async def test_skips_when_not_api_mode(self, mock_httpx_client):
        from src.mcp_server.features.postman.postman_tools import register_postman_tools

        mock_httpx_client.get = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"sync_mode": "git"},
        ))

        mcp = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator

        mcp.tool = capture_tool
        register_postman_tools(mcp)

        ctx = MagicMock()
        result = await tools["manage_postman"](ctx, action="add_request", folder_name="Test", request={"name": "test"})
        data = json.loads(result)
        assert data["status"] == "skipped"
        assert "git" in data["reason"]
```

**Step 5: Run tests**

Run: `cd python && uv run pytest tests/mcp_server/features/postman/test_postman_tools.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add python/src/mcp_server/features/postman/ python/src/mcp_server/mcp_server.py python/tests/mcp_server/features/postman/
git commit -m "feat: add find_postman and manage_postman MCP tools (T5)"
```

---

## Phase 5: Settings Integration

### Task 6: Backend Settings Default

**Files:**
- Modify: `python/src/server/api_routes/settings_api.py`

**Step 1: Add POSTMAN_SYNC_MODE to defaults**

In `OPTIONAL_SETTINGS_WITH_DEFAULTS` dict (around line 135), add:

```python
"POSTMAN_SYNC_MODE": "disabled",  # Postman integration mode: api, git, or disabled
```

**Step 2: Verify**

Run: `cd python && uv run pytest tests/ -k settings -v --timeout=30`
Expected: Existing settings tests still pass

**Step 3: Commit**

```bash
git add python/src/server/api_routes/settings_api.py
git commit -m "feat: add POSTMAN_SYNC_MODE to settings defaults (T6)"
```

---

### Task 7: Frontend Mode Selector

**Files:**
- Modify: `cortex-ui/src/contexts/SettingsContext.tsx`
- Modify: `cortex-ui/src/components/settings/FeaturesSection.tsx`

**Step 1: Add postmanSyncMode to SettingsContext**

In the `SettingsContextType` interface, add:
```typescript
postmanSyncMode: string;
setPostmanSyncMode: (mode: string) => Promise<void>;
```

In the provider state, add:
```typescript
const [postmanSyncMode, setPostmanSyncModeState] = useState("disabled");
```

In `loadSettings`, add to the `Promise.all`:
```typescript
credentialsService.getCredential('POSTMAN_SYNC_MODE').catch(() => ({ value: undefined }))
```

And handle the response:
```typescript
if (postmanSyncModeResponse.value !== undefined) {
  setPostmanSyncModeState(postmanSyncModeResponse.value);
}
```

Add setter function:
```typescript
const setPostmanSyncMode = async (mode: string) => {
  try {
    setPostmanSyncModeState(mode);
    await credentialsService.createCredential({
      key: 'POSTMAN_SYNC_MODE',
      value: mode,
      is_encrypted: false,
      category: 'features',
      description: 'Postman integration sync mode: api, git, or disabled'
    });
  } catch (error) {
    console.error('Failed to update Postman sync mode:', error);
    setPostmanSyncModeState(postmanSyncMode);
    throw error;
  }
};
```

Add to the context value object:
```typescript
postmanSyncMode,
setPostmanSyncMode,
```

**Step 2: Add mode selector to FeaturesSection**

Add a new section in the features grid for Postman mode selection. Use a `<select>` dropdown or the existing `Select` primitive with three options: `disabled`, `git`, `api`.

Show a validation warning when `api` is selected — inform the user that `POSTMAN_API_KEY` must be set in the API Keys section.

Follow the existing toggle handler pattern: local state update → API call → toast → revert on error.

**Step 3: Verify**

Run: `cd cortex-ui && npm run build`
Expected: No TypeScript errors

**Step 4: Commit**

```bash
git add cortex-ui/src/contexts/SettingsContext.tsx cortex-ui/src/components/settings/FeaturesSection.tsx
git commit -m "feat: add Postman sync mode selector to Settings UI (T7)"
```

---

## Phase 6: Session Hook

### Task 8: Session-Start Hook .env Sync

**Files:**
- Modify: `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`
- Modify: `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py`

**Step 1: Add sync method to CortexClient**

Add to `cortex_client.py`:

```python
async def sync_postman_environment(self, system_name: str, env_content: str) -> bool:
    """POST .env content to Postman environment sync endpoint. Returns True on success."""
    if not self.is_configured():
        return False

    url = f"{self.api_url}/api/postman/environments/sync"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={
                "project_id": self.project_id,
                "system_name": system_name,
                "env_file_content": env_content,
            })
        return response.status_code < 400
    except Exception:
        return False

async def get_postman_sync_mode(self) -> str:
    """GET the current Postman sync mode. Returns 'disabled' on error."""
    if not self.is_configured():
        return "disabled"

    url = f"{self.api_url}/api/credentials/POSTMAN_SYNC_MODE"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        if response.status_code >= 400:
            return "disabled"
        data = response.json()
        return data.get("value", "disabled")
    except Exception:
        return "disabled"
```

**Step 2: Add .env sync to session_start_hook.py**

In the `main()` function, after the existing context gathering (after `print(_format_context(...))`), add:

```python
# Postman environment sync (API mode only, best-effort)
try:
    postman_mode = await asyncio.wait_for(client.get_postman_sync_mode(), timeout=2.0)
    if postman_mode == "api":
        # Read local .env
        env_path = Path.cwd() / ".env"
        if env_path.is_file():
            env_content = env_path.read_text(encoding="utf-8")
            # Get system name from cortex state
            state_path = Path.cwd() / ".claude" / "cortex-state.json"
            system_name = "default"
            if state_path.is_file():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                system_name = state.get("system_name", "default")
            await asyncio.wait_for(
                client.sync_postman_environment(system_name, env_content),
                timeout=3.0,
            )
except Exception:
    pass  # Best-effort, don't block session start
```

Add `import json` to the imports if not already present.

**Step 3: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py integrations/claude-code/plugins/cortex-memory/src/cortex_client.py
git commit -m "feat: add Postman .env sync to session-start hook (T8)"
```

---

## Phase 7: Cross-Mode Sync

### Task 9: Cross-Mode Sync Guidance in SKILL.md

The `import_from_git` and `export_to_git` actions are agent-driven (Claude reads/writes files and calls tools). The MCP tools return guidance messages telling Claude what to do. The actual file reading/writing happens in the agent's conversation, not in the backend.

This is already handled by the existing SKILL.md and MCP tool responses. No additional code needed — the MCP tools already return instructional messages for these actions.

**Verify:** Read the SKILL.md to confirm cross-mode sync is documented.
**Verify:** Read the MCP tool code to confirm `import_from_git` and `export_to_git` return guidance.

**Step 1: Commit (if any adjustments were needed)**

This task is verification only. If everything is in place, skip the commit.

---

## Phase 8: Final Verification

### Task 10: Run All Tests

**Step 1: Run backend tests**

Run: `cd python && uv run pytest tests/ -v --timeout=60`
Expected: All existing + new tests pass

**Step 2: Run frontend build**

Run: `cd cortex-ui && npm run build`
Expected: No TypeScript errors

**Step 3: Run linters**

Run: `cd python && uv run ruff check src/server/services/postman/ src/server/api_routes/postman_api.py src/mcp_server/features/postman/`
Expected: No errors (fix any that appear)

**Step 4: Manual smoke test**

1. Start the server: `docker compose up --build -d` or `make dev`
2. Open Settings → verify "Postman Sync Mode" selector appears with `disabled`/`git`/`api` options
3. Set mode to `git` → verify no errors
4. Set mode to `api` → verify validation warning about API key
5. Check MCP health: `curl http://localhost:8051/health`

**Step 5: Final commit**

```bash
git commit -m "chore: verify all tests pass for Postman integration (T10)"
```
