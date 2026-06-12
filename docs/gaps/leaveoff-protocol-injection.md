# Gap: LeaveOff Point Protocol Not Active in User Projects

**Discovered**: journeyTest01 Day 1, test 1.10
**Severity**: High -- breaks session continuity across all user projects

---

## 1. Gap Description

### What is broken

Claude Code in user projects (e.g., RecipeRaiders, reciperaiders-spa) does not automatically call `manage_leaveoff_point(action="update")` after completing coding tasks. The LeaveOff Point is never written, so the next session starts with no context about what was accomplished or what to do next.

### Why it is broken

The LeaveOff Point Protocol instructions exist only in Cortex's own `CLAUDE.md` (at `/home/winadmin/projects/Trinity/cortex/CLAUDE.md`, section "## LeaveOff Point Protocol"). That file is only loaded when Claude Code is working inside the Cortex repository itself. User projects have their own `CLAUDE.md` (or none at all) and never see these instructions.

### What already works

The full infrastructure is in place -- only the "tell Claude to use it" piece is missing:

| Component | Location | Status |
|-----------|----------|--------|
| MCP tool | `python/src/mcp_server/features/leaveoff/leaveoff_tools.py` | Working |
| Backend API | `python/src/server/api_routes/leaveoff_api.py` | Working |
| Backend service | `python/src/server/services/leaveoff/leaveoff_service.py` | Working |
| Session start hook (reads LeaveOff) | `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py` | Working -- displays existing LeaveOff Points in `<cortex-context>` |
| Session end hook | `integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py` | Working -- flushes session buffer |
| Cortex CLAUDE.md protocol | `CLAUDE.md` section "## LeaveOff Point Protocol" | Working **only for Cortex repo** |

### The missing link

No mechanism tells Claude in user projects to call `manage_leaveoff_point` after coding tasks. The session start hook displays existing LeaveOff Points, but never injects the behavioral protocol (the "you MUST call this tool after every coding task" instructions).

---

## 2. Impact

### Failing tests

| Test | Description |
|------|-------------|
| 1.10 | LeaveOff Point written after coding task |
| 1.11 | LeaveOff Point contains accurate content, next_steps, references |
| 1.12 | LeaveOff Point restored on session start |
| 3.3  | LeaveOff Point updated after multi-file changes |
| 3.4  | LeaveOff Point persists across sessions |
| 3.12 | 90% rule triggers LeaveOff Point write |
| 3.13 | LeaveOff Point next_steps are actionable and specific |
| 5.4  | Cross-session continuity via LeaveOff Point |
| 5.5  | LeaveOff Point drives task prioritization in new session |

### User impact

Without this fix, every session in every user project starts from scratch. Claude has no memory of what was done last time, what files were changed, or what to do next. This defeats a core value proposition of the Cortex memory system.

---

## 3. Option A: Extension SKILL.md

Create a new extension `cortex-leaveoff-protocol` that gets installed to `<install_dir>/skills/cortex-leaveoff-protocol/SKILL.md`.

### How it would work

The SKILL.md file would contain the LeaveOff Point Protocol instructions styled as a "background behavior" extension -- not an action skill invoked by `/command`, but a set of instructions Claude Code loads and follows automatically.

Claude Code loads all `SKILL.md` files from `~/.claude/skills/` (or `.claude/skills/` for project-scoped installs) and includes their content in the system context. This means the protocol instructions would be visible to Claude every session.

### File structure

```
integrations/claude-code/extensions/cortex-leaveoff-protocol/SKILL.md
```

Content would be the LeaveOff Point Protocol section from Cortex's CLAUDE.md, adapted to reference the `manage_leaveoff_point` MCP tool with proper parameter documentation.

### Pros

- Follows the existing extension distribution pattern (tarball via `cortex-bootstrap`, sync via `cortex-extension-sync`)
- User can see it in `~/.claude/skills/cortex-leaveoff-protocol/SKILL.md` -- transparent
- User can customize, override, or delete it per-project
- No code changes needed -- only a new SKILL.md file plus adding it to the extensions tarball
- Works immediately after bootstrap without requiring any hook changes
- Claude Code loads SKILL.md content into every conversation as available context

### Cons

- SKILL.md files are typically "on-demand" skills invoked via `/command` syntax. Using one for "always-on background instructions" is an unconventional usage of the extension pattern. However, Claude Code does load all SKILL.md content as available context, so the instructions will be visible.
- The `description` field in YAML frontmatter determines when Claude considers the skill relevant. A carefully written description can make Claude treat it as always-relevant context rather than an on-demand action.
- Adds another extension to the registry (minor -- already have 5 extensions)

### Key design question

Claude Code's SKILL.md loading behavior: SKILL.md files are loaded as "available skills" shown in system reminders. Claude sees them and can follow their instructions even without explicit invocation, but the degree to which Claude proactively follows "you MUST do X" instructions in a SKILL.md (vs. waiting for the user to invoke the skill) depends on how the description and content are worded. This is the central risk of Option A.

---

## 4. Option B: SessionStart Hook Injection

Modify `session_start_hook.py` to inject the LeaveOff Point Protocol instructions into the `<cortex-context>` block alongside the existing LeaveOff Point data.

### How it would work

The `_format_context()` function in `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py` already outputs an `<cortex-context>` block. This block is printed to stdout and Claude Code injects it into the system prompt. The modification would add a new section containing the behavioral protocol instructions.

### What changes

In `session_start_hook.py`, the `_format_context()` function would be extended to append a `## LeaveOff Point Protocol` section to the `<cortex-context>` block. This section would contain the same instructions currently in Cortex's CLAUDE.md.

### Pros

- Always active -- Claude sees the protocol every session without needing to invoke anything
- Guaranteed to be in the system prompt context (not an "available skill" that may or may not be consulted)
- Already proven pattern -- the hook already injects LeaveOff Point data and Claude reads it
- Single code change in one file
- No new extension to manage
- Strongest behavioral guarantee: system-prompt-level instructions are the highest priority context for Claude

### Cons

- Adds ~300-500 tokens to every session start (the protocol instructions are relatively short)
- Cannot be easily disabled per-project without modifying the hook or adding a config flag
- Mixes behavioral instructions ("you MUST do X") with data context ("here is your last LeaveOff Point") in the same `<cortex-context>` block
- Requires a code change + rebuild of the plugin, vs. Option A which is just adding a file

### Token cost estimate

The LeaveOff Point Protocol section from Cortex's CLAUDE.md is approximately 350 tokens. At typical session lengths of 50,000-200,000 tokens, this is a negligible overhead (0.2-0.7%).

---

## 5. Recommendation

**Implement Option B (SessionStart hook injection).**

### Rationale

1. **Behavioral reliability is the deciding factor.** The purpose of the LeaveOff Point Protocol is to make Claude proactively call `manage_leaveoff_point` after every coding task -- a background behavior, not a user-invoked action. System-prompt-level injection (Option B) provides the strongest behavioral guarantee. SKILL.md files are designed for on-demand skills and while Claude can see their content, there is meaningful risk that Claude treats it as "available if needed" rather than "always follow."

2. **Token cost is negligible.** 350 tokens per session is trivially small compared to the 200K+ context window.

3. **The infrastructure already exists.** The session_start_hook already injects context. Adding one more section is a minimal, low-risk change.

4. **Consistency with existing pattern.** The hook already injects LeaveOff Point *data* (the "## LeaveOff Point (Last Session State)" section). Adding the LeaveOff Point *protocol* (the "you must update this after coding tasks" instructions) to the same block creates a natural pairing: "here is your last state" + "here is how to update it."

5. **Simplicity.** One file change, no new extensions to manage, no questions about whether Claude will follow the instructions.

### Risk mitigation

- Add a config flag (`leaveoff_protocol_enabled` in `cortex-config.json`, default `true`) so users can disable the injection if needed
- Keep the protocol section concise (the current CLAUDE.md version can be tightened for user-project context)

### Why not Option A

Option A is viable and could work. If testing shows that Claude reliably follows SKILL.md "background behavior" instructions, it would be the cleaner architectural choice (data in hooks, behavior in extensions). But the risk of Claude not proactively following the protocol is too high for a feature this important. Option B eliminates that risk entirely.

### Hybrid consideration (Option C)

A hybrid approach -- inject via hook AND create a SKILL.md -- would provide belt-and-suspenders coverage but adds unnecessary complexity. The hook injection alone is sufficient. If a SKILL.md is added later for user-facing documentation or customization, it would complement rather than replace the hook injection.

---

## 6. Implementation Prompt

The following prompt can be given directly to Claude Code to implement the fix.

---

### Prompt

Modify the session start hook to inject the LeaveOff Point Protocol into every session. This ensures Claude in user projects automatically calls `manage_leaveoff_point(action="update")` after completing coding tasks.

#### What to change

**File**: `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`

**In the `_format_context()` function**, after the existing `<cortex-context>` content is built but before the closing `</cortex-context>` tag, inject a new section containing the LeaveOff Point Protocol.

The protocol section should be added conditionally: only when the client is configured (i.e., `cortex-config.json` has `project_id` and `cortex_api_url`). If the client is not configured, skip the protocol injection (the `_setup_message()` path already handles unconfigured state).

#### Protocol content to inject

Add the following as a new section in the `<cortex-context>` block. Place it AFTER the LeaveOff Point data section (if present) and BEFORE the closing tag:

```markdown
## LeaveOff Point Protocol

### After Every Coding Task
After completing any coding task that adds, modifies, or removes functionality, you MUST
update the LeaveOff Point before moving to the next task:

1. Call `manage_leaveoff_point(action="update")` with:
   - `project_id`: Use the project ID from the cortex-context above
   - `content`: What was accomplished in this task (be specific about files changed and why)
   - `component`: The architectural module or feature area being worked on
   - `next_steps`: Concrete, actionable items for the next session (include file paths, not vague descriptions)
   - `references`: Key files that were changed or informed this work

2. This is NOT optional. Skipping this step means the next session starts with no context.

### Session Resource Management (The 90% Rule)
When you observe any of these signals, you are approaching resource limits:
- The conversation has exceeded 80+ tool uses
- You receive a system reminder about observation count
- You sense the conversation has been running extensively

Upon detecting these signals:
1. Stop active coding immediately
2. Generate a final LeaveOff Point via `manage_leaveoff_point(action="update")` with
   comprehensive next_steps covering all remaining planned work
3. Advise the user: "This session has reached its resource limit. The LeaveOff Point
   has been saved. Please start a new session to continue."
4. Do not continue coding after generating the final LeaveOff Point
```

#### Implementation details

1. **Add a helper function** `_leaveoff_protocol_section()` that returns the protocol text as a string. This keeps the `_format_context()` function clean.

2. **Modify `_format_context()`** to accept a `project_id` parameter (or extract it from the leaveoff data). Append the protocol section by calling `_leaveoff_protocol_section()` just before the closing `</cortex-context>` tag.

3. **Make it conditional** on the client being configured. The `main()` function already checks `client.is_configured()` before calling `_format_context()`, so if we reach `_format_context()` the client is necessarily configured. However, include the `project_id` in the protocol text so Claude knows which project to pass to the MCP tool.

4. **Pass `project_id` to `_format_context()`**. Update the `main()` function to pass `client.project_id` to `_format_context()`. The protocol section should reference this project_id so Claude has the exact value to use in `manage_leaveoff_point` calls.

5. **Update the function signature** of `_format_context()`:
   ```python
   def _format_context(sessions, tasks, knowledge, leaveoff=None, project_id=None):
   ```

6. **In `main()`**, update the call:
   ```python
   print(_format_context(sessions, tasks, knowledge, leaveoff, project_id=client.project_id))
   ```

#### Config flag (optional but recommended)

Add support for a `leaveoff_protocol_enabled` key in `cortex-config.json` (default: `true`). If set to `false`, skip injecting the protocol section. This gives users an escape hatch.

In `_format_context()`:
```python
# Only inject if not explicitly disabled
# (config would need to be passed in or read separately)
```

For the initial implementation, skip the config flag -- just always inject the protocol. The flag can be added later if users request it.

#### Testing

1. **Unit test**: Add a test in `integrations/claude-code/plugins/cortex-memory/tests/` that verifies `_format_context()` includes the protocol section when `project_id` is provided.

2. **Integration test**: Run the session start hook manually and verify the output includes both the LeaveOff Point data (if any) and the protocol instructions:
   ```bash
   cd /path/to/user-project
   python integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py
   ```

3. **End-to-end test**: Start a new Claude Code session in a user project, complete a coding task, and verify Claude calls `manage_leaveoff_point` without being asked.

#### Files to modify

- `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py` -- main change
- `integrations/claude-code/plugins/cortex-memory/tests/test_session_start_hook.py` -- add test (create if not exists)

#### Files for reference (do not modify)

- `python/src/mcp_server/features/leaveoff/leaveoff_tools.py` -- MCP tool signature and parameters
- `CLAUDE.md` section "## LeaveOff Point Protocol" -- original protocol text (adapt for user projects)
- `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py` -- client.project_id source

---

## Appendix: Relevant File Paths

| File | Purpose |
|------|---------|
| `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py` | Hook that injects context on session start (PRIMARY CHANGE TARGET) |
| `integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py` | Hook that flushes session buffer on end |
| `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py` | HTTP client with project_id, get_leaveoff_point() |
| `python/src/mcp_server/features/leaveoff/leaveoff_tools.py` | MCP tool: manage_leaveoff_point |
| `python/src/server/api_routes/leaveoff_api.py` | REST API for LeaveOff Points |
| `python/src/server/services/leaveoff/leaveoff_service.py` | Backend service layer |
| `CLAUDE.md` | Cortex-repo-only protocol (source of protocol text) |
| `integrations/claude-code/extensions/cortex-bootstrap/SKILL.md` | Bootstrap extension (installs other extensions) |
