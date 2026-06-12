# Workflows 2.0 Phases 2–4: HITL, Pattern Discovery, Workflow Editor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Workflows 2.0 engine across three independent phases: HITL approvals with A2UI rendering (Phase 2), proactive pattern discovery (Phase 3), and the workflow editor UI (Phase 4).

**Architecture:** Cortex is a Control Plane. Phase 1 (complete) built dispatch, state tracking, SSE, and callback endpoints. Phases 2–4 extend it with approval handling, intelligence, and authoring UI. Each phase is independently deployable.

**Tech Stack:** Python 3.12, FastAPI, Supabase, python-telegram-bot, httpx, anthropic SDK, prefixspan, React 18, TanStack Query v5, @trinity/a2ui

**Spec:** `docs/superpowers/specs/2026-03-24-workflows-2-orchestration-engine-design.md`
**Companion Spec:** `docs/superpowers/specs/2026-03-24-generative-ui-integration-design.md`

**Phase 1 artifacts (already built):**
- Services: `python/src/server/services/workflow/{workflow_models,backend_service,definition_service,dispatch_service,state_service}.py`
- Routes: `python/src/server/api_routes/workflow_{api,backend_api,approval_api,definition_api}.py`
- Frontend: `cortex-ui/src/features/workflows/{types,services,hooks}/`
- Migrations: `migration/0.1.0/027–032`
- The approval resolve endpoint already transitions node state + fires SSE — it has `TODO Phase 2` markers for resume signal and Telegram

---

## Conventions Reference

Same as Phase 1. All services follow `tuple[bool, dict[str, Any]]` return pattern. API routes use `try/except HTTPException: raise` pattern. Frontend follows TanStack Query patterns with `callAPIWithETag`, `STALE_TIMES`, `DISABLED_QUERY_KEY`.

---

# PHASE 2: Generative UI & HITL Approvals

**Goal:** Workflows pause for human review. Cortex renders approvals with A2UI components, sends Telegram notifications, and resumes the remote-agent after user decision.

## File Structure (Phase 2)

### Files to Create

```
python/src/server/services/workflow/
├── hitl_router.py              # Channel-agnostic approval dispatch
├── hitl_channels/
│   ├── __init__.py
│   ├── ui_channel.py           # SSE push to UI clients
│   └── telegram_channel.py     # Direct Cortex Telegram bot
├── hitl_models.py              # Approval channel protocol, types
└── approval_templates.py       # Deterministic A2UI JSON for standard types

python/src/server/services/generative_ui/
├── __init__.py
├── a2ui_client.py              # HTTP client to Second Brain service
├── a2ui_models.py              # Pydantic models for A2UI component spec
└── a2ui_service.py             # High-level: deterministic templates + LLM fallback

cortex-ui/src/features/workflows/components/
├── ApprovalList.tsx            # Pending approvals list view
├── ApprovalDetail.tsx          # Full approval with A2UI rendering
└── ApprovalActions.tsx         # Approve/Reject buttons + comment

cortex-ui/src/features/generative-ui/
├── components/
│   └── A2UIDisplay.tsx         # Wrapper around @trinity/a2ui renderer
├── hooks/
│   └── useA2UIGeneration.ts    # TanStack mutation for A2UI generation
└── types/
    └── index.ts                # Re-exports from @trinity/a2ui
```

### Files to Modify

```
python/pyproject.toml                              # Add python-telegram-bot
python/src/server/api_routes/workflow_approval_api.py  # Replace TODO stubs with real resume + Telegram
python/src/server/api_routes/workflow_backend_api.py   # Wire HITL router into approval_request_callback
python/src/server/main.py                          # Start Telegram bot in lifespan
docker-compose.yml                                 # Add trinity-a2ui service under trinity profile
cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts  # Add approval hooks
cortex-ui/src/features/workflows/services/workflowService.ts  # Add approval API methods
cortex-ui/src/features/workflows/types/index.ts               # Add ApprovalRequest type
```

---

## Task 1: A2UI Service Adapter (Backend)

**Files:**
- Create: `python/src/server/services/generative_ui/__init__.py`
- Create: `python/src/server/services/generative_ui/a2ui_models.py`
- Create: `python/src/server/services/generative_ui/a2ui_client.py`
- Create: `python/src/server/services/generative_ui/a2ui_service.py`
- Test: `python/tests/server/services/generative_ui/test_a2ui_service.py`

**Context:** Thin adapter that calls the Second Brain's A2UI generation endpoint over HTTP. Returns `None` when unavailable (graceful degradation). Used by the HITL router for `custom` approval types only — standard types use deterministic templates (Task 2).

- [ ] **Step 1: Create package init**

`python/src/server/services/generative_ui/__init__.py`:
```python
"""Generative UI (A2UI) service adapter for the Second Brain integration."""
```

`python/tests/server/services/generative_ui/__init__.py` (empty)

- [ ] **Step 2: Write a2ui_models.py**

```python
"""Pydantic models for A2UI component specs.

Python representation of the A2UI JSON protocol. These validate
responses from the Second Brain service — not a duplication of logic.
"""

from typing import Any

from pydantic import BaseModel, Field


class A2UIComponent(BaseModel):
    type: str = Field(description="Component type, e.g. 'a2ui.StatCard'")
    id: str = Field(description="Unique component ID")
    props: dict[str, Any] = Field(default_factory=dict)
    children: list["A2UIComponent"] | None = None
    layout: dict[str, Any] | None = None
    zone: str | None = None
    styling: dict[str, Any] | None = None


class A2UIGenerationRequest(BaseModel):
    content: str
    context: str | None = None
    content_type: str | None = None


class A2UIGenerationResponse(BaseModel):
    components: list[A2UIComponent]
    analysis: dict[str, Any] | None = None
```

- [ ] **Step 3: Write a2ui_client.py**

```python
"""HTTP client for the Second Brain's A2UI generation endpoint."""

import os
from typing import Any

import httpx

from ...config.logfire_config import get_logger
from .a2ui_models import A2UIGenerationRequest, A2UIGenerationResponse

logger = get_logger(__name__)

A2UI_SERVICE_URL = os.getenv("A2UI_SERVICE_URL", "http://trinity-a2ui:8054")
A2UI_TIMEOUT = float(os.getenv("A2UI_GENERATION_TIMEOUT", "10"))


class A2UIClient:
    """HTTP client to the Second Brain A2UI generation service."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or A2UI_SERVICE_URL).rstrip("/")
        self.timeout = timeout or A2UI_TIMEOUT

    async def generate(self, request: A2UIGenerationRequest) -> A2UIGenerationResponse | None:
        """Call the A2UI generation endpoint. Returns None on any failure."""
        url = f"{self.base_url}/api/a2ui/generate"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=request.model_dump())
            if response.status_code != 200:
                logger.warning(f"A2UI service returned {response.status_code}")
                return None
            return A2UIGenerationResponse.model_validate(response.json())
        except httpx.ConnectError:
            logger.info("A2UI service not available (connection refused)")
            return None
        except httpx.TimeoutException:
            logger.warning("A2UI service timed out")
            return None
        except Exception as e:
            logger.warning(f"A2UI generation failed: {e}")
            return None

    async def is_available(self) -> bool:
        """Check if the A2UI service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
```

- [ ] **Step 4: Write a2ui_service.py**

```python
"""High-level A2UI service used by HITL, chat, and knowledge features.

Delegates to deterministic templates for standard types,
falls back to the Second Brain LLM service for custom types.
"""

from typing import Any

from ...config.logfire_config import get_logger
from .a2ui_client import A2UIClient
from .a2ui_models import A2UIComponent, A2UIGenerationRequest, A2UIGenerationResponse

logger = get_logger(__name__)


class A2UIService:
    def __init__(self, client: A2UIClient | None = None):
        self._client = client or A2UIClient()
        self._available: bool | None = None

    async def is_available(self) -> bool:
        if self._available is None:
            self._available = await self._client.is_available()
        return self._available

    async def generate_approval_components(
        self,
        node_output: str,
        approval_type: str,
    ) -> list[dict[str, Any]] | None:
        """Generate A2UI components for an approval payload.

        Standard types use deterministic templates (no LLM).
        Custom type calls the Second Brain service.
        """
        # Defer to approval_templates for standard types
        from ..workflow.approval_templates import build_approval_payload
        components = build_approval_payload(approval_type, node_output)
        if components is not None:
            return components

        # Custom type: call Second Brain
        if not await self.is_available():
            logger.info("A2UI service unavailable, returning raw output for custom approval")
            return None

        request = A2UIGenerationRequest(
            content=node_output,
            context="workflow_approval",
            content_type=approval_type,
        )
        response = await self._client.generate(request)
        if response is None:
            return None
        return [c.model_dump() for c in response.components]
```

- [ ] **Step 5: Write test**

```python
"""Tests for A2UIService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.generative_ui.a2ui_models import A2UIGenerationResponse, A2UIComponent
from src.server.services.generative_ui.a2ui_service import A2UIService


@pytest.fixture
def service():
    client = AsyncMock()
    return A2UIService(client=client)


class TestGenerateApprovalComponents:
    @pytest.mark.asyncio
    async def test_standard_type_uses_template(self, service):
        """Standard approval types should return deterministic templates, not call LLM."""
        with patch("src.server.services.generative_ui.a2ui_service.build_approval_payload") as mock_build:
            mock_build.return_value = [{"type": "a2ui.StatCard", "id": "s1", "props": {}}]
            result = await service.generate_approval_components("some output", "plan_review")
            assert result is not None
            assert result[0]["type"] == "a2ui.StatCard"
            # LLM client should NOT have been called
            service._client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_type_calls_llm(self, service):
        """Custom approval type should fall through to A2UI service."""
        with patch("src.server.services.generative_ui.a2ui_service.build_approval_payload") as mock_build:
            mock_build.return_value = None  # Not a standard type
            service._available = True
            service._client.generate.return_value = A2UIGenerationResponse(
                components=[A2UIComponent(type="a2ui.ExecutiveSummary", id="e1", props={"title": "Custom"})]
            )
            result = await service.generate_approval_components("output", "custom")
            assert result is not None
            assert result[0]["type"] == "a2ui.ExecutiveSummary"

    @pytest.mark.asyncio
    async def test_custom_type_returns_none_when_unavailable(self, service):
        """When A2UI service is down, custom type returns None (graceful degradation)."""
        with patch("src.server.services.generative_ui.a2ui_service.build_approval_payload") as mock_build:
            mock_build.return_value = None
            service._available = False
            result = await service.generate_approval_components("output", "custom")
            assert result is None
```

- [ ] **Step 6: Run tests, verify pass**

Run: `cd /home/winadmin/projects/Trinity/cortex/python && uv run pytest tests/server/services/generative_ui/ -v`

- [ ] **Step 7: Commit**

```bash
git add python/src/server/services/generative_ui/ python/tests/server/services/generative_ui/
git commit -m "feat(workflows): add A2UI service adapter with graceful degradation"
```

---

## Task 2: Deterministic Approval Templates

**Files:**
- Create: `python/src/server/services/workflow/approval_templates.py`
- Test: `python/tests/server/services/workflow/test_approval_templates.py`

**Context:** Maps standard approval types (`plan_review`, `pr_review`, `deploy_gate`) to A2UI component arrays by parsing node output text. No LLM call — pure string parsing + template population.

- [ ] **Step 1: Write test**

```python
"""Tests for deterministic approval templates."""

import pytest

from src.server.services.workflow.approval_templates import build_approval_payload


PLAN_OUTPUT = """## Rate Limiting Implementation Plan

### Summary
Add token bucket rate limiting to all API endpoints.

### Steps
1. Add Redis dependency
2. Create rate limiter middleware
3. Configure per-endpoint limits

### Stats
- Files to modify: 5
- Estimated complexity: Medium
"""


class TestBuildApprovalPayload:
    def test_plan_review_returns_components(self):
        result = build_approval_payload("plan_review", PLAN_OUTPUT)
        assert result is not None
        types = [c["type"] for c in result]
        assert "a2ui.ExecutiveSummary" in types

    def test_pr_review_returns_components(self):
        pr_output = "## PR: Add auth\n\nFiles changed: 3\n+120 -45\n\n```python\ndef login():\n    pass\n```"
        result = build_approval_payload("pr_review", pr_output)
        assert result is not None
        types = [c["type"] for c in result]
        assert "a2ui.StatCard" in types

    def test_deploy_gate_returns_components(self):
        deploy_output = "## Deploy to Production\n\nEnvironment: prod\nBuild: passing\n\n- [ ] DB migrated\n- [x] Tests pass"
        result = build_approval_payload("deploy_gate", deploy_output)
        assert result is not None
        types = [c["type"] for c in result]
        assert "a2ui.StatCard" in types

    def test_custom_returns_none(self):
        result = build_approval_payload("custom", "anything")
        assert result is None

    def test_unknown_type_returns_none(self):
        result = build_approval_payload("unknown_type", "anything")
        assert result is None
```

- [ ] **Step 2: Implement approval_templates.py**

```python
"""Deterministic A2UI templates for standard approval types.

Parses node_output markdown to extract structured data, then
populates A2UI component JSON. No LLM calls — pure string parsing.
"""

import re
import uuid
from typing import Any

from ...config.logfire_config import get_logger

logger = get_logger(__name__)


def _make_id() -> str:
    return str(uuid.uuid4())[:8]


def _extract_heading(text: str) -> str:
    """Extract first markdown heading or first line."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line)
    return text.split("\n")[0][:100] if text else "Approval Required"


def _extract_summary(text: str) -> str:
    """Extract text between first heading and next heading or code block."""
    lines = text.split("\n")
    summary_lines = []
    past_heading = False
    for line in lines:
        if line.strip().startswith("#"):
            if past_heading:
                break
            past_heading = True
            continue
        if past_heading and line.strip().startswith("```"):
            break
        if past_heading and line.strip():
            summary_lines.append(line.strip())
    return " ".join(summary_lines[:5]) or text[:200]


def _extract_steps(text: str) -> list[dict[str, str]]:
    """Extract numbered list items as steps."""
    steps = []
    for match in re.finditer(r"^\s*(\d+)\.\s+(.+)$", text, re.MULTILINE):
        steps.append({"step": int(match.group(1)), "title": match.group(2).strip()})
    return steps


def _extract_stats(text: str) -> dict[str, str]:
    """Extract key: value pairs from text."""
    stats = {}
    for match in re.finditer(r"^[-*]\s*(.+?):\s*(.+)$", text, re.MULTILINE):
        stats[match.group(1).strip()] = match.group(2).strip()
    # Also check for "Files changed: N" style
    for match in re.finditer(r"(\w[\w\s]+?):\s*(\d+\S*)", text):
        key = match.group(1).strip()
        if key not in stats:
            stats[key] = match.group(2).strip()
    return stats


def _extract_code_blocks(text: str) -> list[dict[str, str]]:
    """Extract fenced code blocks."""
    blocks = []
    for match in re.finditer(r"```(\w*)\n(.*?)```", text, re.DOTALL):
        blocks.append({"language": match.group(1) or "text", "code": match.group(2).strip()})
    return blocks


def _extract_checklist(text: str) -> list[dict[str, Any]]:
    """Extract markdown checklist items."""
    items = []
    for match in re.finditer(r"^\s*-\s*\[([ xX])\]\s*(.+)$", text, re.MULTILINE):
        items.append({"label": match.group(2).strip(), "checked": match.group(1).lower() == "x"})
    return items


def _build_plan_review(node_output: str) -> list[dict[str, Any]]:
    """Build A2UI components for plan_review approval type."""
    components: list[dict[str, Any]] = []
    title = _extract_heading(node_output)
    summary = _extract_summary(node_output)
    steps = _extract_steps(node_output)
    stats = _extract_stats(node_output)
    code_blocks = _extract_code_blocks(node_output)

    components.append({
        "type": "a2ui.ExecutiveSummary",
        "id": _make_id(),
        "props": {"title": title, "summary": summary, "highlights": list(stats.values())[:3]},
        "zone": "hero",
    })
    for step in steps[:10]:
        components.append({
            "type": "a2ui.StepCard",
            "id": _make_id(),
            "props": {"step": step["step"], "title": step["title"]},
            "zone": "content",
        })
    if stats:
        components.append({
            "type": "a2ui.StatCard",
            "id": _make_id(),
            "props": {"stats": [{"label": k, "value": v} for k, v in list(stats.items())[:4]]},
            "zone": "sidebar",
        })
    for block in code_blocks[:2]:
        components.append({
            "type": "a2ui.CodeBlock",
            "id": _make_id(),
            "props": {"language": block["language"], "code": block["code"]},
            "zone": "content",
        })
    return components


def _build_pr_review(node_output: str) -> list[dict[str, Any]]:
    """Build A2UI components for pr_review approval type."""
    components: list[dict[str, Any]] = []
    stats = _extract_stats(node_output)
    code_blocks = _extract_code_blocks(node_output)

    # Parse +/- stats from diff-style output
    additions = re.search(r"\+(\d+)", node_output)
    deletions = re.search(r"-(\d+)", node_output)
    stat_items = []
    if "Files changed" in stats or "files changed" in stats:
        stat_items.append({"label": "Files Changed", "value": stats.get("Files changed", stats.get("files changed", "?"))})
    if additions:
        stat_items.append({"label": "Additions", "value": f"+{additions.group(1)}"})
    if deletions:
        stat_items.append({"label": "Deletions", "value": f"-{deletions.group(1)}"})

    components.append({
        "type": "a2ui.StatCard",
        "id": _make_id(),
        "props": {"stats": stat_items or [{"label": "Review", "value": "PR ready"}]},
        "zone": "hero",
    })
    for block in code_blocks[:3]:
        components.append({
            "type": "a2ui.CodeBlock",
            "id": _make_id(),
            "props": {"language": block["language"], "code": block["code"]},
            "zone": "content",
        })
    return components


def _build_deploy_gate(node_output: str) -> list[dict[str, Any]]:
    """Build A2UI components for deploy_gate approval type."""
    components: list[dict[str, Any]] = []
    stats = _extract_stats(node_output)
    checklist = _extract_checklist(node_output)

    stat_items = [{"label": k, "value": v} for k, v in list(stats.items())[:4]]
    components.append({
        "type": "a2ui.StatCard",
        "id": _make_id(),
        "props": {"stats": stat_items or [{"label": "Deploy", "value": "Ready"}]},
        "zone": "hero",
    })
    for item in checklist:
        components.append({
            "type": "a2ui.ChecklistItem",
            "id": _make_id(),
            "props": {"label": item["label"], "checked": item["checked"]},
            "zone": "content",
        })
    if not checklist:
        components.append({
            "type": "a2ui.CalloutCard",
            "id": _make_id(),
            "props": {"message": "No pre-deploy checklist found in node output.", "severity": "info"},
            "zone": "sidebar",
        })
    return components


_BUILDERS = {
    "plan_review": _build_plan_review,
    "pr_review": _build_pr_review,
    "deploy_gate": _build_deploy_gate,
}


def build_approval_payload(approval_type: str, node_output: str) -> list[dict[str, Any]] | None:
    """Build A2UI component array for a given approval type.

    Returns None for unknown/custom types (caller should use LLM generation).
    """
    builder = _BUILDERS.get(approval_type)
    if builder is None:
        return None
    try:
        return builder(node_output)
    except Exception as e:
        logger.error(f"Error building {approval_type} template: {e}", exc_info=True)
        return None
```

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(workflows): add deterministic A2UI approval templates for standard types"
```

---

## Task 3: HITL Router & Channels

**Files:**
- Create: `python/src/server/services/workflow/hitl_models.py`
- Create: `python/src/server/services/workflow/hitl_router.py`
- Create: `python/src/server/services/workflow/hitl_channels/__init__.py`
- Create: `python/src/server/services/workflow/hitl_channels/ui_channel.py`
- Create: `python/src/server/services/workflow/hitl_channels/telegram_channel.py`
- Modify: `python/pyproject.toml` (add `python-telegram-bot>=21.0`)
- Test: `python/tests/server/services/workflow/test_hitl_router.py`

**Context:** The HITL Router dispatches approval requests to configured channels. UI channel fires SSE events (already works via state_service). Telegram channel sends inline keyboard messages via Cortex's own bot. Channels implement the `ApprovalChannel` protocol (send-side only). Resolution converges on the existing `POST /api/workflows/approvals/{id}/resolve` endpoint.

- [ ] **Step 1: Add python-telegram-bot dependency**

In `python/pyproject.toml`, add `"python-telegram-bot>=21.0",` to the `server` dependency group. Run `uv sync --group server`.

- [ ] **Step 2: Write hitl_models.py**

```python
"""HITL models and channel protocol."""

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ApprovalContext(BaseModel):
    """Context passed to channels when dispatching an approval."""
    approval_id: str
    workflow_run_id: str
    workflow_node_id: str
    yaml_node_id: str
    approval_type: str
    node_output: str
    a2ui_payload: list[dict[str, Any]] | None = None
    channels: list[str] = Field(default_factory=lambda: ["ui"])
    project_name: str | None = None
    cortex_url: str | None = None


class ApprovalChannel(Protocol):
    """Protocol for HITL approval channels. Channels implement send-side only."""

    async def send_approval_request(self, context: ApprovalContext) -> None: ...

    async def notify_resolution(
        self, context: ApprovalContext, decision: str, resolved_by: str
    ) -> None: ...
```

- [ ] **Step 3: Write ui_channel.py**

```python
"""UI channel — dispatches approval events via SSE."""

from ...config.logfire_config import get_logger
from ..workflow.hitl_models import ApprovalContext

logger = get_logger(__name__)


class UIChannel:
    def __init__(self, state_service):
        self._state_service = state_service

    async def send_approval_request(self, context: ApprovalContext) -> None:
        await self._state_service.fire_sse_event(context.workflow_run_id, "approval_requested", {
            "approval_id": context.approval_id,
            "node_id": context.workflow_node_id,
            "yaml_node_id": context.yaml_node_id,
            "approval_type": context.approval_type,
            "summary": context.node_output[:200],
        })

    async def notify_resolution(
        self, context: ApprovalContext, decision: str, resolved_by: str
    ) -> None:
        await self._state_service.fire_sse_event(context.workflow_run_id, "approval_resolved", {
            "approval_id": context.approval_id,
            "decision": decision,
            "resolved_by": resolved_by,
            "resolved_via": "ui",
        })
```

- [ ] **Step 4: Write telegram_channel.py**

```python
"""Telegram channel — sends approval notifications via Cortex's direct bot.

The bot is optional. If CORTEX_TELEGRAM_BOT_TOKEN is not set, this
channel silently does nothing.
"""

import os

from ...config.logfire_config import get_logger
from ..workflow.hitl_models import ApprovalContext

logger = get_logger(__name__)

BOT_TOKEN = os.getenv("CORTEX_TELEGRAM_BOT_TOKEN")
CHAT_IDS = [cid.strip() for cid in os.getenv("CORTEX_TELEGRAM_CHAT_IDS", "").split(",") if cid.strip()]


class TelegramChannel:
    def __init__(self):
        self._bot = None

    async def _get_bot(self):
        if self._bot is not None:
            return self._bot
        if not BOT_TOKEN:
            return None
        try:
            from telegram import Bot
            self._bot = Bot(token=BOT_TOKEN)
            return self._bot
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram bot: {e}")
            return None

    async def send_approval_request(self, context: ApprovalContext) -> None:
        bot = await self._get_bot()
        if not bot or not CHAT_IDS:
            return

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            text = (
                f"**Approval Required: {context.approval_type}**\n\n"
                f"Workflow node `{context.yaml_node_id}` needs review.\n\n"
                f"{context.node_output[:500]}"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Approve", callback_data=f"approve:{context.approval_id}"),
                    InlineKeyboardButton("Reject", callback_data=f"reject:{context.approval_id}"),
                ],
            ])
            if context.cortex_url:
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(
                        "View in Cortex",
                        url=f"{context.cortex_url}/workflows/{context.workflow_run_id}/approvals/{context.approval_id}",
                    ),
                ])

            for chat_id in CHAT_IDS:
                msg = await bot.send_message(
                    chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown",
                )
                # Store telegram_message_id for later editing
                logger.info(f"Telegram approval sent to {chat_id}, message_id={msg.message_id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram approval: {e}", exc_info=True)

    async def notify_resolution(
        self, context: ApprovalContext, decision: str, resolved_by: str
    ) -> None:
        bot = await self._get_bot()
        if not bot or not CHAT_IDS:
            return
        try:
            text = f"**Resolved: {decision}** by {resolved_by}\nNode: `{context.yaml_node_id}`"
            for chat_id in CHAT_IDS:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send Telegram resolution: {e}", exc_info=True)
```

- [ ] **Step 5: Write hitl_router.py**

```python
"""HITL Router — channel-agnostic approval dispatch.

Generates A2UI payload, creates the approval_request record,
and dispatches to all configured channels.
"""

from typing import Any

from src.server.utils import get_supabase_client

from ...config.logfire_config import get_logger
from ..generative_ui.a2ui_service import A2UIService
from .hitl_channels.telegram_channel import TelegramChannel
from .hitl_channels.ui_channel import UIChannel
from .hitl_models import ApprovalContext

logger = get_logger(__name__)


class HITLRouter:
    def __init__(self, state_service, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()
        self._ui_channel = UIChannel(state_service)
        self._telegram_channel = TelegramChannel()
        self._a2ui_service = A2UIService()

    async def handle_approval_request(
        self,
        workflow_run_id: str,
        workflow_node_id: str,
        yaml_node_id: str,
        approval_type: str,
        node_output: str,
        channels: list[str],
    ) -> tuple[bool, dict[str, Any]]:
        """Create approval record, generate A2UI payload, dispatch to channels."""
        try:
            # Generate A2UI payload
            a2ui_payload = await self._a2ui_service.generate_approval_components(
                node_output, approval_type,
            )

            # Create approval_request record
            data = {
                "workflow_run_id": workflow_run_id,
                "workflow_node_id": workflow_node_id,
                "yaml_node_id": yaml_node_id,
                "approval_type": approval_type,
                "payload": {"components": a2ui_payload} if a2ui_payload else {"raw_output": node_output},
                "status": "pending",
                "channels_notified": channels,
            }
            response = self.supabase_client.table("approval_requests").insert(data).execute()
            if not response.data:
                return False, {"error": "Failed to create approval request"}

            approval = response.data[0]
            approval_id = approval["id"]

            # Build context for channels
            context = ApprovalContext(
                approval_id=approval_id,
                workflow_run_id=workflow_run_id,
                workflow_node_id=workflow_node_id,
                yaml_node_id=yaml_node_id,
                approval_type=approval_type,
                node_output=node_output,
                a2ui_payload=a2ui_payload,
                channels=channels,
            )

            # Dispatch to channels
            if "ui" in channels:
                await self._ui_channel.send_approval_request(context)
            if "telegram" in channels:
                await self._telegram_channel.send_approval_request(context)

            return True, {"approval_id": approval_id}
        except Exception as e:
            logger.error(f"Error handling approval request: {e}", exc_info=True)
            return False, {"error": str(e)}

    async def handle_resolution(
        self,
        approval_id: str,
        decision: str,
        resolved_by: str,
    ) -> None:
        """Notify channels of approval resolution."""
        try:
            response = (
                self.supabase_client.table("approval_requests")
                .select("*")
                .eq("id", approval_id)
                .execute()
            )
            if not response.data:
                return

            approval = response.data[0]
            context = ApprovalContext(
                approval_id=approval_id,
                workflow_run_id=approval["workflow_run_id"],
                workflow_node_id=approval["workflow_node_id"],
                yaml_node_id=approval["yaml_node_id"],
                approval_type=approval["approval_type"],
                node_output="",
                channels=approval.get("channels_notified", ["ui"]),
            )

            if "ui" in context.channels:
                await self._ui_channel.notify_resolution(context, decision, resolved_by)
            if "telegram" in context.channels:
                await self._telegram_channel.notify_resolution(context, decision, resolved_by)
        except Exception as e:
            logger.error(f"Error notifying resolution: {e}", exc_info=True)
```

- [ ] **Step 6: Write test**

```python
"""Tests for HITLRouter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.workflow.hitl_router import HITLRouter


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def mock_state_service():
    svc = AsyncMock()
    svc.fire_sse_event = AsyncMock()
    return svc


@pytest.fixture
def router(mock_state_service, mock_supabase):
    return HITLRouter(state_service=mock_state_service, supabase_client=mock_supabase)


class TestHandleApprovalRequest:
    @pytest.mark.asyncio
    async def test_creates_approval_and_dispatches_ui(self, router, mock_supabase, mock_state_service):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "apr_1", "workflow_run_id": "wr_1"}
        ]
        with patch.object(router._a2ui_service, "generate_approval_components", new_callable=AsyncMock) as mock_a2ui:
            mock_a2ui.return_value = [{"type": "a2ui.StatCard", "id": "s1", "props": {}}]
            success, result = await router.handle_approval_request(
                workflow_run_id="wr_1",
                workflow_node_id="n_1",
                yaml_node_id="plan-review",
                approval_type="plan_review",
                node_output="## Plan\n\nDo things",
                channels=["ui"],
            )
        assert success is True
        assert result["approval_id"] == "apr_1"
        mock_state_service.fire_sse_event.assert_called_once()
```

- [ ] **Step 7: Run tests, verify pass**

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(workflows): add HITL Router with UI and Telegram channels"
```

---

## Task 4: Wire HITL into Approval API + Resume Signal

**Files:**
- Modify: `python/src/server/api_routes/workflow_backend_api.py` (replace inline approval creation with HITLRouter)
- Modify: `python/src/server/api_routes/workflow_approval_api.py` (add resume signal to remote-agent)

**Context:** Phase 1 created inline approval records in the callback endpoint and left TODO markers in the resolve endpoint. This task replaces both with the real HITL Router and adds the httpx POST resume signal to the remote-agent.

- [ ] **Step 1: Update workflow_backend_api.py approval_request_callback**

Replace the inline `approval_requests.insert()` block in the `approval_request_callback` function with a call to `HITLRouter.handle_approval_request()`. The HITL Router now owns approval creation and channel dispatch.

- [ ] **Step 2: Update workflow_approval_api.py resolve_approval**

Replace the `TODO Phase 2` markers with:
1. Send resume signal to remote-agent: `POST {backend_url}/api/cortex/workflows/{run_id}/resume` via httpx
2. Call `hitl_router.handle_resolution()` to notify channels

- [ ] **Step 3: Test the full flow manually** (or write integration test)

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(workflows): wire HITL Router into approval callbacks and add resume signal"
```

---

## Task 5: Frontend — Approval UI Components

**Files:**
- Create: `cortex-ui/src/features/generative-ui/components/A2UIDisplay.tsx`
- Create: `cortex-ui/src/features/generative-ui/types/index.ts`
- Create: `cortex-ui/src/features/workflows/components/ApprovalList.tsx`
- Create: `cortex-ui/src/features/workflows/components/ApprovalDetail.tsx`
- Create: `cortex-ui/src/features/workflows/components/ApprovalActions.tsx`
- Modify: `cortex-ui/src/features/workflows/types/index.ts` (add ApprovalRequest type)
- Modify: `cortex-ui/src/features/workflows/services/workflowService.ts` (add approval methods)
- Modify: `cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts` (add approval hooks)

**Context:** The approval UI renders A2UI component payloads from the `approval_requests.payload` JSONB column. For Phase 2, we render raw JSON as a formatted preview — full @trinity/a2ui library integration comes when the Second Brain's library build is ready. The `A2UIDisplay` component is a thin wrapper that renders component JSON or falls back to raw markdown.

- [ ] **Step 1: Add ApprovalRequest type to types/index.ts**

```typescript
export interface ApprovalRequest {
  id: string;
  workflow_run_id: string;
  workflow_node_id: string;
  yaml_node_id: string;
  approval_type: string;
  payload: { components?: A2UIComponent[]; raw_output?: string };
  status: "pending" | "approved" | "rejected" | "expired";
  channels_notified: string[];
  resolved_by: string | null;
  resolved_via: string | null;
  resolved_comment: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface A2UIComponent {
  type: string;
  id: string;
  props: Record<string, unknown>;
  zone?: string;
}

export interface ResolveApprovalRequest {
  decision: "approved" | "rejected";
  comment?: string;
}
```

- [ ] **Step 2: Add approval methods to workflowService.ts**

```typescript
// Add to existing workflowService object:
async listApprovals(status?: string): Promise<ApprovalRequest[]> {
  const params = status ? `?status=${status}` : "";
  return callAPIWithETag<ApprovalRequest[]>(`/api/workflows/approvals${params}`);
},

async getApproval(id: string): Promise<ApprovalRequest> {
  return callAPIWithETag<ApprovalRequest>(`/api/workflows/approvals/${id}`);
},

async resolveApproval(id: string, data: ResolveApprovalRequest): Promise<{ resolved: boolean }> {
  return callAPIWithETag<{ resolved: boolean }>(`/api/workflows/approvals/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify(data),
  });
},
```

- [ ] **Step 3: Add approval hooks to useWorkflowQueries.ts**

```typescript
// Add to workflowKeys:
approvals: () => [...workflowKeys.all, "approvals"] as const,
approvalDetail: (id: string) => [...workflowKeys.all, "approvals", id] as const,

// Add hooks:
export function useApprovals(status?: string) {
  const { refetchInterval } = useSmartPolling(5000);
  return useQuery({
    queryKey: workflowKeys.approvals(),
    queryFn: () => workflowService.listApprovals(status),
    refetchInterval,
    staleTime: STALE_TIMES.frequent,
  });
}

export function useResolveApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ResolveApprovalRequest }) =>
      workflowService.resolveApproval(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.approvals() });
      queryClient.invalidateQueries({ queryKey: workflowKeys.runs() });
    },
  });
}
```

- [ ] **Step 4: Create A2UIDisplay.tsx**

A thin wrapper that renders A2UI components as formatted cards or falls back to raw markdown. Does NOT import `@trinity/a2ui` yet — that comes when the library build exists.

- [ ] **Step 5: Create ApprovalList.tsx, ApprovalDetail.tsx, ApprovalActions.tsx**

Standard React components following Cortex's Tron-inspired glassmorphism styling. ApprovalDetail renders the `payload.components` array through A2UIDisplay, or `payload.raw_output` as markdown.

- [ ] **Step 6: Verify TypeScript compiles**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/workflows" | head -20`

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(workflows): add approval UI components with A2UI rendering"
```

---

# PHASE 3: Pattern Discovery Engine

**Goal:** Analyze activity across 30+ repos to discover and suggest reusable workflow automations.

## File Structure (Phase 3)

### Files to Create

```
migration/0.1.0/
├── 033_activity_events.sql
└── 034_discovered_patterns.sql

python/src/server/services/pattern_discovery/
├── __init__.py
├── capture_service.py           # Event ingestion from git, conversations, workflows
├── normalization_service.py     # Stage 1: Haiku batch intent extraction
├── sequence_mining_service.py   # Stage 2a: PrefixSpan temporal patterns
├── clustering_service.py        # Stage 2b: pgvector embedding clustering
├── scoring_service.py           # Pattern scoring + threshold evaluation
├── generation_service.py        # Sonnet YAML workflow generation
├── suggestion_service.py        # Surfacing, feedback loop, status management
└── backfill_service.py          # One-time historical data ingestion

python/src/server/api_routes/
└── pattern_discovery_api.py     # Suggestion endpoints + nightly trigger

python/tests/server/services/pattern_discovery/
├── __init__.py
├── test_capture_service.py
├── test_normalization_service.py
├── test_sequence_mining_service.py
├── test_scoring_service.py
└── test_suggestion_service.py
```

---

## Task 6: Database Migrations (033-034)

**Files:**
- Create: `migration/0.1.0/033_activity_events.sql`
- Create: `migration/0.1.0/034_discovered_patterns.sql`

- [ ] **Step 1: Write migration 033 — activity_events**

```sql
-- Migration 033: Activity events
-- Captures git commits, agent conversations, and workflow runs for pattern discovery

CREATE TABLE IF NOT EXISTS activity_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  repo_url TEXT,
  raw_content TEXT,
  action_verb TEXT,
  target_object TEXT,
  trigger_context TEXT,
  intent_embedding vector,
  metadata JSONB DEFAULT '{}',
  normalized_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_events_type_created
  ON activity_events (event_type, created_at);

CREATE INDEX IF NOT EXISTS idx_activity_events_pending_normalization
  ON activity_events (created_at)
  WHERE normalized_at IS NULL;
```

Note: The ivfflat index on `intent_embedding` should be created after backfill when there are enough rows (pgvector requires rows for index building).

- [ ] **Step 2: Write migration 034 — discovered_patterns**

```sql
-- Migration 034: Discovered patterns
-- Stores workflow automation suggestions from pattern mining

CREATE TABLE IF NOT EXISTS discovered_patterns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_name TEXT NOT NULL,
  description TEXT,
  pattern_type TEXT NOT NULL,
  sequence_pattern JSONB,
  cluster_embedding vector,
  source_event_ids UUID[] DEFAULT '{}',
  repos_involved TEXT[] DEFAULT '{}',
  frequency_score FLOAT NOT NULL DEFAULT 0,
  cross_repo_score FLOAT NOT NULL DEFAULT 0,
  automation_potential FLOAT NOT NULL DEFAULT 0,
  final_score FLOAT NOT NULL DEFAULT 0,
  suggested_yaml TEXT,
  status TEXT NOT NULL DEFAULT 'pending_review',
  accepted_workflow_id UUID REFERENCES workflow_definitions(id) ON DELETE SET NULL,
  feedback_delta JSONB,
  discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discovered_patterns_status_score
  ON discovered_patterns (status, final_score DESC);
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(patterns): add database migrations 033-034 for activity events and discovered patterns"
```

---

## Task 7: Capture Service

**Files:**
- Create: `python/src/server/services/pattern_discovery/__init__.py`
- Create: `python/src/server/services/pattern_discovery/capture_service.py`
- Test: `python/tests/server/services/pattern_discovery/test_capture_service.py`

**Context:** Ingests events from three sources: git commits (via git log parsing), agent conversations (from chat_messages table), and workflow completions (from workflow_runs table). Each event is stored in `activity_events` with `normalized_at = NULL` (pending normalization).

- [ ] **Step 1: Write test, implementation, commit** (TDD cycle)

Key methods:
- `capture_git_commits(project_id, repo_path, since_days=7)` — runs `git log` and inserts rows
- `capture_workflow_completion(workflow_run_id)` — reads completed run + nodes, inserts one event
- `capture_conversation(conversation_id)` — reads chat messages, inserts summary event
- `get_pending_events(limit=50)` — returns events where `normalized_at IS NULL`

```bash
git commit -m "feat(patterns): add CaptureService for event ingestion from git, conversations, workflows"
```

---

## Task 8: Normalization Service (Stage 1)

**Files:**
- Create: `python/src/server/services/pattern_discovery/normalization_service.py`
- Test: `python/tests/server/services/pattern_discovery/test_normalization_service.py`

**Context:** Calls Anthropic API (Haiku) in batches of up to 50 events. Extracts `action_verb`, `target_object`, `trigger_context` tuples. Generates embeddings of the normalized tuple. Updates `activity_events` with extracted fields + embedding + `normalized_at` timestamp.

- [ ] **Step 1: Add `anthropic` and `prefixspan` to server dependencies in pyproject.toml**

- [ ] **Step 2: Write test, implementation, commit** (TDD cycle)

Key methods:
- `normalize_batch(events: list[dict], batch_size=50)` — sends batch to Haiku, updates rows
- `_build_extraction_prompt(events)` — builds the batch prompt
- `_generate_embedding(text)` — calls embedding API for the normalized tuple string

Cost controls: daily cap via `PATTERN_DISCOVERY_DAILY_CAP` env var (default 500), deduplication via trigram similarity.

```bash
git commit -m "feat(patterns): add NormalizationService for Haiku-based intent extraction"
```

---

## Task 9: Sequence Mining Service (Stage 2a)

**Files:**
- Create: `python/src/server/services/pattern_discovery/sequence_mining_service.py`
- Test: `python/tests/server/services/pattern_discovery/test_sequence_mining_service.py`

**Context:** Uses `prefixspan` PyPI package to find frequent subsequences in `(action_verb, target_object)` tuples. Groups events by repo per week, runs PrefixSpan, filters for patterns with 3+ occurrences across 2+ repos.

- [ ] **Step 1: Write test, implementation, commit** (TDD cycle)

Key methods:
- `mine_sequences(lookback_days=30, min_support=3, min_repos=2)` — runs PrefixSpan, returns pattern candidates
- `_build_sequences_by_repo_week(events)` — groups normalized events into ordered sequences
- `_filter_cross_repo(patterns, min_repos)` — ensures patterns appear across multiple repos

```bash
git commit -m "feat(patterns): add SequenceMiningService with PrefixSpan temporal pattern detection"
```

---

## Task 10: Clustering, Scoring & Generation

**Files:**
- Create: `python/src/server/services/pattern_discovery/clustering_service.py`
- Create: `python/src/server/services/pattern_discovery/scoring_service.py`
- Create: `python/src/server/services/pattern_discovery/generation_service.py`
- Test: `python/tests/server/services/pattern_discovery/test_scoring_service.py`

**Context:** Clustering uses pgvector cosine similarity (threshold > 0.85). Scoring computes `final_score = frequency × cross_repo × automation_potential`. Generation sends high-scoring patterns to Sonnet API to produce YAML workflow definitions.

- [ ] **Step 1: Write tests, implementations, commit** (TDD cycle)

```bash
git commit -m "feat(patterns): add clustering, scoring, and YAML generation for pattern discovery"
```

---

## Task 11: Suggestion Service & API

**Files:**
- Create: `python/src/server/services/pattern_discovery/suggestion_service.py`
- Create: `python/src/server/api_routes/pattern_discovery_api.py`
- Modify: `python/src/server/main.py` (register router)
- Test: `python/tests/server/services/pattern_discovery/test_suggestion_service.py`

**Context:** Surfaces discovered patterns as suggestions. Handles Accept/Customize/Dismiss actions. Accept creates a `workflow_definitions` row with `origin: pattern_discovery`. Dismiss decays scores. API endpoints: `GET /api/patterns/suggestions`, `POST /api/patterns/suggestions/{id}/accept`, `POST /api/patterns/suggestions/{id}/dismiss`.

- [ ] **Step 1: Write test, implementation, commit** (TDD cycle)

```bash
git commit -m "feat(patterns): add suggestion service and pattern discovery API endpoints"
```

---

## Task 12: Backfill Service

**Files:**
- Create: `python/src/server/services/pattern_discovery/backfill_service.py`
- Test: `python/tests/server/services/pattern_discovery/test_backfill_service.py`

**Context:** One-time job that reads git history (last 90 days) from all registered projects, ingests into `activity_events`, then runs the normalization pipeline. Triggered via API: `POST /api/patterns/backfill`.

- [ ] **Step 1: Write test, implementation, commit** (TDD cycle)

```bash
git commit -m "feat(patterns): add backfill service for historical data ingestion"
```

---

# PHASE 4: Workflow Editor & UI Polish

**Goal:** Users can view, edit, and discover workflows in the Cortex UI.

## File Structure (Phase 4)

### Files to Create

```
cortex-ui/src/features/workflows/components/
├── WorkflowEditor.tsx           # Split-pane YAML editor
├── NodeForm.tsx                 # Individual node editing form
├── YamlPanel.tsx                # Live YAML preview with syntax highlighting
├── CommandEditor.tsx            # Markdown command editor
├── WorkflowRunView.tsx          # Live execution view with SSE
├── WorkflowRunCard.tsx          # Run card for list view
├── SuggestedWorkflows.tsx       # Pattern discovery suggestions panel
└── WorkflowsPage.tsx            # Main page combining all sub-views

cortex-ui/src/features/workflows/components/editor/
├── NodeList.tsx                 # Sortable node list
├── MetadataForm.tsx             # Workflow metadata (name, description, tags)
└── DependencySelect.tsx         # Multi-select for depends_on
```

### Files to Modify

```
cortex-ui/src/features/workflows/services/workflowService.ts  # Add command CRUD
cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts   # Add editor hooks
cortex-ui/src/features/workflows/types/index.ts                # Add editor types
```

---

## Task 13: Workflow Run Viewer (SSE-powered)

**Files:**
- Create: `cortex-ui/src/features/workflows/components/WorkflowRunView.tsx`
- Create: `cortex-ui/src/features/workflows/components/WorkflowRunCard.tsx`

**Context:** WorkflowRunView connects to `GET /api/workflows/{run_id}/events` via native `EventSource` API. Renders a live DAG view showing node states, progress messages, and approval gates. WorkflowRunCard is a compact card for list views.

- [ ] **Step 1: Create WorkflowRunCard** — compact card showing run status, node count, timestamps
- [ ] **Step 2: Create WorkflowRunView** — full view with SSE connection, node state indicators, approval prompts
- [ ] **Step 3: Verify TypeScript compiles, commit**

```bash
git commit -m "feat(workflows): add WorkflowRunView with live SSE updates and WorkflowRunCard"
```

---

## Task 14: Split-Pane Workflow Editor

**Files:**
- Create: `cortex-ui/src/features/workflows/components/WorkflowEditor.tsx`
- Create: `cortex-ui/src/features/workflows/components/YamlPanel.tsx`
- Create: `cortex-ui/src/features/workflows/components/NodeForm.tsx`
- Create: `cortex-ui/src/features/workflows/components/editor/NodeList.tsx`
- Create: `cortex-ui/src/features/workflows/components/editor/MetadataForm.tsx`
- Create: `cortex-ui/src/features/workflows/components/editor/DependencySelect.tsx`

**Context:** Split-pane design: left is a form panel (sortable node list, metadata, approval toggles, dependency multi-selects). Right is a live YAML preview that updates bidirectionally. Uses `js-yaml` for YAML serialization.

- [ ] **Step 1: Add `js-yaml` and `@types/js-yaml` to frontend dependencies**
- [ ] **Step 2: Create editor sub-components** (NodeList, MetadataForm, DependencySelect)
- [ ] **Step 3: Create YamlPanel** with syntax highlighting and bidirectional editing
- [ ] **Step 4: Create NodeForm** for individual node editing (command, prompt, depends_on, when, approval)
- [ ] **Step 5: Create WorkflowEditor** as the split-pane container
- [ ] **Step 6: Verify TypeScript compiles, commit**

```bash
git commit -m "feat(workflows): add split-pane workflow editor with YAML preview"
```

---

## Task 15: Command Library Editor

**Files:**
- Create: `cortex-ui/src/features/workflows/components/CommandEditor.tsx`
- Modify: `cortex-ui/src/features/workflows/services/workflowService.ts` (add command CRUD)
- Modify: `cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts` (add command hooks)
- Modify: `cortex-ui/src/features/workflows/types/index.ts` (add WorkflowCommand type)

**Context:** Markdown editor with preview for prompt templates. Supports variable placeholders (`$ARGUMENTS`, `$1`, `$2`), version history, and "fork from built-in" to customize defaults. Backed by the `workflow_commands` table via `DefinitionService`.

Note: The backend command CRUD needs API endpoints. Add `GET /api/workflows/commands`, `POST /api/workflows/commands`, `PUT /api/workflows/commands/{id}`, `DELETE /api/workflows/commands/{id}` to `workflow_definition_api.py`.

- [ ] **Step 1: Add backend command endpoints to workflow_definition_api.py**
- [ ] **Step 2: Add command_service.py** for command CRUD (follows same pattern as definition_service)
- [ ] **Step 3: Add frontend types, service methods, hooks for commands**
- [ ] **Step 4: Create CommandEditor component**
- [ ] **Step 5: Verify TypeScript compiles, commit**

```bash
git commit -m "feat(workflows): add command library editor with markdown preview and versioning"
```

---

## Task 16: Suggested Workflows Dashboard

**Files:**
- Create: `cortex-ui/src/features/workflows/components/SuggestedWorkflows.tsx`
- Modify: `cortex-ui/src/features/workflows/services/workflowService.ts` (add pattern suggestion methods)
- Modify: `cortex-ui/src/features/workflows/hooks/useWorkflowQueries.ts` (add suggestion hooks)
- Modify: `cortex-ui/src/features/workflows/types/index.ts` (add DiscoveredPattern type)

**Context:** Dashboard showing discovered patterns sorted by `final_score`. Each card shows pattern name, description, involved repos, and suggested YAML preview. Actions: Accept (creates definition), Customize (opens in editor), Dismiss (decays score).

- [ ] **Step 1: Add DiscoveredPattern type**
- [ ] **Step 2: Add pattern service methods + hooks**
- [ ] **Step 3: Create SuggestedWorkflows component**
- [ ] **Step 4: Wire feedback loop** (dismiss → POST /api/patterns/suggestions/{id}/dismiss)
- [ ] **Step 5: Verify TypeScript compiles, commit**

```bash
git commit -m "feat(workflows): add Suggested Workflows dashboard with accept/customize/dismiss"
```

---

## Task 17: Workflows Page & Navigation

**Files:**
- Create: `cortex-ui/src/features/workflows/components/WorkflowsPage.tsx`
- Modify: `cortex-ui/src/pages/` (add route)
- Modify: navigation component (add Workflows link)

**Context:** Main page combining all workflow sub-views: tab navigation between Runs, Definitions, Approvals, Suggestions. Uses existing Cortex Tron-inspired glassmorphism styling.

- [ ] **Step 1: Create WorkflowsPage** with tab navigation
- [ ] **Step 2: Add route and navigation link**
- [ ] **Step 3: Verify full app compiles, commit**

```bash
git commit -m "feat(workflows): add WorkflowsPage with tab navigation and route"
```

---

## Task 18: Deprecate Agent Work Orders

**Files:**
- Modify: `python/src/server/api_routes/agent_work_orders_proxy.py` (add deprecation warning)
- Remove: `python/src/agent_work_orders/` (entire module)

**Context:** After all 4 phases are complete, the old agent work orders service is superseded by Workflows 2.0. Add a deprecation header to the proxy, then remove the module entirely. Fix-forward: no backward compatibility.

- [ ] **Step 1: Add deprecation response header to agent_work_orders_proxy**
- [ ] **Step 2: Remove `python/src/agent_work_orders/` directory**
- [ ] **Step 3: Remove agent-work-orders dependency group from pyproject.toml**
- [ ] **Step 4: Remove Docker Compose service for agent-work-orders**
- [ ] **Step 5: Commit**

```bash
git commit -m "chore(workflows): deprecate and remove agent work orders service"
```

---

## Task 19: Final Verification

- [ ] **Step 1: Run all workflow tests**

Run: `cd python && uv run pytest tests/server/services/workflow/ tests/server/services/pattern_discovery/ tests/server/services/generative_ui/ -v`

- [ ] **Step 2: Verify backend starts**
- [ ] **Step 3: Verify frontend compiles with zero errors**
- [ ] **Step 4: Update LeaveOff Point**

---

## Propagation Steps

| What Changed | How to Propagate |
|---|---|
| pyproject.toml (new deps) | `docker compose up --build -d` |
| Backend Python files | `docker compose restart cortex-server` |
| Database migrations 033-034 | Run SQL in Supabase SQL editor |
| Frontend files | Auto-reloads with `npm run dev` |
| docker-compose.yml (trinity profile) | `docker compose --profile trinity up -d` |
| Agent work orders removal | `docker compose down` then `docker compose up -d` |
