"""Authentication and disclosure tests for credential-management routes."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.server.main import app

TOKEN = "test-cortex-settings-token-with-32-characters"


def test_credential_routes_reject_missing_or_invalid_admin_token():
    client = TestClient(app)

    assert client.get("/api/credentials").status_code == 401
    assert client.get("/api/credentials", headers={"X-Cortex-Settings-Token": "invalid"}).status_code == 401
    assert client.get("/internal/credentials/agents").status_code == 401


def test_browser_preferences_never_expose_encrypted_records():
    safe = type(
        "Credential",
        (),
        {
            "key": "PROJECTS_ENABLED",
            "value": "true",
            "is_encrypted": False,
            "category": "features",
            "description": "Project UI",
        },
    )()
    secret = type(
        "Credential",
        (),
        {
            "key": "OPENAI_API_KEY",
            "value": None,
            "is_encrypted": True,
            "category": "api_keys",
            "description": "Provider secret",
        },
    )()
    with patch(
        "src.server.api_routes.settings_api.credential_service.list_all_credentials",
        new=AsyncMock(return_value=[safe, secret]),
    ):
        response = TestClient(app).get("/api/preferences")

    assert response.status_code == 200
    assert response.json() == [
        {
            "key": "PROJECTS_ENABLED",
            "value": "true",
            "is_encrypted": False,
            "category": "features",
            "description": "Project UI",
        }
    ]
    assert "OPENAI_API_KEY" not in response.text


def test_browser_preference_write_rejects_secret_categories():
    response = TestClient(app).post(
        "/api/preferences",
        json={
            "key": "OPENAI_API_KEY",
            "value": "must-not-be-stored",
            "is_encrypted": True,
            "category": "api_keys",
        },
    )

    assert response.status_code == 400
    assert "must-not-be-stored" not in response.text


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
