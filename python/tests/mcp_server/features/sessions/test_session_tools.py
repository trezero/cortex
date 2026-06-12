"""Unit tests for session memory MCP tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import Context

from src.mcp_server.features.sessions.session_tools import register_session_tools


@pytest.fixture
def mock_mcp():
    """Create a mock MCP server that captures registered tools."""
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
    return MagicMock(spec=Context)


@pytest.fixture
def registered_tools(mock_mcp):
    register_session_tools(mock_mcp)
    return mock_mcp._tools


# ── cortex_search_sessions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_sessions_returns_results(registered_tools, mock_context):
    """cortex_search_sessions returns matching sessions as JSON."""
    search_sessions = registered_tools["cortex_search_sessions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "sessions": [
            {"session_id": "s1", "summary": "Fixed auth bug"},
        ]
    }

    with patch("src.mcp_server.features.sessions.session_tools.httpx.AsyncClient") as mock_client:
        mock_async = AsyncMock()
        mock_async.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async

        result = await search_sessions(mock_context, query="auth bug")

    data = json.loads(result)
    assert data["success"] is True
    assert data["count"] == 1
    assert data["sessions"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_search_sessions_with_project_filter(registered_tools, mock_context):
    """cortex_search_sessions passes project_id filter to API."""
    search_sessions = registered_tools["cortex_search_sessions"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"sessions": []}

    with patch("src.mcp_server.features.sessions.session_tools.httpx.AsyncClient") as mock_client:
        mock_async = AsyncMock()
        mock_async.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async

        result = await search_sessions(mock_context, query="deploy", project_id="proj-1", limit=5)

    data = json.loads(result)
    assert data["success"] is True

    call_args = mock_async.get.call_args
    assert "q=deploy" in call_args[0][0]
    assert "project_id=proj-1" in call_args[0][0]
    assert "limit=5" in call_args[0][0]


@pytest.mark.asyncio
async def test_search_sessions_api_error(registered_tools, mock_context):
    """cortex_search_sessions handles API errors gracefully."""
    search_sessions = registered_tools["cortex_search_sessions"]

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("src.mcp_server.features.sessions.session_tools.httpx.AsyncClient") as mock_client:
        mock_async = AsyncMock()
        mock_async.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async

        result = await search_sessions(mock_context, query="something")

    data = json.loads(result)
    assert data["success"] is False


# ── cortex_get_session ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_session_returns_session_with_observations(registered_tools, mock_context):
    """cortex_get_session returns session and observations."""
    get_session = registered_tools["cortex_get_session"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "session": {"session_id": "sess-1", "summary": "Did work"},
        "observations": [{"type": "bugfix", "title": "Fixed null check"}],
    }

    with patch("src.mcp_server.features.sessions.session_tools.httpx.AsyncClient") as mock_client:
        mock_async = AsyncMock()
        mock_async.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async

        result = await get_session(mock_context, session_id="sess-1")

    data = json.loads(result)
    assert data["success"] is True
    assert data["session"]["session_id"] == "sess-1"
    assert len(data["observations"]) == 1


@pytest.mark.asyncio
async def test_get_session_not_found(registered_tools, mock_context):
    """cortex_get_session returns error for missing session."""
    get_session = registered_tools["cortex_get_session"]

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch("src.mcp_server.features.sessions.session_tools.httpx.AsyncClient") as mock_client:
        mock_async = AsyncMock()
        mock_async.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_async

        result = await get_session(mock_context, session_id="bad-id")

    data = json.loads(result)
    assert data["success"] is False
