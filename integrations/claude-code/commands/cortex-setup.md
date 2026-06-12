# Cortex Setup — Register This Machine

Connect this machine to Cortex: register it as a system, download all project extensions, and install them locally.

## Phase 0: Health Check

Call `health_check()` via the Cortex MCP tool.

If the tool is not found (MCP not configured), do the following:

1. Check if `cortex-config.json` exists in `.claude/` or `~/.claude/`. If found, read
   `cortex_mcp_url` from it. Otherwise, ask the user:
   > "What is your Cortex MCP URL? (e.g., http://172.16.1.230:8051)"

   Store the answer as `<cortex_mcp_url>`.

2. Tell the user:
   ```
   Cortex MCP is not configured. I'll add it now.
   ```

3. Run:
   ```bash
   claude mcp add --transport http cortex <cortex_mcp_url>/mcp
   ```

4. Tell the user:
   ```
   Cortex MCP has been added. Please restart Claude Code for the new MCP
   connection to take effect, then run /cortex-setup again.
   ```

5. Stop.

If the tool exists but the server is unreachable, print:
```
Cortex server is not reachable. Check that the Cortex stack is running.
```
Stop.

## Phase 1: Load Existing State and Determine Install Scope

Read `.claude/cortex-state.json` if it exists. Extract:
- `system_fingerprint` → `<fingerprint>` (may be absent)
- `system_name` → `<system_name>` (may be absent)
- `cortex_project_id` → `<project_id>` (may be absent)

Read `.claude/cortex-config.json` if it exists (fall back to `~/.claude/cortex-config.json`). Extract:
- `install_scope` → `<install_scope>` (may be absent)

Determine `<install_dir>`:
- If `<install_scope>` is `"global"` → `~/.claude`
- Otherwise (including `"project"` or absent) → `.claude`

**Important:** The default is always project-scoped (`.claude` in the repo root). Extensions,
commands, and plugins must never be installed into `~/.claude` unless the user has explicitly
opted into global scope via their `cortex-config.json`. If the `.claude` directory does not
exist, create it.

## Phase 2: Collect System Info and Compute Fingerprint

Always run these first to capture the current machine identity:

```bash
hostname
```

Store result as `<hostname>`.

```bash
uname -s
```

Store result as `<os>`.

If `<fingerprint>` was not in the state file:

If `<os>` is `Darwin`:
```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | shasum -a 256 | cut -d' ' -f1
```

Otherwise:
```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

Store result as `<fingerprint>`.

## Phase 3: Confirm System Name (if missing)

If `<system_name>` was not in the state file:

Ask the user:
> I'll register this machine as **`<hostname>`**. Press Enter to confirm or type a different name:

Store confirmed name as `<system_name>`.

## Phase 4: Bootstrap

Call:
```
manage_extensions(
    action="bootstrap",
    system_fingerprint="<fingerprint>",
    system_name="<system_name>",
    hostname="<hostname>",
    os="<os>",
    project_id="<project_id>"   ← omit if no project_id
)
```

If the call fails, report the error and stop.

Extract `<system_id>` from `response.system.id` if present, otherwise `"unknown"`.

## Phase 5: Verify Extensions

Extensions are pre-installed by the setup script. Verify they exist:

```bash
ls <install_dir>/skills/*/SKILL.md 2>/dev/null
```

If extensions are found, count them and continue to Phase 6.

If NO extensions are found (setup script download may have failed), download them:

1. Read `cortex_mcp_url` from `.claude/cortex-config.json` (fall back to `~/.claude/cortex-config.json`)
2. Run:

```bash
mkdir -p <install_dir>/skills
curl -sf "<cortex_mcp_url>/cortex-setup/extensions.tar.gz" | tar xz -C "<install_dir>/skills/"
```

3. Verify again with the `ls` command above

## Phase 5b: Update Slash Commands

Download the latest command files from the Cortex server into the repo-local `.claude/commands/` directory:

```bash
mkdir -p <install_dir>/commands && curl -sf "<cortex_mcp_url>/cortex-setup/commands.tar.gz" | tar xz -C "<install_dir>/commands/"
```

If the download fails, warn the user but continue — existing commands will still work.

## Phase 5c: CLAUDE.md Rules Integration

Ensure the project's `CLAUDE.md` includes the recommended Cortex rules for ambient
knowledge base behavior.

1. Read `cortex_mcp_url` from `.claude/cortex-config.json` (fall back to `~/.claude/cortex-config.json`).

2. Download the Cortex rules snippet:

```bash
curl -sf "<cortex_mcp_url>/cortex-setup/claude-md-snippet.md"
```

Store the result as `<snippet>`. If the download fails, warn and skip this phase.

3. Check the state of `CLAUDE.md` in the project root:

**Case A — `CLAUDE.md` does not exist:**

Create `CLAUDE.md` with the snippet wrapped in sentinel markers:

```markdown
<!-- cortex-rules-start -->
<snippet content here>
<!-- cortex-rules-end -->
```

Report: `Created CLAUDE.md with Cortex knowledge base rules.`

**Case B — `CLAUDE.md` exists and contains `<!-- cortex-rules-start -->`:**

The Cortex rules section is already present. Replace everything between
`<!-- cortex-rules-start -->` and `<!-- cortex-rules-end -->` (inclusive of
markers) with the latest snippet wrapped in the same markers. Preserve all
content before and after the markers exactly as-is.

Report: `Updated Cortex rules section in CLAUDE.md to latest version.`

**Case C — `CLAUDE.md` exists but does NOT contain `<!-- cortex-rules-start -->`:**

This is the intelligent merge case. The setup script may have appended the rules
as a raw block, or the user may have manually written equivalent guidance.

Perform the following:

1. Read the full existing `CLAUDE.md` content.
2. Read the `<snippet>` content.
3. Check whether the existing content already covers Cortex-equivalent guidance
   (e.g., mentions `rag_search_knowledge_base`, `/cortex-memory`, Cortex KB
   status checks). If equivalent guidance exists, remove it to avoid duplication.
4. Determine the best insertion point — typically a new top-level section at the
   end of the file, or grouped with other tool/integration sections if they exist.
5. Write the merged `CLAUDE.md` using the Edit or Write tool. The Cortex rules
   **must** be wrapped in the sentinel markers:

```markdown
<!-- cortex-rules-start -->
<snippet content here>
<!-- cortex-rules-end -->
```

6. Report: `Merged Cortex rules into existing CLAUDE.md.`

**Important:** Never delete or modify the user's custom instructions. Only add
or replace the Cortex-specific section. When in doubt about whether existing
content is Cortex-related, leave it in place and add the new section separately.

## Phase 6: Update State

Read `.claude/cortex-state.json` or start with `{}`.

Merge — do not overwrite existing fields like `cortex_project_id`:
- `system_fingerprint`: `<fingerprint>`
- `system_name`: `<system_name>`
- `system_id`: `<system_id>`
- `last_bootstrap`: current ISO 8601 timestamp

Write merged object back to `.claude/cortex-state.json`.

## Phase 7: Report

```
## Cortex Setup Complete

System: <system_name> (<system_id>)
Extensions installed: <N> → <install_dir>/skills/
  - <list each extension name>
Project: <project name if registered, else "No project linked">

Restart Claude Code for the new extensions to take effect.
```

If `response.system.is_new` is `true`, also print:
```
This system has been registered with Cortex for the first time.
```
