"""Tests for ExtensionSyncService.

Tests sync report computation (hash comparison, drift detection),
install status management, and queue operations using mocked Supabase client.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.server.services.extensions.extension_sync_service import ExtensionSyncService, _compute_direction

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with chainable query methods."""
    client = MagicMock()

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete", "upsert"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.neq.return_value = builder
        builder.order.return_value = builder
        builder.limit.return_value = builder
        return builder

    client.table.side_effect = _table
    return client


@pytest.fixture
def service(mock_supabase):
    """Create an ExtensionSyncService instance with mocked Supabase."""
    return ExtensionSyncService(supabase_client=mock_supabase)


# ── compute_sync_report ─────────────────────────────────────────────────────


class TestComputeSyncReport:
    def test_in_sync_when_hashes_match(self, service):
        """Extension with matching local and Archon hashes should be in_sync."""
        local_extensions = [{"name": "archon-memory", "content_hash": "aaa"}]
        archon_extensions = [{"id": "s1", "name": "archon-memory", "content_hash": "aaa", "content": "..."}]
        system_extensions = [{"extension_id": "s1", "status": "installed", "installed_content_hash": "aaa"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        assert "archon-memory" in report["in_sync"]
        assert len(report["local_changes"]) == 0
        assert len(report["pending_install"]) == 0
        assert len(report["pending_remove"]) == 0
        assert len(report["unknown_local"]) == 0

    def test_detects_local_changes(self, service):
        """Local extension with different hash than Archon should appear in local_changes."""
        local_extensions = [{"name": "archon-memory", "content_hash": "bbb"}]
        archon_extensions = [{"id": "s1", "name": "archon-memory", "content_hash": "aaa", "content": "..."}]
        system_extensions = [{"extension_id": "s1", "status": "installed", "installed_content_hash": "aaa"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        assert len(report["local_changes"]) == 1
        assert report["local_changes"][0]["name"] == "archon-memory"
        assert report["local_changes"][0]["local_hash"] == "bbb"
        assert report["local_changes"][0]["archon_hash"] == "aaa"
        assert len(report["in_sync"]) == 0

    def test_detects_unknown_local(self, service):
        """Local extension not in the Archon registry should appear in unknown_local."""
        local_extensions = [{"name": "new-extension", "content_hash": "xxx"}]
        archon_extensions = []
        system_extensions = []

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        assert len(report["unknown_local"]) == 1
        assert report["unknown_local"][0]["name"] == "new-extension"
        assert report["unknown_local"][0]["content_hash"] == "xxx"

    def test_detects_pending_installs(self, service):
        """Archon extension with pending_install status and no local copy should be pending_install."""
        local_extensions = []
        archon_extensions = [{"id": "s1", "name": "code-reviewer", "content_hash": "ccc", "content": "...content..."}]
        system_extensions = [{"extension_id": "s1", "status": "pending_install"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        assert len(report["pending_install"]) == 1
        assert report["pending_install"][0]["name"] == "code-reviewer"
        assert report["pending_install"][0]["extension_id"] == "s1"
        assert report["pending_install"][0]["content"] == "...content..."

    def test_detects_pending_removals(self, service):
        """Local extension with pending_remove status in system_extensions should be pending_remove."""
        local_extensions = [{"name": "old-extension", "content_hash": "ddd"}]
        archon_extensions = [{"id": "s2", "name": "old-extension", "content_hash": "ddd", "content": "..."}]
        system_extensions = [{"extension_id": "s2", "status": "pending_remove"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        assert len(report["pending_remove"]) == 1
        assert report["pending_remove"][0]["name"] == "old-extension"
        assert report["pending_remove"][0]["extension_id"] == "s2"
        assert len(report["in_sync"]) == 0

    def test_empty_inputs_produce_empty_report(self, service):
        """All empty inputs should produce an empty report with no entries."""
        report = service.compute_sync_report([], [], [])

        assert report["in_sync"] == []
        assert report["local_changes"] == []
        assert report["pending_install"] == []
        assert report["pending_remove"] == []
        assert report["unknown_local"] == []

    def test_multiple_extensions_classified_correctly(self, service):
        """Multiple extensions in different states should each be classified correctly."""
        local_extensions = [
            {"name": "extension-a", "content_hash": "aaa"},
            {"name": "extension-b", "content_hash": "bbb_local"},
            {"name": "extension-unknown", "content_hash": "uuu"},
        ]
        archon_extensions = [
            {"id": "s1", "name": "extension-a", "content_hash": "aaa", "content": "..."},
            {"id": "s2", "name": "extension-b", "content_hash": "bbb_archon", "content": "..."},
            {"id": "s3", "name": "extension-pending", "content_hash": "ppp", "content": "pending content"},
        ]
        system_extensions = [
            {"extension_id": "s1", "status": "installed", "installed_content_hash": "aaa"},
            {"extension_id": "s2", "status": "installed", "installed_content_hash": "bbb_archon"},
            {"extension_id": "s3", "status": "pending_install"},
        ]

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        assert "extension-a" in report["in_sync"]
        assert len(report["local_changes"]) == 1
        assert report["local_changes"][0]["name"] == "extension-b"
        assert len(report["unknown_local"]) == 1
        assert report["unknown_local"][0]["name"] == "extension-unknown"
        assert len(report["pending_install"]) == 1
        assert report["pending_install"][0]["name"] == "extension-pending"

    def test_pending_install_ignored_when_already_local(self, service):
        """If an extension is already local, it should not appear in pending_install even with pending_install status."""
        local_extensions = [{"name": "already-here", "content_hash": "hhh"}]
        archon_extensions = [{"id": "s1", "name": "already-here", "content_hash": "hhh", "content": "..."}]
        system_extensions = [{"extension_id": "s1", "status": "pending_install"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, system_extensions)

        # It should be in_sync (hashes match), not pending_install
        assert "already-here" in report["in_sync"]
        assert len(report["pending_install"]) == 0


# ── _compute_direction ───────────────────────────────────────────────────────


class TestComputeDirection:
    def _ts(self, dt: datetime) -> float:
        """Convert datetime to Unix timestamp."""
        return dt.replace(tzinfo=timezone.utc).timestamp()

    def _iso(self, dt: datetime) -> str:
        """Convert datetime to ISO string as stored in DB."""
        return dt.replace(tzinfo=timezone.utc).isoformat()

    def test_local_newer_when_local_mtime_is_later(self):
        base = datetime(2025, 1, 1, 12, 0, 0)
        archon = datetime(2025, 1, 1, 11, 0, 0)  # 1 hour earlier
        assert _compute_direction(self._ts(base), self._iso(archon)) == "local_newer"

    def test_archon_newer_when_archon_updated_at_is_later(self):
        local = datetime(2025, 1, 1, 11, 0, 0)
        archon = datetime(2025, 1, 1, 12, 0, 0)  # 1 hour later
        assert _compute_direction(self._ts(local), self._iso(archon)) == "archon_newer"

    def test_conflict_when_within_clock_skew_threshold(self):
        base = datetime(2025, 1, 1, 12, 0, 0)
        # 3 seconds apart — within 5-second threshold
        archon = datetime(2025, 1, 1, 12, 0, 3)
        assert _compute_direction(self._ts(base), self._iso(archon)) == "conflict"

    def test_conflict_when_timestamps_are_equal(self):
        dt = datetime(2025, 1, 1, 12, 0, 0)
        assert _compute_direction(self._ts(dt), self._iso(dt)) == "conflict"

    def test_unknown_when_local_mtime_is_none(self):
        archon = datetime(2025, 1, 1, 12, 0, 0)
        assert _compute_direction(None, self._iso(archon)) == "unknown"

    def test_unknown_when_archon_updated_at_is_none(self):
        local = datetime(2025, 1, 1, 12, 0, 0)
        assert _compute_direction(self._ts(local), None) == "unknown"

    def test_unknown_when_both_missing(self):
        assert _compute_direction(None, None) == "unknown"

    def test_unknown_when_archon_timestamp_is_unparseable(self):
        assert _compute_direction(1700000000.0, "not-a-timestamp") == "unknown"

    def test_accepts_integer_local_mtime(self):
        base = datetime(2025, 1, 1, 12, 0, 0)
        archon = datetime(2025, 1, 1, 11, 0, 0)
        assert _compute_direction(int(self._ts(base)), self._iso(archon)) == "local_newer"

    def test_accepts_z_suffix_iso_timestamp(self):
        local = datetime(2025, 1, 1, 11, 0, 0)
        archon_iso = "2025-01-01T12:00:00Z"
        assert _compute_direction(self._ts(local), archon_iso) == "archon_newer"


class TestComputeSyncReportWithTimestamps:
    """Tests that verify direction field is included in local_changes."""

    def test_local_changes_include_direction_local_newer(self, service):
        local_ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        archon_updated = "2025-06-01T11:00:00+00:00"
        local_extensions = [{"name": "my-skill", "content_hash": "bbb", "local_mtime": local_ts}]
        archon_extensions = [{"id": "s1", "name": "my-skill", "content_hash": "aaa", "updated_at": archon_updated}]

        report = service.compute_sync_report(local_extensions, archon_extensions, [])

        assert len(report["local_changes"]) == 1
        change = report["local_changes"][0]
        assert change["direction"] == "local_newer"
        assert change["local_mtime"] == local_ts
        assert change["archon_updated_at"] == archon_updated

    def test_local_changes_include_direction_archon_newer(self, service):
        local_ts = datetime(2025, 6, 1, 11, 0, 0, tzinfo=timezone.utc).timestamp()
        archon_updated = "2025-06-01T12:00:00+00:00"
        local_extensions = [{"name": "my-skill", "content_hash": "bbb", "local_mtime": local_ts}]
        archon_extensions = [{"id": "s1", "name": "my-skill", "content_hash": "aaa", "updated_at": archon_updated}]

        report = service.compute_sync_report(local_extensions, archon_extensions, [])

        assert report["local_changes"][0]["direction"] == "archon_newer"

    def test_local_changes_direction_unknown_when_no_mtime(self, service):
        local_extensions = [{"name": "my-skill", "content_hash": "bbb"}]
        archon_extensions = [{"id": "s1", "name": "my-skill", "content_hash": "aaa", "updated_at": "2025-06-01T12:00:00Z"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, [])

        assert report["local_changes"][0]["direction"] == "unknown"
        assert report["local_changes"][0]["local_mtime"] is None

    def test_local_changes_direction_unknown_when_no_archon_timestamp(self, service):
        local_ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        local_extensions = [{"name": "my-skill", "content_hash": "bbb", "local_mtime": local_ts}]
        archon_extensions = [{"id": "s1", "name": "my-skill", "content_hash": "aaa"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, [])

        assert report["local_changes"][0]["direction"] == "unknown"
        assert report["local_changes"][0]["archon_updated_at"] is None

    def test_in_sync_extensions_not_affected_by_timestamps(self, service):
        local_ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        local_extensions = [{"name": "my-skill", "content_hash": "aaa", "local_mtime": local_ts}]
        archon_extensions = [{"id": "s1", "name": "my-skill", "content_hash": "aaa", "updated_at": "2025-01-01T00:00:00Z"}]

        report = service.compute_sync_report(local_extensions, archon_extensions, [])

        assert "my-skill" in report["in_sync"]
        assert len(report["local_changes"]) == 0


# ── get_system_extensions ────────────────────────────────────────────────────


class TestGetSystemExtensions:
    def test_returns_matching_records(self, service, mock_supabase):
        """Should query archon_system_extensions with system_id and project_id filters."""
        system_extensions_data = [
            {"system_id": "sys-1", "project_id": "proj-1", "extension_id": "s1", "status": "installed"},
            {"system_id": "sys-1", "project_id": "proj-1", "extension_id": "s2", "status": "pending_install"},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=system_extensions_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_system_extensions("sys-1", "proj-1")

        assert len(result) == 2
        mock_supabase.table.assert_called_with("archon_system_extensions")

    def test_returns_empty_list_when_no_records(self, service, mock_supabase):
        """Should return empty list when no system extensions match."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=None)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_system_extensions("sys-1", "proj-1")

        assert result == []


# ── set_install_status ───────────────────────────────────────────────────────


class TestSetInstallStatus:
    def test_upserts_install_record(self, service, mock_supabase):
        """Should upsert into archon_system_extensions with correct data."""
        install_row = {
            "system_id": "sys-1",
            "extension_id": "s1",
            "project_id": "proj-1",
            "status": "installed",
            "installed_content_hash": "aaa",
            "installed_version": 2,
            "has_local_changes": False,
        }

        builder = MagicMock()
        builder.upsert.return_value = builder
        builder.execute.return_value = MagicMock(data=[install_row])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.set_install_status(
            system_id="sys-1",
            extension_id="s1",
            project_id="proj-1",
            status="installed",
            installed_content_hash="aaa",
            installed_version=2,
        )

        assert result["status"] == "installed"
        assert result["installed_content_hash"] == "aaa"

        mock_supabase.table.assert_called_with("archon_system_extensions")
        builder.upsert.assert_called_once()
        upsert_data = builder.upsert.call_args[0][0]
        assert upsert_data["system_id"] == "sys-1"
        assert upsert_data["extension_id"] == "s1"
        assert upsert_data["status"] == "installed"

    def test_raises_on_empty_response(self, service, mock_supabase):
        """Should raise RuntimeError when upsert returns no data."""
        builder = MagicMock()
        builder.upsert.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        with pytest.raises(RuntimeError, match="Failed to set install status"):
            service.set_install_status(
                system_id="sys-1",
                extension_id="s1",
                project_id="proj-1",
                status="installed",
            )


# ── queue_install / queue_remove ────────────────────────────────────────────


class TestQueueInstall:
    def test_queues_install_for_multiple_systems(self, service, mock_supabase):
        """Should call set_install_status for each system and return count."""
        builder = MagicMock()
        builder.upsert.return_value = builder
        builder.execute.return_value = MagicMock(data=[{"status": "pending_install"}])

        mock_supabase.table.side_effect = lambda name: builder

        count = service.queue_install(
            system_ids=["sys-1", "sys-2", "sys-3"],
            extension_id="s1",
            project_id="proj-1",
        )

        assert count == 3


class TestQueueRemove:
    def test_queues_remove_for_multiple_systems(self, service, mock_supabase):
        """Should call set_install_status for each system and return count."""
        builder = MagicMock()
        builder.upsert.return_value = builder
        builder.execute.return_value = MagicMock(data=[{"status": "pending_remove"}])

        mock_supabase.table.side_effect = lambda name: builder

        count = service.queue_remove(
            system_ids=["sys-1", "sys-2"],
            extension_id="s1",
            project_id="proj-1",
        )

        assert count == 2


# ── get_project_systems ──────────────────────────────────────────────────────


class TestGetProjectSystems:
    def test_returns_registered_systems(self, service, mock_supabase):
        """Should return systems from the registrations table."""
        query_data = [
            {"system_id": "sys-1", "archon_systems": {"id": "sys-1", "name": "Dev Machine"}},
            {"system_id": "sys-2", "archon_systems": {"id": "sys-2", "name": "CI Server"}},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=query_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_project_systems("proj-1")

        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"Dev Machine", "CI Server"}

    def test_returns_empty_list_when_no_data(self, service, mock_supabase):
        """Should return empty list when no systems found."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=None)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_project_systems("proj-1")

        assert result == []

    def test_skips_rows_without_system_record(self, service, mock_supabase):
        """Should skip rows where the joined archon_systems data is null."""
        query_data = [
            {"system_id": "sys-1", "archon_systems": {"id": "sys-1", "name": "Dev Machine"}},
            {"system_id": "sys-2", "archon_systems": None},
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=query_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_project_systems("proj-1")

        assert len(result) == 1
        assert result[0]["name"] == "Dev Machine"


# ── get_system_project_extensions ────────────────────────────────────────────


class TestGetSystemProjectExtensions:
    def test_returns_extensions_with_joined_data(self, service, mock_supabase):
        """Should return system extensions with joined archon_extensions metadata."""
        query_data = [
            {
                "system_id": "sys-1",
                "extension_id": "s1",
                "status": "installed",
                "archon_extensions": {"id": "s1", "name": "archon-memory", "display_name": "Archon Memory"},
            },
        ]

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=query_data)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_system_project_extensions("sys-1", "proj-1")

        assert len(result) == 1
        assert result[0]["archon_extensions"]["name"] == "archon-memory"
        mock_supabase.table.assert_called_with("archon_system_extensions")

    def test_returns_empty_list_when_no_data(self, service, mock_supabase):
        """Should return empty list when no system project extensions exist."""
        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=None)

        mock_supabase.table.side_effect = lambda name: builder

        result = service.get_system_project_extensions("sys-1", "proj-1")

        assert result == []


# ── unlink_system_from_project ───────────────────────────────────────────────


class TestUnlinkSystemFromProject:
    def test_deletes_registration_record(self, service, mock_supabase):
        """Should delete from archon_project_system_registrations and return True when found."""
        builder = MagicMock()
        builder.delete.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{"project_id": "proj-1", "system_id": "sys-1"}])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.unlink_system_from_project("sys-1", "proj-1")

        assert result is True
        mock_supabase.table.assert_called_with("archon_project_system_registrations")
        builder.delete.assert_called_once()

    def test_returns_false_when_not_found(self, service, mock_supabase):
        """Should return False when the association does not exist."""
        builder = MagicMock()
        builder.delete.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: builder

        result = service.unlink_system_from_project("sys-1", "proj-1")

        assert result is False
