# Cortex Feature Request: Multi-Project Ecosystem Support (v2.1)

> Revised based on two rounds of review feedback. v2 changes: dropped `group_id`, consolidated Features 2+4, added caching, addressed source-linking duality, added incremental sync, constrained hierarchy to single level. v2.1 changes: removed invalid CHECK constraint, added junction table backfill migration, added upsert implementation note for deterministic IDs, added cache invalidation for parent deletion.

## Context

When using Cortex to manage documentation for a **product family** (multiple related projects sharing common knowledge), several gaps emerge that require client-side workarounds. This document proposes first-class server-side support for multi-project ecosystems.

### Real-World Scenario

Our setup has 5 Cortex projects for one product family:

| Project | Purpose | Sources |
|---------|---------|---------|
| RecipeRaiders | Main app docs (51 files) | 1 source |
| reciperaiders-spa | Marketing site (2 files) | 1 source |
| reciperaiders-repdash | Admin dashboard (3 files) | 1 source |
| RecipeRaiders-Marketing | LinkedIn DM tool (1 file) | 1 source |
| RecipeRaiders Ecosystem | **Shared cross-project knowledge** (parent) | 1 source |

Every sub-project needs to search both its **own** docs and the **parent ecosystem** docs. Currently, this requires the client to:
1. Know two `project_id` values per sub-project (its own + the parent's)
2. Make two separate search calls and mentally merge results
3. Maintain a custom `cortex-global.json` state file mapping the ecosystem
4. Handle source_id instability across syncs

### Pre-existing Issue: Dual Source-Linking

Before proposing new features, there's an existing inconsistency to address. Sources are currently linked to projects via **two independent mechanisms**:

1. **Junction table** (`cortex_project_sources`): Used by `source_linking_service.py` and `project_service.py::get_project()` for display and management. Supports `notes` field distinguishing "technical" vs "business" sources.

2. **Metadata field** (`cortex_sources.metadata->>project_id`): Used by `_resolve_project_source_filter()` in `knowledge_api.py` for search scoping. Set during ingestion when `project_id` is passed to `manage_rag_source`.

These can desync: a source can be in the junction table but not have the metadata field set, or vice versa. The search path only sees mechanism #2.

**Recommendation**: Migrate `_resolve_project_source_filter()` to use the junction table as the canonical source. This is a prerequisite for the cascading search feature and eliminates a category of bugs. The metadata field can remain as a convenience/cache but should not be the authoritative link.

```python
# CURRENT (uses metadata field on cortex_sources):
project_sources = get_supabase_client().table("cortex_sources").select(
    "source_id"
).filter("metadata->>project_id", "eq", project_id).execute()

# PROPOSED (uses junction table — canonical):
project_sources = get_supabase_client().table("cortex_project_sources").select(
    "source_id"
).eq("project_id", project_id).execute()
```

---

## Feature 1: Project Hierarchy (Parent/Child)

### Problem
There is no way to express that projects are related. Each project is a flat, independent entity in `cortex_projects`. The client must track relationships externally.

### Design Decision: Hierarchy, Not Flat Groups

v1 proposed both `group_id` (flat grouping) and `parent_project_id` (hierarchy). These are redundant — if a project has a parent, the group is implicit (the parent and all its children). Having both creates drift risk where a project's `group_id` disagrees with its parent's group.

The **hierarchical model** is the right choice because:
- There is always a natural "parent" — the shared ecosystem project that holds common knowledge
- The parent/child relationship has clear semantics for search: "my sources + parent's sources"
- Group membership is derivable: siblings = all projects with the same `parent_project_id`
- Ecosystem-wide search = search with the parent's `project_id`

**Constraint: Single level only.** A parent cannot itself have a parent. This prevents arbitrarily deep hierarchies that would complicate the search resolution. Enforced via check constraint.

### Current Schema
```sql
CREATE TABLE cortex_projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  docs JSONB DEFAULT '[]'::jsonb,
  features JSONB DEFAULT '[]'::jsonb,
  data JSONB DEFAULT '[]'::jsonb,
  github_repo TEXT,
  pinned BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Proposed Changes

**Database** — Add one column with constraint:

```sql
ALTER TABLE cortex_projects
  ADD COLUMN parent_project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL;

-- Single-level constraint via trigger (CHECK constraints cannot reference other rows)
CREATE OR REPLACE FUNCTION enforce_single_level_hierarchy()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.parent_project_id IS NOT NULL THEN
    -- Check that the parent is not itself a child
    IF EXISTS (
      SELECT 1 FROM cortex_projects
      WHERE id = NEW.parent_project_id AND parent_project_id IS NOT NULL
    ) THEN
      RAISE EXCEPTION 'Cannot nest projects more than one level deep. Parent project % is already a child project.', NEW.parent_project_id;
    END IF;
    -- Check that this project doesn't already have children
    IF EXISTS (
      SELECT 1 FROM cortex_projects
      WHERE parent_project_id = NEW.id
    ) THEN
      RAISE EXCEPTION 'Cannot make project % a child — it already has child projects.', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_single_level_hierarchy
  BEFORE INSERT OR UPDATE OF parent_project_id ON cortex_projects
  FOR EACH ROW EXECUTE FUNCTION enforce_single_level_hierarchy();

CREATE INDEX idx_cortex_projects_parent ON cortex_projects(parent_project_id);
```

**`ON DELETE SET NULL` behavior**: When a parent project is deleted, children become standalone projects. Their cascading search silently narrows to their own sources only. This is the least destructive option — blocking deletion is too rigid for a convenience feature. The `manage_project(action="delete")` response should include a warning if the project has children:

```python
# In project_service.py delete_project():
children = self.supabase_client.table("cortex_projects").select("id, title").eq(
    "parent_project_id", project_id
).execute()
if children.data:
    result["warning"] = f"This project had {len(children.data)} child project(s) that are now standalone: {[c['title'] for c in children.data]}"
    # IMPORTANT: Invalidate search cache for all children.
    # ON DELETE SET NULL fires at the DB level, but children's cached source lists
    # still include the now-deleted parent's sources. Without this, children will
    # continue to search against stale/nonexistent parent sources until cache TTL expires.
    for child in children.data:
        invalidate_source_cache(child["id"])
```

**MCP Tool** — Update `manage_project`:

```python
async def manage_project(
    ctx: Context,
    action: str,
    project_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    github_repo: str | None = None,
    parent_project_id: str | None = None,  # NEW
) -> str:
```

**`find_projects`** — Add sibling/children query:

```python
async def find_projects(
    ctx: Context,
    project_id: str | None = None,
    query: str | None = None,
    parent_project_id: str | None = None,  # NEW - find children of a parent
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
) -> str:
```

**Who sets `parent_project_id`?** MCP tools only for now. The Cortex UI project settings page could add a "Parent Project" dropdown in a future UI update, but this is not required for the feature to be useful — MCP clients are the primary consumers.

**API** — Add `parent_project_id` to `allowed_fields` in `ProjectService.update_project()` and to the `project_data` dict in `ProjectService.create_project()`.

---

## Feature 2: Cascading Search with Caching

### Problem
When searching within a sub-project, results only include that project's sources. Users frequently need to also search the parent project's sources. Currently this requires two API calls.

### Design Decision: Single Mechanism, No Scope Parameter

v1 proposed three overlapping mechanisms: `include_parent`, `group` parameter, and `scope` parameter (Feature 4). These solve the same problem differently. The revised design uses only `include_parent`:

- **`include_parent=True` (default)**: Search this project's sources + parent's sources. Covers the common case.
- **Ecosystem-wide search**: Use the parent's `project_id` directly. Since the parent has its own sources AND cascading search walks up, this naturally includes all sources visible to the parent.
- **Cross-sibling search**: Not a real use case. If you need to search another sibling's docs, you search with that sibling's `project_id`. There's no reason to search all siblings at once.

This avoids adding a `scope` parameter that could silently change behavior for existing clients.

### Current Implementation

`_resolve_project_source_filter()` in `knowledge_api.py` (lines 1315-1331):
- Queries `cortex_sources.metadata->>project_id` (NOT the junction table)
- Returns comma-separated source_ids
- No parent awareness

### Proposed Changes

**Step 1 — Migrate to junction table** (prerequisite):

```python
def _resolve_project_source_filter(project_id, existing_source, include_parent=True):
    """Resolve project_id to comma-separated source_ids using the junction table."""
    if existing_source:
        return existing_source
    if not project_id:
        return None

    source_ids = _get_cached_project_sources(project_id, include_parent)
    return ",".join(source_ids) if source_ids else existing_source
```

**Step 2 — Add caching** to avoid extra DB queries on every search:

```python
import time
from functools import lru_cache

# In-memory cache with TTL (project→source mapping changes rarely)
_source_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 300  # 5 minutes

def _get_cached_project_sources(project_id: str, include_parent: bool) -> list[str]:
    """Get source_ids for a project, with in-memory caching."""
    cache_key = f"{project_id}:{include_parent}"
    now = time.time()

    if cache_key in _source_cache:
        cached_ids, cached_at = _source_cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return cached_ids

    source_ids = []

    # Get this project's sources from junction table
    project_sources = get_supabase_client().table("cortex_project_sources").select(
        "source_id"
    ).eq("project_id", project_id).execute()
    if project_sources.data:
        source_ids.extend(s["source_id"] for s in project_sources.data)

    # Include parent's sources
    if include_parent:
        project = get_supabase_client().table("cortex_projects").select(
            "parent_project_id"
        ).eq("id", project_id).maybe_single().execute()

        if project.data and project.data.get("parent_project_id"):
            parent_id = project.data["parent_project_id"]
            parent_sources = get_supabase_client().table("cortex_project_sources").select(
                "source_id"
            ).eq("project_id", parent_id).execute()
            if parent_sources.data:
                source_ids.extend(s["source_id"] for s in parent_sources.data)

    _source_cache[cache_key] = (source_ids, now)
    return source_ids


def invalidate_source_cache(project_id: str = None):
    """Invalidate cache when sources change. Call from manage_rag_source and source_linking_service."""
    if project_id:
        keys_to_remove = [k for k in _source_cache if k.startswith(f"{project_id}:")]
        for k in keys_to_remove:
            del _source_cache[k]
    else:
        _source_cache.clear()
```

**Step 3 — Update MCP tools**:

```python
@mcp.tool()
async def rag_search_knowledge_base(
    ctx: Context,
    query: str,
    source_id: str | None = None,
    project_id: str | None = None,
    include_parent: bool = True,       # NEW
    match_count: int = 5,
    return_mode: str = "pages"
) -> str:
```

**Cache invalidation hooks** — Call `invalidate_source_cache(project_id)` from:
- `manage_rag_source()` when adding/deleting sources
- `source_linking_service.update_project_sources()` when changing project-source links
- `manage_project()` when updating `parent_project_id`

**Result provenance**: No changes needed. Results already include `source_id` in metadata, which clients can trace back to the originating project via the junction table or `rag_get_available_sources()`.

---

## Feature 3: Stable Source IDs and Inline Sync

### Problem
For `source_type="inline"` sources, sync requires `delete` + `re-add`, which generates a new `source_id` (hash includes `uuid.uuid4()`). This breaks all client-side references and junction table entries.

### Current Behavior
```python
# knowledge_api.py inline ingestion:
source_id = hashlib.sha256(f"{title}_{uuid.uuid4()}".encode()).hexdigest()[:16]
```

### Proposed Changes

**A — True inline sync** (primary):

Support `manage_rag_source(action="sync", source_id="...", documents=[...])` for inline sources:

1. Accept a `documents` parameter on sync (currently only used on add)
2. Delete existing chunks/pages for that source_id (same as URL sync)
3. Re-ingest the new documents under the **same source_id**
4. Preserve the source metadata entry and junction table links

```python
# In rag_tools.py manage_rag_source, sync action:
elif action == "sync":
    if not source_id:
        return MCPErrorFormatter.format_error(...)

    # NEW: Accept documents for inline sync
    if documents:
        # Inline sync path — re-ingest under same source_id
        # 1. Delete existing chunks/pages for this source
        # 2. Re-ingest provided documents
        # 3. Preserve source metadata and project links
        ...
    else:
        # URL sync path — existing behavior (re-crawl)
        ...
```

**B — Deterministic source_id for new inline sources**:

For new `action="add"` calls, generate deterministic IDs when `project_id` is provided:

```python
if project_id:
    source_id = hashlib.sha256(f"inline_{project_id}_{title}".encode()).hexdigest()[:16]
else:
    source_id = hashlib.sha256(f"{title}_{uuid.uuid4()}".encode()).hexdigest()[:16]
```

**Collision semantics**: Same title + same project = same source. This is intentional — if you call `add` twice with the same title and project, the second call should update (upsert) the existing source, not create a duplicate.

**Implementation note**: The current `add` action does not implement upsert logic — it will fail with a primary key collision if `source_id` already exists. The implementation must check whether the computed `source_id` already exists in `cortex_sources` and, if so, route to the sync/update path instead of insert. Concretely: before inserting, query `cortex_sources` for the computed `source_id`. If found, delete existing chunks and re-ingest (same as sync). If not found, proceed with normal insert.

**Rename handling**: If a source is renamed (title changes), the old source_id remains valid. The `title` field on `cortex_sources` is mutable metadata, not part of the identity. Only the `source_id` is the identifier. Clients should always reference sources by `source_id`, never by title.

**C — Incremental inline sync** (optimization, depends on Feature 4):

When syncing inline sources, compare provided `file_hash` values against stored hashes. Only re-embed documents whose hashes have changed:

```python
manage_rag_source(
    action="sync",
    source_id="abc123",
    documents=[
        {"title": "CLAUDE.md", "content": "...", "file_hash": "new_hash_1"},
        {"title": "README.md", "content": "...", "file_hash": "same_hash_2"}
    ]
)
# Server compares hashes, only re-embeds CLAUDE.md
```

This saves significant embedding API costs for large doc sets (e.g., 51 files where only 2 changed). Implementation depends on Feature 4 (server-side hash storage).

---

## Feature 4: Server-Side File Hashes for Incremental Sync

### Problem
Clients track document freshness via local state files (`cortex-state.json` with MD5 hashes). This works but is fragile — state files can be lost, and the client must compute hashes and compare them locally. More importantly, without server-side hashes, **Feature 3C (incremental sync) is impossible** — the server can't know which documents changed.

### Proposed Changes

**A — Accept and store file hashes during ingestion**:

When adding/syncing inline documents, accept an optional `file_hash` per document:

```python
manage_rag_source(
    action="add",
    source_type="inline",
    title="My Docs",
    documents=[
        {"title": "CLAUDE.md", "content": "...", "file_hash": "abc123"},
        {"title": "README.md", "content": "...", "file_hash": "def456"}
    ]
)
```

Store in source metadata:
```json
{
  "file_hashes": {
    "CLAUDE.md": "abc123",
    "README.md": "def456"
  },
  "last_synced": "2026-03-03T23:00:00Z"
}
```

**B — Return hash comparison on sync**:

Instead of a separate `rag_check_freshness` tool (which has marginal value on its own — the client still computes hashes either way), make the sync response include diff information:

```json
{
  "success": true,
  "progress_id": "prog_xxx",
  "sync_diff": {
    "changed": ["CLAUDE.md"],
    "unchanged": ["README.md"],
    "new": [],
    "deleted": []
  },
  "documents_to_process": 1,
  "documents_skipped": 1
}
```

This is more actionable than a standalone freshness check — the user sees the diff as part of the sync they're already doing.

**Why not a standalone `rag_check_freshness` tool?** As the reviewer noted, the client still computes hashes either way. The real value of server-side hashes is enabling **incremental sync** (Feature 3C), not eliminating client state files. A freshness check tool can be added later if there's demand, but it's not a priority.

---

## Feature 5: Progress Data Retention

### Problem
After an ingestion completes, the progress data is available for only ~30 seconds before being garbage collected. If a client polls slightly late, it misses the completion results (chunks_stored, code_examples_stored, etc.).

### Current Implementation
Progress is tracked in-memory in `progress_tracker.py` with a short TTL.

### Proposed Changes

1. **Extend TTL to 5 minutes** after completion (configurable via `cortex_settings` key `PROGRESS_COMPLETION_TTL`):

```python
# In progress_tracker.py:
COMPLETION_TTL = int(os.getenv("PROGRESS_COMPLETION_TTL", "300"))  # 5 min default
```

2. **Persist completion summary in source metadata**: When ingestion completes, write results to the source's metadata JSONB:

```json
{
  "last_ingestion": {
    "completed_at": "2026-03-03T23:05:00Z",
    "documents_processed": 3,
    "chunks_stored": 47,
    "code_examples_stored": 12,
    "status": "completed"
  }
}
```

This ensures completion data is always queryable via `rag_get_available_sources()`, regardless of TTL.

---

## Feature 6: Project Metadata and Tags

### Problem
Projects have no structured metadata field, unlike sources which have `metadata JSONB`. This makes it impossible to store project-level attributes (e.g., `domain`, `directory`, `deployment_url`).

### Why Not Reuse `data`?

The `data` column is a JSONB **array** (`DEFAULT '[]'::jsonb`), not an object. Changing its type would break existing projects that store array data. Adding a new `metadata` JSONB **object** column is cleaner than repurposing `data`. The `data` column can be deprecated for new projects in documentation.

### Proposed Changes

```sql
ALTER TABLE cortex_projects
  ADD COLUMN metadata JSONB DEFAULT '{}',
  ADD COLUMN tags TEXT[] DEFAULT '{}';

CREATE INDEX idx_cortex_projects_metadata ON cortex_projects USING GIN(metadata);
CREATE INDEX idx_cortex_projects_tags ON cortex_projects USING GIN(tags);

COMMENT ON COLUMN cortex_projects.metadata IS 'Key-value metadata (domain, directory, deployment_url, etc.)';
COMMENT ON COLUMN cortex_projects.tags IS 'Filterable tags for categorization';
COMMENT ON COLUMN cortex_projects.data IS 'DEPRECATED: Use metadata for key-value data. Kept for backward compatibility.';
```

Update `manage_project` and `find_projects` tools:
```python
# manage_project — add to allowed update fields
metadata: dict | None = None,
tags: list[str] | None = None,

# find_projects — add filtering
tag: str | None = None,  # Filter by tag
```

---

## Implementation Priority

| Feature | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Prereq: Migrate search to junction table | High | Low | P0 — Fix existing inconsistency |
| 1. Project Hierarchy | High | Low | P0 — One column + trigger |
| 2. Cascading Search with Caching | High | Medium | P0 — Core workflow enabler |
| 3. Stable Source IDs + Inline Sync | Medium | Medium | P1 — Eliminates fragile workaround |
| 4. Server-Side Hashes (for incremental sync) | Medium | Low | P1 — Enables 3C optimization |
| 5. Progress Retention | Low | Low | P2 — Quick improvement |
| 6. Project Metadata/Tags | Low | Low | P2 — Consistency with sources |

Features 1 and 2 together unlock the core multi-project workflow. Feature 3 eliminates the most fragile client-side workaround. Feature 4 is a force multiplier for Feature 3.

---

## Files Affected

Based on analysis of the current Cortex codebase:

### Database
- `migration/complete_setup.sql` — Add `parent_project_id`, `metadata`, `tags` to `cortex_projects`
- New migration file `migration/0.1.0/012_add_project_hierarchy.sql`

### MCP Tools (`python/src/mcp_server/`)
- `features/projects/project_tools.py` — Add `parent_project_id`, `metadata`, `tags` params to `find_projects` and `manage_project`
- `features/rag/rag_tools.py` — Add `include_parent` param to `rag_search_knowledge_base` and `rag_search_code_examples`; accept `documents` on sync action

### Server Services (`python/src/server/`)
- `services/projects/project_service.py` — Add `parent_project_id` to `create_project`, `update_project`, `list_projects`; add deletion warning for parent projects
- `services/projects/source_linking_service.py` — Add cache invalidation hook
- `api_routes/knowledge_api.py` — Rewrite `_resolve_project_source_filter()` to use junction table + caching + parent resolution; add `include_parent` to request models; support inline sync with documents; store file hashes in source metadata
- `api_routes/projects_api.py` — Pass through `parent_project_id`, `metadata`, `tags`
- `utils/progress/progress_tracker.py` — Extend completion TTL; persist results to source metadata on completion

### No Changes Needed
- `models.py` — Projects bypass Pydantic models (direct Supabase)
- `services/search/rag_service.py` — Already handles comma-separated source_ids
- `services/source_management_service.py` — Already handles metadata updates

---

## Migration Path

1. **Phase 1** (prereq): Migrate `_resolve_project_source_filter()` to use `cortex_project_sources` junction table instead of `cortex_sources.metadata->>project_id`.

   **Data migration required**: Sources ingested via MCP (using `manage_rag_source` with `project_id`) set the `metadata->>project_id` field on `cortex_sources` but do NOT create entries in the `cortex_project_sources` junction table. The junction table is only populated by the UI-based source linking workflow. Before switching the search path to the junction table, run a one-time backfill:
   ```sql
   -- Backfill junction table from metadata project_id values
   INSERT INTO cortex_project_sources (project_id, source_id, notes, created_by)
   SELECT
     (metadata->>'project_id')::uuid,
     source_id,
     'technical',
     'migration'
   FROM cortex_sources
   WHERE metadata->>'project_id' IS NOT NULL
     AND NOT EXISTS (
       SELECT 1 FROM cortex_project_sources ps
       WHERE ps.source_id = cortex_sources.source_id
         AND ps.project_id = (cortex_sources.metadata->>'project_id')::uuid
     );
   ```
   Also update `manage_rag_source(action="add")` to write to the junction table during ingestion (in addition to the metadata field), so future sources are linked via both paths.

2. **Phase 2**: Add `parent_project_id` column to `cortex_projects` with trigger constraint. Add `metadata` and `tags` columns. All nullable with defaults — zero impact on existing data.

3. **Phase 3**: Implement cascading search in `_resolve_project_source_filter()` with in-memory caching. Add `include_parent` parameter to MCP search tools. Default `True` is safe — no existing projects have parents, so behavior is identical until someone sets one.

4. **Phase 4**: Add inline sync support (`action="sync"` with `documents` parameter). Add deterministic source_id generation for inline sources with `project_id`.

5. **Phase 5**: Add `file_hash` support to inline ingestion. Store hashes in source metadata. Implement incremental sync (diff-based re-embedding).

6. **Phase 6**: Extend progress TTL. Persist completion data to source metadata.

All changes are backward-compatible. Existing clients that don't use `parent_project_id` continue to work identically.
