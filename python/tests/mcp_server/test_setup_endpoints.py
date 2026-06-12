"""Tests for the cortex-setup download endpoints."""
import io
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient


@pytest.fixture
def mcp_test_client():
    """TestClient using the FastMCP app directly."""
    with patch.dict("os.environ", {"CORTEX_MCP_PORT": "8051"}):
        from src.mcp_server.mcp_server import mcp
        return TestClient(mcp.streamable_http_app())


def test_cortex_setup_sh_returns_200(mcp_test_client):
    with patch("src.mcp_server.mcp_server._render_setup_sh", return_value="#!/bin/bash\nCORTEX_SERVER=http://test"):
        response = mcp_test_client.get("/cortex-setup.sh")
        assert response.status_code == 200


def test_cortex_setup_sh_content_type_is_plain_text(mcp_test_client):
    with patch("src.mcp_server.mcp_server._render_setup_sh", return_value="#!/bin/bash\nCORTEX_SERVER=http://test"):
        response = mcp_test_client.get("/cortex-setup.sh")
        assert response.headers["content-type"].startswith("text/plain")


def test_cortex_setup_bat_returns_200(mcp_test_client):
    with patch("src.mcp_server.mcp_server._render_setup_bat", return_value="@echo off\nset CORTEX_SERVER=http://test"):
        response = mcp_test_client.get("/cortex-setup.bat")
        assert response.status_code == 200


def test_cortex_setup_md_returns_200(mcp_test_client):
    with patch("src.mcp_server.mcp_server._render_setup_md", return_value="# Cortex Setup\n\ncortex-setup content"):
        response = mcp_test_client.get("/cortex-setup.md")
        assert response.status_code == 200


def test_cortex_setup_sh_contains_server_url(mcp_test_client):
    with patch("src.mcp_server.mcp_server._render_setup_sh", return_value="#!/bin/bash\nCORTEX_MCP_URL=http://testserver"):
        response = mcp_test_client.get("/cortex-setup.sh")
        assert "CORTEX_MCP_URL=" in response.text


def test_extensions_tarball_returns_valid_gzip(mcp_test_client):
    """Extensions tarball endpoint returns a valid tar.gz with SKILL.md files."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "extensions": [
            {"name": "test-ext", "content": "---\nname: test-ext\n---\n# Test Extension"},
            {"name": "another-ext", "content": "---\nname: another-ext\n---\n# Another"},
        ]
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = mock_response

    with (
        patch("httpx.AsyncClient") as mock_client,
        patch("src.server.config.service_discovery.get_api_url", return_value="http://localhost:8181"),
    ):
        mock_client.return_value.__aenter__.return_value = mock_client_instance
        response = mcp_test_client.get("/cortex-setup/extensions.tar.gz")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"

    buf = io.BytesIO(response.content)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        names = tar.getnames()
        assert "test-ext/SKILL.md" in names
        assert "another-ext/SKILL.md" in names
        content = tar.extractfile("test-ext/SKILL.md").read().decode()
        assert "# Test Extension" in content


def test_extensions_tarball_skips_empty_content(mcp_test_client):
    """Extensions with empty content are excluded from the tarball."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "extensions": [
            {"name": "has-content", "content": "# Real content"},
            {"name": "no-content", "content": ""},
            {"name": "", "content": "# Nameless"},
        ]
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = mock_response

    with (
        patch("httpx.AsyncClient") as mock_client,
        patch("src.server.config.service_discovery.get_api_url", return_value="http://localhost:8181"),
    ):
        mock_client.return_value.__aenter__.return_value = mock_client_instance
        response = mcp_test_client.get("/cortex-setup/extensions.tar.gz")

    assert response.status_code == 200
    buf = io.BytesIO(response.content)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        names = tar.getnames()
        assert "has-content/SKILL.md" in names
        assert len(names) == 1


def test_extensions_tarball_api_unreachable(mcp_test_client):
    """Returns 502 when the API server is unreachable."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")

    with (
        patch("httpx.AsyncClient") as mock_client,
        patch("src.server.config.service_discovery.get_api_url", return_value="http://localhost:8181"),
    ):
        mock_client.return_value.__aenter__.return_value = mock_client_instance
        response = mcp_test_client.get("/cortex-setup/extensions.tar.gz")

    assert response.status_code == 502
