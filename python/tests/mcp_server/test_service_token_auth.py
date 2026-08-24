"""Security boundary tests for the Cortex streamable HTTP MCP endpoint."""

import json
import os
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from src.mcp_server.mcp_server import CortexServiceTokenVerifier, mcp

TOKEN = "test-cortex-service-token-with-32-characters"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "cortex-auth-test", "version": "1.0"},
    },
}


@pytest.fixture(scope="module")
def authenticated_mcp_client():
    with TestClient(mcp.streamable_http_app()) as client:
        yield client


def test_verifier_accepts_only_the_configured_token():
    import asyncio

    verifier = CortexServiceTokenVerifier()
    accepted = asyncio.run(verifier.verify_token(TOKEN))
    rejected = asyncio.run(verifier.verify_token("x" * 48))

    assert accepted is not None
    assert accepted.scopes == ["cortex:use"]
    assert rejected is None


def test_server_fails_fast_without_auth_token():
    environment = os.environ.copy()
    environment.pop("CORTEX_MCP_AUTH_TOKEN", None)
    result = subprocess.run(
        [sys.executable, "-c", "import src.mcp_server.mcp_server"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode != 0
    assert "CORTEX_MCP_AUTH_TOKEN is required" in result.stderr


def test_mcp_initialize_rejects_missing_token(authenticated_mcp_client):
    response = authenticated_mcp_client.post("/mcp", json=INITIALIZE)

    assert response.status_code in {401, 403}
    assert "mcp-session-id" not in response.headers


def test_mcp_initialize_rejects_invalid_helper_header(authenticated_mcp_client):
    response = authenticated_mcp_client.post(
        "/mcp",
        json=INITIALIZE,
        headers={"X-Cortex-Service-Token": "not-the-configured-token"},
    )

    assert response.status_code in {401, 403}
    assert "mcp-session-id" not in response.headers


def test_mcp_initialize_accepts_bearer_token(authenticated_mcp_client):
    response = authenticated_mcp_client.post(
        "/mcp",
        content=json.dumps(INITIALIZE),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200


def test_mcp_initialize_accepts_codex_helper_header(authenticated_mcp_client):
    response = authenticated_mcp_client.post(
        "/mcp",
        content=json.dumps(INITIALIZE),
        headers={
            "X-Cortex-Service-Token": TOKEN,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200


def test_health_remains_available_without_credentials(authenticated_mcp_client):
    response = authenticated_mcp_client.get("/health")

    assert response.status_code == 200
    assert response.json()["success"] is True
