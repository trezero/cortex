## Cortex Knowledge Base — Ambient Behavio

Cortex is a RAG knowledge management system connected via MCP (`cortex` server). It provides semantic search across project documentation and shared cross-project knowledge. Use the `/cortex-memory` skill for explicit operations.

### Session Start — Always Show Status
At the start of every session, check Cortex state and display a **one-liner status** to the user:

1. Check if `.claude/cortex-state.json` exists in the project
2. If yes, read it and note the Cortex `project_id` and `source_id` for searches
3. Check doc freshness: compute MD5 hashes of docs vs stored hashes (use `md5sum <file> | cut -d' ' -f1` on Linux, `md5 -q` on macOS)
4. Display one of these status lines:

   - **Configured & fresh:** `Cortex KB: <project> — <N> docs, synced <relative time>, up to date`
   - **Configured & stale:** `Cortex KB: <project> — <N> docs, synced <relative time>, <N> files changed. Run /cortex-memory sync`
   - **Not configured:** `Cortex KB: not configured. Run /cortex-memory ingest to set up.`
   - **Server unreachable:** `Cortex KB: server unreachable — search unavailable this session`

This check should be quick (read state file + hash a few files). Do NOT call Cortex APIs for this — just use local state.

### During Normal Work
- When needing project context (architecture, patterns, deployment, historic issues):
  PREFER `rag_search_knowledge_base(query, project_id)` over reading raw doc files
- Cortex search is faster and uses less context than reading entire files
- Fall back to direct file reads only when Cortex search returns no relevant results
- For code pattern questions, also try `rag_search_code_examples(query, project_id)`

### When Docs Are Modified
- If documentation files are modified during a session, Cortex knowledge is stale
- Remind user to run `/cortex-memory sync` before ending the session

### Cross-Project Knowledge
- Shared knowledge (framework docs, tool patterns) is available via `~/.claude/cortex-global.json`
- Search shared KB: `rag_search_knowledge_base(query, project_id=shared_project_id)`
