# LeaveOff Point — User Test Plan

## Overview

This test plan validates the LeaveOff Point feature end-to-end from a user's perspective. The feature ensures context continuity across Claude Code sessions by automatically saving development state after coding tasks and restoring it when a new session begins.

No direct API calls are used in this plan. All interactions are through Claude Code, the Cortex UI, or filesystem inspection.

## Prerequisites

- Cortex stack running and accessible (default: `http://localhost:3737`)
- At least one project configured in Cortex (or create a new one during testing)
- Claude Code CLI installed and connected to Cortex MCP server
- The `cortex-memory` plugin installed (run `/cortex-setup` if not)
- Access to the test project's filesystem to inspect generated files
- Migration `019_add_leaveoff_points.sql` applied to your database

---

## Phase 1: Database Verification

Verify the LeaveOff Points table exists in your Supabase instance.

### 1.1 Check table exists

1. Open your Supabase dashboard SQL editor (or connect via `psql`)
2. Run:
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'cortex_leaveoff_points'
ORDER BY ordinal_position;
```

**Expected:** The table exists with columns: `id` (uuid), `project_id` (uuid), `machine_id` (text), `last_session_id` (uuid), `content` (text), `component` (text), `next_steps` (ARRAY), `references` (ARRAY), `metadata` (jsonb), `updated_at` (timestamptz), `created_at` (timestamptz).

### 1.2 Check constraints

Run:
```sql
SELECT constraint_name, constraint_type FROM information_schema.table_constraints
WHERE table_name = 'cortex_leaveoff_points';
```

**Expected:** You should see:
- A `PRIMARY KEY` constraint on `id`
- A `UNIQUE` constraint on `project_id`
- A `FOREIGN KEY` constraint referencing `cortex_projects(id)`

> **If the table doesn't exist:** Run the migration at `migration/0.1.0/019_add_leaveoff_points.sql` in your Supabase SQL editor.

---

## Phase 2: MCP Tool Registration

Verify the `manage_leaveoff_point` tool is available to Claude Code.

### 2.1 Check MCP server health

1. In your browser, navigate to `http://localhost:8051/health`

**Expected:** Returns a healthy status response.

### 2.2 Verify tool is registered

1. Check the MCP server logs:
   ```bash
   docker compose logs cortex-mcp | grep -i "leaveoff"
   ```

**Expected:** You should see:
```
✓ LeaveOff Point module registered (HTTP-based)
```

### 2.3 Verify tool is visible in Claude Code

1. Open Claude Code in a project connected to Cortex
2. Ask: "What Cortex MCP tools do you have access to?"

**Expected:** Claude should list `manage_leaveoff_point` among the available tools, or you should see it in the MCP tools list.

---

## Phase 3: Creating a LeaveOff Point

### 3.1 Ask Claude to save a LeaveOff Point

1. Open Claude Code in a project that is registered with Cortex
2. Do some small coding task (e.g., add a comment to a file, create a small utility function)
3. After the task is complete, tell Claude:

   > "Save a LeaveOff Point for this session. We just added a utility function to the project."

4. Observe Claude's tool call

**Expected:** Claude calls `manage_leaveoff_point` with:
- `action: "update"`
- `project_id`: your project's Cortex ID
- `content`: a description of what was accomplished
- `next_steps`: a list of actionable next steps
- `component`: the area of the codebase that was worked on

The tool should return a JSON response with the saved record including an `id`, `project_id`, `updated_at`, and all the fields that were passed in.

### 3.2 Verify the database record

1. In Supabase SQL editor, run:
```sql
SELECT id, project_id, component, next_steps, updated_at
FROM cortex_leaveoff_points;
```

**Expected:** Exactly one row for your project with the content Claude provided.

### 3.3 Verify the file was created (if project_path was provided)

1. Navigate to your project directory
2. Check for the file:
   ```bash
   cat .cortex/knowledge/LeaveOffPoint.md
   ```

**Expected:** A markdown file with:
- YAML frontmatter containing `project_id`, `component`, `updated_at`, `machine_id`
- A content section describing what was accomplished
- A `## Next Steps` section with bullet points
- A `## References` section (if references were provided)

> **Note:** The file is only written if `project_path` was included in the MCP tool call. If the file doesn't exist, the database record is still the source of truth.

---

## Phase 4: Updating (Upsert) a LeaveOff Point

### 4.1 Perform another coding task

1. In the same or a new Claude Code session, do another small task in the same project
2. Tell Claude:

   > "Update the LeaveOff Point. We just refactored the error handling in the API layer."

**Expected:** Claude calls `manage_leaveoff_point(action="update")` with new content and next steps.

### 4.2 Verify it replaced (not duplicated)

1. In Supabase SQL editor, run:
```sql
SELECT COUNT(*) FROM cortex_leaveoff_points
WHERE project_id = '<your-project-id>';
```

**Expected:** Count is exactly `1`. The previous LeaveOff Point was replaced, not a second one created.

### 4.3 Verify content was updated

1. Run:
```sql
SELECT content, next_steps, updated_at FROM cortex_leaveoff_points
WHERE project_id = '<your-project-id>';
```

**Expected:** The `content` reflects the refactoring task, the `next_steps` are new, and the `updated_at` timestamp is more recent than before.

---

## Phase 5: Retrieving a LeaveOff Point

### 5.1 Ask Claude to check the current state

1. In Claude Code, ask:

   > "What's the current LeaveOff Point for this project?"

**Expected:** Claude calls `manage_leaveoff_point(action="get")` and displays the current LeaveOff Point content, including what was last accomplished and the next steps.

### 5.2 Verify with a non-existent project

1. Ask Claude:

   > "Get the LeaveOff Point for a project that doesn't exist."

**Expected:** Claude receives a response indicating no LeaveOff Point was found (404 / "No LeaveOff point found for this project").

---

## Phase 6: SessionStart Hook — Automatic Context Loading

This is the most important user experience test. It validates that the LeaveOff Point is automatically injected at the start of every new session.

### 6.1 Ensure a LeaveOff Point exists

1. Make sure your project has a saved LeaveOff Point (from Phase 3 or 4)
2. Verify it exists in the database

### 6.2 Start a brand new Claude Code session

1. Close/exit your current Claude Code session entirely
2. Open a new Claude Code session in the same project directory
3. Wait for the session to initialize

**Expected:** During startup, you should see the Cortex context being loaded. The `<cortex-context>` block injected into the system prompt should now include a **"LeaveOff Point (Last Session State)"** section at the top, before recent sessions and active tasks.

### 6.3 Verify Claude acknowledges the context

1. In the new session, ask Claude:

   > "What context do you have about my recent work on this project?"

**Expected:** Claude should be able to describe:
- What was last worked on (from the LeaveOff Point content)
- The component/area of the codebase
- The next steps that were saved
- Any references that were included

### 6.4 Verify the LeaveOff Point appears first

1. Check the session startup output for the `<cortex-context>` block
2. The LeaveOff Point section should appear **before** Recent Sessions, Active Tasks, and Knowledge Sources

**Expected order:**
1. LeaveOff Point (Last Session State)
2. Recent Sessions
3. Active Tasks
4. Knowledge Sources

---

## Phase 7: The 90% Rule — Observation Counter

### 7.1 Verify the warning mechanism exists

1. Open the observation hook file and confirm the constants:
   ```bash
   grep -n "WARNING_THRESHOLD\|WARNING_REPEAT" integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py
   ```

**Expected:** You should see `_WARNING_THRESHOLD = 80` and `_WARNING_REPEAT_INTERVAL = 10`.

### 7.2 Simulate a high observation count

1. Create a test buffer file with 80 observations:
   ```bash
   python3 -c "
   from pathlib import Path
   buf = Path('.claude/cortex-memory-buffer.jsonl')
   buf.parent.mkdir(parents=True, exist_ok=True)
   with buf.open('w') as f:
       for i in range(80):
           f.write('{\"tool_name\": \"Edit\", \"summary\": \"test\"}\n')
   print(f'Created buffer with {sum(1 for _ in buf.open())} lines')
   "
   ```

2. Trigger the observation hook with a mock tool use:
   ```bash
   echo '{"tool_name": "Edit", "tool_input": {"file_path": "test.py"}, "session_id": "test-123"}' | python3 integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py
   ```

**Expected:** The hook should print a `<system-reminder>` block containing:
- "SESSION RESOURCE WARNING"
- The observation count (81)
- Instructions to generate a final LeaveOff Point
- Advice to start a new session

### 7.3 Clean up the test buffer

```bash
rm -f .claude/cortex-memory-buffer.jsonl
```

### 7.4 Verify CLAUDE.md protocol exists

1. Open `CLAUDE.md` and search for "LeaveOff Point Protocol"
   ```bash
   grep -A 5 "LeaveOff Point Protocol" CLAUDE.md
   ```

**Expected:** The section should exist with subsections for:
- "After Every Coding Task"
- "Session Resource Management (The 90% Rule)"
- "Session Start"

---

## Phase 8: Deleting a LeaveOff Point

### 8.1 Ask Claude to delete it

1. In Claude Code, say:

   > "Delete the LeaveOff Point for this project."

**Expected:** Claude calls `manage_leaveoff_point(action="delete")` and confirms the deletion.

### 8.2 Verify deletion

1. Check the database:
```sql
SELECT COUNT(*) FROM cortex_leaveoff_points
WHERE project_id = '<your-project-id>';
```

**Expected:** Count is `0`.

### 8.3 Verify next session has no LeaveOff context

1. Close and reopen Claude Code
2. Check the startup context

**Expected:** The `<cortex-context>` block should NOT contain a "LeaveOff Point" section (it should gracefully skip it).

---

## Phase 9: Multi-Project Isolation

### 9.1 Create LeaveOff Points for two different projects

1. Open Claude Code in **Project A** and save a LeaveOff Point
2. Open Claude Code in **Project B** and save a different LeaveOff Point

### 9.2 Verify isolation

1. Check the database:
```sql
SELECT project_id, component, content FROM cortex_leaveoff_points ORDER BY updated_at;
```

**Expected:** Two separate rows, one per project, with different content.

### 9.3 Verify correct context per project

1. Open a new Claude Code session in **Project A**
2. Verify the LeaveOff context matches Project A's saved state (not Project B's)
3. Repeat for **Project B**

**Expected:** Each project loads only its own LeaveOff Point at session start.

---

## Phase 10: End-to-End Workflow

This is the full "real world" test.

### 10.1 Session 1 — Do work and leave off

1. Start Claude Code in a project
2. Ask Claude to perform a meaningful coding task (e.g., "Add input validation to the user registration endpoint")
3. After Claude completes the task, verify it saves a LeaveOff Point (per CLAUDE.md protocol)
4. Note the next steps Claude saved
5. End the session

### 10.2 Session 2 — Resume from where you left off

1. Start a new Claude Code session in the same project
2. Ask Claude: "What should we work on next?"

**Expected:** Claude should reference the LeaveOff Point context that was loaded at session start. It should suggest continuing with the next steps from the previous session, demonstrating full context continuity.

### 10.3 Verify the cycle repeats

1. Complete one of the next steps from the LeaveOff Point
2. Verify Claude updates the LeaveOff Point with new next steps
3. The cycle should be self-sustaining across sessions

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `manage_leaveoff_point` tool not found | MCP server doesn't have the module | Check `docker compose logs cortex-mcp` for registration errors; rebuild if needed |
| LeaveOff Point not injected at session start | Plugin not configured or Cortex unreachable | Run `/cortex-setup` and verify `.claude/cortex-config.json` exists |
| 500 error on PUT | Database migration not applied | Run `019_add_leaveoff_points.sql` in Supabase SQL editor |
| Duplicate records | UNIQUE constraint missing | Verify migration was applied correctly (check constraints in Phase 1.2) |
| File not written to disk | `project_path` not provided in tool call | This is optional; the database record is the source of truth |
| Warning not firing at 80 observations | Buffer file path mismatch | Check that `.claude/cortex-memory-buffer.jsonl` exists and is writable |
| Context not loading at session start | Cortex server down or timeout | Check server health at `http://localhost:8181/api/projects` |

---

## Test Results Checklist

| Phase | Test | Pass/Fail | Notes |
|-------|------|-----------|-------|
| 1.1 | Table exists with correct columns | | |
| 1.2 | Constraints (PK, UNIQUE, FK) present | | |
| 2.1 | MCP health check passes | | |
| 2.2 | LeaveOff module registered in logs | | |
| 2.3 | Tool visible to Claude Code | | |
| 3.1 | Claude saves LeaveOff Point via MCP tool | | |
| 3.2 | Database record created correctly | | |
| 3.3 | LeaveOffPoint.md file created (if project_path provided) | | |
| 4.1 | Claude updates LeaveOff Point on second task | | |
| 4.2 | Exactly one record per project (no duplicates) | | |
| 4.3 | Content and timestamp updated | | |
| 5.1 | Claude retrieves current LeaveOff Point | | |
| 5.2 | Graceful handling of non-existent project | | |
| 6.1 | LeaveOff Point exists in DB before test | | |
| 6.2 | New session loads context automatically | | |
| 6.3 | Claude can describe recent work from context | | |
| 6.4 | LeaveOff Point appears first in context block | | |
| 7.1 | Warning constants present in hook | | |
| 7.2 | Warning fires at 80+ observations | | |
| 7.4 | CLAUDE.md protocol section exists | | |
| 8.1 | Claude deletes LeaveOff Point | | |
| 8.2 | Database record removed | | |
| 8.3 | Next session has no LeaveOff context | | |
| 9.1 | Two projects each have a LeaveOff Point | | |
| 9.2 | Database shows separate records | | |
| 9.3 | Each session loads correct project context | | |
| 10.1 | Session 1: work done, LeaveOff saved | | |
| 10.2 | Session 2: context restored, next steps referenced | | |
| 10.3 | Cycle repeats across sessions | | |
