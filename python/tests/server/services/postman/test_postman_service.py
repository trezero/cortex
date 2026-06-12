"""Tests for PostmanService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.postman.postman_service import PostmanService


@pytest.fixture
def mock_credential_service():
    with patch("src.server.services.postman.postman_service.credential_service") as mock:
        async def fake_get_credential(key, **kwargs):
            return {
                "POSTMAN_API_KEY": "PMAK-test-key-123",
                "POSTMAN_WORKSPACE_ID": "workspace-123",
                "POSTMAN_SYNC_MODE": "api",
            }.get(key)

        mock.get_credential = AsyncMock(side_effect=fake_get_credential)
        yield mock


@pytest.fixture
def service(mock_credential_service):
    return PostmanService()


class TestGetSyncMode:
    @pytest.mark.asyncio
    async def test_returns_api_when_configured(self, mock_credential_service):
        svc = PostmanService()
        assert await svc.get_sync_mode() == "api"

    @pytest.mark.asyncio
    async def test_returns_disabled_when_not_set(self):
        with patch("src.server.services.postman.postman_service.credential_service") as mock:
            mock.get_credential = AsyncMock(return_value=None)
            svc = PostmanService()
            assert await svc.get_sync_mode() == "disabled"

    @pytest.mark.asyncio
    async def test_returns_disabled_for_invalid_mode(self):
        with patch("src.server.services.postman.postman_service.credential_service") as mock:
            mock.get_credential = AsyncMock(return_value="invalid_mode")
            svc = PostmanService()
            assert await svc.get_sync_mode() == "disabled"


class TestGetClient:
    @pytest.mark.asyncio
    async def test_raises_when_no_api_key(self):
        with patch("src.server.services.postman.postman_service.credential_service") as mock:
            mock.get_credential = AsyncMock(return_value=None)
            svc = PostmanService()
            with pytest.raises(ValueError, match="POSTMAN_API_KEY not configured"):
                await svc._get_client()


class TestGetOrCreateCollection:
    @pytest.mark.asyncio
    async def test_returns_existing_collection(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.list_collections.return_value = [
                {"name": "Cortex", "uid": "col-123"}
            ]
            mock_client_fn.return_value = mock_client

            uid = await service.get_or_create_collection("Cortex")
            assert uid == "col-123"
            mock_client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_when_not_found(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.list_collections.return_value = []
            mock_client.create_collection.return_value = {"uid": "col-new"}
            mock_client_fn.return_value = mock_client

            uid = await service.get_or_create_collection("Cortex")
            assert uid == "col-new"
            mock_client.create_collection.assert_called_once()


class TestUpsertRequest:
    @pytest.mark.asyncio
    async def test_creates_folder_and_adds_request(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = {
                "collection": {"info": {"name": "Test"}, "item": []}
            }
            mock_client.update_collection.return_value = {"collection": {"uid": "col-123"}}
            mock_client_fn.return_value = mock_client

            await service.upsert_request("col-123", "Projects", {
                "name": "Create Project",
                "method": "POST",
                "url": "{{base_url}}/api/projects",
            })

            mock_client.update_collection.assert_called_once()
            updated = mock_client.update_collection.call_args[0][1]
            assert len(updated["collection"]["item"]) == 1
            assert updated["collection"]["item"][0]["name"] == "Projects"

    @pytest.mark.asyncio
    async def test_updates_existing_request(self, service):
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

            await service.upsert_request("col-123", "Projects", {
                "name": "Create Project",
                "method": "POST",
                "url": "{{base_url}}/api/projects",
            })

            updated = mock_client.update_collection.call_args[0][1]
            folder = updated["collection"]["item"][0]
            assert len(folder["item"]) == 1
            assert folder["item"][0]["request"]["url"] == {"raw": "{{base_url}}/api/projects"}

    @pytest.mark.asyncio
    async def test_adds_test_script_as_event(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = {
                "collection": {"info": {"name": "Test"}, "item": []}
            }
            mock_client.update_collection.return_value = {"collection": {"uid": "col-123"}}
            mock_client_fn.return_value = mock_client

            await service.upsert_request("col-123", "Projects", {
                "name": "Check Status",
                "method": "GET",
                "url": "{{base_url}}/api/health",
                "test_script": "pm.test('status 200', function() {\n  pm.response.to.have.status(200);\n});",
            })

            updated = mock_client.update_collection.call_args[0][1]
            request_item = updated["collection"]["item"][0]["item"][0]
            assert "event" in request_item
            assert request_item["event"][0]["listen"] == "test"
            assert len(request_item["event"][0]["script"]["exec"]) == 3


class TestUpsertEnvironment:
    @pytest.mark.asyncio
    async def test_creates_new_environment(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.list_environments.return_value = []
            mock_client.create_environment.return_value = {"uid": "env-new"}
            mock_client_fn.return_value = mock_client

            result = await service.upsert_environment("Dev", {"base_url": "http://localhost:8181"})
            assert result == {"uid": "env-new"}
            mock_client.create_environment.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_environment(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.list_environments.return_value = [{"name": "Dev", "uid": "env-123"}]
            mock_client.update_environment.return_value = {"uid": "env-123"}
            mock_client_fn.return_value = mock_client

            result = await service.upsert_environment("Dev", {"base_url": "http://localhost:8181"})
            assert result == {"uid": "env-123"}
            mock_client.update_environment.assert_called_once()
            mock_client.create_environment.assert_not_called()


class TestListCollectionStructure:
    @pytest.mark.asyncio
    async def test_returns_folder_request_tree(self, service):
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

            structure = await service.list_collection_structure("col-123")
            assert "Projects" in structure
            assert len(structure["Projects"]) == 2
            assert structure["Projects"][0]["name"] == "Create Project"

    @pytest.mark.asyncio
    async def test_handles_url_as_dict(self, service):
        with patch.object(service, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = {
                "collection": {
                    "info": {"name": "Test"},
                    "item": [{
                        "name": "Auth",
                        "item": [
                            {"name": "Login", "request": {"method": "POST", "url": {"raw": "/api/login"}}},
                        ]
                    }]
                }
            }
            mock_client_fn.return_value = mock_client

            structure = await service.list_collection_structure("col-123")
            assert structure["Auth"][0]["url"] == "/api/login"


class TestBuildPostmanRequest:
    def test_basic_get_request(self):
        svc = PostmanService()
        result = svc._build_postman_request({
            "method": "GET",
            "url": "/api/projects",
        })
        assert result["method"] == "GET"
        assert result["url"] == {"raw": "/api/projects"}
        assert result["header"] == []

    def test_post_request_with_body_and_headers(self):
        svc = PostmanService()
        result = svc._build_postman_request({
            "method": "POST",
            "url": "/api/projects",
            "headers": {"Authorization": "Bearer {{token}}"},
            "body": {"name": "Test Project"},
        })
        assert result["method"] == "POST"
        assert result["header"] == [{"key": "Authorization", "value": "Bearer {{token}}"}]
        assert result["body"]["mode"] == "raw"
        assert "Test Project" in result["body"]["raw"]
        assert result["body"]["options"]["raw"]["language"] == "json"

    def test_defaults_to_get_method(self):
        svc = PostmanService()
        result = svc._build_postman_request({"url": "/api/health"})
        assert result["method"] == "GET"
