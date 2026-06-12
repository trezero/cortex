# Agent Work Orders — End-to-End User Journey

## User Persona

**Alex** is a developer who manages multiple GitHub repositories and wants to use Cortex's
Agent Work Orders feature to automate development workflows — creating branches, writing
implementation plans, executing code changes, and opening pull requests — all driven by
Claude Code CLI running inside an isolated sandbox.

Alex works on a single machine (**WIN-AI-PC** running WSL2) with Cortex deployed locally.

---

## Journey Overview

This journey tests every layer of the Agent Work Orders feature across four phases:

| Phase | Focus |
|-------|-------|
| Phase 1 | Infrastructure — Docker, health checks, service connectivity |
| Phase 2 | Repository management — CRUD, GitHub verification, defaults |
| Phase 3 | Work order execution — creation, sandbox, workflow steps, logs, SSE |
| Phase 4 | Edge cases — invalid inputs, concurrent orders, failure recovery, cleanup |

---

## Prerequisites

- Cortex stack running: `docker compose up -d` (server, MCP, frontend)
- Agent Work Orders service running: `docker compose --profile work-orders up -d`
  or `COMPOSE_PROFILES=work-orders` set in `.env` (recommended)
- Environment variables configured in `.env`:
  - `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` — Supabase connection
  - `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` — Claude CLI auth
  - `GH_TOKEN` (mapped from `GITHUB_PAT_TOKEN`) — GitHub CLI auth
- A **test GitHub repository** you own (e.g., `https://github.com/youruser/test-repo`)
  with at least one commit on `main`. The repo should be expendable — work orders will
  create branches, commits, and PRs against it.
- Agent Work Orders feature enabled in Cortex UI (Settings > Features)
- Browser open to `http://localhost:3737`

---

## Phase 1 — Infrastructure and Service Health

### 1.1 Verify Container is Running

```bash
docker compose ps cortex-agent-work-orders
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Container status | `Up` with `(healthy)` | | |
| Port mapping | `0.0.0.0:8053->8053/tcp` | | |

### 1.2 Health Check — Direct

```bash
curl -s http://localhost:8053/health | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| `status` | `"healthy"` | | |
| `dependencies.claude_cli.available` | `true` | | |
| `dependencies.claude_cli.version` | Non-empty version string | | |
| `dependencies.git.available` | `true` | | |
| `dependencies.github_cli.authenticated` | `true` | | |
| `dependencies.supabase.connected` | `true` | | |
| `dependencies.cortex_server.reachable` | `true` | | |
| `dependencies.cortex_mcp.reachable` | `true` | | |

### 1.3 Health Check — Via Main Server Proxy

```bash
curl -s http://localhost:8181/api/agent-work-orders/health | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Response is identical to 1.2 | Same JSON structure and values | | |
| Proxy is transparent | No extra wrapping or modification | | |

### 1.4 Health Check — Degraded Mode

Temporarily set an invalid `ANTHROPIC_API_KEY` or stop the MCP container to verify
degraded reporting.

```bash
docker compose stop cortex-mcp
curl -s http://localhost:8053/health | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| `status` | `"degraded"` | | |
| `dependencies.cortex_mcp.reachable` | `false` | | |
| Service stays running | Container does not crash | | |

**Cleanup:** `docker compose start cortex-mcp` — wait for it to become healthy.

### 1.5 Feature Toggle in UI

1. Open `http://localhost:3737` in a browser
2. Navigate to **Settings** (gear icon in sidebar)
3. Find the **Agent Work Orders** toggle under Features

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Toggle is visible | Agent Work Orders toggle exists | | |
| Toggle ON | "Agent Work Orders" appears in the left sidebar nav | | |
| Toggle OFF | "Agent Work Orders" disappears from sidebar; navigating to `/agent-work-orders` redirects to `/` | | |

**Leave the toggle ON** for the rest of the journey.

### 1.6 Navigate to Agent Work Orders Page

1. Click **Agent Work Orders** in the left sidebar

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Page loads without errors | No blank screen or console errors | | |
| Empty state shown | Message indicating no repositories configured or no work orders | | |
| Layout toggle visible | Horizontal/Sidebar layout toggle in the UI | | |

---

## Phase 2 — Repository Management

### 2.1 Add a Repository via UI

1. Click the **Add Repository** button (or "+" icon)
2. In the modal, enter your test repo URL: `https://github.com/youruser/test-repo`
3. Submit

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Modal appears | Clean form with URL input | | |
| Verification runs | Spinner/loading indicator while GitHub is checked | | |
| Repository appears in list | Shows `youruser/test-repo` with a green verified badge | | |
| Metadata populated | `owner`, `default_branch` (e.g., `main`), `display_name` visible | | |
| Default commands set | `create-branch`, `planning`, `execute` (or configured defaults) | | |
| Toast notification | Success message shown | | |

### 2.2 Add Repository — API Verification

```bash
curl -s http://localhost:8053/api/agent-work-orders/repositories | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Repository appears in list | JSON array with at least one entry | | |
| `is_verified` | `true` | | |
| `last_verified_at` | Recent timestamp | | |
| `default_branch` | `"main"` or `"master"` | | |
| `repository_url` | Exact URL entered | | |

Record the repository `id` (UUID) for later tests: `______________`

### 2.3 Edit Repository Defaults

1. Click the **Edit** button (pencil icon) on the repository card
2. Change `default_sandbox_type` to `git_worktree` (if not already)
3. Toggle some default commands (e.g., add `commit` and `create-pr`)
4. Save

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Edit modal pre-populated | Current values shown | | |
| Metadata fields read-only | URL, owner, branch are not editable | | |
| Save succeeds | Toast notification, modal closes | | |
| Changes persisted | Reopening edit modal shows updated values | | |

### 2.4 Re-verify Repository

1. Find the **Verify** action on the repository card (or use API)

```bash
curl -s -X POST http://localhost:8053/api/agent-work-orders/repositories/{id}/verify | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| `is_verified` | `true` | | |
| `last_verified_at` | Updated to current time | | |

### 2.5 Add Invalid Repository

1. Click **Add Repository**
2. Enter an invalid URL: `https://github.com/nonexistent/does-not-exist-12345`
3. Submit

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Verification fails | Error message displayed (not a crash) | | |
| Repository NOT added | Does not appear in the list | | |
| Error is descriptive | Mentions repository not found or access denied | | |

### 2.6 Add Duplicate Repository

1. Try adding the same test repo URL again

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Duplicate rejected | Error message about repository already configured | | |
| No duplicate in list | Only one entry for this URL | | |

### 2.7 Verify Repository in Database

```bash
# Query Supabase directly if accessible, or use the API
curl -s http://localhost:8053/api/agent-work-orders/repositories | python3 -m json.tool | head -30
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Data persisted to `cortex_configured_repositories` | Repository data matches what UI shows | | |

---

## Phase 3 — Work Order Execution

### 3.1 Create a Work Order via UI — Planning Only

Start with a lightweight test that only runs `create-branch` and `planning` steps.

1. Click **Create Work Order** button
2. Fill in the form:
   - **Repository**: Select your test repo
   - **Work Request**: `Add a README.md file with a project description and setup instructions`
   - **GitHub Issue**: (leave empty)
   - **Sandbox Type**: `git_worktree`
   - **Workflow Steps**: Check only `create-branch` and `planning`
     (uncheck `execute`, `commit`, `create-pr`)
3. Submit

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Modal accepts input | All fields editable, repository dropdown populated | | |
| Workflow step cascading | Unchecking `execute` auto-unchecks `commit` and `create-pr` | | |
| Submission succeeds | Modal closes, new work order appears in table | | |
| Initial status | `pending` shown in the table row | | |
| Status transitions to `running` | Within a few seconds, status changes to `running` | | |
| Row has live indicator | Glowing cyan indicator for running status | | |

Record the work order ID (e.g., `wo-a3c2f1e4`): `______________`

### 3.2 Observe Real-Time Execution

1. Click on the work order row or the **Details** button to open the detail view

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Detail page loads | Shows work order metadata, progress bar, log panel | | |
| Breadcrumb navigation | Shows path back to work orders list | | |
| Progress bar | Shows workflow steps as nodes connected by lines | | |
| `create-branch` step highlights | Shows as active/in-progress during execution | | |

### 3.3 SSE Live Log Streaming

While the work order is running, observe the log panel:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Logs appear in real-time | New log entries stream in without page refresh | | |
| Log entries have timestamps | Relative timestamps shown | | |
| Log entries have levels | `info`, `debug`, etc. with colored badges | | |
| Level filter works | Selecting "error" filters to only error logs | | |
| Auto-scroll active | Log panel scrolls to bottom as new entries arrive | | |
| Auto-scroll toggle | Can disable auto-scroll; scrolling up pauses it | | |
| Live indicator shown | "Live" badge or indicator visible | | |

### 3.4 SSE API Verification

In a separate terminal, connect to the SSE stream directly:

```bash
curl -N http://localhost:8053/api/agent-work-orders/{work_order_id}/logs/stream
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| SSE events stream | Lines prefixed with `data:` containing JSON | | |
| Heartbeat comments | `: heartbeat` comments appear every ~15 seconds | | |
| Events contain `work_order_id` | Each event has the correct work order ID | | |
| Events have `level`, `event`, `timestamp` | Structured log fields present | | |

Press `Ctrl+C` to stop.

### 3.5 Work Order Completion (Planning Only)

Wait for the work order to finish (typically 1-3 minutes for planning-only).

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Status changes to `completed` | Green indicator in table and detail view | | |
| Progress bar shows all steps done | Both `create-branch` and `planning` nodes marked complete | | |
| Step history populated | Cards for each step showing agent name, duration, output | | |
| `create-branch` step output | Shows the branch name created (e.g., `wo-sandbox-wo-...`) | | |
| `planning` step output | Shows the PRP file path created | | |
| No error messages | `error_message` is null | | |

### 3.6 Step History API

```bash
curl -s http://localhost:8053/api/agent-work-orders/{work_order_id}/steps | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Two step entries | `create-branch` and `planning` | | |
| `step_order` | 0 and 1 respectively | | |
| `success` | `true` for both | | |
| `agent_name` | `BranchCreator` and `Planner` | | |
| `duration_seconds` | Non-zero positive numbers | | |
| `session_id` | Non-null Claude CLI session IDs | | |
| `output` | Branch name and PRP file path | | |

### 3.7 Buffered Logs API

```bash
curl -s "http://localhost:8053/api/agent-work-orders/{work_order_id}/logs?limit=20&offset=0" \
  | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| `log_entries` array returned | Non-empty array | | |
| Entries have expected fields | `timestamp`, `level`, `event`, `work_order_id` | | |
| `total_count` | Total number of log entries | | |
| Pagination works | Changing `offset` returns different entries | | |
| Level filter works | Adding `&level=error` filters results | | |

### 3.8 Git Progress API

```bash
curl -s http://localhost:8053/api/agent-work-orders/{work_order_id}/git-progress | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Response returned | JSON with git stats | | |
| `commit_count` | 0 (no commits in planning-only run) | | |

### 3.9 Verify Sandbox Cleanup

After completion, verify the worktree was cleaned up:

```bash
ls /tmp/agent-work-orders/
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Worktree directory removed | No directory for the completed work order's sandbox | | |
| Base repo clone may persist | `repos/<hash>/main/` may still exist (shared across orders) | | |

---

## Phase 3B — Full Workflow Execution (All Steps)

### 3.10 Create a Full Work Order

1. Click **Create Work Order**
2. Fill in:
   - **Repository**: Select your test repo
   - **Work Request**: `Create a CONTRIBUTING.md file that explains how to fork the repo, create a branch, make changes, and submit a pull request. Include a code of conduct section.`
   - **GitHub Issue**: (leave empty)
   - **Sandbox Type**: `git_worktree`
   - **Workflow Steps**: Check ALL steps: `create-branch`, `planning`, `execute`, `commit`, `create-pr`
3. Submit

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| All 5 steps selected | UI shows all checkboxes checked | | |
| Order created | New row in table with `pending` status | | |

Record work order ID: `______________`

### 3.11 Monitor Full Execution

This will take longer (5-15 minutes depending on complexity). Monitor via the detail view.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| `create-branch` completes | Branch created, step marked success | | |
| `planning` completes | PRP document written, step marked success | | |
| `execute` completes | Code changes implemented, step marked success | | |
| `commit` completes | Changes committed and pushed, step marked success | | |
| `create-pr` completes | Pull request created on GitHub, step marked success | | |
| Final status | `completed` | | |
| PR URL in metadata | `github_pull_request_url` populated | | |

### 3.12 Verify the Pull Request on GitHub

1. Copy the PR URL from the work order detail view or API response
2. Open in browser

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| PR exists on GitHub | Page loads with PR details | | |
| PR title is relevant | Relates to the work request (CONTRIBUTING.md) | | |
| PR description present | Contains meaningful description of changes | | |
| PR branch correct | Branch name matches the one from `create-branch` step | | |
| PR has commits | At least one commit with relevant changes | | |
| Files changed | CONTRIBUTING.md (and possibly other files) | | |

### 3.13 Work Order in Database

```bash
curl -s http://localhost:8053/api/agent-work-orders/{work_order_id} | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| `status` | `"completed"` | | |
| `git_branch_name` | Non-null branch name | | |
| `github_pull_request_url` | Valid GitHub PR URL | | |
| `sandbox_type` | `"git_worktree"` | | |
| `created_at` / `updated_at` | Valid timestamps, `updated_at` > `created_at` | | |

---

## Phase 3C — Work Order with GitHub Issue

### 3.14 Create a GitHub Issue on the Test Repo

Create a test issue manually on GitHub (or via `gh`):

```bash
gh issue create --repo youruser/test-repo \
  --title "Add LICENSE file" \
  --body "We need a LICENSE file. Use MIT license. Include the current year and repo owner name."
```

Record the issue number: `#______________`

### 3.15 Create Work Order Referencing the Issue

1. Click **Create Work Order**
2. Fill in:
   - **Repository**: Your test repo
   - **Work Request**: `Resolve the issue described in the linked GitHub issue`
   - **GitHub Issue**: Enter the issue number from 3.14
   - **Steps**: `create-branch`, `planning`, `execute`, `commit`, `create-pr`
3. Submit

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Issue number accepted | No validation error | | |
| Order starts | Status transitions to running | | |
| Planning step references issue | The PRP/plan mentions the GitHub issue content | | |
| PR references issue | PR description or commits reference the issue | | |
| Completed successfully | Status = `completed` | | |

---

## Phase 4 — Edge Cases and Error Handling

### 4.1 Create Work Order — Invalid Repository URL

```bash
curl -s -X POST http://localhost:8053/api/agent-work-orders/ \
  -H "Content-Type: application/json" \
  -d '{
    "repository_url": "https://github.com/nonexistent/fake-repo-12345",
    "user_request": "Add a README",
    "selected_commands": ["create-branch", "planning"]
  }' | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Work order created | Returns 201 with `pending` status (validation is async) | | |
| Fails during execution | Status transitions to `failed` | | |
| Error message descriptive | Indicates repo clone failure or access denied | | |
| Service remains healthy | Other work orders can still be created | | |

### 4.2 Create Work Order — Empty Request

```bash
curl -s -X POST http://localhost:8053/api/agent-work-orders/ \
  -H "Content-Type: application/json" \
  -d '{
    "repository_url": "https://github.com/youruser/test-repo",
    "user_request": "",
    "selected_commands": ["create-branch"]
  }' | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Validation error | 422 with descriptive error about empty request | | |

### 4.3 Create Work Order — Invalid Commands

```bash
curl -s -X POST http://localhost:8053/api/agent-work-orders/ \
  -H "Content-Type: application/json" \
  -d '{
    "repository_url": "https://github.com/youruser/test-repo",
    "user_request": "Add a README",
    "selected_commands": ["invalid-step", "fake-command"]
  }' | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Validation error | 422 with message about invalid commands | | |
| Valid step names listed | Error includes the valid options | | |

### 4.4 Create Work Order — Empty Commands List

```bash
curl -s -X POST http://localhost:8053/api/agent-work-orders/ \
  -H "Content-Type: application/json" \
  -d '{
    "repository_url": "https://github.com/youruser/test-repo",
    "user_request": "Add a README",
    "selected_commands": []
  }' | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Validation error | 422 — at least one command required | | |

### 4.5 Get Non-Existent Work Order

```bash
curl -s http://localhost:8053/api/agent-work-orders/wo-00000000 | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| 404 returned | Work order not found | | |

### 4.6 List Work Orders with Status Filter

```bash
curl -s "http://localhost:8053/api/agent-work-orders/?status=completed" | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Only completed orders returned | All entries have `status: "completed"` | | |
| Filter values work | `pending`, `running`, `completed`, `failed` all filter correctly | | |

### 4.7 SSE Stream for Completed Work Order

```bash
curl -s -N http://localhost:8053/api/agent-work-orders/{completed_work_order_id}/logs/stream &
sleep 5 && kill %1
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Stream opens successfully | Does not error immediately | | |
| Historical logs sent | Buffered logs flushed as initial events | | |
| No new events | Stream is quiet (order already completed) | | |

### 4.8 Concurrent Work Orders

Create two work orders in quick succession (planning-only for speed):

1. Create Work Order A (planning only)
2. Immediately create Work Order B (planning only) against the same repo

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Both orders created | Two distinct work order IDs returned | | |
| Both run concurrently | Both show `running` status simultaneously | | |
| Separate worktrees | Each gets its own sandbox directory | | |
| Both complete | Both reach `completed` status | | |
| No interference | Different branch names, separate step histories | | |

### 4.9 Delete Repository with Existing Work Orders

1. Attempt to delete the configured repository that has associated work orders

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Delete succeeds or warns | Repository removed from config (work orders reference URL, not config ID) | | |
| Existing work orders unaffected | Historical work orders still visible and queryable | | |

### 4.10 Service Restart Resilience

```bash
docker compose restart cortex-agent-work-orders
sleep 10
curl -s http://localhost:8053/health | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Service restarts cleanly | Health check returns `healthy` | | |
| Historical work orders preserved | `GET /api/agent-work-orders/` returns previous orders (Supabase storage) | | |
| Repositories preserved | `GET /api/agent-work-orders/repositories` returns configured repos | | |

---

## Phase 5 — UI Interaction Details

### 5.1 Layout Toggle

1. On the Agent Work Orders page, find the layout toggle
2. Switch between **Horizontal** and **Sidebar** modes

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Horizontal mode | Repository cards scroll horizontally at top, table below | | |
| Sidebar mode | Collapsible sidebar on left with repository list | | |
| Sidebar collapse | Clicking collapse reduces sidebar to icon-only width | | |
| Preference persisted | Refreshing the page keeps the selected layout | | |

### 5.2 Repository Selection via URL

1. Click on a repository card — note the URL changes to include `?repo={id}`
2. Copy the URL and open in a new tab

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| URL contains `?repo=` param | Repository ID in query string | | |
| New tab shows same selection | Opening the URL selects the correct repo | | |
| Browser back/forward | Navigation history works for repo selection | | |

### 5.3 Work Order Table Filtering

1. With a repository selected, verify the work order table filters to that repo
2. Click "All" in the pill navigation to see all work orders

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Repo filter works | Only work orders for selected repo shown | | |
| Stats accurate | Total/Active/Done counts match visible work orders | | |
| Search filter | Typing in search box filters work orders | | |

### 5.4 Work Order Detail — Step History Cards

1. Open a completed work order's detail view
2. Expand each step history card

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Cards show agent name | `BranchCreator`, `Planner`, `Implementor`, etc. | | |
| Duration shown | Execution time for each step | | |
| Output shown | Branch name, PRP path, PR URL, etc. | | |
| Success/failure indicator | Green check or red X per step | | |
| Collapsible | Cards expand and collapse smoothly | | |

### 5.5 Workflow Progress Visualization

On the detail view, examine the progress bar:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Step nodes rendered | One node per selected workflow step | | |
| Connecting lines | Lines between sequential nodes | | |
| Completed steps colored | Green or success color for completed steps | | |
| Failed step highlighted | Orange/red for failed step (if any) | | |
| Skipped steps grayed out | Steps after a failure are grayed | | |

---

## Phase 6 — Proxy and Networking

### 6.1 All API Calls Work Through Main Server Proxy

Repeat key API calls through port 8181 (main server) instead of 8053 (direct):

```bash
# List work orders via proxy
curl -s http://localhost:8181/api/agent-work-orders/ | python3 -m json.tool

# List repositories via proxy
curl -s http://localhost:8181/api/agent-work-orders/repositories | python3 -m json.tool

# Get specific work order via proxy
curl -s http://localhost:8181/api/agent-work-orders/{work_order_id} | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| List work orders | Same response as direct call | | |
| List repositories | Same response as direct call | | |
| Get work order | Same response as direct call | | |
| Proxy is transparent | No extra wrapping, same status codes | | |

### 6.2 Proxy Behavior When Service is Down

```bash
docker compose stop cortex-agent-work-orders
curl -s http://localhost:8181/api/agent-work-orders/ | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| 503 returned | Service unavailable error | | |
| Error message descriptive | Indicates agent work orders service is unreachable | | |
| Main server unaffected | Other Cortex endpoints still work | | |

**Cleanup:** `docker compose start cortex-agent-work-orders`

---

## Phase 7 — Debug Artifacts

### 7.1 Prompt Logging

After a completed work order, check for saved prompts:

```bash
ls /tmp/agent-work-orders/{work_order_id}/prompts/
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Directory exists | Prompt files saved when `ENABLE_PROMPT_LOGGING=true` | | |
| Files present | `prompt_*.txt` files, one per step | | |
| Content meaningful | Each file contains the rendered prompt sent to Claude CLI | | |

### 7.2 Output Artifacts

```bash
ls /tmp/agent-work-orders/{work_order_id}/outputs/
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Directory exists | Output files saved when `ENABLE_OUTPUT_ARTIFACTS=true` | | |
| JSONL files | `output_*.jsonl` — raw Claude CLI stream output | | |
| JSON files | `output_*.json` — parsed structured output | | |

---

## Cleanup

After completing all tests:

1. **Close PRs**: Close or delete any test PRs created on your test repo
2. **Delete branches**: Remove `wo-*` branches from your test repo
3. **Remove work orders**: Work orders persist in Supabase — leave for historical reference or delete via API
4. **Delete test repository config**: Remove the configured repository if no longer needed
5. **Clean temp files**: `rm -rf /tmp/agent-work-orders/` (optional — files have TTL)

```bash
# Clean up remote branches
gh api repos/youruser/test-repo/git/refs --jq '.[].ref' | grep 'wo-' | while read ref; do
  gh api -X DELETE "repos/youruser/test-repo/git/refs/${ref#refs/}"
done

# Close test PRs
gh pr list --repo youruser/test-repo --state open --json number --jq '.[].number' | while read pr; do
  gh pr close "$pr" --repo youruser/test-repo --delete-branch
done
```

---

## Results Summary

| Phase | Tests | Passed | Failed | Skipped |
|-------|-------|--------|--------|---------|
| 1 — Infrastructure | 1.1–1.6 | | | |
| 2 — Repository Management | 2.1–2.7 | | | |
| 3 — Work Order Execution | 3.1–3.15 | | | |
| 4 — Edge Cases | 4.1–4.10 | | | |
| 5 — UI Interaction | 5.1–5.5 | | | |
| 6 — Proxy & Networking | 6.1–6.2 | | | |
| 7 — Debug Artifacts | 7.1–7.2 | | | |
| **Total** | | | | |

---

## Known Limitations (Not Bugs)

These are documented limitations in the current implementation:

- **No cancellation**: Once a work order starts running, it cannot be stopped
- **Phase 2 placeholder**: `POST /{id}/prompt` (send prompt to running agent) returns success but does nothing
- **Git progress**: `GET /{id}/git-progress` returns metadata values, not live git inspection
- **Human-in-loop stub**: The "Approve and Continue" button in step history cards logs to console only
- **In-memory log buffer**: Logs are lost on service restart (work order state persists in Supabase, but live logs do not)
