# Auto Research — End-to-End User Journey

## User Persona

**Cole** is a developer who maintains Cortex and multiple projects managed by Cortex. He wants
to use the Auto Research engine to automatically improve prompts — skills, commands, and agent
instructions — by iteratively mutating them, testing against evaluation suites, and keeping the
best-performing variants. He works on **WIN-AI-PC** running WSL2 with Cortex deployed locally.

---

## Journey Overview

This journey tests every user-facing aspect of the Auto Research feature across five phases:

| Phase | Focus |
|-------|-------|
| Phase 1 | Navigation — sidebar, page load, empty states |
| Phase 2 | Eval suites — listing, card display, suite details |
| Phase 3 | Starting an optimization — config modal, validation, job kick-off |
| Phase 4 | Monitoring progress — live polling, iteration table, status transitions |
| Phase 5 | Results — applying winning prompts, job history, edge cases |

---

## Prerequisites

- Cortex stack running: `docker compose up -d` (server + frontend)
- Database migration `024_add_auto_research_tables.sql` applied to Supabase
- At least one eval suite JSON file in `python/src/server/data/eval_suites/`
  (the repo ships with `planning_prompt_v1.json`)
- An LLM API key configured in Cortex settings (OpenAI or Anthropic)
- The target prompt file exists on disk (e.g., `.claude/commands/agent-work-orders/planning.md`)
- Browser open to `http://localhost:3737`
- Frontend dev server running: `cd cortex-ui && npm run dev`

---

## Phase 1 — Navigation & Page Load

### 1.1 Sidebar Link Visible

Navigate to Cortex UI in browser.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Sidebar has "Auto Research" entry | Visible with Sparkles icon | | |
| Icon uses cyan accent color | Matches other sidebar icons | | |
| Link position | Below existing nav items | | |

### 1.2 Navigate to Auto Research Page

Click "Auto Research" in the sidebar.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| URL changes to `/auto-research` | Correct | | |
| Sidebar link shows active state | Blue gradient background, neon underline | | |
| Page title | "Auto Research" with Sparkles icon | | |
| Subtitle | "Iterative prompt optimization engine" | | |

### 1.3 Page Sections Load

Wait for data to load (brief "Loading suites..." / "Loading jobs..." text).

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| "Available Eval Suites" section visible | Shows section heading | | |
| "Recent Jobs" section visible | Shows section heading | | |
| No console errors | Clean console | | |

### 1.4 Empty Jobs State

If no optimization jobs have been run yet:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Jobs section shows empty message | "No optimization jobs yet. Run an eval suite to get started." | | |
| No table headers shown | Table hidden when empty | | |

---

## Phase 2 — Eval Suite Display

### 2.1 Suite Cards Render

The shipped `planning_prompt_v1.json` suite should appear.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| At least 1 suite card visible | "Agent Work Orders Planning Prompt" card | | |
| Card layout | Grid: 3 columns on desktop, responsive | | |
| Cards have glassmorphism styling | Dark gradient background, subtle border, backdrop blur | | |

### 2.2 Suite Card Content

Inspect the "Agent Work Orders Planning Prompt" card:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Suite name displayed | "Agent Work Orders Planning Prompt" | | |
| Description shown | Evaluates planning prompt quality text | | |
| Target file path shown | `.claude/commands/agent-work-orders/planning.md` with file icon | | |
| Test case count shown | "3 test cases" with clock icon | | |
| Optimize button present | Cyan "Optimize" button with Sparkles icon at bottom of card | | |
| Optimize button enabled | Clickable (no running jobs) | | |

### 2.3 No Suites State

If you temporarily rename the eval suites directory to test the empty state:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Empty suites message | "No eval suites configured." with file icon | | |
| Message centered in section | Properly styled placeholder | | |

---

## Phase 3 — Starting an Optimization

### 3.1 Open Config Modal

Click the "Optimize" button on the planning prompt suite card.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Config modal opens | Dialog overlay appears | | |
| Modal title | "Optimize: Agent Work Orders Planning Prompt" | | |
| Modal description | "Configure the optimization run parameters." | | |

### 3.2 Config Modal Controls

Inspect the modal contents:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Iteration budget slider present | Range input with label "Iteration Budget" | | |
| Default value is 10 | Slider at 10, label shows "10" in cyan | | |
| Slider range | Min: 1, Max: 50 | | |
| Move slider to 3 | Label updates to "3" | | |
| Min/Max labels below slider | "1" on left, "50" on right | | |
| Model override input present | Text input labeled "Model Override (optional)" | | |
| Model placeholder | "Leave empty for default" | | |
| Cost note | "~3 LLM calls per iteration" in small gray text | | |
| Cancel button | "Cancel" outline button in footer | | |
| Start button | "Start Optimization" cyan button in footer | | |

### 3.3 Cancel Config Modal

Click "Cancel" in the modal footer.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Modal closes | Dialog dismissed, page visible | | |
| No job started | No new job in Recent Jobs table | | |

### 3.4 Start Optimization with Low Iterations

Open the config modal again. Set iterations to **2** (for quick testing). Leave model empty.
Click "Start Optimization."

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Start button shows loading state | Button disabled with spinner/loading indicator | | |
| Modal closes after submission | Dialog dismissed | | |
| Progress modal opens automatically | JobProgressModal appears with "Optimization Progress" title | | |
| Status badge in page header | "Job running..." pulsing badge appears at top of page | | |

---

## Phase 4 — Monitoring Progress

### 4.1 Progress Modal — Running State

While the optimization is running (may take 30-60 seconds per iteration):

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Status badge | "running" in cyan | | |
| Progress bar visible | Cyan bar growing as iterations complete | | |
| Progress percentage | Shows "X%" right-aligned below bar | | |
| Iteration counter | Shows "X / 2 iterations" | | |
| Cancel button visible | Red "Cancel Job" button in footer | | |
| Close button visible | "Close" outline button in footer | | |

### 4.2 Iteration Table Populates

As iterations complete, the table should populate:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Table headers | #, Score, Frontier, Signals | | |
| Iteration 0 row (baseline) | Shows baseline score, "Yes" frontier badge | | |
| Score column | Formatted to 3 decimal places (e.g., "0.600") | | |
| Frontier column | "Yes" in cyan badge for accepted iterations, "—" for rejected | | |
| Signals column | Summary like "3/5 passing" | | |
| Frontier rows highlighted | Left cyan border and light cyan background | | |

### 4.3 Live Polling

The modal polls every 3 seconds while the job is running.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| New iterations appear automatically | Table updates without manual refresh | | |
| Progress bar advances | Percentage increases with each iteration | | |
| No page flicker | Smooth updates, no full re-render | | |

### 4.4 Job Completion

Wait for both iterations to complete.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Status badge changes | "completed" in green | | |
| Progress bar | 100% and green | | |
| Cancel button disappears | No longer shown | | |
| Improvement summary appears | "Baseline X.XXX → Best Y.YYY" text | | |
| If improved: checkmark icon | Green check next to improvement summary | | |
| If improved: Apply button | "Apply Result" cyan button in footer | | |
| If NOT improved: message | "No improvement found" text in footer | | |
| Polling stops | Network tab shows no more polling requests | | |

### 4.5 Close Progress Modal

Click "Close" to dismiss the modal.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Modal closes | Returns to main page | | |
| "Job running" badge gone | No running status in header | | |
| Job appears in Recent Jobs table | New row at top of table | | |

---

## Phase 5 — Results & Job History

### 5.1 Recent Jobs Table

After the optimization completes, check the Recent Jobs section:

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| New job row visible | At top of table (most recent first) | | |
| Suite column | Shows "planning_prompt_v1" | | |
| Status column | Green "completed" badge | | |
| Best Score column | Shows numeric score (e.g., "0.800") | | |
| Iterations column | "2 / 2" | | |
| Started column | Today's date and time | | |

### 5.2 Reopen Job Detail

Click the completed job row in the Recent Jobs table.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Progress modal reopens | Shows completed job details | | |
| All iterations visible | Baseline + 2 mutation iterations in table | | |
| Improvement summary shown | Baseline → Best score comparison | | |
| Apply button available (if improved) | "Apply Result" button in footer | | |

### 5.3 Apply Winning Prompt

If the optimization found an improvement, click "Apply Result."

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Button shows loading state | Brief loading indicator | | |
| Success feedback | Button completes without error | | |
| Target file updated | Run `git diff .claude/commands/agent-work-orders/planning.md` to verify changes | | |
| Changes are reversible | `git checkout .claude/commands/agent-work-orders/planning.md` to revert | | |

### 5.4 Verify File Changes

In terminal, inspect what the engine changed:

```bash
git diff .claude/commands/agent-work-orders/planning.md
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| File has been modified | `git diff` shows changes | | |
| Changes are substantive | Prompt text has been rewritten, not just whitespace | | |
| Original purpose preserved | Prompt still instructs a planning workflow | | |

Revert to original after inspection:

```bash
git checkout .claude/commands/agent-work-orders/planning.md
```

### 5.5 Concurrent Job Guard

While no job is running, start a new optimization. Then **immediately** try to start a second one
from a different suite card (or the same one).

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| First job starts normally | Progress modal opens | | |
| Optimize buttons disabled | All suite cards show disabled Optimize buttons | | |
| Disabled tooltip | Hover shows "An optimization job is already running" | | |
| If bypassed via API | Backend returns 409 Conflict | | |

### 5.6 Cancel a Running Job

Start a new optimization with 10 iterations. While it's running, click "Cancel Job."

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Cancel button works | Click triggers cancellation | | |
| Status changes to "cancelled" | Gray badge in modal | | |
| Progress bar stops | No further progress | | |
| Polling stops | No more network requests | | |
| No Apply button | Footer shows only Close button | | |
| Job appears as cancelled in table | Gray "cancelled" badge in Recent Jobs | | |
| Optimize buttons re-enable | Can start a new optimization | | |

### 5.7 Failed Job Display

To simulate a failure, temporarily rename the target file so the engine can't read it,
then start an optimization.

```bash
mv .claude/commands/agent-work-orders/planning.md .claude/commands/agent-work-orders/planning.md.bak
```

Start an optimization for the planning prompt suite.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Job fails quickly | Status changes to "failed" | | |
| Error message shown | Red error box in progress modal with description | | |
| Progress bar | Red bar | | |
| No Apply button | Footer shows only Close button | | |
| Job in table | Red "failed" badge | | |

Restore the file:

```bash
mv .claude/commands/agent-work-orders/planning.md.bak .claude/commands/agent-work-orders/planning.md
```

---

## Phase 6 — Stale Job Recovery (Optional)

This tests that jobs orphaned by a server restart are cleaned up.

### 6.1 Simulate Server Crash

Start an optimization with 50 iterations. While it's running, restart the backend:

```bash
docker compose restart cortex-server
# or if running locally:
# kill the uv process and restart
```

### 6.2 Verify Recovery

After the server restarts, refresh the Auto Research page.

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Orphaned job is now "failed" | Status changed from running to failed | | |
| Error message | "Server restarted during optimization" | | |
| Can start new jobs | Optimize buttons are enabled | | |

---

## Test Summary

| Phase | Test Count | Result |
|-------|-----------|--------|
| Phase 1 — Navigation | 4 tests | |
| Phase 2 — Eval Suites | 3 tests | |
| Phase 3 — Starting Optimization | 4 tests | |
| Phase 4 — Monitoring Progress | 5 tests | |
| Phase 5 — Results & History | 7 tests | |
| Phase 6 — Stale Recovery | 1 test (optional) | |
| **Total** | **24 tests** | |
