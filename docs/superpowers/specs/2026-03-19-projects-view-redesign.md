# Projects View Redesign — System Filter & Scalable Layout

## Problem

The current Projects view uses a horizontal scrolling row of large cards (288px wide). This works for 5-10 projects but breaks down at 20-30 projects (requiring ~7200px of horizontal scroll). Users managing projects across multiple systems (Windows, WSL, macOS) have no way to filter by system, see which machine a project lives on, or identify uncommitted work left on another machine.

## Solution

Replace the horizontal card row with a toolbar + adaptive grid/table layout that scales to 50+ projects, adds system-aware filtering, and surfaces uncommitted changes per system.

## Design

### 1. Filter Bar

Horizontal toolbar pinned above the project list. Contents left-to-right:

1. **Active toggle** — Pill-shaped button with glowing dot when ON. Persisted to `localStorage` under `cortex_projects_active_filter`. When ON, only shows **pinned** projects — pinning is the mechanism users use to mark projects as "active." Visually distinct: purple glow border, lit dot, gradient background. When OFF, flat/muted appearance. This is the most prominent control in the bar. **Note**: The current codebase enforces single-pin (pinning one project unpins all others). This must be changed to support multi-pin — users should be able to pin multiple projects simultaneously. The unpin-others logic in `useProjectQueries.ts` optimistic update must be removed. **Empty state**: If Active is ON and no projects are pinned, show a centered message: "No active projects. Pin projects to see them here."

2. **System dropdown** — `<select>` populated from `cortex_systems` table. Options: "All Systems" (default) + one entry per registered system. Filtering is **client-side**: the projects list API response already includes `system_registrations` (see Data Fetching section below). The frontend filters the list in memory by checking if the selected system ID appears in a project's registrations. Not persisted — resets to "All Systems" on page load.

3. **Tags dropdown** — Populated from the union of all project `tags[]` arrays. Single-select. Options: "All Tags" (default) + distinct tag values. Not persisted.

4. **Group button** — Toggles parent-project grouping ON/OFF. When ON, child projects indent under their parent in both grid (visual grouping header) and table (indented rows with parent as section header, collapsible via chevron). Default: OFF. Not persisted.

5. **Spacer** — Flex spacer pushing remaining items right.

6. **Search** — Text input, filters by title substring (case-insensitive). Same behavior as current `ProjectHeader` search, relocated into the filter bar. Not persisted.

7. **View toggle** — Grid icon / list icon pair. Switches between grid and table views. Persisted to `localStorage` under `cortex_projects_view_mode`. Default: grid.

8. **+ New button** — Opens project creation modal. Same as current `NewProjectModal`.

**Result count** sits below the bar: "Showing 8 active projects · 24 total" — updates reactively as filters change.

### 2. Grid View (Card Layout)

**Layout**: CSS Grid with `grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))`. Cards reflow from ~5 columns on wide screens to 2 on narrow. Vertical scroll replaces horizontal scroll.

**Card anatomy** (top to bottom):

1. **Header row** — Project title (left-aligned, 14px, semi-bold, 2-line clamp) + PINNED badge (right, small purple pill, only if pinned).

2. **System row** — Primary system badge (color-coded by OS: blue for Windows, green for macOS, orange for Linux/WSL) + "+N" overflow text if registered on multiple systems + amber dot (right-aligned) if any linked system has uncommitted changes.

3. **Task pills row** — Compact inline pills: `N todo` (pink), `N doing` (blue), `N done` (green). Only non-zero counts shown.

4. **Activity timestamp** — Bottom, muted text. Relative format: "2 hours ago", "1 day ago". Derived from `updated_at` on the `cortex_projects` table (already in the API response). No session join needed — `updated_at` is sufficient and already reflects project mutations.

**Card interaction**:
- Click to select — purple glow border + subtle background gradient shift (same aurora effect as current design, adapted to smaller card).
- Selecting opens the project detail area below the grid.

**Sort order**: Pinned projects first, then by most recent activity descending. Not user-configurable in grid view (use table view for custom sorting). When switching from table view (with custom sort) back to grid view, the grid always uses its fixed sort. The table sort persists independently in localStorage and is restored when switching back to table view.

### 3. Table View (List Layout)

Full-width table with sticky header row. Replaces the grid entirely when table mode is toggled.

**Columns**:

| Column | Width | Sortable | Content |
|--------|-------|----------|---------|
| Status | ~4% | No | Amber dot if any system has uncommitted changes |
| Project | auto | Yes | Title + PINNED badge (inline) |
| System | ~15% | Yes | Primary system badge (OS-colored) + "+N" overflow |
| Todo | ~6% | Yes | Count in pink; em-dash if zero |
| Doing | ~6% | Yes | Count in blue; em-dash if zero |
| Done | ~6% | Yes | Count in green; em-dash if zero |
| Tags | ~12% | No | Tag pills (compact) |
| Activity | ~10% | Yes | Relative timestamp, right-aligned |

**Table interaction**:
- Click column headers to sort (ascending/descending toggle).
- Default sort: pinned first, then by activity descending.
- Sort column + direction persisted to `localStorage` under `cortex_projects_sort`.
- Click row to select project — subtle purple background highlight.
- Selecting opens the same project detail area below the table.
- Hover highlight on rows.

**Density**: ~40px per row. 25 projects fit on a 1080p display without scrolling.

**Parent grouping** (when Group toggle is ON): Parent projects render as section header rows (bolder styling). Children indent below with slight left padding. Parent rows are collapsible via a chevron icon.

### 4. Uncommitted Changes Data Pipeline

New data path to power the amber dot indicator on cards and table rows. **This is entirely new work** — neither session hook currently captures git status.

**Schema change** (migration 023):
```sql
ALTER TABLE cortex_project_system_registrations
  ADD COLUMN git_dirty boolean DEFAULT false,
  ADD COLUMN git_dirty_checked_at timestamptz;
```

**New backend endpoint: `PUT /api/projects/{project_id}/systems/{system_id}/git-status`**:

Accepts `{ git_dirty: boolean }` and updates the `git_dirty` and `git_dirty_checked_at` columns on `cortex_project_system_registrations`. This is what the hooks call.

**Session end hook changes** (primary signal — `session_end_hook.py`):

The existing hook flushes observation buffers and materializes LeaveOffPoint.md. Add after those steps:
1. Run `subprocess.run(["git", "status", "--porcelain"], capture_output=True)` in the current working directory.
2. Set `git_dirty = True` if stdout is non-empty, `False` otherwise.
3. Read `project_id` from `.claude/cortex-state.json` (already loaded by the hook for other purposes).
4. Read `system_id` from `.claude/cortex-state.json` (already contains `system_id` from registration).
5. Call `PUT /api/projects/{project_id}/systems/{system_id}/git-status` with `{ git_dirty }`.
6. If `project_id` or `system_id` is missing (project not linked), skip silently.

**Session start hook changes** (correction signal — `session_start_hook.py`):

Same `git status --porcelain` check and API call. This handles the case where a user commits outside Claude Code (manual `git commit`) then starts a new session — clears a stale dirty flag.

**API surface for reading**: The projects list endpoint aggregates `git_dirty` across all linked systems per project (see Section 5). Returns `has_uncommitted_changes: boolean` and `uncommitted_systems: [{system_name, checked_at}]` for tooltip detail.

**Staleness handling**: Amber dot tooltip shows "Uncommitted changes on WIN-AI-PC as of 2h ago". If `git_dirty_checked_at` is older than 24 hours, the dot dims slightly to indicate stale information.

**Relationship to LeaveOff Points**: The LeaveOff Point protocol tracks `git_clean` on `cortex_leaveoff_points` — this is written by Claude Code itself via the `manage_leaveoff_point` MCP tool, not by the hooks. The new `git_dirty` on `cortex_project_system_registrations` is a separate concern: LeaveOff captures session continuity state, while `git_dirty` captures persistent per-system dirty state for the Projects UI. They are independent data paths.

### 5. Data Fetching & API Changes

**Backend changes to `GET /api/projects`**:

The existing `ProjectService.list_projects()` returns rows from `cortex_projects` including `tags` and `parent_project_id` (these are already in the backend response but missing from the frontend `Project` TypeScript type). The endpoint must be extended to **also** include system registration data per project via a batch query (same pattern as task counts):

1. Fetch all projects from `cortex_projects` (existing).
2. Batch query `cortex_project_system_registrations` joined with `cortex_systems` to get `system_name`, `os`, `git_dirty`, `git_dirty_checked_at` per project.
3. Merge into response as `system_registrations: [{system_id, system_name, os, git_dirty, git_dirty_checked_at}]` per project.
4. Compute `has_uncommitted_changes: boolean` (true if any registration has `git_dirty = true`).

This keeps the main query simple and adds the system data as a secondary lookup, similar to how task counts work today.

**`GET /api/systems` endpoint** (for filter dropdown):

This endpoint already exists in `extensions_api.py` (line ~305) and returns all registered systems. Reuse it directly — no new endpoint needed. The frontend `systemService.ts` calls `GET /api/systems`.

**Frontend query hooks**:

New hooks following existing TanStack Query patterns:

```typescript
// In a new file: features/projects/hooks/useSystemQueries.ts
export const systemKeys = {
  all: ["systems"] as const,
  lists: () => [...systemKeys.all, "list"] as const,
};

export function useSystems() {
  return useQuery({
    queryKey: systemKeys.lists(),
    queryFn: () => systemService.listSystems(),
    staleTime: STALE_TIMES.rare, // Systems rarely change
  });
}
```

The existing `useProjects()` hook in `useProjectQueries.ts` continues to work — the response shape just gains `system_registrations` and `has_uncommitted_changes` fields.

**Frontend `Project` type additions**:

```typescript
// In features/projects/types/project.ts
interface ProjectSystemRegistration {
  system_id: string;
  system_name: string;
  os: string | null;
  git_dirty: boolean;
  git_dirty_checked_at: string | null;
}

interface Project {
  // ... existing fields ...
  tags?: string[];                              // Already in DB, needs adding to frontend type
  parent_project_id?: string;                   // Already in DB, needs adding to frontend type
  system_registrations?: ProjectSystemRegistration[];
  has_uncommitted_changes?: boolean;
}
```

**Search debounce**: The search input should use a 200ms debounce via `useDebounce` to avoid excessive re-renders with 50+ projects.

### 6. Parent Project Grouping

When the Group toggle is ON:

- Projects with `parent_project_id` are grouped under their parent.
- The parent project's title is used as the group header. Parent title is resolved from the same projects list (since both parent and child are in the response).
- Orphaned children (parent not in response due to deletion or filtering) appear in an "Ungrouped" section at the bottom.
- Projects with no `parent_project_id` and no children appear as standalone entries (not grouped).
- Collapsibility: group expand/collapse state is held in React state only (not persisted). All groups start expanded.

### 7. Multi-Pin Model Change

The current codebase enforces single-pin: pinning project A unpins all others (see optimistic update in `useProjectQueries.ts`). This must change to support the Active filter use case where users want multiple active projects.

**Changes**:
- Remove the "unpin all others" logic from the `useUpdateProject` optimistic update.
- The `pinned` column on `cortex_projects` is already a boolean per row — no schema change needed.
- The PINNED badge on cards/rows remains, just multiple projects can have it.
- Backend `update_project` endpoint already supports setting `pinned: true/false` per project — no backend change needed.

### 8. Project Detail Area

No functional change to the project detail area (Tasks, Docs, Knowledge, Extensions tabs).

**Layout change**:
- Detail area appears below the grid or table (depending on active view mode).
- When no project is selected, the grid/table fills the full vertical space.
- When a project is selected, the grid/table container gets a `max-height` with `overflow-y: auto` (roughly top 40-50% of viewport), and the detail area occupies the bottom half.
- URL routing unchanged: `/projects/:projectId` selects a project, `/projects` shows grid/table with no selection.

### 9. State Persistence

**Persisted to localStorage** (survives refresh and sessions):

| Key | Values | Default |
|-----|--------|---------|
| `cortex_projects_active_filter` | `true` / `false` | `false` |
| `cortex_projects_view_mode` | `"grid"` / `"table"` | `"grid"` |
| `cortex_projects_sort` | `{column, direction}` | `{column: "activity", direction: "desc"}` |

**Not persisted** (reset on page load):
- System filter — "All Systems"
- Tags filter — "All Tags"
- Group toggle — OFF
- Search query — empty

## Components Affected

### Removed
- `ProjectList.tsx` — horizontal scrolling card list (replaced by grid)
- `ProjectCard.tsx` — large 288px card (replaced by compact card)
- `ProjectCardActions.tsx` — pin/delete actions (integrated into new card)
- `ProjectHeader.tsx` — current header with search + layout toggle (replaced by filter bar)
- Sidebar layout mode and inline `SidebarProjectCard` code within `ProjectsView.tsx` (lines ~351-423)

### New
- `ProjectFilterBar.tsx` — filter bar with all controls
- `ProjectGrid.tsx` — CSS grid of compact cards
- `ProjectGridCard.tsx` — compact ~220px card with system badge, task pills, dirty indicator
- `ProjectTable.tsx` — sortable table with all columns
- `ProjectTableRow.tsx` — individual table row
- `useSystemQueries.ts` — query hook + key factory for global systems list
- `systemService.ts` — API client for `GET /api/systems`

### Modified
- `ProjectsView.tsx` — replace horizontal list + sidebar mode with filter bar + grid/table + detail area layout
- `useProjectQueries.ts` — remove single-pin enforcement from optimistic update
- `project.ts` (types) — add `tags`, `parent_project_id`, `system_registrations`, `has_uncommitted_changes` fields
- `projectService.ts` — update to consume new response fields
- Session end hook script — add `git status --porcelain` check and report
- Session start hook script — add `git status --porcelain` check and report
- `cortex_project_system_registrations` table — add `git_dirty`, `git_dirty_checked_at` columns (migration 023)
- `project_service.py` — extend `list_projects` to batch-query system registrations
- `projects_api.py` — include system registration data in list response; add `PUT /api/projects/{project_id}/systems/{system_id}/git-status` endpoint
- `session_end_hook.py` — add git status capture and report to Cortex
- `session_start_hook.py` — add git status capture and report to Cortex

## System Badge Color Scheme

| OS | Badge Color | Example |
|----|-------------|---------|
| Windows | Blue (`rgba(59,130,246,*)`) | `WIN-AI-PC` |
| macOS / Darwin | Green (`rgba(34,197,94,*)`) | `MacBookPro_M1` |
| Linux / WSL | Orange (`rgba(234,88,12,*)`) | `WSL-Ubuntu` |
| Unknown / null | Gray (`rgba(255,255,255,0.1)`) | `unknown-host` |

OS value is already stored in `cortex_systems.os` column.

## Accessibility

- Sortable table headers use `aria-sort` attribute (`ascending` / `descending` / `none`).
- Amber dot indicator includes `aria-label` with full tooltip text (e.g., "Uncommitted changes on WIN-AI-PC").
- Active toggle uses `aria-pressed` attribute.
- Table rows and grid cards are keyboard-navigable (Enter to select).
- Group collapse/expand chevrons use `aria-expanded`.

## ETag Caching Note

Adding `system_registrations` and `has_uncommitted_changes` to the projects list response means the ETag changes whenever any system's `git_dirty` state changes. This is acceptable — the data changes infrequently (only on session start/end), and the ETag savings from 304 responses still apply for the majority of polling intervals where nothing changed. If this proves to be an issue in practice, system status can be split to a separate endpoint later. This is explicitly out of scope for v1.

## Out of Scope

- Real-time git status monitoring (we capture at session start/end only)
- Bulk project actions (multi-select delete, bulk tag)
- Project creation from the table view (uses same modal as current)
- Changes to the project detail tabs (Tasks, Docs, Knowledge, Extensions)
- Pagination (not needed until 100+ projects; vertical scroll handles 50 well)
