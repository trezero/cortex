# Sub-Project Navigation Design

## Problem

Parent projects (projects with children linked via `parent_project_id`) have no special treatment in the UI. Users cannot discover or navigate to child projects from a parent's inline detail panel. Additionally, parent-child relationships established by the scanner on one system cannot be managed or corrected from the Cortex UI.

## Design Decisions

- **Approach A** selected: horizontal scrolling card strip on the parent's inline detail area, with a management modal
- Parent-child is an **Cortex-level concept** (database), not tied to filesystem layout — a project can be a child on one system's directory structure but standalone on another
- `parent_project_id` is a **single field** — one parent per project, enforced by the DB's single-level hierarchy trigger
- Child cards use the **existing DataCard primitive** at a compact size for styling consistency
- No new database schema — all required fields already exist

## UI Architecture Context

There are no separate "project detail pages" in Cortex. The project UI is a single view (`ProjectsView.tsx`) with:
- A grid/table of projects at the top
- An inline tab panel (PillNavigation) below the grid when a project is selected
- Selecting a project highlights it in the grid and reveals the tab panel

All references to "detail page" in this spec mean the inline tab panel area within `ProjectsView.tsx`. Selecting a project means calling `handleProjectSelect(projectId)` which updates the URL to `/projects/{projectId}` and reveals the tabs.

## Section 1: Projects List — Parent Indicators

### Parent projects in grid/table

When a project has children (is a parent), the card shows:

- A **folder-tree icon** next to the project name
- A **count pill** (e.g., "3 sub-projects") styled consistently with existing StatPill — compact, muted color

The child count is computed **client-side** by iterating the full (unfiltered) project list and counting projects whose `parent_project_id` matches the parent's `id`. This is passed to the card component from the grid/table parent which already has the full list.

No other changes to the card. Clicking selects the project and reveals the detail panel as normal.

### Child projects in grid/table

When viewing the flat (ungrouped) list, child projects show a **breadcrumb-style parent link** under the project name:

- Format: `"↳ RecipeRaiders_Complete"` in muted text
- Clicking the parent name selects the parent project (calls `handleProjectSelect(parentId)`)
- Only visible in flat view — when grouped by parent, the hierarchy is already apparent

### Components affected

- `ProjectGridCard` — add icon + count pill for parents, breadcrumb for children
- `ProjectTableRow` — same indicators adapted for table layout

## Section 2: Inline Detail Area — Sub-Projects Strip

### Placement

When a parent project is selected, the `SubProjectsStrip` renders between the grid/table container and the `PillNavigation` tabs within `ProjectsView.tsx`. Specifically, it is inserted after the project list area (around line 187) and before the tab navigation (around line 195). It only renders when the selected project has children.

### Strip structure

- A muted `"Sub-Projects"` label (left-aligned, inline with the strip)
- Horizontal flex container with `gap: 8px` and `overflow-x: auto`
- Follow horizontal scroll pattern from UI_STANDARDS.md — wrap in `w-full` container, add `scrollbar-hide`, ensure `min-w-0` on flex ancestors
- A `"Manage"` button (`variant="ghost"`, small size) on the right side of the strip header
- Separated from the tabs below by a subtle border

### Child card contents (minimal)

- Project name
- System badges (e.g., macOS, WSL)
- Git dirty indicator (amber dot) if applicable
- Click anywhere on the card → selects that child project (calls `handleProjectSelect(childId)`)

### Click behavior when child is filtered out

If the child project is not visible in the current filtered grid/table (e.g., filtered by system or tag), clicking the child card navigates via URL (`/projects/{childId}`). The auto-select logic in `ProjectsView.tsx` handles selecting the project. The child will appear selected in the detail area even if not visible in the filtered list above — this is acceptable since the user explicitly clicked the child.

### Card styling

Compact variant of DataCard — same border, background, and color system as existing cards. Smaller padding and font size. Fixed minimum width to prevent cards from collapsing on narrow content.

### Loading and empty states

- **Loading:** Show a subtle skeleton placeholder (single line height matching the strip) while `useProjectChildren` is fetching
- **Error:** Show inline muted error text: "Failed to load sub-projects"
- **Empty array:** Hide the strip entirely (no empty state needed — a parent with no children simply has no strip)

### Breadcrumb on child projects

When a child project is selected (visible in the inline detail area), a breadcrumb appears above the project title in the detail header:

- Format: `"RecipeRaiders_Complete › RecipeRaiders"`
- Clicking the parent segment selects the parent project
- Does not appear for root-level projects

## Section 3: Parent-Child Management

### Entry point A: "Manage" button on the sub-projects strip

Opens a **ManageSubProjectsModal** with:

- **Current children** listed with a remove (unlink) button next to each
- **Search field** at the top to find and add existing Cortex projects as children
  - Filters out projects that already have a parent (single-parent constraint)
  - Filters out the parent itself
  - Selecting a project from results sets its `parent_project_id` to this parent
- Unlinking clears the child's `parent_project_id` — does not delete the project

### Entry point B: "Parent Project" dropdown on project edit form

No `EditProjectModal` currently exists. This entry point requires creating one or extending `NewProjectModal` to support editing. The implementation plan should include this as a prerequisite step.

The dropdown:
- Lists all projects that qualify as parents (no parent of their own, per single-level constraint)
- Includes a "None" option to clear the parent and make the project standalone
- Allows moving a child between parents or removing it from a parent entirely

### Entry point C: Scan-time conflict resolution (follow-up)

Deferred to a separate follow-up spec. The scan-time conflict detection (when a project is discovered under a different parent directory than its current `parent_project_id`) involves changes to the scanner script and skill logic that are orthogonal to the UI work in this spec.

For now, the "Set Parent" dropdown in the Cortex UI (Entry Point B) serves as the manual cleanup tool for parent conflicts.

## Section 4: Backend & Data

### Schema

No database changes. `parent_project_id` (UUID, self-referencing FK), `metadata` (JSONB), and `tags` (text array) already exist. Single-level hierarchy enforced by `enforce_single_level_hierarchy` trigger.

### Frontend type prerequisites

`parent_project_id` must be added to:
- `CreateProjectRequest` type in `features/projects/types/project.ts`
- `UpdateProjectRequest` type in `features/projects/types/project.ts`
- `CreateProjectSchema` and `UpdateProjectSchema` Zod schemas in `features/projects/schemas/index.ts`

These are blocking prerequisites for the management features in Section 3.

### Backend prerequisite: clearing `parent_project_id`

The current `PUT /api/projects/{id}` endpoint in `projects_api.py` uses `if request.parent_project_id is not None` to decide whether to update the field. This means sending `null` does NOT clear the parent — the field is simply skipped. To support the "None" option in the Parent Project dropdown and the unlink action in ManageSubProjectsModal, the backend must be updated to distinguish between "field not sent" (skip) and "field explicitly set to null" (clear). Use Pydantic's `model_fields_set` to check whether the field was included in the request body.

### New API endpoint

**`GET /api/projects/{id}/children`**

Returns a lightweight list of child projects for a given parent.

Response shape:
```json
{
  "children": [
    {
      "id": "uuid",
      "title": "string",
      "description": "string | null",
      "tags": ["string"],
      "system_registrations": [
        { "system_name": "string", "os": "string", "has_uncommitted_changes": "boolean" }
      ]
    }
  ]
}
```

The `ChildProject` type is a subset of `Project` — only fields needed by `SubProjectCard`.

This avoids loading full project data for each child on the parent detail panel.

### Existing endpoints (no changes needed)

- `PUT /api/projects/{id}` — backend already accepts `parent_project_id` for setting/clearing parent
- `GET /api/projects` — already returns `parent_project_id` for list indicators
- `GET /api/projects/{id}` — already returns full project data including `parent_project_id`

### Frontend data flow

**New query hook:** `useProjectChildren(projectId)`
- Fetches children via the new endpoint
- Query key: `projectKeys.children(id)` added to the existing factory
- Uses `STALE_TIMES.normal` (30s)

**New service method:** `projectService.getProjectChildren(id)` added to existing service file.

**Optimistic updates:** When linking/unlinking a child via the manage modal:
- Optimistically update the `projectKeys.children(parentId)` query
- Invalidate the affected child's detail query (its `parent_project_id` changed)
- Invalidate `projectKeys.lists()` since the project list includes `parent_project_id` which drives grouping, breadcrumbs, and count pills

### New components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SubProjectsStrip` | `features/projects/components/` | Horizontal strip + manage button, rendered in ProjectsView |
| `SubProjectCard` | `features/projects/components/` | Compact DataCard variant for the strip |
| `ManageSubProjectsModal` | `features/projects/components/` | Modal for adding/removing children |

### Modified components

| Component | Change |
|-----------|--------|
| `ProjectGridCard` | Add folder-tree icon + count pill for parents; breadcrumb link for children |
| `ProjectTableRow` | Same indicators adapted for table layout |
| `ProjectsView` | Insert `SubProjectsStrip` between grid/table and PillNavigation; add breadcrumb for child projects |
| `NewProjectModal` (or new `EditProjectModal`) | Add "Parent Project" dropdown field |
| `features/projects/types/project.ts` | Add `parent_project_id` to request types |
| `features/projects/schemas/index.ts` | Add `parent_project_id` to Zod schemas |

## Out of Scope

- Multi-parent relationships (DB enforces single parent)
- Deep nesting beyond one level (DB trigger prevents it)
- Drag-and-drop reordering of children
- Aggregated task/activity counts across children on the parent card
- Opening projects in external tools (Claude Code, terminals) from the UI
- Scan-time parent conflict detection (deferred to follow-up spec)
