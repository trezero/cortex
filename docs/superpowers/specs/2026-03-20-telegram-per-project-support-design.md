# Telegram Plugin: Per-Project Bot Support

**Date**: 2026-03-20
**Status**: Design approved
**Target**: PR to Anthropic's claude-plugins-official repository

## Problem

The Telegram plugin for Claude Code stores its bot token and access config in a single global location (`~/.claude/channels/telegram/`). Users running multiple Claude Code sessions across different projects cannot use separate Telegram bots — every session shares the same bot and access policy.

## Solution

Add per-project state isolation via a `TELEGRAM_PROJECT_ID` environment variable. Each project can configure its own bot token and access policy in a project-scoped subdirectory, while the global config remains the default fallback.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Bot model | One bot per project | Clean isolation, distinct @usernames per project |
| Token storage | Project-level env var via `.claude/settings.local.json` | Uses existing Claude Code infrastructure |
| Access control | Per-project with global inheritance | New projects bootstrap from global allowlist, then diverge |
| Backward compatibility | Fully backward compatible | No flag = global behavior, identical to current plugin |
| Configure UX | Explicit `--project` and `--global` flags | No ambiguity about where token is saved |

## Architecture

### State Directory Resolution

```
TELEGRAM_PROJECT_ID set?
├── Yes → ~/.claude/channels/telegram/projects/<project-id>/
│         ├── .env              (bot token)
│         ├── access.json       (per-project access policy)
│         ├── inbox/            (downloaded photos)
│         └── approved/         (pairing approval signals)
└── No  → ~/.claude/channels/telegram/     (current global behavior, unchanged)
```

The project ID is a short, user-chosen name (e.g., "cortex", "reciperaiders") used as the directory name.

#### Project ID Constraints

Project IDs must be validated before use in filesystem paths:
- Allowed characters: `[a-zA-Z0-9_-]` (alphanumeric, hyphens, underscores)
- Path separators (`/`, `\`, `..`) are explicitly rejected to prevent path traversal
- Maximum length: 64 characters
- Validation occurs both in the configure skill (at creation) and in `server.ts` (at startup)

### Server Code Changes (server.ts)

~20-30 lines changed. Changes are in the state directory resolution and access bootstrap:

1. **Dynamic STATE_DIR** — At startup, read `process.env.TELEGRAM_PROJECT_ID`:
   - **Critical**: `TELEGRAM_PROJECT_ID` is read exclusively from `process.env` (inherited from the MCP server's env block in `.claude/settings.local.json`), NOT from any `.env` file. The `.env` file only contains `TELEGRAM_BOT_TOKEN`.
   - If set and valid: `STATE_DIR = join(homedir(), '.claude', 'channels', 'telegram', 'projects', projectId)`
   - If not set: `STATE_DIR = join(homedir(), '.claude', 'channels', 'telegram')` (unchanged)
   - If set but invalid (fails validation): log error to stderr and exit (fail fast)
   - All derived paths (`ACCESS_FILE`, `APPROVED_DIR`, `ENV_FILE`, `INBOX_DIR`) are already relative to `STATE_DIR`

2. **Access bootstrap at startup** — After resolving `STATE_DIR`, if `TELEGRAM_PROJECT_ID` is set and the per-project `access.json` does not exist:
   - Read the global `~/.claude/channels/telegram/access.json`
   - If it exists and has `allowFrom` entries, use those as the initial per-project allowlist
   - Save the bootstrapped per-project `access.json` via `saveAccess()`
   - This runs once at startup, NOT lazily inside `readAccessFile()` — keeps the read function side-effect-free
   - In `STATIC` mode, bootstrap is skipped (consistent with static mode's no-write behavior)

3. **No other changes** — Bot logic, gate, MCP tools, chunking, inbox, approvals all reference `STATE_DIR`-relative paths already.

### Configuration Flow

#### Per-project setup
```
/telegram:configure --project cortex 123456789:AAH...
```

Actions:
1. Create `~/.claude/channels/telegram/projects/cortex/`
2. Save bot token to `~/.claude/channels/telegram/projects/cortex/.env`
3. Write `TELEGRAM_PROJECT_ID=cortex` to the project's `.claude/settings.local.json` env block (for MCP server inheritance)
4. If global `access.json` exists with `allowFrom` entries, copy as initial per-project `access.json`
5. Display status confirming per-project mode

#### Global setup (unchanged)
```
/telegram:configure --global 123456789:AAH...
```
Saves to `~/.claude/channels/telegram/.env` — identical to current behavior.

#### Bare token (backward compatible)
```
/telegram:configure 123456789:AAH...
```
Works exactly as today — saves globally. Existing users unaffected.

#### Status check
```
/telegram:configure
```
Shows active mode (global or project), project ID if applicable, token status, and access summary.

### Skill Changes

#### /telegram:configure
- Parse `--project <name>` and `--global` flags from `$ARGUMENTS`
- Validate project ID against constraints (alphanumeric, hyphens, underscores only; max 64 chars)
- `--project <name> <token>`: create project state dir, save token with `chmod 600`, update `.claude/settings.local.json`
- `--project <name>` (no token): show status for that project
- `--global <token>`: current behavior
- `--global` (no token): show global status
- Bare `<token>`: current behavior (global)
- No args: show active mode status
- **After saving**: remind user to restart Claude Code session (or `/reload-plugins`) for the MCP server to pick up the new `TELEGRAM_PROJECT_ID` env var
- **Allowed tools update needed**: add `Bash(chmod *)` to the skill's `allowed-tools` list (pre-existing gap)

#### /telegram:access
- Resolve state directory by reading `TELEGRAM_PROJECT_ID` from `.claude/settings.local.json` (the skill runs as Claude, not inside the MCP server, so it reads the config file directly rather than `process.env`)
- All commands (pair, allow, remove, policy, group, set) work against the resolved state directory — both `access.json` AND the `approved/` directory for pairing signals
- Status display indicates which project's access is being shown (project name and state directory path)

### No Changes Required
- MCP tools (reply, react, edit_message) — unchanged (they use `STATE_DIR`-relative paths at runtime)
- Bot message handling — unchanged
- `access.json` schema — same structure

## User Workflow

### Initial setup (first project)
```bash
# 1. Create bot via @BotFather in Telegram
# 2. In Claude Code, in the project directory:
/telegram:configure --project cortex 123456789:AAH...
# 3. DM the new bot, pair as usual:
/telegram:access pair a4f91c
```

### Adding a second project
```bash
# 1. Create another bot via @BotFather
# 2. In Claude Code, in the second project directory:
/telegram:configure --project reciperaiders 987654321:BBX...
# 3. allowFrom is pre-populated from global config — already paired
# 4. Start two Claude Code sessions, each in its project directory
# 5. Message each bot's DM to reach the respective session
```

## File Changes Summary

| File | Change |
|---|---|
| `server.ts` | Dynamic STATE_DIR based on TELEGRAM_PROJECT_ID; project ID validation; access bootstrap at startup |
| `skills/configure/SKILL.md` | Add --project and --global flag handling; add `Bash(chmod *)` to allowed-tools; restart reminder |
| `skills/access/SKILL.md` | Resolve state dir by reading TELEGRAM_PROJECT_ID from settings.local.json; update approved/ path resolution |
| `ACCESS.md` | Document per-project state directory structure, project ID constraints |
| `README.md` | Add per-project usage section |

## Backward Compatibility

- No `TELEGRAM_PROJECT_ID` set → plugin behaves identically to current version
- No flag on `/telegram:configure <token>` → saves globally as before
- Existing `access.json` in global location → still read and used
- Zero breaking changes for single-project users

## Future Considerations (Out of Scope for PR)

### Cortex Integration
- **cortexSetup integration**: Optional step to configure a per-project Telegram bot during setup
- **claudePro launcher**: Convenience command to launch Claude Code with project-specific config pre-set
- These are Cortex-specific and would be implemented separately after the upstream PR
