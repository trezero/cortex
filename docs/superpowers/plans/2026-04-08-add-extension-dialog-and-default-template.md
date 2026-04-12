# Add Extension Dialog & Default Extension Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `+ Extension` button in the Project Extensions tab that opens a multi-select dialog for linking extensions to a project, and add a Default Extensions section in Settings that lets users mark which extensions are installed on every new Archon-connected application.

**Architecture:** Linking an extension to a project appends the project UUID to the extension's existing `skill_groups` TEXT[] column (the mechanism `list_extensions_for_project` already filters on). A new `is_default BOOLEAN` column on `archon_extensions` powers the Settings template. Both surfaces share the same frontend service and query hooks with new methods added alongside existing ones.

**Tech Stack:** Python 3.12, FastAPI, Supabase (PostgreSQL), React 18, TypeScript, TanStack Query v5, Tailwind, Radix UI Dialog primitives

---

## File Structure

### Backend — Files to Modify / Create

| File | Responsibility |
|---|---|
| `migration/0.1.0/035_add_is_default_to_extensions.sql` | CREATE — add `is_default` column |
| `python/src/server/services/extensions/extension_service.py` | MODIFY — add `link_extension_to_project`, `unlink_extension_from_project`, `set_extension_default`; add `is_default` to select fields |
| `python/src/server/api_routes/extensions_api.py` | MODIFY — add link/unlink endpoints, add `PATCH /extensions/{id}/default`, add `is_default` to list response |
| `python/tests/server/services/extensions/test_extension_service.py` | MODIFY — add tests for new service methods |

### Frontend — Files to Create / Modify

| File | Responsibility |
|---|---|
| `archon-ui-main/src/features/projects/extensions/types/index.ts` | MODIFY — add `is_default` to `Extension` |
| `archon-ui-main/src/features/projects/extensions/services/extensionService.ts` | MODIFY — add `linkExtension`, `unlinkExtension`, `setExtensionDefault` |
| `archon-ui-main/src/features/projects/extensions/hooks/useExtensionQueries.ts` | MODIFY — add `useLinkExtensions`, `useUnlinkExtension`, `useSetExtensionDefault` |
| `archon-ui-main/src/features/projects/extensions/components/AddExtensionDialog.tsx` | CREATE — multi-select dialog |
| `archon-ui-main/src/features/projects/extensions/ExtensionsTab.tsx` | MODIFY — add `+ Extension` button and dialog |
| `archon-ui-main/src/components/settings/DefaultExtensionsSection.tsx` | CREATE — settings section with per-extension toggles |
| `archon-ui-main/src/pages/SettingsPage.tsx` | MODIFY — import and render DefaultExtensionsSection |

---

## Task 1: DB Migration — Add `is_default` Column

**Files:**
- Create: `migration/0.1.0/035_add_is_default_to_extensions.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- 035_add_is_default_to_extensions.sql
-- Adds is_default flag to archon_extensions for the default template feature.
-- Extensions where is_default = true are installed on every new Archon-connected application.

ALTER TABLE archon_extensions
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false;
```

- [ ] **Step 2: Run the migration against Supabase**

Open the Supabase SQL editor (or psql) and execute the file content. Verify:

```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'archon_extensions' AND column_name = 'is_default';
```

Expected: one row, `data_type = boolean`, `column_default = false`.

- [ ] **Step 3: Commit**

```bash
git add migration/0.1.0/035_add_is_default_to_extensions.sql
git commit -m "feat: add is_default column to archon_extensions"
```

---

## Task 2: Backend Service — link/unlink/set_default Methods

**Files:**
- Modify: `python/src/server/services/extensions/extension_service.py`
- Test: `python/tests/server/services/extensions/test_extension_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_extension_service.py` after the existing test classes:

```python
# ── link_extension_to_project ──────────────────────────────────────────────


class TestLinkExtensionToProject:
    def test_appends_project_id_to_skill_groups(self, mock_supabase):
        """link_extension_to_project should add project_id to skill_groups."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {
            "id": extension_id,
            "name": "my-skill",
            "skill_groups": ["proj-uuid-0"],
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        updated = {**existing, "skill_groups": ["proj-uuid-0", project_id]}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        update_builder = MagicMock()
        update_builder.update.return_value = update_builder
        update_builder.eq.return_value = update_builder
        update_builder.execute.return_value = MagicMock(data=[updated])

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_builder
            return update_builder

        mock_supabase.table.side_effect = _table
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.link_extension_to_project(extension_id, project_id)

        assert project_id in result["skill_groups"]
        update_builder.update.assert_called_once()
        update_call_kwargs = update_builder.update.call_args[0][0]
        assert project_id in update_call_kwargs["skill_groups"]

    def test_idempotent_when_already_linked(self, mock_supabase):
        """link_extension_to_project should return early if project_id already present."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {
            "id": extension_id,
            "name": "my-skill",
            "skill_groups": [project_id],
        }

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        mock_supabase.table.return_value = get_builder
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.link_extension_to_project(extension_id, project_id)

        assert result == existing
        # update should NOT be called
        get_builder.update.assert_not_called()

    def test_raises_value_error_when_extension_not_found(self, mock_supabase):
        """link_extension_to_project should raise ValueError for unknown extension_id."""
        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[])

        mock_supabase.table.return_value = get_builder
        service = ExtensionService(supabase_client=mock_supabase)

        with pytest.raises(ValueError, match="not found"):
            service.link_extension_to_project("bad-id", "proj-1")


# ── unlink_extension_from_project ─────────────────────────────────────────


class TestUnlinkExtensionFromProject:
    def test_removes_project_id_from_skill_groups(self, mock_supabase):
        """unlink_extension_from_project should remove project_id from skill_groups."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {
            "id": extension_id,
            "name": "my-skill",
            "skill_groups": ["proj-uuid-0", project_id],
        }
        updated = {**existing, "skill_groups": ["proj-uuid-0"]}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        update_builder = MagicMock()
        update_builder.update.return_value = update_builder
        update_builder.eq.return_value = update_builder
        update_builder.execute.return_value = MagicMock(data=[updated])

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return get_builder
            return update_builder

        mock_supabase.table.side_effect = _table
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.unlink_extension_from_project(extension_id, project_id)

        assert project_id not in result["skill_groups"]

    def test_idempotent_when_not_linked(self, mock_supabase):
        """unlink_extension_from_project should return early if project_id not present."""
        extension_id = "ext-uuid-1"
        project_id = "proj-uuid-1"

        existing = {"id": extension_id, "name": "my-skill", "skill_groups": []}

        get_builder = MagicMock()
        get_builder.select.return_value = get_builder
        get_builder.eq.return_value = get_builder
        get_builder.execute.return_value = MagicMock(data=[existing])

        mock_supabase.table.return_value = get_builder
        service = ExtensionService(supabase_client=mock_supabase)
        result = service.unlink_extension_from_project(extension_id, project_id)

        assert result == existing
        get_builder.update.assert_not_called()


# ── set_extension_default ─────────────────────────────────────────────────


class TestSetExtensionDefault:
    def test_sets_is_default_true(self, mock_supabase):
        """set_extension_default should update is_default on the extension."""
        extension_id = "ext-uuid-1"
        updated = {"id": extension_id, "name": "my-skill", "is_default": True}

        builder = MagicMock()
        for method in ("update", "eq"):
            getattr(builder, method).return_value = builder
        builder.execute.return_value = MagicMock(data=[updated])
        mock_supabase.table.return_value = builder

        service = ExtensionService(supabase_client=mock_supabase)
        result = service.set_extension_default(extension_id, is_default=True)

        assert result["is_default"] is True
        update_kwargs = builder.update.call_args[0][0]
        assert update_kwargs["is_default"] is True

    def test_raises_runtime_error_when_extension_not_found(self, mock_supabase):
        """set_extension_default should raise RuntimeError if update returns no data."""
        builder = MagicMock()
        for method in ("update", "eq"):
            getattr(builder, method).return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value = builder

        service = ExtensionService(supabase_client=mock_supabase)
        with pytest.raises(RuntimeError, match="Failed to update"):
            service.set_extension_default("bad-id", is_default=True)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/winadmin/projects/Trinity/archon && uv run pytest python/tests/server/services/extensions/test_extension_service.py::TestLinkExtensionToProject python/tests/server/services/extensions/test_extension_service.py::TestUnlinkExtensionFromProject python/tests/server/services/extensions/test_extension_service.py::TestSetExtensionDefault -v 2>&1 | tail -20
```

Expected: `ERROR` — `AttributeError` or `FAILED` because the methods don't exist yet.

- [ ] **Step 3: Implement the three new methods in `extension_service.py`**

Add after the `get_project_extensions` method (end of the class):

```python
def link_extension_to_project(self, extension_id: str, project_id: str) -> dict[str, Any]:
    """Append project_id to an extension's skill_groups, making it part of that project.

    Idempotent — if project_id is already in skill_groups, returns the extension unchanged.

    Raises:
        ValueError: If the extension_id does not exist.
        RuntimeError: If the database update fails.
    """
    ext = self.get_extension(extension_id)
    if ext is None:
        raise ValueError(f"Extension '{extension_id}' not found")

    skill_groups: list[str] = ext.get("skill_groups") or []
    if project_id in skill_groups:
        return ext

    updated_groups = [*skill_groups, project_id]
    response = (
        self.supabase_client.table(EXTENSIONS_TABLE)
        .update({"skill_groups": updated_groups, "updated_at": datetime.now(UTC).isoformat()})
        .eq("id", extension_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError(f"Failed to link extension '{extension_id}' to project '{project_id}'")

    logger.info(f"Extension linked to project: {extension_id} -> {project_id}")
    return response.data[0]

def unlink_extension_from_project(self, extension_id: str, project_id: str) -> dict[str, Any]:
    """Remove project_id from an extension's skill_groups.

    Idempotent — if project_id is not in skill_groups, returns the extension unchanged.

    Raises:
        ValueError: If the extension_id does not exist.
        RuntimeError: If the database update fails.
    """
    ext = self.get_extension(extension_id)
    if ext is None:
        raise ValueError(f"Extension '{extension_id}' not found")

    skill_groups: list[str] = ext.get("skill_groups") or []
    if project_id not in skill_groups:
        return ext

    updated_groups = [g for g in skill_groups if g != project_id]
    response = (
        self.supabase_client.table(EXTENSIONS_TABLE)
        .update({"skill_groups": updated_groups, "updated_at": datetime.now(UTC).isoformat()})
        .eq("id", extension_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError(f"Failed to unlink extension '{extension_id}' from project '{project_id}'")

    logger.info(f"Extension unlinked from project: {extension_id} -> {project_id}")
    return response.data[0]

def set_extension_default(self, extension_id: str, is_default: bool) -> dict[str, Any]:
    """Set or clear the is_default flag on an extension.

    Extensions with is_default = True are installed on every new Archon-connected application.

    Raises:
        RuntimeError: If the extension_id does not exist or update fails.
    """
    response = (
        self.supabase_client.table(EXTENSIONS_TABLE)
        .update({"is_default": is_default, "updated_at": datetime.now(UTC).isoformat()})
        .eq("id", extension_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError(f"Failed to update is_default for extension '{extension_id}'")

    logger.info(f"Extension is_default set to {is_default}: {extension_id}")
    return response.data[0]
```

- [ ] **Step 4: Update the `list_extensions` and `list_extensions_for_project` select strings to include `is_default`**

In both methods find the `.select(...)` call and add `is_default` to the field list:

```python
# In list_extensions() — change:
.select("id, name, display_name, description, current_version, content_hash, type, skill_groups, is_required, is_validated, tags, created_by, created_at, updated_at")
# To:
.select("id, name, display_name, description, current_version, content_hash, type, skill_groups, is_required, is_default, is_validated, tags, created_by, created_at, updated_at")

# In list_extensions_for_project() — same change to BOTH branches (include_content=True uses select("*") which already includes is_default; only the False branch needs updating):
.select("id, name, display_name, description, current_version, content_hash, type, skill_groups, is_required, is_default, is_validated, tags, created_by, created_at, updated_at")
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /home/winadmin/projects/Trinity/archon && uv run pytest python/tests/server/services/extensions/test_extension_service.py -v 2>&1 | tail -30
```

Expected: ALL PASS (new and existing tests).

- [ ] **Step 6: Commit**

```bash
git add python/src/server/services/extensions/extension_service.py python/tests/server/services/extensions/test_extension_service.py
git commit -m "feat: add link/unlink project and set_default methods to ExtensionService"
```

---

## Task 3: Backend API — link/unlink Endpoints and `/default` Patch

**Files:**
- Modify: `python/src/server/api_routes/extensions_api.py`

- [ ] **Step 1: Add the `SetExtensionDefaultRequest` model**

Near the top of `extensions_api.py`, alongside the other `BaseModel` request classes, add:

```python
class SetExtensionDefaultRequest(BaseModel):
    is_default: bool
```

- [ ] **Step 2: Add the `PATCH /extensions/{extension_id}/default` endpoint**

Add this block **before** the `@router.get("/projects/{project_id}/extensions")` route (keep the static `/default` route before dynamic `/{extension_id}` sub-paths to avoid any future conflict):

```python
@router.patch("/extensions/{extension_id}/default")
async def set_extension_default(extension_id: str, request: SetExtensionDefaultRequest):
    """Toggle is_default on a single extension.

    Extensions with is_default=True are included in the default template installed
    on every new Archon-connected application.
    """
    try:
        logfire.info(f"Setting is_default | extension_id={extension_id} | is_default={request.is_default}")
        extension_service = ExtensionService()
        extension = extension_service.set_extension_default(extension_id, request.is_default)
        return extension
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail={"error": str(e)}) from e
    except Exception as e:
        logfire.error(f"Failed to set is_default | extension_id={extension_id} | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
```

- [ ] **Step 3: Add the link/unlink project endpoints**

Add these two routes inside the `# ── Project-scoped extensions ──` section, after the existing `unlink_system_from_project` endpoint:

```python
@router.post("/projects/{project_id}/extensions/{extension_id}/link")
async def link_extension_to_project(project_id: str, extension_id: str):
    """Associate an extension with a project by adding project_id to its skill_groups.

    Idempotent — calling it again when already linked is a no-op.
    """
    try:
        logfire.info(f"Linking extension to project | project_id={project_id} | extension_id={extension_id}")
        extension_service = ExtensionService()
        extension = extension_service.link_extension_to_project(extension_id, project_id)
        return extension
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": str(e)}) from e
    except Exception as e:
        logfire.error(
            f"Failed to link extension | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.delete("/projects/{project_id}/extensions/{extension_id}/link")
async def unlink_extension_from_project_route(project_id: str, extension_id: str):
    """Remove an extension from a project by removing project_id from its skill_groups.

    Idempotent — calling it when not linked is a no-op.
    """
    try:
        logfire.info(f"Unlinking extension from project | project_id={project_id} | extension_id={extension_id}")
        extension_service = ExtensionService()
        extension = extension_service.unlink_extension_from_project(extension_id, project_id)
        return extension
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": str(e)}) from e
    except Exception as e:
        logfire.error(
            f"Failed to unlink extension | project_id={project_id} | extension_id={extension_id} | error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
```

- [ ] **Step 4: Verify the backend starts and routes appear**

```bash
cd /home/winadmin/projects/Trinity/archon && uv run python -c "
from src.server.api_routes.extensions_api import router
routes = [r.path for r in router.routes]
assert any('link' in r for r in routes), 'link routes missing'
assert any('default' in r for r in routes), 'default route missing'
print('Routes OK:', [r for r in routes if 'link' in r or 'default' in r])
"
```

Expected: prints the 3 new route paths.

- [ ] **Step 5: Commit**

```bash
git add python/src/server/api_routes/extensions_api.py
git commit -m "feat: add link/unlink project endpoints and PATCH default to extensions API"
```

---

## Task 4: Frontend Types, Service Methods, Query Hooks

**Files:**
- Modify: `archon-ui-main/src/features/projects/extensions/types/index.ts`
- Modify: `archon-ui-main/src/features/projects/extensions/services/extensionService.ts`
- Modify: `archon-ui-main/src/features/projects/extensions/hooks/useExtensionQueries.ts`

- [ ] **Step 1: Add `is_default` to the `Extension` interface in `types/index.ts`**

In the `Extension` interface, add `is_default` after `is_required`:

```typescript
export interface Extension {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content?: string;
  content_hash: string;
  current_version: number;
  is_required: boolean;
  is_default: boolean;
  is_validated: boolean;
  tags: string[];
  type: "skill" | "plugin" | "command";
  plugin_manifest?: PluginManifest | CommandMetadata | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add service methods to `extensionService.ts`**

Add three new methods to the `extensionService` object:

```typescript
  async linkExtension(projectId: string, extensionId: string): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/extensions/${extensionId}/link`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(`Failed to link extension: ${response.statusText}`);
  },

  async unlinkExtension(projectId: string, extensionId: string): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/extensions/${extensionId}/link`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to unlink extension: ${response.statusText}`);
  },

  async setExtensionDefault(extensionId: string, isDefault: boolean): Promise<void> {
    const response = await fetch(`/api/extensions/${extensionId}/default`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_default: isDefault }),
    });
    if (!response.ok) throw new Error(`Failed to update extension default: ${response.statusText}`);
  },
```

- [ ] **Step 3: Add query hooks to `useExtensionQueries.ts`**

Add three new hooks after `useUnlinkSystem`:

```typescript
export function useLinkExtensions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, extensionIds }: { projectId: string; extensionIds: string[] }) =>
      Promise.all(extensionIds.map((id) => extensionService.linkExtension(projectId, id))),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useUnlinkExtension() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, extensionId }: { projectId: string; extensionId: string }) =>
      extensionService.unlinkExtension(projectId, extensionId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.byProject(variables.projectId) });
    },
  });
}

export function useSetExtensionDefault() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ extensionId, isDefault }: { extensionId: string; isDefault: boolean }) =>
      extensionService.setExtensionDefault(extensionId, isDefault),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.lists() });
    },
  });
}
```

- [ ] **Step 4: Run TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npx tsc --noEmit 2>&1 | grep "extensions" | head -20
```

Expected: no errors related to the extensions feature files.

- [ ] **Step 5: Commit**

```bash
git add archon-ui-main/src/features/projects/extensions/types/index.ts \
        archon-ui-main/src/features/projects/extensions/services/extensionService.ts \
        archon-ui-main/src/features/projects/extensions/hooks/useExtensionQueries.ts
git commit -m "feat: add link/unlink/setDefault service methods and query hooks for extensions"
```

---

## Task 5: Frontend — AddExtensionDialog Component

**Files:**
- Create: `archon-ui-main/src/features/projects/extensions/components/AddExtensionDialog.tsx`

The dialog uses the same `Dialog` primitives as `AddKnowledgeDialog`. It fetches all Archon extensions, filters out those already linked to the project, lets the user multi-select, and calls `useLinkExtensions` on submit.

- [ ] **Step 1: Create the component**

```tsx
import { useState, useMemo } from "react";
import { Plus, Search } from "lucide-react";
import { useToast } from "@/features/shared/hooks/useToast";
import { Button, Input } from "@/features/ui/primitives";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/features/ui/primitives/dialog";
import { useAllExtensions, useLinkExtensions } from "../hooks/useExtensionQueries";
import type { Extension } from "../types";

interface AddExtensionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  linkedExtensions: Extension[];
}

const TYPE_LABELS: Record<string, string> = {
  skill: "Skills",
  command: "Commands",
  plugin: "Plugins",
};

const TYPE_COLORS: Record<string, string> = {
  skill: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  command: "bg-violet-500/20 text-violet-400 border-violet-500/30",
  plugin: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

export function AddExtensionDialog({ open, onOpenChange, projectId, linkedExtensions }: AddExtensionDialogProps) {
  const { showToast } = useToast();
  const { data: allExtData } = useAllExtensions();
  const linkExtensions = useLinkExtensions();

  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const linkedIds = useMemo(() => new Set(linkedExtensions.map((e) => e.id)), [linkedExtensions]);

  const available = useMemo(() => {
    const all = allExtData?.extensions ?? [];
    const unlinked = all.filter((e) => !linkedIds.has(e.id));
    if (!search.trim()) return unlinked;
    const q = search.toLowerCase();
    return unlinked.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        (e.display_name ?? "").toLowerCase().includes(q) ||
        (e.description ?? "").toLowerCase().includes(q),
    );
  }, [allExtData, linkedIds, search]);

  const grouped = useMemo(() => {
    const groups: Record<string, Extension[]> = {};
    for (const ext of available) {
      const key = ext.type ?? "skill";
      if (!groups[key]) groups[key] = [];
      groups[key].push(ext);
    }
    return groups;
  }, [available]);

  const typeOrder = ["skill", "command", "plugin"];

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === available.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(available.map((e) => e.id)));
    }
  };

  const handleAdd = async () => {
    if (selectedIds.size === 0) return;
    try {
      await linkExtensions.mutateAsync({ projectId, extensionIds: Array.from(selectedIds) });
      showToast(`Added ${selectedIds.size} extension${selectedIds.size > 1 ? "s" : ""} to project`, "success");
      setSelectedIds(new Set());
      setSearch("");
      onOpenChange(false);
    } catch {
      showToast("Failed to add extensions", "error");
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setSelectedIds(new Set());
      setSearch("");
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add Extensions</DialogTitle>
          <DialogDescription>
            Select extensions to add to this project. Only unlinked extensions are shown.
          </DialogDescription>
        </DialogHeader>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <Input
            placeholder="Search extensions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Select all toggle */}
        {available.length > 0 && (
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <button
              type="button"
              onClick={toggleAll}
              className="hover:text-white transition-colors"
            >
              {selectedIds.size === available.length ? "Deselect all" : "Select all"}
            </button>
            <span>{selectedIds.size} selected</span>
          </div>
        )}

        {/* Extension list grouped by type */}
        <div className="max-h-[360px] overflow-y-auto space-y-4 pr-1">
          {available.length === 0 && (
            <p className="text-sm text-zinc-500 text-center py-8">
              {search ? "No extensions match your search." : "All extensions are already linked to this project."}
            </p>
          )}

          {typeOrder.filter((t) => grouped[t]?.length).map((type) => (
            <div key={type}>
              <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                {TYPE_LABELS[type] ?? type}
              </h4>
              <div className="space-y-1">
                {grouped[type].map((ext) => (
                  <button
                    key={ext.id}
                    type="button"
                    onClick={() => toggleSelected(ext.id)}
                    className={`w-full flex items-start gap-3 p-2.5 rounded-lg border text-left transition-colors ${
                      selectedIds.has(ext.id)
                        ? "border-cyan-500/50 bg-cyan-500/10"
                        : "border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]"
                    }`}
                  >
                    <div
                      className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded border flex items-center justify-center ${
                        selectedIds.has(ext.id)
                          ? "bg-cyan-500 border-cyan-500"
                          : "border-zinc-600"
                      }`}
                    >
                      {selectedIds.has(ext.id) && (
                        <svg className="w-2.5 h-2.5 text-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white truncate">
                          {ext.display_name || ext.name}
                        </span>
                        <span
                          className={`flex-shrink-0 px-1.5 py-0.5 text-[10px] rounded border ${
                            TYPE_COLORS[ext.type] ?? "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
                          }`}
                        >
                          {ext.type}
                        </span>
                      </div>
                      {ext.description && (
                        <p className="text-xs text-zinc-400 mt-0.5 truncate">{ext.description}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-2 border-t border-white/10">
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleAdd}
            disabled={selectedIds.size === 0 || linkExtensions.isPending}
          >
            <Plus className="w-4 h-4 mr-1.5" />
            {linkExtensions.isPending
              ? "Adding..."
              : `Add ${selectedIds.size > 0 ? selectedIds.size + " " : ""}Extension${selectedIds.size !== 1 ? "s" : ""}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Run TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npx tsc --noEmit 2>&1 | grep "AddExtensionDialog" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add archon-ui-main/src/features/projects/extensions/components/AddExtensionDialog.tsx
git commit -m "feat: add AddExtensionDialog component for linking extensions to a project"
```

---

## Task 6: Frontend — Wire `+ Extension` Button into ExtensionsTab

**Files:**
- Modify: `archon-ui-main/src/features/projects/extensions/ExtensionsTab.tsx`

The current tab renders an early-return empty state when `systems.length === 0`. We restructure so the `+ Extension` button header is always visible after data loads, and the empty state / systems layout renders below it.

- [ ] **Step 1: Rewrite `ExtensionsTab.tsx`**

```tsx
import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/features/ui/primitives";
import { SystemCard } from "./components/SystemCard";
import { SystemExtensionList } from "./components/SystemExtensionList";
import { AddExtensionDialog } from "./components/AddExtensionDialog";
import { useInstallExtension, useProjectExtensions, useRemoveExtension, useUnlinkSystem } from "./hooks/useExtensionQueries";

interface ExtensionsTabProps {
  projectId: string;
}

export function ExtensionsTab({ projectId }: ExtensionsTabProps) {
  const { data, isLoading, error } = useProjectExtensions(projectId);
  const installExtension = useInstallExtension();
  const removeExtension = useRemoveExtension();
  const unlinkSystem = useUnlinkSystem();
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  if (isLoading) {
    return <div className="flex items-center justify-center py-12 text-zinc-400">Loading extensions...</div>;
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12 text-red-400">
        Failed to load extensions: {error.message}
      </div>
    );
  }

  const systems = data?.systems ?? [];
  const allExtensions = data?.all_extensions ?? [];
  const selectedSystem = systems.find((s) => s.id === selectedSystemId) ?? systems[0];

  const handleInstall = (extensionId: string) => {
    if (!selectedSystem) return;
    installExtension.mutate({ projectId, extensionId, systemIds: [selectedSystem.id] });
  };

  const handleRemove = (extensionId: string) => {
    if (!selectedSystem) return;
    removeExtension.mutate({ projectId, extensionId, systemIds: [selectedSystem.id] });
  };

  const handleUnlink = (systemId: string) => {
    unlinkSystem.mutate({ projectId, systemId });
    if (selectedSystemId === systemId) setSelectedSystemId(null);
  };

  return (
    <div className="space-y-4">
      {/* Header row with + Extension button */}
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddDialogOpen(true)}>
          <Plus className="w-3.5 h-3.5 mr-1.5" />
          Extension
        </Button>
      </div>

      {systems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-zinc-400 space-y-2">
          <p className="text-sm">No systems registered to this project yet.</p>
          <p className="text-xs text-zinc-500">
            Systems are registered when they connect via the Archon MCP server and run an extension sync.
          </p>
          {allExtensions.length > 0 && (
            <p className="text-xs text-zinc-500">
              {allExtensions.length} extension{allExtensions.length !== 1 ? "s" : ""} linked to this project.
            </p>
          )}
        </div>
      ) : (
        <div className="flex gap-4 h-full">
          {/* Systems list */}
          <div className="w-64 flex-shrink-0 space-y-2">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Systems</h3>
            {systems.map((system) => (
              <SystemCard
                key={system.id}
                system={system}
                isSelected={system.id === (selectedSystem?.id ?? null)}
                onClick={() => setSelectedSystemId(system.id)}
                onUnlink={handleUnlink}
              />
            ))}
          </div>

          {/* Detail panel */}
          <div className="flex-1 min-w-0">
            {selectedSystem && (
              <div className="space-y-4">
                <div className="border-b border-white/10 pb-3">
                  <h3 className="text-lg font-medium text-white">{selectedSystem.name}</h3>
                  <div className="flex gap-4 mt-1 text-xs text-zinc-400">
                    {selectedSystem.hostname && <span>Host: {selectedSystem.hostname}</span>}
                    {selectedSystem.os && <span>OS: {selectedSystem.os}</span>}
                    <span>Last seen: {new Date(selectedSystem.last_seen_at).toLocaleString()}</span>
                  </div>
                </div>
                <SystemExtensionList
                  systemExtensions={selectedSystem.extensions}
                  allExtensions={allExtensions}
                  onInstall={handleInstall}
                  onRemove={handleRemove}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <AddExtensionDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        projectId={projectId}
        linkedExtensions={allExtensions}
      />
    </div>
  );
}
```

- [ ] **Step 2: Run TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npx tsc --noEmit 2>&1 | grep "ExtensionsTab" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add archon-ui-main/src/features/projects/extensions/ExtensionsTab.tsx
git commit -m "feat: add + Extension button and AddExtensionDialog to ExtensionsTab"
```

---

## Task 7: Frontend — DefaultExtensionsSection Settings Component

**Files:**
- Create: `archon-ui-main/src/components/settings/DefaultExtensionsSection.tsx`

This component renders all Archon extensions grouped by type, each with a toggle switch. Toggling calls `useSetExtensionDefault`. It is designed to slot inside a `CollapsibleSettingsCard`.

- [ ] **Step 1: Create `DefaultExtensionsSection.tsx`**

```tsx
import { useAllExtensions, useSetExtensionDefault } from "@/features/projects/extensions/hooks/useExtensionQueries";
import type { Extension } from "@/features/projects/extensions/types";

const TYPE_LABELS: Record<string, string> = {
  skill: "Skills",
  command: "Commands",
  plugin: "Plugins",
};

const TYPE_COLORS: Record<string, string> = {
  skill: "text-cyan-400",
  command: "text-violet-400",
  plugin: "text-amber-400",
};

const TYPE_ORDER = ["skill", "command", "plugin"];

function ExtensionRow({ ext }: { ext: Extension }) {
  const setDefault = useSetExtensionDefault();

  const handleToggle = () => {
    setDefault.mutate({ extensionId: ext.id, isDefault: !ext.is_default });
  };

  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-white/5 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{ext.display_name || ext.name}</p>
        {ext.description && (
          <p className="text-xs text-zinc-400 mt-0.5 truncate">{ext.description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={ext.is_default}
        onClick={handleToggle}
        disabled={setDefault.isPending}
        className={`flex-shrink-0 mt-0.5 relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 disabled:opacity-50 ${
          ext.is_default ? "bg-cyan-500" : "bg-zinc-700"
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
            ext.is_default ? "translate-x-4" : "translate-x-1"
          }`}
        />
      </button>
    </div>
  );
}

export function DefaultExtensionsSection() {
  const { data, isLoading, error } = useAllExtensions();

  if (isLoading) {
    return <p className="text-sm text-zinc-400">Loading extensions...</p>;
  }

  if (error) {
    return <p className="text-sm text-red-400">Failed to load extensions.</p>;
  }

  const extensions = data?.extensions ?? [];

  if (extensions.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        No extensions found. Extensions are synced from your Archon registry.
      </p>
    );
  }

  const grouped: Record<string, Extension[]> = {};
  for (const ext of extensions) {
    const key = ext.type ?? "skill";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(ext);
  }

  const defaultCount = extensions.filter((e) => e.is_default).length;

  return (
    <div className="space-y-5">
      <p className="text-sm text-zinc-400">
        Extensions marked as default are installed on every new application registered via{" "}
        <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded">/archon-setup</code>.{" "}
        <span className="text-zinc-500">{defaultCount} of {extensions.length} selected.</span>
      </p>

      {TYPE_ORDER.filter((t) => grouped[t]?.length).map((type) => (
        <div key={type}>
          <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${TYPE_COLORS[type] ?? "text-zinc-400"}`}>
            {TYPE_LABELS[type] ?? type} ({grouped[type].length})
          </h4>
          <div>
            {grouped[type].map((ext) => (
              <ExtensionRow key={ext.id} ext={ext} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Run TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npx tsc --noEmit 2>&1 | grep "DefaultExtensionsSection" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add archon-ui-main/src/components/settings/DefaultExtensionsSection.tsx
git commit -m "feat: add DefaultExtensionsSection component for settings"
```

---

## Task 8: Frontend — Wire DefaultExtensionsSection into SettingsPage

**Files:**
- Modify: `archon-ui-main/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add the import**

At the top of `SettingsPage.tsx`, alongside the other settings component imports, add:

```typescript
import { DefaultExtensionsSection } from "../components/settings/DefaultExtensionsSection";
```

Also add `Package` to the lucide-react imports:

```typescript
import {
  Loader, Settings, ChevronDown, ChevronUp, Palette, Key, Brain,
  Code, FileCode, Bug, Info, Database, User, Cpu, Package,
} from "lucide-react";
```

- [ ] **Step 2: Add the section in the Left Column, after the IDE Global Rules block**

Find the closing `</div>` of the Left Column (`{/* Left Column */}`). Add the new section inside the `projectsEnabled` conditional or standalone — the Default Extensions feature is most useful when Projects is enabled, so gate it the same way:

```tsx
          {projectsEnabled && (
            <motion.div variants={itemVariants}>
              <CollapsibleSettingsCard
                title="Default Extensions"
                icon={Package}
                accentColor="cyan"
                storageKey="default-extensions"
                defaultExpanded={false}
              >
                <DefaultExtensionsSection />
              </CollapsibleSettingsCard>
            </motion.div>
          )}
```

Place this block immediately after the existing `{projectsEnabled && ... IDEGlobalRules ...}` block, before the closing `</div>` of the left column.

- [ ] **Step 3: Run TypeScript check**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npx tsc --noEmit 2>&1 | grep "SettingsPage" | head -10
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add archon-ui-main/src/pages/SettingsPage.tsx
git commit -m "feat: add Default Extensions section to SettingsPage"
```

---

## Task 9: Run Full Test Suite and Biome Linter

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

```bash
cd /home/winadmin/projects/Trinity/archon && uv run pytest python/tests/ -v 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 2: Run backend linter**

```bash
cd /home/winadmin/projects/Trinity/archon && uv run ruff check python/src/ 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 3: Run frontend type check across entire project**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npx tsc --noEmit 2>&1 | head -40
```

Expected: no errors.

- [ ] **Step 4: Run Biome linter on features directory**

```bash
cd /home/winadmin/projects/Trinity/archon/archon-ui-main && npm run biome 2>&1 | tail -20
```

Expected: no errors or only pre-existing warnings.

- [ ] **Step 5: Manual end-to-end verification**

1. Restart the backend: `docker compose restart archon-server`
2. Open a project in the UI → Extensions tab → verify `+ Extension` button appears
3. Click `+ Extension` → verify dialog opens with extensions grouped by type
4. Select 1-2 extensions → click **Add** → verify they now appear in the Extensions tab
5. Open Settings → Default Extensions (expand) → verify all extensions listed with toggles
6. Toggle an extension on → verify the toggle persists after refresh (check via `curl -s "http://localhost:8181/api/extensions" | python -m json.tool | grep -A2 '"is_default": true'`)

---

## Propagation Steps

| What changed | How to propagate |
|---|---|
| Backend Python (services, API routes) | `docker compose restart archon-server` |
| DB migration (`is_default` column) | Run `migration/0.1.0/035_add_is_default_to_extensions.sql` against Supabase once |
| Frontend (new components, SettingsPage) | Auto-reloads if `npm run dev` is running; otherwise `npm run build` + refresh |
