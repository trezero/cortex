"""Reviewed agent targets and deterministic extension reconciliation."""

import re
from datetime import UTC, datetime
from typing import Any

from ...config.logfire_config import get_logger
from .extension_service import ExtensionService
from .extension_validation_service import ExtensionValidationService

logger = get_logger(__name__)

TARGETS_TABLE = "cortex_extension_targets"
SUPPORTED_MODES = {"direct", "adapted"}
SUPPORTED_SCOPES = {"repository", "global"}
_AGENT_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class ExtensionTargetService:
    """Store and resolve reviewed projections of neutral skill content."""

    def __init__(self, supabase_client=None):
        if supabase_client is None:
            from ...utils import get_supabase_client

            supabase_client = get_supabase_client()
        self.supabase_client = supabase_client

    @staticmethod
    def compatibility_state(extension: dict[str, Any], target: dict[str, Any] | None) -> str:
        """Return pending, stale, invalid, or current for an agent target."""
        if target is None:
            return "pending"
        if target.get("mode") not in SUPPORTED_MODES or target.get("scope") not in SUPPORTED_SCOPES:
            return "invalid"
        if not target.get("payload_content") or not target.get("payload_hash"):
            return "invalid"
        source_digest = extension.get("source_digest") or ExtensionService.compute_package_hash(
            extension["content"],
            extension.get("source_files"),
        )
        if target.get("reviewed_source_hash") != source_digest:
            return "stale"
        if target.get("reviewed_extension_hash") != extension.get("content_hash"):
            return "stale"
        try:
            expected_payload_hash = ExtensionService.compute_package_hash(
                target["payload_content"],
                target.get("payload_files"),
            )
        except ValueError:
            return "invalid"
        if target.get("payload_hash") != expected_payload_hash:
            return "invalid"
        return "current"

    def list_targets(
        self,
        extension_ids: list[str] | None = None,
        agent: str | None = None,
    ) -> list[dict[str, Any]]:
        query = self.supabase_client.table(TARGETS_TABLE).select("*")
        if extension_ids is not None:
            if not extension_ids:
                return []
            query = query.in_("extension_id", extension_ids)
        if agent is not None:
            query = query.eq("agent", agent)
        response = query.order("agent").execute()
        return response.data or []

    def get_target(self, extension_id: str, agent: str) -> dict[str, Any] | None:
        response = (
            self.supabase_client.table(TARGETS_TABLE)
            .select("*")
            .eq("extension_id", extension_id)
            .eq("agent", agent)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def review_target(
        self,
        extension: dict[str, Any],
        agent: str,
        mode: str,
        scope: str,
        reviewed_by: str,
        adapted_content: str | None = None,
        adapted_files: dict[str, str] | None = None,
        expected_source_hash: str | None = None,
    ) -> dict[str, Any]:
        """Record a reviewed payload snapshot against the current source hash."""
        if extension.get("type", "skill") != "skill":
            raise ValueError("Agent targets are supported only for skill extensions")
        if not _AGENT_RE.fullmatch(agent):
            raise ValueError("agent must use lowercase letters, digits, and hyphens")
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"Unsupported target mode: {mode}")
        if scope not in SUPPORTED_SCOPES:
            raise ValueError(f"Unsupported target scope: {scope}")

        source_hash = extension.get("source_digest") or ExtensionService.compute_package_hash(
            extension["content"],
            extension.get("source_files"),
        )
        if expected_source_hash is not None and expected_source_hash != source_hash:
            raise ValueError("Extension source changed during review; reload and review the new source")

        if mode == "direct":
            if adapted_content is not None or adapted_files is not None:
                raise ValueError("adapted content or files are not allowed in direct mode")
            payload_content = extension["content"]
            payload_files = ExtensionService.validate_package_files(extension.get("source_files"))
        else:
            if not adapted_content:
                raise ValueError("adapted_content is required in adapted mode")
            validation = ExtensionValidationService().validate(
                adapted_content,
                existing_name=extension.get("name"),
            )
            if not validation["valid"]:
                raise ValueError(f"Adapted content validation failed: {validation['errors']}")
            payload_content = adapted_content
            payload_files = ExtensionService.validate_package_files(adapted_files)

        now = datetime.now(UTC).isoformat()
        row = {
            "extension_id": extension["id"],
            "agent": agent,
            "mode": mode,
            "scope": scope,
            "reviewed_source_hash": source_hash,
            "reviewed_extension_hash": extension["content_hash"],
            "payload_content": payload_content,
            "payload_files": payload_files,
            "payload_hash": ExtensionService.compute_package_hash(payload_content, payload_files),
            "reviewed_by": reviewed_by,
            "reviewed_at": now,
            "updated_at": now,
        }
        response = (
            self.supabase_client.table(TARGETS_TABLE)
            .upsert(row, on_conflict="extension_id,agent")
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"Failed to save {agent} target for extension {extension['id']}")
        return response.data[0]

    def delete_target(self, extension_id: str, agent: str) -> bool:
        response = (
            self.supabase_client.table(TARGETS_TABLE)
            .delete()
            .eq("extension_id", extension_id)
            .eq("agent", agent)
            .execute()
        )
        return bool(response.data)

    def attach_targets(
        self,
        extensions: list[dict[str, Any]],
        agent: str | None = None,
    ) -> list[dict[str, Any]]:
        """Attach target metadata and derived compatibility state."""
        targets = self.list_targets([extension["id"] for extension in extensions], agent=agent)
        by_extension: dict[str, list[dict[str, Any]]] = {}
        for target in targets:
            by_extension.setdefault(target["extension_id"], []).append(target)

        result: list[dict[str, Any]] = []
        for extension in extensions:
            decorated: list[dict[str, Any]] = []
            for target in by_extension.get(extension["id"], []):
                decorated.append(
                    {
                        **target,
                        "compatibility_state": self.compatibility_state(extension, target),
                    }
                )
            result.append({**extension, "targets": decorated})
        return result

    def compute_sync_report(
        self,
        extensions: list[dict[str, Any]],
        targets: list[dict[str, Any]],
        local_extensions: list[dict[str, Any]],
        system_extensions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a model-free reconciliation plan for one agent and project."""
        target_by_extension = {target["extension_id"]: target for target in targets}
        local_by_name: dict[str, dict[str, Any]] = {}
        duplicate_names: set[str] = set()
        for item in local_extensions:
            if item["name"] in local_by_name:
                duplicate_names.add(item["name"])
            else:
                local_by_name[item["name"]] = item
        system_by_extension = {item["extension_id"]: item for item in system_extensions}
        known_names = {extension["name"] for extension in extensions}

        states: list[dict[str, Any]] = []
        for extension in extensions:
            target = target_by_extension.get(extension["id"])
            review_state = self.compatibility_state(extension, target)
            local = local_by_name.get(extension["name"])
            system_state = system_by_extension.get(extension["id"])
            desired_status = system_state.get("status") if system_state else "pending_install"
            action = "none"
            installation = "not-installed"

            if extension["name"] in duplicate_names:
                installation = "conflict"
            elif desired_status in {"pending_remove", "removed"}:
                action = "remove" if local else "none"
                installation = "pending-remove" if local else "removed"
            elif local and not local.get("managed", False):
                installation = "conflict"
            elif review_state == "current" and target is not None:
                if local is None:
                    action = "install"
                elif (
                    local.get("payload_hash") == target["payload_hash"]
                    and local.get("reviewed_source_hash") == target["reviewed_source_hash"]
                    and local.get("scope") == target["scope"]
                ):
                    installation = "current"
                else:
                    action = "install"
                    installation = "outdated"
            elif local:
                installation = "last-reviewed"

            state = {
                "extension_id": extension["id"],
                "name": extension["name"],
                "review_state": review_state,
                "installation": installation,
                "action": action,
                "desired_status": desired_status,
            }
            if target is not None:
                state["target"] = target
            states.append(state)

        unknown_local = [
            {"name": item["name"], "payload_hash": item.get("payload_hash")}
            for item in local_extensions
            if item["name"] not in known_names
        ]
        return {
            "states": states,
            "unknown_local": unknown_local,
            "duplicate_names": sorted(duplicate_names),
        }
