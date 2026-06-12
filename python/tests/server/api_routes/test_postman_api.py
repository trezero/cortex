"""Tests for Postman API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_postman_service():
    with patch("src.server.api_routes.postman_api.PostmanService") as MockClass:
        mock_instance = MagicMock()
        MockClass.return_value = mock_instance
        mock_instance.get_sync_mode = AsyncMock(return_value="api")
        mock_instance._get_client = AsyncMock()
        mock_instance.get_or_create_collection = AsyncMock(return_value="col-123")
        mock_instance.upsert_request = AsyncMock()
        mock_instance.upsert_environment = AsyncMock(return_value={})
        yield mock_instance


@pytest.fixture
def client():
    from src.server.main import app
    return TestClient(app)


class TestGetStatus:
    def test_returns_sync_mode(self, client, mock_postman_service):
        mock_postman_service.get_sync_mode = AsyncMock(return_value="git")
        response = client.get("/api/postman/status")
        assert response.status_code == 200
        assert response.json()["sync_mode"] == "git"

    def test_returns_disabled_by_default(self, client, mock_postman_service):
        mock_postman_service.get_sync_mode = AsyncMock(return_value="disabled")
        response = client.get("/api/postman/status")
        assert response.status_code == 200
        assert response.json()["sync_mode"] == "disabled"


class TestCreateCollection:
    def test_creates_collection(self, client, mock_postman_service):
        response = client.post("/api/postman/collections", json={"project_name": "Cortex"})
        assert response.status_code == 200
        assert response.json()["collection_uid"] == "col-123"

    def test_skips_when_not_api_mode(self, client, mock_postman_service):
        mock_postman_service.get_sync_mode = AsyncMock(return_value="git")
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
        response = client.post("/api/postman/environments/sync", json={
            "project_id": "proj-123",
            "system_name": "WIN-DEV-01",
            "env_file_content": "BASE_URL=http://localhost:8181\n# comment\nAPI_KEY=secret123",
        })
        assert response.status_code == 200
        assert response.json()["variables_count"] == 2
