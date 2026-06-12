"""Unit tests for extensions management tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import Context

from src.mcp_server.features.extensions.extension_tools import register_extension_tools


@pytest.fixture
def mock_mcp():
    """Create a mock MCP server for testing."""
    mock = MagicMock()
    mock._tools = {}

    def tool_decorator():
        def decorator(func):
            mock._tools[func.__name__] = func
            return func

        return decorator

    mock.tool = tool_decorator
    return mock


@pytest.fixture
def mock_context():
    """Create a mock context for testing."""
    return MagicMock(spec=Context)


@pytest.fixture
def registered_tools(mock_mcp):
    """Register tools and return the tool dict."""
    register_extension_tools(mock_mcp)
    return mock_mcp._tools


# --------------------------------------------------------------------------- #
# find_extensions tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_find_extensions_list_all(registered_tools, mock_context):
    """Test listing all extensions."""
    find_extensions = registered_tools["find_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "extensions": [
            {"id": "sk-1", "name": "memory", "description": "Memory extension"},
            {"id": "sk-2", "name": "deploy", "description": "Deploy extension"},
        ],
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await find_extensions(mock_context)

        data = json.loads(result)
        assert data["success"] is True
        assert data["count"] == 2
        assert len(data["extensions"]) == 2


@pytest.mark.asyncio
async def test_find_extensions_search_by_query(registered_tools, mock_context):
    """Test searching extensions by keyword."""
    find_extensions = registered_tools["find_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "extensions": [
            {"id": "sk-1", "name": "memory", "description": "Persistent memory extension"},
            {"id": "sk-2", "name": "deploy", "description": "Deployment automation"},
        ],
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await find_extensions(mock_context, query="memory")

        data = json.loads(result)
        assert data["success"] is True
        assert data["count"] == 1
        assert data["extensions"][0]["name"] == "memory"


@pytest.mark.asyncio
async def test_find_extensions_by_id(registered_tools, mock_context):
    """Test getting a specific extension by ID."""
    find_extensions = registered_tools["find_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "sk-1",
        "name": "memory",
        "description": "Memory extension",
        "content": "# Full content here",
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await find_extensions(mock_context, extension_id="sk-1")

        data = json.loads(result)
        assert data["success"] is True
        assert data["extension"]["id"] == "sk-1"
        assert data["extension"]["content"] == "# Full content here"


@pytest.mark.asyncio
async def test_find_extensions_by_id_not_found(registered_tools, mock_context):
    """Test getting a non-existent extension."""
    find_extensions = registered_tools["find_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not found"

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await find_extensions(mock_context, extension_id="non-existent")

        data = json.loads(result)
        assert data["success"] is False
        assert data["error"]["type"] == "not_found"


@pytest.mark.asyncio
async def test_find_extensions_for_project(registered_tools, mock_context):
    """Test listing extensions for a specific project."""
    find_extensions = registered_tools["find_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "all_extensions": [
            {"id": "sk-1", "name": "memory", "description": "Memory extension", "installed": True},
        ],
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await find_extensions(mock_context, project_id="proj-1")

        data = json.loads(result)
        assert data["success"] is True
        assert data["project_id"] == "proj-1"
        assert data["count"] == 1


# --------------------------------------------------------------------------- #
# manage_extensions tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_manage_extensions_validate(registered_tools, mock_context):
    """Test validating extension content."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "valid": True,
        "name": "test-extension",
        "warnings": [],
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(
            mock_context,
            action="validate",
            extension_content="---\nname: test-extension\n---\n# Content",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["valid"] is True


@pytest.mark.asyncio
async def test_manage_extensions_validate_missing_content(registered_tools, mock_context):
    """Test validate fails when content is missing."""
    manage_extensions = registered_tools["manage_extensions"]

    result = await manage_extensions(mock_context, action="validate")

    data = json.loads(result)
    assert data["success"] is False
    assert "extension_content" in data["error"]["message"]


@pytest.mark.asyncio
async def test_manage_extensions_upload_new(registered_tools, mock_context):
    """Test uploading a new extension."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "extension": {"id": "sk-new", "name": "my-extension"},
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(
            mock_context,
            action="upload",
            extension_content="---\nname: my-extension\ndescription: An extension\nversion: 1.0\n---\n# Content",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["created"] is True
        assert data["extension"]["name"] == "my-extension"


@pytest.mark.asyncio
async def test_manage_extensions_upload_conflict_updates(registered_tools, mock_context):
    """Test uploading an extension that already exists triggers an update."""
    manage_extensions = registered_tools["manage_extensions"]

    # First POST returns 409
    mock_conflict_response = MagicMock()
    mock_conflict_response.status_code = 409
    mock_conflict_response.json.return_value = {"detail": "Extension already exists"}
    mock_conflict_response.text = '{"detail": "Extension already exists"}'

    # GET /api/extensions returns existing extension
    mock_list_response = MagicMock()
    mock_list_response.status_code = 200
    mock_list_response.json.return_value = {
        "extensions": [{"id": "sk-existing", "name": "my-extension"}],
    }

    # PUT update succeeds
    mock_update_response = MagicMock()
    mock_update_response.status_code = 200
    mock_update_response.json.return_value = {
        "extension": {"id": "sk-existing", "name": "my-extension"},
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_conflict_response
        mock_async_client.get.return_value = mock_list_response
        mock_async_client.put.return_value = mock_update_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(
            mock_context,
            action="upload",
            extension_content="---\nname: my-extension\n---\n# Updated content",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["created"] is False
        assert "updated" in data["message"].lower()


@pytest.mark.asyncio
async def test_manage_extensions_upload_missing_name(registered_tools, mock_context):
    """Test upload fails when no name is provided or parseable."""
    manage_extensions = registered_tools["manage_extensions"]

    result = await manage_extensions(
        mock_context,
        action="upload",
        extension_content="# Just content, no frontmatter",
    )

    data = json.loads(result)
    assert data["success"] is False
    assert "name" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_manage_extensions_install(registered_tools, mock_context):
    """Test installing an extension for a project."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": "Extension installed successfully",
        "installation": {"extension_id": "sk-1", "project_id": "proj-1"},
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(
            mock_context,
            action="install",
            extension_id="sk-1",
            project_id="proj-1",
            system_id="sys-1",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert "installed" in data["message"].lower()


@pytest.mark.asyncio
async def test_manage_extensions_install_missing_params(registered_tools, mock_context):
    """Test install fails without required parameters."""
    manage_extensions = registered_tools["manage_extensions"]

    # Missing extension_id
    result = await manage_extensions(mock_context, action="install", project_id="proj-1")
    data = json.loads(result)
    assert data["success"] is False
    assert "extension_id" in data["error"]["message"]

    # Missing project_id
    result = await manage_extensions(mock_context, action="install", extension_id="sk-1")
    data = json.loads(result)
    assert data["success"] is False
    assert "project_id" in data["error"]["message"]


@pytest.mark.asyncio
async def test_manage_extensions_remove(registered_tools, mock_context):
    """Test removing an extension from a project."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": "Extension removed"}

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(
            mock_context,
            action="remove",
            extension_id="sk-1",
            project_id="proj-1",
            system_id="sys-1",
        )

        data = json.loads(result)
        assert data["success"] is True


@pytest.mark.asyncio
async def test_manage_extensions_invalid_action(registered_tools, mock_context):
    """Test that an invalid action returns an error."""
    manage_extensions = registered_tools["manage_extensions"]

    result = await manage_extensions(mock_context, action="bogus")

    data = json.loads(result)
    assert data["success"] is False
    assert data["error"]["type"] == "invalid_action"


@pytest.mark.asyncio
async def test_manage_extensions_sync(registered_tools, mock_context):
    """Test sync calls the project sync endpoint and returns correct field names."""
    manage_extensions = registered_tools["manage_extensions"]

    # POST /api/projects/{project_id}/sync returns sync report
    mock_sync_response = MagicMock()
    mock_sync_response.status_code = 200
    mock_sync_response.json.return_value = {
        "system": {"id": "sys-1", "name": "My Machine", "is_new": True},
        "in_sync": ["memory"],
        "local_changes": [],
        "pending_install": [{"extension_id": "sk-2", "name": "deploy", "content": "---\nname: deploy\n---\n"}],
        "pending_remove": [],
        "unknown_local": [{"name": "new-extension", "content_hash": "ccc"}],
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_sync_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        local_extensions = [
            {"name": "memory", "content_hash": "aaa"},
            {"name": "new-extension", "content_hash": "ccc"},
        ]

        result = await manage_extensions(
            mock_context,
            action="sync",
            local_extensions=local_extensions,
            system_fingerprint="fp-test",
            system_name="My Machine",
            project_id="proj-1",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["system"]["id"] == "sys-1"
        assert data["system"]["is_new"] is True
        assert data["in_sync"] == ["memory"]
        assert len(data["pending_install"]) == 1
        assert data["pending_install"][0]["name"] == "deploy"
        assert len(data["unknown_local"]) == 1
        assert data["unknown_local"][0]["name"] == "new-extension"


@pytest.mark.asyncio
async def test_manage_extensions_sync_missing_params(registered_tools, mock_context):
    """Test sync fails without required parameters."""
    manage_extensions = registered_tools["manage_extensions"]

    # Missing local_extensions
    result = await manage_extensions(mock_context, action="sync", system_fingerprint="fp")
    data = json.loads(result)
    assert data["success"] is False

    # Missing system_fingerprint
    result = await manage_extensions(mock_context, action="sync", local_extensions=[])
    data = json.loads(result)
    assert data["success"] is False

    # Missing project_id
    result = await manage_extensions(mock_context, action="sync", local_extensions=[], system_fingerprint="fp")
    data = json.loads(result)
    assert data["success"] is False


@pytest.mark.asyncio
async def test_manage_extensions_bootstrap_basic(registered_tools, mock_context):
    """Bootstrap returns extension metadata (no content) and registers system."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_extensions_response = MagicMock()
    mock_extensions_response.status_code = 200
    mock_extensions_response.json.return_value = {
        "extensions": [
            {"name": "cortex-memory", "display_name": "Cortex Memory"},
            {"name": "cortex-bootstrap", "display_name": "Cortex Bootstrap"},
        ]
    }

    mock_sync_response = MagicMock()
    mock_sync_response.status_code = 200
    mock_sync_response.json.return_value = {
        "system": {"id": "sys-1", "name": "My Mac", "is_new": True},
        "in_sync": [], "pending_install": [], "pending_remove": [],
        "local_changes": [], "unknown_local": [],
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_extensions_response
        mock_async_client.post.return_value = mock_sync_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(
            mock_context,
            action="bootstrap",
            system_fingerprint="fp-abc",
            system_name="My Mac",
            project_id="proj-1",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert len(data["extensions"]) == 2
        assert data["extensions"][0]["name"] == "cortex-memory"
        assert "content" not in data["extensions"][0], "Bootstrap should not return extension content"
        assert data["system"]["id"] == "sys-1"
        assert data["system"]["is_new"] is True
        assert "Bootstrap complete" in data["message"]


@pytest.mark.asyncio
async def test_manage_extensions_bootstrap_no_project(registered_tools, mock_context):
    """Bootstrap without project_id skips sync call, still returns extensions."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_extensions_response = MagicMock()
    mock_extensions_response.status_code = 200
    mock_extensions_response.json.return_value = {
        "extensions": [{"name": "cortex-memory", "display_name": "Cortex Memory"}]
    }

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_extensions_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(mock_context, action="bootstrap")

        data = json.loads(result)
        assert data["success"] is True
        assert len(data["extensions"]) == 1
        assert data["system"] is None
        mock_async_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_manage_extensions_bootstrap_not_invalid_action(registered_tools, mock_context):
    """'bootstrap' is now a valid action and must NOT return invalid_action error."""
    manage_extensions = registered_tools["manage_extensions"]

    mock_extensions_response = MagicMock()
    mock_extensions_response.status_code = 200
    mock_extensions_response.json.return_value = {"extensions": []}

    with patch("src.mcp_server.features.extensions.extension_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_extensions_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_extensions(mock_context, action="bootstrap")
        data = json.loads(result)
        assert data.get("error", {}).get("type") != "invalid_action"
