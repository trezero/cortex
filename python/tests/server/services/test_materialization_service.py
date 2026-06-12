"""Tests for MaterializationService DB operations."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.server.services.knowledge.materialization_service import MaterializationService


@pytest.fixture
def mock_supabase():
    client = MagicMock()

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.in_.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        return builder

    client.table.side_effect = _table
    return client


@pytest.fixture
def service(mock_supabase):
    return MaterializationService(supabase_client=mock_supabase)


# ── check_existing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_existing_not_found(service, mock_supabase):
    """Returns None when no matching record exists."""
    result = await service.check_existing(topic="React hooks", project_id="proj-1")
    assert result is None


@pytest.mark.asyncio
async def test_check_existing_found(service, mock_supabase):
    """Returns a MaterializationRecord when a matching record exists."""
    now = datetime.now(UTC).isoformat()
    record_data = {
        "id": "mat-1",
        "project_id": "proj-1",
        "project_path": "/home/user/project",
        "topic": "React hooks",
        "filename": "react-hooks.md",
        "file_path": "/home/user/project/.cortex/knowledge/react-hooks.md",
        "source_ids": ["src-1"],
        "original_urls": ["https://react.dev/hooks"],
        "synthesis_model": "claude-sonnet-4-20250514",
        "word_count": 1500,
        "status": "active",
        "access_count": 3,
        "last_accessed_at": now,
        "materialized_at": now,
        "updated_at": now,
        "metadata": {},
    }

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.in_.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[record_data])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.check_existing(topic="React hooks", project_id="proj-1")
    assert result is not None
    assert result.id == "mat-1"
    assert result.topic == "React hooks"
    assert result.status == "active"
    assert result.word_count == 1500


# ── list_materializations ───────────────────────────────────────


@pytest.mark.asyncio
async def test_list_materializations_empty(service):
    """Returns empty list when no records exist."""
    result = await service.list_materializations()
    assert result == []


@pytest.mark.asyncio
async def test_list_materializations_with_project_filter(service, mock_supabase):
    """Applies project_id filter when provided."""
    now = datetime.now(UTC).isoformat()
    record_data = {
        "id": "mat-1",
        "project_id": "proj-1",
        "project_path": "/home/user/project",
        "topic": "Auth patterns",
        "filename": "auth-patterns.md",
        "file_path": "/home/user/project/.cortex/knowledge/auth-patterns.md",
        "source_ids": [],
        "original_urls": [],
        "synthesis_model": None,
        "word_count": 800,
        "status": "active",
        "access_count": 0,
        "last_accessed_at": None,
        "materialized_at": now,
        "updated_at": now,
        "metadata": {},
    }

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.in_.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[record_data])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.list_materializations(project_id="proj-1")
    assert len(result) == 1
    assert result[0].project_id == "proj-1"


@pytest.mark.asyncio
async def test_list_materializations_with_status_filter(service, mock_supabase):
    """Applies status filter when provided."""
    now = datetime.now(UTC).isoformat()

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.in_.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[{
            "id": "mat-2",
            "project_id": "proj-1",
            "project_path": "/tmp/proj",
            "topic": "stale topic",
            "filename": "stale.md",
            "file_path": "/tmp/proj/.cortex/knowledge/stale.md",
            "source_ids": [],
            "original_urls": [],
            "synthesis_model": None,
            "word_count": 200,
            "status": "stale",
            "access_count": 0,
            "last_accessed_at": None,
            "materialized_at": now,
            "updated_at": now,
            "metadata": {},
        }])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.list_materializations(status="stale")
    assert len(result) == 1
    assert result[0].status == "stale"


# ── create_record ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_record(service, mock_supabase):
    """Creates a record and returns the generated ID."""

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[{"id": "new-mat-id"}])
        return builder

    mock_supabase.table.side_effect = _table

    record_id = await service.create_record(
        project_id="proj-1",
        project_path="/home/user/project",
        topic="FastAPI middleware",
        filename="fastapi-middleware.md",
        file_path="/home/user/project/.cortex/knowledge/fastapi-middleware.md",
        source_ids=["src-1", "src-2"],
        original_urls=["https://fastapi.tiangolo.com/tutorial/middleware/"],
        synthesis_model="claude-sonnet-4-20250514",
        word_count=2000,
        metadata={"agent": "codebase-analyst"},
    )
    assert record_id == "new-mat-id"


# ── mark_accessed ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_accessed(service, mock_supabase):
    """Calls the increment_access_count RPC."""
    mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=[])

    await service.mark_accessed("mat-1")

    mock_supabase.rpc.assert_called_once_with("increment_access_count", {"record_id": "mat-1"})


# ── update_status ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_status(service, mock_supabase):
    """Updates status and updated_at timestamp."""

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        return builder

    mock_supabase.table.side_effect = _table

    await service.update_status("mat-1", "stale")

    # Verify the table was called and update was invoked
    mock_supabase.table.assert_called_with("cortex_materialization_history")


# ── delete_record ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_record(service, mock_supabase):
    """Deletes a record by ID."""

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        return builder

    mock_supabase.table.side_effect = _table

    await service.delete_record("mat-1")

    mock_supabase.table.assert_called_with("cortex_materialization_history")


# ── get_record ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_record_found(service, mock_supabase):
    """Returns a MaterializationRecord when found."""
    now = datetime.now(UTC).isoformat()
    record_data = {
        "id": "mat-1",
        "project_id": "proj-1",
        "project_path": "/home/user/project",
        "topic": "Docker compose",
        "filename": "docker-compose.md",
        "file_path": "/home/user/project/.cortex/knowledge/docker-compose.md",
        "source_ids": ["src-3"],
        "original_urls": ["https://docs.docker.com/compose/"],
        "synthesis_model": "claude-sonnet-4-20250514",
        "word_count": 3000,
        "status": "active",
        "access_count": 5,
        "last_accessed_at": now,
        "materialized_at": now,
        "updated_at": now,
        "metadata": {"version": "2"},
    }

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[record_data])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.get_record("mat-1")
    assert result is not None
    assert result.id == "mat-1"
    assert result.topic == "Docker compose"
    assert result.word_count == 3000
    assert result.metadata == {"version": "2"}


@pytest.mark.asyncio
async def test_get_record_not_found(service):
    """Returns None when record doesn't exist."""
    result = await service.get_record("nonexistent")
    assert result is None
