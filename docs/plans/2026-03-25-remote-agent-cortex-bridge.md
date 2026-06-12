# Remote-Agent: Cortex Bridge Module

**Date:** 2026-03-25
**Repo:** `Trinity/remote-coding-agent`
**Branch:** `feat/cortex-bridge`
**Depends on:** Cortex Workflows 2.0 Phases 1-4 (merged to main)

## Goal

Add an Cortex Bridge module to the remote-coding-agent so it can:
1. Register itself with Cortex as an execution backend
2. Receive workflow dispatch payloads from Cortex
3. Execute YAML workflows using the existing DAG executor
4. Report node state changes, progress, and completion back to Cortex via REST callbacks
5. Handle approval gates (pause execution, send approval webhook, wait for resume signal)
6. Accept resume and cancel signals from Cortex

## Architecture Context

The remote-agent already has a fully-featured DAG executor (`packages/workflows/src/dag-executor.ts`) with topological sorting, parallel execution, conditional branching, retry logic, and session continuity. The bridge module wraps this executor with Cortex-specific dispatch/callback logic without modifying the core executor.

**Communication model:** REST only (no bidirectional SSE). Remote-agent calls Cortex's callback endpoints. Cortex calls remote-agent's dispatch/resume/cancel endpoints.

**Auth model:** Bearer token issued at registration, stored hashed in Cortex's `execution_backends` table.

## Tech Stack

- TypeScript / Bun
- Hono (existing server framework)
- Existing DAG executor (`packages/workflows/src/dag-executor.ts`)
- Existing workflow types (`packages/workflows/src/types.ts`)

## File Structure

```
packages/
├── cortex-bridge/
│   ├── src/
│   │   ├── index.ts                  # Package exports
│   │   ├── types.ts                  # Cortex protocol types
│   │   ├── registration.ts           # Backend registration with Cortex
│   │   ├── callback-client.ts        # HTTP client for Cortex callbacks
│   │   ├── dispatch-handler.ts       # Handles incoming dispatch payloads
│   │   ├── approval-gate.ts          # Approval gate pause/resume logic
│   │   └── bridge-config.ts          # Configuration (env vars, URLs)
│   ├── tests/
│   │   ├── callback-client.test.ts
│   │   ├── dispatch-handler.test.ts
│   │   └── approval-gate.test.ts
│   └── package.json
├── server/
│   └── src/
│       └── routes/
│           └── cortex-routes.ts      # New: Cortex-specific API routes
```

### Files to Modify

```
packages/server/src/routes/api.ts     # Register cortex routes
packages/server/src/index.ts          # Wire up bridge on startup
packages/workflows/src/dag-executor.ts  # Add approval gate hook support
```

---

## Task 1: Cortex Protocol Types

**File:** `packages/cortex-bridge/src/types.ts`

Define TypeScript interfaces matching Cortex's Python models:

```typescript
/** Payload Cortex sends to dispatch a workflow */
export interface DispatchPayload {
  workflow_run_id: string;
  yaml_content: string;
  trigger_context: Record<string, unknown>;
  node_id_map: Record<string, string>; // YAML node ID -> Cortex DB UUID
  callback_url: string;
}

/** Sent to Cortex when a node changes state */
export interface NodeStateCallback {
  state: 'running' | 'completed' | 'failed' | 'skipped' | 'waiting_approval';
  output?: string;
  error?: string;
  session_id?: string;
  duration_seconds?: number;
}

/** Sent to Cortex when a node emits progress */
export interface NodeProgressCallback {
  message: string;
}

/** Sent to Cortex when a node needs approval */
export interface ApprovalRequestCallback {
  workflow_run_id: string;
  workflow_node_id: string;  // Cortex DB UUID
  yaml_node_id: string;
  approval_type: string;     // plan_review, pr_review, deploy_gate, custom
  node_output: string;
  channels: string[];        // ['ui', 'telegram']
}

/** Sent to Cortex when the entire run completes */
export interface RunCompleteCallback {
  status: 'completed' | 'failed' | 'cancelled';
  summary?: string;
  node_outputs?: Record<string, string>;
}

/** Cortex sends this to resume after approval */
export interface ResumePayload {
  yaml_node_id: string;
  decision: 'approved' | 'rejected';
  comment?: string;
}

/** Cortex sends this to cancel a running workflow */
export interface CancelPayload {
  reason: string;
}

/** Bridge configuration */
export interface BridgeConfig {
  cortexUrl: string;
  backendName: string;
  backendId?: string;
  authToken?: string;
  projectId?: string;
  heartbeatIntervalMs: number;
}
```

---

## Task 2: Bridge Configuration

**File:** `packages/cortex-bridge/src/bridge-config.ts`

Read from environment variables:

| Env Var | Default | Description |
|---------|---------|-------------|
| `CORTEX_URL` | `http://localhost:8181` | Cortex API base URL |
| `CORTEX_BACKEND_NAME` | hostname | Name for registration |
| `CORTEX_BACKEND_ID` | (stored after registration) | Persisted backend ID |
| `CORTEX_AUTH_TOKEN` | (stored after registration) | Persisted auth token |
| `CORTEX_PROJECT_ID` | (none) | Optional project scope |
| `CORTEX_HEARTBEAT_INTERVAL` | `30000` | Heartbeat interval in ms |

Store `backend_id` and `auth_token` in a local file (`~/.cortex-bridge.json`) after first registration so restarts don't re-register.

---

## Task 3: Backend Registration

**File:** `packages/cortex-bridge/src/registration.ts`

On startup:
1. Check if `~/.cortex-bridge.json` exists with valid `backend_id` and `auth_token`
2. If yes, verify with a heartbeat (`POST /api/workflows/backends/{id}/heartbeat`)
3. If no or heartbeat fails, register:
   - `POST {cortexUrl}/api/workflows/backends/register`
   - Body: `{ name, base_url, project_id }`
   - Response: `{ backend_id, auth_token }`
   - Persist to `~/.cortex-bridge.json`
4. Start heartbeat interval timer

---

## Task 4: Callback Client

**File:** `packages/cortex-bridge/src/callback-client.ts`

HTTP client that sends state updates to Cortex. All calls use `Authorization: Bearer {auth_token}`.

Methods:
- `reportNodeState(cortexNodeId: string, state: NodeStateCallback): Promise<void>`
  - `POST {callbackUrl}/nodes/{cortexNodeId}/state`
- `reportNodeProgress(cortexNodeId: string, message: string): Promise<void>`
  - `POST {callbackUrl}/nodes/{cortexNodeId}/progress`
- `requestApproval(data: ApprovalRequestCallback): Promise<void>`
  - `POST {callbackUrl}/approvals/request`
- `reportRunComplete(runId: string, data: RunCompleteCallback): Promise<void>`
  - `POST {callbackUrl}/runs/{runId}/complete`

Error handling:
- Retry with exponential backoff (3 attempts, 1s/2s/4s)
- Log failures but don't crash the workflow — Cortex state becomes eventually consistent
- Queue callbacks if Cortex is temporarily unreachable

---

## Task 5: Approval Gate Logic

**File:** `packages/cortex-bridge/src/approval-gate.ts`

When the DAG executor encounters a node with `approval.required: true`:

1. Execute the node normally (get output)
2. Report node state as `waiting_approval` to Cortex
3. Send `ApprovalRequestCallback` to Cortex with node output
4. Create a `Promise` that resolves when resume signal arrives
5. Store the promise resolver in a `Map<string, { resolve, reject }>` keyed by `yaml_node_id`
6. When resume signal arrives (`POST /api/cortex/workflows/{runId}/resume`):
   - Look up the resolver by `yaml_node_id`
   - If `decision === 'approved'`, resolve the promise (node continues as `completed`)
   - If `decision === 'rejected'`, reject the promise (node transitions to `failed`)
7. Timeout: configurable TTL (default 24 hours), auto-reject if no response

```typescript
class ApprovalGateManager {
  private pendingApprovals: Map<string, {
    resolve: (decision: string) => void;
    reject: (reason: string) => void;
    timeout: Timer;
  }>;

  async waitForApproval(yamlNodeId: string, ttlMs?: number): Promise<string>;
  resolveApproval(yamlNodeId: string, decision: string, comment?: string): void;
  cancelAll(reason: string): void;
}
```

---

## Task 6: Dispatch Handler

**File:** `packages/cortex-bridge/src/dispatch-handler.ts`

Handles incoming `POST /api/cortex/workflows/execute`:

1. Parse `DispatchPayload`
2. Load YAML content via the existing workflow loader (`packages/workflows/src/loader.ts`)
3. Create `WorkflowNodeHooks` that map to the callback client:
   - `onNodeStart(nodeId)` -> `reportNodeState(cortexId, { state: 'running' })`
   - `onNodeComplete(nodeId, output)` -> `reportNodeState(cortexId, { state: 'completed', output })`
   - `onNodeFailed(nodeId, error)` -> `reportNodeState(cortexId, { state: 'failed', error })`
   - `onNodeSkipped(nodeId)` -> `reportNodeState(cortexId, { state: 'skipped' })`
   - `onNodeProgress(nodeId, message)` -> `reportNodeProgress(cortexId, message)`
4. For nodes with `approval.required: true`, inject approval gate hook:
   - After node execution, call `approvalGateManager.waitForApproval(yamlNodeId)`
   - Map approval type from YAML `approval.type` field
5. Execute via `DagExecutor.execute(workflow, hooks)`
6. On completion, call `reportRunComplete(runId, { status, summary, node_outputs })`
7. Track active runs in a `Map<string, { executor, approvalManager }>` for cancel support

---

## Task 7: Cortex API Routes

**File:** `packages/server/src/routes/cortex-routes.ts`

New Hono routes under `/api/cortex/`:

```typescript
// Receive workflow dispatch from Cortex
POST /api/cortex/workflows/execute
  -> dispatchHandler.handleDispatch(payload)
  -> Returns { accepted: true, run_id }

// Resume a paused node after approval
POST /api/cortex/workflows/:runId/resume
  -> approvalGateManager.resolveApproval(yamlNodeId, decision, comment)
  -> Returns { resumed: true }

// Cancel a running workflow
POST /api/cortex/workflows/:runId/cancel
  -> activeRuns.get(runId).executor.cancel(reason)
  -> activeRuns.get(runId).approvalManager.cancelAll(reason)
  -> Returns { cancelled: true }

// Health check for Cortex to verify connectivity
GET /api/cortex/health
  -> Returns { status: 'ok', backend_id, active_runs: count }
```

### Modify existing files

**`packages/server/src/routes/api.ts`:**
- Import and mount cortex routes: `app.route('/api/cortex', cortexRoutes)`

**`packages/server/src/index.ts`:**
- On startup, initialize the bridge (registration + heartbeat)
- Only if `CORTEX_URL` is set (opt-in, doesn't break existing standalone usage)

---

## Task 8: DAG Executor Approval Hook

**File to modify:** `packages/workflows/src/dag-executor.ts`

The DAG executor already supports `WorkflowNodeHooks`. Add a new hook type:

```typescript
interface WorkflowNodeHooks {
  // ... existing hooks
  onApprovalRequired?: (nodeId: string, output: string, approvalConfig: ApprovalConfig) => Promise<string>;
  // Returns 'approved' or 'rejected'
}
```

In the executor's node execution loop, after a node completes:
1. Check if the node has `approval.required: true` in its config
2. If yes, call `hooks.onApprovalRequired(nodeId, output, config)`
3. If approved, continue; if rejected, mark node as failed

This keeps the executor generic — the Cortex-specific logic lives entirely in the bridge module's hook implementation.

---

## Task 9: Tests

Write tests for:
- `callback-client.test.ts` — mock HTTP, verify correct endpoints/payloads, retry behavior
- `dispatch-handler.test.ts` — mock DAG executor, verify hooks are wired correctly, verify run tracking
- `approval-gate.test.ts` — test approval/rejection flow, timeout auto-reject, cancel-all

---

## Task 10: Integration Verification

1. Start Cortex (`docker compose up -d` in cortex repo)
2. Start remote-agent with `CORTEX_URL=http://localhost:8181`
3. Verify registration: `GET /api/workflows/backends` shows the remote-agent
4. Create a workflow definition via Cortex UI
5. Dispatch a run — verify node states appear in Cortex's SSE stream
6. Test approval gate: create a workflow with `approval.required: true`, verify it pauses, approve via Cortex UI, verify it resumes

---

## Propagation

| What Changed | How to Propagate |
|---|---|
| New `cortex-bridge` package | `bun install` in remote-agent root |
| New routes in server | Restart remote-agent |
| DAG executor hook changes | Restart remote-agent |
| Environment variables | Set `CORTEX_URL` to enable bridge |

## Dependencies

- Cortex must be running with Workflows 2.0 (Phases 1-4 merged)
- Network connectivity between remote-agent and Cortex
- No new external package dependencies (uses Bun's built-in `fetch` for HTTP)
