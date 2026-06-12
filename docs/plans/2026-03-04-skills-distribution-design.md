# Cortex Skills Distribution System — Design

**Date:** 2026-03-04
**Status:** Approved
**Approach:** Skill-first (B) — bootstrap skill → MCP action → auto-seed → UI

## Problem

After implementing the skills management system, three gaps remain:

1. **No bootstrap path** — Skills must be manually copied to `~/.claude/skills/` on each machine. There is no automated way for a new machine to install the Cortex skills and register itself.
2. **Empty registry on fresh install** — The `cortex_skills` table starts empty. Even if a machine could run bootstrap, there is nothing to install.
3. **Read-only Skills tab** — The UI can show systems and their skill state but cannot remove a skill from a system or unlink a system from a project.

## Design

### Component 1: Auto-seed on Startup

**Location:** `python/src/server/main.py` (lifespan startup event)

On server startup, after the database connection is verified, scan `integrations/claude-code/skills/*/SKILL.md`. For each file:

1. Parse YAML frontmatter to extract `name` and `description`
2. Compute SHA-256 hash of full file content
3. Upsert into `cortex_skills`:
   - If skill does not exist → insert (version 1)
   - If skill exists and hash matches → skip
   - If skill exists and hash differs → update content, bump version

This ensures the registry always reflects the skills bundled with the Cortex repo. No new tables or migrations needed.

**Helper:** Extract seeding logic into `python/src/server/services/skills/skill_seeding_service.py` for testability. Call from the startup lifespan function.

### Component 2: Bootstrap MCP Tool Action

**Location:** `python/src/mcp_server/features/skills/skill_tools.py`

Add `action="bootstrap"` to the existing `manage_skills` MCP tool. A new `_handle_bootstrap()` function:

1. Fetches all skills from `GET /api/skills` with full content (`include_content=true` query param added to the skills list endpoint)
2. If `system_fingerprint` and `project_id` are provided, calls `POST /api/projects/{project_id}/sync` to register the system
3. Returns:

```json
{
  "success": true,
  "skills": [{"name": "cortex-memory", "content": "---\n...", "display_name": "..."}],
  "system": {"id": "...", "is_new": true, "name": "..."},
  "install_path": "~/.claude/skills",
  "message": "Bootstrap complete: 3 skills ready to install"
}
```

**API change:** Add `?include_content=true` query param to `GET /api/skills` endpoint so `list_skills_full()` is exposed via HTTP (currently only callable internally).

**Parameters:**
- `system_fingerprint` (optional) — registers system if provided
- `system_name` (optional) — name for new system
- `project_id` (optional) — links system to project on registration

### Component 3: `cortex-bootstrap` Skill

**Location:** `integrations/claude-code/skills/cortex-bootstrap/SKILL.md`

A Claude Code skill invoked as `/cortex-bootstrap` (or triggered by asking Claude to run the Cortex bootstrap). First-time use requires no pre-existing installation — any Claude Code session with the Cortex MCP server connected can run it.

**Phases:**

**Phase 0: Health check**
Call `health_check()`. Stop with a clear message if Cortex is unreachable.

**Phase 1: Compute fingerprint**
```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

**Phase 2: System name**
Suggest `hostname` as the system name. Ask the user to confirm or provide an alternative.

**Phase 3: Read project context**
Read `.claude/cortex-state.json` if it exists. Extract `cortex_project_id` if present.

**Phase 4: Call bootstrap MCP tool**
```
manage_skills(
    action="bootstrap",
    system_fingerprint="<fingerprint>",
    system_name="<confirmed name>",
    project_id="<cortex_project_id or omit>"
)
```

**Phase 5: Write skill files**
For each skill in the response:
```bash
mkdir -p ~/.claude/skills/<name>
cat > ~/.claude/skills/<name>/SKILL.md << 'EOF'
<content>
EOF
```

**Phase 6: Update state**
Merge into `.claude/cortex-state.json`:
```json
{
  "system_fingerprint": "<fingerprint>",
  "system_name": "<name>",
  "last_bootstrap": "<ISO timestamp>"
}
```

**Phase 7: Report**
```
## Cortex Bootstrap Complete

**System:** <name> (<system_id>)
**Skills installed:** <N> → ~/.claude/skills/
  - cortex-memory
  - cortex-skill-sync
  - cortex-bootstrap
  - cortex-link-project
**Project:** <title> (registered) — or "No project linked"

Restart Claude Code for the new skills to take effect.
```

Since `cortex-bootstrap` is itself one of the returned skills, it installs itself — making future runs available via `/cortex-bootstrap`.

### Component 4: Skills Tab UI Improvements

**Remove skill button** (`SystemSkillList.tsx`)
Add a "Remove" button (destructive styling) next to each installed skill row. Calls `useRemoveSkill()` mutation → existing `POST /api/projects/{project_id}/skills/{skill_id}/remove`.

**Unlink system from project** (`SystemCard.tsx`)
Add a ✕ icon button in the system card header. Calls a new `unlinkSystem` service method → new `DELETE /api/projects/{project_id}/systems/{system_id}` endpoint. On success, invalidate `skillKeys.byProject(projectId)`.

**New backend endpoint:**
```
DELETE /api/projects/{project_id}/systems/{system_id}
```
Deletes from `cortex_project_system_registrations`. System remains globally in `cortex_systems` — only the project association is removed.

**New service method:**
```typescript
async unlinkSystem(projectId: string, systemId: string): Promise<void>
```

**New mutation hook:**
```typescript
useUnlinkSystem() → invalidates skillKeys.byProject(projectId)
```

## Build Sequence (Approach B: Skill-first)

1. Write `cortex-bootstrap` SKILL.md
2. Add `?include_content=true` to skills list API endpoint
3. Add `action="bootstrap"` to `manage_skills` MCP tool
4. Add auto-seed startup logic (`SkillSeedingService` + lifespan hook)
5. Add `DELETE /api/projects/{project_id}/systems/{system_id}` endpoint
6. Add Remove button to `SystemSkillList.tsx`
7. Add Unlink system to `SystemCard.tsx` + service + hook
8. Verify end-to-end: fresh Cortex install → registry seeded → bootstrap on Mac → system appears in Skills tab → remove/unlink works

## Files Changed

### New
- `integrations/claude-code/skills/cortex-bootstrap/SKILL.md`
- `python/src/server/services/skills/skill_seeding_service.py`

### Modified
- `python/src/server/main.py` — startup seeding call
- `python/src/server/api_routes/skills_api.py` — `include_content` param + DELETE system endpoint
- `python/src/mcp_server/features/skills/skill_tools.py` — bootstrap action
- `cortex-ui/src/features/projects/skills/components/SystemSkillList.tsx` — remove button
- `cortex-ui/src/features/projects/skills/components/SystemCard.tsx` — unlink button
- `cortex-ui/src/features/projects/skills/services/skillService.ts` — unlinkSystem
- `cortex-ui/src/features/projects/skills/hooks/useSkillQueries.ts` — useUnlinkSystem

## Success Criteria

- Fresh Cortex install → registry automatically contains all bundled skills
- User in any Claude Code session (Mac, WSL, anywhere) with Cortex MCP connected can ask Claude to run the bootstrap and have skills installed to `~/.claude/skills/`
- System appears in Skills tab for the active project immediately after bootstrap
- Skills tab allows removing a skill from a system and unlinking a system from a project
