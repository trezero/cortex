---
name: archon-extension-sync
description: Sync local Claude Code extensions with the Archon extension registry. Detects new extensions, local modifications, and pending installs. Use when "sync extensions", "check extensions", "update extensions", or at startup when sync is stale.
---

# Archon Extension Sync

Synchronizes local Claude Code extensions with the Archon extension registry. Detects drift, handles conflict resolution, installs pending extensions, and uploads new local extensions.

**Invocation:** `/archon-extension-sync`
**Auto-trigger:** Runs automatically when any Archon extension detects last_extension_sync > 24h in `.claude/archon-state.json`

---

## Phase 0: Compute Machine Fingerprint

### 0a. Gather system info

```bash
hostname
```

```bash
whoami
```

```bash
uname -s
```

### 0b. Compute fingerprint

Concatenate: `<hostname>|<username>|<os>` and compute SHA256:

```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

Store as `system_fingerprint`.

---

## Phase 1: Scan Local Extensions

### 1a. Determine install scope

Read `.claude/archon-config.json` if it exists (fall back to `~/.claude/archon-config.json`). Extract:
- `install_scope` → `<install_scope>` (may be absent)

Determine `<install_dir>`:
- If `<install_scope>` is `"project"` → `.claude`
- If `<install_scope>` is `"global"` or absent → `~/.claude`

### 1b. Find all extension definition files

Scan these directories for SKILL.md extension definition files:
- `<install_dir>/skills/` (user-installed extensions)
- `integrations/claude-code/extensions/` (repo extensions, if in Archon repo)
- Any directory listed in `.claude/archon-state.json` under `extension_directories`

```
Glob: <install_dir>/skills/**/SKILL.md
Glob: integrations/claude-code/extensions/**/SKILL.md
```

### 1c. Parse each extension

For each extension definition file found:
1. Read the file content
2. Parse YAML frontmatter to extract `name`
3. Compute SHA256 hash of the full content:
   ```bash
   sha256sum <filepath> | cut -d' ' -f1
   ```

Build `local_extensions` list: `[{name, content_hash}]`

### 1d. Find all command files

Scan for command definition files alongside extensions:
- `<install_dir>/commands/` (user-installed commands)
- `integrations/claude-code/commands/` (repo commands, if in Archon repo)

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

---

## Phase 2: Sync with Archon

### 2a. Read project state

Read `.claude/archon-state.json` for `archon_project_id`.

If no project ID:
> "No Archon project linked. Run `/link-to-project` first to associate this repo with an Archon project."

Stop here.

### 2b. Call sync

```
manage_extensions(
    action="sync",
    local_extensions=<local_extensions list>,
    system_fingerprint="<fingerprint>",
    project_id="<archon_project_id>"
)
```

### 2c. Handle first-time registration

If response has `system.is_new == true`:

Ask the user:
> "This is the first time this machine is connecting to Archon. What name should we use for this system?"
>
> Suggestion: `<hostname>`

Store the user's choice, then re-call:
```
manage_extensions(
    action="sync",
    local_extensions=<local_extensions list>,
    system_fingerprint="<fingerprint>",
    system_name="<user-provided-name>",
    project_id="<archon_project_id>"
)
```

---

## Phase 3: Process Sync Results

### 3a. Install pending extensions

For each item in `pending_install`:
1. Check the `type` field:
   - If `type == "command"`: Read `plugin_manifest` for `command_group` and `filename`. Write `content` to `<install_dir>/commands/{command_group}/{filename}` (create directory if needed). If no `command_group`, write to `<install_dir>/commands/{filename}`.
   - Otherwise (skill): Write `content` to `<install_dir>/skills/<name>/SKILL.md`
2. Report: "Installed {type}: <name>"

### 3b. Remove pending extensions

For each item in `pending_remove`:
1. Check the `type` field:
   - If `type == "command"`: Read `plugin_manifest` for path info. Delete `<install_dir>/commands/{command_group}/{filename}` (or `<install_dir>/commands/{filename}`).
   - Otherwise (skill): Delete `<install_dir>/skills/<name>/SKILL.md`
2. Report: "Removed {type}: <name>"

### 3c. Resolve local changes

For each item in `local_changes`, ask the user:

> "Extension **<name>** has local modifications (local hash: `<local_hash>`, Archon hash: `<archon_hash>`). What would you like to do?"

Options:
- **Update Source** — Push local content to Archon as a new version
- **Save as Project Version** — Store as a project-specific override
- **Create New Extension** — Upload as a new extension with a different name
- **Discard Changes** — Overwrite local with Archon version

**If Update Source:**
Read the local file content, then:
```
manage_extensions(action="upload", extension_content="<local content>")
```

**If Save as Project Version:**
Read the local file content. The backend stores it as a project override (future API call).

**If Create New Extension:**
Ask for a new name, then:
```
manage_extensions(action="validate", extension_content="<local content>")
```
If validation passes:
```
manage_extensions(action="upload", extension_content="<local content>", extension_name="<new-name>")
```

**If Discard Changes:**
Fetch the Archon version via `find_extensions(extension_id="<extension_id>")` and overwrite the local file.

### 3d. Handle unknown local extensions

For each item in `unknown_local`, ask the user:

> "Found local extension **<name>** not in Archon. Would you like to upload it to the registry?"

Options:
- **Upload** — Validate and upload
- **Skip** — Leave as local-only

**If Upload:**
Read the local file, then:
```
manage_extensions(action="validate", extension_content="<content>")
```
If validation passes (or user accepts warnings):
```
manage_extensions(action="upload", extension_content="<content>")
```
If validation has errors, show them and ask user to fix.

---

## Phase 4: Update State

### 4a. Write sync timestamp

Update `.claude/archon-state.json`:
```json
{
  "last_extension_sync": "<ISO timestamp>",
  "system_fingerprint": "<fingerprint>",
  "system_name": "<name>"
}
```

Merge with existing state — do not overwrite other fields.

### 4b. Summary

> "**Extension sync complete:**
> - In sync: <N> extensions (<M> skills, <K> commands)
> - Installed: <list or 'none'>
> - Removed: <list or 'none'>
> - Updated: <list or 'none'>
> - Uploaded: <list or 'none'>
> - Skipped: <list or 'none'>"

---

## Important Notes

### Sync Freshness

Other Archon extensions check sync freshness in their Phase 0:
```
Read .claude/archon-state.json
If last_extension_sync is missing or older than 24h:
  → Run /archon-extension-sync before continuing
```

### Extension File Locations

- **Installed skills:** `<install_dir>/skills/<name>/SKILL.md`
  - Project scope (`install_scope: "project"`): `.claude/skills/`
  - Global scope (`install_scope: "global"`): `~/.claude/skills/`
- **Installed commands:** `<install_dir>/commands/{group}/{filename}.md` or `<install_dir>/commands/{filename}.md`
- **Repo skills:** `integrations/claude-code/extensions/<name>/SKILL.md`
- **Repo commands:** `integrations/claude-code/commands/{group}/{filename}.md`
- Skills are identified by their frontmatter `name` field, not directory name
- Commands are identified by their file path (group + filename)

### Error Recovery

- If Archon is unreachable, skip sync and continue with stale state
- If a single extension install/upload fails, continue with remaining operations
- Always save the sync timestamp even if some operations failed (prevents retry loops)
