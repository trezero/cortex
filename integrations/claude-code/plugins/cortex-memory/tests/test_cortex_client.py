"""Tests for CortexClient — Cortex HTTP client.

Tests mock httpx to avoid real network calls.
Async tests use @pytest.mark.anyio (pytest-asyncio is NOT installed).
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_config(api_url: str = "http://localhost:8181", project_id: str = "proj-1", machine_id: str = "m-abc") -> dict:
    return {"cortex_api_url": api_url, "project_id": project_id, "machine_id": machine_id}


def _mock_http_client(status_code: int = 200, json_body: object = None):
    """Return a mock httpx.AsyncClient context manager with a preset response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_body or {}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ── Config loading ─────────────────────────────────────────────────────────────


def test_loads_config_from_explicit_path(tmp_path):
    """Config is loaded from the path passed to the constructor."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    client = CortexClient(config_path=str(config_file))
    assert client.api_url == "http://localhost:8181"
    assert client.project_id == "proj-1"
    assert client.machine_id == "m-abc"


def test_loads_config_from_local_claude_dir(tmp_path, monkeypatch):
    """Config is found in .claude/cortex-config.json relative to cwd."""
    from src.cortex_client import CortexClient

    local_dir = tmp_path / ".claude"
    local_dir.mkdir()
    (local_dir / "cortex-config.json").write_text(json.dumps(_make_config(project_id="local-proj")))

    monkeypatch.chdir(tmp_path)
    client = CortexClient()
    assert client.project_id == "local-proj"


def test_falls_back_to_home_claude_dir(tmp_path, monkeypatch):
    """Falls back to ~/.claude/cortex-config.json when local file not found."""
    from src.cortex_client import CortexClient

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    home_claude = home_dir / ".claude"
    home_claude.mkdir()
    (home_claude / "cortex-config.json").write_text(json.dumps(_make_config(project_id="global-proj")))

    # Make cwd a directory without a local .claude/cortex-config.json
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    monkeypatch.setenv("HOME", str(home_dir))

    client = CortexClient()
    assert client.project_id == "global-proj"


def test_returns_empty_config_when_no_file_found(tmp_path, monkeypatch):
    """Returns empty dict (not an error) when no config file exists."""
    from src.cortex_client import CortexClient

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.chdir(work_dir)
    monkeypatch.setenv("HOME", str(home_dir))

    client = CortexClient()
    assert client.api_url == ""
    assert client.project_id == ""
    assert client.machine_id == ""


# ── is_configured ──────────────────────────────────────────────────────────────


def test_is_configured_true_when_all_required_fields_present(tmp_path):
    """is_configured returns True when cortex_api_url, project_id, machine_id are set."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    client = CortexClient(config_path=str(config_file))
    assert client.is_configured() is True


def test_is_configured_false_when_no_config(tmp_path, monkeypatch):
    """is_configured returns False when no config file is found."""
    from src.cortex_client import CortexClient

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.chdir(work_dir)
    monkeypatch.setenv("HOME", str(home_dir))

    client = CortexClient()
    assert client.is_configured() is False


def test_is_configured_false_when_missing_api_url(tmp_path):
    """is_configured returns False when cortex_api_url is missing."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps({"project_id": "p", "machine_id": "m"}))

    client = CortexClient(config_path=str(config_file))
    assert client.is_configured() is False


# ── flush_session ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_flush_session_posts_to_api_sessions(tmp_path):
    """flush_session POSTs session_data to /api/sessions."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    mock_client = _mock_http_client(status_code=200, json_body={"id": "sess-1"})

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.flush_session({"session_id": "sess-1", "summary": "Did work"})

    assert result is True
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "/api/sessions" in call_args[0][0]


@pytest.mark.anyio
async def test_flush_session_returns_false_on_http_error(tmp_path):
    """flush_session returns False when the server responds with an error."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    mock_client = _mock_http_client(status_code=500, json_body={"error": "server error"})

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.flush_session({"session_id": "sess-1"})

    assert result is False


@pytest.mark.anyio
async def test_flush_session_returns_false_when_not_configured(tmp_path, monkeypatch):
    """flush_session returns False immediately when not configured."""
    from src.cortex_client import CortexClient

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.chdir(work_dir)
    monkeypatch.setenv("HOME", str(home_dir))

    client = CortexClient()
    result = await client.flush_session({"session_id": "sess-1"})
    assert result is False


# ── get_recent_sessions ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_recent_sessions_queries_with_project_and_limit(tmp_path):
    """get_recent_sessions GETs /api/sessions with project_id and limit params."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    sessions = [{"session_id": "s1"}, {"session_id": "s2"}]
    mock_client = _mock_http_client(status_code=200, json_body={"sessions": sessions})

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_recent_sessions(limit=3)

    assert result == sessions
    call_kwargs = mock_client.get.call_args[1]
    assert call_kwargs["params"]["limit"] == 3
    assert call_kwargs["params"]["project_id"] == "proj-1"


@pytest.mark.anyio
async def test_get_recent_sessions_returns_empty_list_on_error(tmp_path):
    """get_recent_sessions returns [] when the server responds with an error."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    mock_client = _mock_http_client(status_code=500)

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_recent_sessions()

    assert result == []


# ── get_active_tasks ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_active_tasks_queries_correct_endpoint(tmp_path):
    """get_active_tasks GETs /api/projects/{id}/tasks with status filter."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    tasks = [{"id": "t1", "status": "doing"}]
    mock_client = _mock_http_client(status_code=200, json_body={"tasks": tasks})

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_active_tasks(limit=5)

    assert result == tasks
    call_url = mock_client.get.call_args[0][0]
    assert "proj-1" in call_url
    assert "tasks" in call_url
    call_kwargs = mock_client.get.call_args[1]
    assert "status" in call_kwargs["params"]


@pytest.mark.anyio
async def test_get_active_tasks_returns_empty_list_when_not_configured(tmp_path, monkeypatch):
    """get_active_tasks returns [] when not configured (no project_id)."""
    from src.cortex_client import CortexClient

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.chdir(work_dir)
    monkeypatch.setenv("HOME", str(home_dir))

    client = CortexClient()
    result = await client.get_active_tasks()
    assert result == []


# ── get_knowledge_status ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_knowledge_status_queries_sources_with_project(tmp_path):
    """get_knowledge_status GETs /api/knowledge/sources filtered by project_id."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    sources_data = {"sources": [{"id": "src-1", "name": "Cortex Docs"}]}
    mock_client = _mock_http_client(status_code=200, json_body=sources_data)

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_knowledge_status()

    assert result == sources_data
    call_url = mock_client.get.call_args[0][0]
    assert "knowledge/sources" in call_url


@pytest.mark.anyio
async def test_get_knowledge_status_returns_empty_dict_on_error(tmp_path):
    """get_knowledge_status returns {} on HTTP error."""
    from src.cortex_client import CortexClient

    config_file = tmp_path / "cortex-config.json"
    config_file.write_text(json.dumps(_make_config()))

    mock_client = _mock_http_client(status_code=404)

    client = CortexClient(config_path=str(config_file))
    with patch("src.cortex_client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_knowledge_status()

    assert result == {}
