# Auto-Research Engine — Design & Implementation Plan

**Date:** 2026-03-20
**Status:** Ready for Development

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

## Overview

A self-improvement engine for Cortex. Given any prompt file (skill, command, agent instruction, or config), the engine iteratively mutates the prompt via LLM, runs the mutated version against a defined evaluation suite, scores the output, and keeps the best-performing variant. The winning prompt is presented to the user with a diff for review and one-click application.

The engine is domain-agnostic — it optimizes any text payload that can be scored against test cases. Phase 1 targets file-based prompts (skills, commands, agent prompts). Later phases add system-level targets (CLI execution, web parsing, Postman tests).

## What Changed From the Original Design

The original plan proposed Agent Work Orders (CLI execution in git worktrees) as the Phase 1 target with GitHub PR finalization. After reviewing the codebase, I redesigned the approach:

| Original | Redesigned | Why |
|----------|-----------|-----|
| Phase 1 target: Agent Work Orders | Phase 1 target: Prompt optimization | Agent Work Orders requires Claude Code CLI, git worktrees, code compilation — the hardest possible starting point. Prompt optimization uses only LLM API calls, is fast (seconds per iteration), and covers more targets |
| Raw `subprocess` calls for LLM | PydanticAI agents | Cortex already has a mature PydanticAI framework (`python/src/agents/`). Mutation and evaluation agents get structured output, rate limiting, and model flexibility for free |
| GitHub PR finalization | "Apply" button writes to file | PRs add `gh` CLI dependency, branch management, and auth complexity. Writing to file is simpler, reversible (git shows the diff), and gives the user full control |
| No eval suite concept | JSON eval suites with test cases | The original plan hardcoded test cases in target implementations. Eval suites are data files that can be versioned, shared, and edited without code changes |
| `sandbox_manager` (doesn't exist) | Not needed for Phase 1 | Prompt optimization runs LLM API calls, not system processes. No sandbox required |
| No testing tasks | Each task includes tests | The project requires pytest (backend) and vitest (frontend) |
| No stale job recovery | Startup cleanup of orphaned jobs | `asyncio.create_task` jobs die on server restart |

## Core Architecture

### The Optimization Loop

```
┌─────────────────────────────────────────────────┐
│                 Eval Suite (JSON)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Test Case │ │ Test Case │ │ Test Case │ ...   │
│  │ input +   │ │ input +   │ │ input +   │       │
│  │ signals   │ │ signals   │ │ signals   │       │
│  └──────────┘ └──────────┘ └──────────┘        │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│              Core Loop (per iteration)          │
│                                                 │
│  1. MUTATE   ──▶ LLM rewrites the prompt        │
│  2. EXECUTE  ──▶ Run mutated prompt against      │
│                  each test case via LLM API      │
│  3. EVALUATE ──▶ LLM-as-judge scores each        │
│                  output against expected signals  │
│  4. ACCEPT   ──▶ Keep if score improves AND       │
│                  no critical signal regresses     │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  Winner: best-scoring prompt shown with diff    │
│  User clicks "Apply" to write to file           │
└─────────────────────────────────────────────────┘
```

### PydanticAI Integration

The engine uses two purpose-built PydanticAI agents (NOT subclasses of `BaseAgent` — these are lightweight, internal-only agents):

**Mutator Agent**: Takes the current prompt + iteration history and produces a rewritten prompt. Uses `result_type=str`. System prompt includes the eval suite's `mutation_guidance` to focus improvements.

**Evaluator Agent**: Takes a test case's expected signals + the LLM output from execution and produces structured scores. Uses `result_type=EvalResult` (Pydantic model with boolean signals and reasoning). This is the LLM-as-judge.

**Execution** is not an agent — it's a direct PydanticAI `Agent.run()` call using the mutated prompt as the system prompt and each test case's input as the user message.

### Evaluation Suites

Each target prompt has a corresponding JSON eval suite defining how to test it:

```json
{
  "id": "planning_prompt_v1",
  "name": "Agent Work Orders Planning Prompt",
  "description": "Evaluates planning prompt quality against canonical feature requests",
  "target_file": ".claude/commands/agent-work-orders/planning.md",
  "model": "openai:gpt-4o-mini",
  "mutation_guidance": "Improve clarity and specificity. Plans should have numbered steps, identify specific files, include testing, and match request scope.",
  "test_cases": [
    {
      "id": "tc_simple_crud",
      "name": "Simple CRUD API",
      "input": "Create a REST API for managing a todo list with SQLite storage",
      "signals": {
        "has_numbered_steps": {
          "weight": 1.0,
          "critical": false,
          "description": "Plan has clearly numbered implementation steps"
        },
        "identifies_files": {
          "weight": 2.0,
          "critical": true,
          "description": "Plan identifies specific files to create or modify"
        },
        "includes_testing": {
          "weight": 1.0,
          "critical": false,
          "description": "Plan includes a testing step"
        }
      }
    }
  ]
}
```

Key fields:
- **`target_file`**: Path to the prompt file (relative to repo root, or absolute for other projects)
- **`model`**: LLM model for execution. Uses Cortex's configured credentials. Defaults to the model set in Cortex settings if omitted.
- **`mutation_guidance`**: Tells the mutator what aspects of the prompt to focus on
- **`signals`**: Each signal has a `weight` (for scoring) and `critical` flag (for regression protection)

### Scoring & Acceptance

**Scalar score** = weighted average of signal values, normalized to [0, 1]:
```
score = sum(signal_value * signal_weight) / sum(signal_weights)
```

**Acceptance rule** — a candidate is accepted only if:
1. `candidate.scalar_score > current_best.scalar_score`, AND
2. No signal marked `critical: true` regresses from `true` to `false`

This prevents the optimizer from improving overall score by breaking important behaviors.

## Database Schema

```sql
CREATE TABLE auto_research_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_suite_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',  -- running, completed, failed, cancelled
    target_file TEXT NOT NULL,
    baseline_payload TEXT NOT NULL,
    baseline_score FLOAT,
    best_payload TEXT,
    best_score FLOAT,
    max_iterations INT NOT NULL,
    completed_iterations INT NOT NULL DEFAULT 0,
    model TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE auto_research_iterations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES auto_research_jobs(id) ON DELETE CASCADE,
    iteration_number INT NOT NULL,
    payload TEXT NOT NULL,
    scalar_score FLOAT NOT NULL,
    signals JSONB NOT NULL,           -- {signal_name: {value: bool, reasoning: str}}
    is_frontier BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_auto_research_jobs_status ON auto_research_jobs(status);
CREATE INDEX idx_auto_research_iterations_job_id ON auto_research_iterations(job_id);
```

Changes from original schema:
- Added `eval_suite_id`, `target_file`, `baseline_payload`, `best_payload` to jobs (the job is self-contained — you can see what was optimized and the result without cross-referencing files)
- Added `max_iterations`, `completed_iterations`, `model`, `error_message` to jobs
- Renamed `evaluation_details` to `signals` in iterations (more specific)
- Removed `pr_url` (no PR in Phase 1)
- Added indexes

## File Structure

```
python/src/server/
├── models/
│   └── auto_research.py                # Pydantic models + Protocol
├── services/
│   ├── auto_research_service.py        # Core loop + orchestration
│   └── auto_research/
│       ├── __init__.py
│       ├── eval_suite_loader.py        # JSON loading + validation
│       ├── prompt_target.py            # PromptTarget (Phase 1)
│       ├── mutator.py                  # PydanticAI mutation agent
│       └── evaluator.py               # PydanticAI evaluation agent
├── api_routes/
│   └── auto_research_api.py
└── data/
    └── eval_suites/                    # JSON eval suite fixtures
        └── example_planning.json

cortex-ui/src/features/
└── auto-research/
    ├── types/index.ts
    ├── services/autoResearchService.ts
    ├── hooks/useAutoResearchQueries.ts
    └── components/
        ├── OptimizeButton.tsx
        ├── OptimizeConfigModal.tsx
        └── JobProgressModal.tsx
```

## Design Decisions

### Prompt Optimization First (Not System Testing)

Phase 1 optimizes file-based prompts using LLM API calls only. No CLI tooling, no sandboxing, no external dependencies. Each iteration takes seconds, not minutes. This exercises the full engine (mutate → execute → evaluate → accept) while being fast, cheap, and debuggable.

### PydanticAI for Mutation & Evaluation

Uses PydanticAI `Agent` directly (not `BaseAgent` subclass). The mutation agent returns `str` (new prompt text). The evaluation agent returns `EvalResult` (structured Pydantic model). This gives us structured output, automatic retry, and model flexibility with minimal code.

### ProgressTracker Polling for Live Updates

Uses existing `ProgressTracker` with ETag caching. Frontend polls via `useSmartPolling`. No SSE, no new dependencies. Iteration progress is updated after each iteration completes.

### Single Job Concurrency

One optimization job at a time. `409 Conflict` if a job is already running. Stale jobs (status = `running` at server startup) are marked `failed` with an error message.

### Iteration Cap for Cost Control

Config modal has an iteration budget slider (default: 10, max: 50). UI tooltip notes "~3 LLM calls per iteration." No token tracking in Phase 1.

### Apply Instead of PR

Winning prompt is stored in the DB and shown with a diff in the UI. User clicks "Apply" to write it to the target file. Fully reversible via `git checkout`.

## Phase Roadmap

### Phase 1: Prompt Optimization Engine (This Plan)

Core loop + PromptTarget. File-based prompts only. JSON eval suites. ProgressTracker polling. Minimal UI with iteration table, diff viewer, apply button.

### Phase 2: Rich Targets & Eval Management

- Embedded prompt extraction (Python string variables via AST)
- Web crawling parser target (golden file comparison)
- Knowledge materializer target (synthesizer prompt)
- Eval suite CRUD UI (create/edit suites in browser)
- GitHub PR finalization for winning payloads

### Phase 3: System-Level Targets

- Agent Work Orders target (Claude Code CLI execution in git worktrees)
- Postman test target (Newman execution)
- PR Reviews target (synthetic PR with injected bugs)
- Multi-job concurrency with semaphore
- Cross-project optimization (prompts in other repos managed by Cortex)

---

# Phase 1 — Implementation Plan

## Task 1: Database Migration

**Files:**
- Create: `migration/0.1.0/024_add_auto_research_tables.sql`
- Modify: `migration/complete_setup.sql`

**Steps:**
1. Create `auto_research_jobs` and `auto_research_iterations` tables per the schema above.
2. Add indexes on `status` and `job_id`.
3. Add the migration to `complete_setup.sql`.

**Tests:** Verify migration runs cleanly against a fresh database.

---

## Task 2: Core Models, Protocol & Eval Suite Loader

**Files:**
- Create: `python/src/server/models/auto_research.py`
- Create: `python/src/server/services/auto_research/__init__.py`
- Create: `python/src/server/services/auto_research/eval_suite_loader.py`
- Create: `python/src/server/data/eval_suites/` (directory)

**Steps:**
1. Define Pydantic models:
   - `EvalSignal` — `value: bool`, `weight: float`, `critical: bool`, `reasoning: str | None`
   - `EvalResult` — `signals: dict[str, EvalSignal]`, `scalar_score: float`, `pass_status: bool`
   - `TestCaseDefinition` — `id: str`, `name: str`, `input: str`, `signals: dict[str, SignalDefinition]`
   - `EvalSuiteDefinition` — `id: str`, `name: str`, `target_file: str`, `model: str | None`, `mutation_guidance: str`, `test_cases: list[TestCaseDefinition]`
   - `AutoResearchJob` — matches DB schema
   - `AutoResearchIteration` — matches DB schema
2. Define `AutoResearchTarget` Protocol with methods: `mutate`, `execute`, `evaluate`, `accept`.
3. Implement `EvalSuiteLoader`:
   - `load_suite(suite_id: str) -> EvalSuiteDefinition` — loads and validates a JSON file
   - `list_suites() -> list[EvalSuiteSummary]` — returns id, name, target_file for all suites
   - Scans `python/src/server/data/eval_suites/*.json`
   - Validates against Pydantic models on load

**Tests:**
- Model validation (valid/invalid inputs)
- Suite loader with fixture JSON files
- Error handling for missing/malformed suites

---

## Task 3: Mutation & Evaluation Agents

**Files:**
- Create: `python/src/server/services/auto_research/mutator.py`
- Create: `python/src/server/services/auto_research/evaluator.py`

**Steps:**
1. **Mutator** (`mutator.py`):
   - Create PydanticAI `Agent` with `result_type=str`
   - System prompt: "You are a prompt optimization specialist. Rewrite the given prompt to improve its performance. {mutation_guidance}"
   - `async def mutate(current_payload: str, history: list[dict], guidance: str, model: str) -> str`
   - User message includes current prompt + last N iteration summaries (scores, which signals failed)
   - Returns the complete rewritten prompt text

2. **Evaluator** (`evaluator.py`):
   - Create PydanticAI `Agent` with `result_type=EvalResult`
   - System prompt: "You are an evaluation judge. Score the given output against each expected signal. Be strict and objective."
   - `async def evaluate(test_case: TestCaseDefinition, llm_output: str, model: str) -> EvalResult`
   - User message includes the test case definition (signal names + descriptions) and the LLM output to judge
   - Returns structured `EvalResult` with boolean value + reasoning per signal

3. **LLM model resolution**: Accept `model` parameter. If `None`, fall back to Cortex's configured default model (from `llm_provider_service.py` / environment variables). Use PydanticAI model string format (e.g., `"openai:gpt-4o"`, `"anthropic:claude-sonnet-4-6"`).

**Tests:**
- Mutator returns valid string (mock PydanticAI agent)
- Evaluator returns valid `EvalResult` with all expected signal names (mock PydanticAI agent)
- Model fallback behavior

---

## Task 4: PromptTarget & Core Loop Service

**Files:**
- Create: `python/src/server/services/auto_research/prompt_target.py`
- Create: `python/src/server/services/auto_research_service.py`

**Steps:**
1. **PromptTarget** (`prompt_target.py`):
   - Implements `AutoResearchTarget` protocol
   - Constructor takes `EvalSuiteDefinition`
   - `payload`: Reads target file content from disk
   - `mutate()`: Delegates to mutator agent
   - `execute()`: For each test case, creates a PydanticAI `Agent` with the mutated prompt as system prompt and runs `agent.run(test_case.input)`. Collects outputs.
   - `evaluate()`: For each test case + output pair, delegates to evaluator agent. Aggregates signals across all test cases using weighted average.
   - `accept()`: Score improvement check + critical signal regression check

2. **AutoResearchService** (`auto_research_service.py`):
   - Constructor: Takes Supabase client (follows existing service pattern)
   - `async def run_optimization(eval_suite_id: str, max_iterations: int, model: str | None) -> str`:
     - Load eval suite via `EvalSuiteLoader`
     - Read baseline prompt from target file
     - Create `PromptTarget`
     - Run baseline evaluation (iteration 0)
     - Create job in DB with `status='running'`
     - Create `ProgressTracker` entry
     - Loop `max_iterations` times:
       - Mutate → Execute → Evaluate → Accept
       - Save iteration to DB
       - Update ProgressTracker (current iteration, score, frontier status)
       - Update job's `best_payload` and `best_score` if accepted
     - Mark job `completed` (or `failed` on error)
     - Return job ID
   - `async def apply_result(job_id: str) -> str`: Reads `best_payload` from job, writes to `target_file`, returns the file path
   - `async def get_job(job_id: str) -> AutoResearchJob`: Full job with iterations
   - `async def list_jobs() -> list[AutoResearchJob]`: All jobs ordered by created_at desc
   - **Stale job recovery**: On service initialization, query for `status='running'` jobs and mark them `failed` with `error_message='Server restarted during optimization'`
   - **Concurrency guard**: Before starting, check for active running jobs. Return error if one exists.

**Tests:**
- Core loop with mock target (verify iteration count, DB writes, ProgressTracker updates)
- Accept logic (score improvement + regression protection)
- Stale job recovery
- Concurrency guard
- Apply writes correct content to file

---

## Task 5: API Routes

**Files:**
- Create: `python/src/server/api_routes/auto_research_api.py`
- Modify: `python/src/server/main.py`

**Steps:**
1. `GET /api/auto-research/suites` — List available eval suites (from loader)
2. `POST /api/auto-research/start` — Accepts `{ eval_suite_id, max_iterations, model? }`. Returns `{ job_id, progress_id }`. Starts optimization as background task. Returns `409` if a job is running.
3. `GET /api/auto-research/jobs` — List all jobs (paginated)
4. `GET /api/auto-research/jobs/{job_id}` — Full job detail with all iterations
5. `POST /api/auto-research/jobs/{job_id}/apply` — Write winning payload to target file. Returns `{ file_path, success }`.
6. `POST /api/auto-research/jobs/{job_id}/cancel` — Set status to `cancelled`, stop the background task.
7. Progress polling uses the existing `GET /api/progress/{progress_id}` endpoint — no new progress routes needed.
8. Register router in `main.py`.

**Tests:**
- Route registration
- 409 on concurrent job start
- Apply endpoint writes file
- Cancel endpoint updates status

---

## Task 6: Frontend Types, Service & Query Hooks

**Files:**
- Create: `cortex-ui/src/features/auto-research/types/index.ts`
- Create: `cortex-ui/src/features/auto-research/services/autoResearchService.ts`
- Create: `cortex-ui/src/features/auto-research/hooks/useAutoResearchQueries.ts`

**Steps:**
1. **Types**: `EvalSuiteSummary`, `AutoResearchJob`, `AutoResearchIteration`, `EvalSignalResult`, `StartOptimizationRequest`
2. **Service**: `autoResearchService` object with methods:
   - `listSuites()` — GET /api/auto-research/suites
   - `startOptimization(request)` — POST /api/auto-research/start
   - `listJobs()` — GET /api/auto-research/jobs
   - `getJob(jobId)` — GET /api/auto-research/jobs/{jobId}
   - `applyResult(jobId)` — POST /api/auto-research/jobs/{jobId}/apply
   - `cancelJob(jobId)` — POST /api/auto-research/jobs/{jobId}/cancel
3. **Query hooks**:
   - `autoResearchKeys` factory: `all`, `suites`, `jobs`, `jobDetail(id)`
   - `useEvalSuites()` — list suites with `STALE_TIMES.rare`
   - `useAutoResearchJobs()` — list jobs with smart polling
   - `useAutoResearchJob(jobId)` — job detail with smart polling (polls while `status === 'running'`)
   - `useStartOptimization()` — mutation hook
   - `useApplyResult()` — mutation hook
   - `useCancelJob()` — mutation hook

**Tests:**
- Query key factory structure
- Hook configuration (stale times, enabled conditions)

---

## Task 7: Frontend UI Components

**Files:**
- Create: `cortex-ui/src/features/auto-research/components/OptimizeButton.tsx`
- Create: `cortex-ui/src/features/auto-research/components/OptimizeConfigModal.tsx`
- Create: `cortex-ui/src/features/auto-research/components/JobProgressModal.tsx`
- Create: `cortex-ui/src/features/auto-research/components/AutoResearchPage.tsx`

**Steps:**
1. **AutoResearchPage**: Dedicated page (add route). Lists available eval suites as cards. Each card shows suite name, target file, test case count, and an "Optimize" button. Below the suites, shows recent job history.

2. **OptimizeButton**: Triggers the config modal. Disabled with "Job already running" tooltip when there's an active job.

3. **OptimizeConfigModal**: Radix Dialog with:
   - Suite name and target file (read-only, from selected suite)
   - Iteration budget slider (default 10, max 50)
   - Model selector (optional override, defaults to Cortex's configured model)
   - "~3 LLM calls per iteration" note
   - Start button

4. **JobProgressModal**: Opens automatically when a job starts. Shows:
   - Progress bar with iteration count (`3 / 10 iterations`)
   - Table of completed iterations: iteration number, score, is_frontier flag, signal summary
   - Diff viewer: side-by-side comparison of baseline vs. current best payload
   - On completion: "Apply" button (writes to file) + "Dismiss" button
   - On failure: error message display

**Tests:**
- Component rendering with mock data
- Button disabled state
- Modal open/close behavior

---

## Task 8: Seed Eval Suite & End-to-End Validation

**Files:**
- Create: `python/src/server/data/eval_suites/planning_prompt_v1.json`
- Create: `python/tests/server/services/test_auto_research_e2e.py`

**Steps:**
1. Create a real eval suite for the agent work orders planning prompt (`.claude/commands/agent-work-orders/planning.md`):
   - 3 test cases: simple CRUD, React component, CLI tool
   - 4-5 signals per test case: `has_numbered_steps`, `identifies_files`, `includes_testing`, `scope_matches_request`, `considers_edge_cases`
   - Mutation guidance focused on clarity, specificity, and actionability

2. End-to-end integration test:
   - Loads the suite
   - Runs 2 iterations (keep it cheap)
   - Verifies: job created in DB, iterations recorded, scores computed, best payload tracked
   - Verifies: ProgressTracker updated at each step
   - Verifies: Apply writes correct content to a temp file
   - Mark as `@pytest.mark.integration` (skippable in CI without API keys)

3. Manual validation: Run the full optimization loop against the planning prompt and verify the winning prompt is meaningfully different from the original.

---

## Optimization Target Inventory

These are the Cortex prompts available for optimization once the engine is built. Each needs an eval suite JSON file to be actionable:

### High Impact (create eval suites first)
| Target | File | Why |
|--------|------|-----|
| Planning prompt | `.claude/commands/agent-work-orders/planning.md` | Used for every work order; directly affects code quality |
| Execute prompt | `.claude/commands/agent-work-orders/execute.md` | Controls how agents implement plans |
| PRP creation | `.claude/commands/prp-claude-code/prp-claude-code-create.md` | Drives research quality for implementations |
| Synthesizer system prompt | `python/src/agents/synthesizer_agent.py` (SYSTEM_PROMPT) | Used for ALL knowledge materialization (Phase 2: needs AST extraction) |

### Medium Impact (create eval suites later)
| Target | File |
|--------|------|
| RAG agent system prompt | `python/src/agents/rag_agent.py` (Phase 2: embedded) |
| Cortex prime | `.claude/commands/cortex/cortex-prime.md` |
| Code review | `.claude/commands/cortex/cortex-alpha-review.md` |
| Cortex memory skill | `integrations/claude-code/extensions/cortex-memory/SKILL.md` |

### Other Projects
Any skill or command file in a project managed by Cortex can be targeted by specifying an absolute path in `target_file`.
