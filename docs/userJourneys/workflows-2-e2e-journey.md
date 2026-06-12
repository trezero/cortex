# Workflows 2.0 End-to-End Journey — Automated Multi-Repo Development

## User Persona

**Riley** is a platform engineer managing the Trinity ecosystem — three interconnected repos:

| Repo | Purpose | Tech Stack |
|------|---------|-----------|
| **Cortex** | Control plane — workflow management, HITL approvals, pattern discovery | Python/FastAPI, React, Supabase |
| **Remote-Agent** | Execution engine — runs YAML workflows via DAG executor | TypeScript/Bun, Hono |
| **Second Brain** | Generative UI — A2UI component generation for rich approvals | Python/FastAPI, React, PydanticAI |

Riley works from a single machine (**WIN-AI-PC**, WSL2 Ubuntu) with all three repos cloned under `~/projects/Trinity/`.

---

## Journey Overview

This journey walks through the complete Workflows 2.0 lifecycle: defining a workflow, dispatching it to a remote agent, watching it execute in real-time, reviewing an approval gate with rich A2UI rendering, and discovering automation patterns from historical activity.

| Phase | Focus |
|-------|-------|
| Phase 1 | Infrastructure — Start services, verify connectivity |
| Phase 2 | Define & Dispatch — Create a workflow, trigger execution |
| Phase 3 | Live Monitoring — Watch execution via SSE, inspect node states |
| Phase 4 | HITL Approval — Review approval gate, approve/reject |
| Phase 5 | Pattern Discovery — Backfill history, discover automation patterns |
| Phase 6 | Workflow Editor — Create workflows visually, manage commands |

---

## Prerequisites

- All three Trinity repos cloned under `~/projects/Trinity/`
- Docker and Docker Compose installed
- Local Supabase running (with pgvector extension)
- Database migrations 027-034 applied
- Node.js 18+ and Bun installed (for remote-agent)
- `OPENROUTER_API_KEY` set in environment (for A2UI generation)
- `ANTHROPIC_API_KEY` set in environment (for pattern discovery normalization)

---

## Phase 1 — Infrastructure: Start Services and Verify Connectivity

### 1.1 Start Cortex (Control Plane)

```bash
cd ~/projects/Trinity/cortex
docker compose --profile trinity up --build -d
```

**Expected:** Four Cortex containers start + one Second Brain container:

| Container | Port | Purpose |
|-----------|------|---------|
| `cortex-server` | 8181 | Backend API |
| `cortex-mcp` | 8051 | MCP server for IDE integration |
| `cortex-ui` | 3737 | Frontend UI |
| `cortex-agents` | 8052 | AI agents |
| `trinity-a2ui` | 8054 | Second Brain A2UI generation service |

Verify:
```bash
curl http://localhost:8181/health
```
**Expected:** `{"status":"healthy","service":"cortex-backend",...,"ready":true}`

### 1.2 Verify A2UI Service

```bash
curl http://localhost:8054/health
```
**Expected:** `{"status":"ok","service":"trinity-a2ui"}`

### 1.3 Start Remote-Agent

```bash
cd ~/projects/Trinity/remote-coding-agent
CORTEX_URL=http://localhost:8181 bun run start
```

**Expected:** The remote-agent starts and auto-registers with Cortex:
```
[cortex-bridge] Registering with Cortex at http://localhost:8181...
[cortex-bridge] Registered as backend be_abc123
[cortex-bridge] Heartbeat started (30s interval)
```

### 1.4 Verify Backend Registration

```bash
curl http://localhost:8181/api/workflows/backends
```

**Expected:** Array with one entry showing the remote-agent:
```json
[{
  "id": "be_abc123",
  "name": "WIN-AI-PC",
  "base_url": "http://localhost:3000",
  "status": "healthy",
  "last_heartbeat_at": "2026-03-25T..."
}]
```

### 1.5 Open Cortex UI

Navigate to `http://localhost:3737/workflows` in a browser.

**Expected:**
- Workflows page with 5 tabs: Runs, Definitions, Approvals, Commands, Suggestions
- Runs tab shows "No workflow runs found"
- Layers icon highlighted in sidebar navigation

---

## Phase 2 — Define & Dispatch: Create a Workflow

### 2.1 Create a Workflow Definition via UI

1. Click the **Definitions** tab
2. Click **New Workflow** button
3. The split-pane editor opens with:
   - Left: Metadata form (name, description, tags) + node list
   - Right: Live YAML preview

### 2.2 Build the Workflow

Fill in the metadata:
- **Name:** `feature-implementation`
- **Description:** `Automated feature implementation with plan review and testing`
- **Tags:** `dev, automation`

Add three nodes using the **Add Node** button:

| Node ID | Command | Approval | Depends On |
|---------|---------|----------|------------|
| `plan` | `architect` | No | (none) |
| `review-plan` | `review` | Yes (`plan_review`) | `plan` |
| `implement` | `code` | No | `review-plan` |

**Expected:** The YAML panel on the right updates in real-time:
```yaml
name: feature-implementation
description: Automated feature implementation with plan review and testing
nodes:
  - id: plan
    command: architect
    prompt: Create an implementation plan
    depends_on: []
  - id: review-plan
    command: review
    prompt: Review the plan for completeness
    depends_on:
      - plan
    approval:
      required: true
      type: plan_review
  - id: implement
    command: code
    prompt: Implement the approved plan
    depends_on:
      - review-plan
```

### 2.3 Save the Definition

Click **Save**.

**Expected:**
- Success — definition appears in the Definitions tab list
- Shows name, description, tags (`dev`, `automation`), version `v1`

### 2.4 Dispatch a Workflow Run

```bash
curl -X POST http://localhost:8181/api/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "definition_id": "<definition_id_from_step_2.3>",
    "trigger_context": { "feature": "user-authentication", "repo": "my-project" }
  }'
```

**Expected:**
```json
{
  "run_id": "wr_xyz789",
  "status": "dispatched"
}
```

The dispatch service:
1. Creates `workflow_runs` record with status `dispatched`
2. Creates `workflow_nodes` records for each node (all `pending`)
3. Selects the registered remote-agent backend
4. POSTs `DispatchPayload` to `http://localhost:3000/api/cortex/workflows/execute`

---

## Phase 3 — Live Monitoring: Watch Execution via SSE

### 3.1 Open the Run Viewer

1. Click the **Runs** tab in the Workflows page
2. The new run appears as a `WorkflowRunCard` with status `dispatched` (blue badge)
3. Click the run card to open `WorkflowRunView`

**Expected:** The run detail view shows:
- Header: run status, definition name, start time
- SSE connection indicator (green dot = connected)
- Node list with state indicators:
  - `plan` — `pending` (gray dot)
  - `review-plan` — `pending` (gray dot)
  - `implement` — `pending` (gray dot)

### 3.2 Watch Node States Update

As the remote-agent executes, SSE events stream to the browser:

**First event — `plan` starts:**
- `plan` node dot changes to cyan with pulse animation (`running`)
- Progress messages appear in the live feed: "Analyzing codebase...", "Generating plan..."

**Second event — `plan` completes:**
- `plan` node dot changes to green (`completed`)
- Output preview shows the generated plan text
- Duration shows (e.g., "45s")

**Third event — `review-plan` reaches approval gate:**
- `review-plan` node dot changes to amber with pulse animation (`waiting_approval`)
- An "Approval Required" badge appears next to the node
- The Approvals tab count badge increments

### 3.3 Verify SSE Events

Open browser DevTools → Network → filter by EventStream. You should see:
```
event: node_state_changed
data: {"node_id": "...", "state": "running", "yaml_node_id": "plan"}

event: node_progress
data: {"node_id": "...", "message": "Analyzing codebase..."}

event: node_state_changed
data: {"node_id": "...", "state": "completed", "yaml_node_id": "plan", "output": "..."}

event: approval_requested
data: {"approval_id": "apr_...", "node_id": "...", "yaml_node_id": "review-plan", "approval_type": "plan_review"}
```

---

## Phase 4 — HITL Approval: Review and Decide

### 4.1 View the Approval

1. Click the **Approvals** tab (or click the "Review" button in the run view)
2. The `ApprovalList` shows one pending approval:
   - Node: `review-plan`
   - Type: `plan_review`
   - Status: amber `pending` badge
   - Created timestamp
3. Click the approval to open `ApprovalDetail`

### 4.2 Review A2UI Components

**Expected:** The approval detail renders the plan output as rich A2UI components:

| Component | Content |
|-----------|---------|
| `ExecutiveSummary` | Plan title and summary (hero zone) |
| `StepCard` x N | Numbered implementation steps (content zone) |
| `StatCard` | Files to modify, complexity estimate (sidebar zone) |
| `CodeBlock` | Relevant code snippets (content zone) |

These components are generated by the **deterministic template** (`approval_templates.py`) — no LLM call was needed because `plan_review` is a standard type.

If the approval type were `custom`, the A2UI service at `trinity-a2ui:8054` would generate the components via LLM instead.

### 4.3 Approve the Plan

At the bottom of the detail view, `ApprovalActions` shows:
- **Approve** button (cyan)
- **Reject** button (red)
- Optional comment textarea

1. Type a comment: "Looks good, proceed with implementation"
2. Click **Approve**

**Expected:**
1. The approval status changes to `approved` (green badge)
2. Cortex sends a resume signal to the remote-agent:
   ```
   POST http://localhost:3000/api/cortex/workflows/{runId}/resume
   Body: { "yaml_node_id": "review-plan", "decision": "approved", "comment": "Looks good..." }
   ```
3. The remote-agent's `ApprovalGateManager` resolves the pending promise
4. The `review-plan` node transitions to `completed` (green dot in run view)
5. The `implement` node starts (`running`, cyan pulse)
6. HITL router notifies channels:
   - UI channel: SSE event `approval_resolved`
   - Telegram channel: sends resolution message (if configured)

### 4.4 Watch Implementation Complete

After approval, the `implement` node executes:
- Progress messages stream in
- When complete, all nodes show green dots
- Run status changes to `completed` (green badge)
- `run_status_changed` SSE event fires

### 4.5 Test Rejection Flow (Optional)

Create another run of the same workflow. When the approval gate fires:
1. Click **Reject** with comment: "Plan needs more detail on error handling"
2. **Expected:**
   - `review-plan` transitions to `failed` (red dot)
   - `implement` transitions to `skipped` (gray dot) — dependency failed
   - Run status: `failed`
   - Remote-agent's approval gate promise rejects

---

## Phase 5 — Pattern Discovery: Mine Historical Activity

### 5.1 Backfill Historical Data

Trigger backfill to ingest git history from registered projects:

```bash
curl -X POST http://localhost:8181/api/patterns/backfill?lookback_days=90
```

**Expected:**
```json
{
  "total_captured": 342,
  "normalized": 200,
  "projects": [
    { "project_id": "...", "title": "My Project", "status": "captured", "captured": 342 }
  ]
}
```

The pipeline:
1. `CaptureService` reads `git log` from project repos, inserts `activity_events`
2. `NormalizationService` calls Haiku to extract `(action_verb, target_object, trigger_context)` tuples
3. Generates OpenAI embeddings for each normalized event

### 5.2 Run the Discovery Pipeline

```bash
curl -X POST http://localhost:8181/api/patterns/run-pipeline
```

**Expected:**
```json
{
  "captured": 0,
  "normalized": 0,
  "sequence_patterns": 5,
  "clusters": 3,
  "scored_patterns": 4,
  "stored_patterns": 4
}
```

The pipeline:
1. `SequenceMiningService` runs PrefixSpan on `(verb, object)` tuples grouped by repo/week
2. `ClusteringService` groups events by intent similarity
3. `ScoringService` computes `final_score = frequency(0.4) + cross_repo(0.35) + automation_potential(0.25)`
4. `GenerationService` sends high-scoring patterns to Sonnet to produce YAML workflow suggestions
5. `SuggestionService` stores results in `discovered_patterns` table

### 5.3 View Suggestions in UI

1. Click the **Suggestions** tab in the Workflows page
2. `SuggestedWorkflows` dashboard shows discovered patterns sorted by score

**Expected:** Each card shows:
- Pattern name and description
- Score bar (gradient from red to green)
- Repos involved (pill badges)
- Pattern type badge (sequence or cluster)
- Collapsible YAML preview of the suggested workflow

### 5.4 Accept a Suggestion

Click **Accept** on a suggestion card.

**Expected:**
1. A new `workflow_definitions` row is created with `origin: pattern_discovery`
2. The suggestion status changes to `accepted`
3. The new definition appears in the Definitions tab
4. It's ready to dispatch like any manually-created workflow

### 5.5 Dismiss a Suggestion

Click **Dismiss** on another card, add reason: "Too specific to one repo"

**Expected:**
1. Suggestion status changes to `dismissed`
2. `final_score` decays by 0.5x (needs stronger signal to resurface)
3. Card disappears from the pending list

---

## Phase 6 — Workflow Editor: Visual Authoring and Command Library

### 6.1 Edit an Existing Definition

1. Click the **Definitions** tab
2. Click the `feature-implementation` definition
3. The split-pane editor opens pre-populated

### 6.2 Add a New Node

1. Click **Add Node** in the left panel
2. Fill in:
   - **ID:** `run-tests`
   - **Command:** `test`
   - **Prompt:** `Run the test suite and report results`
   - **Depends on:** select `implement` from the dropdown
   - **Approval required:** check, type: `deploy_gate`
3. The YAML panel updates instantly with the new node

### 6.3 Edit YAML Directly

1. Click the **Edit** toggle on the YAML panel (switches from read-only to editable)
2. Modify the YAML directly — e.g., change a prompt or add a `when:` condition
3. The form panel updates bidirectionally
4. If YAML has a syntax error, an inline error message appears below the editor

### 6.4 Manage Commands

1. Click the **Commands** tab
2. The `CommandEditor` shows:
   - Left: Command library list with count
   - Right: Editor panel ("Select a command or create a new one")

3. Click **+ New**
4. Fill in:
   - **Name:** `deploy-staging`
   - **Description:** `Deploy to staging environment`
   - **Prompt template:**
     ```
     Deploy $ARGUMENTS to the staging environment.

     Steps:
     1. Run pre-deploy checks
     2. Build the application
     3. Deploy to staging
     4. Run smoke tests
     ```
5. The preview panel highlights `$ARGUMENTS` as a variable placeholder
6. Click **Save**

**Expected:** The command appears in the library list and can be referenced by workflow nodes.

---

## Verification Checklist

### Infrastructure
- [ ] Cortex backend returns healthy at `localhost:8181/health`
- [ ] A2UI service returns healthy at `localhost:8054/health`
- [ ] Remote-agent registered in Cortex backends list
- [ ] Heartbeat keeping backend status `healthy`

### Workflow Lifecycle
- [ ] Definition created via split-pane editor
- [ ] YAML preview updates bidirectionally
- [ ] Run dispatched to remote-agent
- [ ] SSE events stream to browser (node states, progress, approvals)
- [ ] Node state indicators update live (gray → cyan → green)
- [ ] Approval gate pauses execution at correct node

### HITL Approvals
- [ ] Approval appears in Approvals tab with `pending` badge
- [ ] A2UI components render (ExecutiveSummary, StepCard, StatCard, CodeBlock)
- [ ] Approve resumes workflow — downstream nodes execute
- [ ] Reject fails the node — dependent nodes skip
- [ ] Comment is stored in resolution record
- [ ] Telegram notification sent (if configured)

### Pattern Discovery
- [ ] Backfill captures git history from registered projects
- [ ] Normalization extracts intent tuples via Haiku
- [ ] PrefixSpan finds repeated sequences across repos
- [ ] Suggestions appear in dashboard sorted by score
- [ ] Accept creates a workflow definition with `origin: pattern_discovery`
- [ ] Dismiss decays score and hides from pending list

### Workflow Editor
- [ ] Split-pane layout renders (form + YAML)
- [ ] Nodes added/removed, dependencies updated
- [ ] YAML edits propagate to form and vice versa
- [ ] Parse errors shown inline
- [ ] Commands created with variable highlighting
- [ ] Definitions saved and listed

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Remote-agent not in backends list | `CORTEX_URL` not set | Start remote-agent with `CORTEX_URL=http://localhost:8181` |
| Backend status `unhealthy` | Heartbeat failing | Check network between remote-agent and Cortex |
| SSE not streaming | Wrong API path | Verify `GET /api/workflows/{runId}/events` returns `text/event-stream` |
| A2UI renders raw JSON | `trinity-a2ui` not running | `docker compose --profile trinity up -d` |
| Approval gate hangs | Resume signal not reaching remote-agent | Check remote-agent logs for incoming POST at `/api/cortex/workflows/{runId}/resume` |
| Pattern discovery empty | No projects with local repos | Ensure `cortex_projects` have `github_repo` pointing to local paths |
| YAML parse error in editor | Invalid YAML syntax | Check for tab characters (use spaces) or unclosed quotes |
| Definitions endpoint 500 | Router ordering | Ensure `workflow_definition_router` is registered before `workflow_router` in `main.py` |
