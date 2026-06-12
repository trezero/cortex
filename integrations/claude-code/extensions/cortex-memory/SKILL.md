---
name: cortex-memory
description: Manage long-term knowledge memory via Cortex RAG. Ingest project documentation, search semantically across projects, sync after changes, manage shared cross-project knowledge, and coordinate tasks. Use when the user says "cortex", "knowledge base", "ingest docs", "search docs", "sync docs", or needs deep project context beyond what MEMORY.md provides.
---

# Cortex Memory — Long-Term Knowledge Management

Bridges Claude Code's native memory with Cortex's RAG knowledge base for semantic search across unlimited documentation, cross-project knowledge sharing, and multi-agent collaboration.

**Invocation:** `/cortex-memory [mode] [arguments]`

Examples:
- `/cortex-memory` — Status overview + freshness check
- `/cortex-memory ingest` — Ingest project docs into Cortex
- `/cortex-memory ingest docs/` — Ingest from specific directory
- `/cortex-memory sync` — Re-ingest changed docs
- `/cortex-memory search subscription gates` — Search project knowledge
- `/cortex-memory search-all firebase auth patterns` — Search all projects
- `/cortex-memory shared add https://firebase.google.com/docs` — Add shared knowledge
- `/cortex-memory shared list` — List shared knowledge sources
- `/cortex-memory ecosystem` — Show all ecosystem projects' Cortex status
- `/cortex-memory tasks` — List project tasks
- `/cortex-memory forget` — Remove project from Cortex

---

## Phase 0: Health Check & State Load (all modes)

Run this before every operation.

### 0a. Verify Cortex is reachable

```
health_check()
```

If Cortex is down or `api_service` is false:
> "Cortex server is not reachable. Check that it's running on the configured host. The cortex MCP server must be configured in .mcp.json or ~/.claude/mcp.json."

Stop here if unhealthy.

### 0b. Check extension sync freshness

Read `.claude/cortex-state.json`. If `last_extension_sync` is missing or older than 24 hours:
> "Extensions are out of sync. Running extension sync first..."

Run `/cortex-extension-sync` before continuing.

### 0c. Load state files

Read these if they exist (don't fail if missing — some modes create them):

- **Project state:** `.claude/cortex-state.json` in the current project
- **Global state:** `~/.claude/cortex-global.json`

### 0d. Parse the mode

| Argument | Mode |
|----------|------|
| *(none)* or `status` | STATUS |
| `ingest [dir]` | INGEST |
| `sync` | SYNC |
| `search <query>` | SEARCH (project-scoped) |
| `search-all <query>` | SEARCH-ALL (unscoped) |
| `shared add <url>` | SHARED-ADD-URL |
| `shared add-docs <dir>` | SHARED-ADD-DOCS |
| `shared search <query>` | SHARED-SEARCH |
| `shared list` | SHARED-LIST |
| `tasks` | TASKS-LIST |
| `task create <title>` | TASK-CREATE |
| `task update <id> <status>` | TASK-UPDATE |
| `project` | PROJECT-INFO |
| `ecosystem` | ECOSYSTEM |
| `forget` | FORGET |

---

## INGEST Mode

First-time ingestion of project documentation into Cortex.

### Phase 1: Determine Project Identity

```bash
git remote get-url origin 2>/dev/null || echo "no-remote"
```

Get the project directory name as fallback:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

Check if an Cortex project already exists for this repo:
```
find_projects(query="<repo-name>")
```

**If found:** Use the existing project. Extract `project_id`.

**If not found:** Create one:
```
manage_project(action="create", title="<repo-name>", github_repo="<remote-url>")
```

Save the `project_id`.

**If `.claude/cortex-state.json` already exists with a source_id:** Warn the user:
> "This project already has docs in Cortex (source: src-xxx, synced <date>). Running ingest again will create a duplicate. Use `/cortex-memory sync` to update instead, or `/cortex-memory forget` first to start fresh."

Stop unless the user explicitly wants to proceed.

### Phase 2: Discover Documents

Scan for documents to ingest:

1. **Primary directory:** All `.md` files in `docs/` (or user-specified directory)
   ```
   Glob: docs/**/*.md (or <specified-dir>/**/*.md)
   ```

2. **Extra files:** Look for these in the project root and parent directory:
   - `CLAUDE.md`
   - `README.md`
   - Parent `CLAUDE.md` (e.g., `../CLAUDE.md` for monorepo setups)

3. **Exclude:** Skip any files matching:
   - `node_modules/`
   - `.git/`
   - Files larger than 500KB (likely generated or binary)

Report discovery to user:
> "Found X documents to ingest:
> - docs/ : Y files
> - CLAUDE.md: found
> - README.md: found
> Total: ~Z KB. Proceed?"

Wait for user confirmation.

### Phase 3: Read & Build Payload

For each discovered file:

1. Check the file's line count:
   ```bash
   wc -l <filepath> | awk '{print $1}'
   ```

2. Read the full file content:
   - **For files ≤ 1500 lines:** Use the Read tool directly (no offset/limit needed).
   - **For files > 1500 lines:** Read in 1500-line chunks using the Read tool's `offset` and `limit` parameters, then concatenate all chunks into the complete content string:
     ```
     Read(file_path=<filepath>, limit=1500)                  # lines 1–1500
     Read(file_path=<filepath>, offset=1500, limit=1500)     # lines 1501–3000
     Read(file_path=<filepath>, offset=3000, limit=1500)     # lines 3001–4500
     # ... continue until offset ≥ total line count
     ```
     Strip the line-number prefix from each chunk (format: `   N→`) before concatenating.

   **CRITICAL:** Never use the Read tool without `limit` on a file before confirming it is ≤ 1500 lines. The default 2000-line limit silently truncates larger files, resulting in partial indexing.

3. Compute MD5 hash of the content:
   ```bash
   md5sum <filepath> 2>/dev/null | cut -d' ' -f1 || md5 -q <filepath> 2>/dev/null
   ```

4. Add to documents array:
   ```json
   {"title": "<filename>", "content": "<full content>", "path": "<relative path>"}
   ```

Use sub-agents to read files in parallel batches for speed (groups of 5-10 files). Each sub-agent must follow the line-count check and chunked reading steps above.

### Phase 4: Ingest via Cortex

```
manage_rag_source(
    action="add",
    source_type="inline",
    title="<repo-name> Documentation",
    documents=<documents array as list>,
    tags=["<repo-name>", "project-docs"],
    project_id="<cortex-project-id>",
    knowledge_type="technical",
    extract_code_examples=true
)
```

**Important:** Pass `documents` as a native list, not a JSON string. Cortex accepts both formats (fixed in commit 8337ec3).

Save `progress_id` and `source_id` from the response.

### Phase 5: Poll for Completion

```
rag_check_progress(progress_id="<progress_id>")
```

Poll every 5 seconds. Report progress:
> "Ingesting... 19/42 documents processed (45%)"

Continue until `status` is `"completed"`, `"failed"`, or `"error"`.

**If failed:** Report the error details and stop. Suggest checking Cortex server logs.

**If progress_id returns 404:** The operation completed and progress data expired (~30s TTL). Check `rag_get_available_sources()` to verify the source was created.

### Phase 6: Verify Ingestion

Run a test search to confirm content is indexed:
```
rag_search_knowledge_base(
    query="project architecture overview",
    project_id="<cortex-project-id>",
    match_count=3
)
```

If results are returned, ingestion is confirmed working.

### Phase 7: Save State

**7a.** Write `.claude/cortex-state.json`:
```json
{
  "cortex_project_id": "<project-id>",
  "cortex_project_title": "<repo-name>",
  "git_remote": "<remote-url>",
  "sources": {
    "project-docs": {
      "source_id": "<source-id>",
      "title": "<repo-name> Documentation",
      "last_synced": "<ISO timestamp>",
      "doc_count": <number>,
      "directories": ["docs/"],
      "extra_files": ["CLAUDE.md", "README.md"],
      "file_hashes": {
        "<relative-path>": "<md5-hash>",
        ...
      }
    }
  },
  "created_at": "<ISO timestamp>"
}
```

**7b.** Ensure `.claude/cortex-state.json` is in `.gitignore`:
```bash
grep -q "cortex-state.json" .gitignore 2>/dev/null || echo ".claude/cortex-state.json" >> .gitignore
```

**7c.** Update MEMORY.md — add or update an "Cortex Knowledge Base" section:
```markdown
## Cortex Knowledge Base
- Project ID: <project-id>
- Source: "<repo-name> Documentation" (<source-id>), <N> docs, synced <date>
- Search: `rag_search_knowledge_base(query="...", project_id="<project-id>")`
```

### Phase 8: Final Report

```
## Cortex Memory — Ingestion Complete

**Project:** <repo-name>
**Cortex Project ID:** <project-id>
**Source ID:** <source-id>
**Documents ingested:** <count>
**Chunks stored:** <from progress results>
**Code examples extracted:** <from progress results>

### What's indexed
- docs/ (<N> files covering: <brief topic summary>)
- CLAUDE.md: project instructions
- README.md: project overview

### How to use
- `/cortex-memory search <query>` — search this project's knowledge
- `/cortex-memory search-all <query>` — search all projects
- `/cortex-memory sync` — re-sync after doc changes
- `/cortex-memory status` — check freshness
```

If any files required chunked reading (> 1500 lines), confirm in the report that all chunks were fully read and the complete content was indexed — do NOT note truncation.

---

## SYNC Mode

Re-ingest project docs after changes. Uses delete + re-add since Cortex inline sync is not reliable.

### Phase 1: Load & Validate State

Read `.claude/cortex-state.json`.

If missing:
> "No Cortex state found for this project. Run `/cortex-memory ingest` first."

### Phase 2: Detect Changes

1. Scan the same directories and files listed in the state config
2. Compute current MD5 hashes:
   ```bash
   md5sum <filepath> 2>/dev/null | cut -d' ' -f1 || md5 -q <filepath> 2>/dev/null
   ```
3. Compare to stored hashes
4. Categorize each file: **unchanged**, **modified**, **added** (new file), **removed** (file deleted)

Report:
> "Changes detected since last sync (<date>):
> - Modified: 3 files
> - Added: 1 file
> - Removed: 0 files
> Proceed with re-sync?"

If no changes detected:
> "All documents are up to date. Last synced: <date>."

### Phase 3: Re-ingest

**Warning:** Sync uses delete + re-add, which means there's a brief window where the knowledge base has no content for this project. If the delete succeeds but re-add fails, run `/cortex-memory ingest` to recover.

1. Re-read all docs first (same as Ingest Phase 3) — read BEFORE deleting to ensure content is ready

2. Delete old source:
   ```
   manage_rag_source(action="delete", source_id="<old-source-id>")
   ```

3. Re-ingest immediately (same as Ingest Phase 4):
   ```
   manage_rag_source(action="add", ...)
   ```

4. Poll for completion (same as Ingest Phase 5)

### Phase 4: Update State

- Update `.claude/cortex-state.json` with **new** source_id, timestamp, and hashes
  (source_id changes on every delete + re-add)
- Update MEMORY.md Cortex Registry section with new source_id

Report:
> "Sync complete. <N> documents re-ingested. New source ID: <source-id>."

---

## SEARCH Mode

Semantic search across ingested documentation.

### For `search <query>` (project-scoped)

```
rag_search_knowledge_base(
    query="<query>",
    project_id="<cortex-project-id>",
    match_count=5,
    return_mode="pages"
)
```

Get `cortex_project_id` from `.claude/cortex-state.json`. If state file is missing, check Cortex directly:
```
find_projects(query="<repo-name>")
```

### For `search-all <query>` (unscoped)

```
rag_search_knowledge_base(
    query="<query>",
    match_count=10,
    return_mode="pages"
)
```

No `project_id` — searches across all projects and shared knowledge.

### Present Results

Show as a table:
```
## Search Results for "<query>"

| # | Section Title | Similarity | Words | Chunks | Source ID |
|---|--------------|------------|-------|--------|-----------|
| 1 | subscriptions.md | 0.89 | 1,250 | 3 | src-xxx |
| 2 | userLogic.md | 0.72 | 3,400 | 5 | src-xxx |
```

Then ask:
> "Want me to read the full content of any of these pages?"

If yes, use:
```
rag_read_full_page(page_id="<page-id-from-results>")
```

### Code Examples (automatic supplement)

Also search for code examples:
```
rag_search_code_examples(
    query="<query>",
    project_id="<cortex-project-id>",
    match_count=3
)
```

If code results found, show them below the page results.

---

## STATUS Mode

Default mode when `/cortex-memory` is called with no arguments.

### Phase 1: Load State

Read `.claude/cortex-state.json`. If missing:
> "No Cortex state found for this project. Run `/cortex-memory ingest` to get started."

### Phase 2: Check Freshness

1. Scan current docs and compute MD5 hashes
2. Compare to stored hashes
3. Count: changed, added, removed

### Phase 3: Live Verification

Query Cortex to verify source still exists:
```
rag_list_pages_for_source(source_id="<source-id>")
```

### Phase 4: Load Global State

Read `~/.claude/cortex-global.json` for shared knowledge info.

### Phase 5: Report

```
## Cortex Memory Status

**Project:** <repo-name> (<project-id>)
**Source:** <source-title> (<source-id>)
**Last synced:** <date> (<relative time>)
**Documents:** <N> indexed
**Freshness:** <N> files changed since last sync
  - <filepath> (modified|added|removed)
  - ...

**Shared Knowledge:** <N> sources
  - <source-title> (<source-id>)
  - ...

**Suggestion:** <action based on state>
```

Suggestions:
- If stale: "Run `/cortex-memory sync` to update."
- If source missing from Cortex: "Source not found in Cortex. Run `/cortex-memory ingest` to re-create."
- If fresh: "Knowledge base is up to date."

---

## SHARED Mode

Manage cross-project shared knowledge. Uses a dedicated "Shared Knowledge Base" project in Cortex.

### `shared add <url>` — Add URL-based shared knowledge

1. Get or create shared project:
   - Read `~/.claude/cortex-global.json` for `shared_project_id`
   - If missing, create:
     ```
     manage_project(action="create", title="Shared Knowledge Base",
         description="Cross-project knowledge accessible from any project")
     ```
   - Save `shared_project_id` to `~/.claude/cortex-global.json`

2. Ingest the URL:
   ```
   manage_rag_source(
       action="add",
       source_type="url",
       title="<extracted domain or user label>",
       url="<url>",
       project_id="<shared-project-id>",
       tags=["shared", "<domain>"]
   )
   ```

3. Poll for completion via `rag_check_progress`

4. Update `~/.claude/cortex-global.json` with new source entry

### `shared add-docs <dir>` — Add local docs as shared knowledge

Same as project ingest flow, but targets the shared knowledge project instead of the current project's Cortex project.

### `shared search <query>`

```
rag_search_knowledge_base(
    query="<query>",
    project_id="<shared-project-id>",
    match_count=5
)
```

### `shared list`

```
rag_get_available_sources()
```

Filter results to sources whose `source_id` matches entries in `~/.claude/cortex-global.json`.

Display:
```
## Shared Knowledge Sources

| # | Title | Source ID | Pages | Last Synced |
|---|-------|----------|-------|-------------|
| 1 | Firebase Documentation | src-xxx | 1,200 | 2026-03-01 |
| 2 | Next.js Documentation | src-yyy | 800 | 2026-03-01 |
```

---

## TASKS Mode

Manage Cortex project tasks for multi-agent coordination.

### `tasks` — List tasks

```
find_tasks(project_id="<cortex-project-id>")
```

Display grouped by status:

```
## Project Tasks

### Doing
- [task-id] Task title (assignee)

### To Do
- [task-id] Task title

### Review
- [task-id] Task title (assignee)

### Done
- [task-id] Task title
```

### `task create <title>`

```
manage_task(action="create",
    project_id="<cortex-project-id>",
    title="<title>",
    status="todo",
    assignee="User"
)
```

Report: "Task created: <title> (ID: <task-id>)"

### `task update <id> <status>`

Valid statuses: `todo`, `doing`, `review`, `done`

```
manage_task(action="update", task_id="<id>", status="<status>")
```

Report: "Task <id> updated to <status>."

---

## PROJECT Mode

View or manage the Cortex project for the current repo.

### No existing project

If `.claude/cortex-state.json` is missing:
> "No Cortex project linked to this repo. Run `/cortex-memory ingest` to create one, or use `manage_project` manually."

### Existing project

```
find_projects(project_id="<cortex-project-id>")
```

Display project details including title, description, github_repo, features.

---

## ECOSYSTEM Mode

Show status of all RecipeRaiders ecosystem projects in Cortex. No arguments needed.

### Phase 1: Load Global State

Read `~/.claude/cortex-global.json`. If missing:
> "No ecosystem configuration found. Run `/cortex-memory ingest` in each project first, or set up the ecosystem via the multi-project rollout process."

### Phase 2: Query Cortex for All Projects

For each project in `ecosystem_projects`:
```
find_projects(project_id="<project-id>")
```

Also check the shared knowledge project:
```
find_projects(project_id="<shared-project-id>")
```

### Phase 3: Check Local State for Current Project

If the current working directory matches one of the ecosystem projects, read its `.claude/cortex-state.json` and run a freshness check (compare file hashes).

### Phase 4: Display Ecosystem Dashboard

```
## RecipeRaiders Ecosystem — Cortex Status

### Shared Knowledge
| Source | Docs | Last Synced | Status |
|--------|------|-------------|--------|
| RecipeRaiders Ecosystem Documentation | 2 | <date> | <fresh/stale> |

### Projects
| Project | Cortex ID | Docs | Last Synced | Status |
|---------|-----------|------|-------------|--------|
| RecipeRaiders (main) | 2d747998... | 51 | <date> | <fresh/stale/unknown> |
| reciperaiders-spa | d452583d... | 2 | <date> | <fresh/stale/unknown> |
| reciperaiders-repdash | 9b18cc38... | 3 | <date> | <fresh/stale/unknown> |
| RecipeRaiders-Marketing | 5ba91517... | 2 | <date> | <fresh/stale/unknown> |

### Current Project: <name>
<Freshness details if available>
```

**Status values:**
- **fresh**: File hashes match stored hashes (can only check if in that project's directory)
- **stale**: File hashes differ — run `/cortex-memory sync`
- **unknown**: Not in this project's directory, can't check local files
- **missing**: Cortex project or source not found

### Phase 5: Suggestions

Based on ecosystem state, suggest:
- If any projects are stale: "Run `/cortex-memory sync` in <project-dir> to update."
- If shared knowledge is stale: "Run `/cortex-memory shared sync` to update ecosystem docs."
- If a project has no cortex state: "Run `/cortex-memory ingest` in <project-dir> to set up."

---

## FORGET Mode

Remove all project knowledge from Cortex.

### Phase 1: Confirm

> "This will permanently remove all project documentation from Cortex's knowledge base. The Cortex project and tasks will be preserved unless you also want to delete those. Proceed?"

Wait for explicit user confirmation.

### Phase 2: Delete Source

```
manage_rag_source(action="delete", source_id="<source-id>")
```

### Phase 3: Optionally Delete Project

Ask:
> "Also delete the Cortex project (removes tasks, documents, versions too)?"

If yes:
```
manage_project(action="delete", project_id="<cortex-project-id>")
```

### Phase 4: Clean Up State

1. Delete `.claude/cortex-state.json`
2. Remove Cortex Registry section from MEMORY.md

Report: "Project knowledge removed from Cortex."

---

## Important Notes

### Query Best Practices
- Keep search queries **short and focused**: 2-5 keywords
- Good: `"subscription gates"`, `"firebase auth"`, `"deploy staging"`
- Bad: `"how do subscription gates work in the payment system for premium users"`
- For multi-concept searches, run multiple focused queries instead of one broad one

### State File Locations
- **Per-project:** `.claude/cortex-state.json` (gitignored, created by ingest)
- **Global:** `~/.claude/cortex-global.json` (shared knowledge registry)
- **MEMORY.md:** Updated with Cortex IDs for quick reference in future sessions

### Cortex Constraints
- Inline sync = delete + re-add (source_id changes each time)
- Chunking is ~5000 characters with markdown header preservation
- Progress data expires ~30 seconds after completion
- Documents parameter accepts both native list and JSON string

### Error Recovery
- If Cortex is unreachable, all modes fail gracefully with a clear message
- If source_id in state file doesn't match Cortex, suggest re-ingest
- If progress polling returns 404, check `rag_get_available_sources()` to verify
- If ingestion fails, the old source (if any) was already deleted — re-run ingest to recover

### Multi-Agent Awareness
All Cortex data is shared across agents. When this Claude Code instance ingests or modifies data, other agents (Cursor, Windsurf, other Claude instances) see the changes immediately. Use Cortex tasks for coordinating work across agents.
