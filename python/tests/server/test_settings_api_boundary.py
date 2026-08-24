"""Authentication and disclosure tests for credential-management routes."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.server.main import app

TOKEN = "test-cortex-settings-token-with-32-characters"


def test_credential_routes_reject_missing_or_invalid_admin_token():
    client = TestClient(app)

    assert client.get("/api/credentials").status_code == 401
    assert client.get("/api/credentials", headers={"X-Cortex-Settings-Token": "invalid"}).status_code == 401


def test_status_check_never_returns_decrypted_value():
    with patch(
        "src.server.api_routes.settings_api.credential_service.get_credential",
        new=AsyncMock(return_value="super-secret-provider-value"),
    ):
        response = TestClient(app).post(
            "/api/credentials/status-check",
            headers={"X-Cortex-Settings-Token": TOKEN},
            json={"keys": ["OPENAI_API_KEY"]},
        )

    assert response.status_code == 200
    assert response.json()["OPENAI_API_KEY"] == {
        "key": "OPENAI_API_KEY",
        "has_value": True,
    }
    assert "super-secret-provider-value" not in response.text
