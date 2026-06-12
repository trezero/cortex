# /link-to-project Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a `/link-to-project` Claude Code skill that walks users through linking the current repo to an Cortex project ecosystem — establishing hierarchy, associating knowledge sources, and optionally ingesting local docs.

**Architecture:** A single SKILL.md file that orchestrates existing MCP tools (`find_projects`, `manage_project`, `rag_get_available_sources`, `manage_rag_source`, `rag_check_progress`) through a sequential wizard flow. Also requires adding `technical_sources` parameter to the `manage_project` MCP tool so the skill can link existing knowledge sources to a project.

**Tech Stack:** Claude Code skill (SKILL.md markdown), Python (MCP tool update), existing Cortex MCP infrastructure

---

### Task 1: Add `technical_sources` parameter to `manage_project` MCP tool

The skill needs to link existing knowledge sources to a project. Currently `manage_project` doesn't support `technical_sources`/`business_sources` params, but the REST API's PUT `/api/projects/{id}` does. We need to thread this through.

**Files:**
- Modify: `python/src/mcp_server/features/projects/project_tools.py`
- Test: `python/tests/mcp_server/features/projects/test_project_tools_source_linking.py`

**Step 1: Write the failing test**

Create `python/tests/mcp_server/features/projects/test_project_tools_source_linking.py`:

```python
"""Tests for manage_project source linking via MCP tool."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


@pytest.fixture
def mock_ctx():
    """Create a mock MCP context."""
    ctx = MagicMock()
    return ctx


@patch("src.mcp_server.features.projects.project_tools.get_api_url", return_value="http://localhost:8181")
@pytest.mark.asyncio
async def test_manage_project_update_sends_technical_sources(mock_api_url, mock_ctx):
    """When technical_sources is provided in update, it should be sent to the API."""
    from src.mcp_server.features.projects.project_tools import register_project_tools
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("test")
    register_project_tools(mcp)

    # Get the registered manage_project function
    tools = mcp.list_tools()
    manage_fn = None
    for tool in tools:
        if tool.name == "manage_project":
            manage_fn = mcp._tools["manage_project"].fn
            break

    assert manage_fn is not None, "manage_project tool not registered"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "proj-123",
        "title": "Test Project",
        "technical_sources": ["src_001", "src_002"],
    }

    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.put = AsyncMock(return_value=mock_response)

        result = await manage_fn(
            mock_ctx,
            action="update",
            project_id="proj-123",
            technical_sources=["src_001", "src_002"],
        )

        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify the API call included technical_sources
        call_args = mock_client.put.call_args
        request_body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "technical_sources" in request_body
        assert request_body["technical_sources"] == ["src_001", "src_002"]
```

**Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/mcp_server/features/projects/test_project_tools_source_linking.py -v`
Expected: FAIL — `manage_project` doesn't accept `technical_sources` parameter

**Step 3: Add `technical_sources` and `business_sources` parameters to `manage_project`**

In `python/src/mcp_server/features/projects/project_tools.py`, update the `manage_project` function signature:

```python
    @mcp.tool()
    async def manage_project(
        ctx: Context,
        action: str,  # "create" | "update" | "delete"
        project_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        github_repo: str | None = None,
        parent_project_id: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        technical_sources: list[str] | None = None,
        business_sources: list[str] | None = None,
    ) -> str:
```

Update the docstring to include:
```
            technical_sources: Source IDs to link as technical knowledge (for update)
            business_sources: Source IDs to link as business knowledge (for update)
```

In the `action == "update"` block, add these to the `update_data` dict:
```python
                    if technical_sources is not None:
                        update_data["technical_sources"] = technical_sources
                    if business_sources is not None:
                        update_data["business_sources"] = business_sources
```

**Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/mcp_server/features/projects/test_project_tools_source_linking.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add python/src/mcp_server/features/projects/project_tools.py python/tests/mcp_server/features/projects/test_project_tools_source_linking.py
git commit -m "feat: add technical_sources param to manage_project MCP tool"
```

---

### Task 2: Create the SKILL.md file — Phase 0 (Health Check & State Load)

**Files:**
- Create: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Create the skill directory and file**

```bash
mkdir -p integrations/claude-code/skills/cortex-link-project
```

**Step 2: Write the skill frontmatter and Phase 0**

Create `integrations/claude-code/skills/cortex-link-project/SKILL.md` with:

```markdown
---
name: cortex-link-project
description: Link the current repo to an Cortex project ecosystem. Establishes project hierarchy (parent/child), associates knowledge sources, and optionally ingests local docs. Use when the user says "link project", "connect to project", "set up project hierarchy", or needs to associate repos within a multi-project ecosystem.
---

# Link to Project — Multi-Repo Ecosystem Setup

Links the current repo to an Cortex project ecosystem by establishing hierarchy, associating knowledge sources, and optionally ingesting local documentation.

**Invocation:** `/link-to-project`

---

## Phase 0: Health Check & State Load

Run this before any operation.

### 0a. Verify Cortex is reachable

```
health_check()
```

If Cortex is down or `api_service` is false:
> "Cortex server is not reachable. Check that it's running on the configured host. The cortex MCP server must be configured in .mcp.json or ~/.claude/mcp.json."

Stop here if unhealthy.

### 0b. Load state file

Read `.claude/cortex-state.json` if it exists.

### 0c. Check for existing link

If `.claude/cortex-state.json` exists and has `cortex_project_id` AND `parent_project_id`:
> "This repo is already linked to an Cortex project ecosystem:
> - **Project:** <project_name> (<cortex_project_id>)
> - **Parent:** <parent_project_name> (<parent_project_id>)
> - **Linked at:** <linked_at>
>
> What would you like to do?"

Ask the user:
- **Modify** — Change hierarchy or source links
- **Re-link** — Start fresh with a different project
- **Cancel** — Exit

If "Modify": skip to Phase 3 (Source Linking).
If "Re-link": continue to Phase 1.
If "Cancel": stop.

If state file exists but has NO `parent_project_id` (project exists but no hierarchy), continue to Phase 1 with the existing project.
```

**Step 3: Commit**

```bash
git add integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: create link-to-project skill with Phase 0"
```

---

### Task 3: Add Phase 1 (Project Discovery) to SKILL.md

**Files:**
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Append Phase 1 to the SKILL.md**

Add after Phase 0:

```markdown

---

## Phase 1: Project Discovery

### 1a. Get current repo identity

```bash
git remote get-url origin 2>/dev/null || echo "no-remote"
```

Get the project directory name as fallback:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

### 1b. List existing Cortex projects

```
find_projects()
```

Present the list to the user:
> "Here are the existing Cortex projects:
>
> | # | Project | ID | Parent | Tags |
> |---|---------|----|---------|----|
> | 1 | RecipeRaiders Ecosystem | 5cb8f561... | — | ecosystem |
> | 2 | RecipeRaiders Main | 2d747998... | 5cb8f561... | backend |
> | 3 | reciperaiders-spa | d452583d... | 5cb8f561... | frontend |
>
> Which project do you want to link this repo to? Or type 'new' to create a new project."

### 1c. Handle selection

**If user selects an existing project:** Store as `target_project_id`. Continue to Phase 2.

**If user says "new":** Ask for project details:
- Title (suggest: `<repo-name>` from 1a)
- Description (optional)
- Tags (optional)

Create the project:
```
manage_project(
    action="create",
    title="<user-provided-title>",
    description="<user-provided-description>",
    tags=<user-provided-tags>
)
```

Store the new `project_id` as `target_project_id`. Continue to Phase 2.

### 1d. Ensure current repo has an Cortex project

If `.claude/cortex-state.json` has no `cortex_project_id`, the current repo needs its own project too.

Check if one exists:
```
find_projects(query="<repo-name>")
```

If not found, create one:
```
manage_project(
    action="create",
    title="<repo-name>",
    github_repo="<remote-url>",
    description="<repo-name> project"
)
```

Store as `this_project_id`.
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: add Phase 1 (Project Discovery) to link-to-project skill"
```

---

### Task 4: Add Phase 2 (Establish Hierarchy) to SKILL.md

**Files:**
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Append Phase 2 to the SKILL.md**

Add after Phase 1:

```markdown

---

## Phase 2: Establish Hierarchy

### 2a. Determine relationship

Ask the user:
> "What's the relationship between **<this-repo-name>** and **<target-project-name>**?"

Options:
- **Child** — This repo is a sub-project of <target-project-name> (most common)
- **Parent** — This repo is the parent; <target-project-name> becomes a child
- **Siblings** — Both share a common parent project

### 2b. Apply hierarchy

**If "Child":**

Set this repo's project as a child of the target:
```
manage_project(
    action="update",
    project_id="<this_project_id>",
    parent_project_id="<target_project_id>"
)
```

**If "Parent":**

Set the target project as a child of this repo's project:
```
manage_project(
    action="update",
    project_id="<target_project_id>",
    parent_project_id="<this_project_id>"
)
```

**If "Siblings":**

Ask: "Which project should be the shared parent?"
- Show list of existing projects from Phase 1
- Option to create a new parent

Then set both projects as children of the chosen parent:
```
manage_project(action="update", project_id="<this_project_id>", parent_project_id="<parent_id>")
manage_project(action="update", project_id="<target_project_id>", parent_project_id="<parent_id>")
```

### 2c. Detect circular hierarchy

Before applying, check: if the target project already has `parent_project_id` equal to `this_project_id`, setting `this_project_id`'s parent to `target_project_id` would create a cycle.

If detected:
> "Cannot create this link — it would create a circular hierarchy (<A> → <B> → <A>). Choose a different relationship or project."

Go back to 2a.

### 2d. Confirm

> "Hierarchy established:
> - **<parent-name>** (parent)
>   └── **<child-name>** (child)
>
> Continuing to source linking..."
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: add Phase 2 (Establish Hierarchy) to link-to-project skill"
```

---

### Task 5: Add Phase 3 (Source Linking) to SKILL.md

**Files:**
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Append Phase 3 to the SKILL.md**

Add after Phase 2:

```markdown

---

## Phase 3: Source Linking

Associate existing knowledge sources with this project.

### 3a. List available sources

```
rag_get_available_sources()
```

Present sources to the user:
> "Here are the available knowledge sources in Cortex:
>
> | # | Title | Source ID | Summary |
> |---|-------|----------|---------|
> | 1 | Firebase Documentation | src_abc | Firebase platform docs... |
> | 2 | RecipeRaiders Docs | src_def | Main app documentation... |
> | 3 | Elasticsearch Guide | src_ghi | Search engine docs... |
>
> Which sources should be linked to **<this-project-name>**? Enter numbers separated by commas, or 'skip' to skip."

### 3b. Categorize sources

If the user selected sources, ask:
> "Should these sources be categorized as **technical** (code docs, API refs) or **business** (requirements, specs)? Or type 'mixed' to assign individually."

**If "technical" or "business":** Apply the same category to all selected.

**If "mixed":** Ask for each source individually.

### 3c. Link sources to project

```
manage_project(
    action="update",
    project_id="<this_project_id>",
    technical_sources=["<source_id_1>", "<source_id_2>"],
    business_sources=["<source_id_3>"]
)
```

Report:
> "Linked <N> sources to **<this-project-name>**:
> - Technical: <list>
> - Business: <list>"

### 3d. Skip option

If user says "skip":
> "Skipping source linking. You can link sources later by running `/link-to-project` again."

Continue to Phase 4.
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: add Phase 3 (Source Linking) to link-to-project skill"
```

---

### Task 6: Add Phase 4 (Local Doc Ingestion) to SKILL.md

**Files:**
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Append Phase 4 to the SKILL.md**

Add after Phase 3:

```markdown

---

## Phase 4: Local Doc Ingestion (Optional)

### 4a. Ask about ingestion

> "Would you like to ingest documentation from this repo into Cortex's knowledge base? This enables semantic search across this project's docs."

Options:
- **Yes** — Scan and ingest docs
- **Skip** — Skip ingestion (can do later with `/cortex-memory ingest`)

If "Skip": continue to Phase 5.

### 4b. Discover documents

Scan for documents to ingest:

1. **Primary directory:** All `.md` files in `docs/` (or ask user for directory)
   ```
   Glob: docs/**/*.md
   ```

2. **Extra files:** Look for these in the project root:
   - `CLAUDE.md`
   - `README.md`

3. **Exclude:** Skip files matching:
   - `node_modules/`
   - `.git/`
   - Files larger than 500KB

Report:
> "Found X documents to ingest:
> - docs/: Y files
> - CLAUDE.md: found
> - README.md: found
> Total: ~Z KB. Proceed?"

Wait for user confirmation.

### 4c. Read and build payload

For each discovered file:

1. Read the file content using the Read tool
2. Compute MD5 hash:
   ```bash
   md5sum <filepath> 2>/dev/null | cut -d' ' -f1 || md5 -q <filepath> 2>/dev/null
   ```
3. Add to documents array:
   ```json
   {"title": "<filename>", "content": "<full content>", "path": "<relative path>"}
   ```

Use sub-agents to read files in parallel batches for speed (groups of 5-10 files).

### 4d. Ingest via Cortex

```
manage_rag_source(
    action="add",
    source_type="inline",
    title="<repo-name> Documentation",
    documents=<documents array as list>,
    tags=["<repo-name>", "project-docs"],
    project_id="<this_project_id>",
    knowledge_type="technical",
    extract_code_examples=true
)
```

Save `progress_id` and `source_id` from the response.

### 4e. Poll for completion

```
rag_check_progress(progress_id="<progress_id>")
```

Poll every 5 seconds. Report progress:
> "Ingesting... 19/42 documents processed (45%)"

Continue until `status` is `"completed"`, `"failed"`, or `"error"`.

**If failed:** Report error details. Suggest checking Cortex server logs. Continue to Phase 5 (save what we have).

**If progress_id returns 404:** Check `rag_get_available_sources()` to verify the source was created.

### 4f. Verify ingestion

Run a test search:
```
rag_search_knowledge_base(
    query="project overview",
    project_id="<this_project_id>",
    match_count=3
)
```

If results are returned, ingestion is confirmed.

> "Ingestion complete. <N> documents indexed, <M> chunks stored."
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: add Phase 4 (Local Doc Ingestion) to link-to-project skill"
```

---

### Task 7: Add Phase 5 (Save State) and Important Notes to SKILL.md

**Files:**
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Append Phase 5 and notes to the SKILL.md**

Add after Phase 4:

```markdown

---

## Phase 5: Save State & Report

### 5a. Update state file

Write or update `.claude/cortex-state.json`:
```json
{
  "cortex_project_id": "<this_project_id>",
  "parent_project_id": "<parent_project_id>",
  "project_name": "<this-project-name>",
  "parent_project_name": "<parent-project-name>",
  "linked_at": "<ISO timestamp>",
  "relationship": "child|parent|sibling",
  "sources": {
    "<source_id>": {
      "title": "<source-title>",
      "last_synced": "<ISO timestamp>",
      "type": "technical|business"
    }
  }
}
```

Merge with existing state — preserve `sources` entries from prior ingestion (cortex-memory skill).

### 5b. Ensure state file is gitignored

```bash
grep -q "cortex-state.json" .gitignore 2>/dev/null || echo ".claude/cortex-state.json" >> .gitignore
```

### 5c. Update MEMORY.md

Add or update an "Cortex Project Ecosystem" section:
```markdown
## Cortex Project Ecosystem
- Project: <project-name> (<project-id>)
- Parent: <parent-name> (<parent-id>)
- Relationship: child of <parent-name>
- Linked sources: <N> technical, <M> business
- Search: `rag_search_knowledge_base(query="...", project_id="<project-id>")`
- Cross-project: `rag_search_knowledge_base(query="...", project_id="<project-id>", include_parent=true)`
```

### 5d. Final report

```
## Link to Project — Complete

**This Project:** <project-name> (<project-id>)
**Linked To:** <parent-or-child-name> (<related-id>)
**Relationship:** <child|parent|sibling>

### Hierarchy
- <parent-name> (parent)
  └── <child-name> (child)

### Knowledge Sources Linked
- Technical: <list of source titles>
- Business: <list of source titles>

### Documents Ingested
- <N> documents, <M> chunks stored, <K> code examples extracted
(or "Skipped — use `/cortex-memory ingest` later")

### What's Next
- `/cortex-memory search <query>` — Search this project's knowledge
- `/cortex-memory search-all <query>` — Search all projects including parent
- `/cortex-memory sync` — Re-sync after doc changes
- `/link-to-project` — Modify links or add more sources
```

---

## Important Notes

### Cross-Project Search
When `include_parent=true` (the default), searching with this project's `project_id` will also return results from the parent project's sources. This enables shared knowledge (design systems, common APIs) to be accessible from any child project.

### State File Compatibility
This skill shares `.claude/cortex-state.json` with the `cortex-memory` skill. Fields are merged — this skill adds `parent_project_id`, `parent_project_name`, `linked_at`, and `relationship`. The `sources` dict is shared: cortex-memory manages `source_id`, `last_synced`, `file_hashes`; this skill adds `type` (technical/business).

### Circular Hierarchy Prevention
Cortex supports single-level hierarchy only. A project can have one parent. The skill checks for cycles before applying hierarchy changes.

### Error Recovery
- If Cortex is unreachable, fail fast with a clear message
- If hierarchy update fails, report error and suggest manual `manage_project` call
- If source linking fails, report which sources failed and continue
- If ingestion partially fails, report failures and save state for successful items
- If state file write fails, display the JSON for manual saving
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: add Phase 5 (Save State) and notes to link-to-project skill"
```

---

### Task 8: Register the skill in the skills index

**Files:**
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md` (verify final)
- Check: Any skill registration file or config that needs updating

**Step 1: Verify the skill file is complete**

Read the full SKILL.md and ensure all phases are present and consistent.

**Step 2: Check if skills need registration anywhere**

```bash
ls integrations/claude-code/skills/
```

Look for any index file, manifest, or registration config. If skills are auto-discovered by directory, no registration needed.

**Step 3: Verify the skill triggers correctly**

Check that the `description` field in the SKILL.md frontmatter includes trigger phrases: "link project", "connect to project", "set up project hierarchy", "associate repos".

**Step 4: Commit final state**

```bash
git add -A integrations/claude-code/skills/cortex-link-project/
git commit -m "feat: complete link-to-project skill implementation"
```

---

### Task 9: Run all related tests to verify nothing is broken

**Step 1: Run MCP project tool tests**

```bash
cd python && uv run pytest tests/mcp_server/features/projects/ -v
```

Expected: All tests PASS including the new source linking test.

**Step 2: Run project source filter tests**

```bash
cd python && uv run pytest tests/server/api_routes/test_resolve_project_source_filter.py -v
```

Expected: All tests PASS (validates the bug fix from earlier doesn't regress).

**Step 3: Run full API route tests**

```bash
cd python && uv run pytest tests/server/api_routes/ -v
```

Expected: All tests PASS.

**Step 4: If any tests fail, fix them before proceeding**

---

### Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add `technical_sources` to `manage_project` MCP tool | project_tools.py + test |
| 2 | Create SKILL.md with Phase 0 (Health Check) | SKILL.md |
| 3 | Add Phase 1 (Project Discovery) | SKILL.md |
| 4 | Add Phase 2 (Establish Hierarchy) | SKILL.md |
| 5 | Add Phase 3 (Source Linking) | SKILL.md |
| 6 | Add Phase 4 (Local Doc Ingestion) | SKILL.md |
| 7 | Add Phase 5 (Save State & Report) | SKILL.md |
| 8 | Register and verify skill | SKILL.md |
| 9 | Run all tests | — |
