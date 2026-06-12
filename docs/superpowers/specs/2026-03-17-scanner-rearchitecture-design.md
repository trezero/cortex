# Local Project Scanner — Rearchitecture Design (Client-Side)

## Problem

The current scanner implementation runs entirely inside the Cortex Docker container via a volume mount (`~/projects:/projects:rw`). This means:

- Only the machine running Docker can scan its projects directory
- Multi-system setups (WSL, Windows, Mac, Ubuntu server) are locked out
- The Docker volume mount is a single-system coupling that breaks the core use case

## Solution

Move scanning and config-writing to the client side. A standalone Python script runs locally on each machine, orchestrated by a Claude Code skill. The Cortex backend only handles project creation via existing APIs.

## Architecture

```
User: "/scan-projects"
        |
        v
+-------------------------------------------------------+
|  /scan-projects Skill (orchestrator)                  |
|                                                        |
|  1. Preflight: verify registered, detect Python & OS   |
|  2. Download cortex-scanner.py from Cortex API         |
|  3. Run: <PYTHON> cortex-scanner.py --scan ~/projects  |
|  4. Fetch existing projects via MCP (find_projects)    |
|  5. Client-side dedup (compare normalized GitHub URLs) |
|  6. Claude generates descriptions from README content  |
|  7. Present results to user for confirmation           |
|  8. Create projects via MCP (manage_project)           |
|  9. Register system via MCP (per project)              |
|  10. Download extensions tarball from Cortex API       |
|  11. Run: <PYTHON> cortex-scanner.py --apply           |
|      --payload-file <TEMP>/payload.json                |
|      --extensions-tarball <TEMP>/extensions.tar.gz     |
|  12. Queue README crawls via MCP (batched, 5 at a time)|
|  13. Display final summary                             |
+-------------------------------------------------------+
```

### Key Properties
- Skill runs entirely on the user's machine via Claude Code
- Script touches local filesystem only (scan reads, apply writes)
- Project creation happens via existing MCP tools (`find_projects`, `manage_project`)
- No Docker volume mount needed
- Works on any system with Python 3.8+ and Claude Code
- Cross-platform: Windows, macOS, Linux (WSL included)

---

## Cross-Platform Compatibility

### Temp Directory
All temp file paths use Python's `tempfile.gettempdir()` semantics. The skill resolves the platform-appropriate temp directory before executing commands:
- Unix/macOS/WSL: `/tmp/`
- Windows: `%TEMP%` (typically `C:\Users\<user>\AppData\Local\Temp`)

The skill detects the OS and uses the correct path. Temp files are named with an `cortex-` prefix for easy identification:
- `<tempdir>/cortex-scanner.py`
- `<tempdir>/cortex-extensions.tar.gz`
- `<tempdir>/cortex-apply-payload.json`

### Python Executable
The `python3` command does not exist on Windows. The skill runs a preflight detection:
1. Try `python3 --version` — if it works, use `python3`
2. Fall back to `python --version` — verify output shows Python 3.x
3. If neither works: stop with "Python 3 not found. Please install Python 3.8+ and ensure it's on your PATH."

The detected executable is stored and used for all subsequent script invocations in the session.

### Shell Quoting
The skill avoids raw `curl` commands with inline JSON payloads (brittle across Bash/CMD/PowerShell). Instead:
- File downloads use simple `curl -s <url> -o <path>` (safe on all platforms)
- JSON payloads are written to temp files via Claude Code's Write tool, then passed as `--payload-file <path>`
- System registration uses an MCP tool (see Step 7) rather than curl with JSON body

---

## Components

### 1. Scanner Script (`cortex-scanner.py`)

**Location:** `python/src/server/static/cortex-scanner.py`
**Distribution:** Served via `GET /api/scanner/script`
**Requirements:** Python 3.8+, stdlib only (no pip dependencies)
**Size:** ~500 lines, single file

#### Scan Mode

```bash
python3 cortex-scanner.py --scan ~/projects
```

Outputs JSON to stdout:

```json
{
  "scan_id": "uuid",
  "scanned_at": "2026-03-17T...",
  "root_directory": "/home/user/projects",
  "projects": [
    {
      "directory_name": "RecipeRaiders",
      "absolute_path": "/home/user/projects/RecipeRaiders",
      "git_remote_url": "git@github.com:user/RecipeRaiders.git",
      "github_url": "https://github.com/user/RecipeRaiders",
      "detected_languages": ["javascript", "typescript"],
      "dependencies": {"npm": ["react", "firebase", "vite"]},
      "infra_markers": ["docker", "github-actions"],
      "project_indicators": ["node", "typescript"],
      "default_branch": "main",
      "has_readme": true,
      "readme_excerpt": "# RecipeRaiders\nA social recipe sharing...",
      "group_name": null,
      "is_group_parent": false
    }
  ],
  "groups": [
    {
      "name": "RecipeRaiders_Complete",
      "path": "/home/user/projects/RecipeRaiders_Complete",
      "children": ["RecipeRaiders", "reciperaiders-dashboard"]
    }
  ],
  "warnings": [
    "Permission denied: /home/user/projects/restricted-dir (skipped)"
  ],
  "summary": {
    "total_found": 12,
    "groups_found": 1
  }
}
```

#### Scan Logic (reused from existing `git_detector.py`)

- **Two-pass directory scan:** depth 1 for repos, depth 2 for groups
- **Skip list:** `node_modules`, `__pycache__`, `.venv`, `venv`, `.cache`, `.npm`, `.nvm`, `dist`, `build`, `.tox`, `vendor`, `target`, `.gradle`, `Pods`
- **Git remote parsing** from `.git/config`
- **GitHub URL normalization:** SSH to HTTPS, strip `.git` suffix, lowercase
- **README reading:** first 5000 chars as excerpt
- **Language detection** from file extensions (top-level + `src/`)
- **Dependency extraction** from `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`. For TOML files (`pyproject.toml`, `Cargo.toml`): uses `tomllib` (Python 3.11+) with a regex-based fallback parser for Python 3.8–3.10 that extracts `[project.dependencies]` and `[dependencies]` blocks. If both fail, dependency extraction is skipped for that file with a warning — the project is still detected
- **Infrastructure markers:** Dockerfile, docker-compose, `.github/workflows/`, `vercel.json`, terraform, k8s manifests

#### Apply Mode

```bash
python3 cortex-scanner.py --apply --payload-file /tmp/cortex-apply-payload.json --extensions-tarball /tmp/extensions.tar.gz
```

The payload is passed via a temp file (not CLI argument) to avoid shell `ARG_MAX` limits with 50+ projects.

Payload structure (written by the skill to a temp file):

```json
{
  "projects": [
    {
      "absolute_path": "/home/user/projects/RecipeRaiders",
      "project_id": "uuid-from-cortex",
      "project_title": "RecipeRaiders",
      "cortex_api_url": "http://localhost:8181",
      "cortex_mcp_url": "http://localhost:8051",
      "system_fingerprint": "abc123",
      "system_name": "WIN-AI-PC"
    }
  ]
}
```

Per project, apply writes:
- `.claude/cortex-config.json` — project_id, project_title, URLs, `installed_by: "scanner"`, extensions_hash (computed from tarball SHA-256), `extensions_installed_at` (ISO timestamp)
- `.claude/cortex-state.json` — system_fingerprint, system_name, cortex_project_id
- `.claude/settings.local.json` — PostToolUse observation hook
- `.gitignore` — append Cortex entries (idempotent, checks for `# Cortex` marker). Before appending, the script ensures the file ends with a newline to prevent corrupting the last existing rule (e.g., `node_modules# Cortex` if the file had no trailing newline)
- `.claude/skills/` — extract extensions tarball (if `--extensions-tarball` provided and file exists)

The `extensions_hash` is computed by the script from the tarball contents (SHA-256 of the file), not passed in the payload.

Outputs JSON summary to stdout with per-project status (created/failed/skipped).

If a single project fails (permissions, disk full), it logs the error and continues with the rest.

---

### 2. Script Distribution Endpoint

**File:** `python/src/server/api_routes/scanner_script_api.py`

Single endpoint:
- `GET /api/scanner/script` — returns `cortex-scanner.py` as `text/plain`
- No authentication (local-only deployment)
- Includes `X-Scanner-Version: 1.0` response header
- ~10 lines of code

The skill always re-downloads the script on each invocation. Since `/scan-projects` is run infrequently (typically once per system), caching is unnecessary. This ensures the user always gets the latest version.

---

### 3. Skill (`/scan-projects`)

**File:** `integrations/claude-code/skills/scan-projects.md`

Rigid, step-by-step skill:

#### Step 1 — Preflight Checks
- Verify `cortex-state.json` exists (`~/.claude/` or current project's `.claude/`)
- Extract `system_fingerprint` and `system_name`
- If not found: tell user to run `/cortex-setup` first, stop
- Detect Python executable: try `python3 --version`, fall back to `python --version` (verify 3.x)
- Detect OS temp directory: use `python -c "import tempfile; print(tempfile.gettempdir())"` or infer from OS
- Store `PYTHON_CMD` and `TEMP_DIR` for use in subsequent steps

#### Step 2 — Download Scanner Script
- `curl -s http://<cortex_api_url>/api/scanner/script -o <TEMP_DIR>/cortex-scanner.py`
- Cortex API URL from `cortex-config.json` or default `http://localhost:8181`
- If download fails: error with instructions to check Cortex is running

#### Step 3 — Run Scan
- Ask user for projects directory path (default: `~/projects`)
- `<PYTHON_CMD> <TEMP_DIR>/cortex-scanner.py --scan <path>`
- Parse JSON output

#### Step 4 — Deduplicate
- Call `find_projects` MCP tool to get all existing Cortex projects
- Compare GitHub URLs (normalized) between scan results and existing projects
- Mark matches as `already_in_cortex` with their `existing_project_id`

#### Step 5 — Present Results
- Display summary: total found, new, existing, groups
- For new projects with READMEs, generate 1-2 sentence descriptions
- Present list to user for confirmation
- User can exclude specific projects before proceeding

#### Step 6 — Create Projects in Cortex
- For each confirmed project, call `manage_project` MCP tool (`action: "create"`):
  - `title`: directory name
  - `description`: AI-generated description
  - `github_repo`: normalized GitHub URL
  - `tags`: detected languages + infra markers
  - `metadata`: `{ dependencies, scanned_from: absolute_path, scanner_version: "1.0" }`
- For project groups: create parent first (tagged `"project-group"`), then children with `parent_project_id`
- Collect all project IDs from responses — the `manage_project` tool returns `{"success": true, "project": {...}, "project_id": "...", "message": "..."}` synchronously

#### Step 7 — Register System
- For each created project, call the `manage_extensions` MCP tool with `action: "sync"` and the `project_id` and `system_fingerprint`
- This uses the same mechanism that `/cortex-setup` uses (extension sync service, table `cortex_project_system_registrations`)
- Links the current system to each project so Cortex knows which systems have which projects
- **Note:** A new MCP tool `register_system_to_project(project_id, system_fingerprint)` should be added if `manage_extensions` does not support a sync action. This avoids raw `curl` commands with JSON payloads which are brittle across platforms (Bash vs CMD vs PowerShell quoting)

#### Step 8 — Download Extensions Tarball
- Read `cortex_mcp_url` from `cortex-config.json` (same file used in Step 2 for `cortex_api_url`), default `http://localhost:8051`
- `curl -s http://<cortex_mcp_url>/cortex-setup/extensions.tar.gz -o <TEMP_DIR>/cortex-extensions.tar.gz`
- One download, reused for all projects

#### Step 9 — Apply Configs
- Build apply payload JSON with all project IDs, paths, titles, and system info
- Write payload to temp file using Claude Code's Write tool: `<TEMP_DIR>/cortex-apply-payload.json`
- `<PYTHON_CMD> <TEMP_DIR>/cortex-scanner.py --apply --payload-file <TEMP_DIR>/cortex-apply-payload.json --extensions-tarball <TEMP_DIR>/cortex-extensions.tar.gz`
- Parse output summary

#### Step 10 — Knowledge Base Ingestion
- For each project with a GitHub URL, call `manage_rag_source` MCP tool:
  ```
  manage_rag_source(
    action="add",
    source_type="url",
    title="<project_name> README",
    url="https://github.com/<owner>/<repo>#readme",
    project_id="<project_id>",
    knowledge_type="technical"
  )
  ```
- This queues a crawl of each project's GitHub README as a knowledge source
- **Rate limiting:** For large scans (20+ projects), the skill should batch these calls in groups of 5 with a brief pause between batches to avoid overwhelming the backend's embedding provider or hitting external rate limits. The backend's crawl queue is already async, but flooding it with 40+ simultaneous jobs can cause resource contention

#### Step 11 — Display Final Summary
- Per-project status (created, skipped, failed)
- Total setup time
- Any errors encountered
- Reminder: "Open Claude Code in any of these projects and Cortex context will be available"

---

## What Gets Removed

### Files
| File | Reason |
|------|--------|
| `python/src/server/api_routes/scanner_api.py` | Replaced by single script endpoint |
| `python/src/server/services/scanner/scanner_service.py` | Logic moves to client-side script |
| `python/src/server/services/scanner/git_detector.py` | Extracted into `cortex-scanner.py` |
| `python/src/server/services/scanner/scan_template.py` | Templates become skill parameters |
| `python/src/server/services/scanner/scan_report.py` | Report generation moves to skill |
| `python/src/server/services/scanner/url_normalizer.py` | URL normalization logic duplicated into `cortex-scanner.py` |
| `python/src/server/services/scanner/cleanup.py` | Cleanup loop removed (scanner tables dropped) |
| `python/src/server/services/scanner/__init__.py` | Package removed |
| `python/src/server/config/scanner_config.py` | No server-side config needed |
| `python/src/mcp_server/features/scanner/scanner_tools.py` | No MCP tools — skill only |
| `python/src/mcp_server/features/scanner/__init__.py` | Package removed |
| `python/tests/server/services/scanner/test_scanner_service.py` | Tests move to script tests |

### Database
- Drop `cortex_scan_results` table
- Drop `cortex_scan_projects` table
- Drop `cortex_scanner_templates` table
- New migration: `019_drop_scanner_tables.sql`

### Docker
- Remove volume mount: `${PROJECTS_DIRECTORY:-~/projects}:/projects:rw`
- Remove env vars: `SCANNER_PROJECTS_ROOT`, `SCANNER_ENABLED`
- Remove from `.env.example`: `PROJECTS_DIRECTORY`, `SCANNER_ENABLED`

### Router Registration
- Remove scanner router from `python/src/server/main.py`
- Remove scanner tools registration from MCP server init
- Remove cleanup loop registration (`start_cleanup_loop()`) from `main.py` startup
- Add scanner script router to `python/src/server/main.py`

---

## Error Handling

### Script Errors (scan mode)
| Scenario | Behavior |
|----------|----------|
| Projects directory doesn't exist | Exit code 1, JSON error: `"Directory not found: /path"` |
| No Python 3 on system | Skill detects before running, tells user to install |
| Permission denied on subdirectory | Skip that directory, include in `warnings` array, continue |
| No git repos found | Success with `total_found: 0`, empty projects array |
| Corrupt `.git/config` | Skip that repo, include in warnings |
| 500+ subdirectories | No hard limit, scans all, includes count in summary |

### Script Errors (apply mode)
| Scenario | Behavior |
|----------|----------|
| Can't create `.claude/` (permissions) | Log failure, continue with other projects |
| Extensions tarball missing/corrupt | Skip extensions, still write configs, warn |
| Path in payload doesn't exist | Skip that project, report as failed |
| Existing `.claude/` from prior setup | Overwrite — apply is idempotent |
| Disk full | Fail on that project, continue with others |

### Skill Errors
| Scenario | Behavior |
|----------|----------|
| Cortex not running | Stop: "Can't reach Cortex at <url>. Is it running?" |
| No `cortex-state.json` | Stop: "System not registered. Run /cortex-setup first." |
| `manage_project` fails for one project | Log failure, continue creating others |
| User cancels at confirmation | Stop cleanly, no changes made |
| Script outputs invalid JSON | Stop with error, show raw output for debugging |
| Extensions tarball download fails | Warn, offer to continue without extensions |

### Idempotency
- **Re-scan:** Always safe — reads filesystem, outputs fresh JSON
- **Re-dedup:** Always accurate — fetches current Cortex projects each time
- **Re-apply configs:** Safe — overwrites existing files with same content
- **Re-create projects:** Skill checks dedup before calling `manage_project`
- **`.gitignore` updates:** Script checks for `# Cortex` marker before appending

---

## Testing

### Script Tests (`python/tests/test_cortex_scanner.py`)

Tests import the script directly. Use `tempfile.mkdtemp()` for disposable directory structures.

| Test | What it verifies |
|------|-----------------|
| Scan empty directory | `total_found: 0`, no errors |
| Scan with git repos | Correct detection, metadata extraction |
| Scan with nested group | Two-pass detection, group parent + children |
| Skip list honored | `node_modules`, etc. not in results |
| Git remote parsing | SSH, HTTPS, no-remote all handled |
| GitHub URL normalization | SSH to HTTPS, `.git` strip, case-insensitive |
| Dependency extraction | npm, pip, cargo, go parsers correct |
| Infra marker detection | Dockerfile, workflows, vercel.json detected |
| README excerpt | First 5000 chars, missing README handled |
| Apply writes config files | Correct JSON in `.claude/*.json` |
| Apply writes settings.local.json | PostToolUse hook present |
| Apply updates .gitignore | Entries appended, idempotent on re-run |
| Apply extracts extensions | Tarball extracted to `.claude/skills/` |
| Apply handles permission errors | Fails gracefully, continues others |
| Apply with missing tarball | Configs written, extensions skipped |
| .gitignore without trailing newline | Newline inserted before Cortex block, no corruption |
| .gitignore already has trailing newline | No extra blank line added |
| TOML parsing on Python 3.10 | Regex fallback extracts dependencies correctly |
| TOML parsing on Python 3.11+ | `tomllib` used, correct results |

No Docker or Cortex instance needed for any tests.

### Journey Test
`docs/userJourneys/projectScannerJourney.md` will be rewritten to reflect:
- No Docker volume mount setup in Phase 0
- Skill invocation instead of MCP tools in Phase 1
- Client-side dedup in Phase 4
- Templates as skill parameters in Phase 8
- New edge case: Python not found on system
- Removed edge case: scanner disabled (no feature flag)
