"""One-time historical data ingestion from registered projects."""

import os
from typing import Any

from src.server.utils import get_supabase_client

from ...config.logfire_config import get_logger
from .capture_service import CaptureService
from .normalization_service import NormalizationService

logger = get_logger(__name__)

DEFAULT_LOOKBACK_DAYS = 90


class BackfillService:
    """Reads git history from all registered projects and ingests into activity_events."""

    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()
        self._capture = CaptureService(supabase_client=self.supabase_client)
        self._normalization = NormalizationService(supabase_client=self.supabase_client)

    async def backfill_all_projects(self, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> tuple[bool, dict[str, Any]]:
        """Backfill activity events from all registered projects' git history.

        Reads cortex_projects to find repos, runs capture_git_commits for each,
        then normalizes all pending events.

        Args:
            lookback_days: How far back to read git history (default 90 days).

        Returns:
            (success, result) tuple with total_captured, normalized, and per-project results.
        """
        try:
            response = self.supabase_client.table("cortex_projects").select("id, title, github_repo").execute()
            projects = response.data or []

            total_captured = 0
            project_results = []

            for project in projects:
                repo = project.get("github_repo")
                if not repo:
                    continue

                if not os.path.isdir(repo):
                    project_results.append({
                        "project_id": project["id"],
                        "title": project.get("title"),
                        "status": "skipped",
                        "reason": "repo path not found locally",
                    })
                    continue

                success, result = await self._capture.capture_git_commits(
                    project_id=project["id"],
                    repo_path=repo,
                    since_days=lookback_days,
                )
                captured = result.get("captured", 0) if success else 0
                total_captured += captured
                project_results.append({
                    "project_id": project["id"],
                    "title": project.get("title"),
                    "status": "captured" if success else "failed",
                    "captured": captured,
                })

            normalized_count = 0
            if total_captured > 0:
                pending_success, pending = await self._capture.get_pending_events(limit=500)
                if pending_success and pending.get("events"):
                    norm_success, norm_result = await self._normalization.normalize_batch(
                        pending["events"]
                    )
                    if norm_success:
                        normalized_count = norm_result.get("normalized", 0)

            return True, {
                "total_captured": total_captured,
                "normalized": normalized_count,
                "projects": project_results,
            }
        except Exception as e:
            logger.error(f"Error during backfill: {e}", exc_info=True)
            return False, {"error": str(e)}
