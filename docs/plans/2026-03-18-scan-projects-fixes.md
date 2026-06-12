# Scan-Projects Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 10 issues discovered during the first `/scan-projects` journey test — covering local README ingestion, dedup improvements, skill hardening, crawl infrastructure resilience, and REST/MCP parity.

**Architecture:** Changes span the skill file, scanner script, backend API, progress tracking, and MCP server. The skill orchestrates Claude Code's behavior; the scanner runs locally on the user's machine; backend services handle crawl orchestration and progress tracking.

**Tech Stack:** Python 3.12 (backend), Python 3.8+ (scanner script, stdlib only), Markdown (skill file), SQL (migrations)

---

## Issue → Task Mapping

| Issue # | Title | Task(s) |
|---------|-------|---------|
| #5 | Local README ingestion as default | T1 |
| #2 | Recursive crawling wrong for READMEs | Eliminated by T1 |
| #6 | No dedup within scan results | T2 |
| #7 | Dedup by title as fallback | T2 |
| #9 | PostmanFastAPIDemo phantom directory | T3 |
| #4 | REST/MCP parity — project_id linking | T4 |
| #1 | Crawl queue persistence | T5 |
| #10 | Concurrent crawl limiting / crash prevention | T6 |
| #8 | No bulk progress monitoring | T7 |
| #3 | MCP session breaks on restart | T8 |
| — | Journey test Phase 5 update | T9 |
| — | Log findings in journey test | T10 |
| — | MCP endpoint gap (already fixed) | Done this session |

---

## Task 1: Rewrite Step 10 — Local README Inline Ingestion

**Files:**
- Modify: `integrations/claude-code/commands/scan-projects.md` (Steps 10 and 11)

- [ ] **Step 1: Replace Step 10 in the skill**

Replace lines 130-141 (current Step 10) with:

```markdown
### Step 10 — Knowledge Base Ingestion

For each created project that has `readme_excerpt` (non-null) in the scan results:
- Call `manage_rag_source` MCP tool with:
  - `action: "add"`
  - `source_type: "inline"`
  - `title: "<directory_name> README"`
  - `documents: [{"title": "README.md", "content": "<readme_excerpt>"}]`
  - `project_id: "<project_id>"`
  - `knowledge_type: "technical"`

This uses the locally-read README content from the scan (already captured in Step 3).
No external crawling is needed — the content is already available from the local filesystem.

Inline ingestion is deterministic: calling it again with the same `project_id` and `title`
will update the existing source, not create a duplicate.

For large scans (20+ projects), batch these calls in groups of 5 with a brief pause between
batches.
```

- [ ] **Step 2: Update Step 11 summary template**

Change `README crawls queued` to `README sources ingested` in the final summary.

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/commands/scan-projects.md
git commit -m "fix: use local README inline ingestion instead of URL crawls in /scan-projects"
```

---

## Task 2: Add Intra-Scan Deduplication and Title Fallback (Issues #6, #7)

**Files:**
- Modify: `integrations/claude-code/commands/scan-projects.md` (Steps 4 and 5)

- [ ] **Step 1: Rewrite Step 4 dedup logic**

Replace the current Step 4 content with:

```markdown
### Step 4 — Deduplicate Against Existing Cortex Projects

1. Call the `find_projects` MCP tool to get all existing Cortex projects.
2. For each project in the scan results, compare its `github_url` (normalized, lowercase)
   against the `github_repo` field of existing Cortex projects.
3. **Fallback matching:** If no `github_url` match is found, also compare by case-insensitive
   `directory_name` against existing project `title` fields. This catches projects that were
   created without a `github_repo` value (e.g., projects created manually via the UI).
4. Mark matches by setting `already_in_cortex: true` and storing the `existing_project_id`.
5. **Intra-scan dedup:** Check for multiple scan results sharing the same non-null `github_url`.
   If found:
   - Keep the first occurrence as the primary.
   - Mark subsequent occurrences with `duplicate_of: "<directory_name of primary>"`.
   - Present these to the user in Step 5 for a decision (create both, skip one, or merge).
6. Count: how many are new, how many already exist, how many are intra-scan duplicates.
```

- [ ] **Step 2: Update Step 5 presentation to show duplicates**

After the "Already in Cortex (will skip)" line in Step 5, add:

```markdown
If intra-scan duplicates were found, show:
\```
Duplicate GitHub URLs detected:
- <name1> and <name2> both point to <github_url>
  → Create both as separate projects? [y/N] Or skip <name2>?
\```

Wait for user input on each duplicate pair before proceeding.
```

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/commands/scan-projects.md
git commit -m "fix: add intra-scan dedup and title-based fallback matching in /scan-projects"
```

---

## Task 3: Add Directory Validation to Scanner Apply Mode (Issue #9)

**Files:**
- Modify: `python/src/server/static/cortex-scanner.py` (apply mode loop)

- [ ] **Step 1: Find the apply function**

Read the apply/config-writing logic in `cortex-scanner.py` — find where it iterates over projects in the payload and writes `.claude/` files.

- [ ] **Step 2: Add directory existence check**

In the apply loop, before writing config files for each project, add:

```python
if not os.path.isdir(project["absolute_path"]):
    results["skipped"].append({
        "project_title": project.get("project_title", "unknown"),
        "absolute_path": project["absolute_path"],
        "reason": "directory not found",
    })
    continue
```

Ensure the `results` dict includes a `"skipped"` key (empty list by default) and that the final JSON output reports skipped count alongside success/failure.

- [ ] **Step 3: Test manually**

Create a payload with a nonexistent path. Run `python3 cortex-scanner.py --apply --payload-file <path>`. Expect: skipped count = 1, no crash, valid JSON output.

- [ ] **Step 4: Commit**

```bash
git add python/src/server/static/cortex-scanner.py
git commit -m "fix: skip missing directories in scanner apply mode instead of crashing"
```

---

## Task 4: REST Crawl Endpoint — Link project_id Upfront (Issue #4)

**Problem:** The REST `POST /api/knowledge-items/crawl` passes `project_id` through to `DocumentStorageOperations`, but the junction table entry (`cortex_project_sources`) is only created *after* crawling completes. If the crawl fails or the server crashes mid-crawl, the project-source link is never created. The inline ingestion endpoint creates a deterministic `source_id` and can upsert upfront — the crawl endpoint should do the same for the junction table.

**Files:**
- Modify: `python/src/server/api_routes/knowledge_api.py` (around line 782-828)

- [ ] **Step 1: After generating source_id, create junction table entry upfront**

In `crawl_knowledge_item()`, after the `source_id` is generated (line 792) and before spawning the background task (line 817), insert:

```python
# Link project upfront so the association exists even if the crawl fails
if request.project_id:
    try:
        supabase_client = get_supabase_client()
        supabase_client.table("cortex_project_sources").upsert(
            {
                "project_id": request.project_id,
                "source_id": source_id,
                "notes": request.knowledge_type or "technical",
                "created_by": "crawl",
            },
            on_conflict="project_id,source_id",
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to pre-link project {request.project_id} to source {source_id}: {e}")
```

- [ ] **Step 2: Verify DocumentStorageOperations still does its upsert too**

The existing link in `source_management_service.py` (line 368-382) does an upsert, so having both is safe — the second call is a no-op. No change needed there.

- [ ] **Step 3: Test**

```bash
cd /home/winadmin/projects/Trinity/cortex/python
uv run pytest tests/ -k "crawl" -v --no-header 2>&1 | tail -20
```

If no existing crawl tests cover this, verify manually:
1. Start a crawl with `project_id` set
2. Check `cortex_project_sources` immediately (before crawl completes)
3. Confirm the junction table row exists

- [ ] **Step 4: Commit**

```bash
git add python/src/server/api_routes/knowledge_api.py
git commit -m "fix: link project_id to source upfront in REST crawl endpoint"
```

---

## Task 5: Crawl State Persistence — Mark Incomplete Jobs on Startup (Issue #1)

**Problem:** Progress state is purely in-memory (`ProgressTracker._progress_states` dict). On server crash/restart, all progress is lost — clients get 404 for their progress IDs with no way to know what happened.

**Approach:** Rather than a full job queue, use the existing `cortex_sources` table. When a crawl starts, write a status marker. On startup, find any sources stuck in "crawling" status and mark them as failed. This gives clients a recoverable state.

**Files:**
- Modify: `python/src/server/api_routes/knowledge_api.py` (crawl start + startup)
- Modify: `python/src/server/main.py` (startup hook)
- Modify: `python/src/server/services/source_management_service.py` (helper)

- [ ] **Step 1: Write "crawling" status to source record when crawl starts**

In `crawl_knowledge_item()` (knowledge_api.py), after generating `source_id` (line 792) and before spawning the background task, upsert a source record:

```python
# Mark source as "crawling" in the database for crash recovery
try:
    supabase_client = get_supabase_client()
    supabase_client.table("cortex_sources").upsert(
        {
            "source_id": source_id,
            "url": str(request.url),
            "display_name": str(request.url),
            "crawl_status": "crawling",
            "metadata": json.dumps({
                "progress_id": progress_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "project_id": request.project_id,
            }),
        },
        on_conflict="source_id",
    ).execute()
except Exception as e:
    logger.warning(f"Failed to write crawl status for source {source_id}: {e}")
```

- [ ] **Step 2: Update source status on crawl completion/failure**

In `_perform_crawl_with_progress()`, after the crawl succeeds (around line 890), the source is already updated by `DocumentStorageOperations`. But on failure (the `except` block around line 896), explicitly mark the source as failed:

```python
# In the except block of _perform_crawl_with_progress, after tracker.error():
try:
    supabase_client = get_supabase_client()
    supabase_client.table("cortex_sources").update(
        {"crawl_status": "failed"}
    ).eq("source_id", URLHandler.generate_unique_source_id(str(request.url))).execute()
except Exception:
    pass  # Best effort
```

- [ ] **Step 3: Add startup recovery in main.py**

In `python/src/server/main.py`, find the `@app.on_event("startup")` handler (or the lifespan function). Add a call to mark stale crawls:

```python
# Mark any sources stuck in "crawling" status as failed (crash recovery)
try:
    from .config.database import get_supabase_client
    client = get_supabase_client()
    result = client.table("cortex_sources").update(
        {"crawl_status": "failed"}
    ).eq("crawl_status", "crawling").execute()
    if result.data:
        logger.warning(f"Marked {len(result.data)} stale crawls as failed (server restart recovery)")
except Exception as e:
    logger.warning(f"Failed to recover stale crawls on startup: {e}")
```

- [ ] **Step 4: Test**

1. Start a crawl
2. Kill the server mid-crawl (`docker compose restart cortex-server`)
3. After restart, query: `SELECT source_id, crawl_status FROM cortex_sources WHERE crawl_status = 'failed'`
4. Confirm the interrupted crawl is marked as failed

- [ ] **Step 5: Commit**

```bash
git add python/src/server/api_routes/knowledge_api.py python/src/server/main.py
git commit -m "fix: persist crawl status to DB and recover stale crawls on startup"
```

---

## Task 6: Reject Crawls When Queue Is Full (Issue #10)

**Problem:** The semaphore limits concurrent execution to 3, but `asyncio.create_task()` still creates all background tasks immediately. 17 simultaneous requests create 17 tasks — 3 run and 14 wait on the semaphore, all consuming memory and holding state. This likely caused the OOM crash.

**Approach:** Add a queue depth check before accepting new crawls. If more than N crawls are pending (waiting + running), reject with 429 Too Many Requests.

**Files:**
- Modify: `python/src/server/api_routes/knowledge_api.py` (around lines 43-58 and 764)

- [ ] **Step 1: Add a queue depth counter alongside the semaphore**

Near the existing semaphore (line 54), add:

```python
MAX_QUEUED_CRAWLS = 6  # Max total crawls (running + waiting). 3 run, 3 can queue.
_queued_crawl_count = 0
_crawl_count_lock = asyncio.Lock()
```

- [ ] **Step 2: Add guard in the crawl endpoint**

At the top of `crawl_knowledge_item()`, before validation:

```python
global _queued_crawl_count
async with _crawl_count_lock:
    if _queued_crawl_count >= MAX_QUEUED_CRAWLS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many crawls in progress ({_queued_crawl_count}). "
                   f"Maximum {MAX_QUEUED_CRAWLS} allowed. Try again shortly.",
        )
    _queued_crawl_count += 1
```

- [ ] **Step 3: Decrement counter when crawl finishes**

In `_perform_crawl_with_progress()`, in the `finally` block (around line 916), add:

```python
global _queued_crawl_count
async with _crawl_count_lock:
    _queued_crawl_count = max(0, _queued_crawl_count - 1)
```

- [ ] **Step 4: Test**

Submit 7+ crawl requests rapidly. Confirm first 6 are accepted and 7th returns 429.

- [ ] **Step 5: Commit**

```bash
git add python/src/server/api_routes/knowledge_api.py
git commit -m "fix: reject crawls when queue is full to prevent OOM crashes"
```

---

## Task 7: Batch Progress Endpoint (Issue #8)

**Problem:** After queuing multiple crawls, checking each progress_id individually is tedious. No aggregate view exists.

**Approach:** Add `GET /api/progress/active` that returns all in-flight progress entries. The `ProgressTracker.list_active()` class method already exists (line 61 of progress_tracker.py).

**Files:**
- Modify: `python/src/server/api_routes/progress_api.py`

- [ ] **Step 1: Read current progress_api.py**

Read `python/src/server/api_routes/progress_api.py` to understand existing endpoints.

- [ ] **Step 2: Add GET /api/progress/active endpoint**

```python
@router.get("/progress/active")
async def get_active_progress():
    """Return all active progress entries (running + recently completed)."""
    from ..utils.progress.progress_tracker import ProgressTracker
    active = ProgressTracker.list_active()
    return {
        "success": True,
        "count": len(active),
        "operations": [
            {
                "progress_id": pid,
                "status": state.get("status", "unknown"),
                "progress": state.get("progress", 0),
                "type": state.get("type", "unknown"),
                "url": state.get("url", state.get("title", "")),
                "start_time": state.get("start_time"),
            }
            for pid, state in active.items()
        ],
    }
```

- [ ] **Step 3: Verify it doesn't conflict with existing `GET /api/progress/{operation_id}`**

The `{operation_id}` path parameter is a UUID string. The literal path `/progress/active` should match before the parameterized route if registered first. Verify the route order in the router.

- [ ] **Step 4: Test**

```bash
# Start a crawl, then immediately hit the active endpoint:
curl -s http://localhost:8181/api/progress/active | python3 -m json.tool
```

- [ ] **Step 5: Commit**

```bash
git add python/src/server/api_routes/progress_api.py
git commit -m "feat: add GET /api/progress/active endpoint for batch progress monitoring"
```

---

## Task 8: MCP Session Recovery Guidance in Skill (Issue #3)

**Problem:** When the Cortex server restarts mid-scan, all MCP sessions are invalidated. MCP tool calls fail with "No valid session ID provided." The user has no guidance on how to recover.

**Approach:** Add recovery instructions to the skill so Claude Code knows what to do. Also make the scan-projects skill's critical path (project creation) more resilient.

**Files:**
- Modify: `integrations/claude-code/commands/scan-projects.md` (add error handling section)

- [ ] **Step 1: Add error recovery section after Step 2 (Download Scanner Script)**

After Step 2, add:

```markdown
### Error Recovery — MCP Connection Issues

If at any point MCP tool calls fail with "session" errors, "connection refused", or
timeout errors:

1. Tell the user: "The Cortex MCP connection was lost (server may have restarted).
   Please restart Claude Code to re-establish the MCP session, then re-run /scan-projects."
2. STOP. Do not attempt to fall back to REST API calls — the MCP tools have different
   behavior (deterministic IDs, project linking) that REST endpoints may not replicate.
3. If the scan was partially completed (some projects already created), re-running
   /scan-projects is safe — Step 4 deduplication will detect already-created projects.
```

- [ ] **Step 2: Commit**

```bash
git add integrations/claude-code/commands/scan-projects.md
git commit -m "docs: add MCP session recovery guidance to /scan-projects skill"
```

---

## Task 9: Update Journey Test Phase 5

**Files:**
- Modify: `docs/userJourneys/projectScannerJourney.md` (Phase 5, lines 333-359)

- [ ] **Step 1: Rewrite Phase 5 for inline ingestion**

Replace the current Phase 5 with:

```markdown
## Phase 5 — Verify Knowledge Base Ingestion

### 5.1 Inline README Ingestion via `manage_rag_source` MCP

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 5.1a | `manage_rag_source` called | One call per created project with a `readme_excerpt` | |
| 5.1b | Source type is inline | `source_type: "inline"`, NOT `"url"` | |
| 5.1c | Content from local disk | `documents` contains locally-read README content | |
| 5.1d | Batched for large scans | Calls made in groups of 5 (20+ projects) | |
| 5.1e | Knowledge sources created | Sources appear in Cortex UI under Knowledge | |
| 5.1f | Project linking | Each source is linked to its project (`project_id` set) | |

### 5.2 Verify in Cortex UI

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 5.2a | Sources listed | README sources visible for created projects | |
| 5.2b | Ingestion status | Shows completed (inline is near-instant) | |
| 5.2c | No external crawls | No URL-based sources created for READMEs | |

### 5.3 RAG Search Test

> "Search the Cortex knowledge base for information about recipe management."

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 5.3a | Results returned | RAG search finds content from RecipeRaiders README | |
```

- [ ] **Step 2: Update the Test Results Summary table**

Update the Phase 5 row check count and recalculate the total.

- [ ] **Step 3: Commit**

```bash
git add docs/userJourneys/projectScannerJourney.md
git commit -m "docs: update journey test Phase 5 for inline README ingestion"
```

---

## Task 10: Log All Findings in Journey Test

**Files:**
- Modify: `docs/userJourneys/projectScannerJourney.md` (Bugs Found table)

- [ ] **Step 1: Add rows to the Bugs Found table**

```markdown
| 1 | 5 | WIN_AI_PC_WSL | Critical | Crawl queue state was in-memory only — lost on server restart | Fixed: T5 |
| 2 | 5 | WIN_AI_PC_WSL | Critical | Recursive crawling followed hundreds of unrelated GitHub links for README crawls | Fixed: T1 (replaced with inline) |
| 3 | All | WIN_AI_PC_WSL | High | MCP session breaks on server restart — all tool calls fail | Mitigated: T8 (recovery guidance) |
| 4 | 5 | WIN_AI_PC_WSL | Medium | REST crawl endpoint didn't link project_id until after crawl completed | Fixed: T4 |
| 5 | 5 | WIN_AI_PC_WSL | Critical | Local README ingestion not used — unnecessary external crawls | Fixed: T1 |
| 6 | 3 | WIN_AI_PC_WSL | Medium | No dedup within scan results — same GitHub URL created twice | Fixed: T2 |
| 7 | 3 | WIN_AI_PC_WSL | Medium | No title-based fallback dedup for projects without github_repo | Fixed: T2 |
| 8 | 5 | WIN_AI_PC_WSL | Medium | No bulk progress monitoring — had to check 17 IDs individually | Fixed: T7 |
| 9 | 4 | WIN_AI_PC_WSL | Low | PostmanFastAPIDemo directory not found during apply step | Fixed: T3 |
| 10 | 5 | WIN_AI_PC_WSL | Critical | 17 simultaneous crawls overwhelmed server causing OOM crash | Fixed: T6 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/userJourneys/projectScannerJourney.md
git commit -m "docs: log all findings from scan-projects journey test"
```

---

## Execution Dependencies

```
T1 (inline ingestion) ──────┐
T2 (dedup improvements) ────┤
T3 (dir validation) ────────┤── all independent, parallelizable
T4 (project_id upfront) ────┤
T5 (crawl persistence) ─────┤
T6 (queue depth limit) ─────┤
T7 (batch progress) ────────┤
T8 (MCP recovery guidance) ─┘
                             │
T9 (journey test Phase 5) ──┤── depends on T1
T10 (log findings) ─────────┘── depends on all above (references fix status)
```

T1-T8 can all be parallelized. T9 depends on T1. T10 should run last.

## Post-Execution

After all tasks complete:
1. Rebuild Docker: `docker compose up --build -d`
2. Run backend tests: `cd python && uv run pytest tests/ -v --no-header`
3. Re-run the journey test from Phase 0
