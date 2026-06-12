"""Tests for BackfillService — historical data ingestion from registered projects."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.pattern_discovery.backfill_service import BackfillService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return BackfillService(supabase_client=mock_supabase)


def _make_projects_response(projects: list) -> MagicMock:
    """Helper to create a supabase response mock for cortex_projects."""
    response = MagicMock()
    response.data = projects
    return response


class TestBackfillAllProjects:
    @pytest.mark.asyncio
    async def test_processes_project_with_valid_local_repo(self, service, mock_supabase):
        """Projects with a valid local git repo path get their commits captured."""
        projects = [{"id": "proj-1", "title": "My App", "github_repo": "/some/local/repo"}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        with patch("os.path.isdir", return_value=True):
            service._capture.capture_git_commits = AsyncMock(return_value=(True, {"captured": 5}))
            service._capture.get_pending_events = AsyncMock(
                return_value=(True, {"events": [{"id": "evt-1"}]})
            )
            service._normalization.normalize_batch = AsyncMock(
                return_value=(True, {"normalized": 5, "failed": 0})
            )

            success, result = await service.backfill_all_projects(lookback_days=30)

        assert success is True
        assert result["total_captured"] == 5
        assert result["normalized"] == 5
        assert len(result["projects"]) == 1
        assert result["projects"][0]["status"] == "captured"
        assert result["projects"][0]["captured"] == 5

        service._capture.capture_git_commits.assert_called_once_with(
            project_id="proj-1",
            repo_path="/some/local/repo",
            since_days=30,
        )

    @pytest.mark.asyncio
    async def test_skips_projects_without_github_repo(self, service, mock_supabase):
        """Projects with no github_repo field are silently skipped."""
        projects = [
            {"id": "proj-1", "title": "No Repo", "github_repo": None},
            {"id": "proj-2", "title": "Also No Repo"},
        ]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        service._capture.capture_git_commits = AsyncMock(return_value=(True, {"captured": 0}))

        success, result = await service.backfill_all_projects()

        assert success is True
        assert result["total_captured"] == 0
        assert result["projects"] == []
        service._capture.capture_git_commits.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_projects_with_nonexistent_path(self, service, mock_supabase):
        """Projects whose repo path does not exist locally are recorded as skipped."""
        projects = [{"id": "proj-1", "title": "Ghost Repo", "github_repo": "/nonexistent/path"}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        with patch("os.path.isdir", return_value=False):
            service._capture.capture_git_commits = AsyncMock(return_value=(True, {"captured": 0}))

            success, result = await service.backfill_all_projects()

        assert success is True
        assert result["total_captured"] == 0
        assert len(result["projects"]) == 1
        assert result["projects"][0]["status"] == "skipped"
        assert result["projects"][0]["reason"] == "repo path not found locally"
        service._capture.capture_git_commits.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_normalization_after_capture(self, service, mock_supabase):
        """Normalization pipeline runs on pending events after all captures complete."""
        projects = [{"id": "proj-1", "title": "App", "github_repo": "/valid/repo"}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        pending_events = [
            {"id": "evt-1", "event_type": "git_commit"},
            {"id": "evt-2", "event_type": "git_commit"},
        ]

        with patch("os.path.isdir", return_value=True):
            service._capture.capture_git_commits = AsyncMock(return_value=(True, {"captured": 2}))
            service._capture.get_pending_events = AsyncMock(
                return_value=(True, {"events": pending_events})
            )
            service._normalization.normalize_batch = AsyncMock(
                return_value=(True, {"normalized": 2, "failed": 0})
            )

            success, result = await service.backfill_all_projects()

        assert success is True
        service._capture.get_pending_events.assert_called_once_with(limit=500)
        service._normalization.normalize_batch.assert_called_once_with(pending_events)
        assert result["normalized"] == 2

    @pytest.mark.asyncio
    async def test_skips_normalization_when_nothing_captured(self, service, mock_supabase):
        """Normalization is not triggered when total_captured is zero."""
        projects = [{"id": "proj-1", "title": "Empty Repo", "github_repo": "/valid/repo"}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        with patch("os.path.isdir", return_value=True):
            service._capture.capture_git_commits = AsyncMock(return_value=(True, {"captured": 0}))
            service._capture.get_pending_events = AsyncMock()
            service._normalization.normalize_batch = AsyncMock()

            success, result = await service.backfill_all_projects()

        assert success is True
        assert result["total_captured"] == 0
        assert result["normalized"] == 0
        service._capture.get_pending_events.assert_not_called()
        service._normalization.normalize_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_capture_marks_project_as_failed(self, service, mock_supabase):
        """When capture_git_commits returns failure, project entry is marked failed."""
        projects = [{"id": "proj-1", "title": "Bad Repo", "github_repo": "/valid/repo"}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        with patch("os.path.isdir", return_value=True):
            service._capture.capture_git_commits = AsyncMock(
                return_value=(False, {"error": "git log failed"})
            )
            service._capture.get_pending_events = AsyncMock()
            service._normalization.normalize_batch = AsyncMock()

            success, result = await service.backfill_all_projects()

        assert success is True
        assert result["projects"][0]["status"] == "failed"
        assert result["projects"][0]["captured"] == 0
        assert result["total_captured"] == 0

    @pytest.mark.asyncio
    async def test_processes_multiple_projects(self, service, mock_supabase):
        """Multiple projects are all processed; totals accumulate correctly."""
        projects = [
            {"id": "proj-1", "title": "App A", "github_repo": "/repo/a"},
            {"id": "proj-2", "title": "App B", "github_repo": "/repo/b"},
            {"id": "proj-3", "title": "No Repo"},
        ]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        capture_results = [
            (True, {"captured": 3}),
            (True, {"captured": 7}),
        ]

        with patch("os.path.isdir", return_value=True):
            service._capture.capture_git_commits = AsyncMock(side_effect=capture_results)
            service._capture.get_pending_events = AsyncMock(
                return_value=(True, {"events": [{"id": "e1"}]})
            )
            service._normalization.normalize_batch = AsyncMock(
                return_value=(True, {"normalized": 10, "failed": 0})
            )

            success, result = await service.backfill_all_projects()

        assert success is True
        assert result["total_captured"] == 10
        # proj-3 has no repo so is skipped entirely (not added to project_results)
        assert len(result["projects"]) == 2
        assert result["projects"][0]["captured"] == 3
        assert result["projects"][1]["captured"] == 7

    @pytest.mark.asyncio
    async def test_supabase_query_failure_returns_error(self, service, mock_supabase):
        """A database failure when loading projects returns a failure tuple."""
        mock_supabase.table.return_value.select.return_value.execute.side_effect = Exception(
            "Connection refused"
        )

        success, result = await service.backfill_all_projects()

        assert success is False
        assert "error" in result
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_uses_default_lookback_days(self, service, mock_supabase):
        """Default lookback of 90 days is passed to capture_git_commits."""
        from src.server.services.pattern_discovery.backfill_service import DEFAULT_LOOKBACK_DAYS

        assert DEFAULT_LOOKBACK_DAYS == 90

        projects = [{"id": "proj-1", "title": "App", "github_repo": "/valid/repo"}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response(projects)
        )

        with patch("os.path.isdir", return_value=True):
            service._capture.capture_git_commits = AsyncMock(return_value=(True, {"captured": 0}))

            await service.backfill_all_projects()

        service._capture.capture_git_commits.assert_called_once_with(
            project_id="proj-1",
            repo_path="/valid/repo",
            since_days=DEFAULT_LOOKBACK_DAYS,
        )

    @pytest.mark.asyncio
    async def test_empty_projects_list_returns_zero_totals(self, service, mock_supabase):
        """When no projects exist in the database, the result has zero counts."""
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            _make_projects_response([])
        )

        success, result = await service.backfill_all_projects()

        assert success is True
        assert result["total_captured"] == 0
        assert result["normalized"] == 0
        assert result["projects"] == []
