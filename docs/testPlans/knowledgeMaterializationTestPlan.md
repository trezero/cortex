# Knowledge Materialization — User Test Plan

## Overview

This test plan validates the Knowledge Materialization feature end-to-end from a user's perspective. The feature allows agents to search the global Vector DB/RAG archive, synthesize results via LLM, and write permanent Markdown documentation into project repos at `.cortex/knowledge/`.

## Prerequisites

- Cortex stack running and accessible in a browser (default: `http://localhost:3737`)
- At least one project configured in Cortex with knowledge sources already crawled
- Claude Code CLI installed and connected to Cortex MCP
- A test project linked to Cortex (or create a new one during testing)
- Access to the test project's filesystem to inspect generated files

---

## Phase 1: Database Migration

Verify the materialization history table exists in your Supabase instance.

### 1.1 Check table exists

1. Open your Supabase dashboard (or use the SQL editor)
2. Look for the `cortex_materialization_history` table

**Expected:** The table exists with columns: `id`, `project_id`, `project_path`, `topic`, `filename`, `file_path`, `source_ids`, `original_urls`, `synthesis_model`, `word_count`, `status`, `access_count`, `last_accessed_at`, `materialized_at`, `updated_at`, `metadata`.

### 1.2 Check function exists

In the Supabase SQL editor, run:
```sql
SELECT proname FROM pg_proc WHERE proname = 'increment_access_count';
```

**Expected:** One row returned — the `increment_access_count` function exists.

> **If the table doesn't exist:** Run the migration at `migration/0.1.0/018_add_materialization_history.sql` in your Supabase SQL editor.

---

## Phase 2: UI — Materialized Toggle Button

### 2.1 Navigate to Knowledge Base

1. Open the Cortex web UI
2. Click **Knowledge** in the left navigation

**Expected:** The Knowledge Base page loads showing your existing knowledge items (or an empty state).

### 2.2 Locate the Materialized toggle

1. Look at the filter bar below the "Knowledge Base" heading
2. Find the button with a sparkle icon labeled **Materialized**

**Expected:** The button appears in the filter row between the type filter toggle group and the project dropdown. It has a ghost/outline style with gray text when inactive.

### 2.3 Toggle Materialized view ON

1. Click the **Materialized** button

**Expected:**
- The button changes to a purple-highlighted style (purple background tint, purple text)
- The main content area switches from the knowledge cards/table to the Materialized list view
- If no materializations exist yet, the message reads: "No materialized knowledge files yet. Agents will automatically materialize knowledge when they detect gaps in local context."

### 2.4 Toggle Materialized view OFF

1. Click the **Materialized** button again

**Expected:**
- The button returns to its gray/inactive style
- The knowledge cards/table view reappears

---

## Phase 3: MCP Tool — Materialize Knowledge

This is the core test. You will use Claude Code to materialize knowledge from the Vector DB into a project repo.

### 3.1 Verify MCP tools are available

1. Open Claude Code in your test project directory
2. Check that the Cortex MCP connection is active

**Expected:** The following materialization tools should be available:
- `cortex:materialize_knowledge`
- `cortex:find_materializations`
- `cortex:manage_materialization`

### 3.2 Materialize a topic

1. In Claude Code, ask:
   > "Use materialize_knowledge to materialize knowledge about [TOPIC] for this project"

   Replace `[TOPIC]` with a topic that exists in your knowledge base (e.g., "React hooks", "FastAPI middleware", "Supabase RLS policies" — whatever you've crawled).

2. Provide the project_id and project_path when prompted (or if the agent already has context from Cortex config, it may fill these in automatically).

**Expected:**
- The tool executes (may take 10-60 seconds depending on LLM synthesis)
- Returns a JSON response with:
  - `"success": true`
  - `"file_path"` — e.g., `.cortex/knowledge/react-hooks.md`
  - `"filename"` — e.g., `react-hooks.md`
  - `"word_count"` — a positive number
  - `"summary"` — a one-sentence description
  - `"materialization_id"` — a UUID

### 3.3 Verify the file was written

1. In your terminal, navigate to the test project directory
2. List the knowledge directory:
   ```bash
   ls .cortex/knowledge/
   ```

**Expected:** A Markdown file matching the topic slug exists (e.g., `react-hooks.md`).

### 3.4 Inspect the materialized file

1. Open the generated file:
   ```bash
   cat .cortex/knowledge/<filename>.md
   ```

**Expected:** The file contains:
- **YAML frontmatter** between `---` delimiters with:
  - `cortex_source: vector_archive`
  - `materialized_at:` — ISO timestamp
  - `topic:` — the normalized topic (lowercase)
  - `source_urls:` — list of URLs from the knowledge base
  - `source_ids:` — list of source IDs
  - `synthesis_model:` — e.g., `openai:gpt-4.1-nano`
  - `materialization_id:` — UUID matching the API response
- **Markdown content** with:
  - An H1 title at the top
  - Logical headers (##, ###)
  - Synthesized, deduplicated content (not raw chunks)
  - Code blocks with language tags where relevant
  - A `## Sources` section at the end

### 3.5 Verify the index was updated

1. Check the auto-generated index:
   ```bash
   cat .cortex/index.md
   ```

**Expected:**
- Header: `# .cortex Knowledge Index`
- "Auto-generated by Cortex. Do not edit manually."
- A `## Materialized Knowledge` section
- A list entry linking to the new file with topic name, date, and source URLs

---

## Phase 4: Duplicate Detection

### 4.1 Attempt to materialize the same topic again

1. In Claude Code, ask to materialize the exact same topic again:
   > "Use materialize_knowledge to materialize knowledge about [SAME TOPIC]"

**Expected:**
- The tool returns quickly (no new synthesis performed)
- `"success": true`
- The same `file_path`, `filename`, and `materialization_id` as before
- No new file created — only one file in `.cortex/knowledge/` for this topic

### 4.2 Verify case-insensitive deduplication

1. Try the same topic with different casing:
   > "Use materialize_knowledge to materialize knowledge about [SAME TOPIC IN ALL CAPS]"

**Expected:** Returns the existing record, not a duplicate. Topics are normalized to lowercase.

---

## Phase 5: UI — Viewing Materialization History

### 5.1 View materialization in the UI

1. Return to the Cortex web UI → Knowledge page
2. Click the **Materialized** toggle button

**Expected:** The materialization you just created appears in the list with:
- **Topic name** in white text
- **Status badge** — green "active" badge
- **File path** — e.g., `.cortex/knowledge/react-hooks.md`
- **Word count** — matches what was returned
- **Access count** — 1 or 2 (depending on duplicate test)
- **Materialized date** — today's date
- **Source URL** — shown if available (e.g., "from https://...")
- **Delete button** — red text on the right

### 5.2 Filter by project

1. If you have multiple projects, select a specific project from the project dropdown
2. With the **Materialized** toggle active, observe the list

**Expected:** Only materializations for the selected project are shown. Switching to "All Projects" shows all materializations.

### 5.3 Delete a materialization from the UI

1. Click the **Delete** button on a materialization entry

**Expected:**
- The entry disappears from the list
- The file is removed from `.cortex/knowledge/` on disk
- The `.cortex/index.md` is updated (entry removed)

Verify on disk:
```bash
ls .cortex/knowledge/
cat .cortex/index.md
```

---

## Phase 6: MCP Tools — Find and Manage

### 6.1 Find materializations

1. In Claude Code, ask:
   > "Use find_materializations to list all materializations for this project"

**Expected:** Returns a JSON object with `items` array containing all materialization records for the project, each with full metadata (topic, status, word_count, etc.).

### 6.2 Mark a materialization as stale

1. Ask Claude:
   > "Use manage_materialization to mark that materialization as stale"

**Expected:** Returns `{"success": true}`. The status in the UI changes to a yellow "stale" badge.

### 6.3 Archive a materialization

1. Ask Claude:
   > "Use manage_materialization to archive that materialization"

**Expected:** Returns `{"success": true}`. The status in the UI changes to a gray "archived" badge.

### 6.4 Mark accessed

1. Ask Claude:
   > "Use manage_materialization to mark that materialization as accessed"

**Expected:** Returns `{"success": true}`. The access count increments by 1.

### 6.5 Delete via MCP

1. Ask Claude:
   > "Use manage_materialization to delete that materialization"

**Expected:** Returns `{"success": true}`. The record disappears from the list, and the file is removed from disk.

---

## Phase 7: Codebase Analyst Context Escalation

This tests the autonomous materialization flow triggered by the codebase-analyst agent.

### 7.1 Trigger context escalation

1. In Claude Code, with a project linked to Cortex, ask a question about a topic that:
   - Is NOT documented in your local codebase
   - IS present in your Cortex knowledge base (something you've crawled)

   Example:
   > "Analyze how we should implement Supabase RLS policies in this project, following best practices"

2. Observe Claude's behavior — it should use the codebase-analyst agent which follows the Context Escalation Protocol.

**Expected behavior (autonomous flow):**
1. Agent checks local context first (`.cortex/index.md`, source files, docs)
2. Finds insufficient local coverage
3. Calls `materialize_knowledge` to pull knowledge from the global knowledge base
4. Reads the newly materialized file
5. Incorporates the knowledge into its analysis

**Verify after completion:**
```bash
ls .cortex/knowledge/
cat .cortex/index.md
```
A new materialized file should appear for the topic the agent escalated.

### 7.2 Verify subsequent sessions use cached knowledge

1. Start a new Claude Code session in the same project
2. Ask about the same topic again

**Expected:** The agent finds the materialized file locally (via `.cortex/index.md`) and uses it directly — no new materialization is triggered.

---

## Phase 8: Status Badge Verification

### 8.1 Verify all status badges render correctly

Create or modify materializations to have each status, then check the UI:

| Status | Expected Badge |
|--------|---------------|
| pending | Blue background (`bg-blue-900/50`), blue text |
| active | Green background (`bg-green-900/50`), green text |
| stale | Yellow background (`bg-yellow-900/50`), yellow text |
| archived | Gray background (`bg-gray-700`), gray text |

**How to test:** Use the `manage_materialization` MCP tool to change statuses, then verify each badge appearance in the Materialized list view.

---

## Phase 9: Error Handling

### 9.1 Materialize a topic with no matching content

1. In Claude Code, ask:
   > "Use materialize_knowledge to materialize knowledge about 'xyzzy_nonexistent_topic_12345'"

**Expected:** Returns `{"success": false, "reason": "no_relevant_content"}`. No file is created, no database record left behind.

### 9.2 Verify no orphaned pending records

1. After the failed materialization above, check the UI Materialized list

**Expected:** No "pending" record appears for the failed topic — it was cleaned up automatically.

---

## Phase 10: Regression — Automated Tests

Run the automated test suite to confirm nothing is broken:

```bash
cd /home/winadmin/projects/Trinity/cortex/python
uv run pytest tests/server/services/test_materialization_service.py tests/server/services/test_materialization_pipeline.py tests/server/services/test_indexer_service.py tests/agents/test_synthesizer_agent.py tests/server/api_routes/test_materialization_api.py -v
```

**Expected:** 72 tests pass, 0 failures.

---

## Pass Criteria Summary

| # | Test | Pass |
|---|------|------|
| 1.1 | `cortex_materialization_history` table exists | ☐ |
| 1.2 | `increment_access_count` function exists | ☐ |
| 2.1 | Knowledge Base page loads | ☐ |
| 2.2 | Materialized toggle button visible in filter bar | ☐ |
| 2.3 | Toggle ON shows purple highlight and materialized list | ☐ |
| 2.4 | Toggle OFF returns to normal knowledge view | ☐ |
| 3.1 | MCP materialization tools are available | ☐ |
| 3.2 | `materialize_knowledge` succeeds with valid response | ☐ |
| 3.3 | Markdown file created in `.cortex/knowledge/` | ☐ |
| 3.4 | File has correct YAML frontmatter and synthesized content | ☐ |
| 3.5 | `.cortex/index.md` updated with new entry | ☐ |
| 4.1 | Duplicate topic returns existing record (no new file) | ☐ |
| 4.2 | Case-insensitive deduplication works | ☐ |
| 5.1 | Materialization appears in UI with correct metadata | ☐ |
| 5.2 | Project filter works on materialized list | ☐ |
| 5.3 | Delete from UI removes record, file, and index entry | ☐ |
| 6.1 | `find_materializations` returns records | ☐ |
| 6.2 | `manage_materialization` mark_stale updates status | ☐ |
| 6.3 | `manage_materialization` archive updates status | ☐ |
| 6.4 | `manage_materialization` mark_accessed increments count | ☐ |
| 6.5 | `manage_materialization` delete removes record and file | ☐ |
| 7.1 | Codebase analyst escalates to materialization autonomously | ☐ |
| 7.2 | Subsequent sessions use cached materialized file | ☐ |
| 8.1 | All four status badges render with correct colors | ☐ |
| 9.1 | Nonexistent topic returns failure, no orphaned records | ☐ |
| 9.2 | No pending records left after failed materialization | ☐ |
| 10.1 | All 72 automated tests pass | ☐ |
