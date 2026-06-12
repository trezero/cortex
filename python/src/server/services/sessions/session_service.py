"""Session memory service for storing and retrieving session observations."""
from typing import Any

from src.server.config.logfire_config import get_logger
from src.server.utils import get_supabase_client

logger = get_logger(__name__)

SESSIONS_TABLE = "cortex_sessions"
OBSERVATIONS_TABLE = "cortex_session_observations"


class SessionService:
    """Service for session memory CRUD and search operations."""

    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def create_session(
        self,
        session_id: str,
        machine_id: str,
        project_id: str | None,
        started_at: str,
        ended_at: str | None = None,
        summary: str | None = None,
        observations: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Insert a session row and batch-insert its observations.

        Args:
            session_id: Unique session identifier (UUID or generated string).
            machine_id: SHA256 fingerprint of the machine.
            project_id: Optional Cortex project UUID.
            started_at: ISO timestamp of session start.
            ended_at: ISO timestamp of session end (optional).
            summary: Human-readable summary of what happened (optional).
            observations: List of observation dicts with keys: type, title,
                content, files, timestamp.

        Returns:
            (True, {"session": <row>}) on success.
            (False, {"error": <msg>}) on validation or DB error.
        """
        if not session_id:
            return False, {"error": "session_id is required"}
        if not machine_id:
            return False, {"error": "machine_id is required"}

        session_data: dict[str, Any] = {
            "session_id": session_id,
            "machine_id": machine_id,
            "started_at": started_at,
        }
        if project_id:
            session_data["project_id"] = project_id
        if ended_at:
            session_data["ended_at"] = ended_at
        if summary:
            session_data["summary"] = summary
        if observations:
            session_data["observation_count"] = len(observations)

        try:
            result = (
                self.supabase_client.table(SESSIONS_TABLE)
                .insert(session_data)
                .execute()
            )
            if not result.data:
                return False, {"error": "Session insert returned no data"}

            session_row = result.data[0]

            if observations:
                obs_rows = [
                    {
                        "session_id": session_id,
                        "machine_id": machine_id,
                        "project_id": project_id,
                        "type": obs.get("type", "general"),
                        "title": obs.get("title", ""),
                        "content": obs.get("content"),
                        "files": obs.get("files", []),
                        "observed_at": obs.get("timestamp", started_at),
                    }
                    for obs in observations
                ]
                self.supabase_client.table(OBSERVATIONS_TABLE).insert(obs_rows).execute()

            logger.info(
                "Session created",
                session_id=session_id,
                machine_id=machine_id,
                observation_count=len(observations or []),
            )
            return True, {"session": session_row}

        except Exception as e:
            logger.error("Failed to create session", session_id=session_id, exc_info=True)
            return False, {"error": str(e)}

    def list_sessions(
        self,
        project_id: str | None = None,
        machine_id: str | None = None,
        limit: int = 10,
    ) -> tuple[bool, dict[str, Any]]:
        """List sessions ordered by started_at DESC.

        Args:
            project_id: Filter to sessions for a specific project.
            machine_id: Filter to sessions from a specific machine.
            limit: Maximum number of sessions to return.

        Returns:
            (True, {"sessions": [...]}) on success.
            (False, {"error": <msg>}) on DB error.
        """
        try:
            query = (
                self.supabase_client.table(SESSIONS_TABLE)
                .select("*")
                .order("started_at", desc=True)
                .limit(limit)
            )
            if project_id:
                query = query.eq("project_id", project_id)
            if machine_id:
                query = query.eq("machine_id", machine_id)

            result = query.execute()
            return True, {"sessions": result.data or []}

        except Exception as e:
            logger.error("Failed to list sessions", exc_info=True)
            return False, {"error": str(e)}

    def get_session(self, session_id: str) -> tuple[bool, dict[str, Any]]:
        """Get a single session with all its observations.

        Args:
            session_id: The unique session identifier.

        Returns:
            (True, {"session": <row>, "observations": [...]}) on success.
            (False, {"error": <msg>}) if not found or on DB error.
        """
        try:
            session_result = (
                self.supabase_client.table(SESSIONS_TABLE)
                .select("*")
                .eq("session_id", session_id)
                .execute()
            )
            if not session_result.data:
                return False, {"error": f"Session '{session_id}' not found"}

            obs_result = (
                self.supabase_client.table(OBSERVATIONS_TABLE)
                .select("*")
                .eq("session_id", session_id)
                .order("observed_at")
                .execute()
            )
            return True, {
                "session": session_result.data[0],
                "observations": obs_result.data or [],
            }

        except Exception as e:
            logger.error("Failed to get session", session_id=session_id, exc_info=True)
            return False, {"error": str(e)}

    def search_sessions(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
    ) -> tuple[bool, dict[str, Any]]:
        """Full-text search across session observations.

        Uses Postgres full-text search on the search_vector column which is
        auto-populated from title + content + files by a DB trigger.

        Args:
            query: Search terms.
            project_id: Optional project scope.
            limit: Maximum results to return.

        Returns:
            (True, {"sessions": [...]}) on success.
            (False, {"error": <msg>}) if query empty or on DB error.
        """
        if not query or not query.strip():
            return False, {"error": "query is required"}

        try:
            params: dict[str, Any] = {"search_query": query.strip(), "result_limit": limit}
            if project_id:
                params["filter_project_id"] = project_id

            result = self.supabase_client.rpc("search_session_observations", params).execute()
            return True, {"sessions": result.data or []}

        except Exception as e:
            logger.error("Failed to search sessions", query=query, exc_info=True)
            return False, {"error": str(e)}
