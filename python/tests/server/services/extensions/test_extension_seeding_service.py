"""
Unit tests for ExtensionSeedingService.

Tests upsert logic (create / skip / update) for bundled SKILL.md files,
using tmp_path for a temporary extensions directory and MagicMock for ExtensionService.
"""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from src.server.services.extensions.extension_seeding_service import ExtensionSeedingService
from src.server.services.extensions.extension_service import ExtensionService

# ── Fixtures & Helpers ───────────────────────────────────────────────────────

SAMPLE_SKILL_MD = textwrap.dedent("""\
    ---
    name: archon-memory
    description: Manage long-term knowledge memory via Archon RAG.
    ---

    # Archon Memory

    Some content here.
""")


def _make_skill_dir(base: Path, skill_name: str, content: str) -> Path:
    """Create a skill subdirectory with a SKILL.md file."""
    skill_dir = base / skill_name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


@pytest.fixture
def mock_extension_service():
    """Return a MagicMock standing in for ExtensionService."""
    return MagicMock(spec=ExtensionService)


@pytest.fixture
def service(mock_extension_service):
    """Create an ExtensionSeedingService with the mocked ExtensionService."""
    return ExtensionSeedingService(extension_service=mock_extension_service)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSeedOneCreatePath:
    def test_creates_new_extension_when_not_in_registry(self, service, mock_extension_service, tmp_path):
        """When find_by_name returns None, create_extension is called with correct args."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "abc123", "name": "archon-memory"}

        _make_skill_dir(tmp_path, "archon-memory", SAMPLE_SKILL_MD)

        counts = service.seed_extensions(tmp_path)

        mock_extension_service.find_by_name.assert_called_once_with("archon-memory")
        mock_extension_service.create_extension.assert_called_once_with(
            "archon-memory",
            "Manage long-term knowledge memory via Archon RAG.",
            SAMPLE_SKILL_MD,
            created_by="archon-seeder",
        )
        assert counts == {"created": 1, "updated": 0, "skipped": 0, "errors": 0}


class TestSeedOneSkipPath:
    def test_skips_extension_when_hash_unchanged(self, service, mock_extension_service, tmp_path):
        """When the content hash matches the registry, neither create nor update is called."""
        content_hash = ExtensionService.compute_content_hash(SAMPLE_SKILL_MD)
        mock_extension_service.find_by_name.return_value = {
            "id": "abc123",
            "name": "archon-memory",
            "content_hash": content_hash,
            "current_version": 1,
        }

        _make_skill_dir(tmp_path, "archon-memory", SAMPLE_SKILL_MD)

        counts = service.seed_extensions(tmp_path)

        mock_extension_service.create_extension.assert_not_called()
        mock_extension_service.update_extension.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "skipped": 1, "errors": 0}


class TestSeedOneUpdatePath:
    def test_updates_extension_when_hash_changed(self, service, mock_extension_service, tmp_path):
        """When the content hash differs, update_extension is called with new_version bumped by 1."""
        mock_extension_service.find_by_name.return_value = {
            "id": "abc123",
            "name": "archon-memory",
            "content_hash": "old-hash-does-not-match",
            "current_version": 2,
        }
        mock_extension_service.update_extension.return_value = {"id": "abc123"}

        _make_skill_dir(tmp_path, "archon-memory", SAMPLE_SKILL_MD)

        counts = service.seed_extensions(tmp_path)

        mock_extension_service.update_extension.assert_called_once_with(
            "abc123",
            SAMPLE_SKILL_MD,
            new_version=3,
            updated_by="archon-seeder",
            description="Manage long-term knowledge memory via Archon RAG.",
        )
        mock_extension_service.create_extension.assert_not_called()
        assert counts == {"created": 0, "updated": 1, "skipped": 0, "errors": 0}


class TestSeedSkipsDirectoryWithoutSkillMd:
    def test_skips_directory_without_skill_md(self, service, mock_extension_service, tmp_path):
        """A subdirectory that contains no SKILL.md is silently skipped."""
        empty_dir = tmp_path / "no-skill-here"
        empty_dir.mkdir()

        counts = service.seed_extensions(tmp_path)

        mock_extension_service.find_by_name.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "skipped": 0, "errors": 0}


class TestSeedSkipsSkillWithNoName:
    def test_skips_skill_with_no_name_in_frontmatter(self, service, mock_extension_service, tmp_path):
        """A SKILL.md that lacks a 'name' field in frontmatter is skipped (no DB call)."""
        no_name_md = textwrap.dedent("""\
            # Just a plain markdown file

            No frontmatter at all.
        """)
        _make_skill_dir(tmp_path, "nameless-skill", no_name_md)

        counts = service.seed_extensions(tmp_path)

        mock_extension_service.find_by_name.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "skipped": 1, "errors": 0}


class TestSeedMultipleSkills:
    def test_seeds_multiple_extensions(self, service, mock_extension_service, tmp_path):
        """All skills in subdirectories are processed; create_extension called once per new extension."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "new-id"}

        for skill_name in ("skill-alpha", "skill-beta", "skill-gamma"):
            skill_md = textwrap.dedent(f"""\
                ---
                name: {skill_name}
                description: Description for {skill_name}.
                ---

                Content for {skill_name}.
            """)
            _make_skill_dir(tmp_path, skill_name, skill_md)

        counts = service.seed_extensions(tmp_path)

        assert mock_extension_service.create_extension.call_count == 3
        assert counts == {"created": 3, "updated": 0, "skipped": 0, "errors": 0}


class TestSeedContinuesOnError:
    def test_continues_on_error_for_one_skill(self, service, mock_extension_service, tmp_path):
        """An error processing one skill is caught; remaining skills are still processed."""
        # Two skills: first raises, second succeeds
        call_count = 0

        def find_by_name_side_effect(name):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB connection lost")
            return None

        mock_extension_service.find_by_name.side_effect = find_by_name_side_effect
        mock_extension_service.create_extension.return_value = {"id": "new-id"}

        for skill_name in ("skill-one", "skill-two"):
            skill_md = textwrap.dedent(f"""\
                ---
                name: {skill_name}
                description: A skill.
                ---

                Content.
            """)
            _make_skill_dir(tmp_path, skill_name, skill_md)

        counts = service.seed_extensions(tmp_path)

        assert counts["errors"] == 1
        assert counts["created"] == 1
        assert counts["created"] + counts["errors"] == 2


class TestDefaultDirResolvesCorrectly:
    def test_default_dir_resolves_correctly(self, service):
        """default_extensions_dir() should end with integrations/claude-code/extensions."""
        default_dir = service.default_extensions_dir()
        parts = default_dir.parts
        assert parts[-3:] == ("integrations", "claude-code", "extensions")


# ── Command Seeding Tests ────────────────────────────────────────────────────

SAMPLE_COMMAND_NO_FRONTMATTER = textwrap.dedent("""\
    # Archon Setup — Register This Machine

    Connect this machine to Archon.

    ## Phase 0: Health Check

    Call `health_check()` via the Archon MCP tool.
""")

SAMPLE_COMMAND_WITH_FRONTMATTER = textwrap.dedent("""\
    ---
    name: prime
    description: Prime Claude Code with deep context.
    argument-hint: <service> <focus>
    ---

    # Prime

    You're about to work on the codebase.
""")


def _make_command_file(base: Path, filename: str, content: str, group: str | None = None) -> Path:
    """Create a command .md file at base/filename or base/group/filename."""
    if group:
        target_dir = base / group
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = base
    filepath = target_dir / filename
    filepath.write_text(content)
    return filepath


class TestSeedCommandsFlatFile:
    def test_creates_flat_command_with_correct_args(self, service, mock_extension_service, tmp_path):
        """A flat (root-level) .md file is seeded as a command with no group."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "cmd1", "name": "archon-setup"}

        _make_command_file(tmp_path, "archon-setup.md", SAMPLE_COMMAND_NO_FRONTMATTER)

        counts = service.seed_commands(tmp_path)

        mock_extension_service.find_by_name.assert_called_once_with("archon-setup")
        mock_extension_service.create_extension.assert_called_once_with(
            "archon-setup",
            "Archon Setup — Register This Machine",
            SAMPLE_COMMAND_NO_FRONTMATTER,
            created_by="archon-seeder",
            type="command",
            plugin_manifest={"command_group": None, "filename": "archon-setup.md"},
        )
        assert counts == {"created": 1, "updated": 0, "skipped": 0, "errors": 0}


class TestSeedCommandsGroupedFile:
    def test_creates_grouped_command_with_group_prefix_stripped(self, service, mock_extension_service, tmp_path):
        """A file in archon/ whose stem already starts with 'archon' keeps its stem as name."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "cmd2", "name": "archon-prime"}

        _make_command_file(tmp_path, "archon-prime.md", SAMPLE_COMMAND_WITH_FRONTMATTER, group="archon")

        counts = service.seed_commands(tmp_path)

        mock_extension_service.find_by_name.assert_called_once_with("archon-prime")
        mock_extension_service.create_extension.assert_called_once_with(
            "archon-prime",
            "Prime Claude Code with deep context.",
            SAMPLE_COMMAND_WITH_FRONTMATTER,
            created_by="archon-seeder",
            type="command",
            plugin_manifest={"command_group": "archon", "filename": "archon-prime.md"},
        )
        assert counts == {"created": 1, "updated": 0, "skipped": 0, "errors": 0}


class TestSeedCommandsGroupPrefixed:
    def test_creates_group_prefixed_name_when_stem_has_different_prefix(
        self, service, mock_extension_service, tmp_path
    ):
        """A file in agent-work-orders/ whose stem is 'commit' gets name 'agent-work-orders-commit'."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "cmd3", "name": "agent-work-orders-commit"}

        content = textwrap.dedent("""\
            # Commit

            Create a git commit.
        """)
        _make_command_file(tmp_path, "commit.md", content, group="agent-work-orders")

        counts = service.seed_commands(tmp_path)

        mock_extension_service.find_by_name.assert_called_once_with("agent-work-orders-commit")
        mock_extension_service.create_extension.assert_called_once_with(
            "agent-work-orders-commit",
            "Commit",
            content,
            created_by="archon-seeder",
            type="command",
            plugin_manifest={"command_group": "agent-work-orders", "filename": "commit.md"},
        )
        assert counts == {"created": 1, "updated": 0, "skipped": 0, "errors": 0}


class TestSeedCommandsSkipUnchanged:
    def test_skips_command_when_hash_unchanged(self, service, mock_extension_service, tmp_path):
        """When the content hash matches the registry entry, no create or update is called."""
        content_hash = ExtensionService.compute_content_hash(SAMPLE_COMMAND_NO_FRONTMATTER)
        mock_extension_service.find_by_name.return_value = {
            "id": "cmd1",
            "name": "archon-setup",
            "content_hash": content_hash,
            "current_version": 1,
        }

        _make_command_file(tmp_path, "archon-setup.md", SAMPLE_COMMAND_NO_FRONTMATTER)

        counts = service.seed_commands(tmp_path)

        mock_extension_service.create_extension.assert_not_called()
        mock_extension_service.update_extension.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "skipped": 1, "errors": 0}


class TestSeedCommandsUpdateChanged:
    def test_updates_command_when_hash_differs(self, service, mock_extension_service, tmp_path):
        """When the content hash differs from the registry, update_extension is called."""
        mock_extension_service.find_by_name.return_value = {
            "id": "cmd1",
            "name": "archon-setup",
            "content_hash": "old-hash-does-not-match",
            "current_version": 2,
        }
        mock_extension_service.update_extension.return_value = {"id": "cmd1"}

        _make_command_file(tmp_path, "archon-setup.md", SAMPLE_COMMAND_NO_FRONTMATTER)

        counts = service.seed_commands(tmp_path)

        mock_extension_service.update_extension.assert_called_once_with(
            "cmd1",
            SAMPLE_COMMAND_NO_FRONTMATTER,
            new_version=3,
            updated_by="archon-seeder",
            description="Archon Setup — Register This Machine",
        )
        mock_extension_service.create_extension.assert_not_called()
        assert counts == {"created": 0, "updated": 1, "skipped": 0, "errors": 0}


class TestSeedCommandsEmptyDir:
    def test_returns_zero_counts_for_empty_dir(self, service, mock_extension_service, tmp_path):
        """An empty commands directory produces zero counts and no DB calls."""
        counts = service.seed_commands(tmp_path)

        mock_extension_service.find_by_name.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "skipped": 0, "errors": 0}


class TestDefaultCommandsDirResolvesCorrectly:
    def test_default_commands_dir_resolves_correctly(self, service):
        """default_commands_dir() should end with integrations/claude-code/commands."""
        default_dir = service.default_commands_dir()
        parts = default_dir.parts
        assert parts[-3:] == ("integrations", "claude-code", "commands")
