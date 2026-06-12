# Local Project Scanner — Web UI Plan (Deferred)

## Status: Deferred

This document captures the web UI features for the Local Project Scanner that are **deferred to a future development cycle**. The v1 implementation (see [local-project-scanner-plan.md](./local-project-scanner-plan.md)) delivers the full scanning and setup flow via Claude Code CLI and MCP tools.

The web UI can be built on top of the same backend API endpoints created in v1.

---

## Why Deferred

1. **CLI-first user base**: Most Cortex users interact via Claude Code. The MCP tool flow covers the primary use case.
2. **Docker filesystem complexity**: The web UI would need the same volume mount as the CLI flow, but users might expect to type any path — needs clear UX around the mount constraint.
3. **AI description generation**: In CLI mode, Claude Code generates descriptions for free. The web UI would need a separate AI provider integration for description generation.
4. **Scope control**: The scanner backend + MCP tools are already substantial. Adding a full frontend feature doubles the scope.

---

## Planned Web UI Features

### 3-Step Wizard (`/scanner` page)

**Step 1: Scan**
- Text input for directory path (constrained to mounted volume root)
- "Scan" button with loading spinner
- Displays count of found repos immediately
- Error messaging if scanner is not enabled or volume not mounted

**Step 2: Review & Select**
- List of detected projects with checkboxes (all new checked by default)
- Each card shows: folder name, GitHub URL, detected languages, status badges
- Status badges: "New" (green), "Already in Cortex" (yellow/unchecked), "No Remote" (gray), "Group" (blue)
- Project groups displayed with visual hierarchy (parent + indented children)
- Filter/search within results
- Summary bar: "23 selected of 47 found (3 project groups)"

**Step 3: Configure & Apply**
- Template editor form with ScanTemplate fields
- "Save as Default Template" / "Load Saved Template" options
- AI description generation toggle (requires AI provider selection — see below)
- Time estimate displayed: "Estimated time: ~15 minutes (23 projects, 20 README crawls)"
- Review summary before applying
- "Apply" button → progress tracking using existing `useProgress` pattern
- Per-project status updates during creation

### Frontend Feature Structure

```
src/features/scanner/
├── components/
│   ├── ScanDirectoryForm.tsx       # Path input + scan button
│   ├── ScanResultsList.tsx         # List with checkboxes
│   ├── ScanResultCard.tsx          # Individual project card
│   ├── ProjectGroupCard.tsx        # Group parent with child list
│   ├── ScanTemplateEditor.tsx      # Template configuration form
│   ├── ScanApplyProgress.tsx       # Progress tracking during apply
│   ├── AiProviderSelector.tsx      # Provider selection for descriptions
│   └── index.ts
├── hooks/
│   └── useScannerQueries.ts        # Query keys, scan/apply mutations
├── services/
│   └── scannerService.ts           # API calls
├── types/
│   └── index.ts                    # TypeScript types
└── views/
    └── ScannerView.tsx             # Main view orchestrating the wizard
```

### Query Hooks

```typescript
export const scannerKeys = {
  all: ["scanner"] as const,
  scan: (scanId: string) => [...scannerKeys.all, "scan", scanId] as const,
  templates: () => [...scannerKeys.all, "templates"] as const,
};

// useScanDirectory() - mutation → POST /api/scanner/scan
// useScanResults(scanId) - query → GET /api/scanner/results/{scan_id}
// useApplyScan() - mutation → POST /api/scanner/apply
// useEstimateApply() - query → GET /api/scanner/estimate
// useScanTemplates() - query → GET /api/scanner/templates
// useSaveScanTemplate() - mutation → POST /api/scanner/templates
// useDeleteScanTemplate() - mutation → DELETE /api/scanner/templates/{id}
```

### Navigation

- Dedicated page: `/scanner` accessible from the sidebar
- Icon: `FolderSearch` (Lucide)
- Visible only when `SCANNER_ENABLED=true` (check via `/api/scanner/status` endpoint)

---

## AI Description Generation (Web UI)

In the CLI flow, Claude Code generates descriptions. The web UI needs a different approach:

### Backend Description Generation Endpoint

```
POST /api/scanner/generate-descriptions
{
    "scan_id": "uuid",
    "project_ids": ["uuid1", "uuid2"],
    "provider": "openai" | "anthropic" | "openrouter"  // user-selected
}
```

### Provider Selection Flow

1. Before description generation, query available AI providers: `GET /api/settings/providers`
2. If 0 providers configured → disable description generation, show message
3. If 1 provider configured → use it automatically
4. If 2+ providers configured → show selector dropdown, let user choose
5. Validate provider has working API key before starting generation

### Implementation Notes

- Use the existing `agents/` infrastructure for LLM calls
- Each description generation is a lightweight prompt: "Given this README, write a 1-2 sentence project description"
- Rate limit: generate descriptions sequentially to avoid burning API quota
- Cache generated descriptions in `cortex_scan_projects.description` column (add to schema)

---

## Additional Web-Only Features

### Scan History Page

- List of past scans with timestamps, project counts, and status
- Ability to view past scan results (within 24h TTL)
- Re-run expired scans with one click

### Template Management UI

- Dedicated template management section
- Create, edit, delete, and set default templates
- Template import/export (JSON)

### Bulk Operations

- Select multiple existing Cortex projects → "Re-scan" to check for updates
- Bulk delete projects created by a scan (undo operation)
- Bulk re-crawl knowledge sources for scanned projects

---

## Prerequisites from v1

The web UI depends on these v1 backend components being complete:
- [ ] Scanner API endpoints (`/api/scanner/*`)
- [ ] Database tables (`cortex_scan_results`, `cortex_scan_projects`, `cortex_scanner_templates`)
- [ ] Scanner service with config file writing
- [ ] Docker volume mount configuration

No v1 backend changes are needed for the web UI — it uses the same API endpoints.

---

## Estimated Scope

| Component | Effort |
|-----------|--------|
| Frontend feature (wizard, cards, forms) | Medium-Large |
| AI description generation endpoint | Small |
| Provider selector component | Small |
| Scan history page | Small |
| Template management UI | Small |
| Navigation integration | Trivial |
| **Total** | **Medium-Large** |

---

## When to Build

Build the web UI when:
1. v1 CLI flow is proven stable and users request a web interface
2. The scanner backend has been exercised enough to surface edge cases
3. There's a clear need for non-Claude-Code users to access scanning
