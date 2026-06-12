"""System registration service for machine fingerprint tracking.

Manages the cortex_systems table, which records each machine that
interacts with the extensions management system.  A system is identified
by a unique fingerprint derived from hardware/OS attributes.
"""

from datetime import UTC, datetime
from typing import Any

from ...config.logfire_config import get_logger

logger = get_logger(__name__)

TABLE = "cortex_systems"


class SystemService:
    """CRUD operations for registered systems (machines)."""

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

    # ── Lookup ────────────────────────────────────────────────────────────

    def find_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        """Return the system record matching *fingerprint*, or ``None``."""
        response = (
            self.supabase_client.table(TABLE)
            .select("*")
            .eq("fingerprint", fingerprint)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    def get_system(self, system_id: str) -> dict[str, Any] | None:
        """Return a single system by primary key, or ``None``."""
        response = (
            self.supabase_client.table(TABLE)
            .select("*")
            .eq("id", system_id)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    # ── List ──────────────────────────────────────────────────────────────

    def list_systems(self) -> list[dict[str, Any]]:
        """Return all registered systems ordered by creation date."""
        response = (
            self.supabase_client.table(TABLE)
            .select("*")
            .order("created_at")
            .execute()
        )
        return response.data

    # ── Create ────────────────────────────────────────────────────────────

    def register_system(
        self,
        fingerprint: str,
        name: str,
        hostname: str | None = None,
        os: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new system record and return it.

        Raises ``RuntimeError`` if the database returns an empty response.
        """
        record: dict[str, Any] = {
            "fingerprint": fingerprint,
            "name": name,
            "hostname": hostname,
            "os": os,
        }

        response = self.supabase_client.table(TABLE).insert(record).execute()

        if not response.data:
            raise RuntimeError(
                f"Failed to register system with fingerprint '{fingerprint}': "
                "database returned no data"
            )

        system = response.data[0]
        logger.info(f"Registered system id={system['id']} fingerprint={fingerprint}")
        return system

    # ── Update ────────────────────────────────────────────────────────────

    def update_last_seen(self, system_id: str) -> dict[str, Any] | None:
        """Touch the *last_seen_at* timestamp for *system_id*."""
        response = (
            self.supabase_client.table(TABLE)
            .update({"last_seen_at": datetime.now(UTC).isoformat()})
            .eq("id", system_id)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    def update_system(
        self,
        system_id: str,
        name: str | None = None,
        hostname: str | None = None,
    ) -> dict[str, Any] | None:
        """Update mutable fields on a system record.

        Only fields that are explicitly passed (not ``None``) are included
        in the update payload.  Returns the updated record or ``None``
        if the system was not found.
        """
        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = name
        if hostname is not None:
            updates["hostname"] = hostname

        if not updates:
            return self.get_system(system_id)

        response = (
            self.supabase_client.table(TABLE)
            .update(updates)
            .eq("id", system_id)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    # ── Delete ────────────────────────────────────────────────────────────

    def delete_system(self, system_id: str) -> bool:
        """Delete a system by ID.  Returns ``True`` if a row was removed."""
        response = (
            self.supabase_client.table(TABLE)
            .delete()
            .eq("id", system_id)
            .execute()
        )
        return bool(response.data)
