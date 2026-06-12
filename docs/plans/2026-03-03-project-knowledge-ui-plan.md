# Project Knowledge Sources UI Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface MCP-ingested knowledge sources within the Project view (new Knowledge tab with inline inspector) and add project filtering to the Knowledge page.

**Architecture:** Backend adds a `project_id` filter to the existing `KnowledgeSummaryService` and exposes it via both a new project-scoped endpoint and the existing summary endpoint. Frontend adds a Knowledge tab to the Project view with a split-panel layout (source list + inspector) and a project filter dropdown to the Knowledge page header.

**Tech Stack:** Python/FastAPI, React/TypeScript, TanStack Query v5, Supabase (PostgREST), Radix UI primitives

**Design doc:** `docs/plans/2026-03-03-project-knowledge-ui-design.md`

---

## Task 1: Backend — Add `project_id` filter to `KnowledgeSummaryService`

**Files:**
- Modify: `python/src/server/services/knowledge/knowledge_summary_service.py:28-90`
- Test: `python/tests/server/services/test_knowledge_summary_project_filter.py`

**Step 1: Write the failing test**

Create `python/tests/server/services/test_knowledge_summary_project_filter.py`:

```python
"""Tests for project_id filtering in KnowledgeSummaryService."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with chainable query builder."""
    client = MagicMock()
    return client


@pytest.fixture
def service(mock_supabase):
    """Create a KnowledgeSummaryService with mocked client."""
    from src.server.services.knowledge.knowledge_summary_service import KnowledgeSummaryService
    svc = KnowledgeSummaryService()
    svc.supabase = mock_supabase
    return svc


@pytest.mark.asyncio
async def test_get_summaries_with_project_id_filters_by_metadata(service, mock_supabase):
    """When project_id is provided, query should filter cortex_sources by metadata->>'project_id'."""
    # Setup mock chain for main query
    query_mock = MagicMock()
    query_mock.eq.return_value = query_mock
    query_mock.range.return_value = query_mock
    query_mock.order.return_value = query_mock
    query_mock.execute.return_value = MagicMock(data=[])

    # Setup mock chain for count query
    count_mock = MagicMock()
    count_mock.eq.return_value = count_mock
    count_mock.execute.return_value = MagicMock(count=0)

    mock_supabase.from_.return_value.select.side_effect = [query_mock, count_mock]

    project_id = "2d747998-7c66-46bb-82a9-74a6dcffd6c2"
    result = await service.get_summaries(project_id=project_id)

    # Verify the metadata filter was applied to both queries
    query_mock.eq.assert_called_with("metadata->>project_id", project_id)
    count_mock.eq.assert_called_with("metadata->>project_id", project_id)
    assert result["items"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_get_summaries_without_project_id_returns_all(service, mock_supabase):
    """When project_id is None, no project filter should be applied."""
    query_mock = MagicMock()
    query_mock.range.return_value = query_mock
    query_mock.order.return_value = query_mock
    query_mock.execute.return_value = MagicMock(data=[])

    count_mock = MagicMock()
    count_mock.execute.return_value = MagicMock(count=0)

    mock_supabase.from_.return_value.select.side_effect = [query_mock, count_mock]

    result = await service.get_summaries()

    # eq should NOT have been called (no project filter)
    query_mock.eq.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/server/services/test_knowledge_summary_project_filter.py -v`
Expected: FAIL — `get_summaries()` doesn't accept `project_id` parameter

**Step 3: Implement the filter**

In `python/src/server/services/knowledge/knowledge_summary_service.py`, modify `get_summaries()` at line 28:

Add `project_id: Optional[str] = None` parameter to the signature:

```python
async def get_summaries(
    self,
    page: int = 1,
    per_page: int = 20,
    knowledge_type: Optional[str] = None,
    search: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
```

After the existing filters (after line 68), add the project_id filter to both queries:

```python
if project_id:
    query = query.eq("metadata->>project_id", project_id)
```

And similarly in the count query section (after line 82):

```python
if project_id:
    count_query = count_query.eq("metadata->>project_id", project_id)
```

**Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/server/services/test_knowledge_summary_project_filter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add python/src/server/services/knowledge/knowledge_summary_service.py python/tests/server/services/test_knowledge_summary_project_filter.py
git commit -m "feat: add project_id filter to KnowledgeSummaryService"
```

---

## Task 2: Backend — New project knowledge-sources endpoint + summary filter param

**Files:**
- Modify: `python/src/server/api_routes/projects_api.py` (add after line 1278)
- Modify: `python/src/server/api_routes/knowledge_api.py:278-300` (add project_id param)
- Test: `python/tests/server/api_routes/test_project_knowledge_api.py`

**Step 1: Write the failing test**

Create `python/tests/server/api_routes/test_project_knowledge_api.py`:

```python
"""Tests for project knowledge sources API endpoint."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_get_project_knowledge_sources_endpoint():
    """GET /api/projects/{project_id}/knowledge-sources returns filtered sources."""
    from httpx import ASGITransport, AsyncClient
    from src.server.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/projects/test-project-id/knowledge-sources")
        # Should return 200 (even if empty)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
```

**Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/server/api_routes/test_project_knowledge_api.py -v`
Expected: FAIL — 404 (endpoint doesn't exist)

**Step 3: Add the endpoint to projects_api.py**

At the end of `python/src/server/api_routes/projects_api.py` (after the last endpoint ~line 1278), add:

```python
@router.get("/projects/{project_id}/knowledge-sources")
async def get_project_knowledge_sources(
    project_id: str,
    page: int = 1,
    per_page: int = 20,
    knowledge_type: str | None = None,
    search: str | None = None,
):
    """Get knowledge sources associated with a project via metadata.project_id."""
    page = max(1, page)
    per_page = min(100, max(1, per_page))

    from src.server.services.knowledge.knowledge_summary_service import KnowledgeSummaryService

    service = KnowledgeSummaryService()
    return await service.get_summaries(
        page=page,
        per_page=per_page,
        knowledge_type=knowledge_type,
        search=search,
        project_id=project_id,
    )
```

**Step 4: Add `project_id` param to existing summary endpoint**

In `python/src/server/api_routes/knowledge_api.py` at line ~278, add `project_id` parameter:

```python
@router.get("/knowledge-items/summary")
async def get_knowledge_items_summary(
    page: int = 1, per_page: int = 20, knowledge_type: str | None = None, search: str | None = None, project_id: str | None = None
):
```

And pass it to the service call:

```python
result = await service.get_summaries(page, per_page, knowledge_type, search, project_id=project_id)
```

**Step 5: Run test to verify it passes**

Run: `cd python && uv run pytest tests/server/api_routes/test_project_knowledge_api.py -v`
Expected: PASS

**Step 6: Run all existing tests to verify no regressions**

Run: `cd python && uv run pytest tests/ -v --timeout=30`
Expected: All pass

**Step 7: Commit**

```bash
git add python/src/server/api_routes/projects_api.py python/src/server/api_routes/knowledge_api.py python/tests/server/api_routes/test_project_knowledge_api.py
git commit -m "feat: add project knowledge-sources endpoint and project_id filter to summary"
```

---

## Task 3: Frontend — Project Knowledge types, service, and query hooks

**Files:**
- Create: `cortex-ui/src/features/projects/knowledge/types/index.ts`
- Create: `cortex-ui/src/features/projects/knowledge/services/projectKnowledgeService.ts`
- Create: `cortex-ui/src/features/projects/knowledge/hooks/useProjectKnowledgeQueries.ts`

**Step 1: Create the types file**

Create `cortex-ui/src/features/projects/knowledge/types/index.ts`:

```typescript
/**
 * Project Knowledge Types
 * Re-exports knowledge types used in the project knowledge tab
 */
export type {
  KnowledgeItem,
  KnowledgeItemMetadata,
  KnowledgeItemsResponse,
  DocumentChunk,
  CodeExample,
  ChunksResponse,
  CodeExamplesResponse,
  InspectorSelectedItem,
  DocumentChunkMetadata,
  CodeExampleMetadata,
} from "@/features/knowledge/types/knowledge";
```

**Step 2: Create the service**

Create `cortex-ui/src/features/projects/knowledge/services/projectKnowledgeService.ts`:

```typescript
/**
 * Project Knowledge Service
 * Fetches knowledge sources scoped to a specific project
 */
import { callAPIWithETag } from "@/features/shared/api/apiClient";
import type { KnowledgeItemsResponse } from "../types";

export const projectKnowledgeService = {
  async getProjectKnowledgeSources(
    projectId: string,
    params?: { page?: number; per_page?: number; search?: string; knowledge_type?: string },
  ): Promise<KnowledgeItemsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.append("page", params.page.toString());
    if (params?.per_page) searchParams.append("per_page", params.per_page.toString());
    if (params?.search) searchParams.append("search", params.search);
    if (params?.knowledge_type) searchParams.append("knowledge_type", params.knowledge_type);

    const queryString = searchParams.toString();
    const endpoint = `/api/projects/${projectId}/knowledge-sources${queryString ? `?${queryString}` : ""}`;

    return callAPIWithETag<KnowledgeItemsResponse>(endpoint);
  },
};
```

**Step 3: Create the query hooks**

Create `cortex-ui/src/features/projects/knowledge/hooks/useProjectKnowledgeQueries.ts`:

```typescript
/**
 * Project Knowledge Query Hooks
 * Handles fetching knowledge sources scoped to a project
 */
import { useQuery } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { projectKnowledgeService } from "../services/projectKnowledgeService";
import type { KnowledgeItemsResponse } from "../types";

export const projectKnowledgeKeys = {
  all: ["projects", "knowledge-sources"] as const,
  byProject: (projectId: string) => ["projects", projectId, "knowledge-sources"] as const,
};

export function useProjectKnowledgeSources(projectId: string | undefined) {
  return useQuery<KnowledgeItemsResponse>({
    queryKey: projectId ? projectKnowledgeKeys.byProject(projectId) : DISABLED_QUERY_KEY,
    queryFn: () =>
      projectId
        ? projectKnowledgeService.getProjectKnowledgeSources(projectId, { per_page: 100 })
        : Promise.reject("No project ID"),
    enabled: !!projectId,
    staleTime: STALE_TIMES.normal,
  });
}
```

**Step 4: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects/knowledge" || echo "No TypeScript errors"`
Expected: No errors

**Step 5: Commit**

```bash
git add cortex-ui/src/features/projects/knowledge/
git commit -m "feat: add project knowledge types, service, and query hooks"
```

---

## Task 4: Frontend — Project Knowledge Tab components

**Files:**
- Create: `cortex-ui/src/features/projects/knowledge/components/ProjectSourceCard.tsx`
- Create: `cortex-ui/src/features/projects/knowledge/components/ProjectSourceInspector.tsx`
- Create: `cortex-ui/src/features/projects/knowledge/KnowledgeTab.tsx`

**Step 1: Create ProjectSourceCard component**

Create `cortex-ui/src/features/projects/knowledge/components/ProjectSourceCard.tsx`:

```typescript
/**
 * Compact card for a knowledge source within the project knowledge tab.
 * Shows title, type, counts, and status.
 */
import { FileText, Code2, Globe, FileUp } from "lucide-react";
import { cn } from "@/features/ui/primitives/styles";
import type { KnowledgeItem } from "../types";

interface ProjectSourceCardProps {
  source: KnowledgeItem;
  isSelected: boolean;
  onSelect: (source: KnowledgeItem) => void;
}

export function ProjectSourceCard({ source, isSelected, onSelect }: ProjectSourceCardProps) {
  const isUrl = source.source_type === "url";
  const SourceIcon = isUrl ? Globe : FileUp;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(source)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(source);
        }
      }}
      aria-selected={isSelected}
      className={cn(
        "group px-3 py-2.5 cursor-pointer border-b border-white/5",
        "transition-all duration-150",
        isSelected
          ? "bg-cyan-500/10 border-l-2 border-l-cyan-400"
          : "hover:bg-white/5 border-l-2 border-l-transparent",
      )}
    >
      {/* Title row */}
      <div className="flex items-center gap-2 mb-1">
        <SourceIcon
          className={cn("w-3.5 h-3.5 shrink-0", isSelected ? "text-cyan-400" : "text-gray-500")}
          aria-hidden="true"
        />
        <span className={cn("text-sm font-medium truncate", isSelected ? "text-cyan-100" : "text-gray-300")}>
          {source.title}
        </span>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3 ml-5.5 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <FileText className="w-3 h-3" aria-hidden="true" />
          {source.document_count}
        </span>
        {source.code_examples_count > 0 && (
          <span className="flex items-center gap-1">
            <Code2 className="w-3 h-3" aria-hidden="true" />
            {source.code_examples_count}
          </span>
        )}
        <span
          className={cn(
            "capitalize text-[10px] px-1.5 py-0.5 rounded-full",
            source.knowledge_type === "technical"
              ? "bg-cyan-500/10 text-cyan-400"
              : "bg-purple-500/10 text-purple-400",
          )}
        >
          {source.knowledge_type}
        </span>
      </div>
    </div>
  );
}
```

**Step 2: Create ProjectSourceInspector component**

Create `cortex-ui/src/features/projects/knowledge/components/ProjectSourceInspector.tsx`:

This component reuses the existing `useInspectorPagination` hook, `InspectorSidebar`, and `ContentViewer` from the knowledge inspector. It renders them inline (not in a dialog).

```typescript
/**
 * Inline inspector for a knowledge source within the project knowledge tab.
 * Reuses knowledge inspector internals but renders inline instead of in a dialog.
 */
import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { copyToClipboard } from "@/features/shared/utils/clipboard";
import { ContentViewer } from "@/features/knowledge/inspector/components/ContentViewer";
import { InspectorHeader } from "@/features/knowledge/inspector/components/InspectorHeader";
import { InspectorSidebar } from "@/features/knowledge/inspector/components/InspectorSidebar";
import { useInspectorPagination } from "@/features/knowledge/inspector/hooks/useInspectorPagination";
import type { CodeExample, DocumentChunk, InspectorSelectedItem, KnowledgeItem } from "../types";

interface ProjectSourceInspectorProps {
  source: KnowledgeItem;
}

type ViewMode = "documents" | "code";

export function ProjectSourceInspector({ source }: ProjectSourceInspectorProps) {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>("documents");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItem, setSelectedItem] = useState<InspectorSelectedItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Reset when source changes
  useEffect(() => {
    setViewMode("documents");
    setSelectedItem(null);
    setSearchQuery("");
  }, [source.source_id]);

  // Reuse the existing pagination hook from knowledge inspector
  const paginationData = useInspectorPagination({
    sourceId: source.source_id,
    viewMode,
    searchQuery,
  });

  const currentItems = paginationData.items;
  const totalDocumentCount = source.document_count ?? source.metadata?.document_count ?? 0;
  const totalCodeCount = source.code_examples_count ?? source.metadata?.code_examples_count ?? 0;

  // Auto-select first item when data loads
  useEffect(() => {
    if (selectedItem || currentItems.length === 0) return;

    const firstItem = currentItems[0];
    if (viewMode === "documents") {
      const firstDoc = firstItem as DocumentChunk;
      setSelectedItem({
        type: "document",
        id: firstDoc.id,
        content: firstDoc.content || "",
        metadata: {
          title: firstDoc.title || firstDoc.metadata?.title,
          section: firstDoc.section || firstDoc.metadata?.section,
          relevance_score: firstDoc.metadata?.relevance_score,
          url: firstDoc.url || firstDoc.metadata?.url,
          tags: firstDoc.metadata?.tags,
        },
      });
    } else {
      const firstCode = firstItem as CodeExample;
      setSelectedItem({
        type: "code",
        id: String(firstCode.id || ""),
        content: firstCode.content || firstCode.code || "",
        metadata: {
          language: firstCode.language,
          file_path: firstCode.file_path,
          summary: firstCode.summary,
          relevance_score: firstCode.metadata?.relevance_score,
          title: firstCode.title || firstCode.example_name,
        },
      });
    }
  }, [viewMode, currentItems, selectedItem]);

  const handleCopy = useCallback(async (text: string, id: string) => {
    const result = await copyToClipboard(text);
    if (result.success) {
      setCopiedId(id);
      setTimeout(() => setCopiedId((v) => (v === id ? null : v)), 2000);
    }
  }, []);

  const handleItemSelect = useCallback(
    (item: DocumentChunk | CodeExample) => {
      if (viewMode === "documents") {
        const doc = item as DocumentChunk;
        setSelectedItem({
          type: "document",
          id: doc.id || "",
          content: doc.content || "",
          metadata: {
            title: doc.title || doc.metadata?.title,
            section: doc.section || doc.metadata?.section,
            relevance_score: doc.metadata?.relevance_score,
            url: doc.url || doc.metadata?.url,
            tags: doc.metadata?.tags,
          },
        });
      } else {
        const code = item as CodeExample;
        setSelectedItem({
          type: "code",
          id: String(code.id),
          content: code.content || code.code || "",
          metadata: {
            language: code.language,
            file_path: code.file_path,
            summary: code.summary,
            relevance_score: code.metadata?.relevance_score,
            title: code.title || code.example_name,
          },
        });
      }
    },
    [viewMode],
  );

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    setSelectedItem(null);
    setSearchQuery("");
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Source header with link to Knowledge page */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
        <h3 className="text-sm font-medium text-white/90 truncate">{source.title}</h3>
        <button
          type="button"
          onClick={() => navigate("/knowledge")}
          className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
          aria-label="View in Knowledge Base"
        >
          <ExternalLink className="w-3 h-3" aria-hidden="true" />
          Knowledge Base
        </button>
      </div>

      {/* Inspector header with view mode toggle */}
      <div className="flex-shrink-0">
        <InspectorHeader
          item={source}
          viewMode={viewMode}
          onViewModeChange={handleViewModeChange}
          documentCount={totalDocumentCount}
          codeCount={totalCodeCount}
          filteredDocumentCount={viewMode === "documents" ? currentItems.length : 0}
          filteredCodeCount={viewMode === "code" ? currentItems.length : 0}
        />
      </div>

      {/* Split view: sidebar + content */}
      <div className="flex flex-1 min-h-0">
        <InspectorSidebar
          viewMode={viewMode}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          items={currentItems as DocumentChunk[] | CodeExample[]}
          selectedItemId={selectedItem?.id || null}
          onItemSelect={handleItemSelect}
          isLoading={paginationData.isLoading}
          hasNextPage={paginationData.hasNextPage}
          onLoadMore={paginationData.fetchNextPage}
          isFetchingNextPage={paginationData.isFetchingNextPage}
        />
        <div className="flex-1 min-h-0 min-w-0 bg-black/20 flex flex-col">
          <ContentViewer selectedItem={selectedItem} onCopy={handleCopy} copiedId={copiedId} />
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Create KnowledgeTab component**

Create `cortex-ui/src/features/projects/knowledge/KnowledgeTab.tsx`:

```typescript
/**
 * Knowledge Tab for Project View
 * Shows knowledge sources associated with a project via metadata.project_id
 * Split layout: source list (left) + inline inspector (right)
 */
import { BookOpen, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/features/ui/primitives/styles";
import type { KnowledgeItem } from "./types";
import { useProjectKnowledgeSources } from "./hooks/useProjectKnowledgeQueries";
import { ProjectSourceCard } from "./components/ProjectSourceCard";
import { ProjectSourceInspector } from "./components/ProjectSourceInspector";

interface KnowledgeTabProps {
  projectId: string;
}

export function KnowledgeTab({ projectId }: KnowledgeTabProps) {
  const { data, isLoading, error } = useProjectKnowledgeSources(projectId);
  const [selectedSource, setSelectedSource] = useState<KnowledgeItem | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const sources = data?.items || [];

  // Filter sources by search query
  const filteredSources = useMemo(() => {
    if (!searchQuery) return sources;
    const q = searchQuery.toLowerCase();
    return sources.filter((s) => s.title.toLowerCase().includes(q));
  }, [sources, searchQuery]);

  // Auto-select first source when data loads
  useMemo(() => {
    if (!selectedSource && filteredSources.length > 0) {
      setSelectedSource(filteredSources[0]);
    }
  }, [filteredSources, selectedSource]);

  // Sync selection when sources change
  useMemo(() => {
    if (selectedSource && !sources.find((s) => s.source_id === selectedSource.source_id)) {
      setSelectedSource(sources.length > 0 ? sources[0] : null);
    }
  }, [sources, selectedSource]);

  if (isLoading) {
    return (
      <div className="h-[600px] flex items-center justify-center text-gray-500">
        <div className="animate-pulse">Loading knowledge sources...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-[600px] flex items-center justify-center text-red-400">
        Failed to load knowledge sources
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="h-[600px] flex flex-col items-center justify-center text-gray-500 gap-3">
        <BookOpen className="w-12 h-12 text-gray-600" aria-hidden="true" />
        <p className="text-sm">No knowledge sources linked to this project</p>
        <p className="text-xs text-gray-600">
          Use MCP tools to ingest documentation with this project's ID
        </p>
      </div>
    );
  }

  return (
    <div className="h-[600px] flex border border-white/10 rounded-lg overflow-hidden bg-black/20">
      {/* Left: Source list */}
      <div className="w-64 shrink-0 border-r border-white/10 flex flex-col">
        {/* Search */}
        <div className="p-2 border-b border-white/10">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" aria-hidden="true" />
            <input
              type="text"
              placeholder="Filter sources..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={cn(
                "w-full pl-7 pr-2 py-1.5 text-xs bg-white/5 border border-white/10 rounded",
                "text-gray-300 placeholder:text-gray-600",
                "focus:outline-none focus:border-cyan-500/50",
              )}
            />
          </div>
        </div>

        {/* Source list */}
        <div className="flex-1 overflow-y-auto">
          {filteredSources.map((source) => (
            <ProjectSourceCard
              key={source.source_id}
              source={source}
              isSelected={selectedSource?.source_id === source.source_id}
              onSelect={setSelectedSource}
            />
          ))}
          {filteredSources.length === 0 && searchQuery && (
            <div className="p-4 text-xs text-gray-600 text-center">No matching sources</div>
          )}
        </div>

        {/* Count footer */}
        <div className="px-3 py-2 border-t border-white/10 text-xs text-gray-500">
          {filteredSources.length} source{filteredSources.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Right: Inspector */}
      <div className="flex-1 min-w-0 flex flex-col">
        {selectedSource ? (
          <ProjectSourceInspector source={selectedSource} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
            Select a source to inspect
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 4: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects/knowledge" || echo "No TypeScript errors"`
Expected: No errors (may need adjustments based on actual import paths)

**Step 5: Commit**

```bash
git add cortex-ui/src/features/projects/knowledge/
git commit -m "feat: add Knowledge tab components for project view"
```

---

## Task 5: Frontend — Integrate Knowledge tab into ProjectsView

**Files:**
- Modify: `cortex-ui/src/features/projects/views/ProjectsView.tsx:2-4,214-217,231-232,293-296,311-312`

**Step 1: Add import for KnowledgeTab and Library icon**

At the top of `ProjectsView.tsx`, add the Library icon import (line 3) and KnowledgeTab import:

```typescript
import { Activity, CheckCircle2, FileText, Library, List, ListTodo, Pin } from "lucide-react";
```

And add the KnowledgeTab import after the DocsTab import (around line 16):

```typescript
import { KnowledgeTab } from "../knowledge/KnowledgeTab";
```

**Step 2: Add Knowledge to PillNavigation items (horizontal mode, ~line 214)**

Change the items array from:

```typescript
items={[
  { id: "docs", label: "Docs", icon: <FileText className="w-4 h-4" /> },
  { id: "tasks", label: "Tasks", icon: <ListTodo className="w-4 h-4" /> },
]}
```

To:

```typescript
items={[
  { id: "docs", label: "Docs", icon: <FileText className="w-4 h-4" /> },
  { id: "knowledge", label: "Knowledge", icon: <Library className="w-4 h-4" /> },
  { id: "tasks", label: "Tasks", icon: <ListTodo className="w-4 h-4" /> },
]}
```

**Step 3: Add conditional rendering for Knowledge tab (horizontal mode, ~line 231)**

After the docs conditional and before the tasks conditional:

```typescript
{activeTab === "docs" && <DocsTab project={selectedProject} />}
{activeTab === "knowledge" && <KnowledgeTab projectId={selectedProject.id} />}
{activeTab === "tasks" && <TasksTab projectId={selectedProject.id} />}
```

**Step 4: Repeat for sidebar mode (~line 293 and 311)**

Same changes to the second PillNavigation items array (~line 293) and the second set of conditional renders (~line 311).

**Step 5: Verify TypeScript compiles and visually check**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep "error" || echo "No TypeScript errors"`

Manually verify: Navigate to `http://localhost:3737/projects/{project_id}` and confirm the Knowledge tab appears between Docs and Tasks.

**Step 6: Commit**

```bash
git add cortex-ui/src/features/projects/views/ProjectsView.tsx
git commit -m "feat: integrate Knowledge tab into project view"
```

---

## Task 6: Frontend — Add project filter to Knowledge page

**Files:**
- Modify: `cortex-ui/src/features/knowledge/types/knowledge.ts:127-134` (add project_id to filter)
- Modify: `cortex-ui/src/features/knowledge/services/knowledgeService.ts:28-45` (pass project_id param)
- Modify: `cortex-ui/src/features/knowledge/components/KnowledgeHeader.tsx:10-32` (add project dropdown)
- Modify: `cortex-ui/src/features/knowledge/views/KnowledgeView.tsx:29-44` (manage project filter state)

**Step 1: Add `project_id` to KnowledgeItemsFilter type**

In `cortex-ui/src/features/knowledge/types/knowledge.ts`, modify the `KnowledgeItemsFilter` interface (line 127):

```typescript
export interface KnowledgeItemsFilter {
  knowledge_type?: "technical" | "business";
  tags?: string[];
  source_type?: "url" | "file";
  search?: string;
  page?: number;
  per_page?: number;
  project_id?: string;
}
```

**Step 2: Pass `project_id` in the service**

In `cortex-ui/src/features/knowledge/services/knowledgeService.ts`, add to `getKnowledgeSummaries` (around line 38):

```typescript
if (filter?.project_id) params.append("project_id", filter.project_id);
```

Add this line after the existing `if (filter?.search)` block.

**Step 3: Add project filter props to KnowledgeHeader**

In `cortex-ui/src/features/knowledge/components/KnowledgeHeader.tsx`:

Add to the props interface:

```typescript
projectFilter: string;
onProjectFilterChange: (projectId: string) => void;
projects: Array<{ id: string; title: string }>;
```

Add a project dropdown in the filter area (after the type filter toggle, before the view mode toggle). Use a simple select element wrapped in the existing styling pattern:

```typescript
{/* Project filter */}
{projects.length > 0 && (
  <select
    value={projectFilter}
    onChange={(e) => onProjectFilterChange(e.target.value)}
    className={cn(
      "h-8 px-2 text-xs bg-white/5 border border-white/10 rounded",
      "text-gray-300 focus:outline-none focus:border-cyan-500/50",
    )}
    aria-label="Filter by project"
  >
    <option value="">All Projects</option>
    {projects.map((p) => (
      <option key={p.id} value={p.id}>{p.title}</option>
    ))}
  </select>
)}
```

Note: Per UI_STANDARDS.md section 4 (Radix UI), native `<select>` should ideally be replaced with a Radix Select component. However, for an initial implementation with minimal scope, a native select is acceptable — it can be upgraded in a follow-up if desired.

**Step 4: Wire up project filter in KnowledgeView**

In `cortex-ui/src/features/knowledge/views/KnowledgeView.tsx`:

Add project state and import:

```typescript
import { useProjects } from "@/features/projects/hooks/useProjectQueries";
```

Add state (after `typeFilter` state, ~line 21):

```typescript
const [projectFilter, setProjectFilter] = useState("");
```

Add projects query:

```typescript
const { data: projectsData = [] } = useProjects();
const projects = (projectsData as Array<{ id: string; title: string }>).map((p) => ({
  id: p.id,
  title: p.title,
}));
```

Add `project_id` to filter object (inside `useMemo`, ~line 39):

```typescript
if (projectFilter) {
  f.project_id = projectFilter;
}
```

Pass new props to KnowledgeHeader:

```typescript
<KnowledgeHeader
  // ... existing props
  projectFilter={projectFilter}
  onProjectFilterChange={setProjectFilter}
  projects={projects}
/>
```

**Step 5: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep "error" || echo "No TypeScript errors"`

**Step 6: Commit**

```bash
git add cortex-ui/src/features/knowledge/types/knowledge.ts cortex-ui/src/features/knowledge/services/knowledgeService.ts cortex-ui/src/features/knowledge/components/KnowledgeHeader.tsx cortex-ui/src/features/knowledge/views/KnowledgeView.tsx
git commit -m "feat: add project filter dropdown to Knowledge page"
```

---

## Task 7: End-to-end verification

**Step 1: Start services**

Run: `make dev` (or `docker compose --profile backend up -d && cd cortex-ui && npm run dev`)

**Step 2: Verify project knowledge tab**

1. Navigate to `http://localhost:3737/projects/2d747998-7c66-46bb-82a9-74a6dcffd6c2`
2. Click the "Knowledge" tab
3. Verify "RecipeRaiders Documentation" source appears with 147 document count
4. Click the source and verify the inline inspector shows document chunks
5. Verify "View in Knowledge Base" link navigates to `/knowledge`

**Step 3: Verify knowledge page project filter**

1. Navigate to `http://localhost:3737/knowledge`
2. Verify the project filter dropdown appears
3. Select "RecipeRaiders" from the dropdown
4. Verify only "RecipeRaiders Documentation" source is shown
5. Select "All Projects" and verify all sources return

**Step 4: Verify API directly**

```bash
curl http://localhost:8181/api/projects/2d747998-7c66-46bb-82a9-74a6dcffd6c2/knowledge-sources | python3 -m json.tool
curl "http://localhost:8181/api/knowledge-items/summary?project_id=2d747998-7c66-46bb-82a9-74a6dcffd6c2" | python3 -m json.tool
```

**Step 5: Run all tests**

```bash
cd python && uv run pytest tests/ -v --timeout=30
cd cortex-ui && npm run test
```

**Step 6: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during e2e verification"
```
