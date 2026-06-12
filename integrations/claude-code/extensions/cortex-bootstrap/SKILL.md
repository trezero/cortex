---
name: cortex-bootstrap
description: Bootstrap Cortex extensions onto this machine. Fetches all extensions from the Cortex registry and installs them locally, registers this system, and links it to the current project. Run once on any new machine to set up Cortex integration. Use when the user says "bootstrap cortex", "install cortex extensions", "set up cortex", or "run cortex bootstrap".
---

# Cortex Bootstrap

Bootstrap Cortex extensions onto this machine by fetching all extensions from the Cortex registry, installing them locally (extension definition files), registering this system, and optionally linking it to the current project.

## Phase 0: Health Check

Call the `health_check()` MCP tool.

If the server is unhealthy or unreachable, print the following error and stop:

```
Cortex server is not reachable. Ensure Cortex is running and configured in .mcp.json or ~/.claude/mcp.json. Cannot bootstrap.
```

## Phase 1: Compute System Fingerprint

Run the following command to detect the operating system:

```bash
uname -s
```

If the output is `Darwin`, use `shasum -a 256` to compute the fingerprint:

```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | shasum -a 256 | cut -d' ' -f1
```

Otherwise (Linux and all other systems), use `sha256sum`:

```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

Store the resulting hash as `<fingerprint>`.

## Phase 2: System Name

Run:

```bash
hostname
```

Ask the user:

> I'll register this machine as **`<hostname>`**. Press Enter to confirm or type a different name:

Store the confirmed name as `<system_name>`.

## Phase 3: Read Project Context and Determine Install Scope

Read `.claude/cortex-state.json` if it exists.

Extract the value of `cortex_project_id` if present and store it as `<project_id>`.

If the file does not exist or the key is absent, `<project_id>` is omitted from the next step.

Read `.claude/cortex-config.json` if it exists (fall back to `~/.claude/cortex-config.json`). Extract:
- `install_scope` → `<install_scope>` (may be absent)

Determine `<install_dir>`:
- If `<install_scope>` is `"global"` → `~/.claude`
- Otherwise (including `"project"` or absent) → `.claude`

**Important:** The default is always project-scoped (`.claude` in the repo root). Extensions and
commands must never be installed into `~/.claude` unless the user has explicitly opted into global
scope via `cortex-config.json`. If the `.claude` directory does not exist, create it.

## Phase 4: Call Bootstrap MCP Tool

Call:

```
manage_extensions(
    action="bootstrap",
    system_fingerprint="<fingerprint>",
    system_name="<system_name>",
    project_id="<project_id>"   ← omit this parameter if no project_id was found
)
```

If the call fails, report the error and stop.

Extract `<system_id>` from `response.system.id` (if `response.system` is present, otherwise use `"unknown"`).

## Phase 5: Download Extension Files

Extensions are delivered via HTTP tarball to avoid bloating the LLM context.

Read `cortex_mcp_url` from `.claude/cortex-config.json` (fall back to `~/.claude/cortex-config.json`).

Download and extract extensions:

```bash
mkdir -p <install_dir>/skills
curl -sf "<cortex_mcp_url>/cortex-setup/extensions.tar.gz" | tar xz -C "<install_dir>/skills/"
```

If the download fails, report the error but continue with Phase 6.

Verify installed extensions:

```bash
ls <install_dir>/skills/*/SKILL.md 2>/dev/null
```

### 5b. Download commands

```bash
mkdir -p "<install_dir>/commands"
curl -sf "<cortex_mcp_url>/cortex-setup/commands.tar.gz" | tar xz -C "<install_dir>/commands/"
```

If the download fails (e.g., no commands registered yet), warn but continue:
> "No commands available from the registry. Commands will be installed during the next extension sync."

## Phase 6: Update State

Read `.claude/cortex-state.json` if it exists, or start with an empty object `{}`.

Merge in the following fields:

- `system_fingerprint`: `<fingerprint>`
- `system_name`: `<system_name>`
- `last_bootstrap`: current timestamp in ISO 8601 format

Merge with existing state — do not overwrite other fields such as `cortex_project_id`.

Write the merged object back to `.claude/cortex-state.json`.

## Phase 7: Report

Print the following summary:

```
## Cortex Bootstrap Complete

**System:** <system_name> (<system_id>)
**Skills installed:** <N> → <install_dir>/skills/
  - <list each skill name>
**Commands installed:** <N> → <install_dir>/commands/
  - <list each command name>
**Project:** <project_title if registered> — or "No project linked"

Restart Claude Code for the new extensions to take effect.
```

If `response.system.is_new` is `true`, also print:

```
This system has been registered with Cortex for the first time.
```

If `<install_scope>` is not `"global"` (i.e., extensions were installed to `.claude/`), also print:

```
Run /cortex-extension-sync to detect and remove any duplicate extensions that
may exist in ~/.claude from a previous global install.
```
