# Generative UI Integration: A2UI in Cortex

**Date**: 2026-03-24
**Status**: Draft
**Scope**: Integrate the Second Brain's A2UI (Agent-to-UI) generative UI system into Cortex for rich HITL approvals, chat responses, and knowledge display. Companion spec to [Workflows 2.0: DAG Orchestration Engine Design](2026-03-24-workflows-2-orchestration-engine-design.md).

---

## Table of Contents

1. [Context & Motivation](#1-context--motivation)
2. [Design Decisions](#2-design-decisions)
3. [Integration Architecture](#3-integration-architecture)
4. [Integration Use Cases](#4-integration-use-cases)
5. [Graceful Degradation](#5-graceful-degradation)
6. [Shared Type Definitions](#6-shared-type-definitions)
7. [Database Impact](#7-database-impact)
8. [Frontend Changes in Cortex](#8-frontend-changes-in-cortex)
9. [Configuration](#9-configuration)
10. [Migration & Rollout](#10-migration--rollout)

---

## 1. Context & Motivation

### The Trinity

Three repos live under `~/projects/Trinity/`:

| Repo | Role | Stack |
|------|------|-------|
| **Cortex** (`cortex/`) | Brain & control plane | React 18 + TypeScript + Vite + Tailwind. FastAPI backend. Supabase DB. |
| **Remote-Coding-Agent** (`remote-coding-agent/`) | Execution engine | TypeScript/Bun. DAG workflows, Claude Agent SDK, git worktrees. |
| **Second Brain** (`second-brain-research-dashboard/`) | Generative UI engine | React 19 + TypeScript + Vite + Tailwind. FastAPI backend with PydanticAI. |

### Why A2UI?

The [Workflows 2.0 spec](2026-03-24-workflows-2-orchestration-engine-design.md) introduces HITL approval gates where users review plans, PR diffs, deployment checklists, and custom node outputs before a workflow proceeds. Rendering these payloads as raw markdown is functional but loses structure. The Second Brain already solves this problem with its A2UI (Agent-to-UI) protocol: a JSON specification that maps content to 50+ typed React components (StatCard, ComparisonTable, CodeBlock, ExecutiveSummary, StepCard, ProgressRing, DataTable, and more).

Integrating A2UI into Cortex enables:

- **Rich HITL approvals** — Structured dashboards with stats, diffs, checklists, and progress indicators instead of markdown walls.
- **Generative chat responses** — Chat messages rendered as visual component layouts when the content warrants it (comparisons, code, summaries).
- **Enhanced knowledge display** — RAG results rendered as RepoCards, CodeBlocks, LinkCards, and KeyTakeaways instead of plain text chunks.

### Critical Constraint: DRY

**The Second Brain repo is the single source of truth for ALL A2UI code.** Cortex never duplicates components, renderers, or generation logic. It consumes the Second Brain's pre-built component library (frontend) and calls it over HTTP (backend). Cortex's role is thin glue code that connects its data flows to the Second Brain's rendering and generation capabilities.

---

## 2. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Frontend component sharing** | Pre-built library (`@trinity/a2ui`) consumed as a local dependency | Second Brain builds its A2UI components into a distributable bundle. Cortex references it via `"file:../../second-brain-research-dashboard/frontend"` in `package.json`. All internal `@/` aliases resolve at the Second Brain's build time, producing clean exports. |
| **Backend generation** | HTTP service call to Second Brain's FastAPI container | Generation logic (LLM pipeline, content analysis, layout selection) stays in the Second Brain. Cortex sends content, receives components. |
| **LLM orchestration** | Second Brain service uses its own PydanticAI setup; Cortex does not inject its agent infrastructure | The A2UI generation pipeline is self-contained. Forcing Cortex's agent infrastructure onto it creates tight coupling for no benefit. Cortex controls what content to send and when, not how the LLM generates components. |
| **Docker deployment** | Second Brain added as a service in Cortex's `docker-compose.yml` under a `trinity` profile | Opt-in. Users without the Second Brain repo run Cortex standalone with no impact. Single `docker compose --profile trinity up` starts everything. |
| **Graceful degradation** | A2UI is always a UX enhancement, never a blocking dependency | If the service is unavailable, Cortex renders raw markdown. No workflow blocks, no errors surfaced to users. |
| **Type sharing** | Frontend: import from `@trinity/a2ui` package. Backend: minimal Pydantic models matching the JSON schema | TypeScript types come from the library's bundled declarations. Python models are the protocol's Python representation, not a duplication of logic. |
| **Storage** | A2UI component arrays stored as JSONB in existing columns | No new tables. Approval payloads, chat messages, and knowledge results use existing or minimally extended schemas. |
| **React version gap** | Pin shared React peer dependency; use compatibility boundary if needed | Cortex runs React 18, Second Brain runs React 19. The A2UI components use standard React patterns that work in both versions. If breakage occurs, a thin compatibility wrapper isolates the boundary. |

---

## 3. Integration Architecture

### Frontend Integration (Pre-Built Library)

The Second Brain builds its A2UI components into a distributable library bundle that Cortex consumes as a local dependency. This avoids the `@/` alias collision problem: the Second Brain's ~40 component files import from `@/components/ui/card`, `@/lib/utils`, etc. using the `@/` alias, which resolves to the Second Brain's own `src/` at its build time. If Cortex tried to import the raw source, Vite would resolve `@/` to Cortex's `src/`, breaking every import.

#### Second Brain Build Step

The Second Brain adds a library build target to its Vite config:

```bash
# In second-brain-research-dashboard/frontend/
vite build --mode lib
```

This produces:
- `dist/a2ui.js` — Bundled ESM module with all A2UI components
- `dist/a2ui.d.ts` — TypeScript declarations

The library entry point exports: `A2UIRenderer`, `A2UIRendererList`, `a2uiCatalog`, `isComponentRegistered`, and all component types.

The library build externalizes `react`, `react-dom`, `framer-motion`, and `lucide-react` so the host app provides its own versions (see Compatibility Considerations below).

#### Cortex Consumes the Library

**`cortex-ui/package.json`** — add local dependency:

```json
{
  "dependencies": {
    "@trinity/a2ui": "file:../../second-brain-research-dashboard/frontend"
  }
}
```

This enables any Cortex component to import directly:

```typescript
import { A2UIRenderer, A2UIRendererList } from '@trinity/a2ui'
import { a2uiCatalog } from '@trinity/a2ui'
```

No Vite alias configuration is needed. No `tsconfig.json` path mapping is needed. The `@trinity/a2ui` package resolves through standard Node module resolution, and TypeScript picks up the bundled `.d.ts` declarations automatically.

**Development workflow (HMR)**: Vite does not automatically watch `node_modules` or symlinked local packages for changes. When developing A2UI components in the Second Brain repo:
1. Run `npm run build:lib -- --watch` in the Second Brain frontend to continuously rebuild on changes
2. In Cortex's `vite.config.ts`, add the Second Brain dist path to the watcher:
   ```typescript
   server: {
     watch: {
       // Watch the pre-built library for changes during development
       ignored: ['!**/node_modules/@trinity/a2ui/**']
     }
   }
   ```
3. Vite will detect the updated `dist/a2ui.js` and trigger HMR in Cortex

This gives a fast development loop: edit component in Second Brain → auto-rebuild → Cortex hot-reloads.

#### Compatibility Considerations

**React versions**: Cortex uses React 18; the Second Brain uses React 19. The library build externalizes `react` and `react-dom`, so Cortex provides its own React 18 at runtime. The A2UI components use standard patterns (functional components, hooks, JSX) that are forward-compatible. If a React 19-only API is used in a component, Cortex wraps the import in a compatibility boundary that catches and falls back gracefully. In practice, the A2UI component catalog avoids React 19-specific features (Actions, `use()`, etc.) because it was built for broad compatibility.

**framer-motion**: The library build externalizes `framer-motion` so Cortex provides its own version. The Second Brain uses framer-motion v12; Cortex uses v11. `framer-motion` should be listed as a peer dependency of `@trinity/a2ui`. Only `A2UIRendererList` uses framer-motion (for stagger animations). If version incompatibility causes runtime issues, Cortex's thin `A2UIDisplay.tsx` wrapper can re-implement the stagger animation using Cortex's own framer-motion v11, bypassing the library's `A2UIRendererList` for that specific behavior.

**lucide-react**: The Second Brain uses `lucide-react` ^0.563; Cortex uses ^0.441. The library build externalizes `lucide-react` so the host app provides icons. If icon names were added between versions, missing icons render as empty spans (graceful degradation). Cortex should upgrade `lucide-react` when convenient to close the gap.

**Tailwind CSS**: Both repos use Tailwind v4 with dark themes. With the pre-built library approach, Tailwind classes used by A2UI components are resolved at the Second Brain's build time. Cortex does not need to add Second Brain source directories to its content paths. However, Second Brain's custom animations (`scroll`, `shimmer`, `fade-in`) must be replicated in Cortex's `tailwind.config.js` or the library must inline them as CSS keyframes in the bundle.

**Tailwind theme variable alignment**: The `@trinity/a2ui` library outputs Tailwind utility classes that reference CSS custom properties (e.g., `bg-primary`, `text-muted-foreground`). At runtime, these resolve against Cortex's `globals.css` theme variables, not the Second Brain's. This is usually desirable — components inherit Cortex's visual theme. However:

- **Missing variables**: If Second Brain defines theme variables that Cortex does not (e.g., `--chart-1`, `--ring`), components using those classes will render with no color. Audit Second Brain's `globals.css` for custom properties and ensure Cortex's CSS defines them.
- **Hardcoded values**: Some A2UI components may use hardcoded hex/HSL values instead of theme variables. These will not adapt to Cortex's theme. Flag and replace during integration testing.
- **Dark mode**: Both repos use dark themes, but HSL values may differ. Verify visual consistency by rendering each component type in Cortex's theme during Phase 2 integration testing.

**`cn()` utility**: The `clsx`/`tailwind-merge` utility `cn()` is bundled within the `@trinity/a2ui` library. No cross-repo dependency on this function.

### Backend Integration (HTTP Service)

The Second Brain runs as a FastAPI service in Docker. Cortex calls it over HTTP when it needs A2UI generation. The generation pipeline (content analysis, layout selection, component generation via LLM) runs entirely inside the Second Brain container.

**Endpoint**: `POST http://trinity-a2ui:8054/api/a2ui/generate`

**Request**:
```json
{
  "content": "## Plan Summary\n\nThis PR adds rate limiting...",
  "context": "workflow_approval",
  "content_type": "plan_review"
}
```

**Response**:
```json
{
  "components": [
    {
      "type": "a2ui.ExecutiveSummary",
      "id": "es-001",
      "props": {
        "title": "Rate Limiting Implementation Plan",
        "summary": "Adds token bucket rate limiting to all API endpoints...",
        "highlights": ["3 files modified", "Redis-backed", "Per-user limits"]
      },
      "zone": "hero"
    },
    {
      "type": "a2ui.StepCard",
      "id": "sc-001",
      "props": {
        "step": 1,
        "title": "Add Redis dependency",
        "description": "Install redis-py and configure connection pool"
      },
      "zone": "content"
    }
  ],
  "analysis": {
    "content_type": "plan",
    "structure": {"headings": 4, "code_blocks": 2, "lists": 3},
    "suggested_layout": "dashboard"
  }
}
```

#### Required Second Brain Development

The Second Brain does not currently expose a standalone A2UI generation endpoint. The following work must be completed in the Second Brain repo before Cortex can integrate:

1. **New REST endpoint**: `POST /api/a2ui/generate` — Accepts `content`, `context`, and `content_type` fields; returns an A2UI component array and analysis metadata (schema shown above). This requires decoupling the generation logic from the AG-UI streaming protocol so it can be called as a standalone request/response operation.

2. **Dockerfile**: Add a production Dockerfile to the Second Brain repo for containerized deployment. The image runs the FastAPI backend and exposes the A2UI generation endpoint. Must include a `/health` endpoint for Docker healthchecks.

3. **Port configuration**: Expose on port 8054 by default, configurable via `A2UI_PORT` environment variable.

4. **Externalized LLM config**: Accept `OPENROUTER_API_KEY` as an environment variable (already used internally) so the container can be configured via Cortex's Docker Compose environment block.

#### A2UI Service Adapter in Cortex

A thin adapter layer in Cortex handles HTTP communication and typing. No generation logic lives here.

```
python/src/server/services/generative_ui/
├── a2ui_client.py          # HTTP client to Second Brain service
├── a2ui_models.py          # Pydantic models for A2UI component specs
└── a2ui_service.py         # High-level service used by HITL, chat, knowledge
```

**`a2ui_client.py`**: Makes HTTP calls to the Second Brain endpoint. Handles timeouts, connection errors, and retries. Returns typed responses or `None` on failure.

**`a2ui_models.py`**: Pydantic models that match the A2UI JSON schema. These are the Python representation of the protocol, not a duplication of logic. They validate the JSON coming back from the Second Brain service.

**`a2ui_service.py`**: High-level methods called by other Cortex services:
- `generate_approval_components(node_output, approval_type)` — Used by the HITL Router
- `generate_chat_components(message_content)` — Used by the chat service
- `generate_knowledge_components(search_results)` — Used by the knowledge display layer
- `is_available()` — Health check, cached with TTL

### Docker Compose Integration

Added to Cortex's `docker-compose.yml` under a `trinity` profile so it is opt-in:

```yaml
  trinity-a2ui:
    build:
      context: ../second-brain-research-dashboard
      dockerfile: Dockerfile
    ports:
      - "8054:8054"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    networks:
      - default
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8054/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    profiles:
      - trinity
```

Users who do not have the Second Brain repo cloned simply omit the `trinity` profile. Cortex detects the absence of the service and disables A2UI features transparently.

---

## 4. Integration Use Cases

### Use Case 1: HITL Approval Rendering

When a workflow node hits `waiting_approval` state (see [Workflows 2.0 spec, Section 5](2026-03-24-workflows-2-orchestration-engine-design.md#5-hitl-router--approval-flow)):

1. DAG engine collects the node's output (raw markdown/text/JSON)
2. HITL Router calls `a2ui_service.generate_approval_components(output, approval_type)`
3. `a2ui_service` sends content to `POST http://trinity-a2ui:8054/api/a2ui/generate`
4. Second Brain's LLM pipeline analyzes content and returns an A2UI component array
5. Component array stored in `approval_requests.payload` (JSONB column, already defined in Workflows 2.0 schema)
6. Cortex UI receives the approval via SSE, renders components using `A2UIRenderer` (imported from `@trinity/a2ui`)
7. Telegram receives a text summary with approve/reject buttons and a link to the full UI view (Telegram cannot render React components)

**Approval type mapping** (from Workflows 2.0 spec):

| Approval Type | A2UI Components Used |
|---|---|
| `plan_review` | ExecutiveSummary, StepCard list, StatCard (scope estimate), CodeBlock |
| `pr_review` | StatCard (files changed, +/-), ComparisonTable (before/after), CodeBlock (key diffs), ProgressRing (test coverage) |
| `deploy_gate` | StatCard (environment, build status), ChecklistItem list, CalloutCard (warnings) |
| `custom` | Components generated dynamically from node output content |

### Use Case 2: Chat with Generative UI

When Cortex's chat agent produces a response that benefits from structured display:

1. Chat agent generates a response containing structured data (comparisons, statistics, code, multi-step explanations)
2. Backend checks if A2UI service is available; if not, stores raw text only
3. If available, routes response through `a2ui_service.generate_chat_components(response_text)`
4. Chat message stored with both `content` (raw text) and `a2ui_components` (JSONB, nullable)
5. Frontend chat bubble checks for `a2ui_components`:
   - If present: renders A2UI component layout via `A2UIRenderer`
   - If absent: renders raw markdown (existing behavior)
6. User can toggle between "rich" and "raw" views per message

### Use Case 3: Knowledge Base Display

When RAG search returns results:

1. Knowledge service returns document chunks, code examples, and source metadata
2. If A2UI service is available, transforms results into component arrays on-the-fly
3. Knowledge UI renders results as RepoCards, CodeBlocks, LinkCards, KeyTakeaways
4. Richer than current plain-text display, with structured navigation and visual hierarchy
5. Results are rendered on-the-fly, not stored — regenerated each time the query runs

**Latency mitigation**: RAG search results are rendered in two passes:
1. **Immediate**: Raw text results render instantly in the UI using existing markdown display (no A2UI service call)
2. **Async enhancement**: In the background, the frontend calls `useA2UIGeneration` to request component generation. When the A2UI service responds, components fade in and replace the markdown view

This ensures search feels instant while A2UI components load asynchronously. If the A2UI service is slow or unavailable, the user still has the full text results immediately.

**Alternative for high-traffic deployments**: Pre-generate A2UI representations at document ingestion time (when chunks are embedded). Store the component arrays alongside the document chunks in Supabase. At query time, return pre-generated components directly — zero LLM latency. This trades storage space for query speed.

---

## 5. Graceful Degradation

**The Second Brain service is OPTIONAL. Cortex must function fully without it.**

### Degradation Behavior

| Scenario | Behavior |
|---|---|
| `trinity-a2ui` service not running | All A2UI features silently disabled. `a2ui_service.is_available()` returns `false`. |
| `trinity-a2ui` service unreachable (network error) | Same as not running. Client catches `ConnectionError`, logs warning, returns `None`. |
| Generation request times out | Returns `None`. Caller falls back to raw content rendering. Timeout is configurable (default 10s). |
| Generation returns malformed JSON | Pydantic validation fails. Logged as warning. Returns `None`. Caller renders raw content. |
| Second Brain repo not cloned | Docker Compose `trinity` profile not activated. No container started. Cortex runs standalone. |

### Implementation Strategy

**Auto-detection on startup**: When the Cortex server starts, `a2ui_service` calls the health endpoint (`GET http://trinity-a2ui:8054/health`). If reachable, sets `a2ui_available = True`. If not, sets `a2ui_available = False` and logs an info message (not a warning — this is expected for users without the Second Brain).

**Periodic re-check**: Every 60 seconds, if `a2ui_available` is `False`, the service re-checks the health endpoint. This handles the case where the Second Brain container starts after Cortex.

**Per-request guard**: Every public method on `a2ui_service` checks `is_available()` first. If `False`, returns `None` immediately without attempting an HTTP call. Callers always handle `None` as "render raw content."

**No exceptions surfaced**: Connection errors, timeouts, and validation failures are caught inside `a2ui_client.py` and logged. No exceptions propagate to callers. The A2UI layer is a pure UX enhancement that never disrupts core functionality.

---

## 6. Shared Type Definitions

The A2UI component spec (`A2UIComponent` type) is the contract between the Second Brain (producer) and Cortex (consumer).

### TypeScript (Frontend)

The Second Brain defines the canonical TypeScript types. Cortex imports them from the `@trinity/a2ui` package:

```typescript
// In any Cortex component
import type { A2UIComponent } from '@trinity/a2ui'
```

No type duplication. Layout information is inline within the `A2UIComponent` type (the `layout` and `zone` fields). If the Second Brain adds a new component type, Cortex picks it up after rebuilding the library.

### Python (Backend)

Cortex defines minimal Pydantic models in `a2ui_models.py` that match the JSON schema:

```python
class A2UIComponent(BaseModel):
    type: str                          # e.g., "a2ui.StatCard"
    id: str                            # Unique component ID
    props: dict[str, Any]              # Component-specific props
    children: list["A2UIComponent"] | None = None
    layout: dict[str, Any] | None = None
    zone: str | None = None            # SemanticZone: "hero", "content", "resources"
    styling: dict[str, Any] | None = None  # Optional component styling overrides

class A2UIGenerationRequest(BaseModel):
    content: str
    context: str | None = None
    content_type: str | None = None

class A2UIGenerationResponse(BaseModel):
    components: list[A2UIComponent]
    analysis: dict[str, Any] | None = None
```

This is not duplication of logic. It is the Python representation of the same JSON protocol, necessary for type-safe HTTP communication and JSONB storage validation.

---

## 7. Database Impact

**No new tables.** A2UI component arrays are stored as JSONB within existing or already-planned columns.

| Location | Column | Change | Notes |
|---|---|---|---|
| `approval_requests.payload` | JSONB | No change | Already defined in Workflows 2.0 schema (migration 031). Contains A2UI component arrays. |
| `chat_messages` | `a2ui_components` | Add nullable JSONB column | Migration 035. Null when A2UI is unavailable or content doesn't warrant rich rendering. |
| Knowledge results | _(none)_ | No storage | Rendered on-the-fly from search results. Not persisted. |

The `a2ui_components` column addition to the `chat_messages` table is migration 035. The column is nullable with no default, so existing rows are unaffected.

---

## 8. Frontend Changes in Cortex

### New Feature Directory

```
cortex-ui/src/features/generative-ui/
├── components/
│   └── A2UIDisplay.tsx          # Wrapper that imports A2UIRenderer from @trinity/a2ui
├── hooks/
│   └── useA2UIGeneration.ts     # Hook to request A2UI generation from backend
└── types/
    └── index.ts                 # Re-exports types from @trinity/a2ui package
```

This directory is intentionally thin. It is glue code, not a component library.

### `A2UIDisplay.tsx`

Wrapper component that handles:
- Importing `A2UIRenderer` from `@trinity/a2ui`
- Error boundary around the renderer (if a component fails, falls back to raw content)
- Loading state while components are being generated
- Empty state when no components are available

```typescript
interface A2UIDisplayProps {
  components: A2UIComponent[] | null
  fallback: React.ReactNode    // Raw markdown/text to show if components are null
}
```

### `useA2UIGeneration.ts`

TanStack Query mutation hook that calls the Cortex backend to generate A2UI components:

```typescript
export function useA2UIGeneration() {
  return useMutation({
    mutationFn: (request: A2UIGenerationRequest) =>
      generativeUiService.generate(request),
  })
}
```

Follows the same patterns as all other Cortex mutation hooks (see [QUERY_PATTERNS.md](../../PRPs/ai_docs/QUERY_PATTERNS.md)).

### Integration Points in Existing Features

The `A2UIDisplay` component is used in three places:

1. **Workflows feature** — `ApprovalDetail.tsx` renders `approval.payload` through `A2UIDisplay`
2. **Chat feature** — Chat message bubbles check for `a2ui_components` and render through `A2UIDisplay`
3. **Knowledge feature** — Search results optionally rendered through `A2UIDisplay`

Each integration follows the same pattern: check for A2UI data, render if present, fall back to existing rendering if not.

---

## 9. Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `A2UI_SERVICE_URL` | `http://trinity-a2ui:8054` | URL of the Second Brain's A2UI generation service |
| `A2UI_ENABLED` | `auto` | Feature flag. `auto` = enabled if service is reachable. `true` = always attempt. `false` = always disabled. |
| `A2UI_GENERATION_TIMEOUT` | `10` | Timeout in seconds for generation HTTP calls |
| `OPENROUTER_API_KEY` | _(none)_ | Required by the Second Brain service for LLM calls. Passed through Docker Compose environment. |

### Settings

No UI settings toggle for A2UI. The feature is transparently enabled when the service is available and disabled when it is not. Users do not need to configure anything beyond starting the Docker profile.

---

## 10. Migration & Rollout

Each phase is independently deployable. The system degrades gracefully at every stage.

### Phase 1: Infrastructure

**Goal**: Second Brain running as a Docker service, Vite alias configured, thin adapter in place.

- Complete Required Second Brain Development (see Section 3): `POST /api/a2ui/generate` endpoint, Dockerfile, port config
- Add `trinity-a2ui` service to `docker-compose.yml` under `trinity` profile
- Add `"@trinity/a2ui": "file:../../second-brain-research-dashboard/frontend"` to Cortex's `package.json`
- Replicate Second Brain's custom Tailwind animations (`scroll`, `shimmer`, `fade-in`) in Cortex's `tailwind.config.js`
- Create `python/src/server/services/generative_ui/` with `a2ui_client.py`, `a2ui_models.py`, `a2ui_service.py`
- Create `cortex-ui/src/features/generative-ui/` with `A2UIDisplay.tsx`, `useA2UIGeneration.ts`, `types/index.ts`
- Verify: `A2UIRenderer` renders a hardcoded component array in a test page
- **No production UI changes.** Existing behavior unchanged.

### Phase 2: HITL Approvals

**Goal**: Workflow approval payloads rendered as A2UI components.

- Wire `a2ui_service.generate_approval_components()` into the HITL Router's approval creation flow
- `ApprovalDetail.tsx` uses `A2UIDisplay` to render `approval.payload`
- Fallback: if `payload` contains no A2UI components (or A2UI is unavailable), render as raw markdown
- Test with all four approval types: `plan_review`, `pr_review`, `deploy_gate`, `custom`

### Phase 3: Chat Responses

**Goal**: Chat messages optionally rendered with A2UI components.

- Add `a2ui_components` nullable JSONB column to `chat_messages` table (migration 035)
- Chat backend calls `a2ui_service.generate_chat_components()` for messages with structured content
- Chat frontend renders `A2UIDisplay` when `a2ui_components` is present
- Add raw/rich toggle per message
- Fallback: text rendering when A2UI is unavailable

### Phase 4: Knowledge Display

**Goal**: RAG search results rendered with A2UI components.

- Knowledge display layer calls `a2ui_service.generate_knowledge_components()` on-the-fly
- Results rendered as RepoCards, CodeBlocks, LinkCards, KeyTakeaways
- No storage — components generated per query
- Fallback: current plain-text display when A2UI is unavailable

---

## File Location Summary

### Backend (Python)

```
python/src/server/services/generative_ui/
├── __init__.py
├── a2ui_client.py          # HTTP client to Second Brain service
├── a2ui_models.py          # Pydantic models for A2UI component specs
└── a2ui_service.py         # High-level service (generate, health check)
```

### Frontend (TypeScript)

```
cortex-ui/src/features/generative-ui/
├── components/
│   └── A2UIDisplay.tsx      # Wrapper around @trinity/a2ui's A2UIRenderer
├── hooks/
│   └── useA2UIGeneration.ts # TanStack Query mutation hook
└── types/
    └── index.ts             # Re-exports from @trinity/a2ui package
```

### Configuration

```
cortex-ui/package.json         # @trinity/a2ui local dependency
cortex-ui/tailwind.config.js   # Custom animation replicas (scroll, shimmer, fade-in)
docker-compose.yml                  # trinity-a2ui service (trinity profile)
```
