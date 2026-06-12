# Cortex Setup — Guided Machine Onboarding Design

**Goal:** Replace the manual "type a raw MCP tool call" bootstrap experience with a single downloadable setup script that walks the user through connecting a new machine to Cortex in under a minute.

---

## Problem

Currently, connecting a new machine to Cortex requires the user to:

1. Know to add the MCP server manually via `claude mcp add`
2. Understand what `manage_skills(action="bootstrap")` is and type it with the correct parameters

This is not discoverable and produces errors (wrong parameter types, missing system registration, skills not written to disk).

---

## Solution Overview

A downloadable shell script (`cortexSetup.sh` / `cortexSetup.bat`) served directly from the Cortex server. The user downloads it from the MCP page, runs it in their project directory, and it handles everything interactively. After the script completes, the user opens Claude Code and runs `/cortex-setup` to finish registration and install skills.

---

## Components

### 1. Setup Scripts (`cortexSetup.sh` / `cortexSetup.bat`)

Served by the Cortex MCP server. The Cortex server URL is baked into the script at download time so the user never types a URL.

**Interactive CLI flow:**

```
╔══════════════════════════════════════╗
║        Cortex Setup v1.0.0           ║
║  Connecting to: http://192.168.1.10  ║
╚══════════════════════════════════════╝

[1/4] System name
      Detected: Jasons-M1-MAX-2
      Press Enter to accept or type a new name: _

[2/4] Project
      Matched in Cortex: RecipeRaiders
      Press Enter to accept or type to search: _

[3/4] Setting up Claude Code MCP...
      ✓ Added cortex MCP server

[4/4] Installing /cortex-setup command...
      ✓ Installed to ~/.claude/commands/cortex-setup.md

══════════════════════════════════════
✓ Setup complete!

Open Claude Code in this directory and run:
  /cortex-setup

This will register your system and install all project skills.
══════════════════════════════════════
```

**Script responsibilities:**

- Detect OS (macOS/Linux/Windows) and adapt commands accordingly
- Auto-detect system name from `hostname`, let user confirm or override
- Query `GET /api/projects?q=<dirname>` to find matching project
- Handle project selection interactively (see below)
- Run `claude mcp add --transport http cortex <SERVER_URL>/mcp`
- Download `cortex-setup.md` to `~/.claude/commands/cortex-setup.md`
- Write `.claude/cortex-state.json` with `system_name` and `cortex_project_id`

---

### 2. Project Selection

The script calls `GET /api/projects` at startup. Project selection is handled intelligently:

**If directory name matches an Cortex project exactly:**

```
[2/4] Project
      Matched in Cortex: RecipeRaiders
      Press Enter to accept or type to search: _
```

**If no match:**

```
[2/4] Project
      No Cortex project matched "MyApp".
      Search (or press Enter to list all): _
```

**Search results** (calls `GET /api/projects?q=<term>`, max 10 per page):

```
      Results for "recipe":
        1. RecipeRaiders
        2. RecipeRaiders-Backend
        3. RecipeManager-Legacy
        C. Create new project in Cortex

      Enter number, N for next page, new search, or C to create: _
```

- No third-party dependencies (no `fzf`, no `jq` required — pure shell + `curl`)
- Server-side search via `?q=` param — never downloads all 100+ projects at once
- `C` option always visible — user can create a new project if not found

**If user chooses `C` (create new project):**

```
      New project name [MyApp]: _
      Description (optional): _

      Creating project... ✓ Created "MyApp"
      Project ID: 2d747998-7c66-46bb-82a9-74a6dcffd6c2
```

Script calls `POST /api/projects` and continues with the new project ID.

---

### 3. Server Endpoints

Three new endpoints on the Cortex MCP server (`python/src/mcp_server/`):

| Endpoint | Response | Description |
|---|---|---|
| `GET /cortex-setup.sh` | `text/plain` | Shell script with server URL baked in |
| `GET /cortex-setup.bat` | `text/plain` | Windows batch script with server URL baked in |
| `GET /cortex-setup.md` | `text/plain` | The `/cortex-setup` Claude Code slash command |

The scripts are generated dynamically — the server injects its own `request.base_url` so the downloaded script always points back to the correct Cortex instance.

---

### 4. `/cortex-setup` Claude Code Slash Command

Installed to `~/.claude/commands/cortex-setup.md` by the setup script. Replaces the existing `cortex-bootstrap` SKILL.md for the primary onboarding flow.

**Flow:**

1. Read `.claude/cortex-state.json` — extract `system_name`, `cortex_project_id`, `system_fingerprint` if present
2. If `system_fingerprint` missing: compute it (`sha256sum` / `shasum -a 256` based on OS)
3. Call `manage_skills(action="bootstrap", system_fingerprint=..., system_name=..., project_id=...)`
4. Write each skill in the response to `~/.claude/skills/<name>/SKILL.md`
5. Update `.claude/cortex-state.json` with `system_fingerprint`, `system_id`, `last_bootstrap`
6. Print summary: system name, skills installed, project linked

Because `cortexSetup.sh` already collected `system_name` and `cortex_project_id` and wrote them to `cortex-state.json`, `/cortex-setup` runs without asking any questions on first use.

---

### 5. MCP Page UI — "Connect a New Machine" Section

A new section at the top of the MCP page (`/mcp`), above existing content:

```
┌─────────────────────────────────────────────────────────────┐
│  Connect a New Machine                                       │
│                                                             │
│  Download the Cortex setup script and run it in your        │
│  project directory. It will add Cortex to Claude Code       │
│  and install the /cortex-setup command in one step.         │
│                                                             │
│  [ ↓ cortexSetup.sh ]  [ ↓ cortexSetup.bat ]               │
│                                                             │
│  Then open Claude Code and run /cortex-setup                │
└─────────────────────────────────────────────────────────────┘
```

- Two download buttons: Mac/Linux (`.sh`) and Windows (`.bat`)
- Plain-English description — no jargon, no parameters
- The next step (`/cortex-setup`) is called out explicitly

---

## Data Flow

```
User downloads cortexSetup.sh from MCP page
        ↓
Script collects: system_name, project selection/creation
        ↓
Script runs: claude mcp add cortex <URL>/mcp
Script runs: curl -o ~/.claude/commands/cortex-setup.md <URL>/cortex-setup.md
Script writes: .claude/cortex-state.json { system_name, cortex_project_id }
        ↓
User opens Claude Code → runs /cortex-setup
        ↓
Command reads cortex-state.json
Command computes fingerprint (if missing)
Command calls: manage_skills(action="bootstrap", ...)
Command writes: ~/.claude/skills/<name>/SKILL.md for each skill
Command updates: cortex-state.json { system_fingerprint, system_id, last_bootstrap }
        ↓
Done — machine registered, skills installed, project linked
```

---

## What Replaces What

| Old | New |
|---|---|
| Manual `claude mcp add` | Handled by `cortexSetup.sh` |
| Manual `manage_skills(action="bootstrap", ...)` call | Handled by `/cortex-setup` command |
| `cortex-bootstrap` SKILL.md | Superseded by `/cortex-setup` (SKILL.md can remain as natural language fallback) |
| No discoverability | MCP page download buttons |

---

## Out of Scope

- Automatic skill sync on every Claude Code session start (separate feature)
- GUI installer (shell script is sufficient for developer audience)
- Windows PowerShell version (`.bat` covers Windows for now)
