# Scan Local Projects

Scan a local projects directory for Git repositories and bulk-onboard them into Archon. Downloads a scanner script, detects repos, creates Archon projects via MCP, and writes config files — all from the current machine.

## Prerequisites
- System must be registered with Archon (run `/archon-setup` in any project first)
- Archon stack must be running

## Procedure

Follow these steps exactly in order. Do not skip steps.

### Step 1 — Preflight Checks

1. Look for `archon-state.json` in `~/.claude/` or the current project's `.claude/` directory. Read it.
2. Extract `system_fingerprint` and `system_name`. If the file is not found, tell the user: "System not registered. Run /archon-setup in any project first." and STOP.
3. Look for `archon-config.json` in the same locations. Extract `archon_api_url` (default: `http://localhost:8181`) and `archon_mcp_url` (default: `http://localhost:8051`).
4. Detect the Python executable:
   - Try both `python3` and `python` — for each, run `<cmd> -c "import sys; print(sys.version_info[:2])"` and pick the first one that is Python 3.x
   - On conda/miniforge systems, `python` is often the correct command (not `python3`)
   - If neither works: tell the user "Python 3.10+ not found. Please install Python 3.10 and ensure it's on your PATH." and STOP.
   - Check the version is 3.10+. If not, warn: "Python 3.10+ is recommended. Install from https://www.python.org/downloads/" but allow the user to continue.
   - Store the working command as PYTHON_CMD for later use.
5. Detect the temp directory:
   - Run: `<PYTHON_CMD> -c "import tempfile; print(tempfile.gettempdir())"`
   - Store the output as TEMP_DIR.
6. Collect system metadata for registration:
   - Run: `hostname` — store as HOSTNAME.
   - Run: `uname -s` — store as OS_NAME.

### Step 2 — Download Scanner Script

1. Run: `curl -s <archon_api_url>/api/scanner/script -o <TEMP_DIR>/archon-scanner.py`
2. If the download fails (curl error or empty file), tell the user: "Can't reach Archon at <url>. Is the Archon stack running?" and STOP.

### Error Recovery — MCP Connection Issues

If at any point MCP tool calls fail with "session" errors, "connection refused", or
timeout errors:

1. Tell the user: "The Archon MCP connection was lost (server may have restarted).
   Please restart Claude Code to re-establish the MCP session, then re-run /scan-projects."
2. STOP. Do not attempt to fall back to REST API calls — the MCP tools have different
   behavior (deterministic IDs, project linking) that REST endpoints may not replicate.
3. If the scan was partially completed (some projects already created), re-running
   /scan-projects is safe — Step 4 deduplication will detect already-created projects.

### Step 3 — Run Scan

1. Ask the user: "What directory should I scan? (default: ~/projects)"
2. Run: `<PYTHON_CMD> <TEMP_DIR>/archon-scanner.py --scan <directory>`
3. Parse the JSON output. If the output contains an `error` key, display the error and STOP.
4. Store the full scan result for use in later steps.

### Step 4 — Deduplicate Against Existing Archon Projects

1. Call the `find_projects` MCP tool to get all existing Archon projects.
2. For each project in the scan results, compare its `github_url` (normalized, lowercase)
   against the `github_repo` field of existing Archon projects.
3. **Fallback matching:** If no `github_url` match is found, also compare by case-insensitive
   `directory_name` against existing project `title` fields. This catches projects that were
   created without a `github_repo` value (e.g., projects created manually via the UI).
4. Mark matches by setting `already_in_archon: true` and storing the `existing_project_id`.
   **CRITICAL**: Always preserve the LOCAL scan result's `absolute_path` for matched projects.
   The path stored in Archon may be from a different machine (e.g., a WSL path). The local
   `absolute_path` from the scan is the path on THIS machine and must be used in Steps 7 and 9.
5. **Intra-scan dedup:** Check for multiple scan results sharing the same non-null `github_url`.
   If found:
   - Keep the first occurrence as the primary.
   - Mark subsequent occurrences with `duplicate_of: "<directory_name of primary>"`.
   - Present these to the user in Step 5 for a decision (create both, skip one, or merge).
6. Count: how many are new, how many already exist, how many are intra-scan duplicates.

### Step 5 — Present Results to User

Display a summary like:
```
Scan complete!
- Total repositories found: <N>
- New (not in Archon): <N>
- Already in Archon: <N> (<names>)
- Project groups: <N>
```

For each NEW project:
- If it has a `readme_excerpt`, generate a 1-2 sentence description from it.
- If no README, note the detected languages and infra markers.

Present the list:
```
New projects to set up:
1. <name> — <description>
2. <name> — [no README, detected: python, docker]
...

Already in Archon (will link to this system): <names>
```

If intra-scan duplicates were found, show:
```
Duplicate GitHub URLs detected:
- <name1> and <name2> both point to <github_url>
  → Create both as separate projects? [y/N] Or skip <name2>?
```

Wait for user input on each duplicate pair before proceeding.

```
Proceed with setting up these <N> projects? You can exclude any by number.
```

Wait for user confirmation. If they exclude projects, remove them from the list. If they cancel, STOP.

**Note**: "Already in Archon" projects are NOT skipped — they still go through Steps 7 and 9
to register this system and write config files. The user confirmation above only applies to
creating NEW projects in Step 6. Existing projects always proceed through system registration
and config writes.

### Step 6 — Create Projects in Archon

For each confirmed new project:
1. If the project belongs to a group and the group parent hasn't been created yet:
   - Call `manage_project` MCP tool with `action: "create"`, `title: "<group_name>"`, `tags: ["project-group"]`, `description: "Project group containing <child names>"`.
   - Store the returned `project_id` as the group parent ID.
2. Call `manage_project` MCP tool with:
   - `action: "create"`
   - `title`: directory_name
   - `description`: the AI-generated description
   - `github_repo`: the normalized `github_url` (or null if no GitHub remote)
   - `tags`: combine `detected_languages` + `infra_markers`
   - `metadata`: `{"dependencies": <deps>, "scanned_from": "<absolute_path>", "scanner_version": "1.0"}`
   - `parent_project_id`: group parent ID if applicable
3. Store the returned `project_id` for each project.

The `manage_project` tool returns `{"success": true, "project": {...}, "project_id": "...", "message": "..."}` synchronously.

### Step 7 — Register System and Extensions for Each Project

This step must run for **every project** — both newly created AND already-existing projects
that the user did not exclude. The goal is to link this machine to all local projects so
Archon knows which systems have which projects and which extensions are installed.

For each project, call the `manage_extensions` MCP tool with:
- `action: "bootstrap"`
- `project_id`: the project's ID (created in Step 6, or `existing_project_id` from Step 4)
- `system_fingerprint`: from Step 1
- `system_name`: from Step 1
- `hostname`: HOSTNAME from Step 1
- `os`: OS_NAME from Step 1

The bootstrap action registers the system in the database, links it to the project,
and records all Archon extensions as installed for this system+project combination.

Store the returned `system.id` from each response — you will need it in Step 9.
All calls should return the same `system.id` (one system, many projects).

If a bootstrap call fails, warn the user but continue with the remaining projects.

### Step 8 — Download Extensions Tarball

Run: `curl -s <archon_mcp_url>/archon-setup/extensions.tar.gz -o <TEMP_DIR>/archon-extensions.tar.gz`

If the download fails, warn the user: "Extensions tarball download failed. Projects will be created without extensions." Continue to Step 9.

### Step 9 — Apply Config Files

1. Build a JSON payload with **all projects** (newly created AND existing).

   **CRITICAL**: For `absolute_path`, ALWAYS use the path from the Step 3 scan results — this
   is the local path on THIS machine. NEVER use a path stored in an existing Archon project,
   as that path may be from a different system (e.g., a WSL path like `/home/user/projects/Foo`
   vs a macOS path like `/Users/user/Projects/Foo`). Every project that was discovered locally
   in Step 3 MUST appear in this payload — do NOT skip config writes for projects that already
   exist in Archon. The entire purpose of this step is to configure THIS machine for ALL
   locally-found projects.

```json
{
  "projects": [
    {
      "absolute_path": "<absolute_path FROM STEP 3 SCAN RESULTS — the local path on this machine>",
      "project_id": "<id from Step 6 or existing_project_id from Step 4>",
      "project_title": "<directory_name>",
      "archon_api_url": "<from Step 1>",
      "archon_mcp_url": "<from Step 1>",
      "system_fingerprint": "<from Step 1>",
      "system_name": "<from Step 1>",
      "system_id": "<from Step 7 bootstrap response>"
    }
  ]
}
```
2. Write the payload to `<TEMP_DIR>/archon-apply-payload.json` using the Write tool.
3. Run: `<PYTHON_CMD> <TEMP_DIR>/archon-scanner.py --apply --payload-file <TEMP_DIR>/archon-apply-payload.json --extensions-tarball <TEMP_DIR>/archon-extensions.tar.gz`
4. Parse the JSON output for success/failure counts.

The scanner writes to each project: `archon-config.json`, `archon-state.json` (with system_id),
`settings.local.json` (hooks), `.mcp.json` (MCP server config), `.gitignore` updates,
and extensions.

### Step 10 — Knowledge Base Ingestion

For each created project that has `readme_excerpt` (non-null) in the scan results:
- Call `manage_rag_source` MCP tool with:
  - `action: "add"`
  - `source_type: "inline"`
  - `title: "<directory_name> README"`
  - `documents: [{"title": "README.md", "content": "<readme_excerpt>"}]`
  - `project_id: "<project_id>"`
  - `knowledge_type: "technical"`

This uses the locally-read README content from the scan (already captured in Step 3).
No external crawling is needed — the content is already available from the local filesystem.

Inline ingestion is deterministic: calling it again with the same `project_id` and `title`
will update the existing source, not create a duplicate.

For large scans (20+ projects), batch these calls in groups of 5 with a brief pause between
batches.

### Step 11 — Display Final Summary

```
Setup complete!
- Projects created: <N>
- Existing projects updated: <N>
- System registered: <system_name> (linked to <total> projects)
- Extensions installed: <N> per project
- Config files written: <N> projects
- README sources ingested: <N>
- Projects failed: <N>

<If any failures, list them with error messages>

You can now open Claude Code in any of these projects — Archon MCP,
extensions, and context will be available automatically.
```
