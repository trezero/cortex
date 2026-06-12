"""Unit tests for materialization API endpoints."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.server.models.materialization import MaterializationRecord, MaterializationResult

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_record(**overrides) -> MaterializationRecord:
    defaults = {
        "id": "mat-1",
        "project_id": "proj-1",
        "project_path": "/tmp/proj",
        "topic": "auth patterns",
        "filename": "auth-patterns.md",
        "file_path": ".cortex/knowledge/auth-patterns.md",
        "source_ids": ["src-1"],
        "original_urls": ["https://example.com"],
        "synthesis_model": "gpt-4o-mini",
        "word_count": 500,
        "status": "active",
        "access_count": 0,
        "last_accessed_at": None,
        "materialized_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "metadata": {},
    }
    defaults.update(overrides)
    return MaterializationRecord(**defaults)


# ── POST /api/materialization/execute ────────────────────────────────────────


def test_execute_materialization_success():
    """POST /execute calls service.materialize and returns structured result."""
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.materialize = AsyncMock(
            return_value=MaterializationResult(
                success=True,
                file_path=".cortex/knowledge/auth-patterns.md",
                filename="auth-patterns.md",
                word_count=500,
                summary="Auth overview",
                materialization_id="mat-1",
            )
        )

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import execute_materialization
            from src.server.models.materialization import MaterializationRequest

            req = MaterializationRequest(
                topic="auth patterns",
                project_id="proj-1",
                project_path="/tmp/proj",
            )
            result = asyncio.run(execute_materialization(req))

        assert result["success"] is True
        assert result["filename"] == "auth-patterns.md"
        assert result["word_count"] == 500
        assert result["materialization_id"] == "mat-1"
        assert "progress_id" in result
        instance.materialize.assert_called_once()


def test_execute_materialization_failure():
    """POST /execute returns failure info when service reports no content."""
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.materialize = AsyncMock(
            return_value=MaterializationResult(success=False, reason="no_relevant_content")
        )

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import execute_materialization
            from src.server.models.materialization import MaterializationRequest

            req = MaterializationRequest(
                topic="obscure topic",
                project_id="proj-1",
                project_path="/tmp/proj",
            )
            result = asyncio.run(execute_materialization(req))

        assert result["success"] is False
        assert result["reason"] == "no_relevant_content"


# ── GET /api/materialization/history ─────────────────────────────────────────


def test_list_materializations_returns_items():
    """GET /history returns items list with total count."""
    record = _make_record()
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.list_materializations = AsyncMock(return_value=[record])

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import list_materializations

            result = asyncio.run(list_materializations(project_id="proj-1", status=None))

        assert result["total"] == 1
        assert result["items"][0]["id"] == "mat-1"
        instance.list_materializations.assert_called_once_with(project_id="proj-1", status=None)


def test_list_materializations_empty():
    """GET /history with no records returns empty list."""
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.list_materializations = AsyncMock(return_value=[])

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import list_materializations

            result = asyncio.run(list_materializations(project_id=None, status=None))

        assert result["total"] == 0
        assert result["items"] == []


# ── GET /api/materialization/{materialization_id} ────────────────────────────


def test_get_materialization_success():
    """GET /{id} returns the record when found."""
    record = _make_record()
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_record = AsyncMock(return_value=record)

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import get_materialization

            result = asyncio.run(get_materialization("mat-1"))

        assert result["id"] == "mat-1"
        assert result["topic"] == "auth patterns"
        instance.get_record.assert_called_once_with("mat-1")


def test_get_materialization_not_found_raises_404():
    """GET /{id} raises 404 when record doesn't exist."""
    from fastapi import HTTPException

    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_record = AsyncMock(return_value=None)

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import get_materialization

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_materialization("bad-id"))

        assert exc_info.value.status_code == 404


# ── PUT /api/materialization/{id}/access ─────────────────────────────────────


def test_mark_accessed_success():
    """PUT /{id}/access calls mark_accessed and returns success."""
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.mark_accessed = AsyncMock()

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import mark_accessed

            result = asyncio.run(mark_accessed("mat-1"))

        assert result["success"] is True
        instance.mark_accessed.assert_called_once_with("mat-1")


# ── PUT /api/materialization/{id}/status ─────────────────────────────────────


def test_update_status_valid():
    """PUT /{id}/status with valid status calls service and returns success."""
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.update_status = AsyncMock()

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import update_status

            result = asyncio.run(update_status("mat-1", "archived"))

        assert result["success"] is True
        instance.update_status.assert_called_once_with("mat-1", "archived")


def test_update_status_invalid_raises_400():
    """PUT /{id}/status with invalid status raises 400."""
    from fastapi import HTTPException

    with patch("src.server.api_routes.materialization_api.get_supabase_client"):
        from src.server.api_routes.materialization_api import update_status

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(update_status("mat-1", "invalid_status"))

    assert exc_info.value.status_code == 400


# ── DELETE /api/materialization/{id} ─────────────────────────────────────────


def test_delete_materialization_success():
    """DELETE /{id} removes file, updates index, and deletes record."""
    record = _make_record()
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_record = AsyncMock(return_value=record)
        instance.delete_record = AsyncMock()

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            with patch("src.server.services.knowledge.indexer_service.IndexerService") as MockIndexer:
                indexer_instance = MockIndexer.return_value
                indexer_instance.remove_file = AsyncMock()
                indexer_instance.update_index = AsyncMock()

                from src.server.api_routes.materialization_api import delete_materialization

                result = asyncio.run(delete_materialization("mat-1"))

        assert result["success"] is True
        instance.get_record.assert_called_once_with("mat-1")
        indexer_instance.remove_file.assert_called_once_with(record.project_path, record.filename)
        indexer_instance.update_index.assert_called_once_with(record.project_path)
        instance.delete_record.assert_called_once_with("mat-1")


def test_delete_materialization_not_found_raises_404():
    """DELETE /{id} for missing record raises 404."""
    from fastapi import HTTPException

    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_record = AsyncMock(return_value=None)

        with patch("src.server.api_routes.materialization_api.get_supabase_client"):
            from src.server.api_routes.materialization_api import delete_materialization

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(delete_materialization("bad-id"))

        assert exc_info.value.status_code == 404
