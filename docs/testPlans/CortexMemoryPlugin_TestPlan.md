# Cortex Memory Plugin — End-to-End Test Plan

## Prerequisites

- Cortex stack running and accessible in a browser (default: `http://localhost:3737`)
- Claude Code CLI installed
- Python 3 available on PATH
- A clean test project directory (e.g. `~/test-project/`)

---

## Phase 1: Download and Run the Setup Script

### 1.1 Navigate to the MCP page

1. Open the Cortex web UI in your browser
2. Click **MCP** in the left navigation
3. Scroll to the **Connect a New Machine** card

**Expected:** The card shows two download buttons — `cortexSetup.sh` (Mac / Linux) and `cortexSetup.bat` (Windows).

### 1.2 Download the setup script

- **Mac / Linux:** Click **cortexSetup.sh** — the browser downloads `cortexSetup.sh`
- **Windows:** Click **cortexSetup.bat** — the browser downloads `cortexSetup.bat`

**Expected:** The file downloads to your Downloads folder (or browser-configured download location).

### 1.3 Run the setup script

Open a terminal, navigate to your test project directory, and run the downloaded script:

**Mac / Linux:**
```bash
cd ~/test-project
bash ~/Downloads/cortexSetup.sh
```

**Windows:**
```cmd
cd %USERPROFILE%\test-project
%USERPROFILE%\Downloads\cortexSetup.bat
```

**Expected at each prompt:**
| Step | Expected |
|------|----------|
| System name | Detects hostname; press Enter to accept |
| Project | Finds or creates a project in Cortex |
| MCP | Reports "Added cortex MCP server" |
| Install scope | Prompts `[1]` project-local / `[2]` global — choose 1 |
| Plugin install | Reports "Plugin installed to .claude/plugins/cortex-memory/" |
| Config | Reports "Wrote .claude/cortex-config.json" |
| Done | Shows "sync extensions and project context" message |

### 1.4 Verify files were created

In the terminal:
```bash
ls .claude/
```
**Expected:** `cortex-config.json`, `cortex-state.json`, `plugins/` all present.

```bash
ls .claude/plugins/cortex-memory/
```
**Expected:** `src/`, `scripts/`, `hooks/`, `skills/`, `.claude-plugin/`, `.mcp.json`, `requirements.txt` all present.

### 1.5 Verify cortex-config.json content

Open `.claude/cortex-config.json` in any text editor.

**Expected:** Valid JSON with all of these fields populated (non-empty):
- `cortex_api_url`
- `cortex_mcp_url`
- `project_id`
- `machine_id`
- `install_scope` = `"1"`

### 1.6 Verify .gitignore was updated

Open `.gitignore` in any text editor.

**Expected:** These lines are present:
- `.claude/plugins/`
- `.claude/cortex-config.json`
- `.claude/cortex-memory-buffer.jsonl`

---

## Phase 2: Plugin Distribution — Browser Verification

### 2.1 Verify plugin manifest

Open this URL in the browser:
```
http://localhost:8051/cortex-setup/plugin-manifest
```

**Expected:** Browser displays JSON:
```json
{
  "name": "cortex-memory",
  "version": "1.0.0",
  "description": "Smart code exploration, session memory, and Cortex integration for Claude Code",
  "author": "Cortex"
}
```

### 2.2 Verify plugin download

Open this URL in the browser:
```
http://localhost:8051/cortex-setup/plugin/cortex-memory.tar.gz
```

**Expected:** Browser triggers a file download of `cortex-memory.tar.gz` (non-zero file size, typically 20–100 KB).

---

## Phase 3: Extension Registry (Cortex UI)

### 3.1 Verify plugin appears as an extension

1. Open Cortex web UI → navigate to your test project
2. Click the **Extensions** tab

**Expected:**
- `cortex-memory` appears in the extensions list
- Its type is shown as `plugin` (not `skill`)
- Version shows `1.0.0`
- Description matches: "Smart code exploration, session memory, and Cortex integration for Claude Code"

### 3.2 Verify existing extensions still present

In the same Extensions tab:

**Expected (no duplicates, all present):**
- `cortex-extension-sync`
- `cortex-bootstrap`
- `cortex-memory` (plugin)

---

## Phase 4: Claude Code — SessionStart Context Injection

Open Claude Code in `~/test-project/` (the directory where you ran the setup script).

### 4.1 With Cortex configured

Start a new conversation or run `/clear`.

**Expected:** An `<cortex-context>` block appears at the start of the conversation containing one or more of:
- `## Recent Sessions`
- `## Active Tasks` (populated from the linked project)
- `## Knowledge Sources`

### 4.2 Without Cortex configured (negative test)

Open Claude Code in a **different** directory that has no `.claude/cortex-config.json` (e.g. `~/test-unconfigured/`).

**Expected:** An `<cortex-setup-needed>` message appears in context explaining how to run setup — no errors or crashes.

---

## Phase 5: Smart Explore MCP Tools

In Claude Code, within `~/test-project/`, verify the `cortex-memory` MCP server is connected (it should appear in the MCP tool list).

Ask Claude to use each tool in turn:

### 5.1 smart_search

> "Use smart_search to find the `flush_session` function in the Cortex plugin directory"

**Expected:** Returns a ranked list of results — `src/cortex_client.py` with the function signature and line number. Does NOT read entire files.

### 5.2 smart_outline

> "Use smart_outline on the file `integrations/claude-code/plugins/cortex-memory/src/mcp_server.py`"

**Expected:** Returns a folded structural view showing `smart_search`, `smart_outline`, `smart_unfold` with their signatures and line ranges. Does NOT show full file content.

### 5.3 smart_unfold

> "Now use smart_unfold to show me the full `_smart_search_impl` function from that file"

**Expected:** Returns only that function's complete source with a location header (e.g. `mcp_server.py:47–55`).

### 5.4 smart_unfold — unknown symbol (negative test)

> "Use smart_unfold on that file for a symbol called `nonexistent_function`"

**Expected:** Returns an error message listing the available symbols (`smart_search`, `smart_outline`, `smart_unfold`) — does not crash.

---

## Phase 6: Observation Hook (PostToolUse)

While in the Claude Code session in `~/test-project/`, trigger a few tool uses (e.g. ask Claude to read a file or search for something).

Then open `.claude/cortex-memory-buffer.jsonl` in a text editor.

**Expected:** One JSON object per line, each containing:
- `tool_name` — name of the tool used
- `timestamp` — ISO 8601 datetime
- `session_id` — a non-empty string

Trigger more tool uses and re-open the file — new lines should have been appended.

---

## Phase 7: Session End Hook (Stop)

End the Claude Code session (close the window or type `/stop`). Then check the buffer file.

**Expected:** `.claude/cortex-memory-buffer.jsonl` is either empty or no longer exists — the session was flushed on exit.

### 7.1 Verify session stored in Cortex UI

1. Open Cortex web UI → your test project
2. Navigate to a **Sessions** tab or ask Claude (in a new session) to search for the session

**Expected:** A session entry exists with:
- `started_at` timestamp from the session you just ended
- `observations` matching the tool uses you triggered
- Linked to the correct project

---

## Phase 8: Session History Search

In a new Claude Code session in `~/test-project/`, ask:

### 8.1 Search sessions

> "Search Cortex session history for recent work in this project"

**Expected:** Returns the session from Phase 7 with its summary and observations.

### 8.2 Get session details

> "Get the full details of that session"

**Expected:** Full session object with all observations listed in order.

---

## Phase 9: claude-mem Conflict Detection (if applicable)

If `claude-mem` is already installed, re-download `cortexSetup.sh` from the MCP page (Phase 1.1–1.2) and run it again in a test directory.

**Expected at the plugin step:**
- Script detects the existing `claude-mem` installation
- Presents three options: remove and replace, keep both, or skip
- Choosing `[1]` removes claude-mem and installs cortex-memory
- Choosing `[3]` skips plugin installation entirely

After choosing `[1]`, verify in the file system that `~/.claude/plugins/cache/thedotmack/claude-mem/` no longer exists.

---

## Phase 10: Regression — Automated Tests

Run in a terminal to confirm nothing regressed:

```bash
cd /home/winadmin/projects/Trinity/cortex/python
uv run pytest tests/ -q
# Expected: 948+ passed, 0 failed
```

```bash
cd /home/winadmin/projects/Trinity/cortex/integrations/claude-code/plugins/cortex-memory
python -m pytest tests/ -q
# Expected: 98 passed, 0 failed
```

---

## Pass Criteria Summary

| # | Test | Pass |
|---|------|------|
| 1.1 | MCP page shows "Connect a New Machine" card with download buttons | ☐ |
| 1.2 | Clicking download button delivers the script file | ☐ |
| 1.3 | Setup script runs to completion without errors | ☐ |
| 1.4 | Plugin files installed to `.claude/plugins/cortex-memory/` | ☐ |
| 1.5 | `cortex-config.json` written with all required fields | ☐ |
| 1.6 | `.gitignore` updated with cortex entries | ☐ |
| 2.1 | Plugin manifest URL shows correct JSON in browser | ☐ |
| 2.2 | Plugin tarball URL triggers a file download | ☐ |
| 3.1 | `cortex-memory` visible in Extensions tab as type=plugin | ☐ |
| 3.2 | Existing extensions still present, no duplicates | ☐ |
| 4.1 | `<cortex-context>` injected at SessionStart | ☐ |
| 4.2 | `<cortex-setup-needed>` shown in unconfigured directory | ☐ |
| 5.1 | `smart_search` returns ranked symbol results | ☐ |
| 5.2 | `smart_outline` returns folded file structure | ☐ |
| 5.3 | `smart_unfold` returns a single symbol's full source | ☐ |
| 5.4 | `smart_unfold` with unknown symbol lists available names | ☐ |
| 6.1 | Buffer file accumulates observations during session | ☐ |
| 7.1 | Buffer cleared after session ends | ☐ |
| 7.2 | Session visible in Cortex after Stop | ☐ |
| 8.1 | `cortex_search_sessions` finds previous session | ☐ |
| 8.2 | `cortex_get_session` returns full session detail | ☐ |
| 9.1 | claude-mem detection and removal flow works | ☐ |
| 10.1 | Backend test suite passes | ☐ |
| 10.2 | Plugin test suite passes | ☐ |
