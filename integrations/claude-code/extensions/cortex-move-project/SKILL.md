---
name: cortex-move-project
description: Move the Cortex project directory to a new location. Handles pre-move preparation (backup, checklist) and post-move cleanup (venv regeneration, memory migration, path updates). Use when the user says "move project", "move cortex", "relocate repo", or "change project directory".
---

# Move Cortex Project

Assists with relocating the Cortex project directory. Handles the full lifecycle: pre-move preparation (backup, clean git state) and post-move fixup (venv regeneration, Claude Code memory migration, stale path replacement, Docker verification).

**Invocation:** `/cortex-move-project`

---

## Phase 0: Detect State

Determine whether the user needs pre-move or post-move actions.

### 0a. Ask the user

> "Are you **preparing to move** the Cortex project, or have you **already moved** it?"
>
> 1. **Pre-move** — Haven't moved yet; need to prepare and back up
> 2. **Post-move** — Already moved; need to fix up the new location

### 0b. Auto-detect hint (optional)

If `.claude/cortex-state.json` exists, read it. If the paths stored in it match `$(pwd)`, the user is likely already working from the new location (post-move). Mention this observation but still let the user confirm.

**If Pre-move:** proceed to Phase 1.
**If Post-move:** proceed to Phase 2.

---

## Phase 1: Pre-Move

Prepare the project for relocation.

### 1a. Verify clean git state

```bash
set -euo pipefail
git status --porcelain
```

If there is output (uncommitted changes), warn the user:

> "There are uncommitted changes. It is strongly recommended to commit or stash before moving. Continue anyway?"

Wait for confirmation. If the user declines, stop.

### 1b. Record current path

```bash
set -euo pipefail
CURRENT_DIR="$(cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && pwd)"
echo "$CURRENT_DIR"
```

Store this as `<old_path>`. Print it:

> "Current Cortex directory: `<old_path>`"
> "Remember this path -- you will need it if running post-move from a fresh session."

### 1c. Run backup

Suggest the pre-move backup:

> "Running a tagged backup before the move..."

```bash
set -euo pipefail
CORTEX_DIR="$(cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && pwd)"
"$CORTEX_DIR/scripts/backup/cortex-backup.sh" --tag "pre-move"
```

If the backup script does not exist or fails, report the error but continue:

> "Backup script not found or failed. Proceeding without backup -- ensure you have a recent backup elsewhere."

### 1d. Ask for target location

> "Where do you want to move the project? Provide the **full target path** (e.g., `/home/winadmin/repos/cortex`)."

Wait for the user to provide `<target_path>`.

Validate:
- `<target_path>` must be an absolute path (starts with `/`)
- The parent directory of `<target_path>` must exist:
  ```bash
  set -euo pipefail
  test -d "$(dirname '<target_path>')" && echo "OK" || echo "MISSING"
  ```
- `<target_path>` itself must NOT already exist:
  ```bash
  set -euo pipefail
  test -e '<target_path>' && echo "EXISTS" || echo "OK"
  ```

If validation fails, report the issue and ask again.

### 1e. Generate move commands

Print the exact commands the user will run in their terminal:

> "Run the following commands to move the project:"
>
> ```bash
> mv <old_path> <target_path>
> cd <target_path>
> ```
>
> After moving, open a new Claude Code session from `<target_path>` and run `/cortex-move-project` again, selecting **Post-move**.

Stop here. The user must perform the filesystem move themselves.

---

## Phase 2: Post-Move

Fix up the project after it has been relocated. Execute these steps automatically, asking for confirmation before any destructive action.

### 2a. Compute current path and namespace

```bash
set -euo pipefail
CURRENT_DIR="$(cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && pwd)"
CURRENT_SLUG="$(echo "$CURRENT_DIR" | sed 's|^/||; s|/|-|g')"
CURRENT_NAMESPACE="-${CURRENT_SLUG}"
echo "CURRENT_DIR=$CURRENT_DIR"
echo "CURRENT_NAMESPACE=$CURRENT_NAMESPACE"
```

Store `<current_dir>`, `<current_namespace>`.

### 2b. Detect old project directory

Claude Code stores project memory in `~/.claude/projects/<namespace>/memory/`. The namespace is the absolute path with a leading dash and all slashes replaced by dashes.

Scan for candidate old project directories:

```bash
set -euo pipefail
CURRENT_NAMESPACE="<current_namespace>"
echo "=== All project directories ==="
ls -1d ~/.claude/projects/*/ 2>/dev/null | while read -r dir; do
    ns="$(basename "$dir")"
    # Skip the current namespace
    if [ "$ns" = "$CURRENT_NAMESPACE" ]; then
        continue
    fi
    # Check if this looks like an Cortex project (has cortex-state.json or MEMORY.md with cortex references)
    if [ -f "$dir/memory/MEMORY.md" ]; then
        if grep -qi "cortex" "$dir/memory/MEMORY.md" 2>/dev/null; then
            echo "CANDIDATE: $ns"
            echo "  Path: $dir"
            if [ -d "$dir/memory" ]; then
                echo "  Memory files: $(ls "$dir/memory/" 2>/dev/null | wc -l)"
            fi
        fi
    fi
done
echo "=== Done ==="
```

If **no candidates** are found:

> "No old Cortex project directories found in `~/.claude/projects/`. This may be a fresh install or the old directory was already cleaned up. Skipping memory migration."

Proceed to step 2d.

If **one candidate** is found, store it as `<old_namespace>` and continue.

If **multiple candidates** are found, list them and ask the user to select:

> "Found multiple potential old project directories:
>
> 1. `<namespace_1>` (N memory files)
> 2. `<namespace_2>` (M memory files)
>
> Which one is the old Cortex project? Enter a number, or 'skip' to skip memory migration."

Store the selection as `<old_namespace>`.

### 2c. Migrate Claude Code memory

If `<old_namespace>` was identified:

```bash
set -euo pipefail
OLD_DIR="$HOME/.claude/projects/<old_namespace>"
NEW_DIR="$HOME/.claude/projects/<current_namespace>"
mkdir -p "$NEW_DIR/memory"
if [ -d "$OLD_DIR/memory" ] && [ "$(ls -A "$OLD_DIR/memory" 2>/dev/null)" ]; then
    cp -rn "$OLD_DIR/memory/"* "$NEW_DIR/memory/" 2>/dev/null || true
    echo "Copied memory files from $OLD_DIR/memory/ to $NEW_DIR/memory/"
    echo "Files in new memory dir:"
    ls -la "$NEW_DIR/memory/"
else
    echo "No memory files to copy from $OLD_DIR/memory/"
fi
```

> "Memory files have been copied to the new namespace. The old directory has NOT been deleted yet."

Derive `<old_path>` from `<old_namespace>` for later use in path replacement:

```bash
set -euo pipefail
OLD_NAMESPACE="<old_namespace>"
# Remove leading dash, replace dashes with slashes
OLD_PATH="/$(echo "$OLD_NAMESPACE" | sed 's|^-||; s|-|/|g')"
echo "OLD_PATH=$OLD_PATH"
```

Store as `<old_path>`.

### 2d. Regenerate Python virtual environments

> "Regenerating Python virtual environment..."

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
cd "$CORTEX_DIR/python"
rm -rf .venv
uv sync --group all
echo "Main venv regenerated at $CORTEX_DIR/python/.venv"
```

If `uv` is not found, report:

> "`uv` is not installed or not in PATH. Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` and then run `cd <current_dir>/python && uv sync --group all` manually."

Check for the cortex-memory plugin venv:

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
PLUGIN_DIR="$CORTEX_DIR/.claude/plugins/cortex-memory"
if [ -d "$PLUGIN_DIR" ] && [ -f "$PLUGIN_DIR/requirements.txt" ]; then
    echo "Found cortex-memory plugin, regenerating venv..."
    rm -rf "$PLUGIN_DIR/.venv"
    cd "$PLUGIN_DIR"
    python3 -m venv .venv
    "$PLUGIN_DIR/.venv/bin/pip" install -r requirements.txt
    echo "Plugin venv regenerated at $PLUGIN_DIR/.venv"
else
    echo "No cortex-memory plugin found, skipping."
fi
```

### 2e. Update stale path references in documentation

Only run this step if `<old_path>` was identified in step 2c.

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
OLD_PATH="<old_path>"
NEW_PATH="<current_dir>"

# Skip if old and new paths are identical
if [ "$OLD_PATH" = "$NEW_PATH" ]; then
    echo "Old and new paths are identical. Nothing to update."
    exit 0
fi

echo "Searching for old path references in docs/..."
MATCH_COUNT=0
FILE_COUNT=0
while IFS= read -r file; do
    count=$(grep -c "$OLD_PATH" "$file" 2>/dev/null || true)
    if [ "$count" -gt 0 ]; then
        echo "  $file: $count occurrence(s)"
        MATCH_COUNT=$((MATCH_COUNT + count))
        FILE_COUNT=$((FILE_COUNT + 1))
    fi
done < <(find "$CORTEX_DIR/docs" -name "*.md" -type f 2>/dev/null)

echo ""
echo "Found $MATCH_COUNT occurrence(s) in $FILE_COUNT file(s)."
```

If occurrences are found, ask for confirmation:

> "Found `<MATCH_COUNT>` references to the old path across `<FILE_COUNT>` files under `docs/`. Replace all with the new path?"

If confirmed:

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
OLD_PATH="<old_path>"
NEW_PATH="<current_dir>"

find "$CORTEX_DIR/docs" -name "*.md" -type f -exec \
    sed -i "s|$OLD_PATH|$NEW_PATH|g" {} +

echo "Path references updated."
```

Also check `.claude/` for stale paths:

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
OLD_PATH="<old_path>"
NEW_PATH="<current_dir>"

echo "Checking .claude/ directory for stale path references..."
while IFS= read -r file; do
    count=$(grep -c "$OLD_PATH" "$file" 2>/dev/null || true)
    if [ "$count" -gt 0 ]; then
        echo "  $file: $count occurrence(s)"
        sed -i "s|$OLD_PATH|$NEW_PATH|g" "$file"
        echo "    -> Updated"
    fi
done < <(find "$CORTEX_DIR/.claude" -name "*.json" -o -name "*.md" -type f 2>/dev/null)
```

### 2f. Verify Docker Compose

```bash
set -euo pipefail
cd "<current_dir>"
docker compose config --quiet 2>&1 && echo "Docker Compose config is valid." || echo "DOCKER_COMPOSE_ERROR"
```

If the output contains `DOCKER_COMPOSE_ERROR`, report:

> "Docker Compose configuration has errors. Run `docker compose config` to see details and fix any path issues."

### 2g. Verify backup scripts

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
SCRIPT="$CORTEX_DIR/scripts/backup/cortex-backup.sh"
if [ -f "$SCRIPT" ]; then
    # Extract the path resolution logic to verify it resolves correctly
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT")" && pwd)"
    RESOLVED_CORTEX_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
    CORTEX_PATH_SLUG="$(echo "$RESOLVED_CORTEX_DIR" | sed 's|^/||; s|/|-|g')"
    RESOLVED_MEMORY_DIR="$HOME/.claude/projects/-${CORTEX_PATH_SLUG}/memory"
    echo "Backup script resolves:"
    echo "  CORTEX_DIR  = $RESOLVED_CORTEX_DIR"
    echo "  MEMORY_DIR  = $RESOLVED_MEMORY_DIR"
    if [ "$RESOLVED_CORTEX_DIR" = "$CORTEX_DIR" ]; then
        echo "  Status: Paths resolve correctly to the new location."
    else
        echo "  WARNING: CORTEX_DIR resolved to $RESOLVED_CORTEX_DIR, expected $CORTEX_DIR"
    fi
else
    echo "Backup script not found at $SCRIPT -- skipping verification."
fi
```

### 2h. Update cortex-state.json

If `.claude/cortex-state.json` exists and `<old_path>` was identified:

Read `.claude/cortex-state.json`. For every string field value that contains `<old_path>`, replace it with `<current_dir>`. Write the updated file back.

If `.claude/cortex-state.json` does not exist, skip this step.

### 2i. Frontend dependencies

```bash
set -euo pipefail
CORTEX_DIR="<current_dir>"
if [ -d "$CORTEX_DIR/cortex-ui/node_modules" ]; then
    echo "node_modules exists. Native modules may have stale paths."
    echo "NEEDS_REBUILD=true"
else
    echo "No node_modules found."
    echo "NEEDS_REBUILD=false"
fi
```

If `NEEDS_REBUILD=true`:

> "Frontend `node_modules` exist and may contain native modules with stale paths. Run `cd <current_dir>/cortex-ui && npm install` to rebuild?"

If confirmed:

```bash
set -euo pipefail
cd "<current_dir>/cortex-ui"
npm install
echo "Frontend dependencies rebuilt."
```

If declined, remind:

> "If the frontend fails to start, run `cd <current_dir>/cortex-ui && npm install`."

### 2j. Cleanup prompt

Only show this if `<old_namespace>` was identified in step 2b.

> "Would you like to remove the old Claude Code project directory at `~/.claude/projects/<old_namespace>/`? Memory has already been copied to the new namespace."
>
> - **Yes** — Delete the old directory
> - **No** — Keep it (you can remove it manually later)

If yes:

```bash
set -euo pipefail
rm -rf "$HOME/.claude/projects/<old_namespace>"
echo "Removed old project directory."
```

### 2k. Final verification and summary

Print a summary of everything that was done:

> "## Post-Move Complete
>
> **New location:** `<current_dir>`
> **New Claude namespace:** `<current_namespace>`
>
> ### Actions taken:
> - Memory migration: <Copied N files from old namespace / Skipped (no old namespace found)>
> - Python venv: Regenerated at `python/.venv`
> - Plugin venv: <Regenerated / Not found>
> - Doc path updates: <Updated N occurrences in M files / No old path to replace / No stale references found>
> - Docker Compose: <Valid / Errors found (see above)>
> - Backup scripts: <Paths resolve correctly / Not found>
> - cortex-state.json: <Updated / No changes needed / Not found>
> - Frontend deps: <Rebuilt / Skipped / Not found>
> - Old namespace cleanup: <Removed / Kept>
>
> ### Next steps:
> 1. Run `docker compose up --build -d` to restart services with the new paths.
> 2. Verify the UI loads: `cd <current_dir>/cortex-ui && npm run dev`
> 3. Test a knowledge search to confirm Supabase connectivity.
> 4. Run `/cortex-bootstrap` if extensions need re-registration."

---

## Important Notes

### Path Computation
All paths are computed dynamically using `git rev-parse --show-toplevel` or `pwd`. No paths are hardcoded in this skill.

### Namespace Format
Claude Code project namespaces are derived from the absolute directory path: strip the leading `/`, replace all `/` with `-`, then prefix with `-`. For example:
- `/home/winadmin/projects/cortex` becomes `-home-winadmin-projects-cortex`

### Non-Destructive by Default
The skill never deletes data without explicit user confirmation. Memory files are copied (not moved), and the old namespace directory is only removed if the user opts in.

### No MCP Tools Required
This skill is fully self-contained using filesystem operations and shell commands. No Cortex MCP tools are needed.

### Error Recovery
- If venv regeneration fails, the skill reports the error and continues with remaining steps.
- If Docker Compose validation fails, the skill reports it but does not attempt to fix it.
- If memory migration finds no old namespace, it skips gracefully.
- If the backup script is missing, the pre-move phase continues without backup.

### Edge Cases Handled
- **Fresh install moved before Claude Code was used:** No old project namespace exists. Memory migration is skipped. All other steps proceed normally.
- **Multiple candidate old namespaces:** The user is prompted to select the correct one.
- **Old and new paths are identical:** Path replacement is skipped with a message.
- **Missing tools (uv, docker, npm):** Each step checks for the tool and reports clearly if it is not available.
