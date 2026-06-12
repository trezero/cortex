# Project Knowledge Sources UI Integration

**Date:** 2026-03-03
**Status:** Approved

## Problem

When coding agents ingest documentation via MCP tools (`manage_rag_source`) with a `project_id`, those knowledge sources don't appear anywhere in the Project view. The project's "Docs" tab only shows manually-created project documents (stored in `cortex_projects.docs` JSONB), while MCP-ingested sources live in `cortex_sources` with chunks in `cortex_documents` — a completely separate system.

The RecipeRaiders project demonstrates this: 0 project documents shown, but 147 document chunks exist in the knowledge base with `metadata.project_id` pointing to the project.

## Solution

Two complementary UI changes:

1. **Knowledge tab in Project view** — New tab alongside "Docs" and "Tasks" with inline source inspector
2. **Project filter on Knowledge page** — Dropdown to filter sources by project

## Data Linkage

Query `cortex_sources WHERE metadata->>'project_id' = project_id`. This uses the existing JSONB metadata set during MCP ingestion. No schema changes needed.

## Backend API Changes

### New endpoint: `GET /api/projects/{project_id}/knowledge-sources`

Returns knowledge source summaries associated with the project.

- Add route in `python/src/server/api_routes/projects_api.py`
- Add `get_project_knowledge_sources(project_id)` to `KnowledgeSummaryService`
- Query: `cortex_sources` filtered by `metadata->>'project_id'`
- Response: `{ items: [...], total_count: number }`
- Each item matches the existing knowledge summary format: source_id, title, url, status, document_count, code_examples_count, knowledge_type, source_type, metadata, created_at, updated_at

### Modified endpoint: `GET /api/knowledge-items/summary?project_id={id}`

Add optional `project_id` query parameter to the existing summary endpoint.

- When set, filter sources by `metadata->>'project_id'`
- When unset, return all sources (current behavior)

## Frontend Changes

### 1. Knowledge Tab in Project View

**Location:** `cortex-ui/src/features/projects/knowledge/`

Split layout matching the Docs tab pattern (sidebar + inspector):

**Left panel — Source List (256px):**
- Compact source cards with title, source type icon (URL/inline), document count, code example count, status badge
- Search/filter by title
- Click to select and inspect

**Right panel — Inline Source Inspector (flex-1):**
- Source metadata card (title, type, URL/inline indicator, tags, dates)
- Document chunks tab with pagination (uses `GET /api/knowledge-items/{source_id}/chunks`)
- Code examples tab with pagination (uses `GET /api/knowledge-items/{source_id}/code-examples`)
- "View in Knowledge Base" link to navigate to full Knowledge page

**Component structure:**
```
features/projects/knowledge/
├── KnowledgeTab.tsx              # Split layout container
├── components/
│   ├── ProjectSourceList.tsx     # Scrollable source list
│   ├── ProjectSourceCard.tsx     # Individual source card
│   └── ProjectSourceInspector.tsx # Source details + chunks
├── hooks/
│   └── useProjectKnowledgeQueries.ts  # Query hooks & keys
├── services/
│   └── projectKnowledgeService.ts     # API calls
└── types/
    └── index.ts                       # Types (reuse from knowledge feature)
```

**Tab integration in ProjectsView.tsx:**
- Add "Knowledge" tab (Library icon) to PillNavigation
- Render `<KnowledgeTab projectId={selectedProject.id} />` when active

### 2. Project Filter on Knowledge Page

**Location:** `cortex-ui/src/features/knowledge/`

- Add project dropdown in `KnowledgeHeader.tsx` alongside existing knowledge_type filter
- Populate from `useProjects()` hook
- Default: "All Projects" (no filter)
- When selected, pass `project_id` to `useKnowledgeSummaries()` hook
- Hook passes as query param to `/api/knowledge-items/summary?project_id={id}`

### Query Key Patterns

```typescript
// Project knowledge sources (new)
projectKnowledgeKeys = {
  all: ["projects", "knowledge"] as const,
  byProject: (projectId: string) => ["projects", projectId, "knowledge-sources"] as const,
}

// Knowledge summaries (modified - add project_id to key)
knowledgeKeys.summaries: (filter?) => [...knowledgeKeys.all, "summaries", filter] as const
// filter now includes optional project_id
```

## UI Standards Compliance

- Uses Radix UI primitives from `src/features/ui/primitives/`
- Tron-inspired glassmorphism styling via `glassCard` and `glassmorphism` from `styles.ts`
- Static Tailwind classes only (no dynamic construction)
- Dark mode support on all elements
- Keyboard accessible with proper ARIA attributes
- Responsive layout with `min-w-0` on flex containers
- Follows TanStack Query patterns with `STALE_TIMES` and `DISABLED_QUERY_KEY`

## Implementation Priority

1. Backend: Add metadata filter to knowledge summary service
2. Backend: New project knowledge-sources endpoint + project_id param on summary endpoint
3. Frontend: Project Knowledge tab (KnowledgeTab + components + hooks + services)
4. Frontend: Knowledge page project filter dropdown
