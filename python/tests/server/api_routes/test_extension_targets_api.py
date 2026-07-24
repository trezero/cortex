"""API contract tests for agent targets and agent-aware system registration."""

import asyncio
from unittest.mock import patch

from src.server.api_routes.extensions_api import (
    RegisterSystemRequest,
    ReviewExtensionTargetRequest,
    register_system,
    review_extension_target,
)


def test_register_system_defaults_to_claude():
    system = {"id": "sys-1", "fingerprint": "fp", "agent": "claude"}
    with patch("src.server.api_routes.extensions_api.SystemService") as service_class:
        service = service_class.return_value
        service.find_by_fingerprint.return_value = None
        service.register_system.return_value = system

        result = asyncio.run(register_system(RegisterSystemRequest(fingerprint="fp", name="host")))

    service.find_by_fingerprint.assert_called_once_with("fp", "claude")
    service.register_system.assert_called_once_with(
        fingerprint="fp",
        name="host",
        hostname=None,
        os=None,
        agent="claude",
    )
    assert result["system"]["agent"] == "claude"


def test_review_codex_target_uses_exact_source_digest():
    extension = {
        "id": "ext-1",
        "name": "example",
        "content": "content",
        "content_hash": "source-hash",
        "type": "skill",
    }
    target = {
        "extension_id": "ext-1",
        "agent": "codex",
        "mode": "direct",
        "scope": "repository",
    }
    with (
        patch("src.server.api_routes.extensions_api.ExtensionService") as extension_class,
        patch("src.server.api_routes.extensions_api.ExtensionTargetService") as target_class,
    ):
        extension_class.return_value.get_extension.return_value = extension
        target_service = target_class.return_value
        target_service.review_target.return_value = target
        target_service.compatibility_state.return_value = "current"

        result = asyncio.run(
            review_extension_target(
                "ext-1",
                "codex",
                ReviewExtensionTargetRequest(
                    mode="direct",
                    scope="repository",
                    reviewed_by="tester",
                    expected_source_hash="source-hash",
                ),
            )
        )

    target_service.review_target.assert_called_once_with(
        extension=extension,
        agent="codex",
        mode="direct",
        scope="repository",
        reviewed_by="tester",
        adapted_content=None,
        adapted_files=None,
        expected_source_hash="source-hash",
    )
    assert result["compatibility_state"] == "current"


def test_register_same_fingerprint_for_codex_is_separate_agent():
    with patch("src.server.api_routes.extensions_api.SystemService") as service_class:
        service = service_class.return_value
        service.find_by_fingerprint.return_value = None
        service.register_system.return_value = {"id": "sys-codex", "fingerprint": "fp", "agent": "codex"}

        asyncio.run(
            register_system(
                RegisterSystemRequest(
                    fingerprint="fp",
                    name="host Codex",
                    agent="codex",
                )
            )
        )

    service.find_by_fingerprint.assert_called_once_with("fp", "codex")
