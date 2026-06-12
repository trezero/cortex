# Command Extension Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `"command"` as a first-class extension type in the Cortex registry so Claude Code slash commands can be synced, versioned, and distributed through the same Extensions system that already handles skills and plugins.

**Architecture:** Commands are stored in the existing `cortex_extensions` table with `type = "command"`. The `plugin_manifest` JSONB column (already nullable) is reused to store command-specific metadata (`command_group` and `filename`) needed to reconstruct the correct install path (`~/.claude/commands/{group}/{file}.md`). The seeding service scans `integrations/claude-code/commands/` recursively at startup, and the commands tarball endpoint switches from static file serving to registry-backed generation. The sync skill and bootstrap flow are updated to handle commands alongside skills.

**Tech Stack:** Python 3.12 (FastAPI, Pydantic), TypeScript (React, TanStack Query), Supabase (PostgreSQL)

---

## File Structure

### Backend — Files to Modify

| File | Responsibility |
|---|---|
| `python/src/server/services/extensions/extension_service.py` | Add `type` param to `create_extension()`, add `type` filter to list methods |
| `python/src/server/services/extensions/extension_seeding_service.py` | Add `seed_commands()` method scanning `integrations/claude-code/commands/` |
| `python/src/server/services/extensions/extension_validation_service.py` | Add command-aware validation (frontmatter optional for commands) |
| `python/src/server/api_routes/extensions_api.py` | Add `type` field to `CreateExtensionRequest`, add `type` query filter to list endpoint |
| `python/src/server/main.py` | Call `seeder.seed_commands()` at startup |
| `python/src/mcp_server/features/extensions/extension_tools.py` | Add `extension_type` param to `manage_extensions` upload action |
| `python/src/mcp_server/mcp_server.py` | Replace static `http_download_commands` with registry-backed tarball generation |

### Backend — Test Files to Modify

| File | Responsibility |
|---|---|
| `python/tests/server/services/extensions/test_extension_service.py` | Test `type` parameter in create, test `type` filter in list |
| `python/tests/server/services/extensions/test_extension_seeding_service.py` | Test `seed_commands()` for flat and grouped command files |
| `python/tests/server/services/extensions/test_extension_validation_service.py` | Test command validation (no frontmatter required) |

### Frontend — Files to Modify

| File | Responsibility |
|---|---|
| `cortex-ui/src/features/projects/extensions/types/index.ts` | Extend `Extension.type` union, add `CommandMetadata` interface |
| `cortex-ui/src/features/projects/extensions/components/SystemExtensionList.tsx` | Group extensions by type, show type badges |
| `cortex-ui/src/features/projects/extensions/components/ExtensionStatusBadge.tsx` | Add type-aware icon/label |

### Integration — Files to Modify

| File | Responsibility |
|---|---|
| `integrations/claude-code/extensions/cortex-extension-sync/SKILL.md` | Scan commands dir in Phase 1, install commands correctly in Phase 3, remove Phase 3e |
| `integrations/claude-code/extensions/cortex-bootstrap/SKILL.md` | Download commands tarball alongside extensions tarball |
| `integrations/claude-code/setup/cortexSetup.sh` | Use registry-backed commands tarball instead of individual curl downloads |
| `integrations/claude-code/setup/cortexSetup.bat` | Same as above for Windows |

---

## Design Decisions

### Command Metadata Storage

Commands install to a different path structure than skills:
- Skills: `~/.claude/skills/{name}/SKILL.md`
- Commands: `~/.claude/commands/{group}/{filename}.md` (grouped) or `~/.claude/commands/{filename}.md` (ungrouped)

To reconstruct the install path, we store metadata in the existing `plugin_manifest` JSONB column:

```json
{"command_group": "cortex", "filename": "cortex-prime.md"}
```

For ungrouped commands (e.g., `cortex-setup.md` at the root of the commands dir):

```json
{"command_group": null, "filename": "cortex-setup.md"}
```

### Command Name Derivation

The extension `name` field (unique, kebab-case) is derived from the file path:
- `cortex/cortex-prime.md` → `cortex-prime` (filename stem)
- `agent-work-orders/commit.md` → `agent-work-orders-commit` (group prefix + filename stem)
- `cortex-setup.md` → `cortex-setup` (filename stem, ungrouped)

Rule: if the filename stem already starts with the group name, use just the filename stem. Otherwise, prefix with `{group}-`.

### Validation Differences

Skills require YAML frontmatter with a `name` field. Commands may or may not have frontmatter. For `type = "command"`:
- Frontmatter is optional
- Name is derived from file path (not frontmatter)
- Size limit, secret scanning, and hardcoded path checks still apply

### No Migration Needed

The `type` column in `cortex_extensions` is already free-text (`TEXT NOT NULL DEFAULT 'skill'`). We just insert `"command"` values. The `plugin_manifest` column is already `JSONB` and nullable.

---

## Task 1: Backend — Add `type` Parameter to ExtensionService

**Files:**
- Modify: `python/src/server/services/extensions/extension_service.py:34-94` (create_extension method)
- Modify: `python/src/server/services/extensions/extension_service.py:96-156` (list methods)
- Test: `python/tests/server/services/extensions/test_extension_service.py`

- [ ] **Step 1: Write failing test for `create_extension` with type parameter**

Add to `python/tests/server/services/extensions/test_extension_service.py`:

```python
class TestCreateExtensionWithType:
    def test_creates_extension_with_command_type(self, service, mock_supabase):
        """create_extension with type='command' should include type in the insert payload."""
        extension_row = {
            "id": "cmd-uuid-1",
            "name": "cortex-setup",
            "type": "command",
            "content": "# Cortex Setup\n\nSome content.",
            "content_hash": ExtensionService.compute_content_hash("# Cortex Setup\n\nSome content."),
        }
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [extension_row]
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [extension_row]

        result = service.create_extension(
            name="cortex-setup",
            description="Setup command",
            content="# Cortex Setup\n\nSome content.",
            created_by="test",
            type="command",
        )

        insert_call = mock_supabase.table.return_value.insert.call_args
        assert insert_call[0][0]["type"] == "command"
        assert result["type"] == "command"

    def test_creates_extension_with_default_skill_type(self, service, mock_supabase):
        """create_extension without type should default to 'skill' (existing behavior)."""
        extension_row = {
            "id": "ext-uuid-1",
            "name": "my-skill",
            "content": "---\nname: my-skill\n---\n# Content",
            "content_hash": ExtensionService.compute_content_hash("---\nname: my-skill\n---\n# Content"),
        }
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [extension_row]

        result = service.create_extension(
            name="my-skill",
            description="A skill",
            content="---\nname: my-skill\n---\n# Content",
            created_by="test",
        )

        insert_call = mock_supabase.table.return_value.insert.call_args
        # type should NOT be in the payload when defaulting (DB default handles it)
        assert "type" not in insert_call[0][0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_service.py::TestCreateExtensionWithType -v
```

Expected: FAIL — `create_extension() got an unexpected keyword argument 'type'`

- [ ] **Step 3: Implement `type` parameter in `create_extension`**

In `python/src/server/services/extensions/extension_service.py`, modify `create_extension`:

```python
def create_extension(
    self,
    name: str,
    description: str,
    content: str,
    created_by: str,
    skill_groups: list[str] | None = None,
    type: str | None = None,
    plugin_manifest: dict | None = None,
) -> dict[str, Any]:
```

In the `extension_data` dict construction (around line 64), add conditionally:

```python
extension_data = {
    "name": name,
    "display_name": name,
    "description": description,
    "content": content,
    "content_hash": content_hash,
    "current_version": 1,
    "skill_groups": skill_groups,
    "created_by": created_by,
    "created_at": now,
    "updated_at": now,
}
if type is not None:
    extension_data["type"] = type
if plugin_manifest is not None:
    extension_data["plugin_manifest"] = plugin_manifest
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_service.py::TestCreateExtensionWithType -v
```

Expected: PASS

- [ ] **Step 5: Write failing test for `type` filter on list methods**

Add to `python/tests/server/services/extensions/test_extension_service.py`:

```python
class TestListExtensionsWithTypeFilter:
    def test_list_extensions_filters_by_type(self, service, mock_supabase):
        """list_extensions with type filter should add .eq('type', value) to query."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []

        service.list_extensions(type="command")

        mock_supabase.table.return_value.select.return_value.eq.assert_called_with("type", "command")

    def test_list_extensions_no_type_filter(self, service, mock_supabase):
        """list_extensions without type should not filter by type."""
        mock_supabase.table.return_value.select.return_value.order.return_value.execute.return_value.data = []

        service.list_extensions()

        # eq should not be called (no type filter, no skill_group filter)
        mock_supabase.table.return_value.select.return_value.eq.assert_not_called()
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_service.py::TestListExtensionsWithTypeFilter -v
```

Expected: FAIL — `list_extensions() got an unexpected keyword argument 'type'`

- [ ] **Step 7: Add `type` filter to list methods**

In `python/src/server/services/extensions/extension_service.py`, modify `list_extensions`:

```python
def list_extensions(self, skill_group: str | None = None, type: str | None = None) -> list[dict[str, Any]]:
```

After the existing `skill_group` filter, add:

```python
if type is not None:
    query = query.eq("type", type)
```

Apply the same pattern to `list_extensions_full` and `list_extensions_for_project`.

- [ ] **Step 8: Run all extension service tests**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_service.py -v
```

Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add python/src/server/services/extensions/extension_service.py python/tests/server/services/extensions/test_extension_service.py
git commit -m "feat: add type parameter to ExtensionService create and list methods"
```

---

## Task 2: Backend — Add Command Validation Support

**Files:**
- Modify: `python/src/server/services/extensions/extension_validation_service.py:48-108`
- Test: `python/tests/server/services/extensions/test_extension_validation_service.py`

- [ ] **Step 1: Write failing test for command validation**

Add to `python/tests/server/services/extensions/test_extension_validation_service.py`:

```python
class TestCommandValidation:
    def test_command_without_frontmatter_is_valid(self):
        """Commands should be valid even without YAML frontmatter."""
        service = ExtensionValidationService()
        content = "# My Command\n\nDo something useful.\n\n## Instructions\n\nStep 1..."
        result = service.validate(content, extension_type="command")
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_command_with_frontmatter_is_valid(self):
        """Commands with frontmatter should also pass validation."""
        service = ExtensionValidationService()
        content = "---\nname: prime\ndescription: Prime the context\n---\n\n# Prime\n\nContent here."
        result = service.validate(content, extension_type="command")
        assert result["valid"] is True

    def test_command_still_checks_size_limit(self):
        """Commands should still be rejected if they exceed the size limit."""
        service = ExtensionValidationService()
        content = "# Huge Command\n\n" + "x" * (50 * 1024 + 1)
        result = service.validate(content, extension_type="command")
        assert result["valid"] is False
        assert any("size" in e.lower() for e in result["errors"])

    def test_command_still_checks_secrets(self):
        """Commands should still be rejected if they contain secrets."""
        service = ExtensionValidationService()
        content = "# Setup\n\ntoken = 'sk-proj-AAAAAAAAAAAAAAAAAAAAAA'"
        result = service.validate(content, extension_type="command")
        assert result["valid"] is False
        assert any("secret" in e.lower() for e in result["errors"])

    def test_skill_without_frontmatter_still_fails(self):
        """Skills (default type) should still require frontmatter."""
        service = ExtensionValidationService()
        content = "# No Frontmatter Skill\n\nContent."
        result = service.validate(content)
        assert result["valid"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_validation_service.py::TestCommandValidation -v
```

Expected: FAIL — `validate() got an unexpected keyword argument 'extension_type'`

- [ ] **Step 3: Implement command-aware validation**

In `python/src/server/services/extensions/extension_validation_service.py`, modify `validate`:

```python
def validate(self, content: str, existing_name: str | None = None, extension_type: str = "skill") -> dict[str, Any]:
```

Replace the frontmatter section (lines 66-94) with type-aware logic:

```python
        # Size check (runs on raw content before any parsing)
        self._check_size_limit(content, errors)

        # Frontmatter extraction
        frontmatter = self._parse_frontmatter(content)
        body = self._get_body(content)
        parsed["body"] = body

        if extension_type == "command":
            # Commands: frontmatter is optional
            if frontmatter is not None:
                name = frontmatter.get("name")
                parsed["name"] = name
                description = frontmatter.get("description")
                parsed["description"] = description
                for key, value in frontmatter.items():
                    if key not in ("name", "description"):
                        parsed[key] = value
        else:
            # Skills: frontmatter is required
            if frontmatter is None:
                errors.append("Missing or malformed YAML frontmatter. Content must start with '---' delimiters.")
            else:
                name = frontmatter.get("name")
                parsed["name"] = name
                self._check_name(name, errors)

                if existing_name is not None and name and name != existing_name:
                    errors.append(
                        f"Name mismatch: frontmatter name '{name}' does not match "
                        f"existing extension name '{existing_name}'. Extension names cannot be changed after creation."
                    )

                description = frontmatter.get("description")
                parsed["description"] = description
                self._check_description(description, warnings)

                for key, value in frontmatter.items():
                    if key not in ("name", "description"):
                        parsed[key] = value

        # Content quality checks (run on body)
        self._check_content_structure(body, warnings)
        self._check_hardcoded_paths(body, warnings)

        # Security scan (run on entire content including frontmatter)
        self._check_secrets(content, errors)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_validation_service.py -v
```

Expected: ALL PASS (new tests and existing tests)

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/extensions/extension_validation_service.py python/tests/server/services/extensions/test_extension_validation_service.py
git commit -m "feat: add command-aware validation (frontmatter optional for commands)"
```

---

## Task 3: Backend — Add Command Seeding to ExtensionSeedingService

**Files:**
- Modify: `python/src/server/services/extensions/extension_seeding_service.py`
- Test: `python/tests/server/services/extensions/test_extension_seeding_service.py`

- [ ] **Step 1: Write failing test for `seed_commands` — flat file**

Add to `python/tests/server/services/extensions/test_extension_seeding_service.py`:

```python
SAMPLE_COMMAND_NO_FRONTMATTER = textwrap.dedent("""\
    # Cortex Setup — Register This Machine

    Connect this machine to Cortex.

    ## Phase 0: Health Check

    Call `health_check()` via the Cortex MCP tool.
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
    """Create a command .md file, optionally inside a group subdirectory."""
    if group:
        target_dir = base / group
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = base
    filepath = target_dir / filename
    filepath.write_text(content)
    return filepath


class TestSeedCommandsFlatFile:
    def test_creates_command_from_flat_md_file(self, service, mock_extension_service, tmp_path):
        """A .md file at the root of commands dir should be seeded as type='command'."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "cmd-1", "name": "cortex-setup"}

        _make_command_file(tmp_path, "cortex-setup.md", SAMPLE_COMMAND_NO_FRONTMATTER)

        counts = service.seed_commands(tmp_path)

        mock_extension_service.create_extension.assert_called_once()
        call_kwargs = mock_extension_service.create_extension.call_args
        assert call_kwargs[1]["name"] == "cortex-setup"
        assert call_kwargs[1]["type"] == "command"
        assert call_kwargs[1]["plugin_manifest"] == {"command_group": None, "filename": "cortex-setup.md"}
        assert counts["created"] == 1


class TestSeedCommandsGroupedFile:
    def test_creates_command_from_grouped_md_file(self, service, mock_extension_service, tmp_path):
        """A .md file inside a subdirectory should include the group in the name and metadata."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "cmd-2", "name": "cortex-prime"}

        _make_command_file(tmp_path, "cortex-prime.md", SAMPLE_COMMAND_WITH_FRONTMATTER, group="cortex")

        counts = service.seed_commands(tmp_path)

        mock_extension_service.create_extension.assert_called_once()
        call_kwargs = mock_extension_service.create_extension.call_args
        assert call_kwargs[1]["name"] == "cortex-prime"
        assert call_kwargs[1]["type"] == "command"
        assert call_kwargs[1]["plugin_manifest"] == {"command_group": "cortex", "filename": "cortex-prime.md"}
        assert counts["created"] == 1


class TestSeedCommandsGroupPrefixed:
    def test_prefixes_group_when_filename_does_not_include_it(self, service, mock_extension_service, tmp_path):
        """When filename doesn't start with group name, prefix group to avoid name collisions."""
        mock_extension_service.find_by_name.return_value = None
        mock_extension_service.create_extension.return_value = {"id": "cmd-3", "name": "agent-work-orders-commit"}

        content = "# Create Git Commit\n\nCreate an atomic commit."
        _make_command_file(tmp_path, "commit.md", content, group="agent-work-orders")

        counts = service.seed_commands(tmp_path)

        call_kwargs = mock_extension_service.create_extension.call_args
        assert call_kwargs[1]["name"] == "agent-work-orders-commit"
        assert call_kwargs[1]["plugin_manifest"] == {"command_group": "agent-work-orders", "filename": "commit.md"}


class TestSeedCommandsSkipUnchanged:
    def test_skips_command_when_hash_unchanged(self, service, mock_extension_service, tmp_path):
        """When content hash matches, the command should be skipped."""
        content_hash = ExtensionService.compute_content_hash(SAMPLE_COMMAND_NO_FRONTMATTER)
        mock_extension_service.find_by_name.return_value = {
            "id": "cmd-existing",
            "name": "cortex-setup",
            "content_hash": content_hash,
            "current_version": 1,
        }

        _make_command_file(tmp_path, "cortex-setup.md", SAMPLE_COMMAND_NO_FRONTMATTER)

        counts = service.seed_commands(tmp_path)

        mock_extension_service.create_extension.assert_not_called()
        mock_extension_service.update_extension.assert_not_called()
        assert counts["skipped"] == 1


class TestSeedCommandsEmptyDir:
    def test_returns_zero_counts_for_empty_directory(self, service, tmp_path):
        """An empty commands directory should return all-zero counts."""
        counts = service.seed_commands(tmp_path)
        assert counts == {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_seeding_service.py::TestSeedCommandsFlatFile -v
```

Expected: FAIL — `ExtensionSeedingService has no attribute 'seed_commands'`

- [ ] **Step 3: Implement `seed_commands` in ExtensionSeedingService**

Add to `python/src/server/services/extensions/extension_seeding_service.py`:

```python
@staticmethod
def default_commands_dir() -> Path:
    """Return the absolute path to the bundled commands directory."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "integrations" / "claude-code" / "commands"
        if candidate.is_dir():
            return candidate
    return Path(__file__).parents[5] / "integrations" / "claude-code" / "commands"

def seed_commands(self, commands_dir: Path | None = None) -> dict[str, int]:
    """Scan commands_dir and upsert every .md file into the registry as type='command'.

    Handles both flat files (root-level .md) and grouped files (subdirectory/*.md).
    Group directories provide the command namespace for slash commands.

    Args:
        commands_dir: Directory to scan. Defaults to ``default_commands_dir()``.

    Returns:
        Counts dict with keys ``created``, ``updated``, ``skipped``, ``errors``.
    """
    if commands_dir is None:
        commands_dir = self.default_commands_dir()

    counts: dict[str, int] = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    if not commands_dir.exists():
        logger.warning(f"Commands directory does not exist, skipping seed: {commands_dir}")
        return counts

    # Collect all .md files: flat (root) and grouped (subdirectory)
    command_files: list[tuple[Path, str | None]] = []  # (filepath, group_name_or_None)

    for entry in sorted(commands_dir.iterdir()):
        if entry.is_file() and entry.suffix == ".md":
            command_files.append((entry, None))
        elif entry.is_dir():
            for md_file in sorted(entry.glob("*.md")):
                command_files.append((md_file, entry.name))

    for filepath, group in command_files:
        try:
            self._seed_one_command(filepath, group, counts)
        except Exception:
            logger.error(f"Failed to seed command from {filepath}", exc_info=True)
            counts["errors"] += 1

    logger.info(
        f"Command seeding complete: {counts['created']} created, "
        f"{counts['updated']} updated, {counts['skipped']} skipped, "
        f"{counts['errors']} errors"
    )
    return counts

def _seed_one_command(self, filepath: Path, group: str | None, counts: dict[str, int]) -> None:
    """Upsert a single command .md file into the extension registry.

    Args:
        filepath: Absolute path to the command .md file.
        group: Subdirectory name (slash command namespace), or None for root-level commands.
        counts: Mutable counts dict updated in place.
    """
    content = filepath.read_text(encoding="utf-8")
    filename = filepath.name
    stem = filepath.stem  # filename without .md

    # Derive unique extension name
    if group and not stem.startswith(group):
        name = f"{group}-{stem}"
    else:
        name = stem

    # Extract description from frontmatter if present, else from first heading
    frontmatter = _parse_frontmatter(content)
    description = frontmatter.get("description", "")
    if not description:
        # Try to extract from first markdown heading
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# "):
                description = stripped[2:].strip()
                break

    content_hash = ExtensionService.compute_content_hash(content)
    existing = self.extension_service.find_by_name(name)

    command_metadata = {"command_group": group, "filename": filename}

    if existing is None:
        self.extension_service.create_extension(
            name=name,
            description=description,
            content=content,
            created_by="cortex-seeder",
            type="command",
            plugin_manifest=command_metadata,
        )
        logger.info(f"Created command extension: {name}")
        counts["created"] += 1
        return

    if existing["content_hash"] == content_hash:
        logger.debug(f"Command extension unchanged, skipping: {name}")
        counts["skipped"] += 1
        return

    self.extension_service.update_extension(
        existing["id"],
        content,
        new_version=existing["current_version"] + 1,
        updated_by="cortex-seeder",
        description=description or None,
    )
    logger.info(f"Updated command extension: {name} -> v{existing['current_version'] + 1}")
    counts["updated"] += 1
```

- [ ] **Step 4: Run all seeding tests**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/extensions/test_extension_seeding_service.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/extensions/extension_seeding_service.py python/tests/server/services/extensions/test_extension_seeding_service.py
git commit -m "feat: add seed_commands() to ExtensionSeedingService"
```

---

## Task 4: Backend — Wire Up Command Seeding at Startup

**Files:**
- Modify: `python/src/server/main.py:129-136`

- [ ] **Step 1: Add `seed_commands()` call in main.py startup**

In `python/src/server/main.py`, find the seeding block (around line 129-136) and add command seeding:

```python
seeder = ExtensionSeedingService()
counts = seeder.seed_extensions()
plugin_counts = seeder.seed_plugins()
command_counts = seeder.seed_commands()
total_created = counts["created"] + plugin_counts["created"] + command_counts["created"]
total_updated = counts["updated"] + plugin_counts["updated"] + command_counts["updated"]
total_skipped = counts["skipped"] + plugin_counts["skipped"] + command_counts["skipped"]
```

- [ ] **Step 2: Verify server starts without errors**

```bash
cd /home/winadmin/projects/Trinity/cortex && timeout 10 uv run python -m src.server.main || true
```

Expected: Server starts, logs show "Command seeding complete: N created, ..."

- [ ] **Step 3: Commit**

```bash
git add python/src/server/main.py
git commit -m "feat: seed commands at server startup"
```

---

## Task 5: Backend — Add `type` Filter to API Endpoints

**Files:**
- Modify: `python/src/server/api_routes/extensions_api.py:25-31` (request models)
- Modify: `python/src/server/api_routes/extensions_api.py:94-109` (list endpoint)
- Modify: `python/src/server/api_routes/extensions_api.py:129-179` (create endpoint)

- [ ] **Step 1: Add `type` to CreateExtensionRequest**

In `python/src/server/api_routes/extensions_api.py`, modify the request model:

```python
class CreateExtensionRequest(BaseModel):
    name: str
    description: str
    content: str
    created_by: str
    skill_groups: list[str] | None = None
    type: str | None = None
    plugin_manifest: dict | None = None
```

- [ ] **Step 2: Add `type` query parameter to list endpoint**

Modify the `list_extensions` endpoint:

```python
@router.get("/extensions")
async def list_extensions(
    include_content: bool = Query(False),
    skill_group: str | None = Query(None),
    type: str | None = Query(None),
):
    """List extensions. Filter with ?type=command, ?skill_group=template, ?include_content=true."""
    try:
        logfire.debug(f"Listing extensions | include_content={include_content} | skill_group={skill_group} | type={type}")
        service = ExtensionService()
        if include_content:
            extensions = service.list_extensions_full(skill_group=skill_group, type=type)
        else:
            extensions = service.list_extensions(skill_group=skill_group, type=type)
        return {"extensions": extensions, "count": len(extensions)}
```

- [ ] **Step 3: Pass `type` through in create endpoint**

In the `create_extension` endpoint, modify the validation and creation call:

```python
        # Validate content first
        validator = ExtensionValidationService()
        validation = validator.validate(request.content, extension_type=request.type or "skill")
        if not validation["valid"]:
            raise HTTPException(...)

        extension = service.create_extension(
            name=request.name,
            description=request.description,
            content=request.content,
            created_by=request.created_by,
            skill_groups=request.skill_groups,
            type=request.type,
            plugin_manifest=request.plugin_manifest,
        )
```

- [ ] **Step 4: Run existing API tests to verify no regressions**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/api_routes/ -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/server/api_routes/extensions_api.py
git commit -m "feat: add type field to extension API create and list endpoints"
```

---

## Task 6: Backend — Replace Static Commands Tarball with Registry-Backed Generation

**Files:**
- Modify: `python/src/mcp_server/mcp_server.py:938-967` (http_download_commands)

- [ ] **Step 1: Replace `http_download_commands` implementation**

Replace the existing static-file-based implementation with a registry-backed one that mirrors how `http_download_extensions` works:

```python
async def http_download_commands(request: Request):
    """Return all registered commands as a compressed tar archive.

    Fetches type='command' extensions from the registry and packages them
    using the command_group/filename structure from plugin_manifest metadata.
    Falls back to the static integrations/claude-code/commands/ directory
    if the registry query fails.
    """
    import io
    import tarfile

    import httpx
    from starlette.responses import Response

    from src.server.config.service_discovery import get_api_url

    try:
        api_url = get_api_url()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_url}/api/extensions",
                params={"include_content": True, "type": "command", "skill_group": "template"},
            )
            if response.status_code == 200:
                extensions = response.json().get("extensions", [])
                if extensions:
                    buf = io.BytesIO()
                    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                        for ext in extensions:
                            content = ext.get("content", "")
                            manifest = ext.get("plugin_manifest") or {}
                            group = manifest.get("command_group")
                            filename = manifest.get("filename") or f"{ext.get('name', 'unknown')}.md"

                            if group:
                                arcname = f"{group}/{filename}"
                            else:
                                arcname = filename

                            data = content.encode("utf-8")
                            info = tarfile.TarInfo(name=arcname)
                            info.size = len(data)
                            tar.addfile(info, io.BytesIO(data))
                    buf.seek(0)
                    return Response(
                        content=buf.read(),
                        media_type="application/gzip",
                        headers={"Content-Disposition": 'attachment; filename="commands.tar.gz"'},
                    )
    except (httpx.RequestError, Exception) as e:
        logger.warning(f"Registry-backed commands tarball failed, falling back to static: {e}")

    # Fallback: serve static files from integrations/claude-code/commands/
    for parent in Path(__file__).resolve().parents:
        commands_dir = parent / "integrations" / "claude-code" / "commands"
        if commands_dir.is_dir():
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for md_file in sorted(commands_dir.rglob("*.md")):
                    rel_path = md_file.relative_to(commands_dir)
                    tar.add(md_file, arcname=str(rel_path))
            buf.seek(0)
            return Response(
                content=buf.read(),
                media_type="application/gzip",
                headers={"Content-Disposition": 'attachment; filename="commands.tar.gz"'},
            )
    return JSONResponse({"error": "commands directory not found"}, status_code=404)
```

Note: the fallback now uses `rglob("*.md")` instead of `glob("*.md")` to include subdirectories.

- [ ] **Step 2: Verify the endpoint works**

Start the server and test:

```bash
curl -sf http://localhost:8051/cortex-setup/commands.tar.gz | tar tz
```

Expected: List of files like `cortex-setup.md`, `scan-projects.md` (and any grouped commands that have been seeded).

- [ ] **Step 3: Commit**

```bash
git add python/src/mcp_server/mcp_server.py
git commit -m "feat: replace static commands tarball with registry-backed generation"
```

---

## Task 7: Backend — Add `extension_type` Parameter to MCP Upload Tool

**Files:**
- Modify: `python/src/mcp_server/features/extensions/extension_tools.py:184-267` (manage_extensions signature)
- Modify: `python/src/mcp_server/features/extensions/extension_tools.py:288-385` (_handle_upload)

- [ ] **Step 1: Add `extension_type` parameter to `manage_extensions`**

In `python/src/mcp_server/features/extensions/extension_tools.py`, add the parameter:

```python
@mcp.tool()
async def manage_extensions(
    ctx: Context,
    action: str,
    # For sync
    local_extensions: list | None = None,
    system_fingerprint: str | None = None,
    system_name: str | None = None,
    hostname: str | None = None,
    os: str | None = None,
    project_id: str | None = None,
    # For upload / validate
    extension_content: str | None = None,
    extension_name: str | None = None,
    extension_type: str | None = None,
    # For install / remove
    extension_id: str | None = None,
    system_id: str | None = None,
) -> str:
```

Update the docstring Args section to include:

```
extension_type: Extension type for upload: "skill" (default), "command", or "plugin"
```

Pass `extension_type` to `_handle_upload`:

```python
elif action == "upload":
    return await _handle_upload(client, api_url, extension_content, extension_name, project_id, extension_type)
```

- [ ] **Step 2: Update `_handle_upload` to pass `type` to the API**

Modify the function signature and the create payload:

```python
async def _handle_upload(
    client: httpx.AsyncClient,
    api_url: str,
    extension_content: str | None,
    extension_name: str | None,
    project_id: str | None = None,
    extension_type: str | None = None,
) -> str:
```

In the `create_payload` construction, add:

```python
    create_payload: dict = {
        "name": name,
        "description": description,
        "content": extension_content,
        "created_by": "mcp-upload",
    }
    if project_id:
        create_payload["skill_groups"] = [project_id]
    if extension_type:
        create_payload["type"] = extension_type
```

- [ ] **Step 3: Add `type` filter to `find_extensions` list call**

In `find_extensions`, when listing all extensions, pass the `type` filter if a new `extension_type` parameter is provided. Add `extension_type: str | None = None` to the function signature:

```python
@mcp.tool()
async def find_extensions(
    ctx: Context,
    extension_id: str | None = None,
    query: str | None = None,
    project_id: str | None = None,
    include_content: bool = False,
    extension_type: str | None = None,
) -> str:
```

In the "List all extensions" branch, add type filter:

```python
                params: dict = {}
                if extension_type:
                    params["type"] = extension_type
                response = await client.get(urljoin(api_url, "/api/extensions"), params=params)
```

- [ ] **Step 4: Run MCP tool tests**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/mcp_server/features/extensions/ -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add python/src/mcp_server/features/extensions/extension_tools.py
git commit -m "feat: add extension_type parameter to MCP extension tools"
```

---

## Task 8: Frontend — Update Extension Types

**Files:**
- Modify: `cortex-ui/src/features/projects/extensions/types/index.ts`

- [ ] **Step 1: Extend the Extension type union and add CommandMetadata**

```typescript
export interface CommandMetadata {
  command_group: string | null;
  filename: string;
}

export interface Extension {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content?: string;
  content_hash: string;
  current_version: number;
  is_required: boolean;
  is_validated: boolean;
  tags: string[];
  type: "skill" | "plugin" | "command";
  plugin_manifest?: PluginManifest | CommandMetadata | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep -i "extensions" || echo "No type errors"
```

Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/extensions/types/index.ts
git commit -m "feat: extend Extension type to support 'command' type"
```

---

## Task 9: Frontend — Add Type Grouping to SystemExtensionList

**Files:**
- Modify: `cortex-ui/src/features/projects/extensions/components/SystemExtensionList.tsx`

- [ ] **Step 1: Add type grouping and type badges**

Replace the contents of `SystemExtensionList.tsx`:

```tsx
import type { Extension, SystemExtension } from "../types";
import { ExtensionStatusBadge } from "./ExtensionStatusBadge";

interface SystemExtensionListProps {
  systemExtensions: SystemExtension[];
  allExtensions: Extension[];
  onInstall: (extensionId: string) => void;
  onRemove: (extensionId: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  skill: "Skills",
  command: "Commands",
  plugin: "Plugins",
};

const TYPE_ORDER: string[] = ["skill", "command", "plugin"];

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    skill: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
    command: "bg-violet-500/20 text-violet-400 border-violet-500/30",
    plugin: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  };
  return (
    <span className={`px-1.5 py-0.5 text-[10px] rounded border ${colors[type] ?? "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"}`}>
      {type}
    </span>
  );
}

function groupByType<T extends { type?: string }>(items: T[]): Record<string, T[]> {
  const groups: Record<string, T[]> = {};
  for (const item of items) {
    const type = item.type ?? "skill";
    if (!groups[type]) groups[type] = [];
    groups[type].push(item);
  }
  return groups;
}

export function SystemExtensionList({ systemExtensions, allExtensions, onInstall, onRemove }: SystemExtensionListProps) {
  const installedExtensionIds = new Set(systemExtensions.map((se) => se.extension_id));
  const availableExtensions = allExtensions.filter((e) => !installedExtensionIds.has(e.id));

  // Group installed by type (via joined extension data)
  const installedByType: Record<string, SystemExtension[]> = {};
  for (const se of systemExtensions) {
    const type = se.cortex_extensions?.type ?? "skill";
    if (!installedByType[type]) installedByType[type] = [];
    installedByType[type].push(se);
  }

  const availableByType = groupByType(availableExtensions);

  const hasInstalled = systemExtensions.length > 0;
  const hasAvailable = availableExtensions.length > 0;

  return (
    <div className="space-y-4">
      {hasInstalled && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Installed Extensions</h4>
          <div className="space-y-3">
            {TYPE_ORDER.filter((t) => installedByType[t]?.length).map((type) => (
              <div key={type}>
                <div className="text-[11px] text-zinc-500 font-medium mb-1">{TYPE_LABELS[type] ?? type}</div>
                <div className="space-y-1">
                  {installedByType[type].map((se) => (
                    <div key={se.id} className="flex items-center justify-between p-2 rounded-md bg-white/5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white">
                          {se.cortex_extensions?.display_name || se.cortex_extensions?.name || se.extension_id}
                        </span>
                        <TypeBadge type={type} />
                      </div>
                      <div className="flex items-center gap-2">
                        <ExtensionStatusBadge status={se.status} hasLocalChanges={se.has_local_changes} />
                        <button
                          type="button"
                          onClick={() => onRemove(se.extension_id)}
                          className="px-2 py-1 text-xs rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {hasAvailable && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Available</h4>
          <div className="space-y-3">
            {TYPE_ORDER.filter((t) => availableByType[t]?.length).map((type) => (
              <div key={type}>
                <div className="text-[11px] text-zinc-500 font-medium mb-1">{TYPE_LABELS[type] ?? type}</div>
                <div className="space-y-1">
                  {availableByType[type].map((extension) => (
                    <div key={extension.id} className="flex items-center justify-between p-2 rounded-md bg-white/5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white">{extension.display_name || extension.name}</span>
                        <TypeBadge type={type} />
                        {extension.is_required && <span className="text-xs text-cyan-400">Required</span>}
                      </div>
                      <button
                        type="button"
                        onClick={() => onInstall(extension.id)}
                        className="px-3 py-1 text-xs rounded-md bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors"
                      >
                        Install
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasInstalled && !hasAvailable && (
        <div className="text-center py-8 text-zinc-500 text-sm">
          No extensions in the registry yet. Extensions are added when systems sync.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles and dev server renders**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/extensions/components/SystemExtensionList.tsx
git commit -m "feat: group extensions by type in SystemExtensionList with type badges"
```

---

## Task 10: Integration — Update cortex-extension-sync Skill

**Files:**
- Modify: `integrations/claude-code/extensions/cortex-extension-sync/SKILL.md`

- [ ] **Step 1: Update Phase 1 to scan commands directory**

In the Phase 1 section, after the skills scanning (1b), add command scanning:

Add a new section **1d. Find all command files**:

```markdown
### 1d. Find all command files

Scan for command definition files alongside extensions:
- `<install_dir>/commands/` (user-installed commands)
- `integrations/claude-code/commands/` (repo commands, if in Cortex repo)

```
Glob: <install_dir>/commands/**/*.md
Glob: integrations/claude-code/commands/**/*.md
```

### 1e. Parse each command

For each command `.md` file found:
1. Read the file content
2. Derive the extension name:
   - If file is in a subdirectory (group): use `{group}-{filename_stem}` if the stem doesn't already start with the group name, otherwise use `{filename_stem}`
   - If file is at root: use `{filename_stem}`
3. Compute SHA256 hash of the full content:
   ```bash
   sha256sum <filepath> | cut -d' ' -f1
   ```

Add to the `local_extensions` list: `[{name, content_hash}]`

Commands and skills share the same `local_extensions` list for the sync call.
```

- [ ] **Step 2: Update Phase 3 to install commands to correct path**

Replace Phase 3a with type-aware install logic:

```markdown
### 3a. Install pending extensions

For each item in `pending_install`:
1. Check the `type` field:
   - If `type == "command"`: Read `plugin_manifest` for `command_group` and `filename`. Write `content` to `<install_dir>/commands/{command_group}/{filename}` (create directory if needed). If no `command_group`, write to `<install_dir>/commands/{filename}`.
   - Otherwise (skill): Write `content` to `<install_dir>/skills/<name>/SKILL.md`
2. Report: "Installed {type}: <name>"
```

Update Phase 3b similarly for removals:

```markdown
### 3b. Remove pending extensions

For each item in `pending_remove`:
1. Check the `type` field:
   - If `type == "command"`: Read `plugin_manifest` for path info. Delete `<install_dir>/commands/{command_group}/{filename}` (or `<install_dir>/commands/{filename}`).
   - Otherwise (skill): Delete `<install_dir>/skills/<name>/SKILL.md`
2. Report: "Removed {type}: <name>"
```

- [ ] **Step 3: Remove Phase 3e (static commands download)**

Delete the entire "3e. Update slash commands" section. Commands are now synced through the registry like skills — no separate download step needed.

- [ ] **Step 4: Update Phase 4 summary to mention commands**

```markdown
> "**Extension sync complete:**
> - In sync: <N> extensions (<M> skills, <K> commands)
> - Installed: <list or 'none'>
> - Removed: <list or 'none'>
> - Updated: <list or 'none'>
> - Uploaded: <list or 'none'>
> - Skipped: <list or 'none'>"
```

- [ ] **Step 5: Commit**

```bash
git add integrations/claude-code/extensions/cortex-extension-sync/SKILL.md
git commit -m "feat: update extension-sync skill to handle command type"
```

---

## Task 11: Integration — Update cortex-bootstrap Skill

**Files:**
- Modify: `integrations/claude-code/extensions/cortex-bootstrap/SKILL.md`

- [ ] **Step 1: Add commands tarball download alongside extensions**

Find the phase where extensions are downloaded (Phase 5 in the bootstrap skill). After the extensions tarball download, add:

```markdown
### 5b. Download commands

```bash
curl -sf "<cortex_mcp_url>/cortex-setup/commands.tar.gz" | tar xz -C "<install_dir>/commands/"
```

Create the commands directory first:

```bash
mkdir -p "<install_dir>/commands"
```

If the download fails (e.g., no commands registered yet), warn but continue:
> "No commands available from the registry. Commands will be installed during the next extension sync."
```

- [ ] **Step 2: Commit**

```bash
git add integrations/claude-code/extensions/cortex-bootstrap/SKILL.md
git commit -m "feat: add commands tarball download to bootstrap skill"
```

---

## Task 12: Integration — Update Setup Scripts

**Files:**
- Modify: `integrations/claude-code/setup/cortexSetup.sh`
- Modify: `integrations/claude-code/setup/cortexSetup.bat`

- [ ] **Step 1: Update cortexSetup.sh to use commands tarball**

Find the section where individual commands are downloaded via curl (around lines 638-647). Replace the individual `curl` downloads with the tarball approach:

Replace:
```bash
curl -sf "$CORTEX_MCP_URL/cortex-setup.md" -o "$HOME/.claude/commands/cortex-setup.md"
curl -sf "$CORTEX_MCP_URL/scan-projects.md" -o "$HOME/.claude/commands/scan-projects.md"
```

With:
```bash
echo "📦 Downloading slash commands..."
mkdir -p "$HOME/.claude/commands"
if curl -sf "${CORTEX_MCP_URL}/cortex-setup/commands.tar.gz" | tar xz -C "$HOME/.claude/commands/"; then
    echo "✓ Slash commands installed"
else
    echo "⚠ Could not download commands from registry, trying individual files..."
    curl -sf "$CORTEX_MCP_URL/cortex-setup.md" -o "$HOME/.claude/commands/cortex-setup.md" 2>/dev/null || true
    curl -sf "$CORTEX_MCP_URL/scan-projects.md" -o "$HOME/.claude/commands/scan-projects.md" 2>/dev/null || true
fi
```

- [ ] **Step 2: Apply equivalent change to cortexSetup.bat**

Find the equivalent section in the `.bat` script and update similarly (using `tar` on Windows or PowerShell's `Invoke-WebRequest`).

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/setup/cortexSetup.sh integrations/claude-code/setup/cortexSetup.bat
git commit -m "feat: update setup scripts to use registry-backed commands tarball"
```

---

## Task 13: Move Distributable Commands to integrations Directory

**Files:**
- Modify: `integrations/claude-code/commands/` (add subdirectories)

This task populates `integrations/claude-code/commands/` with the commands that should be distributed to all Cortex-connected projects. Currently only `cortex-setup.md` and `scan-projects.md` exist there. The `.claude/commands/` directory contains Cortex-specific development commands that may or may not be appropriate for distribution.

- [ ] **Step 1: Decide which commands from `.claude/commands/` should be shared**

Review each command group and determine distribution scope:

| Group | Commands | Distribute? | Rationale |
|---|---|---|---|
| `cortex/` | cortex-prime, cortex-rca, cortex-alpha-review, etc. | Yes — Cortex-scoped | Useful for any project connected to Cortex |
| `agent-work-orders/` | commit, planning, execute, etc. | Yes — if work orders feature enabled | Core workflow commands |
| `prp-claude-code/` | prp-create, prp-execute, etc. | Yes | PRP framework commands |
| `prp-any-agent/` | prp-any-cli-create, prp-any-cli-execute | Yes | Agent-agnostic PRP commands |

This decision should be made by the user/team. For this task, copy the commands that are confirmed for distribution.

- [ ] **Step 2: Copy confirmed commands to `integrations/claude-code/commands/`**

For each confirmed group, create the subdirectory and copy files:

```bash
# Example for cortex group:
mkdir -p integrations/claude-code/commands/cortex
cp .claude/commands/cortex/*.md integrations/claude-code/commands/cortex/
```

Repeat for each confirmed group.

- [ ] **Step 3: Verify seeding picks them up**

Restart the server and check logs:

```bash
cd /home/winadmin/projects/Trinity/cortex && timeout 10 uv run python -m src.server.main 2>&1 | grep -i "command seeding"
```

Expected: "Command seeding complete: N created, ..."

- [ ] **Step 4: Commit**

```bash
git add integrations/claude-code/commands/
git commit -m "feat: add distributable command files to integrations directory"
```

---

## Task 14: Run Full Test Suite and Verify End-to-End

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/ -v
```

Expected: ALL PASS

- [ ] **Step 2: Run frontend type check**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Run frontend linter**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npm run biome
```

Expected: No errors

- [ ] **Step 4: Run backend linter**

```bash
cd /home/winadmin/projects/Trinity/cortex && uv run ruff check python/src/
```

Expected: No errors

- [ ] **Step 5: Manual end-to-end verification**

1. Start the server: `docker compose up --build -d`
2. Verify commands are seeded: `curl -s http://localhost:8181/api/extensions?type=command | python -m json.tool`
3. Verify commands tarball: `curl -sf http://localhost:8051/cortex-setup/commands.tar.gz | tar tz`
4. Open the UI, navigate to a project's Extensions tab, verify commands appear grouped separately from skills
5. Run `/cortex-extension-sync` in a connected project and verify commands sync correctly

- [ ] **Step 6: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix: address issues found during end-to-end verification"
```

---

## Propagation Steps

After all changes are complete:

| What changed | How to propagate |
|---|---|
| Backend Python (services, API routes) | Restart Docker: `docker compose restart cortex-server cortex-mcp` |
| Frontend (types, components) | Auto-reloads if `npm run dev` running; otherwise `npm run build` + refresh |
| MCP tools | `docker compose restart cortex-mcp` |
| Setup scripts | Re-download and re-run on each target machine |
| Extension sync skill | Restart backend, then run `/cortex-extension-sync` in each project |
| Bootstrap skill | Restart backend, then run `/cortex-bootstrap` on new machines |
