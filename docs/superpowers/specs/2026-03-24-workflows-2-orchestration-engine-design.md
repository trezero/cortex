# Workflows 2.0: Control Plane & Orchestration Engine Design

**Date**: 2026-03-24
**Status**: Draft (Revised — Control Plane Architecture)
**Scope**: Transition Cortex from a linear CLI-wrapper into a Control Plane that dispatches DAG-based workflows to the remote-coding-agent for execution, with omnichannel HITL approvals, UI-driven workflow authoring, and proactive pattern discovery.

---

## Table of Contents

1. [Context & Motivation](#1-context--motivation)
2. [Design Decisions](#2-design-decisions)
3. [System Architecture](#3-system-architecture)
4. [Workflow Dispatch & State Tracking](#4-workflow-dispatch--state-tracking)
5. [HITL Router & Approval Flow](#5-hitl-router--approval-flow)
6. [Remote-Agent Protocol](#6-remote-agent-protocol)
7. [Workflow Editor & YAML Schema](#7-workflow-editor--yaml-schema)
8. [Pattern Discovery Engine](#8-pattern-discovery-engine)
9. [Database Schema](#9-database-schema)
10. [Migration from Agent Work Orders](#10-migration-from-agent-work-orders)
11. [Remote-Agent Integration Bridge](#11-remote-agent-integration-bridge)

---

## 1. Context & Motivation

### Current State

Cortex's Agent Work Orders service (`python/src/agent_work_orders/`, ~6,100 LOC) automates development workflows using a linear, hardcoded sequence of steps (`create-branch` → `planning` → `execute` → `commit` → `create-pr` → `prp-review`). It wraps the Claude Code CLI in subprocess calls, uses static Markdown prompt files, stores state in memory only, and has no human-in-the-loop capabilities.

Separately, Cortex serves as the MCP brain for a `remote-coding-agent` system that runs headless Claude Code instances connected to per-project Telegram bots. The remote-agent already has a battle-tested DAG workflow executor (TypeScript) with topological layering, in-memory concurrency via `Promise.allSettled`, shell escaping, condition evaluation (`evaluateCondition`), the Claude Agent SDK, session management with resumption, and YAML workflow definitions with conditional branching.

### Problem

1. **Rigid orchestration**: Linear step execution cannot express conditional branching, parallel execution, or approval gates.
2. **No HITL**: Users cannot review plans or approve PRs before the agent proceeds.
3. **Brittle CLI wrapper**: Subprocess-based Claude CLI execution lacks structured outputs and tool calling.
4. **Static commands**: Markdown prompt files are not editable from the UI and have no versioning.
5. **Two disconnected systems**: Cortex and the remote-agent share no orchestration protocol despite serving the same user.
6. **Duplicated execution logic**: Building a new DAG engine in Python would duplicate thousands of lines of battle-tested TypeScript execution code in the remote-agent.
7. **No cross-repo intelligence**: Neither system analyzes activity patterns to suggest workflow automation.

### Goal

Transform Cortex into a **Control Plane** that:
- Stores canonical workflow definitions (YAML) and serves as the workflow registry
- Dispatches workflows to remote-agent instances for native DAG execution
- Tracks execution state as a mirror of the remote-agent's progress
- Handles HITL approval gates via the Cortex UI and a direct Cortex Telegram bot
- Provides a UI-driven workflow editor with YAML-native storage
- Proactively discovers and suggests workflow automation patterns from cross-repo activity

Cortex does **not** implement DAG evaluation, topological sorting, condition evaluation, or node scheduling. Those responsibilities belong to the remote-coding-agent's existing TypeScript engine.

---

## 2. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Architecture model** | Control Plane — Cortex stores definitions, dispatches YAML, tracks state, handles HITL. Remote-agent executes the DAG natively in TypeScript. | Avoids duplicating the remote-agent's battle-tested DAG executor (~3,000 LOC). Keeps Cortex focused on orchestration-level concerns (state, approvals, UI) while the remote-agent handles execution-level concerns (processes, concurrency, isolation). |
| **HITL channel priority** | UI-first — rich A2UI approvals in Cortex UI; Telegram gets summary + approve/reject buttons + link | Rich diffs and plan rendering require the UI; Telegram's formatting constraints make it secondary |
| **Telegram bot strategy** | Direct Cortex bot — a single, lightweight, global Telegram bot owned by Cortex for system notifications and HITL approvals | Eliminates the remote-agent as a single point of failure for approval delivery. Cortex owns the notification path end-to-end. |
| **AI execution strategy** | Fully delegated — the remote-agent uses the Claude Agent SDK natively for all execution. Cortex makes no LLM calls for workflow execution. | By delegating to the remote-agent, we get native SDK integration without building a separate executor in Python. |
| **Command/workflow storage** | YAML-native with UI editor, stored in Supabase, compatible with remote-agent format | Avoids n8n-level visual builder complexity; maintains compatibility with existing YAML workflows |
| **Pattern discovery trigger** | Scheduled batch (nightly) + on-demand analysis | Multi-day patterns don't need real-time detection; nightly batch + on-demand gives 90% value at 30% complexity |
| **Communication protocol** | REST-only between Cortex and remote-agent; SSE from Cortex to UI clients | Remote-agent pushes state to Cortex via REST callbacks. Cortex relays to UI via SSE. Simple, reliable, no bidirectional SSE complexity. |
| **HITL payload format** | A2UI components — deterministic templates for standard approval types; LLM generation only for custom types | Keeps HITL hot-path latency near zero for standard gates. Companion spec covers full A2UI integration. |
| **Execution backend abstraction** | Routing table — `execution_backends` table stores connection info for remote-agent instances, no capability negotiation | YAGNI. Keep the table for routing (multiple remote-agents for multiple projects) but drop generic multi-backend abstraction. Generalize later if needed. |

---

## 3. System Architecture

### Component Map

```
┌─────────────────────┐    ┌──────────────────────────────┐    ┌──────────────────────┐
│    CLIENTS           │    │     CORTEX (Control Plane)    │    │  REMOTE-CODING-AGENT │
│                      │    │                              │    │  (Execution Engine)  │
│  Cortex Web UI  ◄────SSE──┤  Workflow Registry           │    │                      │
│                      │    │  State Mirror                ├─REST─►  DAG Executor (TS)  │
│  Cortex Telegram ◄───Bot──┤  HITL Router                 │    │  Claude Agent SDK    │
│  Bot (global)        │    │  Pattern Discovery           ◄─REST──  State Callbacks    │
│                      │    │  Generative UI (A2UI)        │    │  Worktree Isolation   │
│  MCP Clients         │    │                              │    │                      │
└─────────────────────┘    └──────────────┬───────────────┘    └──────────────────────┘
                                          │
                                ┌─────────┴─────────┐
                                │     SUPABASE       │
                                │  PostgreSQL        │
                                │  + pgvector        │
                                └────────────────────┘
```

### Data Flow

```
1. User triggers workflow         → REST POST to Cortex
2. Cortex dispatches YAML         → REST POST to remote-agent
3. Remote-agent executes DAG      → native TS engine
4. Node state changes             → REST callback to Cortex
5. Cortex updates DB + fires SSE  → UI receives live updates
6. Approval gate hit              → REST webhook to Cortex
7. Cortex renders A2UI + notifies → SSE to UI, message to Telegram bot
8. User approves                  → REST to Cortex
9. Cortex sends resume signal     → REST POST to remote-agent
10. Workflow completes            → final REST callback to Cortex
```

### Communication Summary

| Path | Protocol | Purpose |
|------|----------|---------|
| Client → Cortex | REST | Start workflow, approve/reject, cancel, CRUD definitions |
| Cortex → UI Client | SSE | Live state updates, approval notifications |
| Cortex → Remote-Agent | REST | Dispatch workflow, resume after approval, cancel |
| Remote-Agent → Cortex | REST | Report node state changes, request approvals |
| Cortex → Telegram | Bot API | Send approval summaries with inline buttons |
| Telegram → Cortex | Webhook | Receive approval button callbacks |

### Architectural Note: SSE as a New Pattern

Cortex's main server (`python/src/server/`) currently uses HTTP polling with smart intervals and has no SSE endpoints. This design introduces SSE to the main Cortex server for workflow events to the UI.

SSE is used **only** for Cortex → UI client communication. The Cortex ↔ remote-agent channel is pure REST (callbacks + dispatch).

**Fallback behavior**: SSE is a latency optimization, not a correctness requirement. If the SSE connection drops, the UI falls back to polling `GET /api/workflows/{run_id}` on a 5-second interval (same smart polling pattern used elsewhere in Cortex).

---

## 4. Workflow Dispatch & State Tracking

### Cortex's Role

Cortex does **not** evaluate DAGs, sort nodes topologically, or schedule execution. It:

1. **Stores** workflow definitions (YAML) in Supabase
2. **Dispatches** the full YAML payload to a remote-agent instance
3. **Mirrors** execution state by receiving REST callbacks from the remote-agent
4. **Pauses** workflows when the remote-agent reports an approval gate
5. **Resumes** workflows by sending a resume signal after user approval
6. **Cancels** workflows by sending a cancel signal to the remote-agent

### Node State Machine

Cortex tracks node states as a mirror of the remote-agent's execution progress:

```
pending → running → completed
                  → waiting_approval → completed (approved)
                                     → failed (rejected)
         → failed
         → skipped
         → cancelled
```

| State | Meaning |
|-------|---------|
| `pending` | Node not yet reached by the remote-agent's DAG executor |
| `running` | Remote-agent is actively executing this node |
| `waiting_approval` | Remote-agent paused; waiting for HITL resolution from Cortex |
| `completed` | Node finished successfully |
| `failed` | Node finished with error, or approval was rejected |
| `skipped` | Node's `when:` condition evaluated false (by remote-agent) |
| `cancelled` | User cancelled the workflow from Cortex |

### Workflow Run Status

| Status | Meaning |
|--------|---------|
| `pending` | Run created, not yet dispatched |
| `dispatched` | YAML sent to remote-agent, awaiting first callback |
| `running` | At least one node is `running` |
| `paused` | A node is `waiting_approval`; DAG execution suspended |
| `completed` | All nodes in terminal states; workflow succeeded |
| `failed` | At least one node failed; no further progress possible |
| `cancelled` | User cancelled the workflow |

### Dispatch Flow

```
1. User creates workflow run (via UI, MCP, or chat)
2. Cortex:
   a. Creates workflow_run record (status: pending)
   b. Creates workflow_nodes records for all YAML nodes (state: pending)
   c. Resolves target backend from execution_backends table
   d. POSTs dispatch payload to remote-agent:
      POST {backend_url}/api/cortex/workflows/execute
      {
        "workflow_run_id": "wr_abc123",
        "yaml_content": "...",
        "trigger_context": {
          "user_request": "Add rate limiting to the API",
          "project_id": "proj_xyz"
        },
        "node_id_map": {
          "create-branch": "uuid-1",   // YAML node ID → Cortex DB UUID
          "planning": "uuid-2",
          ...
        },
        "callback_url": "http://cortex:8181/api/workflows"
      }
   e. Updates workflow_run status to dispatched
3. Remote-agent receives YAML, begins native DAG execution
4. Remote-agent fires REST callbacks to Cortex as nodes progress
5. Cortex updates workflow_nodes + workflow_run states, fires SSE to UI
```

### Node ID Mapping

The `node_id_map` bridges Cortex's database UUIDs with the YAML's string node IDs. When the remote-agent reports a node result, it includes the Cortex UUID so Cortex can update the correct database record without ambiguity.

### Backend Routing

When dispatching a workflow, Cortex resolves the target backend:

1. If the `workflow_run` specifies a `backend_id`, use that backend
2. Otherwise, find a backend registered for the run's `project_id`
3. If no project-specific backend exists, use the default backend (no `project_id` set)
4. If no backends are registered, fail the run immediately with a clear error

### File Location

```
python/src/server/services/workflow/
├── dispatch_service.py     # Workflow dispatch, backend routing, state tracking
├── state_service.py        # Process callbacks, update DB, fire SSE events
└── workflow_models.py      # RunStatus, NodeState, dispatch/callback types
```

---

## 5. HITL Router & Approval Flow

### Approval Request Lifecycle

**Phase 1 — Pause** (triggered by remote-agent webhook):
1. Remote-agent's DAG executor encounters a node with `approval.required: true`
2. Remote-agent pauses its execution loop
3. Remote-agent fires webhook to Cortex:
   ```
   POST {callback_url}/approvals/request
   {
     "workflow_run_id": "wr_abc123",
     "workflow_node_id": "uuid-for-plan-review",
     "yaml_node_id": "plan-review",
     "approval_type": "plan_review",
     "node_output": "## Plan Summary\n\nThis PR adds rate limiting...",
     "channels": ["ui", "telegram"]
   }
   ```
4. Cortex updates node state to `waiting_approval`, run status to `paused`
5. Cortex generates A2UI payload:
   - Standard types (`plan_review`, `pr_review`, `deploy_gate`): deterministic JSON templates
   - Custom type: calls Second Brain's A2UI generation service (see companion spec)
6. Cortex creates `approval_request` record with A2UI payload
7. HITL Router dispatches to configured channels

**Phase 2 — Wait**:
8. Remote-agent's DAG loop is suspended, waiting for resume signal
9. Configurable TTL (default: 24 hours)
10. If TTL expires → Cortex auto-rejects, sends resume with `decision: "rejected"` to remote-agent

**Phase 3 — Resume**:
11. User approves via UI or Telegram → `POST /api/workflows/approvals/{id}/resolve`
12. Cortex updates approval status, node state, and run status
13. Cortex sends resume signal to remote-agent:
    ```
    POST {backend_url}/api/cortex/workflows/{run_id}/resume
    {
      "yaml_node_id": "plan-review",
      "decision": "approved",
      "comment": "Looks good, proceed"
    }
    ```
14. Remote-agent resumes DAG execution from the paused node
15. SSE fired to UI; Telegram message edited with resolution status

### Approval Types

| Type | UI Payload (A2UI) | Telegram Payload |
|------|-------------------|-----------------|
| `plan_review` | Deterministic: ExecutiveSummary + StepCard list + StatCard (scope) + CodeBlock | Summary text + approve/reject buttons + link to full UI view |
| `pr_review` | Deterministic: StatCard (files/insertions/deletions) + ComparisonTable + CodeBlock + ProgressRing | Stats text + approve/reject buttons + link |
| `deploy_gate` | Deterministic: StatCard (environment/build) + ChecklistItem list + CalloutCard | Environment + test summary + approve/reject buttons + link |
| `custom` | LLM-generated via Second Brain A2UI service | Node output summary + approve/reject buttons + link |

### HITL Router Architecture

Channel-agnostic dispatch via `ApprovalChannel` protocol:

```python
class ApprovalChannel(Protocol):
    async def send_approval_request(
        self,
        approval: ApprovalRequest,
        project: Project,
    ) -> None: ...

    async def notify_resolution(
        self,
        approval: ApprovalRequest,
        decision: str,
        resolved_by: str,
    ) -> None: ...
```

Channels only implement the **send** side. All resolution converges on a single REST endpoint (`POST /api/workflows/approvals/{id}/resolve`). Adding a new channel (Slack, Discord) = implement the two methods above.

### Direct Cortex Telegram Bot

Cortex runs a lightweight, global Telegram bot for system notifications and HITL approvals. This bot is independent of the remote-agent's per-project Telegram adapter.

**Responsibilities**:
- Send approval request summaries with inline keyboard buttons (Approve / Reject)
- Handle `callback_query` events from button presses
- Edit messages with resolution status after approval/rejection
- Route callback data to `POST /api/workflows/approvals/{id}/resolve`

**Configuration**:
- `CORTEX_TELEGRAM_BOT_TOKEN` environment variable
- `CORTEX_TELEGRAM_CHAT_IDS` — comma-separated list of authorized chat IDs (security: only respond to known chats)
- Bot runs as an async background task within the Cortex server process (using `python-telegram-bot` library)

**Inline Keyboard Format**:
```python
InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Approve", callback_data=f"approve:{approval_id}"),
        InlineKeyboardButton("Reject", callback_data=f"reject:{approval_id}"),
    ],
    [
        InlineKeyboardButton("View in Cortex", url=f"{cortex_url}/workflows/{run_id}/approvals/{approval_id}"),
    ]
])
```

**Fallback**: If the Telegram bot is not configured (`CORTEX_TELEGRAM_BOT_TOKEN` not set), the Telegram channel is silently disabled. Approvals are still available via the UI. No errors surfaced.

### A2UI Integration

Approval payloads use the A2UI (Agent-to-UI) component format — a JSON specification where each element maps to a registered React component in the Cortex frontend. The A2UI component library, renderer, and generation service are defined in a companion spec: `docs/superpowers/specs/2026-03-24-generative-ui-integration-design.md`.

**Standard approval types use deterministic templates** — no LLM call required. The `a2ui_service` maps the `approval_type` and `node_output` to a fixed component layout:

```python
APPROVAL_TEMPLATES = {
    "plan_review": [
        {"type": "a2ui.ExecutiveSummary", "zone": "hero"},
        {"type": "a2ui.StepCard", "zone": "content", "repeat": True},
        {"type": "a2ui.StatCard", "zone": "sidebar"},
    ],
    "pr_review": [
        {"type": "a2ui.StatCard", "zone": "hero"},
        {"type": "a2ui.ComparisonTable", "zone": "content"},
        {"type": "a2ui.CodeBlock", "zone": "content"},
    ],
    "deploy_gate": [
        {"type": "a2ui.StatCard", "zone": "hero"},
        {"type": "a2ui.ChecklistItem", "zone": "content", "repeat": True},
        {"type": "a2ui.CalloutCard", "zone": "sidebar"},
    ],
}
```

The template populates component `props` by parsing the `node_output` text (markdown heading extraction, code block detection, stat parsing). Only the `custom` type calls the Second Brain's LLM-based generation service.

### File Location

```
python/src/server/services/workflow/
├── hitl_router.py             # HITLRouter, channel dispatch
├── hitl_channels/
│   ├── ui_channel.py          # SSE-based UI notifications
│   └── telegram_channel.py    # Direct Cortex Telegram bot
├── hitl_models.py             # ApprovalRequest, ApprovalType, channel types
└── approval_templates.py      # Deterministic A2UI templates for standard types
```

---

## 6. Remote-Agent Protocol

### Overview

The protocol between Cortex and the remote-agent is a simple REST-based callback pattern. Cortex dispatches workflows and sends control signals (resume, cancel). The remote-agent reports execution state back to Cortex via REST callbacks. There is no SSE between Cortex and the remote-agent.

### Backend Registration

Remote-agent instances register with Cortex to enable workflow dispatch:

```
POST /api/workflows/backends/register
Body: {
  "name": "remote-agent-alpha",
  "base_url": "http://remote-agent:3000",
  "project_id": "proj_xyz"           // Optional: scopes this backend to a project
}
Response: {
  "backend_id": "be_abc123",
  "auth_token": "tok_..."            // Store this; used for all callbacks
}
```

The `auth_token` is returned once at registration. Cortex stores `auth_token_hash` (bcrypt). The remote-agent includes it in all callback requests as `Authorization: Bearer {token}`.

### Heartbeat

- Remote-agent sends heartbeat every 30 seconds: `POST /api/workflows/backends/{id}/heartbeat`
- If 3 intervals missed (90s): backend marked `unhealthy`
- Running workflow nodes on an unhealthy backend are marked `failed` with `error: "backend_timeout"`
- When the backend recovers and sends a heartbeat, it is marked `healthy` again

### Cortex → Remote-Agent Endpoints

These are endpoints the remote-agent must implement:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/cortex/workflows/execute` | POST | Dispatch a workflow for execution |
| `/api/cortex/workflows/{run_id}/resume` | POST | Resume after HITL approval |
| `/api/cortex/workflows/{run_id}/cancel` | POST | Cancel a running workflow |

### Remote-Agent → Cortex Callbacks

These are Cortex endpoints the remote-agent calls during execution:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workflows/nodes/{id}/state` | POST | Report node state change (running, completed, failed, skipped) |
| `/api/workflows/nodes/{id}/progress` | POST | Report execution progress (log lines, partial output) |
| `/api/workflows/approvals/request` | POST | Request HITL approval (pauses workflow) |
| `/api/workflows/runs/{id}/complete` | POST | Report workflow completion/failure |

### Callback Payloads

**Node state change** (`POST /api/workflows/nodes/{id}/state`):
```json
{
  "state": "completed",
  "output": "feat/rate-limiting",
  "session_id": "sess_abc123",
  "duration_seconds": 45.2
}
```

**Approval request** (`POST /api/workflows/approvals/request`):
```json
{
  "workflow_run_id": "wr_abc123",
  "node_id": "uuid-for-plan-review",
  "yaml_node_id": "plan-review",
  "approval_type": "plan_review",
  "node_output": "## Plan Summary\n\n...",
  "channels": ["ui", "telegram"]
}
```

**Workflow completion** (`POST /api/workflows/runs/{id}/complete`):
```json
{
  "status": "completed",
  "summary": "Feature implemented successfully. PR #42 created.",
  "node_outputs": {
    "create-branch": "feat/rate-limiting",
    "create-pr": "https://github.com/org/repo/pull/42"
  }
}
```

### Authentication

- **UI-facing endpoints** (`/api/workflows`, `/api/workflows/approvals`): Same authentication as all other Cortex API endpoints (no additional auth for single-user beta)
- **Callback endpoints** (`/api/workflows/nodes/*`, `/api/workflows/runs/*`, `/api/workflows/approvals/request`): Authenticated via `Authorization: Bearer {token}` header using the token issued during backend registration

### Error Handling

All workflow API endpoints follow Cortex's existing error handling patterns — custom exceptions in `python/src/server/exceptions.py` processed by exception handlers in `main.py`.

**Dispatch failures**: If the remote-agent is unreachable, the workflow run is marked `failed` with a clear error message. No retries — the user re-triggers when the backend is available.

**Callback failures**: If a callback from the remote-agent fails (Cortex is temporarily down), the remote-agent should retry with exponential backoff (3 attempts, 1s/2s/4s delays). After 3 failures, the remote-agent logs the error and continues execution — Cortex's state will be stale but the work completes. On the next successful callback, Cortex reconciles by querying the remote-agent for the full run state.

### REST API Surface

**Workflow Management** (clients):
- `POST /api/workflows` — Create and dispatch workflow run
- `GET /api/workflows` — List workflow runs (filterable by status, project)
- `GET /api/workflows/{run_id}` — Get run status + all node states
- `GET /api/workflows/{run_id}/events` — SSE stream for UI
- `POST /api/workflows/{run_id}/cancel` — Cancel workflow run

**Approval Management** (clients + Telegram bot callback):
- `GET /api/workflows/approvals` — List pending approvals
- `GET /api/workflows/approvals/{id}` — Get full approval with A2UI payload
- `POST /api/workflows/approvals/{id}/resolve` — Approve or reject

**Definition Management** (UI editor):
- `GET /api/workflows/definitions` — List all definitions
- `POST /api/workflows/definitions` — Create new definition
- `PUT /api/workflows/definitions/{id}` — Update (creates new version)
- `DELETE /api/workflows/definitions/{id}` — Soft delete
- `POST /api/workflows/definitions/{id}/export` — Export as YAML file

**Backend Management** (registration + health):
- `POST /api/workflows/backends/register` — Register remote-agent instance
- `POST /api/workflows/backends/{id}/heartbeat` — Heartbeat
- `GET /api/workflows/backends` — List registered backends
- `DELETE /api/workflows/backends/{id}` — Deregister backend

**Callback Endpoints** (remote-agent → Cortex):
- `POST /api/workflows/nodes/{id}/state` — Node state change
- `POST /api/workflows/nodes/{id}/progress` — Execution progress
- `POST /api/workflows/approvals/request` — HITL approval request
- `POST /api/workflows/runs/{id}/complete` — Workflow completion

### SSE Event Schema (UI Only)

A single SSE stream type for UI clients. Uses named events with JSON `data` payloads and sequential `id` fields for reconnection via `Last-Event-ID`. A 256-event replay buffer is maintained per stream.

**Client SSE events** (`GET /api/workflows/{run_id}/events`):

| Event Type | Data Payload | When Fired |
|---|---|---|
| `node_state_changed` | `{node_id, previous_state, new_state, output?}` | Any node state transition |
| `run_status_changed` | `{status, previous_status}` | Workflow run status change |
| `approval_requested` | `{approval_id, node_id, approval_type, summary}` | HITL gate hit |
| `approval_resolved` | `{approval_id, decision, resolved_by, resolved_via}` | HITL gate resolved |
| `node_progress` | `{node_id, message}` | Remote-agent reports progress |
| `heartbeat` | `{timestamp}` | Every 15 seconds |

### File Location

```
python/src/server/api_routes/
├── workflow_api.py             # Workflow run management + SSE stream
├── workflow_approval_api.py    # Approval endpoints
├── workflow_backend_api.py     # Registration, heartbeat, callbacks
└── workflow_definition_api.py  # Definition CRUD + export

python/src/server/services/workflow/
├── dispatch_service.py         # Workflow dispatch, backend routing
├── state_service.py            # Process callbacks, update state, fire SSE
├── backend_service.py          # Registration, health tracking
└── workflow_models.py          # All workflow-related Pydantic models
```

---

## 7. Workflow Editor & YAML Schema

### Unified YAML Schema

Extends the remote-agent's existing format with Cortex-specific fields:

```yaml
name: implement-feature
description: "Full feature implementation with plan review gate"
provider: claude
model: sonnet

nodes:
  - id: create-branch
    command: create-branch
    context: fresh

  - id: planning
    command: planning
    depends_on: [create-branch]

  - id: plan-review                    # HITL gate node
    prompt: "Summarize the plan for approval"
    depends_on: [planning]
    approval:                          # Cortex extension
      required: true
      type: plan_review
      ttl_hours: 24
      channels: [ui, telegram]

  - id: execute
    command: execute
    depends_on: [plan-review]

  - id: commit
    command: commit
    depends_on: [execute]

  - id: create-pr
    command: create-pr
    depends_on: [commit]

  # Conditional branching (same syntax as remote-agent)
  - id: classify-issue
    prompt: "Classify this as BUG or FEATURE. Output JSON: {type: '...'}"
    output_format: {type: "object", properties: {type: {type: "string"}}}

  - id: hotfix-path
    command: hotfix
    depends_on: [classify-issue]
    when: "$classify-issue.output.type == 'BUG'"

  - id: feature-path
    command: planning
    depends_on: [classify-issue]
    when: "$classify-issue.output.type == 'FEATURE'"

# Cortex-only metadata (ignored by remote-agent)
cortex:
  project_id: proj_xyz
  tags: [feature, full-pipeline]
  icon: rocket
  suggested_by: pattern_discovery
```

**Compatibility strategy**: The `approval:` block and `cortex:` metadata are Cortex extensions. The remote-agent's YAML parser ignores unknown fields, so the same file works in both systems. The `approval:` block is the signal to the remote-agent's Cortex bridge to pause execution and fire a webhook — if no bridge is active, the field is ignored and the node executes normally.

### DAG Evaluation Ownership

All DAG evaluation logic — topological sorting, `when:` condition evaluation, `trigger_rule` processing, parallel fan-out via `Promise.allSettled` — is handled by the remote-agent's existing TypeScript engine. Cortex validates YAML structure (node IDs, `depends_on` references, required fields) but does not interpret execution semantics.

### Storage

YAML is the canonical format stored in the `workflow_definitions` table (`yaml_content` column). A pre-parsed `parsed_definition` JSONB column enables fast queries (e.g., find definitions containing a specific command, list definitions with approval gates). Versioning is automatic — updates create new versions with `is_latest` flag management.

### UI Editor

Split-pane design:
- **Left**: Form panel — sortable node list, metadata fields, approval gate toggles, dependency multi-selects, condition input with syntax help
- **Right**: Live YAML preview — editable, bidirectional sync with form

Import/export: Upload YAML from `.cortex/workflows/` → parsed into form. Export generates clean YAML (strips `cortex:` metadata) compatible with standalone remote-agent use.

### Command Library

Commands referenced by workflow nodes are resolved by the **remote-agent** at execution time using its own `CommandRouter`. Cortex stores command templates in the `workflow_commands` table for UI editing and versioning, but the canonical resolution at execution time is the remote-agent's responsibility.

When Cortex dispatches a workflow, it can optionally include resolved command templates in the dispatch payload if the remote-agent requests them. This enables a UI-authored command to override a filesystem `.md` file without requiring the remote-agent to have direct Supabase access.

UI provides a markdown editor with preview, variable placeholder hints, version history, and "fork from built-in" to customize defaults.

### File Location

```
python/src/server/services/workflow/
├── definition_service.py       # CRUD, versioning, YAML parsing/validation
├── command_service.py          # Command storage, versioning
└── yaml_schema.py              # YAML validation (structure only, not execution semantics)

cortex-ui/src/features/workflows/
├── components/
│   ├── WorkflowEditor.tsx      # Split-pane editor
│   ├── NodeForm.tsx            # Individual node editing
│   ├── YamlPanel.tsx           # Live YAML preview/editor
│   ├── CommandEditor.tsx       # Markdown command editor
│   ├── WorkflowRunView.tsx     # Live workflow execution view
│   ├── ApprovalList.tsx        # Pending approvals list
│   ├── ApprovalDetail.tsx      # Full approval payload + A2UI diff view
│   └── SuggestedWorkflows.tsx  # Pattern discovery suggestions
├── hooks/
│   └── useWorkflowQueries.ts
├── services/
│   └── workflowService.ts
└── types/
    └── index.ts
```

---

## 8. Pattern Discovery Engine

### Overview

The Pattern Discovery Engine analyzes activity across all Cortex-connected repositories to proactively suggest reusable workflow automations. It uses a two-stage pipeline: first normalizing heterogeneous events (git commits, agent conversations, workflow runs) into structured tuples, then mining those tuples for repeated patterns.

### Two-Stage Pipeline Architecture

```
Stage 1: Normalization (per-event, on ingest)
┌─────────────┐   ┌──────────────────┐   ┌───────────────────┐
│ Raw Event    │──→│ Intent Extractor │──→│ Normalized        │
│ (commit/chat │   │ (Haiku batch)    │   │ Activity Record   │
│  /workflow)  │   │                  │   │                   │
└─────────────┘   └──────────────────┘   └───────────────────┘
                   Extracts:
                   - action_verb (created, fixed, refactored, tested, deployed)
                   - target_object (auth middleware, API endpoint, database schema)
                   - trigger_context (pre-PR, post-merge, on-demand, scheduled)

Stage 2: Pattern Mining (nightly batch + on-demand)
┌───────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Normalized        │──→│ Sequence Mining  │──→│ Pattern          │
│ Activity Records  │   │ + Embedding      │   │ Candidates       │
│ (last 30 days)    │   │ Clustering       │   │                  │
└───────────────────┘   └──────────────────┘   └──────────────────┘
```

The key insight: **extract structured fields first, then embed the structured representation**. This solves the semantic mismatch between git commits (code-style text) and conversation transcripts (natural language). "Refactored auth middleware" and "hey can you fix the login flow" both normalize to `{action: "fix", target: "authentication", trigger: "on-demand"}`, which clusters trivially.

### Data Capture Pipeline

Three input streams converge into a unified `activity_events` table:

| Stream | Source | Captured Data | Frequency |
|--------|--------|---------------|-----------|
| **Git Activity** | Post-commit hooks + periodic git log polling | Commit message, diff stats, file paths, branch patterns, time of day | Real-time via hook or 15min poll |
| **Agent Conversations** | Remote-agent messages + Cortex chat sessions | User request text, repo context, tools used, workflow invocations, outcomes | On conversation end |
| **Workflow Runs** | `workflow_runs` + `workflow_nodes` tables | Which workflow, node execution patterns, HITL approval behavior, repo context | On workflow completion |

### Stage 1: Intent Normalization

For each new event, extract a structured tuple using Haiku:

**Input** (batched — up to 50 events per prompt):
```
Event 1: [commit] "refactored auth middleware to use JWT tokens"
Event 2: [conversation] "can you update the login page to handle OAuth?"
Event 3: [workflow_run] "implement-feature workflow on repo alpha, nodes: create-branch, planning, execute, commit, create-pr"
```

**Output** (structured JSON):
```json
[
  {"action_verb": "refactored", "target_object": "authentication", "trigger_context": "on-demand"},
  {"action_verb": "updated", "target_object": "authentication", "trigger_context": "on-demand"},
  {"action_verb": "implemented", "target_object": "feature", "trigger_context": "workflow"}
]
```

After extraction, generate a vector embedding of the normalized tuple (concatenated as a sentence: "refactored authentication on-demand"). Store the embedding in `intent_embedding`.

**Cost controls**:
- **Batch extraction**: Group up to 50 events into a single Haiku prompt
- **Daily cap**: Maximum 500 extractions per day (configurable via `PATTERN_DISCOVERY_DAILY_CAP`). Events beyond the cap are queued for the next batch cycle
- **Deduplication**: Skip commits with near-identical messages (automated version bumps, merge commits from bots). Use a simple trigram similarity check (threshold 0.9) before sending to LLM.
- **Sampling**: For repos with 100+ daily commits, sample a representative subset

### Stage 2: Pattern Mining

#### Sequence Mining (Temporal Patterns)

Pure embedding similarity finds *similar events*, but the real value is *repeated sequences*. "I notice you always run security audits before PRs" requires detecting the temporal pattern: `[security-audit] → [create-pr]` happening repeatedly.

**Approach**: After normalization, extract ordered activity sequences per repo per week. Use a frequent subsequence algorithm (PrefixSpan, via the `prefixspan` PyPI package) on the `(action_verb, target_object)` tuples:

```
Repo Alpha Week 12: [test, auth] → [fix, auth] → [test, auth] → [create-pr, auth]
Repo Alpha Week 13: [test, api] → [fix, api] → [test, api] → [create-pr, api]
Repo Beta  Week 12: [test, database] → [fix, database] → [test, database] → [create-pr, database]
```

PrefixSpan discovers: `[test, *] → [fix, *] → [test, *] → [create-pr, *]` appears 3 times across 2 repos. This is a candidate pattern: "test-fix-retest-PR" workflow.

Minimum support: 3 occurrences across 2+ repos.

#### Embedding Clustering (Similarity Patterns)

For patterns that don't have a clear temporal sequence (e.g., "you always configure logging the same way"), use pgvector cosine similarity on the normalized embeddings:

- Query events from last 30 days
- Cluster threshold: cosine similarity > 0.85
- Minimum cluster size: 3 events across 2+ repos

#### Pattern Scoring

Each discovered pattern (from either method) receives a composite score:

- `frequency_score` = occurrences / days in window
- `cross_repo_score` = unique repos with pattern / total connected repos
- `automation_potential` = % of events that were manual (not workflow-triggered)
- `final_score` = frequency × cross_repo × automation_potential
- Threshold: `final_score > 0.4` → candidate for suggestion

#### Workflow Generation

Send high-scoring patterns to Anthropic API (Sonnet) with the pattern data and example events. Sonnet generates a reusable Workflows 2.0 YAML definition. Validate against the YAML schema. Store in `discovered_patterns` with status `pending_review`.

### User Feedback Loop

User responses to suggested patterns feed back into the scoring model:

| Action | Effect |
|--------|--------|
| **Accepted** | Pattern saved to `workflow_definitions` with `origin: pattern_discovery`. Boost `final_score` for similar future patterns (same cluster). |
| **Customized** | Same as accepted, but store the delta between suggested and accepted YAML. Use the delta to improve the generation prompt for similar patterns. |
| **Dismissed** | Pattern marked `dismissed`. Decay `final_score` for similar patterns. After 3 dismissals of patterns in the same cluster, auto-suppress that cluster. |

### Suggestion Surfacing

- **Cortex UI**: Suggestions panel on Workflows page with Accept / Customize / Dismiss actions
- **Chat/MCP**: `cortex:suggest_workflows` MCP tool for conversational discovery
- Accept saves to `workflow_definitions` with `origin: pattern_discovery`
- Dismiss marks pattern `dismissed`, won't suggest again

### Backfill Strategy

For the 30+ existing projects: run a one-time backfill job that reads git history (last 90 days) and existing workflow run data, ingests into `activity_events`, and runs the normalization pipeline. This seeds the pattern discovery engine with historical data so it can produce suggestions from day one.

### File Location

```
python/src/server/services/pattern_discovery/
├── capture_service.py          # Event ingestion from git, conversations, workflows
├── normalization_service.py    # Stage 1: Haiku-based intent extraction
├── sequence_mining_service.py  # Stage 2a: PrefixSpan temporal pattern detection
├── clustering_service.py       # Stage 2b: pgvector embedding clustering
├── scoring_service.py          # Pattern scoring and threshold evaluation
├── generation_service.py       # Sonnet-based YAML workflow generation
├── suggestion_service.py       # Surfacing logic, feedback loop, status management
└── backfill_service.py         # One-time historical data ingestion
```

---

## 9. Database Schema

### New Tables (Migrations 027–034)

> **Note**: Migration numbering starts at 027 based on the current state of `migration/0.1.0/` (last migration is 026). If other feature branches land migrations before this one, adjust numbering accordingly. Verify against the actual migration directory at implementation time.

**027: workflow_definitions**
- id (uuid PK), name, description, project_id (FK → cortex_projects, nullable), yaml_content (text), parsed_definition (jsonb), version (int), is_latest (bool), tags (text[]), origin (text — 'user' | 'pattern_discovery' | 'import'), created_at, deleted_at
- UNIQUE(name, project_id, version)

**028: workflow_commands**
- id (uuid PK), name, description, prompt_template (text), variables (jsonb), version (int), is_latest (bool), project_id (FK nullable), created_at, deleted_at
- UNIQUE(name, project_id, version)

**029: workflow_runs**
- id (uuid PK), definition_id (FK → workflow_definitions), project_id (FK → cortex_projects), backend_id (FK → execution_backends), status (pending|dispatched|running|paused|completed|failed|cancelled), triggered_by (text), trigger_context (jsonb), started_at, completed_at, created_at
- INDEX on (status), (project_id, status)

**030: workflow_nodes**
- id (uuid PK), workflow_run_id (FK → workflow_runs), node_id (text — YAML node ID), state (pending|running|waiting_approval|completed|failed|skipped|cancelled), output (text), error (text nullable), session_id (text nullable — Claude Agent SDK session for resumption), started_at, completed_at
- INDEX on (workflow_run_id, state)
- UNIQUE(workflow_run_id, node_id)

**031: approval_requests**
- id (uuid PK), workflow_run_id (FK → workflow_runs), workflow_node_id (FK → workflow_nodes.id), yaml_node_id (text — human-readable YAML node ID for display, e.g. "plan-review"), approval_type (text), payload (jsonb — A2UI component array), status (pending|approved|rejected|expired), channels_notified (text[]), resolved_by (text nullable), resolved_via (text nullable — 'ui' | 'telegram'), resolved_comment (text nullable), telegram_message_id (text nullable), expires_at, created_at, resolved_at
- INDEX on (status), (workflow_run_id)

**032: execution_backends**
- id (uuid PK), name (UNIQUE), base_url (text), auth_token_hash (text), project_id (FK → cortex_projects, nullable — null means default backend), status (healthy|unhealthy|disconnected), last_heartbeat_at, registered_at
- INDEX on (project_id)

**033: activity_events**
- id (uuid PK), event_type (commit|conversation|workflow_run), project_id (FK nullable), repo_url (text), raw_content (text — original commit message, conversation excerpt, etc.), action_verb (text nullable — extracted by normalization), target_object (text nullable — extracted by normalization), trigger_context (text nullable — extracted by normalization), intent_embedding (vector nullable — dimension matches Cortex's configured embedding model; use same dimension as `documents.embedding` column for consistency), metadata (jsonb — diff stats, file paths, tools used, etc.), normalized_at (timestamp nullable — null means pending normalization), created_at
- INDEX on (event_type, created_at)
- INDEX on (normalized_at) WHERE normalized_at IS NULL — for batch processing queue
- ivfflat INDEX on intent_embedding

**034: discovered_patterns**
- id (uuid PK), pattern_name, description, pattern_type (text — 'sequence' | 'cluster'), sequence_pattern (jsonb nullable — for sequence mining results: ordered list of action/target tuples), cluster_embedding (vector nullable — for clustering results), source_event_ids (uuid[]), repos_involved (text[]), frequency_score (float), cross_repo_score (float), automation_potential (float), final_score (float), suggested_yaml (text), status (pending_review|accepted|customized|dismissed|expired), accepted_workflow_id (FK → workflow_definitions, nullable), feedback_delta (jsonb nullable — diff between suggested and accepted YAML for customized patterns), discovered_at
- INDEX on (status, final_score DESC)

### Entity Relationships

```
cortex_projects
  ├─← workflow_definitions.project_id
  ├─← workflow_commands.project_id
  ├─← workflow_runs.project_id
  ├─← execution_backends.project_id
  └─← activity_events.project_id

workflow_definitions
  ├─← workflow_runs.definition_id
  └─← discovered_patterns.accepted_workflow_id

workflow_runs
  ├─← workflow_nodes.workflow_run_id
  ├─← approval_requests.workflow_run_id
  └─→ execution_backends.id (via backend_id)

workflow_nodes
  └─← approval_requests.workflow_node_id

activity_events
  └─← discovered_patterns.source_event_ids (array reference)
```

---

## 10. Migration from Agent Work Orders

### Phase 1: The Control Plane & Remote-Agent Bridge (Foundation)

**Goal**: Cortex can dispatch a YAML workflow to the remote-agent, and the remote-agent executes it natively.

- Run database migrations 027–032 (definitions, commands, runs, nodes, approvals, backends)
- Implement backend registration (`POST /api/workflows/backends/register`) and heartbeat
- Implement workflow dispatch service (create run, create nodes, POST to remote-agent)
- Implement callback endpoints (node state, progress, completion)
- Implement SSE stream for UI clients
- Create the `cortex-bridge` module in the remote-coding-agent repo
- Bridge receives YAML, passes to `executeDagWorkflow()`, fires callbacks to Cortex
- Convert the 6 hardcoded agent work order steps into a YAML workflow definition
- Agent work orders service continues running unchanged alongside new system

### Phase 2: Generative UI & HITL Approvals (Magic)

**Goal**: Workflows pause for human review with rich A2UI rendering.

- Port A2UI renderer and component library from Second Brain into Cortex UI
- Implement approval gate handling: remote-agent pauses, fires webhook, Cortex creates approval
- Implement deterministic A2UI templates for standard approval types
- Implement the HITL Router with UI channel (SSE) and Telegram channel (direct bot)
- Implement approval resolution flow: user approves → Cortex sends resume to remote-agent
- Build approval UI in Cortex frontend (ApprovalList, ApprovalDetail with A2UI rendering)

### Phase 3: Pattern Discovery Engine (Intelligence)

**Goal**: Mine the 30+ existing projects to proactively suggest workflow automations.

- Run database migrations 033–034 (activity_events, discovered_patterns)
- Implement event capture pipeline (git hooks, conversation ingestion, workflow completion events)
- Implement Stage 1 normalization (Haiku-based intent extraction)
- Run backfill job on existing 30+ projects (last 90 days of git history)
- Implement Stage 2a sequence mining (PrefixSpan on normalized tuples)
- Implement Stage 2b embedding clustering (pgvector cosine similarity)
- Implement pattern scoring and YAML generation (Sonnet)
- Implement suggestion surfacing (MCP tool + API endpoint)

### Phase 4: Workflow Editor & UI Polish

**Goal**: Users can view, edit, and discover workflows in the Cortex UI.

- Build the split-pane YAML workflow editor (visual node config + live YAML preview)
- Build the command library editor (markdown with preview, versioning)
- Build the "Suggested Automations" dashboard (Accept / Customize / Dismiss)
- Wire the feedback loop (dismiss decays cluster score, accept creates definition)
- Build the workflow execution viewer (live DAG visualization with SSE updates)
- Deprecate and remove agent work orders service

### Deprecation of Agent Work Orders

After Phase 4 is complete:
- All work order creation routed through new Workflows 2.0 engine
- `/api/agent-work-orders/` endpoints return deprecation warning
- Agent work orders module (`python/src/agent_work_orders/`) removed
- Fix-forward: no backward compatibility shims

**Preserved**: Structured logging patterns, GitHub integration (gh CLI operations).

**Replaced**: Linear WorkflowOrchestrator → Control Plane dispatch, in-memory state → Supabase persistence, hardcoded command_map → YAML definitions, separate microservice → integrated into Cortex server, `/api/agent-work-orders/` → `/api/workflows/`, CLI subprocess wrapper → remote-agent's native Claude Agent SDK.

---

## 11. Remote-Agent Integration Bridge

### New Module

Location: `packages/core/src/cortex-bridge/` in the remote-coding-agent repo.

### Responsibilities

1. **Register** with Cortex on startup (`POST /api/workflows/backends/register`)
2. **Receive** workflow dispatch (`POST /api/cortex/workflows/execute`)
3. **Execute** the YAML by passing it to the existing `executeDagWorkflow()` engine
4. **Report** node state changes to Cortex via REST callbacks
5. **Pause** at approval gates and fire approval webhook to Cortex
6. **Resume** when Cortex sends the resume signal
7. **Cancel** gracefully when Cortex sends cancel signal
8. **Heartbeat** every 30 seconds to maintain healthy status

### Execution Flow

```
1. Bridge receives POST /api/cortex/workflows/execute
   - Extracts yaml_content, trigger_context, node_id_map, callback_url
2. Bridge parses YAML (already handled by remote-agent's parser)
3. Bridge hooks into the DAG executor's event system:
   - onNodeStart(nodeId) → POST {callback_url}/nodes/{cortex_id}/state {state: "running"}
   - onNodeComplete(nodeId, output) → POST {callback_url}/nodes/{cortex_id}/state {state: "completed", output}
   - onNodeFailed(nodeId, error) → POST {callback_url}/nodes/{cortex_id}/state {state: "failed", error}
   - onNodeSkipped(nodeId) → POST {callback_url}/nodes/{cortex_id}/state {state: "skipped"}
4. Bridge intercepts approval gates:
   - When DAG executor encounters approval.required: true
   - Bridge pauses executor (stores continuation)
   - Fires POST {callback_url}/approvals/request
   - Awaits POST /api/cortex/workflows/{run_id}/resume
   - On resume: passes decision to continuation, executor resumes
5. On workflow completion:
   - Bridge fires POST {callback_url}/runs/{run_id}/complete
```

### Node ID Translation

The bridge maintains an in-memory map from YAML node IDs to Cortex UUIDs (received in `node_id_map`). All callbacks to Cortex use the Cortex UUID. All internal DAG execution uses the YAML node ID. The bridge translates at the boundary.

### Session Continuity

Node results include `session_id` from the Claude Agent SDK. The bridge includes this in callbacks to Cortex. Cortex stores it in `workflow_nodes.session_id`. If a node needs to continue a previous session (e.g., `execute` continuing from `planning`), the bridge passes the upstream node's `session_id` through the DAG context.

### Isolation

The bridge reuses the remote-agent's existing `IsolationResolver` for git worktree lifecycle. Cortex does not need to know about isolation details — the working directory is managed entirely by the remote-agent.

### Key Principle

The bridge is an **additive** module. The remote-agent's existing orchestrator, adapters, and workflow engine remain untouched. Users can still use the remote-agent standalone without Cortex. The bridge activates only when `CORTEX_URL` is configured in the remote-agent's environment.

### Cancellation

When Cortex sends `POST /api/cortex/workflows/{run_id}/cancel`:

1. Bridge signals the DAG executor to abort
2. Executor sends SIGTERM to any running Claude Code subprocess
3. Waits 5 seconds for graceful shutdown
4. SIGKILL if still running
5. Bridge fires state callbacks for all running/pending nodes as `cancelled`
6. Bridge fires workflow completion callback with `status: "cancelled"`

### Required Remote-Agent Development

| Task | Description |
|------|-------------|
| **Cortex bridge module** | New `packages/core/src/cortex-bridge/` with registration, dispatch handler, callback client, resume handler |
| **DAG executor hooks** | Extend `executeDagWorkflow()` with event callbacks (onNodeStart, onNodeComplete, onNodeFailed, onNodeSkipped) |
| **Approval gate interception** | When `approval.required: true` is present, pause execution and await external resume signal instead of continuing |
| **New REST endpoints** | `/api/cortex/workflows/execute`, `/api/cortex/workflows/{run_id}/resume`, `/api/cortex/workflows/{run_id}/cancel` |

This is scoped as a separate workstream within the remote-agent repo, independent of the Cortex-side implementation.
