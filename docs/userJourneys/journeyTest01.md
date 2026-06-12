# Journey Test 01 — Multi-Machine Developer with Multiple Projects

## User Persona

**Jordan** is a full-stack developer working on two interconnected projects:

- **RecipeRaiders** — A consumer-facing recipe discovery app (main repo)
- **RecipeRaiders-Admin** — A companion admin dashboard (separate repo, child project)

Jordan works across four machines:
| Machine ID | OS | Role |
|---|---|---|
| **MacBookPro_M1** | macOS 14 (Apple Silicon) | Primary dev workstation |
| **WIN_AI_PC** | Windows 11 | Windows-native dev (Claude Code via `.bat`) |
| **WIN_AI_PC WSL** | Ubuntu 22.04 on WSL2 | Linux dev environment on same Windows PC |
| **WhiteSharkAI** | Ubuntu 22.04 (bare metal) | High-performance AI workstation |

All four machines connect to the **same Cortex instance** running at `http://cortex.local:3737`.
The Cortex server is accessible across the local network.

---

## Journey Overview

This journey covers one week of Jordan's development activity. Each day highlights different
Cortex features, building toward a complete picture of how the platform powers multi-machine,
multi-project development with persistent context.

| Day | Machine | Focus |
|-----|---------|-------|
| Day 1 | MacBookPro_M1 | First-time setup, project creation, knowledge ingestion |
| Day 2 | WIN_AI_PC | Windows setup, extensions sync, project linking |
| Day 3 | WIN_AI_PC WSL | WSL setup, knowledge materialization, LeaveOff Points |
| Day 4 | WhiteSharkAI | Fourth machine, cross-machine session history, full flow |
| Day 5 | MacBookPro_M1 | Return session — context continuity, materialization reuse |

---

## Prerequisites

- Cortex stack deployed and accessible at `http://cortex.local:3737` (or `localhost:3737`)
- Cortex MCP server accessible at `http://cortex.local:8051`
- Claude Code CLI installed on all four machines
- Python 3 available on PATH on all machines
- Internet access for initial dependency installation

---

## Day 1 — MacBookPro_M1: First-Time Setup and Knowledge Ingestion

### 1.1 Discover the Setup Flow via Cortex UI

**Machine:** MacBookPro_M1

1. Open a browser and navigate to `http://cortex.local:3737`
2. Click **MCP** in the left navigation
3. Scroll to the **Connect a New Machine** card at the top of the page

**Expected:** The card shows:
- A clear description: "Download the Cortex setup script and run it in your project directory"
- Two download buttons: **cortexSetup.sh** (Mac/Linux) and **cortexSetup.bat** (Windows)
- A note: "Then open Claude Code and run /cortex-setup"

### 1.2 Download and Run the Setup Script (Mac)

1. Click **cortexSetup.sh** — browser downloads the file to `~/Downloads/cortexSetup.sh`
2. Open Terminal and navigate to the RecipeRaiders repo:

```bash
cd ~/projects/RecipeRaiders
bash ~/Downloads/cortexSetup.sh
```

**Expected at each setup step:**

| Step | Expected Output |
|------|----------------|
| Banner | Displays `Cortex Setup v1.0.0` with the server URL |
| System name | `Detected: MacBookPro-M1` — press Enter to accept |
| Server confirmation | Shows detected API and MCP URLs, asks to confirm |
| Project match | `Matched in Cortex: RecipeRaiders` — press Enter to accept |
| MCP registration | `✓ Added cortex MCP server` |
| Install scope prompt | `[1] This project only / [2] Global` — choose `1` |
| claude-mem detection | If present: offers to remove and replace — choose `[1]` |
| Plugin install | `✓ Plugin installed to .claude/plugins/cortex-memory/` |
| Config write | `✓ Wrote .claude/cortex-config.json` |
| Summary | "Open Claude Code and run /cortex-setup" |

### 1.3 Verify Setup Files

```bash
ls .claude/
```

**Expected:** `cortex-config.json`, `cortex-state.json`, `plugins/`, `settings.local.json` present.

```bash
ls .claude/plugins/cortex-memory/
```

**Expected:** `src/`, `scripts/`, `hooks/`, `skills/`, `.claude-plugin/`, `.mcp.json`, `requirements.txt` all present.

```bash
cat .claude/cortex-config.json
```

**Expected:** Valid JSON with all fields populated:
- `cortex_api_url` → `http://cortex.local:8181`
- `cortex_mcp_url` → `http://cortex.local:8051`
- `project_id` → non-empty UUID
- `machine_id` → non-empty SHA256 fingerprint
- `install_scope` → `"1"`

```bash
grep -E "\.claude/plugins|cortex-config|cortex-memory-buffer" .gitignore
```

**Expected:** All three gitignore entries present.

### 1.4 Complete Registration via /cortex-setup

1. Open Claude Code in `~/projects/RecipeRaiders/`
2. Run `/cortex-setup`

**Expected flow:**
1. Claude reads `.claude/cortex-state.json` — finds `system_name` and `cortex_project_id`
2. Computes system fingerprint (SHA256 of hostname | username | OS)
3. Calls `manage_extensions(action="bootstrap", ...)` with fingerprint and project ID
4. Installs extensions: `cortex-extension-sync`, `cortex-memory`, `cortex-bootstrap`
5. Updates `.claude/cortex-state.json` with `system_fingerprint`, `system_id`, `last_bootstrap`
6. Prints summary: system name, extensions installed, project linked

### 1.5 Verify SessionStart Context Injection

1. Close and reopen Claude Code (or run `/clear`)
2. Wait for initialization

**Expected:** An `<cortex-context>` block appears at the top of the session containing:
- `## Project: RecipeRaiders` with Cortex project ID
- `### Recent Sessions` section (empty or minimal on first run)
- `### Active Tasks` section
- `### Knowledge Sources` section

### 1.6 Ingest Local Documentation via MCP RAG Tool

Now Jordan ingests the project's existing docs into Cortex's knowledge base.

In Claude Code, ask:

> "Scan the docs/ directory in this repo and ingest all markdown files into Cortex's knowledge base for the RecipeRaiders project."

**Expected behavior:**
1. Claude reads all `.md` files from `docs/` (e.g., `README.md`, `docs/architecture/`, `docs/api/`)
2. Calls `manage_rag_source(action="add", source_type="inline", title="RecipeRaiders Documentation", documents=[...], project_id=<id>, tags=["RecipeRaiders", "docs"], knowledge_type="technical")`
3. Receives `{success: true, progress_id: "...", source_id: "...", estimated_seconds: N}`
4. Calls `rag_check_progress(progress_id=...)` repeatedly until `status="completed"`
5. Reports: `X chunks stored, Y code examples extracted`

### 1.7 Verify Knowledge Appears in Cortex UI

1. Open Cortex UI → **Knowledge** page
2. Look for the new "RecipeRaiders Documentation" source

**Expected:** Source card shows:
- Title: "RecipeRaiders Documentation"
- Type: inline
- Document count: matches the file count ingested
- Status: completed (green)

### 1.8 Verify Knowledge Tab in Project View

1. In Cortex UI → click **Projects** in left navigation
2. Select the **RecipeRaiders** project
3. Click the **Knowledge** tab in the project detail view

**Expected:**
- Left panel lists all ingested knowledge sources associated with RecipeRaiders
- Clicking a source shows document chunks and code examples in the right inspector panel
- "View in Knowledge Base" link navigates to the full Knowledge page filtered to this source

### 1.9 Search Knowledge with Project Scope

In Claude Code:

> "Search Cortex's knowledge base for information about subscription gates, scoped to the RecipeRaiders project."

**Expected:** Claude calls `rag_search_knowledge_base(query="subscription gates", project_id=<id>)` and returns relevant chunks only from RecipeRaiders sources (not from any other projects).

### 1.10 Do Real Work and Save First LeaveOff Point

1. Ask Claude to perform a meaningful task:

   > "Add input validation to the user registration endpoint based on our docs."

2. Claude performs the work and modifies files
3. After completion, verify Claude automatically calls `manage_leaveoff_point(action="update")` with:
   - `content`: description of what was accomplished
   - `component`: e.g., "User Authentication Module"
   - `next_steps`: list of concrete next steps with file paths
   - `references`: relevant files and docs

**Expected:** Tool returns a JSON response with the saved record including `id`, `project_id`, `updated_at`.

### 1.11 Verify LeaveOff Point in Database

1. Open Supabase dashboard or use a DB client
2. Run:

```sql
SELECT id, project_id, component, next_steps, updated_at
FROM cortex_leaveoff_points;
```

**Expected:** One row for RecipeRaiders with the content Claude provided.

### 1.12 Verify LeaveOffPoint.md Written to Repo

```bash
cat .cortex/knowledge/LeaveOffPoint.md
```

**Expected:** A markdown file with YAML frontmatter (`project_id`, `component`, `updated_at`, `machine_id`) and a `## Next Steps` section with bullet points.

---

## Day 2 — WIN_AI_PC: Windows Setup and Extensions Sync

Jordan switches to the Windows AI PC and sets up Cortex for a second project: RecipeRaiders-Admin.

### 2.1 Download and Run the Windows Setup Script

**Machine:** WIN_AI_PC

1. Open a browser → navigate to `http://cortex.local:3737` → **MCP** page
2. Click **cortexSetup.bat** — downloads to `%USERPROFILE%\Downloads\cortexSetup.bat`
3. Open Command Prompt and run:

```cmd
cd %USERPROFILE%\projects\RecipeRaiders-Admin
%USERPROFILE%\Downloads\cortexSetup.bat
```

**Expected flow:**
- Banner shows `Cortex Setup v1.0.0` with server URL
- System name detected: `WIN_AI_PC` — press Enter to accept
- Server URL confirmation displayed — press Enter to accept
- Project search: "RecipeRaiders-Admin" — matched or manually searched and selected
- If not found: choose `C` to create new project named "RecipeRaiders-Admin"
- MCP registered: `✓ Added cortex MCP server`
- Install scope: choose `[1]` (project-local)
- Plugin installed to `.claude\plugins\cortex-memory\`
- `cortex-config.json` written

### 2.2 Verify Windows Config Files

```cmd
dir .claude\
dir .claude\plugins\cortex-memory\
type .claude\cortex-config.json
```

**Expected:**
- All plugin subdirectories present (`src\`, `scripts\`, `hooks\`, `skills\`)
- `cortex-config.json` shows `WIN_AI_PC`'s fingerprint, RecipeRaiders-Admin project ID

### 2.3 Run /cortex-setup on Windows

1. Open Claude Code in `%USERPROFILE%\projects\RecipeRaiders-Admin\`
2. Run `/cortex-setup`

**Expected:** Extensions installed, WIN_AI_PC registered with Cortex as a new system.

### 2.4 Verify Extensions Tab Shows Both Systems

1. Open Cortex UI → **Projects** → select **RecipeRaiders-Admin**
2. Click the **Extensions** tab

**Expected:**
- `cortex-memory` appears as type `plugin` with version `1.0.0`
- `cortex-extension-sync` appears as type `skill`
- `cortex-bootstrap` appears as type `skill`
- `WIN_AI_PC` listed as a registered system with all extensions installed

### 2.5 Verify MacBookPro_M1 Also Shows in Extensions Registry

1. In Cortex UI → **Projects** → select **RecipeRaiders**
2. Click the **Extensions** tab

**Expected:**
- Same extensions listed
- `MacBookPro-M1` listed as a registered system
- `WIN_AI_PC` NOT listed here (it's registered to a different project)

### 2.6 Link RecipeRaiders-Admin as Child Project

In Claude Code on WIN_AI_PC:

> "Link this repo to Cortex. This is a child project of RecipeRaiders."

**Expected:** Claude uses the `cortex-link-project` skill:
1. Phase 0: Verifies Cortex reachable, reads `.claude/cortex-state.json`
2. Phase 1: Finds RecipeRaiders-Admin already exists, confirms selection
3. Phase 2: Asks about relationship — user selects "child of RecipeRaiders"
4. Calls `manage_project(action="update", parent_project_id=<RecipeRaiders-id>)`
5. Phase 3: Shows available knowledge sources — user skips or links RecipeRaiders sources
6. Phase 4: Offers to ingest local docs from `docs/` — user accepts
7. Calls `manage_rag_source(action="add", source_type="inline", ...)` for admin docs
8. Phase 5: Updates `.claude/cortex-state.json` with `parent_project_id`

**Verify in Cortex UI:** RecipeRaiders-Admin shows `parent_project_id` linking to RecipeRaiders.

### 2.7 Verify Project Filter on Knowledge Page

1. Open Cortex UI → **Knowledge** page
2. Find the **project filter dropdown** in the filter bar

**Expected:** Dropdown contains "All Projects", "RecipeRaiders", "RecipeRaiders-Admin"

3. Select **RecipeRaiders-Admin**

**Expected:** Only knowledge sources tagged to RecipeRaiders-Admin are shown (admin docs).

4. Select **RecipeRaiders**

**Expected:** Only RecipeRaiders sources shown.

5. Select **All Projects**

**Expected:** All sources shown.

### 2.8 Check SessionStart Context on WIN_AI_PC (First Session)

1. Start a fresh Claude Code session (or `/clear`) in RecipeRaiders-Admin
2. Observe startup output

**Expected:** `<cortex-context>` block shows:
- `## Project: RecipeRaiders-Admin`
- `### Active Tasks` (tasks assigned in Cortex)
- `### Knowledge Sources` (admin docs just ingested)
- `### LeaveOff Point` section is **absent** (no LeaveOff Point yet for this project)

---

## Day 3 — WIN_AI_PC WSL: Knowledge Materialization and LeaveOff Continuity

Jordan opens the WSL Ubuntu terminal on the same Windows PC to work in a Linux environment.

### 3.1 WSL Setup

**Machine:** WIN_AI_PC WSL (Ubuntu 22.04 on WSL2)

1. Open WSL terminal and navigate to the repo (accessible via `/mnt/c/Users/Jordan/projects/RecipeRaiders`):

```bash
cd /mnt/c/Users/Jordan/projects/RecipeRaiders
bash ~/Downloads/cortexSetup.sh
```

Or download directly:
```bash
curl -o /tmp/cortexSetup.sh http://cortex.local:8051/cortex-setup.sh
bash /tmp/cortexSetup.sh
```

**Expected:** Same setup flow as Day 1 (Mac). System name detected as `WIN_AI_PC-WSL` or similar hostname. Install scope: choose `[1]` (project-local).

**Note:** The same RecipeRaiders repo directory is used (Windows path mounted in WSL). This tests that the same project directory can have Cortex configured on multiple machines.

### 3.2 Verify WSL Registers as Separate System

1. Open Cortex UI → **Projects** → **RecipeRaiders** → **Extensions** tab

**Expected:**
- `MacBookPro-M1` listed (from Day 1)
- `WIN_AI_PC-WSL` listed (just registered)
- Both show all extensions installed

### 3.3 Verify LeaveOff Point from Day 1 Is Loaded

1. Open Claude Code in the RecipeRaiders repo from WSL
2. Wait for session initialization

**Expected:** `<cortex-context>` block contains:

```
## LeaveOff Point (Last Session State)
**Component:** User Authentication Module
**Updated:** [Day 1 timestamp]

### Next Steps
- [Bullet points from Jordan's Day 1 session]

### References
- [Files referenced on Day 1]
```

The LeaveOff Point appears **before** Recent Sessions and Active Tasks.

### 3.4 Ask Claude What to Work on Next

> "What should we work on next based on where we left off?"

**Expected:** Claude references the LeaveOff Point and suggests continuing with the saved next steps from Day 1 — demonstrating true cross-machine context continuity.

### 3.5 Perform a Task and Trigger Knowledge Materialization

1. Ask Claude a question about a topic that exists in the knowledge base but not in local docs:

   > "Analyze how we should implement Supabase RLS policies for the subscription gate feature, following best practices from our knowledge base."

2. Observe Claude's behavior

**Expected autonomous flow (codebase-analyst Context Escalation Protocol):**
1. Agent checks `.cortex/index.md` and local source files — finds insufficient coverage
2. Calls `materialize_knowledge(topic="supabase-rls-policies", project_id=<id>, project_path=<path>)`
3. Waits for materialization to complete (10–60 seconds)
4. Reads the newly created `.cortex/knowledge/supabase-rls-policies.md`
5. Incorporates the knowledge into its analysis

### 3.6 Verify Materialized File on Disk

```bash
ls .cortex/knowledge/
cat .cortex/knowledge/supabase-rls-policies.md
```

**Expected file contains:**
- YAML frontmatter with:
  - `cortex_source: vector_archive`
  - `materialized_at:` — today's timestamp
  - `topic: supabase-rls-policies`
  - `source_urls:` — list of source URLs
  - `synthesis_model:` — model used
  - `materialization_id:` — UUID
- H1 title at the top
- Logical sections (##, ###)
- Synthesized, deduplicated content (not raw chunks)
- Code blocks with language tags
- `## Sources` section at the bottom

### 3.7 Verify .cortex/index.md Updated

```bash
cat .cortex/index.md
```

**Expected:**
- Header: `# .cortex Knowledge Index`
- Note: "Auto-generated by Cortex. Do not edit manually."
- `## Materialized Knowledge` section with an entry for `supabase-rls-policies.md`

### 3.8 Verify Materialization in Cortex UI

1. Open Cortex UI → **Knowledge** page
2. Click the **Materialized** toggle button in the filter bar

**Expected:**
- Button changes to purple-highlighted style
- Materialized list view appears
- `supabase-rls-policies` entry shows:
  - Topic name in white text
  - Green "active" status badge
  - File path: `.cortex/knowledge/supabase-rls-policies.md`
  - Word count (positive number)
  - Access count: 1
  - Today's date
  - Source URL(s)

### 3.9 Toggle Materialized View Off

1. Click **Materialized** button again

**Expected:** Button returns to gray/inactive style. Normal knowledge cards reappear.

### 3.10 Test Duplicate Materialization Prevention

In Claude Code:

> "Use materialize_knowledge to materialize knowledge about supabase-rls-policies again."

**Expected:** Tool returns quickly with the existing record — no new file created, access count bumped to 2.

### 3.11 Test Case-Insensitive Deduplication

> "Use materialize_knowledge to materialize knowledge about SUPABASE RLS POLICIES."

**Expected:** Returns the existing record (topics normalized to lowercase). No new file.

### 3.12 Complete the Task and Update LeaveOff Point

After Claude finishes the RLS policy analysis and implementation:

**Expected:** Claude calls `manage_leaveoff_point(action="update")` automatically with:
- New content describing the RLS work
- Updated next steps
- References to the materialized file and modified source files

### 3.13 Verify LeaveOff Point Was Updated (Not Duplicated)

```sql
SELECT COUNT(*), updated_at FROM cortex_leaveoff_points
WHERE project_id = '<RecipeRaiders-project-id>';
```

**Expected:** Count is exactly `1`. Timestamp is updated to today.

---

## Day 4 — WhiteSharkAI: Fourth Machine Setup and Full Cross-Machine Test

### 4.1 Setup on WhiteSharkAI (Ubuntu 22 Bare Metal)

**Machine:** WhiteSharkAI

```bash
cd ~/projects/RecipeRaiders
curl -o /tmp/cortexSetup.sh http://cortex.local:8051/cortex-setup.sh
bash /tmp/cortexSetup.sh
```

**Expected:** System name detected as `WhiteSharkAI`. Script completes successfully. Install scope: choose `[2]` (global) to test global installation.

**Verify global installation path:**
```bash
ls ~/.claude/plugins/cortex-memory/
ls ~/.claude/settings.json  # or ~/.claude.json — verify global MCP registration
```

**Expected:** Plugin files in `~/.claude/plugins/` (not in project `.claude/`). Cortex MCP server registered globally.

### 4.2 Verify All Four Machines in Extensions Registry

1. Open Cortex UI → **Projects** → **RecipeRaiders** → **Extensions** tab

**Expected:** Four registered systems visible:
- `MacBookPro-M1` (installed, last seen: Day 1)
- `WIN_AI_PC-WSL` (installed, last seen: Day 3)
- `WhiteSharkAI` (installed, just now)

**Note:** `WIN_AI_PC` is registered to RecipeRaiders-Admin only, so it should NOT appear here.

### 4.3 Verify Context from Previous Sessions Is Loaded

1. Open Claude Code in RecipeRaiders on WhiteSharkAI
2. Observe session initialization

**Expected `<cortex-context>` block includes:**
- **LeaveOff Point** — content from Day 3's session (RLS policy work)
- **Recent Sessions** — sessions from MacBookPro_M1 (Day 1) and WIN_AI_PC-WSL (Day 3)
- **Active Tasks** — any tasks in the project

### 4.4 Ask About Previous Session Work

> "Search Cortex session history for recent work on subscription gates in this project."

**Expected:** Claude calls `cortex_search_sessions(query="subscription gates", project_id=<id>)` and returns sessions from Day 1 and Day 3 with summaries and observation counts.

### 4.5 Get Full Session Detail

> "Get the full details of the Day 3 session."

**Expected:** Claude calls `cortex_get_session(session_id=<id>)` and returns the full session with all observations from the Day 3 WSL session in order.

### 4.6 Verify Materialized Knowledge Is Reused

1. Ask Claude the same question about RLS policies:

   > "How should we implement Supabase RLS policies for subscription gates?"

**Expected:** Claude finds `.cortex/knowledge/supabase-rls-policies.md` locally via `.cortex/index.md` and reads it directly — **no new materialization call**. Access count in UI increments to 3.

### 4.7 Smart Explore Tools — Code Navigation

In Claude Code on WhiteSharkAI:

**smart_search:**
> "Use smart_search to find the subscription gate validation function across this codebase."

**Expected:** Returns ranked results showing file paths, function signatures, and line numbers — does NOT read entire files.

**smart_outline:**
> "Use smart_outline on `python/src/server/services/subscription_service.py`"

**Expected:** Returns structural skeleton — all class methods with signatures and line ranges, import summary, token estimate. Typically 1–3k tokens vs 12k+ for full file.

**smart_unfold:**
> "Use smart_unfold on that file for the `validate_subscription_gate` method."

**Expected:** Returns only that method's complete source with a location header (e.g., `subscription_service.py:47–85`).

**smart_unfold — negative test:**
> "Use smart_unfold for a function called `nonexistent_function_xyz` in that file."

**Expected:** Returns an error listing the available symbols — no crash.

### 4.8 Observe PostToolUse Buffer Accumulation

After triggering several tool uses (searches, file reads, edits):

```bash
wc -l ~/.claude/cortex-memory-buffer.jsonl  # (global install path)
```

**Expected:** One line per tool use, each containing `tool_name`, `timestamp`, `session_id`.

### 4.9 Test the 90% Rule (Observation Count Warning)

Simulate a high-observation session:

```bash
python3 -c "
from pathlib import Path
buf = Path('~/.claude/cortex-memory-buffer.jsonl').expanduser()
buf.parent.mkdir(parents=True, exist_ok=True)
with buf.open('w') as f:
    for i in range(80):
        f.write('{\"tool_name\": \"Edit\", \"summary\": \"test\"}\n')
print(f'Created buffer with {sum(1 for _ in buf.open())} lines')
"
```

Then trigger one more tool use and observe Claude's session:

**Expected:** A `<system-reminder>` block appears containing:
- "SESSION RESOURCE WARNING"
- Observation count (81)
- Instruction to generate a final LeaveOff Point
- Advice to start a new session

Clean up:
```bash
rm -f ~/.claude/cortex-memory-buffer.jsonl
```

### 4.10 Verify CLAUDE.md Protocol Exists

```bash
grep -A 5 "LeaveOff Point Protocol" CLAUDE.md
```

**Expected:** Section exists with subsections for "After Every Coding Task", "Session Resource Management (The 90% Rule)", and "Session Start".

### 4.11 Materialize Knowledge About a New Topic

> "Use materialize_knowledge to materialize knowledge about React hooks best practices for this project"

**Expected:**
- Tool executes (10–60 seconds)
- Returns `{success: true, file_path: ".cortex/knowledge/react-hooks-best-practices.md", word_count: N}`
- File appears in `.cortex/knowledge/`
- `.cortex/index.md` updated with new entry

### 4.12 View All Materializations for the Project

> "Use find_materializations to list all materializations for this project."

**Expected:** Returns array with both materializations:
1. `supabase-rls-policies` (from Day 3)
2. `react-hooks-best-practices` (just created)

Each record includes: topic, status, word_count, access_count, materialized_at, file_path.

### 4.13 Manage Materialization Status

**Mark as stale:**
> "Use manage_materialization to mark the supabase-rls-policies materialization as stale."

**Expected:** Returns `{success: true}`. In Cortex UI → Knowledge → Materialized: status badge changes to yellow "stale".

**Archive:**
> "Use manage_materialization to archive the react-hooks-best-practices materialization."

**Expected:** Returns `{success: true}`. Status badge changes to gray "archived".

**Mark accessed:**
> "Use manage_materialization to mark the supabase-rls-policies file as accessed."

**Expected:** Returns `{success: true}`. Access count increments.

### 4.14 Delete a Materialization

1. In Cortex UI → **Knowledge** → click **Materialized** toggle
2. Click **Delete** on the `supabase-rls-policies` entry

**Expected:**
- Entry disappears from the list
- Verify on disk: file removed from `.cortex/knowledge/`
- `.cortex/index.md` updated (entry removed)

```bash
ls .cortex/knowledge/
cat .cortex/index.md
```

### 4.15 Test Materialization Failure Handling

> "Use materialize_knowledge to materialize knowledge about 'xyzzy_nonexistent_topic_12345_abc'"

**Expected:** Returns `{success: false, reason: "no_relevant_content"}`. No file created. No orphaned pending records in the UI.

### 4.16 End Session — Verify Buffer Flushed

1. Close Claude Code session
2. Verify the buffer was flushed:

```bash
# For global install:
ls -la ~/.claude/cortex-memory-buffer.jsonl
# Should be empty or absent
```

### 4.17 Verify Session Stored in Cortex UI

1. In a new Claude Code session
2. Ask: "Search Cortex session history for today's work on WhiteSharkAI"

**Expected:** The completed session appears with:
- `started_at` timestamp from today
- `observations` matching the tool uses triggered
- Linked to RecipeRaiders project

---

## Day 5 — MacBookPro_M1: Return Session and Full Context Continuity

Jordan returns to the Mac after 4 days of multi-machine work.

### 5.1 Open New Session and Verify Complete Context

1. Open Claude Code in `~/projects/RecipeRaiders/` on MacBookPro_M1
2. Wait for session initialization

**Expected `<cortex-context>` block shows all four sections in order:**

```
## LeaveOff Point (Last Session State)
**Component:** [Component from last save]
**Updated:** [Day 4 timestamp from WhiteSharkAI]

### Next Steps
- [Bullet points from WhiteSharkAI session]

### References
- [Files from WhiteSharkAI work]

### Recent Sessions
- [4h ago] WhiteSharkAI — React hooks and RLS policy work
- [2d ago] WIN_AI_PC-WSL — RLS policies implementation
- [4d ago] MacBookPro-M1 — User registration validation

### Active Tasks
- [doing] ...

### Knowledge Sources
- 2 materializations, N docs indexed
```

### 5.2 Verify Context Order

The order must be:
1. LeaveOff Point (Last Session State)
2. Recent Sessions
3. Active Tasks
4. Knowledge Sources

### 5.3 Ask Claude What to Work on Next

> "What context do you have about my recent work on this project? What should we tackle next?"

**Expected:** Claude summarizes:
- What was last accomplished (from LeaveOff Point — Day 4's work)
- Specific next steps saved
- References to relevant files
- Mentions recent sessions from other machines (WhiteSharkAI, WSL)

This demonstrates full cross-machine, cross-session context continuity.

### 5.4 Work on a Task, Verify LeaveOff Updates

1. Ask Claude to implement one of the next steps from the LeaveOff Point
2. After completion, verify Claude automatically updates the LeaveOff Point with new content

**Expected:** `manage_leaveoff_point(action="update")` called with fresh content reflecting the Day 5 work.

### 5.5 Verify Only One LeaveOff Point Per Project

```sql
SELECT COUNT(*) FROM cortex_leaveoff_points
WHERE project_id = '<RecipeRaiders-id>';
```

**Expected:** Exactly `1`. Previous LeaveOff Points were replaced, not duplicated (upsert semantics).

### 5.6 Verify Multi-Project Isolation

1. Open Claude Code in `~/projects/RecipeRaiders-Admin/` (if accessible from Mac, or use a different terminal)
2. Check that the LeaveOff Point for RecipeRaiders-Admin is **different** from RecipeRaiders

```sql
SELECT project_id, component, updated_at
FROM cortex_leaveoff_points
ORDER BY updated_at DESC;
```

**Expected:** Two rows — one per project — with different content.

### 5.7 Extension Sync — Detect Drift

1. Manually modify an extension file on MacBookPro_M1:

```bash
echo "# Local modification" >> .claude/skills/cortex-memory/SKILL.md
```

2. Run `/cortex-extension-sync`

**Expected sync flow:**
1. Computes SHA256 hash of local extension files
2. Compares with Cortex registry hashes
3. Detects `cortex-memory` has local changes (hash mismatch)
4. Presents options:
   - `[1]` Update Source — push local content as new canonical version
   - `[2]` Save Project Version — store as project-specific override
   - `[3]` Create New Extension — upload as new extension with new name
   - `[4]` Discard Changes — overwrite local with Cortex canonical version
5. User chooses `[4]` to discard local changes
6. Extension restored to canonical version

### 5.8 Verify Unknown Local Extension Discovery

1. Create a new local extension:

```bash
mkdir -p .claude/skills/my-test-skill
cat > .claude/skills/my-test-skill/SKILL.md << 'EOF'
---
name: my-test-skill
description: A local test skill that Jordan created
---

# My Test Skill

This skill does something useful locally.
EOF
```

2. Run `/cortex-extension-sync`

**Expected:** Sync detects `my-test-skill` as "unknown local" and presents options:
- `[1]` Upload to Cortex — validates and uploads
- `[2]` Skip — leave as local-only

Choose `[1]` to upload.

**Expected validation:**
- Frontmatter check: passes
- Name format: passes (kebab-case)
- Description quality: passes (>=20 chars)
- Secrets check: passes

After upload: extension appears in Cortex UI → **Extensions** registry.

### 5.9 Install an Extension Remotely via Cortex UI

1. Open Cortex UI → **Projects** → **RecipeRaiders** → **Extensions** tab
2. Find `WhiteSharkAI` in the systems list
3. Click **Install Skills** to queue an installation
4. Select `my-test-skill` for installation on WhiteSharkAI

**Expected:** Extension status for WhiteSharkAI changes to `pending_install` (yellow badge).

5. Switch to WhiteSharkAI and run `/cortex-extension-sync`

**Expected:** Extension is picked up from `pending_install` queue and written to disk. Status changes to `installed` (green badge).

---

## Full Feature Coverage Summary

### Features Verified in This Journey

| Feature | Day | Machine | Test |
|---------|-----|---------|------|
| MCP page download buttons | 1 | MacBookPro_M1 | 1.1 |
| cortexSetup.sh (Mac) | 1 | MacBookPro_M1 | 1.2–1.3 |
| /cortex-setup command | 1 | MacBookPro_M1 | 1.4 |
| SessionStart context injection | 1 | MacBookPro_M1 | 1.5 |
| manage_rag_source (inline) | 1 | MacBookPro_M1 | 1.6 |
| rag_check_progress polling | 1 | MacBookPro_M1 | 1.6 |
| Knowledge page (source visible) | 1 | MacBookPro_M1 | 1.7 |
| Knowledge tab in project view | 1 | MacBookPro_M1 | 1.8 |
| RAG search with project_id filter | 1 | MacBookPro_M1 | 1.9 |
| LeaveOff Point — create | 1 | MacBookPro_M1 | 1.10–1.12 |
| cortexSetup.bat (Windows) | 2 | WIN_AI_PC | 2.1–2.2 |
| /cortex-setup on Windows | 2 | WIN_AI_PC | 2.3 |
| Extensions tab — multi-system | 2 | WIN_AI_PC | 2.4–2.5 |
| /link-to-project (child hierarchy) | 2 | WIN_AI_PC | 2.6 |
| Knowledge page project filter | 2 | WIN_AI_PC | 2.7 |
| SessionStart without LeaveOff | 2 | WIN_AI_PC | 2.8 |
| cortexSetup.sh (WSL) | 3 | WIN_AI_PC WSL | 3.1 |
| WSL as separate registered system | 3 | WIN_AI_PC WSL | 3.2 |
| LeaveOff Point loaded cross-machine | 3 | WIN_AI_PC WSL | 3.3–3.4 |
| Knowledge materialization (autonomous) | 3 | WIN_AI_PC WSL | 3.5 |
| Materialized file content verification | 3 | WIN_AI_PC WSL | 3.6–3.7 |
| Materialized toggle in UI | 3 | WIN_AI_PC WSL | 3.8–3.9 |
| Duplicate materialization prevention | 3 | WIN_AI_PC WSL | 3.10–3.11 |
| LeaveOff Point — upsert (not duplicate) | 3 | WIN_AI_PC WSL | 3.12–3.13 |
| cortexSetup.sh (Ubuntu, global scope) | 4 | WhiteSharkAI | 4.1 |
| All 4 machines in Extensions registry | 4 | WhiteSharkAI | 4.2 |
| Cross-machine context restoration | 4 | WhiteSharkAI | 4.3 |
| cortex_search_sessions | 4 | WhiteSharkAI | 4.4 |
| cortex_get_session (full detail) | 4 | WhiteSharkAI | 4.5 |
| Materialized knowledge reuse (no re-fetch) | 4 | WhiteSharkAI | 4.6 |
| smart_search | 4 | WhiteSharkAI | 4.7 |
| smart_outline | 4 | WhiteSharkAI | 4.7 |
| smart_unfold | 4 | WhiteSharkAI | 4.7 |
| smart_unfold — unknown symbol | 4 | WhiteSharkAI | 4.7 |
| PostToolUse buffer accumulation | 4 | WhiteSharkAI | 4.8 |
| 90% Rule — observation warning | 4 | WhiteSharkAI | 4.9 |
| CLAUDE.md protocol section | 4 | WhiteSharkAI | 4.10 |
| materialize_knowledge (explicit) | 4 | WhiteSharkAI | 4.11 |
| find_materializations | 4 | WhiteSharkAI | 4.12 |
| manage_materialization (mark_stale) | 4 | WhiteSharkAI | 4.13 |
| manage_materialization (archive) | 4 | WhiteSharkAI | 4.13 |
| manage_materialization (mark_accessed) | 4 | WhiteSharkAI | 4.13 |
| Delete materialization from UI | 4 | WhiteSharkAI | 4.14 |
| Materialization failure handling | 4 | WhiteSharkAI | 4.15 |
| Session buffer flush on Stop | 4 | WhiteSharkAI | 4.16 |
| Session stored in Cortex after Stop | 4 | WhiteSharkAI | 4.17 |
| Full context on return session | 5 | MacBookPro_M1 | 5.1–5.3 |
| LeaveOff cycle repeats | 5 | MacBookPro_M1 | 5.4 |
| One LeaveOff per project (upsert) | 5 | MacBookPro_M1 | 5.5 |
| Multi-project LeaveOff isolation | 5 | MacBookPro_M1 | 5.6 |
| Extension sync — drift detection | 5 | MacBookPro_M1 | 5.7 |
| Extension sync — unknown local | 5 | MacBookPro_M1 | 5.8 |
| Remote extension install via UI | 5 | MacBookPro_M1 | 5.9 |

---

## Pass/Fail Checklist

Use this checklist during test execution. Mark each item Pass (P), Fail (F), or Skip (S) with notes.

**Test execution started:** 2026-03-14, MacBookPro_M1
**Cortex server:** 172.16.1.230 (API :8181, MCP :8051)
**Test project:** RecipeRaiders (2d747998-7c66-46bb-82a9-74a6dcffd6c2)
**Secondary project tested:** MemeCoinInvestor2026 (320fe077-18c6-4082-944a-969f53659aac)

### Day 1 — MacBookPro_M1

| # | Test | P/F/S | Notes |
|---|------|-------|-------|
| 1.1 | MCP page shows download card with both buttons | P | Both .sh and .bat buttons visible |
| 1.2 | cortexSetup.sh runs to completion on Mac | P | Required fixes: venv creation (--clear flag, Python 3.10+ detection), pip upgrade before install, chmod after tarball extract. Also tested on MemeCoinInvestor2026 (clean repo) — passed. |
| 1.3 | All expected files created in .claude/ | P | cortex-config.json, cortex-state.json, plugins/cortex-memory/, skills/ (14 extensions), settings.local.json all present |
| 1.4 | /cortex-setup registers system and installs extensions | P | System: Jasons-M1-MAX-2.local (925ebc1a). Bootstrap response optimized from ~12.5k to ~500 tokens (content moved to HTTP tarball). 9 extensions verified. |
| 1.5 | `<cortex-context>` block injected at session start | P | Required fixes: (1) hooks must be in ~/.claude/settings.json for SessionStart/Stop (not settings.local.json), (2) plugin Python deps must be installed in venv, (3) venv --clear to prevent stale symlinks. "No recent context available" shown correctly for first session. |
| 1.6 | manage_rag_source ingests docs successfully | P | RecipeRaiders: 52 files already ingested (detected, no re-sync). MemeCoinInvestor2026: 49 files ingested fresh, 53 chunks created, source ID 407ea00b345893e8. |
| 1.7 | Knowledge source visible in Cortex UI | P | 149 document chunks visible for RecipeRaiders Documentation source |
| 1.8 | Knowledge tab shows project-scoped sources | P | Source listed in left panel, document chunks browsable with pagination in right panel |
| 1.9 | RAG search respects project_id filter | P | Searched "subscription gates" scoped to RecipeRaiders — returned relevant chunks about subscription tiers, gate functions, and implementation details. No cross-project contamination. |
| 1.10 | Claude saves LeaveOff Point after coding task | P* | *Tool works when prompted — Claude successfully called manage_leaveoff_point with comprehensive content, next_steps, references. Not yet automatic (requires explicit prompt). LeaveOff Protocol now injected via SessionStart hook. See docs/gaps/leaveoff-protocol-injection.md for improvement plan. |
| 1.11 | LeaveOff Point record in database | P | Record confirmed in `cortex_leaveoff_points` table via Cortex API — project_id matches, component and next_steps populated. |
| 1.12 | LeaveOffPoint.md written to .cortex/knowledge/ | P | Required fix: server-side `_write_file()` can't write to remote client filesystem. Added local materialization to `session_end_hook.py` — fetches LeaveOff from API and writes `.cortex/knowledge/LeaveOffPoint.md` on the client machine. Also fixed hooks to use venv Python (system python3 lacked httpx). |

#### Bugs Found and Fixed During Day 1

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Bootstrap MCP response ~12.5k tokens | `_handle_bootstrap` returned full SKILL.md content for all extensions | Added `/cortex-setup/extensions.tar.gz` HTTP endpoint; shell script downloads tarball; bootstrap returns metadata only |
| SessionStart hook not firing | Hooks in `settings.local.json` — Claude Code only supports SessionStart/Stop in global `~/.claude/settings.json` | Split hooks: lifecycle → global settings, PostToolUse → project settings |
| Plugin Python deps not installed | Setup script extracted tarball but never ran pip install | Added venv creation + pip install step to setup script |
| Venv created with wrong Python | macOS had Python 3.8 (system) and 3.13 (homebrew); `python3 -m venv` picked 3.8, pip used 3.13, site-packages mismatch | Added Python 3.10+ detection loop, `--clear` flag, stale venv removal, pip upgrade before install |
| File permissions after tarball extract | `requirements.txt` had no read permission | Added `chmod -R u+r` after extraction |
| LeaveOffPoint.md never written to repo | `LeaveOffService._write_file()` runs server-side but project dir is on the remote client — path doesn't exist on server | Added local materialization to `session_end_hook.py`: fetches LeaveOff from API at session end and writes `.cortex/knowledge/LeaveOffPoint.md` on the client machine |
| SessionStart/Stop hooks using system python3 | `settings.local.json` had `python3` for lifecycle hooks but httpx is only in the plugin venv | Fixed hook commands to use `.claude/plugins/cortex-memory/.venv/bin/python` for all three hooks |
| `.cortex/` not in .gitignore | Setup script didn't include `.cortex/` in the gitignore entries | Added `.cortex/` to both `cortexSetup.sh` and `cortexSetup.bat` gitignore lists |
| MCP session errors (400 Bad Request) | Docker container rebuilds invalidated active MCP sessions | Restarted cortex-mcp container |
| LeaveOff Protocol not injected to user projects | Protocol only existed in Cortex's own CLAUDE.md, not in any extension or hook output | Added `_leaveoff_protocol_section()` to `session_start_hook.py` — injects protocol with project_id into `<cortex-context>` |

### Day 2 — WIN_AI_PC

| # | Test | P/F/S | Notes |
|---|------|-------|-------|
| 2.1 | cortexSetup.bat runs on Windows | | |
| 2.2 | Windows config files created correctly | | |
| 2.3 | /cortex-setup works on Windows | | |
| 2.4 | Extensions tab shows WIN_AI_PC registered | | |
| 2.5 | MacBookPro_M1 shows in RecipeRaiders extensions | | |
| 2.6 | /link-to-project establishes child hierarchy | | |
| 2.7 | Project filter works on Knowledge page | | |
| 2.8 | SessionStart without LeaveOff shows correct context | | |

### Day 3 — WIN_AI_PC WSL

| # | Test | P/F/S | Notes |
|---|------|-------|-------|
| 3.1 | cortexSetup.sh works on WSL Ubuntu | | |
| 3.2 | WIN_AI_PC-WSL registered as separate system | | |
| 3.3 | LeaveOff Point from Day 1 loaded in WSL session | | |
| 3.4 | Claude references previous work correctly | | |
| 3.5 | Autonomous materialization triggered by codebase-analyst | | |
| 3.6 | Materialized file has correct YAML frontmatter and content | | |
| 3.7 | .cortex/index.md updated | | |
| 3.8 | Materialized toggle shows entry in UI | | |
| 3.9 | Toggle off returns to normal view | | |
| 3.10 | Duplicate topic returns existing record | | |
| 3.11 | Case-insensitive deduplication works | | |
| 3.12 | Claude updates (not duplicates) LeaveOff Point | | |
| 3.13 | Exactly 1 LeaveOff record per project in DB | | |

### Day 4 — WhiteSharkAI

| # | Test | P/F/S | Notes |
|---|------|-------|-------|
| 4.1 | cortexSetup.sh works on Ubuntu bare metal (global scope) | | |
| 4.2 | All 3 RecipeRaiders machines in Extensions tab | | |
| 4.3 | LeaveOff Point from Day 3 loaded on WhiteSharkAI | | |
| 4.4 | cortex_search_sessions finds previous sessions | | |
| 4.5 | cortex_get_session returns full detail | | |
| 4.6 | Materialized knowledge reused without re-fetch | | |
| 4.7a | smart_search returns ranked symbol results | | |
| 4.7b | smart_outline returns folded file structure | | |
| 4.7c | smart_unfold returns single function source | | |
| 4.7d | smart_unfold with unknown symbol lists available names | | |
| 4.8 | Buffer accumulates tool observations | | |
| 4.9 | 90% Rule warning fires at 80+ observations | | |
| 4.10 | CLAUDE.md has LeaveOff Point Protocol section | | |
| 4.11 | materialize_knowledge creates new topic file | | |
| 4.12 | find_materializations returns both materializations | | |
| 4.13a | manage_materialization mark_stale updates status | | |
| 4.13b | manage_materialization archive updates status | | |
| 4.13c | manage_materialization mark_accessed increments count | | |
| 4.14 | Delete from UI removes record and file | | |
| 4.15 | Nonexistent topic returns failure, no orphaned records | | |
| 4.16 | Buffer cleared after session ends | | |
| 4.17 | Session stored in Cortex after Stop | | |

### Day 5 — MacBookPro_M1 (Return)

| # | Test | P/F/S | Notes |
|---|------|-------|-------|
| 5.1 | Full context block shows on return session | | |
| 5.2 | Context sections appear in correct order | | |
| 5.3 | Claude accurately describes previous work from context | | |
| 5.4 | LeaveOff Point cycle continues on Day 5 | | |
| 5.5 | Exactly 1 LeaveOff record per project | | |
| 5.6 | Two separate LeaveOff records, one per project | | |
| 5.7 | Extension sync detects local drift | | |
| 5.8 | Unknown local extension discovered and uploadable | | |
| 5.9 | Remote install via UI propagates to target machine | | |

---

## Troubleshooting Reference

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Setup script hangs at project search | Cortex server unreachable | Check `http://cortex.local:8181/api/projects` returns 200 |
| `manage_leaveoff_point` not found | MCP module not registered | `docker compose logs cortex-mcp \| grep leaveoff` — rebuild if missing |
| LeaveOff Point not in session context | Plugin not configured or Cortex unreachable | Check `.claude/cortex-config.json` exists; verify Cortex API at port 8181 |
| Materialization returns no_relevant_content | Topic not in knowledge base | Verify docs were crawled for the topic via Knowledge page |
| 500 error on LeaveOff PUT | DB migration not applied | Run `019_add_leaveoff_points.sql` in Supabase |
| 500 error on materialization POST | DB migration not applied | Run `018_add_materialization_history.sql` in Supabase |
| Buffer file not found | Global vs local install mismatch | Check both `~/.claude/` and `.claude/` paths |
| System shows "offline" in Extensions tab | `last_seen_at` > 5 minutes ago | Run `/cortex-setup` or `/cortex-extension-sync` to ping Cortex |
| Wrong project linked | Old cortex-state.json | Delete `.claude/cortex-state.json` and re-run setup script |
| Extension sync finds no changes | Already in sync | Expected — no action needed |
| Smart explore tools not found | cortex-memory plugin not registered | Check `.mcp.json` in plugin directory; verify MCP server is running |
| Context not loading on session start | Cortex server down | Check `http://cortex.local:8181/api/projects`; restart Cortex stack |
| Duplicate LeaveOff records | Migration UNIQUE constraint missing | Verify `project_id UNIQUE` in `cortex_leaveoff_points` schema |
