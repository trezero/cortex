"""Extension sync service.

Compares local extension state against the Archon registry,
resolves pending actions, and detects drift between
what a system has installed and what the registry expects.
"""

from datetime import datetime, timezone
from typing import Any

from ...config.logfire_config import get_logger

logger = get_logger(__name__)

SYSTEM_EXTENSIONS_TABLE = "archon_system_extensions"
REGISTRATIONS_TABLE = "archon_project_system_registrations"

# Seconds of tolerance when comparing local file mtime against archon updated_at.
# Guards against minor clock skew between machines.
_CLOCK_SKEW_SECONDS = 5


def _compute_direction(local_mtime: float | int | None, archon_updated_at: str | None) -> str:
    """Determine which copy of an extension is newer based on timestamps.

    Returns one of:
      "local_newer"   — local file mtime is meaningfully later than Archon's updated_at
      "archon_newer"  — Archon's updated_at is meaningfully later than local file mtime
      "conflict"      — timestamps are within clock-skew threshold (genuine conflict)
      "unknown"       — one or both timestamps are missing or unparseable
    """
    if local_mtime is None or not archon_updated_at:
        return "unknown"
    try:
        archon_ts = datetime.fromisoformat(archon_updated_at.replace("Z", "+00:00")).timestamp()
        local_ts = float(local_mtime)
        if local_ts > archon_ts + _CLOCK_SKEW_SECONDS:
            return "local_newer"
        if archon_ts > local_ts + _CLOCK_SKEW_SECONDS:
            return "archon_newer"
        return "conflict"
    except (ValueError, TypeError, AttributeError):
        return "unknown"


class ExtensionSyncService:
    """Handles sync logic between local systems and the Archon extension registry."""

    def __init__(self, supabase_client=None):
        """Initialize with an optional Supabase client.

        When *supabase_client* is ``None`` the global client is
        fetched lazily so the service can be instantiated before
        environment variables are loaded.
        """
        if supabase_client is None:
            from ...utils import get_supabase_client

            supabase_client = get_supabase_client()
        self.supabase_client = supabase_client

    # ── Sync Report ────────────────────────────────────────────────────────

    def compute_sync_report(
        self,
        local_extensions: list[dict[str, Any]],
        archon_extensions: list[dict[str, Any]],
        system_extensions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compare local extensions against Archon state and return a sync report.

        Args:
            local_extensions: [{name, content_hash, local_mtime?}] from the client's disk.
                local_mtime is a Unix timestamp (seconds) of the file's last modification.
            archon_extensions: Full extension records from archon_extensions table.
            system_extensions: Records from archon_system_extensions for this system+project.

        Returns:
            Sync report with keys: in_sync, local_changes, pending_install,
            pending_remove, unknown_local.

            Each local_changes item includes:
              direction: "local_newer" | "archon_newer" | "conflict" | "unknown"
              local_mtime: Unix timestamp from the client (or None)
              archon_updated_at: ISO timestamp from the Archon record (or None)
        """
        archon_by_name: dict[str, dict[str, Any]] = {s["name"]: s for s in archon_extensions}
        system_by_extension_id: dict[str, dict[str, Any]] = {s["extension_id"]: s for s in system_extensions}
        local_by_name: dict[str, dict[str, Any]] = {s["name"]: s for s in local_extensions}

        in_sync: list[str] = []
        local_changes: list[dict[str, Any]] = []
        pending_install: list[dict[str, Any]] = []
        pending_remove: list[dict[str, Any]] = []
        unknown_local: list[dict[str, Any]] = []

        # Classify each local extension against the Archon registry
        for local in local_extensions:
            name = local["name"]
            archon_extension = archon_by_name.get(name)

            if not archon_extension:
                unknown_local.append({"name": name, "content_hash": local["content_hash"]})
                continue

            # is_required extensions are system-critical and must never be auto-updated
            # or removed by sync — always treat as in_sync regardless of content hash
            if archon_extension.get("is_required"):
                in_sync.append(name)
                continue

            sys_extension = system_by_extension_id.get(archon_extension["id"])

            if sys_extension and sys_extension["status"] == "pending_remove":
                pending_remove.append({
                    "extension_id": archon_extension["id"],
                    "name": name,
                })
            elif local["content_hash"] == archon_extension["content_hash"]:
                in_sync.append(name)
            else:
                local_mtime = local.get("local_mtime")
                archon_updated_at = archon_extension.get("updated_at")
                local_changes.append({
                    "name": name,
                    "extension_id": archon_extension["id"],
                    "local_hash": local["content_hash"],
                    "archon_hash": archon_extension["content_hash"],
                    "direction": _compute_direction(local_mtime, archon_updated_at),
                    "local_mtime": local_mtime,
                    "archon_updated_at": archon_updated_at,
                })

        # Detect pending installs: extensions in Archon with pending_install status
        # that are NOT already present locally (skip is_required extensions)
        for sys_extension in system_extensions:
            if sys_extension["status"] != "pending_install":
                continue
            extension_id = sys_extension["extension_id"]
            archon_extension = next((s for s in archon_extensions if s["id"] == extension_id), None)
            if archon_extension and archon_extension["name"] not in local_by_name:
                if archon_extension.get("is_required"):
                    continue
                pending_install.append({
                    "extension_id": extension_id,
                    "name": archon_extension["name"],
                    "content": archon_extension.get("content", ""),
                })

        return {
            "in_sync": in_sync,
            "local_changes": local_changes,
            "pending_install": pending_install,
            "pending_remove": pending_remove,
            "unknown_local": unknown_local,
        }

    # ── Project-System Registration ────────────────────────────────────────

    def register_system_for_project(self, system_id: str, project_id: str) -> None:
        """Upsert a registration record linking a system to a project.

        Called on every extension sync so the system appears in the project's
        Extensions tab immediately, even before any extensions are installed.
        """
        self.supabase_client.table(REGISTRATIONS_TABLE).upsert(
            {"project_id": project_id, "system_id": system_id, "last_sync_at": "now()"},
            on_conflict="project_id,system_id",
        ).execute()

    def unlink_system_from_project(self, system_id: str, project_id: str) -> bool:
        """Remove a system's association with a project.

        Deletes from archon_project_system_registrations. The system remains
        globally in archon_systems — only the project link is removed.
        Returns True if a record was deleted, False if the association did not exist.
        """
        result = (
            self.supabase_client.table(REGISTRATIONS_TABLE)
            .delete()
            .eq("project_id", project_id)
            .eq("system_id", system_id)
            .execute()
        )
        return len(result.data) > 0

    def get_project_systems(self, project_id: str) -> list[dict[str, Any]]:
        """Get all systems that have synced with a project."""
        result = (
            self.supabase_client.table(REGISTRATIONS_TABLE)
            .select("system_id, archon_systems(*)")
            .eq("project_id", project_id)
            .execute()
        )
        if not result.data:
            return []
        return [row["archon_systems"] for row in result.data if row.get("archon_systems")]

    # ── System Extension Queries ───────────────────────────────────────────

    def get_system_extensions(self, system_id: str, project_id: str) -> list[dict[str, Any]]:
        """Get all extension install records for a system+project pair."""
        result = (
            self.supabase_client.table(SYSTEM_EXTENSIONS_TABLE)
            .select("*")
            .eq("system_id", system_id)
            .eq("project_id", project_id)
            .execute()
        )
        return result.data or []

    def get_system_project_extensions(self, system_id: str, project_id: str) -> list[dict[str, Any]]:
        """Get detailed extension state for a system within a project.

        Joins with archon_extensions to include extension metadata alongside
        install status information.
        """
        result = (
            self.supabase_client.table(SYSTEM_EXTENSIONS_TABLE)
            .select(
                "*, archon_extensions(id, name, display_name, description, current_version,"
                " content_hash, is_required, is_validated, tags)"
            )
            .eq("system_id", system_id)
            .eq("project_id", project_id)
            .execute()
        )
        return result.data or []

    # ── Install Status Management ──────────────────────────────────────────

    def set_install_status(
        self,
        system_id: str,
        extension_id: str,
        project_id: str,
        status: str,
        installed_content_hash: str | None = None,
        installed_version: int | None = None,
        has_local_changes: bool = False,
    ) -> dict[str, Any]:
        """Create or update a system-extension install record.

        Uses upsert on the (system_id, extension_id, project_id) composite key.

        Raises:
            RuntimeError: If the database upsert returns no data.
        """
        data: dict[str, Any] = {
            "system_id": system_id,
            "extension_id": extension_id,
            "project_id": project_id,
            "status": status,
            "installed_content_hash": installed_content_hash,
            "installed_version": installed_version,
            "has_local_changes": has_local_changes,
        }
        result = (
            self.supabase_client.table(SYSTEM_EXTENSIONS_TABLE)
            .upsert(data, on_conflict="system_id,extension_id,project_id")
            .execute()
        )
        if not result.data:
            raise RuntimeError(f"Failed to set install status for extension {extension_id} on system {system_id}")
        return result.data[0]

    # ── Queue Operations ───────────────────────────────────────────────────

    def queue_install(self, system_ids: list[str], extension_id: str, project_id: str) -> int:
        """Queue an extension for installation on multiple systems.

        Returns the number of systems queued.
        """
        count = 0
        for system_id in system_ids:
            self.set_install_status(system_id, extension_id, project_id, status="pending_install")
            count += 1
        return count

    def queue_remove(self, system_ids: list[str], extension_id: str, project_id: str) -> int:
        """Queue an extension for removal on multiple systems.

        Returns the number of systems queued.
        """
        count = 0
        for system_id in system_ids:
            self.set_install_status(system_id, extension_id, project_id, status="pending_remove")
            count += 1
        return count
