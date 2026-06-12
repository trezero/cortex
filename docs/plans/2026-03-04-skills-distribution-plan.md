# Skills Distribution System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable any machine with the Cortex MCP server connected to bootstrap all skills automatically, auto-seed the registry on server startup, and provide remove/unlink actions in the Skills tab UI.

**Architecture:** A new `cortex-bootstrap` skill triggers `manage_skills(action="bootstrap")` via MCP, which fetches all skills with full content and registers the system. On server startup a `SkillSeedingService` scans `integrations/claude-code/skills/*/SKILL.md` and upserts any new or changed skills into `cortex_skills`. The UI gains two new destructive actions: Remove skill (for a system) and Unlink system (from a project).

**Tech Stack:** Python 3.12, FastAPI, Supabase (via postgrest-py), httpx, React 18, TypeScript, TanStack Query v5, Tailwind, Biome

---

## Task 1: Write `cortex-bootstrap` SKILL.md

**Files:**
- Create: `integrations/claude-code/skills/cortex-bootstrap/SKILL.md`

**Step 1: Create the directory and file**

```bash
mkdir -p integrations/claude-code/skills/cortex-bootstrap
```

Write `integrations/claude-code/skills/cortex-bootstrap/SKILL.md`:

```markdown
---
name: cortex-bootstrap
description: Bootstrap Cortex skills onto this machine. Fetches all skills from the Cortex registry and installs them to ~/.claude/skills/, registers this system, and links it to the current project. Run once on any new machine to set up Cortex integration. Use when the user says "bootstrap cortex", "install cortex skills", "set up cortex", or "run cortex bootstrap".
---

# Cortex Bootstrap — Skills Installer

Fetches all Cortex skills from the registry and installs them to `~/.claude/skills/`. Registers this machine as a system and links it to the current project.

**Invocation:** `/cortex-bootstrap`

---

## Phase 0: Health Check

```
health_check()
```

If Cortex is unreachable:
> "Cortex server is not reachable. Ensure Cortex is running and configured in .mcp.json or ~/.claude/mcp.json. Cannot bootstrap."

Stop here if unhealthy.

---

## Phase 1: Compute System Fingerprint

```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

On macOS, `sha256sum` may not be available — use:
```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | shasum -a 256 | cut -d' ' -f1
```

Store the result as `<fingerprint>`.

---

## Phase 2: System Name

Get the hostname:
```bash
hostname
```

Suggest it as the system name. Ask the user:
> "I'll register this machine as **`<hostname>`**. Press Enter to confirm or type a different name:"

Store the confirmed name as `<system_name>`.

---

## Phase 3: Read Project Context

Read `.claude/cortex-state.json` if it exists. Extract `cortex_project_id` if present.
Store as `<project_id>` (may be omitted if not found).

---

## Phase 4: Call Bootstrap MCP Tool

```
manage_skills(
    action="bootstrap",
    system_fingerprint="<fingerprint>",
    system_name="<system_name>",
    project_id="<project_id>"   ← omit if no project_id
)
```

If the call fails, report the error and stop.

---

## Phase 5: Write Skill Files

For each skill in `response.skills`:

```bash
mkdir -p ~/.claude/skills/<name>
```

Write the content to `~/.claude/skills/<name>/SKILL.md`.

Use the Write tool to write each file. Do not use heredoc — pass the exact content string from `skill.content`.

---

## Phase 6: Update State

Read `.claude/cortex-state.json` (or start with `{}`). Merge in:

```json
{
  "system_fingerprint": "<fingerprint>",
  "system_name": "<system_name>",
  "last_bootstrap": "<ISO 8601 timestamp>"
}
```

Write back to `.claude/cortex-state.json`.

---

## Phase 7: Report

```
## Cortex Bootstrap Complete

**System:** <system_name> (<system_id from response.system.id>)
**Skills installed:** <N> → ~/.claude/skills/
  - <list each skill name>
**Project:** <project_title if registered> — or "No project linked"

Restart Claude Code for the new skills to take effect.
```

If `response.system.is_new` is true, add:
> "This system has been registered with Cortex for the first time."
```

**Step 2: Verify the frontmatter parses correctly**

Manually check: the file must start with `---`, have `name: cortex-bootstrap` and `description:` fields, and end the frontmatter with `---`.

**Step 3: Commit**

```bash
git add integrations/claude-code/skills/cortex-bootstrap/SKILL.md
git commit -m "feat: add cortex-bootstrap skill for first-time skill installation"
```

---

## Task 2: Add `?include_content=true` to `GET /api/skills`

**Files:**
- Modify: `python/src/server/api_routes/skills_api.py`
- Test: `python/tests/server/api_routes/test_skills_api.py` (create if not exists)

**Step 1: Write failing test**

Check if `python/tests/server/api_routes/test_skills_api.py` exists. If not, create it:

```python
"""Tests for skills API endpoints."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    return client


def test_list_skills_without_content(client):
    """GET /api/skills returns metadata only by default."""
    with patch("src.server.api_routes.skills_api.SkillService") as MockService:
        instance = MockService.return_value
        instance.list_skills.return_value = [
            {"id": "s1", "name": "cortex-memory", "content_hash": "abc"}
        ]
        response = client.get("/api/skills")
        assert response.status_code == 200
        instance.list_skills.assert_called_once()
        instance.list_skills_full.assert_not_called()


def test_list_skills_with_content(client):
    """GET /api/skills?include_content=true returns full content."""
    with patch("src.server.api_routes.skills_api.SkillService") as MockService:
        instance = MockService.return_value
        instance.list_skills_full.return_value = [
            {"id": "s1", "name": "cortex-memory", "content": "---\nname: cortex-memory\n---\n# Content"}
        ]
        response = client.get("/api/skills?include_content=true")
        assert response.status_code == 200
        instance.list_skills_full.assert_called_once()
        instance.list_skills.assert_not_called()
```

Note: The `client` fixture likely lives in `python/tests/conftest.py`. Check by running:
```bash
cd python && uv run pytest tests/server/api_routes/test_skills_api.py -v 2>&1 | head -30
```

**Step 2: Run to confirm it fails**

```bash
cd python && uv run pytest tests/server/api_routes/test_skills_api.py -v
```

Expected: FAIL or fixture error (client not found, or `list_skills_full` not called when `include_content=true`).

**Step 3: Modify the endpoint**

In `python/src/server/api_routes/skills_api.py`, update the `list_skills` route:

```python
from fastapi import APIRouter, HTTPException, Query   # add Query

@router.get("/skills")
async def list_skills(include_content: bool = Query(False)):
    """List all skills. Pass ?include_content=true to include full content."""
    try:
        logfire.debug("Listing all skills")
        service = SkillService()
        if include_content:
            skills = service.list_skills_full()
        else:
            skills = service.list_skills()
        return {"skills": skills, "count": len(skills)}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list skills | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
```

**Step 4: Run tests**

```bash
cd python && uv run pytest tests/server/api_routes/test_skills_api.py -v
```

Expected: PASS

**Step 5: Run full test suite to ensure no regressions**

```bash
cd python && uv run pytest -v 2>&1 | tail -20
```

Expected: all previous tests still pass.

**Step 6: Commit**

```bash
git add python/src/server/api_routes/skills_api.py python/tests/server/api_routes/test_skills_api.py
git commit -m "feat: add include_content query param to GET /api/skills"
```

---

## Task 3: Add `action="bootstrap"` to `manage_skills` MCP Tool

**Files:**
- Modify: `python/src/mcp_server/features/skills/skill_tools.py`
- Modify: `python/tests/mcp_server/features/skills/test_skill_tools.py`

**Step 1: Write failing tests**

Add to `python/tests/mcp_server/features/skills/test_skill_tools.py`:

```python
@pytest.mark.asyncio
async def test_manage_skills_bootstrap_basic(registered_tools, mock_context):
    """Bootstrap returns all skills and registers system when fingerprint+project provided."""
    manage_skills = registered_tools["manage_skills"]

    # GET /api/skills?include_content=true returns skills
    mock_skills_response = MagicMock()
    mock_skills_response.status_code = 200
    mock_skills_response.json.return_value = {
        "skills": [
            {"name": "cortex-memory", "content": "---\nname: cortex-memory\n---\n# Content", "display_name": "Cortex Memory"},
            {"name": "cortex-bootstrap", "content": "---\nname: cortex-bootstrap\n---\n# Bootstrap", "display_name": "Cortex Bootstrap"},
        ]
    }

    # POST /api/projects/{project_id}/sync returns system
    mock_sync_response = MagicMock()
    mock_sync_response.status_code = 200
    mock_sync_response.json.return_value = {
        "system": {"id": "sys-1", "name": "My Mac", "is_new": True},
        "in_sync": [], "pending_install": [], "pending_remove": [],
        "local_changes": [], "unknown_local": [],
    }

    with patch("src.mcp_server.features.skills.skill_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_skills_response
        mock_async_client.post.return_value = mock_sync_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_skills(
            mock_context,
            action="bootstrap",
            system_fingerprint="fp-abc",
            system_name="My Mac",
            project_id="proj-1",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert len(data["skills"]) == 2
        assert data["skills"][0]["name"] == "cortex-memory"
        assert data["system"]["id"] == "sys-1"
        assert data["system"]["is_new"] is True
        assert "install_path" in data
        assert "Bootstrap complete" in data["message"]


@pytest.mark.asyncio
async def test_manage_skills_bootstrap_no_project(registered_tools, mock_context):
    """Bootstrap works without project_id — skips sync call, still returns skills."""
    manage_skills = registered_tools["manage_skills"]

    mock_skills_response = MagicMock()
    mock_skills_response.status_code = 200
    mock_skills_response.json.return_value = {
        "skills": [{"name": "cortex-memory", "content": "---\nname: cortex-memory\n---\n# Content", "display_name": "Cortex Memory"}]
    }

    with patch("src.mcp_server.features.skills.skill_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_skills_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_skills(
            mock_context,
            action="bootstrap",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert len(data["skills"]) == 1
        assert data["system"] is None
        # GET was called once (for skills), POST was NOT called (no project)
        mock_async_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_manage_skills_bootstrap_invalid_action_still_caught(registered_tools, mock_context):
    """Verify 'bootstrap' is now valid and not caught by the invalid_action branch."""
    manage_skills = registered_tools["manage_skills"]

    mock_skills_response = MagicMock()
    mock_skills_response.status_code = 200
    mock_skills_response.json.return_value = {"skills": []}

    with patch("src.mcp_server.features.skills.skill_tools.httpx.AsyncClient") as mock_client:
        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_skills_response
        mock_client.return_value.__aenter__.return_value = mock_async_client

        result = await manage_skills(mock_context, action="bootstrap")
        data = json.loads(result)
        # Should succeed (even with 0 skills), NOT return invalid_action error
        assert data.get("error", {}).get("type") != "invalid_action"
```

**Step 2: Run tests to confirm they fail**

```bash
cd python && uv run pytest tests/mcp_server/features/skills/test_skill_tools.py::test_manage_skills_bootstrap_basic -v
```

Expected: FAIL with `KeyError` or assertion error.

**Step 3: Update the `manage_skills` docstring and dispatcher**

In `python/src/mcp_server/features/skills/skill_tools.py`, update the `manage_skills` function:

In the docstring, change:
```python
            action: "sync" | "upload" | "validate" | "install" | "remove"
```
to:
```python
            action: "sync" | "upload" | "validate" | "install" | "remove" | "bootstrap"
```

Also add to the Examples:
```python
            manage_skills("bootstrap")  # Fetch all skills for installation
            manage_skills("bootstrap", system_fingerprint="fp-abc", system_name="My Mac", project_id="proj-1")
```

In the dispatcher body, add before the `else` branch:
```python
                elif action == "bootstrap":
                    return await _handle_bootstrap(
                        client, api_url, system_fingerprint, system_name, project_id
                    )
```

Also update the invalid action error message:
```python
                    return MCPErrorFormatter.format_error(
                        "invalid_action",
                        f"Unknown action: {action}. Valid actions: sync, upload, validate, install, remove, bootstrap",
                    )
```

**Step 4: Add the `_handle_bootstrap` function**

Add after the `_handle_remove` function at the bottom of `skill_tools.py`:

```python
async def _handle_bootstrap(
    client: httpx.AsyncClient,
    api_url: str,
    system_fingerprint: str | None,
    system_name: str | None,
    project_id: str | None,
) -> str:
    """Fetch all skills with content for local installation, optionally registering system."""
    # Fetch all skills with full content
    response = await client.get(urljoin(api_url, "/api/skills"), params={"include_content": "true"})
    if response.status_code != 200:
        return MCPErrorFormatter.from_http_error(response, "fetch skills for bootstrap")

    data = response.json()
    skills = data.get("skills", [])

    # Normalise: keep only name, display_name, content
    skill_list = [
        {
            "name": s.get("name", ""),
            "display_name": s.get("display_name") or s.get("name", ""),
            "content": s.get("content", ""),
        }
        for s in skills
    ]

    system = None

    # Register system and link to project if fingerprint + project_id provided
    if system_fingerprint and project_id:
        payload: dict[str, object] = {
            "fingerprint": system_fingerprint,
            "local_skills": [],  # Bootstrap sends no local skills — nothing installed yet
        }
        if system_name:
            payload["system_name"] = system_name

        sync_response = await client.post(
            urljoin(api_url, f"/api/projects/{project_id}/sync"),
            json=payload,
        )
        if sync_response.status_code == 200:
            sync_data = sync_response.json()
            system = sync_data.get("system")

    return json.dumps({
        "success": True,
        "skills": skill_list,
        "system": system,
        "install_path": "~/.claude/skills",
        "message": f"Bootstrap complete: {len(skill_list)} skill{'s' if len(skill_list) != 1 else ''} ready to install",
    })
```

**Step 5: Run bootstrap tests**

```bash
cd python && uv run pytest tests/mcp_server/features/skills/test_skill_tools.py -v
```

Expected: All tests pass including the 3 new bootstrap tests.

**Step 6: Run full test suite**

```bash
cd python && uv run pytest -v 2>&1 | tail -20
```

Expected: All pass.

**Step 7: Commit**

```bash
git add python/src/mcp_server/features/skills/skill_tools.py \
        python/tests/mcp_server/features/skills/test_skill_tools.py
git commit -m "feat: add bootstrap action to manage_skills MCP tool"
```

---

## Task 4: Write `SkillSeedingService`

**Files:**
- Create: `python/src/server/services/skills/skill_seeding_service.py`
- Create: `python/tests/server/services/skills/test_skill_seeding_service.py`

**Step 1: Write failing tests first**

Create `python/tests/server/services/skills/test_skill_seeding_service.py`:

```python
"""Tests for SkillSeedingService — startup seeding of the skills registry."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.server.services.skills.skill_seeding_service import SkillSeedingService


SAMPLE_SKILL_MD = textwrap.dedent("""\
    ---
    name: cortex-memory
    description: Manage long-term knowledge memory via Cortex RAG.
    ---

    # Cortex Memory

    Some content here.
""")


@pytest.fixture
def mock_skill_service():
    svc = MagicMock()
    svc.find_by_name.return_value = None  # skill does not exist yet
    svc.create_skill.return_value = {"id": "s1", "name": "cortex-memory", "current_version": 1}
    return svc


@pytest.fixture
def seeder(mock_skill_service):
    return SkillSeedingService(skill_service=mock_skill_service)


class TestSeedSkills:
    def test_creates_new_skill_when_not_in_registry(self, seeder, mock_skill_service, tmp_path):
        """A skill file not in the registry should be inserted with version 1."""
        skill_dir = tmp_path / "cortex-memory"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)

        seeder.seed_skills(skills_dir=tmp_path)

        mock_skill_service.find_by_name.assert_called_once_with("cortex-memory")
        mock_skill_service.create_skill.assert_called_once()
        call_kwargs = mock_skill_service.create_skill.call_args.kwargs
        assert call_kwargs["name"] == "cortex-memory"
        assert call_kwargs["created_by"] == "cortex-seeder"

    def test_skips_skill_when_hash_unchanged(self, seeder, mock_skill_service, tmp_path):
        """If skill exists and hash matches, skip without update."""
        import hashlib
        content_hash = hashlib.sha256(SAMPLE_SKILL_MD.encode()).hexdigest()
        mock_skill_service.find_by_name.return_value = {
            "id": "s1",
            "name": "cortex-memory",
            "content_hash": content_hash,
            "current_version": 1,
        }

        skill_dir = tmp_path / "cortex-memory"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)

        seeder.seed_skills(skills_dir=tmp_path)

        mock_skill_service.create_skill.assert_not_called()
        mock_skill_service.update_skill.assert_not_called()

    def test_updates_skill_when_hash_changed(self, seeder, mock_skill_service, tmp_path):
        """If skill exists and hash differs, update content and bump version."""
        mock_skill_service.find_by_name.return_value = {
            "id": "s1",
            "name": "cortex-memory",
            "content_hash": "old-hash-that-does-not-match",
            "current_version": 2,
        }
        mock_skill_service.update_skill.return_value = {
            "id": "s1",
            "name": "cortex-memory",
            "current_version": 3,
        }

        skill_dir = tmp_path / "cortex-memory"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)

        seeder.seed_skills(skills_dir=tmp_path)

        mock_skill_service.update_skill.assert_called_once()
        call_kwargs = mock_skill_service.update_skill.call_args.kwargs
        assert call_kwargs["new_version"] == 3
        assert call_kwargs["updated_by"] == "cortex-seeder"

    def test_skips_directory_without_skill_md(self, seeder, mock_skill_service, tmp_path):
        """Directories without SKILL.md are silently ignored."""
        other_dir = tmp_path / "not-a-skill"
        other_dir.mkdir()
        (other_dir / "README.md").write_text("not a skill")

        seeder.seed_skills(skills_dir=tmp_path)

        mock_skill_service.find_by_name.assert_not_called()

    def test_skips_skill_with_no_name_in_frontmatter(self, seeder, mock_skill_service, tmp_path):
        """SKILL.md without a 'name' field in frontmatter is logged and skipped."""
        skill_dir = tmp_path / "broken-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just a header, no frontmatter")

        seeder.seed_skills(skills_dir=tmp_path)

        mock_skill_service.find_by_name.assert_not_called()
        mock_skill_service.create_skill.assert_not_called()

    def test_seeds_multiple_skills(self, seeder, mock_skill_service, tmp_path):
        """Multiple skill directories are each processed."""
        mock_skill_service.find_by_name.return_value = None
        mock_skill_service.create_skill.return_value = {"id": "s-x", "name": "x", "current_version": 1}

        for name in ("skill-a", "skill-b", "skill-c"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\n# {name}\n")

        seeder.seed_skills(skills_dir=tmp_path)

        assert mock_skill_service.create_skill.call_count == 3

    def test_continues_on_error_for_one_skill(self, seeder, mock_skill_service, tmp_path):
        """If one skill fails to seed, the others continue processing."""
        mock_skill_service.find_by_name.return_value = None
        mock_skill_service.create_skill.side_effect = [RuntimeError("DB error"), {"id": "s2", "name": "skill-b", "current_version": 1}]

        for name in ("skill-a", "skill-b"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Desc\n---\n# {name}\n")

        # Should not raise — error is logged and skipped
        seeder.seed_skills(skills_dir=tmp_path)

        assert mock_skill_service.create_skill.call_count == 2


class TestDefaultSkillsDir:
    def test_default_dir_resolves_from_package_location(self):
        """default_skills_dir() points to integrations/claude-code/skills/ relative to repo root."""
        seeder = SkillSeedingService.__new__(SkillSeedingService)
        path = seeder.default_skills_dir()
        # The path must end with integrations/claude-code/skills
        assert path.parts[-3:] == ("integrations", "claude-code", "skills"), (
            f"Unexpected path: {path}"
        )
```

**Step 2: Run to confirm they fail**

```bash
cd python && uv run pytest tests/server/services/skills/test_skill_seeding_service.py -v 2>&1 | head -20
```

Expected: `ImportError` — module not found.

**Step 3: Implement `SkillSeedingService`**

Create `python/src/server/services/skills/skill_seeding_service.py`:

```python
"""Startup seeding service that syncs SKILL.md files from the repo into the DB registry.

On server startup, scans integrations/claude-code/skills/*/SKILL.md and upserts
each skill into cortex_skills:
  - If not in registry → create (version 1)
  - If in registry and hash matches → skip
  - If in registry and hash differs → update content, bump version
"""

import logging
import re
from pathlib import Path

from src.server.services.skills.skill_service import SkillService

logger = logging.getLogger(__name__)


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract name and description from YAML frontmatter."""
    metadata: dict[str, str] = {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return metadata
    for line in match.group(1).split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip("\"'")
            if key in ("name", "description"):
                metadata[key] = value
    return metadata


class SkillSeedingService:
    """Seeds the cortex_skills table from SKILL.md files bundled in the repo."""

    def __init__(self, skill_service: SkillService | None = None):
        self.skill_service = skill_service or SkillService()

    def default_skills_dir(self) -> Path:
        """Return the path to integrations/claude-code/skills/ relative to the repo root.

        Navigates up from this file's location:
          python/src/server/services/skills/skill_seeding_service.py
          → up 5 parents → repo root
          → integrations/claude-code/skills/
        """
        return Path(__file__).parents[5] / "integrations" / "claude-code" / "skills"

    def seed_skills(self, skills_dir: Path | None = None) -> dict[str, int]:
        """Scan skills_dir and upsert each SKILL.md into the registry.

        Args:
            skills_dir: Directory containing skill subdirectories. Defaults to
                        integrations/claude-code/skills/ relative to the repo root.

        Returns:
            Dict with counts: {"created": N, "updated": N, "skipped": N, "errors": N}
        """
        if skills_dir is None:
            skills_dir = self.default_skills_dir()

        if not skills_dir.is_dir():
            logger.warning(f"Skills directory not found: {skills_dir} — skipping seeding")
            return {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        counts = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                self._seed_one(skill_md, counts)
            except Exception:
                logger.error(f"Failed to seed skill from {skill_md}", exc_info=True)
                counts["errors"] += 1

        logger.info(
            f"Skill seeding complete: {counts['created']} created, "
            f"{counts['updated']} updated, {counts['skipped']} skipped, "
            f"{counts['errors']} errors"
        )
        return counts

    def _seed_one(self, skill_md: Path, counts: dict[str, int]) -> None:
        """Process a single SKILL.md file."""
        content = skill_md.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)

        name = meta.get("name")
        if not name:
            logger.warning(f"Skipping {skill_md}: no 'name' in frontmatter")
            counts["skipped"] += 1
            return

        description = meta.get("description", "")
        content_hash = SkillService.compute_content_hash(content)

        existing = self.skill_service.find_by_name(name)

        if existing is None:
            self.skill_service.create_skill(
                name=name,
                description=description,
                content=content,
                created_by="cortex-seeder",
            )
            logger.info(f"Seeded new skill: {name}")
            counts["created"] += 1

        elif existing["content_hash"] == content_hash:
            logger.debug(f"Skill '{name}' unchanged — skipping")
            counts["skipped"] += 1

        else:
            new_version = existing["current_version"] + 1
            self.skill_service.update_skill(
                skill_id=existing["id"],
                content=content,
                new_version=new_version,
                updated_by="cortex-seeder",
                description=description or None,
            )
            logger.info(f"Updated skill '{name}' to v{new_version}")
            counts["updated"] += 1
```

**Step 4: Run tests**

```bash
cd python && uv run pytest tests/server/services/skills/test_skill_seeding_service.py -v
```

Expected: All 9 tests pass.

**Step 5: Run full suite**

```bash
cd python && uv run pytest -v 2>&1 | tail -20
```

Expected: All pass.

**Step 6: Commit**

```bash
git add python/src/server/services/skills/skill_seeding_service.py \
        python/tests/server/services/skills/test_skill_seeding_service.py
git commit -m "feat: add SkillSeedingService to upsert bundled skills into registry on startup"
```

---

## Task 5: Hook Seeding into Server Startup

**Files:**
- Modify: `python/src/server/main.py`

There are no automated tests for this task — the startup lifespan is hard to unit test in isolation. Verification is done by restarting the server and checking the Skills tab.

**Step 1: Add the seeding call to the lifespan function**

In `python/src/server/main.py`, in the `lifespan` async context manager, add after the prompt service init block (around line 114, before `_initialization_complete = True`):

```python
        # Seed bundled skills into the registry on startup
        try:
            from .services.skills.skill_seeding_service import SkillSeedingService

            seeder = SkillSeedingService()
            counts = seeder.seed_skills()
            api_logger.info(
                f"✅ Skills seeded: {counts['created']} created, "
                f"{counts['updated']} updated, {counts['skipped']} unchanged"
            )
        except Exception as e:
            api_logger.warning(f"Skill seeding failed (non-fatal): {e}", exc_info=True)
```

The `try/except` here is intentional — seeding is non-critical. The server must still start even if seeding fails (e.g., DB temporarily unavailable during a migration).

**Step 2: Verify import chain (no circular imports)**

```bash
cd python && uv run python -c "from src.server.main import app; print('OK')"
```

Expected: `OK` with no import errors.

**Step 3: Run full test suite**

```bash
cd python && uv run pytest -v 2>&1 | tail -20
```

Expected: All pass.

**Step 4: Commit**

```bash
git add python/src/server/main.py
git commit -m "feat: seed bundled skills into registry on server startup"
```

---

## Task 6: Add `DELETE /api/projects/{project_id}/systems/{system_id}` Endpoint

**Files:**
- Modify: `python/src/server/services/skills/skill_sync_service.py`
- Modify: `python/src/server/api_routes/skills_api.py`
- Modify: `python/tests/server/services/skills/test_skill_sync_service.py`

**Step 1: Write failing test for the service method**

Add to `python/tests/server/services/skills/test_skill_sync_service.py`:

```python
class TestUnlinkSystemFromProject:
    def test_deletes_registration_record(self, service, mock_supabase):
        """Should delete from cortex_project_system_registrations."""
        builder = MagicMock()
        builder.delete.return_value = builder
        builder.eq.return_value = builder
        builder.execute.return_value = MagicMock(data=[{"project_id": "proj-1", "system_id": "sys-1"}])

        mock_supabase.table.side_effect = lambda name: builder

        service.unlink_system_from_project("sys-1", "proj-1")

        mock_supabase.table.assert_called_with("cortex_project_system_registrations")
        builder.delete.assert_called_once()
```

**Step 2: Run to confirm it fails**

```bash
cd python && uv run pytest tests/server/services/skills/test_skill_sync_service.py::TestUnlinkSystemFromProject -v
```

Expected: `AttributeError: 'SkillSyncService' object has no attribute 'unlink_system_from_project'`

**Step 3: Add `unlink_system_from_project` to `SkillSyncService`**

In `python/src/server/services/skills/skill_sync_service.py`, add after `register_system_for_project`:

```python
    def unlink_system_from_project(self, system_id: str, project_id: str) -> None:
        """Remove a system's association with a project.

        Deletes from cortex_project_system_registrations. The system remains
        globally in cortex_systems — only the project link is removed.
        """
        (
            self.supabase_client.table(REGISTRATIONS_TABLE)
            .delete()
            .eq("project_id", project_id)
            .eq("system_id", system_id)
            .execute()
        )
```

**Step 4: Run service test**

```bash
cd python && uv run pytest tests/server/services/skills/test_skill_sync_service.py -v
```

Expected: All pass.

**Step 5: Add the API endpoint**

In `python/src/server/api_routes/skills_api.py`, add after the `get_project_systems` endpoint (around line 505):

```python
@router.delete("/projects/{project_id}/systems/{system_id}")
async def unlink_system_from_project(project_id: str, system_id: str):
    """Remove a system's association with a project.

    The system remains in the global cortex_systems table — only the
    project-level link in cortex_project_system_registrations is removed.
    """
    try:
        logfire.info(f"Unlinking system | project_id={project_id} | system_id={system_id}")

        from ..services.skills.skill_sync_service import SkillSyncService

        sync_service = SkillSyncService()
        sync_service.unlink_system_from_project(system_id, project_id)

        logfire.info(f"System unlinked | project_id={project_id} | system_id={system_id}")
        return {"status": "unlinked", "project_id": project_id, "system_id": system_id}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to unlink system | project_id={project_id} | system_id={system_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
```

**Step 6: Run full suite**

```bash
cd python && uv run pytest -v 2>&1 | tail -20
```

Expected: All pass.

**Step 7: Commit**

```bash
git add python/src/server/services/skills/skill_sync_service.py \
        python/src/server/api_routes/skills_api.py \
        python/tests/server/services/skills/test_skill_sync_service.py
git commit -m "feat: add DELETE /api/projects/{project_id}/systems/{system_id} endpoint"
```

---

## Task 7: Add Remove Skill Button to `SystemSkillList.tsx`

**Files:**
- Modify: `cortex-ui/src/features/projects/skills/components/SystemSkillList.tsx`
- Modify: `cortex-ui/src/features/projects/skills/SkillsTab.tsx`

**Step 1: Update `SystemSkillList` props and add Remove button**

Replace `cortex-ui/src/features/projects/skills/components/SystemSkillList.tsx` with:

```typescript
import { SkillStatusBadge } from "./SkillStatusBadge";
import type { Skill, SystemSkill } from "../types";

interface SystemSkillListProps {
	systemSkills: SystemSkill[];
	allSkills: Skill[];
	onInstall: (skillId: string) => void;
	onRemove: (skillId: string) => void;
}

export function SystemSkillList({ systemSkills, allSkills, onInstall, onRemove }: SystemSkillListProps) {
	const installedSkillIds = new Set(systemSkills.map((ss) => ss.skill_id));
	const availableSkills = allSkills.filter((s) => !installedSkillIds.has(s.id));

	return (
		<div className="space-y-4">
			{systemSkills.length > 0 && (
				<div>
					<h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
						Installed Skills
					</h4>
					<div className="space-y-1">
						{systemSkills.map((ss) => (
							<div key={ss.id} className="flex items-center justify-between p-2 rounded-md bg-white/5">
								<span className="text-sm text-white">
									{ss.cortex_skills?.display_name || ss.cortex_skills?.name || ss.skill_id}
								</span>
								<div className="flex items-center gap-2">
									<SkillStatusBadge status={ss.status} hasLocalChanges={ss.has_local_changes} />
									<button
										type="button"
										onClick={() => onRemove(ss.skill_id)}
										className="px-2 py-1 text-xs rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
									>
										Remove
									</button>
								</div>
							</div>
						))}
					</div>
				</div>
			)}

			{availableSkills.length > 0 && (
				<div>
					<h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Available</h4>
					<div className="space-y-1">
						{availableSkills.map((skill) => (
							<div
								key={skill.id}
								className="flex items-center justify-between p-2 rounded-md bg-white/5"
							>
								<div>
									<span className="text-sm text-white">{skill.display_name || skill.name}</span>
									{skill.is_required && (
										<span className="ml-2 text-xs text-cyan-400">Required</span>
									)}
								</div>
								<button
									type="button"
									onClick={() => onInstall(skill.id)}
									className="px-3 py-1 text-xs rounded-md bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors"
								>
									Install
								</button>
							</div>
						))}
					</div>
				</div>
			)}

			{systemSkills.length === 0 && availableSkills.length === 0 && (
				<div className="text-center py-8 text-zinc-500 text-sm">
					No skills in the registry yet. Skills are added when systems sync.
				</div>
			)}
		</div>
	);
}
```

**Step 2: Update `SkillsTab.tsx` to wire the `onRemove` handler**

In `cortex-ui/src/features/projects/skills/SkillsTab.tsx`, add `useRemoveSkill` to the imports:

```typescript
import { useState } from "react";
import { useProjectSkills, useInstallSkill, useRemoveSkill } from "./hooks/useSkillQueries";
import { SystemCard } from "./components/SystemCard";
import { SystemSkillList } from "./components/SystemSkillList";
```

Add the `removeSkill` mutation after the `installSkill` line:

```typescript
	const installSkill = useInstallSkill();
	const removeSkill = useRemoveSkill();
```

Add `handleRemove` after `handleInstall`:

```typescript
	const handleRemove = (skillId: string) => {
		if (!selectedSystem) return;
		removeSkill.mutate({
			projectId,
			skillId,
			systemIds: [selectedSystem.id],
		});
	};
```

Pass `onRemove` to `SystemSkillList`:

```typescript
						<SystemSkillList
							systemSkills={selectedSystem.skills}
							allSkills={allSkills}
							onInstall={handleInstall}
							onRemove={handleRemove}
						/>
```

**Step 3: Check for TypeScript errors**

```bash
cd cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects/skills"
```

Expected: No errors.

**Step 4: Run Biome on the changed files**

```bash
cd cortex-ui && npm run biome:fix -- src/features/projects/skills/
```

**Step 5: Commit**

```bash
git add cortex-ui/src/features/projects/skills/components/SystemSkillList.tsx \
        cortex-ui/src/features/projects/skills/SkillsTab.tsx
git commit -m "feat: add Remove skill button to SystemSkillList"
```

---

## Task 8: Add Unlink System to `SystemCard.tsx`, Service, and Hook

**Files:**
- Modify: `cortex-ui/src/features/projects/skills/services/skillService.ts`
- Modify: `cortex-ui/src/features/projects/skills/hooks/useSkillQueries.ts`
- Modify: `cortex-ui/src/features/projects/skills/components/SystemCard.tsx`
- Modify: `cortex-ui/src/features/projects/skills/SkillsTab.tsx`

**Step 1: Add `unlinkSystem` to `skillService.ts`**

In `cortex-ui/src/features/projects/skills/services/skillService.ts`, add after `removeSkill`:

```typescript
	async unlinkSystem(projectId: string, systemId: string): Promise<void> {
		const response = await fetch(`/api/projects/${projectId}/systems/${systemId}`, {
			method: "DELETE",
		});
		if (!response.ok) throw new Error(`Failed to unlink system: ${response.statusText}`);
	},
```

**Step 2: Add `useUnlinkSystem` hook to `useSkillQueries.ts`**

In `cortex-ui/src/features/projects/skills/hooks/useSkillQueries.ts`, add after `useRemoveSkill`:

```typescript
export function useUnlinkSystem() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: ({ projectId, systemId }: { projectId: string; systemId: string }) =>
			skillService.unlinkSystem(projectId, systemId),
		onSuccess: (_, variables) => {
			queryClient.invalidateQueries({ queryKey: skillKeys.byProject(variables.projectId) });
		},
	});
}
```

**Step 3: Update `SystemCard.tsx` to accept and show unlink button**

Replace `cortex-ui/src/features/projects/skills/components/SystemCard.tsx` with:

```typescript
import type { SystemWithSkills } from "../types";

interface SystemCardProps {
	system: SystemWithSkills;
	isSelected: boolean;
	onClick: () => void;
	onUnlink: (systemId: string) => void;
}

export function SystemCard({ system, isSelected, onClick, onUnlink }: SystemCardProps) {
	const isOnline = isRecentlyActive(system.last_seen_at);
	const skillCount = system.skills?.length ?? 0;

	return (
		<div
			className={`w-full text-left p-3 rounded-lg border transition-colors ${
				isSelected
					? "border-cyan-500/50 bg-cyan-500/10"
					: "border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/[0.07]"
			}`}
		>
			<button type="button" onClick={onClick} className="w-full text-left">
				<div className="flex items-center gap-2">
					<span className={`w-2 h-2 rounded-full ${isOnline ? "bg-emerald-400" : "bg-zinc-500"}`} />
					<span className="font-medium text-sm text-white truncate">{system.name}</span>
				</div>
				<div className="mt-1 text-xs text-zinc-400">
					{skillCount} skill{skillCount !== 1 ? "s" : ""}
					{system.hostname && ` · ${system.hostname}`}
				</div>
			</button>
			<div className="mt-2 flex justify-end">
				<button
					type="button"
					onClick={(e) => {
						e.stopPropagation();
						onUnlink(system.id);
					}}
					className="px-2 py-1 text-xs rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
					title="Unlink this system from the project"
				>
					Unlink
				</button>
			</div>
		</div>
	);
}

function isRecentlyActive(lastSeen: string): boolean {
	const fiveMinutes = 5 * 60 * 1000;
	return Date.now() - new Date(lastSeen).getTime() < fiveMinutes;
}
```

**Step 4: Wire `useUnlinkSystem` in `SkillsTab.tsx`**

Import `useUnlinkSystem`:

```typescript
import { useProjectSkills, useInstallSkill, useRemoveSkill, useUnlinkSystem } from "./hooks/useSkillQueries";
```

Add the mutation:

```typescript
	const unlinkSystem = useUnlinkSystem();
```

Add `handleUnlink`:

```typescript
	const handleUnlink = (systemId: string) => {
		unlinkSystem.mutate({ projectId, systemId });
		// If the unlinked system was selected, clear selection
		if (selectedSystemId === systemId) {
			setSelectedSystemId(null);
		}
	};
```

Pass `onUnlink` to `SystemCard`:

```typescript
				<SystemCard
					key={system.id}
					system={system}
					isSelected={system.id === (selectedSystem?.id ?? null)}
					onClick={() => setSelectedSystemId(system.id)}
					onUnlink={handleUnlink}
				/>
```

**Step 5: Check TypeScript**

```bash
cd cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects/skills"
```

Expected: No errors.

**Step 6: Run Biome**

```bash
cd cortex-ui && npm run biome:fix -- src/features/projects/skills/
```

**Step 7: Commit**

```bash
git add cortex-ui/src/features/projects/skills/services/skillService.ts \
        cortex-ui/src/features/projects/skills/hooks/useSkillQueries.ts \
        cortex-ui/src/features/projects/skills/components/SystemCard.tsx \
        cortex-ui/src/features/projects/skills/SkillsTab.tsx
git commit -m "feat: add Unlink system action to SystemCard in Skills tab"
```

---

## Task 9: End-to-End Verification

**Step 1: Apply DB migration 015 if not already applied**

```bash
docker cp migration/0.1.0/015_add_project_system_registrations.sql cortex-supabase-db:/tmp/015.sql
docker exec cortex-supabase-db psql -U postgres -d postgres -f /tmp/015.sql
```

Expected: `CREATE TABLE` or `already exists` — no errors.

**Step 2: Restart the Cortex backend**

```bash
docker compose restart cortex-server
```

Wait ~10 seconds, then check logs:

```bash
docker compose logs cortex-server 2>&1 | grep -E "(Skills seeded|Seeded|seed)" | head -10
```

Expected: Log lines like `Skills seeded: 3 created, 0 updated, 0 unchanged`.

**Step 3: Verify skills appear in UI**

Open the Cortex UI → Settings → Skills (or any project → Skills tab). Confirm `cortex-memory`, `cortex-skill-sync`, and `cortex-bootstrap` appear in the registry.

**Step 4: Test bootstrap MCP action manually**

In a Claude Code session with the Cortex MCP connected, run:

```
manage_skills(action="bootstrap")
```

Expected JSON response:
```json
{
  "success": true,
  "skills": [{"name": "cortex-memory", "content": "---\n...", "display_name": "..."}],
  "system": null,
  "install_path": "~/.claude/skills",
  "message": "Bootstrap complete: 3 skills ready to install"
}
```

**Step 5: Run `/cortex-bootstrap` via the skill**

If the `cortex-bootstrap` SKILL.md is already installed (or copy it manually), run `/cortex-bootstrap` in a Claude Code session for any project. Verify:
- Skills written to `~/.claude/skills/cortex-memory/SKILL.md`, etc.
- `.claude/cortex-state.json` updated with `system_fingerprint`, `system_name`, `last_bootstrap`
- System appears in project Skills tab within 30 seconds (or after a manual page refresh)

**Step 6: Test Remove and Unlink in UI**

1. Open Skills tab for the bootstrapped project
2. Select a system
3. Click "Remove" on an installed skill → skill should move to Available list
4. Click "Unlink" on a system → system should disappear from the systems list

**Step 7: Run full test suite one final time**

```bash
cd python && uv run pytest -v 2>&1 | tail -20
```

Expected: All tests pass.

**Step 8: Final commit**

If any loose files remain uncommitted:

```bash
git status
```

Commit any stragglers, then tag this as complete.
