---
name: mem-search
description: Search Cortex session memory for past decisions, bugs, and implementation context. Use when asked "did we already solve this?", "how did we do X last time?", or needing context from previous sessions. Requires Cortex MCP server to be connected.
---

# Memory Search

Search your session history stored in Cortex to retrieve past decisions, bug fixes, and implementation context across sessions.

## Tools

These tools are provided by the Cortex MCP server (not the cortex-memory plugin):

- `cortex_search_sessions` — Full-text search across all session observations
- `cortex_get_session` — Get a specific session with all its observations

## When to Use

Use this skill when you need to recall:
- Past decisions or rationale ("why did we choose X?")
- How a previous bug was fixed ("what broke the auth flow last week?")
- Prior implementation patterns ("how did we handle pagination before?")
- Work done in a previous session on this project

## Workflow

1. **Search for relevant sessions**
   ```
   cortex_search_sessions(query="authentication refactor", project_id="...", limit=5)
   ```

2. **Inspect a specific session for details**
   ```
   cortex_get_session(session_id="sess_abc123")
   ```

3. **Apply context** — use retrieved information to inform current work

## Tips

- Search with short, concrete terms ("fix login bug", "refactor session service")
- Use `project_id` filter when you only want this project's history
- Sessions are stored automatically — no manual saving needed
- If Cortex is unreachable, no sessions will be found (graceful failure)
