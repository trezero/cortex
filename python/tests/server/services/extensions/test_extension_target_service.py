"""Tests for reviewed agent targets and deterministic reconciliation."""

from unittest.mock import MagicMock

import pytest

from src.server.services.extensions.extension_service import ExtensionService
from src.server.services.extensions.extension_target_service import ExtensionTargetService

SOURCE = """---
name: test-skill
description: A sufficiently descriptive test skill.
---
# Test

Use this test workflow.
"""


@pytest.fixture
def service():
    return ExtensionTargetService(supabase_client=MagicMock())


def extension(content: str = SOURCE) -> dict:
    return {
        "id": "ext-1",
        "name": "test-skill",
        "type": "skill",
        "content": content,
        "content_hash": ExtensionService.compute_content_hash(content),
        "current_version": 1,
    }


def target(source: dict, *, mode: str = "direct", scope: str = "repository", payload: str | None = None) -> dict:
    content = payload or source["content"]
    return {
        "extension_id": source["id"],
        "agent": "codex",
        "mode": mode,
        "scope": scope,
        "reviewed_source_hash": ExtensionService.compute_package_hash(
            source["content"],
            source.get("source_files"),
        ),
        "reviewed_extension_hash": source["content_hash"],
        "payload_content": content,
        "payload_files": {},
        "payload_hash": ExtensionService.compute_package_hash(content),
    }


class TestCompatibility:
    def test_pending_without_target(self, service):
        assert service.compatibility_state(extension(), None) == "pending"

    def test_direct_target_is_current(self, service):
        source = extension()
        assert service.compatibility_state(source, target(source)) == "current"

    def test_adapted_target_is_current(self, service):
        source = extension()
        adapted = SOURCE.replace("Use this test workflow.", "Use this Codex workflow.")
        assert service.compatibility_state(source, target(source, mode="adapted", payload=adapted)) == "current"

    def test_source_digest_change_is_stale(self, service):
        source = extension()
        reviewed = target(source)
        changed = extension(SOURCE + "\nChanged.\n")
        assert service.compatibility_state(changed, reviewed) == "stale"

    def test_tampered_payload_is_invalid(self, service):
        source = extension()
        reviewed = target(source)
        reviewed["payload_content"] += "tampered"
        assert service.compatibility_state(source, reviewed) == "invalid"


class TestReconciliation:
    def test_current_repository_install(self, service):
        source = extension()
        reviewed = target(source)
        local = [{
            "name": source["name"],
            "managed": True,
            "scope": "repository",
            "payload_hash": reviewed["payload_hash"],
            "reviewed_source_hash": reviewed["reviewed_source_hash"],
        }]
        report = service.compute_sync_report([source], [reviewed], local, [])
        assert report["states"][0]["installation"] == "current"
        assert report["states"][0]["action"] == "none"

    def test_global_scope_mismatch_requires_install(self, service):
        source = extension()
        reviewed = target(source, scope="global")
        local = [{
            "name": source["name"],
            "managed": True,
            "scope": "repository",
            "payload_hash": reviewed["payload_hash"],
            "reviewed_source_hash": reviewed["reviewed_source_hash"],
        }]
        report = service.compute_sync_report([source], [reviewed], local, [])
        assert report["states"][0]["installation"] == "outdated"
        assert report["states"][0]["action"] == "install"

    def test_unmanaged_name_is_conflict(self, service):
        source = extension()
        report = service.compute_sync_report(
            [source],
            [target(source)],
            [{"name": source["name"], "managed": False, "scope": "repository"}],
            [],
        )
        assert report["states"][0]["installation"] == "conflict"
        assert report["states"][0]["action"] == "none"

    def test_duplicate_name_is_conflict(self, service):
        source = extension()
        local = [
            {"name": source["name"], "managed": True, "scope": "repository"},
            {"name": source["name"], "managed": True, "scope": "global"},
        ]
        report = service.compute_sync_report([source], [target(source)], local, [])
        assert report["duplicate_names"] == [source["name"]]
        assert report["states"][0]["installation"] == "conflict"

    def test_pending_remove_is_reported(self, service):
        source = extension()
        local = [{"name": source["name"], "managed": True, "scope": "repository"}]
        system = [{"extension_id": source["id"], "status": "pending_remove"}]
        report = service.compute_sync_report([source], [target(source)], local, system)
        assert report["states"][0]["action"] == "remove"
