# Projects View Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the horizontal card layout with a toolbar + adaptive grid/table view that scales to 50+ projects, adds system filtering, and surfaces uncommitted changes per system.

**Architecture:** Toolbar filter bar above a switchable grid/table layout. Client-side filtering using data enriched via backend batch queries. Session hooks capture git dirty state and report to backend.

**Tech Stack:** React 18, TypeScript 5, TanStack Query v5, Tailwind CSS, FastAPI, Supabase (PostgreSQL)

**Spec:** `docs/superpowers/specs/2026-03-19-projects-view-redesign.md`

---

## File Structure

### New Files (Frontend)
| File | Responsibility |
|------|---------------|
| `cortex-ui/src/features/projects/components/ProjectFilterBar.tsx` | Filter bar: Active toggle, System dropdown, Tags, Group, Search, View toggle, +New |
| `cortex-ui/src/features/projects/components/ProjectGrid.tsx` | CSS Grid container rendering ProjectGridCards |
| `cortex-ui/src/features/projects/components/ProjectGridCard.tsx` | Compact card: title, system badge, task pills, dirty dot, activity |
| `cortex-ui/src/features/projects/components/ProjectTable.tsx` | Sortable table with sticky header |
| `cortex-ui/src/features/projects/components/ProjectTableRow.tsx` | Individual table row |
| `cortex-ui/src/features/projects/components/SystemBadge.tsx` | Reusable OS-colored system badge |
| `cortex-ui/src/features/projects/hooks/useSystemQueries.ts` | Query hook + key factory for global systems list |
| `cortex-ui/src/features/projects/hooks/useProjectFilters.ts` | Filter state hook (Active toggle, system, tags, group, search, view mode) with localStorage persistence |
| `cortex-ui/src/features/projects/services/systemService.ts` | API client for `GET /api/systems` |

### New Files (Backend / Plugin)
| File | Responsibility |
|------|---------------|
| `migration/0.1.0/023_add_git_dirty_to_registrations.sql` | Add `git_dirty`, `git_dirty_checked_at` columns |
| `integrations/claude-code/plugins/cortex-memory/src/git_utils.py` | Shared `check_git_dirty()` and `load_system_id()` helpers for hooks |

### Modified Files (Frontend)
| File | Change |
|------|--------|
| `cortex-ui/src/features/projects/types/project.ts` | Add `tags`, `parent_project_id`, `system_registrations`, `has_uncommitted_changes` to Project interface |
| `cortex-ui/src/features/projects/views/ProjectsView.tsx` | Replace horizontal list + sidebar mode with filter bar + grid/table + detail area |
| `cortex-ui/src/features/projects/hooks/useProjectQueries.ts` | Remove single-pin enforcement from useUpdateProject optimistic update |
| `cortex-ui/src/features/projects/services/projectService.ts` | No change needed — response shape handled by type update |

### Modified Files (Backend)
| File | Change |
|------|--------|
| `python/src/server/services/projects/project_service.py` | Add batch query for system registrations in `list_projects`; remove single-pin enforcement from `update_project` |
| `python/src/server/api_routes/projects_api.py` | Include system registration data in list response; add `PUT .../git-status` endpoint |
| `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py` | Add `report_git_status()` method |
| `integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py` | Add git status capture and report |
| `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py` | Add git status capture and report |

### Removed Files
| File | Reason |
|------|--------|
| `cortex-ui/src/features/projects/components/ProjectList.tsx` | Replaced by ProjectGrid |
| `cortex-ui/src/features/projects/components/ProjectCard.tsx` | Replaced by ProjectGridCard |
| `cortex-ui/src/features/projects/components/ProjectCardActions.tsx` | Integrated into ProjectGridCard |
| `cortex-ui/src/features/projects/components/ProjectHeader.tsx` | Replaced by ProjectFilterBar |

---

## Task 1: Database Migration — git_dirty columns

**Files:**
- Create: `migration/0.1.0/023_add_git_dirty_to_registrations.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- 023_add_git_dirty_to_registrations.sql
-- Adds git dirty tracking to project-system registrations for the Projects view
-- uncommitted changes indicator.

ALTER TABLE cortex_project_system_registrations
  ADD COLUMN IF NOT EXISTS git_dirty boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS git_dirty_checked_at timestamptz;
```

- [ ] **Step 2: Run migration against Supabase**

Run: `psql $SUPABASE_DB_URL -f migration/0.1.0/023_add_git_dirty_to_registrations.sql`
Expected: ALTER TABLE (no errors)

- [ ] **Step 3: Verify columns exist**

Run: `psql $SUPABASE_DB_URL -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'cortex_project_system_registrations' AND column_name IN ('git_dirty', 'git_dirty_checked_at');"`
Expected: 2 rows returned

- [ ] **Step 4: Commit**

```bash
git add migration/0.1.0/023_add_git_dirty_to_registrations.sql
git commit -m "feat: add git_dirty columns to project system registrations"
```

---

## Task 2: Backend — Extend project list with system registrations

**Files:**
- Modify: `python/src/server/services/projects/project_service.py` (list_projects, ~line 89)
- Modify: `python/src/server/api_routes/projects_api.py` (list_projects endpoint, ~line 85)

- [ ] **Step 1: Add system registration batch query to ProjectService**

In `project_service.py`, add a new method after `list_projects`:

```python
async def get_system_registrations_for_projects(self, project_ids: list[str]) -> dict[str, list[dict]]:
    """Batch fetch system registrations for multiple projects.

    Returns a dict mapping project_id -> list of registration dicts.
    Each dict: {system_id, system_name, os, git_dirty, git_dirty_checked_at}
    """
    if not project_ids:
        return {}

    result = self.supabase_client.table("cortex_project_system_registrations") \
        .select("project_id, system_id, git_dirty, git_dirty_checked_at, cortex_systems(id, name, os)") \
        .in_("project_id", project_ids) \
        .execute()

    registrations: dict[str, list[dict]] = {}
    for row in result.data or []:
        pid = row["project_id"]
        system = row.get("cortex_systems") or {}
        entry = {
            "system_id": row["system_id"],
            "system_name": system.get("name", ""),
            "os": system.get("os"),
            "git_dirty": row.get("git_dirty", False),
            "git_dirty_checked_at": row.get("git_dirty_checked_at"),
        }
        registrations.setdefault(pid, []).append(entry)

    return registrations
```

- [ ] **Step 2: Update list_projects API endpoint to include system data**

In `projects_api.py`, in the `list_projects` endpoint, after fetching projects, add the batch query and merge:

```python
# After fetching projects list (existing code)
project_ids = [p["id"] for p in projects]
system_regs = await project_service.get_system_registrations_for_projects(project_ids)

# Enrich each project with system data
for project in projects:
    regs = system_regs.get(project["id"], [])
    project["system_registrations"] = regs
    project["has_uncommitted_changes"] = any(r.get("git_dirty") for r in regs)
```

- [ ] **Step 3: Test the endpoint manually**

Run: `curl -s http://localhost:8181/api/projects | python3 -m json.tool | head -40`
Expected: Projects include `system_registrations` array and `has_uncommitted_changes` boolean

- [ ] **Step 4: Commit**

```bash
git add python/src/server/services/projects/project_service.py python/src/server/api_routes/projects_api.py
git commit -m "feat: include system registrations in project list response"
```

---

## Task 3: Backend — git status reporting endpoint

**Files:**
- Modify: `python/src/server/api_routes/projects_api.py`

- [ ] **Step 1: Add PUT endpoint for git status reporting**

Add to `projects_api.py`:

```python
@router.put("/projects/{project_id}/systems/{system_id}/git-status")
async def update_git_status(project_id: str, system_id: str, request: Request):
    """Update git dirty status for a project-system registration."""
    body = await request.json()
    git_dirty = body.get("git_dirty", False)

    supabase = get_supabase_client()
    result = supabase.from_("cortex_project_system_registrations") \
        .update({
            "git_dirty": git_dirty,
            "git_dirty_checked_at": datetime.now(timezone.utc).isoformat(),
        }) \
        .eq("project_id", project_id) \
        .eq("system_id", system_id) \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Project-system registration not found")

    return {"success": True, "git_dirty": git_dirty}
```

Add `from datetime import datetime, timezone` import if not already present.

- [ ] **Step 2: Test the endpoint**

Run: `curl -s -X PUT http://localhost:8181/api/projects/TEST_PROJECT_ID/systems/TEST_SYSTEM_ID/git-status -H "Content-Type: application/json" -d '{"git_dirty": true}'`
Expected: `{"success": true, "git_dirty": true}` (or 404 if IDs don't match a real registration)

- [ ] **Step 3: Commit**

```bash
git add python/src/server/api_routes/projects_api.py
git commit -m "feat: add git status reporting endpoint for project-system registrations"
```

---

## Task 4: Plugin — Add git status reporting to CortexClient

**Files:**
- Modify: `integrations/claude-code/plugins/cortex-memory/src/cortex_client.py`

- [ ] **Step 1: Add report_git_status method**

Add to `CortexClient` class:

```python
async def report_git_status(self, system_id: str, git_dirty: bool) -> bool:
    """Report git dirty status for the current project + system."""
    if not self.api_url or not self.project_id or not system_id:
        return False

    url = f"{self.api_url}/api/projects/{self.project_id}/systems/{system_id}/git-status"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.put(url, json={"git_dirty": git_dirty})
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
```

- [ ] **Step 2: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/src/cortex_client.py
git commit -m "feat: add report_git_status to CortexClient"
```

---

## Task 5: Plugin — Add git status capture to session hooks

**Files:**
- Modify: `integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py`
- Modify: `integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py`

- [ ] **Step 1: Create shared git status helpers**

Create `integrations/claude-code/plugins/cortex-memory/src/git_utils.py` with shared helpers used by both hooks:

```python
import subprocess
import json as _json

def _check_git_dirty() -> bool:
    """Run git status --porcelain and return True if there are uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

def _load_system_id() -> str:
    """Read system_id from .claude/cortex-state.json."""
    state_path = Path.cwd() / ".claude" / "cortex-state.json"
    if state_path.is_file():
        try:
            data = _json.loads(state_path.read_text(encoding="utf-8"))
            return data.get("system_id", "")
        except (ValueError, OSError):
            pass
    return ""
```

- [ ] **Step 2: Add git status reporting to session_end_hook main()**

Add after the LeaveOffPoint materialization block (after line ~113):

```python
    # ── Report git dirty status ──────────────────────────────────────────
    if client.is_configured():
        system_id = _load_system_id()
        if system_id:
            try:
                git_dirty = _check_git_dirty()
                success = await asyncio.wait_for(
                    client.report_git_status(system_id, git_dirty),
                    timeout=3.0,
                )
                if success:
                    status = "dirty" if git_dirty else "clean"
                    print(f"cortex-memory: git status reported ({status})", file=sys.stderr)
            except (asyncio.TimeoutError, Exception) as e:
                print(f"cortex-memory: git status report failed: {e}", file=sys.stderr)
```

- [ ] **Step 3: Add git status reporting to session_start_hook**

In `session_start_hook.py`, import from the shared module:
```python
from src.git_utils import check_git_dirty, load_system_id
```

Add the same reporting block at the end of `main()`, after context is gathered but before output. This acts as the correction signal (handles commits made outside Claude Code).

- [ ] **Step 4: Test session end hook locally**

Run: `cd /home/winadmin/projects/Trinity/cortex && python integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py`
Expected: Should print git status report line to stderr (or "not configured" if Cortex is down)

- [ ] **Step 5: Commit**

```bash
git add integrations/claude-code/plugins/cortex-memory/src/git_utils.py integrations/claude-code/plugins/cortex-memory/scripts/session_end_hook.py integrations/claude-code/plugins/cortex-memory/scripts/session_start_hook.py
git commit -m "feat: capture and report git dirty status in session hooks"
```

---

## Task 6: Frontend — Project type updates + multi-pin model

**Files:**
- Modify: `cortex-ui/src/features/projects/types/project.ts` (lines 44-65)
- Modify: `cortex-ui/src/features/projects/hooks/useProjectQueries.ts` (lines 138-144)

- [ ] **Step 1: Add new fields to Project interface**

In `project.ts`, add to the `Project` interface after `business_sources`:

```typescript
  // System & hierarchy fields (already in backend response)
  tags?: string[];
  parent_project_id?: string;
  metadata?: Record<string, unknown>;

  // System registration data (from enriched list response)
  system_registrations?: ProjectSystemRegistration[];
  has_uncommitted_changes?: boolean;
```

Add the `ProjectSystemRegistration` interface above `Project`:

```typescript
export interface ProjectSystemRegistration {
  system_id: string;
  system_name: string;
  os: string | null;
  git_dirty: boolean;
  git_dirty_checked_at: string | null;
}
```

- [ ] **Step 2: Remove backend single-pin enforcement**

In `python/src/server/services/projects/project_service.py`, find the `update_project` method (~line 393) and **remove** the block that unpins all other projects when one is pinned:

```python
# DELETE THIS BLOCK (approximately lines 393-403):
if update_fields.get("pinned") is True:
    # Unpin any other pinned projects first
    unpin_response = (
        self.supabase_client.table("cortex_projects")
        .update({"pinned": False})
        .neq("id", project_id)
        .eq("pinned", True)
        .execute()
    )
```

- [ ] **Step 3: Remove frontend single-pin enforcement**

In `useProjectQueries.ts`, replace lines 138-144 in `useUpdateProject` `onMutate`:

```typescript
        // If pinning a project, unpin all others first
        if (updates.pinned === true) {
          return old.map((p) => ({
            ...p,
            pinned: p.id === projectId,
          }));
        }
```

With:

```typescript
        // Multi-pin: just update the target project's pinned state
```

So the `onMutate` falls through to line 146 which already handles generic updates: `return old.map((p) => (p.id === projectId ? { ...p, ...updates } : p));`

- [ ] **Step 4: Update pin success toast message**

In `useProjectQueries.ts`, update the `onSuccess` handler (~line 162-167) to remove "as default project" language:

```typescript
      if (variables.updates.pinned !== undefined) {
        const message = variables.updates.pinned
          ? `Pinned "${data.title}"`
          : `Unpinned "${data.title}"`;
        showToast(message, "info");
      }
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 6: Commit**

```bash
git add cortex-ui/src/features/projects/types/project.ts cortex-ui/src/features/projects/hooks/useProjectQueries.ts python/src/server/services/projects/project_service.py
git commit -m "feat: add system registration types and enable multi-pin"
```

---

## Task 7: Frontend — System service + query hook

**Files:**
- Create: `cortex-ui/src/features/projects/services/systemService.ts`
- Create: `cortex-ui/src/features/projects/hooks/useSystemQueries.ts`

- [ ] **Step 1: Create systemService.ts**

```typescript
import { callAPIWithETag } from "@/features/shared/api/apiClient";

export interface SystemSummary {
  id: string;
  name: string;
  os: string | null;
}

interface SystemsResponse {
  systems: SystemSummary[];
  count: number;
}

export const systemService = {
  async listSystems(): Promise<SystemSummary[]> {
    const response = await callAPIWithETag<SystemsResponse>("/api/systems");
    return response.systems;
  },
};
```

- [ ] **Step 2: Create useSystemQueries.ts**

```typescript
import { useQuery } from "@tanstack/react-query";
import { STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { systemService } from "../services/systemService";

export const systemKeys = {
  all: ["systems"] as const,
  lists: () => [...systemKeys.all, "list"] as const,
};

export function useSystems() {
  return useQuery({
    queryKey: systemKeys.lists(),
    queryFn: () => systemService.listSystems(),
    staleTime: STALE_TIMES.rare,
  });
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/projects/services/systemService.ts cortex-ui/src/features/projects/hooks/useSystemQueries.ts
git commit -m "feat: add system service and query hook for projects filter"
```

---

## Task 8: Frontend — Filter state hook with localStorage persistence

**Files:**
- Create: `cortex-ui/src/features/projects/hooks/useProjectFilters.ts`

- [ ] **Step 1: Create useProjectFilters hook**

```typescript
import { useCallback, useDeferredValue, useMemo, useState } from "react";
import type { Project } from "../types";

type ViewMode = "grid" | "table";
type SortColumn = "project" | "system" | "todo" | "doing" | "done" | "activity";
type SortDirection = "asc" | "desc";

interface SortState {
  column: SortColumn;
  direction: SortDirection;
}

const STORAGE_KEYS = {
  activeFilter: "cortex_projects_active_filter",
  viewMode: "cortex_projects_view_mode",
  sort: "cortex_projects_sort",
} as const;

function loadFromStorage<T>(key: string, fallback: T): T {
  try {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : fallback;
  } catch {
    return fallback;
  }
}

function saveToStorage(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage unavailable — ignore
  }
}

export function useProjectFilters() {
  // Persisted state
  const [activeOnly, setActiveOnlyRaw] = useState(() =>
    loadFromStorage(STORAGE_KEYS.activeFilter, false),
  );
  const [viewMode, setViewModeRaw] = useState<ViewMode>(() =>
    loadFromStorage(STORAGE_KEYS.viewMode, "grid"),
  );
  const [sort, setSortRaw] = useState<SortState>(() =>
    loadFromStorage(STORAGE_KEYS.sort, { column: "activity", direction: "desc" }),
  );

  // Non-persisted state
  const [systemId, setSystemId] = useState<string>("");
  const [tag, setTag] = useState<string>("");
  const [groupByParent, setGroupByParent] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearch = useDeferredValue(searchQuery);

  // Persisted setters
  const setActiveOnly = useCallback((value: boolean) => {
    setActiveOnlyRaw(value);
    saveToStorage(STORAGE_KEYS.activeFilter, value);
  }, []);

  const setViewMode = useCallback((value: ViewMode) => {
    setViewModeRaw(value);
    saveToStorage(STORAGE_KEYS.viewMode, value);
  }, []);

  const setSort = useCallback((value: SortState) => {
    setSortRaw(value);
    saveToStorage(STORAGE_KEYS.sort, value);
  }, []);

  const toggleSort = useCallback((column: SortColumn) => {
    setSort(prev => ({
      column,
      direction: prev.column === column && prev.direction === "asc" ? "desc" : "asc",
    }));
  }, [setSort]);

  // Filter function
  const filterProjects = useCallback(
    (projects: Project[]): Project[] => {
      let filtered = projects;

      if (activeOnly) {
        filtered = filtered.filter((p) => p.pinned);
      }
      if (systemId) {
        filtered = filtered.filter((p) =>
          p.system_registrations?.some((r) => r.system_id === systemId),
        );
      }
      if (tag) {
        filtered = filtered.filter((p) => p.tags?.includes(tag));
      }
      if (deferredSearch) {
        const q = deferredSearch.toLowerCase();
        filtered = filtered.filter((p) => p.title.toLowerCase().includes(q));
      }

      return filtered;
    },
    [activeOnly, systemId, tag, deferredSearch],
  );

  // Sort function (used by table view; grid always uses pinned-first + activity-desc)
  const sortProjects = useCallback(
    (projects: Project[], mode: "grid" | "table"): Project[] => {
      const sorted = [...projects];
      const pinnedFirst = (a: Project, b: Project) =>
        (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);

      if (mode === "grid") {
        // Fixed: pinned first, then by updated_at descending
        return sorted.sort((a, b) => {
          const pin = pinnedFirst(a, b);
          if (pin !== 0) return pin;
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });
      }

      // Table: pinned first, then by user-selected column
      return sorted.sort((a, b) => {
        const pin = pinnedFirst(a, b);
        if (pin !== 0) return pin;

        const dir = sort.direction === "asc" ? 1 : -1;
        switch (sort.column) {
          case "project": return dir * a.title.localeCompare(b.title);
          case "system": {
            const aName = a.system_registrations?.[0]?.system_name ?? "";
            const bName = b.system_registrations?.[0]?.system_name ?? "";
            return dir * aName.localeCompare(bName);
          }
          case "activity":
            return dir * (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime());
          default: return 0;
        }
      });
    },
    [sort],
  );

  // Extract unique tags from all projects
  const extractTags = useCallback((projects: Project[]): string[] => {
    const tagSet = new Set<string>();
    for (const p of projects) {
      for (const t of p.tags ?? []) {
        tagSet.add(t);
      }
    }
    return Array.from(tagSet).sort();
  }, []);

  return {
    // Filter state
    activeOnly, setActiveOnly,
    systemId, setSystemId,
    tag, setTag,
    groupByParent, setGroupByParent,
    searchQuery, setSearchQuery,
    // View state
    viewMode, setViewMode,
    sort, setSort, toggleSort,
    // Utilities
    filterProjects,
    sortProjects,
    extractTags,
  };
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/hooks/useProjectFilters.ts
git commit -m "feat: add useProjectFilters hook with localStorage persistence"
```

---

## Task 9: Frontend — SystemBadge component

**Files:**
- Create: `cortex-ui/src/features/projects/components/SystemBadge.tsx`

- [ ] **Step 1: Create SystemBadge**

```tsx
interface SystemBadgeProps {
  name: string;
  os: string | null;
  className?: string;
}

const OS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  Windows: { bg: "bg-blue-500/15", text: "text-blue-300", border: "border-blue-500/20" },
  Darwin: { bg: "bg-green-500/12", text: "text-green-300", border: "border-green-500/15" },
  Linux: { bg: "bg-orange-500/15", text: "text-orange-300", border: "border-orange-500/20" },
};

const DEFAULT_COLOR = { bg: "bg-white/10", text: "text-gray-400", border: "border-white/10" };

export function SystemBadge({ name, os, className = "" }: SystemBadgeProps) {
  const colors = (os && OS_COLORS[os]) || DEFAULT_COLOR;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] border ${colors.bg} ${colors.text} ${colors.border} ${className}`}
    >
      {name}
    </span>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/projects/components/SystemBadge.tsx
git commit -m "feat: add SystemBadge component with OS-based coloring"
```

---

## Task 10: Frontend — ProjectFilterBar component

**Files:**
- Create: `cortex-ui/src/features/projects/components/ProjectFilterBar.tsx`

- [ ] **Step 1: Create ProjectFilterBar**

Build the horizontal filter bar using the hook from Task 8 and systems from Task 7. Key elements:

- Active toggle: pill button with `aria-pressed`, glowing when active (purple glow via `box-shadow` and `ring`)
- System dropdown: `<select>` from `useSystems()` data
- Tags dropdown: `<select>` from `extractTags()`
- Group toggle button
- Search input with magnifying glass icon
- Grid/table view toggle (two buttons with active highlight)
- + New button (triggers `onNewProject` callback)
- Result count text below the bar: "Showing N filtered · M total"

Props: filter state from `useProjectFilters`, systems from `useSystems`, `onNewProject` callback, `totalCount` and `filteredCount` numbers.

Reference the mockup at `.superpowers/brainstorm/47395-1773953249/grid-layout-mockup.html` for exact styling and layout.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/components/ProjectFilterBar.tsx
git commit -m "feat: add ProjectFilterBar with Active toggle, system/tag filters, and view toggle"
```

---

## Task 11: Frontend — ProjectGridCard component

**Files:**
- Create: `cortex-ui/src/features/projects/components/ProjectGridCard.tsx`

- [ ] **Step 1: Create ProjectGridCard**

Compact card (~220px min-width) with:
- Header: title (left, semi-bold, 2-line clamp) + PINNED badge (right, small purple pill)
- System row: primary `SystemBadge` + "+N" overflow + amber dot for uncommitted changes
- Task pills: compact inline `N todo` (pink), `N doing` (blue), `N done` (green) — only non-zero
- Activity: relative timestamp at bottom (muted text)
- Selection: purple glow border + gradient on `isSelected`
- Click handler: `onSelect(project.id)`

Props: `project: Project`, `taskCounts`, `isSelected: boolean`, `onSelect: (id: string) => void`

The primary system is `system_registrations[0]` (or whichever was most recently active). Amber dot: `has_uncommitted_changes` boolean. Tooltip on amber dot: list systems with uncommitted changes and their `git_dirty_checked_at` as relative time.

Reference mockup at `.superpowers/brainstorm/47395-1773953249/grid-layout-mockup.html`.

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/projects/components/ProjectGridCard.tsx
git commit -m "feat: add ProjectGridCard with system badge and uncommitted indicator"
```

---

## Task 12: Frontend — ProjectGrid component

**Files:**
- Create: `cortex-ui/src/features/projects/components/ProjectGrid.tsx`

- [ ] **Step 1: Create ProjectGrid**

CSS Grid container:
```css
grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
gap: 12px;
```

Props: `projects: Project[]`, `taskCounts`, `selectedProjectId`, `onSelectProject`, `groupByParent: boolean`

When `groupByParent` is true:
- Group projects by `parent_project_id`
- Render parent title as section header (resolve from same projects array)
- Orphaned children (parent not in list) go to "Ungrouped" section
- Standalone projects (no parent, no children) render directly

When `groupByParent` is false: flat grid, all cards rendered.

Sort: pinned first, then by `updated_at` descending.

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/projects/components/ProjectGrid.tsx
git commit -m "feat: add ProjectGrid with CSS grid layout and parent grouping"
```

---

## Task 13: Frontend — ProjectTableRow + ProjectTable

**Files:**
- Create: `cortex-ui/src/features/projects/components/ProjectTableRow.tsx`
- Create: `cortex-ui/src/features/projects/components/ProjectTable.tsx`

- [ ] **Step 1: Create ProjectTableRow**

Table row with columns matching spec:
- Status: amber dot if `has_uncommitted_changes` (with `aria-label`)
- Project: title + PINNED badge
- System: primary `SystemBadge` + "+N"
- Todo/Doing/Done: colored counts, em-dash if zero
- Tags: compact tag pills
- Activity: relative time, right-aligned

Props: `project: Project`, `taskCounts`, `isSelected`, `onSelect`

- [ ] **Step 2: Create ProjectTable**

Full-width table with:
- Sticky header row with sortable columns (`aria-sort` attributes)
- Click headers to call `toggleSort(column)`
- Visual sort indicator (arrow up/down)
- Hover highlight on rows
- Sort logic: apply sort from `useProjectFilters` to project array
- Parent grouping: collapsible section headers when `groupByParent` is true

Props: `projects: Project[]`, `taskCounts`, `selectedProjectId`, `onSelectProject`, `sort`, `toggleSort`, `groupByParent`

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/projects/components/ProjectTableRow.tsx cortex-ui/src/features/projects/components/ProjectTable.tsx
git commit -m "feat: add ProjectTable and ProjectTableRow with sorting and grouping"
```

---

## Task 14: Frontend — Rewrite ProjectsView to use new components

**Files:**
- Modify: `cortex-ui/src/features/projects/views/ProjectsView.tsx`

This is the integration task. The current file is ~461 lines and manages horizontal/sidebar layout modes.

- [ ] **Step 1: Remove old layout code and components**

Remove from `ProjectsView.tsx`:
- `layoutMode` state and all sidebar-related code (~lines 54, 213-350)
- `searchQuery` state (~line 56) — now in `useProjectFilters`
- `SidebarProjectCard` inline component (~lines 351-423)
- `ProjectHeader` render (~lines 187-193)
- `ProjectList` render (~lines 197-207)
- Imports for `ProjectList`, `ProjectHeader`, `ProjectCard`

- [ ] **Step 2: Wire up new components**

Replace with:
```tsx
const filters = useProjectFilters();
const { data: systems = [] } = useSystems();
const { data: projects = [], isLoading } = useProjects();

const filteredProjects = filters.filterProjects(projects);
const availableTags = filters.extractTags(projects);
```

Render structure:
```tsx
<ProjectFilterBar
  filters={filters}
  systems={systems}
  tags={availableTags}
  totalCount={projects.length}
  filteredCount={filteredProjects.length}
  onNewProject={() => setShowNewProjectModal(true)}
/>

{/* Grid/Table area — constrained height when project selected */}
<div className={selectedProject ? "max-h-[45vh] overflow-y-auto" : "flex-1 overflow-y-auto"}>
  {filters.viewMode === "grid" ? (
    <ProjectGrid
      projects={filteredProjects}
      taskCounts={taskCounts}
      selectedProjectId={selectedProject?.id}
      onSelectProject={handleSelectProject}
      groupByParent={filters.groupByParent}
    />
  ) : (
    <ProjectTable
      projects={filteredProjects}
      taskCounts={taskCounts}
      selectedProjectId={selectedProject?.id}
      onSelectProject={handleSelectProject}
      sort={filters.sort}
      toggleSort={filters.toggleSort}
      groupByParent={filters.groupByParent}
    />
  )}
</div>

{/* Project detail tabs — same as current */}
{selectedProject && (
  <div className="flex-1 min-h-0 overflow-y-auto">
    {/* existing tab content */}
  </div>
)}
```

- [ ] **Step 3: Delete old component files**

Delete:
- `cortex-ui/src/features/projects/components/ProjectList.tsx`
- `cortex-ui/src/features/projects/components/ProjectCard.tsx`
- `cortex-ui/src/features/projects/components/ProjectCardActions.tsx`
- `cortex-ui/src/features/projects/components/ProjectHeader.tsx`

Verify no other files import them:

Run: `cd cortex-ui && grep -r "ProjectList\|ProjectCard\|ProjectCardActions\|ProjectHeader" src/ --include="*.tsx" --include="*.ts" -l`

Expected: Only the deleted files and possibly barrel exports to clean up.

- [ ] **Step 4: Verify the app builds**

Run: `cd cortex-ui && npx tsc --noEmit && npm run build`
Expected: No errors

- [ ] **Step 5: Verify the app runs**

Run: `cd cortex-ui && npm run dev`
Open `http://localhost:3737/projects` — verify filter bar renders, grid shows projects, table toggle works, Active toggle filters to pinned only.

- [ ] **Step 6: Commit**

```bash
git add -A cortex-ui/src/features/projects/
git commit -m "feat: replace horizontal project list with filterable grid/table view"
```

---

## Task 15: Visual polish and edge cases

**Files:**
- Modify: various components from Tasks 9-14

- [ ] **Step 1: Empty state for Active filter**

When Active toggle is ON and no projects are pinned, show centered message in the grid/table area:
"No active projects. Pin projects to see them here."

- [ ] **Step 2: Verify dark mode styling**

Open the app, check both grid and table views match the Tron-inspired glassmorphism aesthetic. Verify:
- Card backgrounds use `backdrop-blur` + transparency
- Selected card has purple aurora glow
- Table rows have hover highlights
- Active toggle glows when ON
- System badges are readable

- [ ] **Step 3: Keyboard accessibility**

- Table rows: focusable, Enter to select
- Active toggle: `aria-pressed`
- Sort headers: `aria-sort`
- Amber dot: `aria-label` with tooltip text

- [ ] **Step 4: Test with many projects**

If possible, create 15-20 test projects to verify:
- Grid reflows correctly at different viewport widths
- Table fits ~25 rows without scrolling at 1080p
- Filters work correctly with many items
- Performance is acceptable (no jank on filter changes)

- [ ] **Step 5: Commit**

```bash
git add -A cortex-ui/src/features/projects/
git commit -m "feat: polish projects view — empty states, accessibility, dark mode"
```

---

## Task 16: Restart backend and verify end-to-end

- [ ] **Step 1: Restart Docker services**

Run: `docker compose restart cortex-server cortex-mcp`

- [ ] **Step 2: Verify project list includes system data**

Run: `curl -s http://localhost:8181/api/projects | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d[0] if d else {}, indent=2))" | head -30`
Expected: First project includes `system_registrations` array

- [ ] **Step 3: Verify frontend consumes system data**

Open `http://localhost:3737/projects` and verify:
- System badges appear on project cards
- System filter dropdown is populated
- Uncommitted changes dots appear where applicable

- [ ] **Step 4: Test session end hook git reporting**

End a Claude Code session on a project with uncommitted changes, verify the amber dot appears.

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address integration issues from end-to-end testing"
```
