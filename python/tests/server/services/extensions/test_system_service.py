"""
Unit tests for SystemService.

Tests machine fingerprint registration, lookup, update, and deletion
against the cortex_systems table using a mocked Supabase client.
"""

from unittest.mock import MagicMock

import pytest

from src.server.services.extensions import SystemService


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with chained table builder."""
    client = MagicMock()
    return client


@pytest.fixture
def service(mock_supabase):
    """Create a SystemService with the mocked Supabase client."""
    return SystemService(supabase_client=mock_supabase)


SAMPLE_SYSTEM = {
    "id": "abc-123",
    "fingerprint": "fp-deadbeef",
    "name": "dev-laptop",
    "hostname": "cortex-box",
    "os": "linux",
    "last_seen_at": "2026-03-04T00:00:00+00:00",
    "created_at": "2026-03-04T00:00:00+00:00",
}


# ── find_by_fingerprint ──────────────────────────────────────────────────────


class TestFindByFingerprint:
    def test_returns_system_when_found(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            SAMPLE_SYSTEM
        ]

        result = service.find_by_fingerprint("fp-deadbeef")

        assert result == SAMPLE_SYSTEM
        mock_supabase.table.assert_called_with("cortex_systems")
        mock_supabase.table.return_value.select.assert_called_once_with("*")
        mock_supabase.table.return_value.select.return_value.eq.assert_called_once_with(
            "fingerprint", "fp-deadbeef"
        )

    def test_returns_none_when_not_found(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        result = service.find_by_fingerprint("fp-nonexistent")

        assert result is None


# ── register_system ──────────────────────────────────────────────────────────


class TestRegisterSystem:
    def test_creates_record_with_all_fields(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            SAMPLE_SYSTEM
        ]

        result = service.register_system(
            fingerprint="fp-deadbeef",
            name="dev-laptop",
            hostname="cortex-box",
            os="linux",
        )

        assert result == SAMPLE_SYSTEM
        mock_supabase.table.assert_called_with("cortex_systems")
        insert_arg = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_arg["fingerprint"] == "fp-deadbeef"
        assert insert_arg["name"] == "dev-laptop"
        assert insert_arg["hostname"] == "cortex-box"
        assert insert_arg["os"] == "linux"

    def test_raises_on_empty_response(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = []

        with pytest.raises(RuntimeError, match="Failed to register system"):
            service.register_system(
                fingerprint="fp-deadbeef",
                name="dev-laptop",
            )

    def test_creates_with_optional_fields_none(self, service, mock_supabase):
        created = {**SAMPLE_SYSTEM, "hostname": None, "os": None}
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [created]

        result = service.register_system(
            fingerprint="fp-deadbeef",
            name="dev-laptop",
        )

        assert result["hostname"] is None
        assert result["os"] is None
        insert_arg = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_arg.get("hostname") is None
        assert insert_arg.get("os") is None


# ── update_last_seen ─────────────────────────────────────────────────────────


class TestUpdateLastSeen:
    def test_updates_timestamp(self, service, mock_supabase):
        updated = {**SAMPLE_SYSTEM, "last_seen_at": "2026-03-04T12:00:00+00:00"}
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            updated
        ]

        result = service.update_last_seen("abc-123")

        assert result == updated
        mock_supabase.table.assert_called_with("cortex_systems")
        mock_supabase.table.return_value.update.return_value.eq.assert_called_once_with("id", "abc-123")
        update_arg = mock_supabase.table.return_value.update.call_args[0][0]
        assert "last_seen_at" in update_arg


# ── list_systems ─────────────────────────────────────────────────────────────


class TestListSystems:
    def test_returns_all_systems(self, service, mock_supabase):
        systems = [SAMPLE_SYSTEM, {**SAMPLE_SYSTEM, "id": "def-456", "name": "ci-server"}]
        mock_supabase.table.return_value.select.return_value.order.return_value.execute.return_value.data = systems

        result = service.list_systems()

        assert result == systems
        assert len(result) == 2
        mock_supabase.table.assert_called_with("cortex_systems")
        mock_supabase.table.return_value.select.assert_called_once_with("*")

    def test_returns_empty_list_when_no_systems(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.order.return_value.execute.return_value.data = []

        result = service.list_systems()

        assert result == []


# ── get_system ───────────────────────────────────────────────────────────────


class TestGetSystem:
    def test_returns_system_by_id(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            SAMPLE_SYSTEM
        ]

        result = service.get_system("abc-123")

        assert result == SAMPLE_SYSTEM
        mock_supabase.table.return_value.select.return_value.eq.assert_called_once_with("id", "abc-123")

    def test_returns_none_when_not_found(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        result = service.get_system("nonexistent-id")

        assert result is None


# ── update_system ────────────────────────────────────────────────────────────


class TestUpdateSystem:
    def test_updates_name(self, service, mock_supabase):
        updated = {**SAMPLE_SYSTEM, "name": "renamed-laptop"}
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            updated
        ]

        result = service.update_system("abc-123", name="renamed-laptop")

        assert result == updated
        mock_supabase.table.return_value.update.return_value.eq.assert_called_once_with("id", "abc-123")
        update_arg = mock_supabase.table.return_value.update.call_args[0][0]
        assert update_arg["name"] == "renamed-laptop"

    def test_updates_hostname(self, service, mock_supabase):
        updated = {**SAMPLE_SYSTEM, "hostname": "new-host"}
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            updated
        ]

        result = service.update_system("abc-123", hostname="new-host")

        assert result == updated
        update_arg = mock_supabase.table.return_value.update.call_args[0][0]
        assert update_arg["hostname"] == "new-host"

    def test_returns_none_when_not_found(self, service, mock_supabase):
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

        result = service.update_system("nonexistent-id", name="whatever")

        assert result is None


# ── delete_system ────────────────────────────────────────────────────────────


class TestDeleteSystem:
    def test_deletes_system(self, service, mock_supabase):
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [
            SAMPLE_SYSTEM
        ]

        result = service.delete_system("abc-123")

        assert result is True
        mock_supabase.table.assert_called_with("cortex_systems")
        mock_supabase.table.return_value.delete.return_value.eq.assert_called_once_with("id", "abc-123")

    def test_returns_false_when_not_found(self, service, mock_supabase):
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []

        result = service.delete_system("nonexistent-id")

        assert result is False
