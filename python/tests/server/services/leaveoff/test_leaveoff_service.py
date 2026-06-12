"""Tests for LeaveOffService."""
from unittest.mock import MagicMock

import pytest

from src.server.services.leaveoff.leaveoff_service import LeaveOffService


@pytest.fixture
def mock_supabase():
    client = MagicMock()

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        return builder

    client.table.side_effect = _table
    return client


@pytest.fixture
def service(mock_supabase):
    return LeaveOffService(supabase_client=mock_supabase)


@pytest.mark.asyncio
async def test_upsert_creates_new_record(service, mock_supabase):
    """Verify upsert creates a new LeaveOff point."""
    row = {
        "id": "uuid-1",
        "project_id": "proj-1",
        "content": "Working on auth module",
        "component": "auth",
        "next_steps": ["Add token refresh"],
        "references": ["src/auth.py"],
        "machine_id": "machine-abc",
        "last_session_id": "sess-1",
        "metadata": {},
    }

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[row])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.upsert(
        project_id="proj-1",
        content="Working on auth module",
        next_steps=["Add token refresh"],
        component="auth",
        references=["src/auth.py"],
        machine_id="machine-abc",
        last_session_id="sess-1",
    )

    assert result["project_id"] == "proj-1"
    assert result["content"] == "Working on auth module"
    assert result["next_steps"] == ["Add token refresh"]

    # Verify upsert was called on the correct table
    mock_supabase.table.assert_any_call("cortex_leaveoff_points")


@pytest.mark.asyncio
async def test_upsert_replaces_existing_record(service, mock_supabase):
    """Verify upsert replaces an existing record via on_conflict."""
    updated_row = {
        "id": "uuid-1",
        "project_id": "proj-1",
        "content": "Now working on API layer",
        "component": "api",
        "next_steps": ["Add rate limiting"],
        "references": ["src/api.py"],
        "machine_id": "machine-abc",
        "last_session_id": "sess-2",
        "metadata": {"priority": "high"},
    }

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[updated_row])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.upsert(
        project_id="proj-1",
        content="Now working on API layer",
        next_steps=["Add rate limiting"],
        component="api",
        references=["src/api.py"],
        machine_id="machine-abc",
        last_session_id="sess-2",
        metadata={"priority": "high"},
    )

    assert result["content"] == "Now working on API layer"
    assert result["component"] == "api"
    assert result["metadata"] == {"priority": "high"}


@pytest.mark.asyncio
async def test_get_returns_record(service, mock_supabase):
    """Verify get returns the record for a project."""
    row = {
        "id": "uuid-1",
        "project_id": "proj-1",
        "content": "Working on auth module",
        "next_steps": ["Add token refresh"],
    }

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[row])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.get("proj-1")

    assert result is not None
    assert result["project_id"] == "proj-1"
    assert result["content"] == "Working on auth module"


@pytest.mark.asyncio
async def test_get_returns_none_when_not_found(service, mock_supabase):
    """Verify get returns None when nothing exists for the project."""
    result = await service.get("nonexistent-project")

    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_record(service, mock_supabase):
    """Verify delete removes and returns True."""
    deleted_row = {"id": "uuid-1", "project_id": "proj-1"}

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[deleted_row])
        return builder

    mock_supabase.table.side_effect = _table

    result = await service.delete("proj-1")

    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_not_found(service, mock_supabase):
    """Verify delete returns False when nothing exists to delete."""
    result = await service.delete("nonexistent-project")

    assert result is False
