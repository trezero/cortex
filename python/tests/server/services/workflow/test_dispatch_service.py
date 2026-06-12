"""Tests for DispatchService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.workflow.dispatch_service import DispatchService


SAMPLE_YAML = """name: test-workflow
nodes:
  - id: step-one
    command: create-branch
  - id: step-two
    command: planning
    depends_on: [step-one]
"""


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return DispatchService(supabase_client=mock_supabase)


class TestCreateRun:
    def test_creates_run_record(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "wr_1", "status": "pending", "definition_id": "def_1"}
        ]
        success, result = service.create_run(
            definition_id="def_1",
            project_id="proj_1",
            backend_id="be_1",
            triggered_by="user",
            trigger_context={"user_request": "test"},
        )
        assert success is True
        assert result["run"]["id"] == "wr_1"


class TestCreateNodes:
    def test_creates_node_records_and_returns_map(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "n1", "node_id": "step-one"},
            {"id": "n2", "node_id": "step-two"},
        ]
        success, result = service.create_nodes_for_run("wr_1", SAMPLE_YAML)
        assert success is True
        assert "step-one" in result["node_id_map"]
        assert "step-two" in result["node_id_map"]
        assert len(result["node_id_map"]) == 2


class TestDispatchToBackend:
    @pytest.mark.asyncio
    async def test_posts_to_backend_url(self, service):
        backend = {"id": "be_1", "base_url": "http://agent:3000", "auth_token_hash": "x", "name": "test-agent"}
        with patch("src.server.services.workflow.dispatch_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = MagicMock(status_code=200, json=lambda: {"accepted": True})
            mock_client_cls.return_value = mock_client

            success, result = await service.dispatch_to_backend(
                workflow_run_id="wr_1",
                yaml_content=SAMPLE_YAML,
                backend=backend,
                node_id_map={"step-one": "n1", "step-two": "n2"},
                trigger_context={"user_request": "test"},
                callback_url="http://cortex:8181/api/workflows",
            )
            assert success is True
            mock_client.post.assert_called_once()
            call_url = mock_client.post.call_args[0][0]
            assert "cortex/workflows/execute" in call_url
