# Second Brain: A2UI Generation Service for Cortex

**Date:** 2026-03-25
**Repo:** `Trinity/second-brain-research-dashboard`
**Branch:** `feat/a2ui-service`
**Depends on:** Cortex Workflows 2.0 Phases 1-4 (merged to main)

## Goal

Expose the Second Brain's A2UI component generation pipeline as a standalone REST endpoint that Cortex can call for rendering workflow approval payloads. Add containerization so it can run as a Docker service alongside Cortex.

The Second Brain already has all 59 A2UI components, a content analyzer, layout selector, and LLM-driven generation pipeline. This plan adds the HTTP interface and Docker packaging — no new AI logic needed.

## Architecture Context

Cortex's `A2UIService` (`python/src/server/services/generative_ui/a2ui_service.py`) already calls:
- `POST http://trinity-a2ui:8054/api/a2ui/generate` for custom approval types
- `GET http://trinity-a2ui:8054/health` to check availability

Cortex gracefully degrades when the service is unavailable (returns `None`, falls back to raw markdown). Standard approval types (`plan_review`, `pr_review`, `deploy_gate`) use deterministic templates and never call the A2UI service.

## Current State

**What exists:**
- 59 A2UI React components across 11 categories in `frontend/src/components/A2UI/`
- `A2UIRenderer.tsx` — dynamic component renderer by type string
- `agent/content_analyzer.py` — markdown parsing, link/code/table extraction
- `agent/layout_selector.py` — 10 layout strategies (dashboard, timeline, comparison, etc.)
- `agent/llm_orchestrator.py` — PydanticAI agent for component spec generation
- `agent/a2ui_generator.py` — base A2UI component infrastructure
- `agent/main.py` — AG-UI SSE protocol endpoint (not REST)

**What's missing:**
- Standalone REST endpoint (`POST /api/a2ui/generate`)
- Health check endpoint (`GET /health`)
- Dockerfile for containerized deployment
- Request/response Pydantic models matching Cortex's `A2UIGenerationRequest`/`A2UIGenerationResponse`
- Environment variable configuration for LLM API keys
- Docker Compose integration in Cortex's `docker-compose.yml`

## Tech Stack

- Python 3.11+ / FastAPI (existing)
- PydanticAI (existing)
- OpenRouter for LLM calls (existing)
- React 19 / TypeScript / Vite (existing frontend — for `@trinity/a2ui` package build)

## File Structure

### Files to Create

```
agent/
├── a2ui_service_api.py        # FastAPI app with REST endpoints
├── a2ui_request_models.py     # Pydantic request/response models
└── Dockerfile                 # Container definition

frontend/
└── package.json               # Add build script for @trinity/a2ui library
```

### Files to Modify

```
agent/main.py                  # Mount a2ui_service_api alongside AG-UI endpoint
agent/llm_orchestrator.py      # Extract generate() into a reusable async function
cortex/docker-compose.yml      # Add trinity-a2ui service under trinity profile
```

---

## Task 1: Request/Response Models

**File:** `agent/a2ui_request_models.py`

Pydantic models matching Cortex's client expectations:

```python
"""Request and response models for the A2UI generation REST API.

These must match the models in Cortex's a2ui_models.py.
"""

from typing import Any

from pydantic import BaseModel, Field


class A2UIGenerationRequest(BaseModel):
    """Request payload from Cortex."""
    content: str = Field(description="Raw content to render (markdown, text, etc.)")
    context: str | None = Field(None, description="Usage context, e.g. 'workflow_approval'")
    content_type: str | None = Field(None, description="Content category, e.g. 'plan_review'")


class A2UIComponent(BaseModel):
    """Single A2UI component specification."""
    type: str = Field(description="Component type, e.g. 'a2ui.StatCard'")
    id: str = Field(description="Unique component ID")
    props: dict[str, Any] = Field(default_factory=dict)
    children: list["A2UIComponent"] | None = None
    layout: dict[str, Any] | None = None
    zone: str | None = None
    styling: dict[str, Any] | None = None


class A2UIGenerationResponse(BaseModel):
    """Response payload to Cortex."""
    components: list[A2UIComponent]
    analysis: dict[str, Any] | None = Field(
        None,
        description="Content analysis metadata (content_type, structure, suggested_layout)",
    )
```

---

## Task 2: A2UI Service API

**File:** `agent/a2ui_service_api.py`

Standalone FastAPI application (or sub-router mountable onto existing app):

```python
"""A2UI Generation REST API.

Exposes the Second Brain's component generation pipeline
as a synchronous REST endpoint for Cortex integration.
"""

import logging
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .a2ui_request_models import (
    A2UIComponent,
    A2UIGenerationRequest,
    A2UIGenerationResponse,
)
from .content_analyzer import ContentAnalyzer
from .layout_selector import LayoutSelector
from .llm_orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)

app = FastAPI(title="Trinity A2UI Generation Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check for Docker and Cortex availability probes."""
    return {"status": "ok", "service": "trinity-a2ui"}


@app.post("/api/a2ui/generate", response_model=A2UIGenerationResponse)
async def generate_components(request: A2UIGenerationRequest):
    """Generate A2UI components from raw content.

    Pipeline:
    1. Analyze content (markdown parsing, structure extraction)
    2. Select layout strategy
    3. Generate component specs via LLM
    4. Validate and return
    """
    try:
        # Step 1: Analyze content
        analyzer = ContentAnalyzer()
        analysis = analyzer.analyze(request.content)

        # Step 2: Select layout
        selector = LayoutSelector()
        layout = selector.select(analysis, context=request.context)

        # Step 3: Generate components
        orchestrator = LLMOrchestrator()
        raw_components = await orchestrator.generate(
            content=request.content,
            analysis=analysis,
            layout=layout,
            content_type=request.content_type,
        )

        # Step 4: Convert to response format
        components = [
            A2UIComponent(
                type=c.get("type", "a2ui.Section"),
                id=c.get("id", str(uuid.uuid4())[:8]),
                props=c.get("props", {}),
                children=c.get("children"),
                layout=c.get("layout"),
                zone=c.get("zone"),
                styling=c.get("styling"),
            )
            for c in raw_components
        ]

        return A2UIGenerationResponse(
            components=components,
            analysis={
                "content_type": analysis.get("content_type"),
                "structure": analysis.get("structure"),
                "suggested_layout": layout,
            },
        )
    except Exception as e:
        logger.error(f"A2UI generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})
```

**Important:** The actual integration with `ContentAnalyzer`, `LayoutSelector`, and `LLMOrchestrator` will need adaptation based on their current method signatures. The pattern above shows the intended pipeline — implementation should call the existing functions rather than reimplementing them.

---

## Task 3: Wire into Existing Server

**File to modify:** `agent/main.py`

The existing `main.py` serves the AG-UI SSE endpoint. Mount the A2UI REST API alongside it:

```python
# Option A: Mount as sub-application
from .a2ui_service_api import app as a2ui_app
app.mount("/", a2ui_app)  # or use a shared FastAPI instance

# Option B: Create a shared app and mount both
from fastapi import FastAPI
app = FastAPI()
# Mount AG-UI routes
# Mount A2UI routes
```

The key constraint is that both endpoints share the same LLM configuration (API keys, model selection).

---

## Task 4: Extract Reusable Generation Function

**File to modify:** `agent/llm_orchestrator.py`

The existing `LLMOrchestrator` is tightly coupled to the AG-UI SSE streaming protocol. Extract the core generation logic into a reusable async function:

```python
async def generate_components(
    content: str,
    analysis: dict,
    layout: str,
    content_type: str | None = None,
) -> list[dict]:
    """Generate A2UI component specs from analyzed content.

    Returns list of component dicts (not streamed, not wrapped in SSE events).
    """
    # ... existing generation logic, but returning components directly
    # instead of streaming them via SSE events
```

This allows the AG-UI endpoint to continue using SSE streaming while the REST endpoint calls the same function synchronously.

---

## Task 5: Dockerfile

**File:** `agent/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv pip install --system .

# Copy source
COPY agent/ agent/

# Environment
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8054/health || exit 1

EXPOSE 8054

CMD ["uvicorn", "agent.a2ui_service_api:app", "--host", "0.0.0.0", "--port", "8054"]
```

**Note:** Adjust paths based on actual project structure. The `pyproject.toml` and `uv.lock` must be at the build context root.

---

## Task 6: Docker Compose Integration (in Cortex repo)

**File to modify:** `cortex/docker-compose.yml`

Add under the `trinity` profile:

```yaml
  trinity-a2ui:
    profiles:
      - trinity
    build:
      context: ../second-brain-research-dashboard
      dockerfile: agent/Dockerfile
    container_name: trinity-a2ui
    ports:
      - "${A2UI_PORT:-8054}:8054"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
      - A2UI_MODEL=${A2UI_MODEL:-anthropic/claude-haiku-4-5-20251001}
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8054/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

Usage: `docker compose --profile trinity up -d`

---

## Task 7: @trinity/a2ui Frontend Package Build

**File to modify:** `frontend/package.json`

Add a build script that exports the A2UI components as a consumable library:

```json
{
  "name": "@trinity/a2ui",
  "version": "0.1.0",
  "exports": {
    ".": "./src/components/A2UI/index.ts",
    "./renderer": "./src/components/A2UIRenderer.tsx"
  },
  "scripts": {
    "build:lib": "vite build --config vite.lib.config.ts"
  }
}
```

Create `frontend/vite.lib.config.ts` for library build mode that exports components without bundling React/Tailwind (peer dependencies).

**Cortex consumption:** In `cortex-ui/package.json`:
```json
{
  "dependencies": {
    "@trinity/a2ui": "file:../../second-brain-research-dashboard/frontend"
  }
}
```

This replaces the current raw JSON rendering in `A2UIDisplay.tsx` with the real component library.

**Note:** This is a future enhancement. The current `A2UIDisplay.tsx` renders components as formatted cards, which works for beta. The real library integration can be done when the build pipeline is stable.

---

## Task 8: Environment Configuration

Required environment variables for the A2UI service:

| Env Var | Required | Default | Description |
|---------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | (none) | API key for LLM calls |
| `A2UI_MODEL` | No | `anthropic/claude-haiku-4-5-20251001` | Model for component generation |
| `A2UI_PORT` | No | `8054` | Server port |
| `A2UI_MAX_COMPONENTS` | No | `20` | Max components per response |
| `A2UI_TIMEOUT` | No | `10` | Generation timeout in seconds |

---

## Task 9: Tests

Write tests for:
- `test_a2ui_service_api.py` — test `/health` and `/api/a2ui/generate` endpoints with mock LLM
- `test_a2ui_request_models.py` — validate Pydantic models serialize/deserialize correctly
- Verify response format matches what Cortex's `A2UIClient` expects

---

## Task 10: Integration Verification

1. Build the Docker image: `docker build -f agent/Dockerfile -t trinity-a2ui .`
2. Run: `docker run -p 8054:8054 -e OPENROUTER_API_KEY=... trinity-a2ui`
3. Test health: `curl http://localhost:8054/health`
4. Test generation:
   ```bash
   curl -X POST http://localhost:8054/api/a2ui/generate \
     -H "Content-Type: application/json" \
     -d '{
       "content": "## Plan\n\n1. Add auth\n2. Add tests\n\n- Files: 5\n- Complexity: Medium",
       "context": "workflow_approval",
       "content_type": "plan_review"
     }'
   ```
5. Start via Cortex's Docker Compose:
   ```bash
   cd cortex && docker compose --profile trinity up -d
   ```
6. Verify Cortex can reach it: set `A2UI_SERVICE_URL=http://trinity-a2ui:8054` in Cortex's `.env`
7. Create a custom approval in Cortex — verify A2UI components are generated and rendered

---

## Propagation

| What Changed | How to Propagate |
|---|---|
| New REST endpoint in Second Brain | `docker compose --profile trinity up --build -d` |
| Docker Compose changes in Cortex | `docker compose --profile trinity up -d` |
| @trinity/a2ui package (future) | `cd cortex-ui && npm install` |
| Environment variables | Add `OPENROUTER_API_KEY` to Cortex `.env` |

## Dependencies

- OpenRouter API key for LLM-based component generation
- Cortex must be running with Workflows 2.0
- Network connectivity between Cortex and Second Brain containers
- No new Python package dependencies (uses existing PydanticAI, FastAPI)
