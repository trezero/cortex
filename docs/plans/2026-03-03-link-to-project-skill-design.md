# /link-to-project Skill Design

**Date:** 2026-03-03
**Status:** Approved

## Overview

A Claude Code skill (`/link-to-project`) that links the current repo to an Cortex project ecosystem. It establishes project hierarchy, associates knowledge sources, and optionally ingests local docs — all through a sequential wizard flow using existing MCP tools.

## Skill Identity

- **Name:** `cortex-link-project`
- **Command:** `/link-to-project`
- **Location:** `integrations/claude-code/skills/cortex-link-project/SKILL.md`
- **Approach:** Sequential wizard — phase-by-phase guided flow with questions at each step

## Workflow Phases

### Phase 0 — Health Check & State Load

- Verify Cortex is reachable (health endpoint)
- Read `.claude/cortex-state.json` if it exists
- If already linked, show current state and ask if user wants to modify, re-link, or cancel

### Phase 1 — Project Discovery

- Call `find_projects()` to list all existing projects
- Present the list and ask: "Which project do you want to link this repo to?"
- Options: select an existing project, or create a new one
- If creating new: ask for name, description, tags

### Phase 2 — Establish Hierarchy

- Ask: "What's the relationship?" with options:
  - **This repo is a child** of the selected project (selected project becomes parent)
  - **This repo is the parent** of the selected project (selected project becomes child)
  - **Siblings** — both share a common parent (ask which or create one)
- Call `manage_project` to create/update with `parent_project_id`
- If the current repo doesn't have its own project yet, create one first

### Phase 3 — Source Linking

- Call `rag_get_available_sources()` to show all knowledge sources
- Ask which sources to associate with this project (technical vs business categorization)
- Call the projects API to link selected sources via the junction table

### Phase 4 — Local Doc Ingestion (Optional)

- Ask: "Want to ingest docs from this repo into Cortex?"
- If yes: scan for doc files (`docs/`, `README.md`, `*.md`, etc.), show what was found
- Let user select which to ingest
- Call `manage_rag_source(action="add", source_type="inline", project_id=..., documents=[...])`
- Poll `rag_check_progress` until complete

### Phase 5 — Save State

- Write/update `.claude/cortex-state.json` with project link details
- Show summary of what was linked

## State File Schema

The skill reads and writes `.claude/cortex-state.json` (shared with cortex-memory skill):

```json
{
  "cortex_project_id": "9b18cc38-...",
  "parent_project_id": "5cb8f561-...",
  "project_name": "RecipeRaiders Admin Dashboard",
  "parent_project_name": "RecipeRaiders Ecosystem",
  "linked_at": "2026-03-03T19:30:00Z",
  "relationship": "child",
  "sources": {
    "bc86ca3c5826f4cd": {
      "title": "repdash-docs",
      "last_synced": "2026-03-03T19:30:00Z",
      "type": "technical"
    }
  }
}
```

## MCP Tool Call Sequence

| Phase | Tool | Purpose |
|-------|------|---------|
| 0 | (read local file) | Load `.claude/cortex-state.json` |
| 1 | `find_projects()` | List all projects for selection |
| 1 | `manage_project(action="create")` | Create new project if needed |
| 2 | `manage_project(action="update", parent_project_id=...)` | Set hierarchy |
| 3 | `rag_get_available_sources()` | List sources for linking |
| 3 | `manage_project(action="update")` | Associate sources via API |
| 4 | `manage_rag_source(action="add", source_type="inline")` | Ingest local docs |
| 4 | `rag_check_progress(progress_id=...)` | Poll ingestion status |
| 5 | (write local file) | Save `.claude/cortex-state.json` |

No new backend endpoints or MCP tools are needed — the skill orchestrates existing tools entirely.

## Error Handling

- **Already linked:** Show current state, ask to modify/re-link/cancel
- **Project not found:** Offer to create or search again
- **Cortex unreachable:** Fail fast with clear connection error message
- **Ingestion failures:** Report which files failed, continue with successful ones
- **No docs found:** Skip Phase 4 gracefully with a note
- **Circular hierarchy:** Detect and block A→B→A cycles with explanation

## Design Decisions

- **Sequential wizard over auto-detection:** More reliable, follows existing cortex-memory skill pattern, easier to debug
- **Uses existing MCP tools only:** No backend changes required
- **Shared state file:** `.claude/cortex-state.json` is shared with cortex-memory skill so other skills can read `parent_project_id` for cross-project searches
- **Can run from any repo:** Handles both parent and child directions
