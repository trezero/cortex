"""LeaveOff point service for storing and retrieving where a developer left off."""
import os
from datetime import UTC, datetime

import yaml

from ...config.logfire_config import get_logger
from ...utils import get_supabase_client

logger = get_logger(__name__)

TABLE = "cortex_leaveoff_points"
KNOWLEDGE_DIR = ".cortex/knowledge"
FILENAME = "LeaveOffPoint.md"


class LeaveOffService:
    """Service for LeaveOff point CRUD operations.

    Each project has at most one LeaveOff point (upsert on project_id).
    """

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    def _write_file(self, project_path: str, record: dict) -> str:
        """Write a LeaveOffPoint.md file into the project's .cortex/knowledge/ directory.

        Args:
            project_path: Absolute path to the project root.
            record: The LeaveOff point record dict from the database.

        Returns:
            The absolute path to the written file.
        """
        dir_path = os.path.join(project_path, KNOWLEDGE_DIR)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, FILENAME)

        frontmatter = {
            "project_id": record.get("project_id"),
            "component": record.get("component"),
            "updated_at": record.get("updated_at"),
            "machine_id": record.get("machine_id"),
            "system_name": record.get("system_name"),
            "git_clean": record.get("git_clean"),
        }

        lines: list[str] = []
        lines.append("---")
        lines.append(yaml.dump(frontmatter, default_flow_style=False).rstrip())
        lines.append("---")
        lines.append("")
        lines.append(record.get("content", ""))

        next_steps = record.get("next_steps") or []
        if next_steps:
            lines.append("")
            lines.append("## Next Steps")
            for step in next_steps:
                lines.append(f"- {step}")

        references = record.get("references") or []
        if references:
            lines.append("")
            lines.append("## References")
            for ref in references:
                lines.append(f"- {ref}")

        lines.append("")  # trailing newline
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"LeaveOffPoint.md written | path={file_path}")
        return file_path

    async def upsert(
        self,
        project_id: str,
        content: str,
        next_steps: list[str] | None = None,
        component: str | None = None,
        references: list[str] | None = None,
        machine_id: str | None = None,
        system_name: str | None = None,
        git_clean: bool | None = None,
        last_session_id: str | None = None,
        metadata: dict | None = None,
        project_path: str | None = None,
    ) -> dict:
        """Atomic UPSERT using on_conflict='project_id'.

        Creates a new LeaveOff point or replaces the existing one for the given project.
        When project_path is provided, also writes a LeaveOffPoint.md file to disk.

        Args:
            project_id: The project this LeaveOff point belongs to.
            content: Free-form description of current state / where you left off.
            next_steps: Ordered list of next actions to take.
            component: Which component or area of the project was being worked on.
            references: File paths, URLs, or other references relevant to the work.
            machine_id: SHA256 fingerprint of the machine that created this point.
            last_session_id: Session ID from the last coding session.
            metadata: Arbitrary key-value data.
            project_path: Absolute path to the project root for file writing.

        Returns:
            The upserted row as a dict.

        Raises:
            RuntimeError: If the upsert returns no data.
        """
        now = datetime.now(UTC).isoformat()
        data = {
            "project_id": project_id,
            "content": content,
            "component": component,
            "next_steps": next_steps or [],
            "references": references or [],
            "machine_id": machine_id,
            "system_name": system_name,
            "git_clean": git_clean,
            "last_session_id": last_session_id,
            "metadata": metadata or {},
            "updated_at": now,
        }
        result = self.supabase.table(TABLE).upsert(data, on_conflict="project_id").execute()
        if not result.data:
            raise RuntimeError(f"LeaveOff upsert returned no data for project {project_id}")
        record = result.data[0]
        logger.info(f"LeaveOff point upserted | project_id={project_id} | component={component}")

        if project_path:
            try:
                self._write_file(project_path, record)
            except Exception:
                logger.error(f"Failed to write LeaveOffPoint.md | project_path={project_path} | project_id={project_id}", exc_info=True)

        return record

    async def get(self, project_id: str) -> dict | None:
        """Get the LeaveOff point for a project.

        Args:
            project_id: The project to look up.

        Returns:
            The row as a dict, or None if no LeaveOff point exists for this project.
        """
        result = self.supabase.table(TABLE).select("*").eq("project_id", project_id).execute()
        if not result.data:
            return None
        return result.data[0]

    async def delete(self, project_id: str, project_path: str | None = None) -> bool:
        """Delete the LeaveOff point for a project.

        Args:
            project_id: The project whose LeaveOff point should be removed.
            project_path: If provided, also remove the LeaveOffPoint.md file from disk.

        Returns:
            True if a record was deleted, False if nothing existed.
        """
        result = self.supabase.table(TABLE).delete().eq("project_id", project_id).execute()
        deleted = bool(result.data)
        if deleted:
            logger.info(f"LeaveOff point deleted | project_id={project_id}")

        if project_path:
            file_path = os.path.join(project_path, KNOWLEDGE_DIR, FILENAME)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"LeaveOffPoint.md removed | path={file_path}")
            except Exception:
                logger.error(f"Failed to remove LeaveOffPoint.md | path={file_path} | project_id={project_id}", exc_info=True)

        return deleted
