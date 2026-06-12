# Sub-Project Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable parent-child project navigation with inline sub-project strips, management modals, and visual hierarchy indicators.

**Architecture:** Backend adds a children endpoint and fixes parent_project_id clearing. Frontend adds a SubProjectsStrip with compact DataCards to the inline detail area, parent/child indicators on grid cards and table rows, a ManageSubProjectsModal for link/unlink operations, and a parent dropdown on the project creation modal.

**Tech Stack:** FastAPI + Pydantic (backend), React 18 + TanStack Query v5 + Radix UI + Tailwind CSS (frontend)

**Spec:** `docs/superpowers/specs/2026-03-19-sub-project-navigation-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `cortex-ui/src/features/projects/components/SubProjectCard.tsx` | Compact DataCard for child projects in the strip |
| `cortex-ui/src/features/projects/components/SubProjectsStrip.tsx` | Horizontal scrolling strip + manage button |
| `cortex-ui/src/features/projects/components/ManageSubProjectsModal.tsx` | Modal to add/remove child projects |
| `python/tests/server/api_routes/test_project_children.py` | Backend tests for children endpoint + parent clearing |

### Modified Files
| File | Change |
|------|--------|
| `python/src/server/api_routes/projects_api.py` | Fix parent_project_id clearing via `model_fields_set`; add `GET /projects/{id}/children` |
| `python/src/server/services/projects/project_service.py` | Add `get_project_children()` method |
| `cortex-ui/src/features/projects/types/project.ts` | Add `parent_project_id` to request types; add `ChildProject` type |
| `cortex-ui/src/features/projects/schemas/index.ts` | Add `parent_project_id` to Zod schemas |
| `cortex-ui/src/features/projects/services/projectService.ts` | Add `getProjectChildren()` method |
| `cortex-ui/src/features/projects/hooks/useProjectQueries.ts` | Add `projectKeys.children()`, `useProjectChildren()` hook, `useSetParentProject()` mutation |
| `cortex-ui/src/features/projects/components/ProjectGridCard.tsx` | Folder-tree icon + count pill for parents; breadcrumb for children |
| `cortex-ui/src/features/projects/components/ProjectTableRow.tsx` | Same indicators for table layout |
| `cortex-ui/src/features/projects/views/ProjectsView.tsx` | Insert SubProjectsStrip; add breadcrumb in detail header |
| `cortex-ui/src/features/projects/components/NewProjectModal.tsx` | Add "Parent Project" dropdown field |

---

### Task 1: Backend — Fix parent_project_id clearing + children endpoint

**Files:**
- Modify: `python/src/server/api_routes/projects_api.py:408-435` (PUT endpoint)
- Modify: `python/src/server/api_routes/projects_api.py` (add GET children endpoint after PUT)
- Modify: `python/src/server/services/projects/project_service.py` (add `get_project_children`)
- Create: `python/tests/server/api_routes/test_project_children.py`

- [ ] **Step 1: Write backend tests for parent clearing and children endpoint**

Create `python/tests/server/api_routes/test_project_children.py`:

```python
"""Tests for sub-project navigation backend features."""
import pytest
from unittest.mock import MagicMock, patch


class TestParentProjectClearing:
    """Test that PUT /api/projects/{id} can clear parent_project_id."""

    @pytest.mark.asyncio
    async def test_explicit_null_clears_parent(self):
        """Sending parent_project_id=null should clear the field."""
        from src.server.api_routes.projects_api import UpdateProjectRequest

        # When parent_project_id is explicitly set to None in the JSON body,
        # it should appear in model_fields_set
        request = UpdateProjectRequest.model_validate({"parent_project_id": None})
        assert "parent_project_id" in request.model_fields_set

    def test_omitted_field_not_in_fields_set(self):
        """Omitting parent_project_id should NOT include it in model_fields_set."""
        from src.server.api_routes.projects_api import UpdateProjectRequest

        request = UpdateProjectRequest.model_validate({"title": "Updated"})
        assert "parent_project_id" not in request.model_fields_set

    def test_explicit_value_in_fields_set(self):
        """Sending a UUID for parent_project_id should include it in model_fields_set."""
        from src.server.api_routes.projects_api import UpdateProjectRequest

        request = UpdateProjectRequest.model_validate(
            {"parent_project_id": "550e8400-e29b-41d4-a716-446655440000"}
        )
        assert "parent_project_id" in request.model_fields_set
        assert request.parent_project_id == "550e8400-e29b-41d4-a716-446655440000"


class TestGetProjectChildren:
    """Test GET /api/projects/{id}/children endpoint."""

    def test_get_children_returns_list(self):
        """Service method should return child projects for a parent."""
        from src.server.services.projects.project_service import ProjectService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "child-1",
                "title": "Child Project",
                "description": "A child",
                "tags": ["tag1"],
                "parent_project_id": "parent-1",
            }
        ]

        # Chain the fluent API
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = ProjectService(mock_client)
        success, result = service.get_project_children("parent-1")

        assert success is True
        assert len(result["children"]) == 1
        assert result["children"][0]["id"] == "child-1"

    def test_get_children_empty(self):
        """No children returns empty list."""
        from src.server.services.projects.project_service import ProjectService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        service = ProjectService(mock_client)
        success, result = service.get_project_children("parent-with-no-children")

        assert success is True
        assert result["children"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/api_routes/test_project_children.py -v
```

Expected: FAIL — `get_project_children` does not exist yet.

- [ ] **Step 3: Add `get_project_children` to ProjectService**

In `python/src/server/services/projects/project_service.py`, add after the `update_project` method (after line ~469):

```python
    def get_project_children(
        self, parent_id: str
    ) -> tuple[bool, dict[str, Any]]:
        """
        Get lightweight child projects for a parent project.

        Returns only fields needed by SubProjectCard:
        id, title, description, tags, parent_project_id
        """
        try:
            response = (
                self.supabase_client.table("cortex_projects")
                .select("id, title, description, tags, parent_project_id")
                .eq("parent_project_id", parent_id)
                .execute()
            )

            children = response.data or []
            return True, {"children": children}

        except Exception as e:
            logger.error(f"Error fetching children for project {parent_id}: {e}")
            return False, {"error": f"Error fetching project children: {str(e)}"}
```

- [ ] **Step 4: Fix parent_project_id clearing in PUT endpoint**

In `python/src/server/api_routes/projects_api.py`, replace lines 430-431 (the `parent_project_id` guard in the PUT handler) with `model_fields_set` logic.

Replace:
```python
        if request.parent_project_id is not None:
            update_fields["parent_project_id"] = request.parent_project_id
```

With:
```python
        if "parent_project_id" in request.model_fields_set:
            update_fields["parent_project_id"] = request.parent_project_id
```

This allows sending `{"parent_project_id": null}` to clear the parent, while omitting the field entirely skips the update.

- [ ] **Step 5: Add GET /projects/{id}/children endpoint**

In `python/src/server/api_routes/projects_api.py`, add after the PUT endpoint (after the `update_project` function):

```python
@router.get("/projects/{project_id}/children")
async def get_project_children(project_id: str):
    """Get lightweight child projects for a parent project."""
    try:
        supabase_client = get_supabase_client()
        project_service = ProjectService(supabase_client)

        success, result = project_service.get_project_children(project_id)

        if not success:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to fetch children"))

        # Enrich children with system_registrations
        # get_system_registrations_for_projects returns dict[str, list[dict]]
        # mapping project_id -> list of registration dicts directly
        children = result.get("children", [])
        if children:
            child_ids = [c["id"] for c in children]
            reg_map = project_service.get_system_registrations_for_projects(child_ids)
            for child in children:
                child["system_registrations"] = reg_map.get(child["id"], [])

        return {"children": children}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project children | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/api_routes/test_project_children.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add python/src/server/api_routes/projects_api.py python/src/server/services/projects/project_service.py python/tests/server/api_routes/test_project_children.py
git commit -m "feat: add children endpoint and fix parent_project_id clearing"
```

---

### Task 2: Frontend types and Zod schemas

**Files:**
- Modify: `cortex-ui/src/features/projects/types/project.ts:85-108`
- Modify: `cortex-ui/src/features/projects/schemas/index.ts:7-22`

- [ ] **Step 1: Add `parent_project_id` to request types and add `ChildProject` type**

In `cortex-ui/src/features/projects/types/project.ts`:

Add to `CreateProjectRequest` (after line 95, the `business_sources` field):
```typescript
  parent_project_id?: string | null;
```

Add to `UpdateProjectRequest` (after line 107, the `pinned` field):
```typescript
  parent_project_id?: string | null;
```

Add `ChildProject` type at the end of the file (after `PaginatedResponse`):
```typescript
/** Lightweight child project for SubProjectCard display */
export interface ChildProject {
  id: string;
  title: string;
  description?: string | null;
  tags?: string[];
  parent_project_id: string;
  system_registrations?: ProjectSystemRegistration[];
}
```

- [ ] **Step 2: Add `parent_project_id` to Zod schemas**

In `cortex-ui/src/features/projects/schemas/index.ts`:

Add to `CreateProjectSchema` (after the `pinned` field on line 19):
```typescript
  parent_project_id: z.string().uuid().nullable().optional(),
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects"
```

Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/projects/types/project.ts cortex-ui/src/features/projects/schemas/index.ts
git commit -m "feat: add parent_project_id to FE request types and Zod schemas"
```

---

### Task 3: Frontend service method + query hooks

**Files:**
- Modify: `cortex-ui/src/features/projects/services/projectService.ts`
- Modify: `cortex-ui/src/features/projects/hooks/useProjectQueries.ts`

- [ ] **Step 1: Add `getProjectChildren` to projectService**

In `cortex-ui/src/features/projects/services/projectService.ts`, add after the `getProjectFeatures` method (before the closing `};`):

```typescript
  /**
   * Get lightweight child projects for a parent
   */
  async getProjectChildren(projectId: string): Promise<ChildProject[]> {
    try {
      const response = await callAPIWithETag<{ children: ChildProject[] }>(
        `/api/projects/${projectId}/children`,
      );
      return response.children || [];
    } catch (error) {
      console.error(`Failed to get children for project ${projectId}:`, error);
      throw error;
    }
  },
```

Add the `ChildProject` import at the top:
```typescript
import type { ChildProject, CreateProjectRequest, Project, ProjectFeatures, UpdateProjectRequest } from "../types";
```

- [ ] **Step 2: Add `projectKeys.children` and `useProjectChildren` hook**

In `cortex-ui/src/features/projects/hooks/useProjectQueries.ts`:

Add to `projectKeys` factory (after the `features` key, line 19):
```typescript
  children: (id: string) => [...projectKeys.all, id, "children"] as const,
```

Add `ChildProject` to the type import:
```typescript
import type { ChildProject, CreateProjectRequest, Project, UpdateProjectRequest } from "../types";
```

Add `useProjectChildren` hook after `useProjectFeatures`:
```typescript
// Fetch child projects for a parent
export function useProjectChildren(projectId: string | undefined) {
  return useQuery<ChildProject[]>({
    queryKey: projectId ? projectKeys.children(projectId) : DISABLED_QUERY_KEY,
    queryFn: () =>
      projectId ? projectService.getProjectChildren(projectId) : Promise.reject("No project ID"),
    enabled: !!projectId,
    staleTime: STALE_TIMES.normal,
  });
}
```

Add `useSetParentProject` mutation hook after `useDeleteProject`:
```typescript
// Set or clear a project's parent (for manage modal + parent dropdown)
export function useSetParentProject() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: ({
      projectId,
      parentProjectId,
    }: {
      projectId: string;
      parentProjectId: string | null;
    }) => projectService.updateProject(projectId, { parent_project_id: parentProjectId }),

    onSuccess: (_data, variables) => {
      // Invalidate lists (parent indicators change) and all children queries.
      // We can't know the old parent when unlinking, so invalidate broadly.
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) && query.queryKey.includes("children"),
      });

      const action = variables.parentProjectId ? "linked" : "unlinked";
      showToast(`Project ${action} successfully`, "success");
    },
    onError: () => {
      showToast("Failed to update parent project", "error");
    },
  });
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects"
```

Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/projects/services/projectService.ts cortex-ui/src/features/projects/hooks/useProjectQueries.ts
git commit -m "feat: add children service method and query hooks"
```

---

### Task 4: SubProjectCard component

**Files:**
- Create: `cortex-ui/src/features/projects/components/SubProjectCard.tsx`

- [ ] **Step 1: Create SubProjectCard**

Create `cortex-ui/src/features/projects/components/SubProjectCard.tsx`:

```tsx
import { DataCard, DataCardContent } from "../../ui/primitives/data-card";
import { cn } from "../../ui/primitives/styles";
import type { ChildProject } from "../types";
import { resolveEdgeColor, SystemBadge } from "./SystemBadge";

interface SubProjectCardProps {
  project: ChildProject;
  onSelect: (id: string) => void;
}

export function SubProjectCard({ project, onSelect }: SubProjectCardProps) {
  const registrations = project.system_registrations ?? [];
  const primaryReg = registrations[0];
  const edgeColor = primaryReg ? resolveEdgeColor(primaryReg.system_name) : "cyan";

  const hasDirty = registrations.some((r) => r.git_dirty);

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "shrink-0 w-52 cursor-pointer transition-transform duration-200",
        "hover:scale-[1.02] hover:shadow-[0_0_15px_rgba(6,182,212,0.15)]",
      )}
      onClick={() => onSelect(project.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(project.id);
        }
      }}
    >
      <DataCard edgePosition="top" edgeColor={edgeColor} blur="md" compact>
        <DataCardContent className="px-3 py-2.5 space-y-1.5">
          {/* Project name */}
          <span className="text-sm font-medium text-white/80 truncate block">
            {project.title}
          </span>

          {/* System badges + dirty indicator */}
          <div className="flex items-center gap-1.5">
            {primaryReg && (
              <SystemBadge name={primaryReg.system_name} os={primaryReg.os} />
            )}
            {registrations.length > 1 && (
              <span className="text-[10px] text-gray-500">
                +{registrations.length - 1}
              </span>
            )}
            {hasDirty && (
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full bg-amber-500 ml-auto shrink-0",
                  "shadow-[0_0_4px_rgba(245,158,11,0.5)]",
                )}
                aria-label="Uncommitted changes"
              />
            )}
          </div>
        </DataCardContent>
      </DataCard>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "SubProjectCard"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/components/SubProjectCard.tsx
git commit -m "feat: add SubProjectCard compact component"
```

---

### Task 5: SubProjectsStrip component

**Files:**
- Create: `cortex-ui/src/features/projects/components/SubProjectsStrip.tsx`

- [ ] **Step 1: Create SubProjectsStrip**

Create `cortex-ui/src/features/projects/components/SubProjectsStrip.tsx`:

```tsx
import { Settings2 } from "lucide-react";
import { Button } from "../../ui/primitives/button";
import { cn } from "../../ui/primitives/styles";
import { useProjectChildren } from "../hooks/useProjectQueries";
import { SubProjectCard } from "./SubProjectCard";

interface SubProjectsStripProps {
  parentProjectId: string;
  onSelectProject: (id: string) => void;
  onManage: () => void;
}

export function SubProjectsStrip({
  parentProjectId,
  onSelectProject,
  onManage,
}: SubProjectsStripProps) {
  const { data: children, isLoading, error } = useProjectChildren(parentProjectId);

  // Hide strip entirely when no children and not loading
  if (!isLoading && !error && (!children || children.length === 0)) {
    return null;
  }

  return (
    <div className="border-b border-white/5 pb-3 mb-1">
      {/* Strip header */}
      <div className="flex items-center justify-between px-4 mb-2">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
          Sub-Projects
        </span>
        <Button
          variant="ghost"
          size="xs"
          onClick={onManage}
          aria-label="Manage sub-projects"
        >
          <Settings2 className="w-3.5 h-3.5 mr-1" aria-hidden="true" />
          Manage
        </Button>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="px-4">
          <div className="h-16 rounded-lg bg-white/5 animate-pulse" />
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="px-4 text-xs text-red-400/70">
          Failed to load sub-projects
        </div>
      )}

      {/* Cards strip */}
      {children && children.length > 0 && (
        <div className="w-full px-4">
          <div className={cn("overflow-x-auto scrollbar-hide")}>
            <div className="flex gap-2 min-w-max">
              {children.map((child) => (
                <SubProjectCard
                  key={child.id}
                  project={child}
                  onSelect={onSelectProject}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "SubProjectsStrip"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/components/SubProjectsStrip.tsx
git commit -m "feat: add SubProjectsStrip horizontal scrolling component"
```

---

### Task 6: Parent/child indicators on ProjectGridCard and ProjectTableRow

**Files:**
- Modify: `cortex-ui/src/features/projects/components/ProjectGridCard.tsx`
- Modify: `cortex-ui/src/features/projects/components/ProjectTableRow.tsx`

- [ ] **Step 1: Add childCount and parentTitle props to ProjectGridCard**

In `cortex-ui/src/features/projects/components/ProjectGridCard.tsx`:

Add `FolderTree` to the lucide import:
```typescript
import { Clock, FolderTree, Zap } from "lucide-react";
```

Extend the interface (add after `onTogglePin`):
```typescript
  childCount?: number;
  parentTitle?: string;
  onSelectParent?: (parentId: string) => void;
```

Add after `const edgeColor = ...` (line 47):
```typescript
  const parentId = project.parent_project_id;
```

In the title `<span>` section (inside `DataCardHeader`, after the pin button), wrap the title and add indicators. Replace the `<span>` for the title (lines 106-113):
```tsx
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                {childCount !== undefined && childCount > 0 && (
                  <FolderTree className="w-3.5 h-3.5 text-gray-400 shrink-0" aria-hidden="true" />
                )}
                <span
                  className={cn(
                    "text-base font-semibold leading-tight line-clamp-2",
                    isSelected ? "text-white/90" : "text-white/80",
                  )}
                >
                  {project.title}
                </span>
              </div>
              {parentTitle && parentId && (
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:text-cyan-400 transition-colors truncate block mt-0.5"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectParent?.(parentId);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onSelectParent?.(parentId);
                    }
                  }}
                >
                  ↳ {parentTitle}
                </button>
              )}
            </div>
```

Add child count pill after the task pills row (after the `{/* Task pills row */}` section, before `{/* Activity timestamp */}`):
```tsx
          {/* Sub-project count */}
          {childCount !== undefined && childCount > 0 && (
            <StatPill color="gray" value={`${childCount} sub`} size="sm" />
          )}
```

Add `StatPill` import if not already present (it's already imported).

- [ ] **Step 2: Add same props to ProjectTableRow**

In `cortex-ui/src/features/projects/components/ProjectTableRow.tsx`:

Add `FolderTree` to imports:
```typescript
import { FolderTree, Zap } from "lucide-react";
```

Extend the interface (add after `onTogglePin`):
```typescript
  childCount?: number;
  parentTitle?: string;
  onSelectParent?: (parentId: string) => void;
```

Update the destructuring:
```typescript
export function ProjectTableRow({
  project, taskCounts, isSelected, onSelect, onTogglePin,
  childCount, parentTitle, onSelectParent,
}: ProjectTableRowProps) {
```

In the project name column (lines 87-89), add indicators:
```tsx
      {/* Project column (flex-1) */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {childCount !== undefined && childCount > 0 && (
            <FolderTree className="w-3 h-3 text-gray-500 shrink-0" aria-hidden="true" />
          )}
          <span className="text-sm text-[#c0c0d8] truncate">{project.title}</span>
          {childCount !== undefined && childCount > 0 && (
            <span className="text-[10px] text-gray-600 shrink-0">{childCount} sub</span>
          )}
        </div>
        {parentTitle && project.parent_project_id && (
          <button
            type="button"
            className="text-[11px] text-gray-500 hover:text-cyan-400 transition-colors truncate block"
            onClick={(e) => {
              e.stopPropagation();
              onSelectParent?.(project.parent_project_id!);
            }}
          >
            ↳ {parentTitle}
          </button>
        )}
      </div>
```

- [ ] **Step 3: Update ProjectGrid and ProjectTable to pass new props**

In `cortex-ui/src/features/projects/components/ProjectGrid.tsx`:

Add `allProjects` prop (full unfiltered list for child counting) and `onSelectProject` becomes the parent selector too. Actually, `projects` is the sorted/filtered list. We need the **full** list for child counting. Add a new prop:

Extend props:
```typescript
interface ProjectGridProps {
  projects: Project[];
  allProjects: Project[];
  taskCounts: TaskCountMap;
  selectedProjectId?: string;
  onSelectProject: (id: string) => void;
  onTogglePin?: (id: string, pinned: boolean) => void;
  groupByParent: boolean;
}
```

Add after destructuring:
```typescript
  // Build child count map from the full project list
  const childCountMap = new Map<string, number>();
  const parentTitleMap = new Map<string, string>();
  for (const p of allProjects) {
    if (p.parent_project_id) {
      childCountMap.set(p.parent_project_id, (childCountMap.get(p.parent_project_id) ?? 0) + 1);
    }
  }
  // Build parent title lookup
  const projectTitleMap = new Map(allProjects.map((p) => [p.id, p.title]));
```

Pass new props to every `<ProjectGridCard>`:
```tsx
  childCount={childCountMap.get(project.id)}
  parentTitle={project.parent_project_id ? projectTitleMap.get(project.parent_project_id) : undefined}
  onSelectParent={onSelectProject}
```

In `cortex-ui/src/features/projects/components/ProjectTable.tsx`:

Add `allProjects` to the interface:
```typescript
interface ProjectTableProps {
  projects: Project[];
  allProjects: Project[];
  taskCounts: TaskCountMap;
  selectedProjectId?: string;
  onSelectProject: (id: string) => void;
  onTogglePin?: (id: string, pinned: boolean) => void;
  sort: SortState;
  toggleSort: (column: SortColumn) => void;
  groupByParent: boolean;
}
```

Add the same child/parent maps after destructuring (same pattern as ProjectGrid):
```typescript
  const childCountMap = new Map<string, number>();
  for (const p of allProjects) {
    if (p.parent_project_id) {
      childCountMap.set(p.parent_project_id, (childCountMap.get(p.parent_project_id) ?? 0) + 1);
    }
  }
  const projectTitleMap = new Map(allProjects.map((p) => [p.id, p.title]));
```

Update the `renderRow` helper to pass new props:
```typescript
  const renderRow = (project: Project) => (
    <ProjectTableRow
      key={project.id}
      project={project}
      taskCounts={taskCounts[project.id]}
      isSelected={selectedProjectId === project.id}
      onSelect={onSelectProject}
      onTogglePin={onTogglePin}
      childCount={childCountMap.get(project.id)}
      parentTitle={project.parent_project_id ? projectTitleMap.get(project.parent_project_id) : undefined}
      onSelectParent={onSelectProject}
    />
  );
```

Also fix the group collapse toggle (line 92-101) for accessibility — add `role`, `tabIndex`, `onKeyDown`, `aria-expanded`:
```tsx
          <div
            key={`group-${parent.id}`}
            role="button"
            tabIndex={0}
            aria-expanded={!isCollapsed}
            className="flex items-center gap-2 px-4 py-1.5 bg-white/[0.015] border-b border-white/5 cursor-pointer hover:bg-white/[0.03] transition-colors focus:outline-none focus:ring-1 focus:ring-purple-500/30"
            onClick={() => toggleCollapse(parent.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleCollapse(parent.id);
              }
            }}
          >
```

- [ ] **Step 4: Update ProjectsView to pass `allProjects` to Grid/Table**

In `cortex-ui/src/features/projects/views/ProjectsView.tsx`, pass `allProjects={projects as Project[]}` to both `<ProjectGrid>` and `<ProjectTable>`.

- [ ] **Step 5: Verify TypeScript compiles and check in browser**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects"
```

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add cortex-ui/src/features/projects/components/ProjectGridCard.tsx cortex-ui/src/features/projects/components/ProjectTableRow.tsx cortex-ui/src/features/projects/components/ProjectGrid.tsx cortex-ui/src/features/projects/components/ProjectTable.tsx cortex-ui/src/features/projects/views/ProjectsView.tsx
git commit -m "feat: add parent/child indicators to grid cards and table rows"
```

---

### Task 7: Integrate SubProjectsStrip into ProjectsView

**Files:**
- Modify: `cortex-ui/src/features/projects/views/ProjectsView.tsx`

- [ ] **Step 1: Add SubProjectsStrip and breadcrumb to ProjectsView**

Add imports:
```typescript
import { SubProjectsStrip } from "../components/SubProjectsStrip";
```

Add state for manage modal:
```typescript
const [isManageSubProjectsOpen, setIsManageSubProjectsOpen] = useState(false);
```

Compute whether selected project is a parent (has children). Use the full projects list:
```typescript
const selectedIsParent = selectedProject
  ? (projects as Project[]).some((p) => p.parent_project_id === selectedProject.id)
  : false;

const selectedParentTitle = selectedProject?.parent_project_id
  ? (projects as Project[]).find((p) => p.id === selectedProject.parent_project_id)?.title
  : undefined;
```

Insert `SubProjectsStrip` after the grid/table area `</div>` (after line 187) and before the detail tabs section:
```tsx
        {/* Sub-projects strip for parent projects */}
        {selectedProject && selectedIsParent && (
          <SubProjectsStrip
            parentProjectId={selectedProject.id}
            onSelectProject={handleProjectSelect}
            onManage={() => setIsManageSubProjectsOpen(true)}
          />
        )}
```

Add breadcrumb above the PillNavigation (inside the detail area, before the `<div className="flex items-center justify-between mb-6">`):
```tsx
              {/* Breadcrumb for child projects */}
              {selectedParentTitle && selectedProject?.parent_project_id && (
                <div className="flex items-center gap-1.5 text-sm text-gray-500 mb-2 px-1">
                  <button
                    type="button"
                    className="hover:text-cyan-400 transition-colors truncate max-w-[200px]"
                    onClick={() => handleProjectSelect(selectedProject.parent_project_id!)}
                  >
                    {selectedParentTitle}
                  </button>
                  <span className="text-gray-600">›</span>
                  <span className="text-gray-400 truncate">{selectedProject.title}</span>
                </div>
              )}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/views/ProjectsView.tsx
git commit -m "feat: integrate SubProjectsStrip and breadcrumb into ProjectsView"
```

---

### Task 8: ManageSubProjectsModal

**Files:**
- Create: `cortex-ui/src/features/projects/components/ManageSubProjectsModal.tsx`
- Modify: `cortex-ui/src/features/projects/views/ProjectsView.tsx` (wire up modal)

- [ ] **Step 1: Create ManageSubProjectsModal**

Create `cortex-ui/src/features/projects/components/ManageSubProjectsModal.tsx`:

```tsx
import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../../ui/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../ui/primitives/dialog";
import { Input } from "../../ui/primitives/input";
import { cn } from "../../ui/primitives/styles";
import {
  useProjectChildren,
  useProjects,
  useSetParentProject,
} from "../hooks/useProjectQueries";
import type { Project } from "../types";

interface ManageSubProjectsModalProps {
  parentProjectId: string;
  parentTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ManageSubProjectsModal({
  parentProjectId,
  parentTitle,
  open,
  onOpenChange,
}: ManageSubProjectsModalProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const { data: children = [] } = useProjectChildren(parentProjectId);
  const { data: allProjects = [] } = useProjects();
  const setParentMutation = useSetParentProject();

  // Candidates: projects that can be added as children
  // - Not the parent itself
  // - Don't already have a parent (single-parent constraint)
  // - Not already a child of this parent
  const candidates = useMemo(() => {
    const childIds = new Set(children.map((c) => c.id));
    const query = searchQuery.toLowerCase().trim();
    return (allProjects as Project[]).filter((p) => {
      if (p.id === parentProjectId) return false;
      if (p.parent_project_id) return false;
      if (childIds.has(p.id)) return false;
      if (query && !p.title.toLowerCase().includes(query)) return false;
      return true;
    });
  }, [allProjects, parentProjectId, children, searchQuery]);

  const handleLink = (projectId: string) => {
    setParentMutation.mutate({
      projectId,
      parentProjectId: parentProjectId,
    });
  };

  const handleUnlink = (projectId: string) => {
    setParentMutation.mutate({
      projectId,
      parentProjectId: null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle
            className={cn(
              "text-lg font-bold",
              "bg-gradient-to-r from-cyan-400 to-blue-500",
              "text-transparent bg-clip-text",
            )}
          >
            Manage Sub-Projects — {parentTitle}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Current children */}
          <div>
            <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
              Current Sub-Projects ({children.length})
            </h4>
            {children.length === 0 ? (
              <p className="text-sm text-gray-600">No sub-projects linked.</p>
            ) : (
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {children.map((child) => (
                  <div
                    key={child.id}
                    className={cn(
                      "flex items-center justify-between px-3 py-2 rounded-lg",
                      "bg-white/5 border border-white/5",
                    )}
                  >
                    <span className="text-sm text-gray-300 truncate">
                      {child.title}
                    </span>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => handleUnlink(child.id)}
                      disabled={setParentMutation.isPending}
                      aria-label={`Unlink ${child.title}`}
                    >
                      <X className="w-3.5 h-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Search to add */}
          <div>
            <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
              Add Projects
            </h4>
            <div className="relative mb-2">
              <Search
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500"
                aria-hidden="true"
              />
              <Input
                placeholder="Search projects..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-8 text-sm"
              />
            </div>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {candidates.length === 0 ? (
                <p className="text-sm text-gray-600 py-2">
                  {searchQuery ? "No matching projects" : "No available projects"}
                </p>
              ) : (
                candidates.slice(0, 20).map((project) => (
                  <div
                    key={project.id}
                    className={cn(
                      "flex items-center justify-between px-3 py-2 rounded-lg",
                      "hover:bg-white/5 transition-colors cursor-pointer",
                    )}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleLink(project.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleLink(project.id);
                      }
                    }}
                  >
                    <span className="text-sm text-gray-300 truncate">
                      {project.title}
                    </span>
                    <span className="text-[10px] text-cyan-500 shrink-0 ml-2">
                      + Add
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Wire ManageSubProjectsModal into ProjectsView**

In `cortex-ui/src/features/projects/views/ProjectsView.tsx`:

Add import:
```typescript
import { ManageSubProjectsModal } from "../components/ManageSubProjectsModal";
```

Add the modal at the bottom of the component, alongside other modals:
```tsx
      {selectedProject && (
        <ManageSubProjectsModal
          parentProjectId={selectedProject.id}
          parentTitle={selectedProject.title}
          open={isManageSubProjectsOpen}
          onOpenChange={setIsManageSubProjectsOpen}
        />
      )}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects"
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/projects/components/ManageSubProjectsModal.tsx cortex-ui/src/features/projects/views/ProjectsView.tsx
git commit -m "feat: add ManageSubProjectsModal for linking/unlinking children"
```

---

### Task 9: Parent Project dropdown on NewProjectModal

**Files:**
- Modify: `cortex-ui/src/features/projects/components/NewProjectModal.tsx`

- [ ] **Step 1: Add Parent Project dropdown to NewProjectModal**

In `cortex-ui/src/features/projects/components/NewProjectModal.tsx`:

Add imports:
```typescript
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/primitives/select";
import { useProjects } from "../hooks/useProjectQueries";
import type { Project } from "../types";
```

Inside the component, add the projects query:
```typescript
const { data: allProjects = [] } = useProjects();
```

Compute eligible parents (projects that don't already have a parent — single-level constraint):
```typescript
const eligibleParents = (allProjects as Project[]).filter(
  (p) => !p.parent_project_id,
);
```

Add a "Parent Project" field in the form, after the description textarea section:
```tsx
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Parent Project
              </label>
              <Select
                value={formData.parent_project_id ?? "__none__"}
                onValueChange={(val) =>
                  setFormData((prev) => ({
                    ...prev,
                    parent_project_id: val === "__none__" ? undefined : val,
                  }))
                }
              >
                <SelectTrigger color="cyan" className="w-full">
                  <SelectValue placeholder="None (standalone)" />
                </SelectTrigger>
                <SelectContent color="cyan">
                  <SelectItem value="__none__" color="cyan">
                    None (standalone)
                  </SelectItem>
                  {eligibleParents.map((p) => (
                    <SelectItem key={p.id} value={p.id} color="cyan">
                      {p.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
```

Update `handleClose` and the `onSuccess` callback to reset `parent_project_id`:
```typescript
setFormData({ title: "", description: "", parent_project_id: undefined });
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/components/NewProjectModal.tsx
git commit -m "feat: add Parent Project dropdown to NewProjectModal"
```

---

### Task 10: Final verification and cleanup

- [ ] **Step 1: Run full TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit
```

Expected: No new errors in `src/features/projects`.

- [ ] **Step 2: Run Biome on features directory**

```bash
cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npm run biome:fix
```

Fix any formatting issues.

- [ ] **Step 3: Run backend linter**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run ruff check src/server/api_routes/projects_api.py src/server/services/projects/project_service.py --fix
```

- [ ] **Step 4: Run backend tests**

```bash
cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/api_routes/test_project_children.py -v
```

Expected: All pass.

- [ ] **Step 5: Visual check in browser**

Start the dev servers and verify:
1. Parent projects show folder-tree icon + sub-project count in grid/table
2. Child projects show breadcrumb link to parent
3. Selecting a parent project reveals the SubProjectsStrip with child cards
4. Clicking a child card in the strip selects that child
5. "Manage" button opens ManageSubProjectsModal
6. Linking/unlinking a project works
7. NewProjectModal shows Parent Project dropdown
8. Breadcrumb appears in detail area for child projects

- [ ] **Step 6: Final commit if any lint/format fixes**

```bash
git add -u
git commit -m "chore: lint and format fixes for sub-project navigation"
```

---

## Propagation Steps

After all changes:
- **Backend**: Restart Docker: `docker compose restart cortex-server`
- **Frontend**: Auto-reloads if `npm run dev` is running
