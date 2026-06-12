# LeaveOff Point Feature Design

## Overview

The LeaveOff Point feature ensures context continuity across Claude Code sessions for every Cortex-managed project. Each project maintains a single, current development state that is automatically updated after coding tasks and automatically loaded at session start.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Per-project, last-writer-wins | One canonical state per project. Any machine can overwrite. Aligns with materialization dedup pattern. |
| Storage | File + database | `.cortex/knowledge/LeaveOffPoint.md` for human readability; `cortex_leaveoff_points` table for RAG retrieval. |
| 90% guardrail | CLAUDE.md instruction + observation count safety net | Prompt-based self-monitoring with PostToolUse hook emitting warnings at threshold. |
| Session start consumption | Extend existing SessionStart hook | Fetched in parallel with existing context; injected into `<cortex-context>` block. |
| Architecture | Standalone service | Dedicated table, service, API, and MCP tool. Conceptually distinct from materializations. |

## Database Schema

Migration: `019_add_leaveoff_points.sql`

```sql
CREATE TABLE cortex_leaveoff_points (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id      UUID NOT NULL UNIQUE REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id      TEXT,
    last_session_id UUID,
    content         TEXT NOT NULL,
    component       TEXT,
    next_steps      TEXT[] NOT NULL DEFAULT '{}',
    references      TEXT[] NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_leaveoff_project ON cortex_leaveoff_points(project_id);
```

Key constraints:
- `project_id UNIQUE` enforces exactly one LeaveOff per project at the DB level.
- `ON DELETE CASCADE` cleans up when a project is deleted.
- `last_session_id` has no FK constraint (session lifecycle is independent).
- `metadata JSONB` provides an escape hatch for model-generated extras (perf stats, env vars).

## Service Layer

**File:** `python/src/server/services/leaveoff/leaveoff_service.py`

```python
class LeaveOffService:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    async def upsert(self, project_id, content, component, next_steps,
                     references, machine_id, last_session_id, metadata) -> dict:
        """Atomic UPSERT -- creates or replaces the LeaveOff point."""
        # 1. UPSERT into cortex_leaveoff_points (ON CONFLICT project_id DO UPDATE)
        # 2. Write .cortex/knowledge/LeaveOffPoint.md via IndexerService
        # 3. Return the upserted record

    async def get(self, project_id) -> dict | None:
        """Get the current LeaveOff point for a project."""

    async def delete(self, project_id) -> bool:
        """Remove LeaveOff point and corresponding file."""
```

Coordinates with `IndexerService` for file writing. DB is source of truth; file is the local readable copy.

### LeaveOffPoint.md Format

```markdown
---
project_id: <uuid>
component: "Authentication Module"
updated_at: "2026-03-08T14:30:00Z"
machine_id: "dev-workstation"
---

## What Was Accomplished
Added OAuth2 token refresh logic to the auth middleware...

## Component
Authentication Module -- `python/src/server/middleware/auth.py`

## Next Steps
- Implement token revocation endpoint
- Add refresh token rotation
- Write integration tests for token expiry edge cases

## References
- PRPs/ai_docs/AUTH_DESIGN.md
- python/src/server/services/auth_service.py
```

## API Routes

**File:** `python/src/server/api_routes/leaveoff_api.py`

| Method | Endpoint | Action |
|--------|----------|--------|
| `PUT` | `/api/projects/{project_id}/leaveoff` | Upsert (create or replace) |
| `GET` | `/api/projects/{project_id}/leaveoff` | Get current state |
| `DELETE` | `/api/projects/{project_id}/leaveoff` | Remove |

Nested under projects since it's a per-project singleton resource.

## MCP Tool

**File:** `python/src/mcp_server/features/leaveoff/leaveoff_tools.py`

Single tool: `manage_leaveoff_point(action, project_id, ...)`

Actions:
- `"update"` -- PUT to API. Required: `content`, `next_steps`. Optional: `component`, `references`, `machine_id`, `last_session_id`, `metadata`.
- `"get"` -- GET from API.
- `"delete"` -- DELETE from API.

Tool description explicitly mentions its role in session termination and context continuity.

## SessionStart Hook Integration

**Modification to:** `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`

Add a parallel fetch for the LeaveOff Point during the existing context-loading phase:

```python
sessions, tasks, knowledge, leaveoff = await asyncio.gather(
    client.get_recent_sessions(limit=5),
    client.get_active_tasks(limit=10),
    client.get_knowledge_status(),
    client.get_leaveoff_point(),          # NEW
    return_exceptions=True,
)
```

Inject into the `<cortex-context>` block:

```xml
## LeaveOff Point (Last Session State)
**Component:** Authentication Module
**Updated:** 2026-03-08T14:30:00Z

### Next Steps
- Implement token revocation endpoint
- Add refresh token rotation
- Write integration tests for token expiry edge cases

### References
- PRPs/ai_docs/AUTH_DESIGN.md
- python/src/server/services/auth_service.py
```

## Behavioral Enforcement (CLAUDE.md)

New section added after "Code Quality":

```markdown
## LeaveOff Point Protocol

### After Every Coding Task
After completing any coding task that adds, modifies, or removes functionality,
update the LeaveOff Point before moving to the next task:

1. Call `manage_leaveoff_point(action="update")` with:
   - `content`: What was accomplished (specific files changed and why)
   - `component`: The architectural module or feature area
   - `next_steps`: Concrete, actionable items for the next session (include file paths)
   - `references`: PRPs, design docs, or key files that informed this work

2. This is NOT optional. Skipping means the next session starts with no context.

### Session Resource Management (The 90% Rule)
When you observe any of these signals:
- The conversation has exceeded 80+ tool uses
- You receive a system reminder about observation count
- You sense the conversation has been running extensively

Upon detecting these signals:
1. Stop active coding immediately
2. Generate a final LeaveOff Point with comprehensive next_steps
3. Advise the user to start a new session
4. Do not continue coding after generating the final LeaveOff Point

### Session Start
The LeaveOff Point is automatically loaded via the session start hook.
Review the injected context and orient work around the documented next steps.
```

## 90% Rule: PostToolUse Observation Counter

**Modification to:** `integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py`

After appending observation to buffer, count total lines in JSONL file. At threshold (default: 80), emit a system reminder to stdout:

```
<system-reminder>
SESSION RESOURCE WARNING: This session has recorded {count} tool operations.
You are approaching resource limits. After completing your current task,
generate a final LeaveOff Point and advise the user to start a new session.
</system-reminder>
```

Fires once at threshold, then every 10 observations after. Does not force termination -- Claude sees the warning and follows the CLAUDE.md protocol.

## File Impact Summary

| File | Change Type |
|------|-------------|
| `migration/0.1.0/019_add_leaveoff_points.sql` | New |
| `python/src/server/services/leaveoff/__init__.py` | New |
| `python/src/server/services/leaveoff/leaveoff_service.py` | New |
| `python/src/server/api_routes/leaveoff_api.py` | New |
| `python/src/server/main.py` | Modify (register router) |
| `python/src/mcp_server/features/leaveoff/__init__.py` | New |
| `python/src/mcp_server/features/leaveoff/leaveoff_tools.py` | New |
| `python/src/mcp_server/mcp_server.py` | Modify (register tools) |
| `integrations/claude-code/plugins/cortex-memory/scripts/observation_hook.py` | Modify |
| `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py` | Modify |
| `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py` | Modify (add get_leaveoff_point) |
| `CLAUDE.md` | Modify (add LeaveOff Protocol section) |
| `python/tests/server/services/leaveoff/test_leaveoff_service.py` | New |
| `python/tests/server/api_routes/test_leaveoff_api.py` | New |
