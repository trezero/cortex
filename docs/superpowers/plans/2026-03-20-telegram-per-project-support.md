# Telegram Per-Project Bot Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-project bot token isolation to the Telegram plugin so each Claude Code project can use its own Telegram bot.

**Architecture:** A `TELEGRAM_PROJECT_ID` env var (set via project `.claude/settings.local.json`) drives dynamic state directory resolution. Per-project state lives under `~/.claude/channels/telegram/projects/<id>/`. Global fallback is unchanged for backward compatibility. Access config inherits from global on first creation.

**Tech Stack:** TypeScript (Bun), MCP SDK, grammy (Telegram Bot API), Markdown skills

**Spec:** `docs/superpowers/specs/2026-03-20-telegram-per-project-support-design.md`

**Working directory:** The plugin source is at `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.1/`. For PR purposes, fork the upstream repo and apply changes there. During development, modify the cached copy for local testing.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `server.ts` | Modify | Add project ID validation, dynamic STATE_DIR, access bootstrap at startup |
| `skills/configure/SKILL.md` | Modify | Add --project/--global flag parsing, project state dir creation, settings.local.json writes |
| `skills/access/SKILL.md` | Modify | Dynamic state dir resolution via settings.local.json read |
| `ACCESS.md` | Modify | Document per-project directory structure and project ID constraints |
| `README.md` | Modify | Add per-project setup section |

---

### Task 1: Add project ID validation and dynamic STATE_DIR to server.ts

**Files:**
- Modify: `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.1/server.ts:25-52`

- [ ] **Step 1: Add project ID validation function**

After the imports (line 23), before `const STATE_DIR`, add:

```typescript
const GLOBAL_STATE_DIR = join(homedir(), '.claude', 'channels', 'telegram')

function validateProjectId(id: string): void {
  if (id.length > 64) {
    process.stderr.write(`telegram channel: TELEGRAM_PROJECT_ID too long (${id.length} chars, max 64)\n`)
    process.exit(1)
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) {
    process.stderr.write(
      `telegram channel: TELEGRAM_PROJECT_ID contains invalid characters: "${id}"\n` +
      `  allowed: letters, digits, hyphens, underscores\n`,
    )
    process.exit(1)
  }
}
```

- [ ] **Step 2: Replace static STATE_DIR with dynamic resolution**

Replace the existing `const STATE_DIR` block (lines 25-28):

```typescript
// Old:
// const STATE_DIR = join(homedir(), '.claude', 'channels', 'telegram')
// const ACCESS_FILE = join(STATE_DIR, 'access.json')
// const APPROVED_DIR = join(STATE_DIR, 'approved')
// const ENV_FILE = join(STATE_DIR, '.env')
```

With:

```typescript
const PROJECT_ID = process.env.TELEGRAM_PROJECT_ID

if (PROJECT_ID) validateProjectId(PROJECT_ID)

const STATE_DIR = PROJECT_ID
  ? join(GLOBAL_STATE_DIR, 'projects', PROJECT_ID)
  : GLOBAL_STATE_DIR

const ACCESS_FILE = join(STATE_DIR, 'access.json')
const APPROVED_DIR = join(STATE_DIR, 'approved')
const ENV_FILE = join(STATE_DIR, '.env')
```

- [ ] **Step 3: Add access bootstrap after BOOT_ACCESS initialization**

Insert after the closing of the `BOOT_ACCESS` ternary (line 155 is `: null` — the BOOT_ACCESS const spans lines 143-155). Place the bootstrap block immediately after this, before the `loadAccess` function:

**Precondition**: The configure skill creates the per-project `.env` (with the bot token) before the user restarts the session. If the `.env` doesn't exist, the server exits with "TELEGRAM_BOT_TOKEN required" before reaching bootstrap. This is expected — configure must run first.

**Note on intentional redundancy**: The configure skill (Task 2 Step 3, item 7) also copies global access.json at configure time. The server bootstrap here is a safety net for cases where the server starts fresh (e.g., `.env` was manually created). Both paths are intentional — the first to run creates the file, the second is a no-op.

```typescript
// Bootstrap per-project access from global allowlist on first run.
if (PROJECT_ID && !STATIC) {
  try {
    readFileSync(ACCESS_FILE)
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
      // Per-project access.json doesn't exist — bootstrap from global.
      let initial = defaultAccess()
      try {
        const globalRaw = readFileSync(join(GLOBAL_STATE_DIR, 'access.json'), 'utf8')
        const globalAccess = JSON.parse(globalRaw) as Partial<Access>
        if (globalAccess.allowFrom?.length) {
          initial.allowFrom = [...globalAccess.allowFrom]
        }
      } catch {}
      mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 })
      saveAccess(initial)
      process.stderr.write(
        `telegram channel: bootstrapped per-project access for "${PROJECT_ID}"` +
        (initial.allowFrom.length ? ` with ${initial.allowFrom.length} inherited user(s)\n` : '\n'),
      )
    }
  }
}
```

- [ ] **Step 4: Verify no other STATE_DIR references need updating**

Confirm these are all derived from STATE_DIR and need no changes:
- `INBOX_DIR` (line 52) — already `join(STATE_DIR, 'inbox')` ✓
- `assertSendable` — uses `realpathSync(STATE_DIR)` at call time ✓
- `readAccessFile` — uses `ACCESS_FILE` ✓
- `saveAccess` — uses `STATE_DIR` and `ACCESS_FILE` ✓
- `checkApprovals` — uses `APPROVED_DIR` ✓

- [ ] **Step 5: Test locally — global mode unchanged**

Stop any running Claude Code session. Start a new one without `TELEGRAM_PROJECT_ID` set. Verify the bot connects and responds to DMs exactly as before.

- [ ] **Step 6: Test locally — per-project mode**

Create a test project config and verify:
1. Set `TELEGRAM_PROJECT_ID=test` in the environment
2. Verify `~/.claude/channels/telegram/projects/test/` is created
3. Verify `access.json` is bootstrapped from global
4. Verify the bot connects using the per-project `.env` token

- [ ] **Step 7: Test — invalid project ID rejection**

Set `TELEGRAM_PROJECT_ID=../../../etc` and verify the server exits with a clear error message.

- [ ] **Step 8: Commit**

```bash
git add server.ts
git commit -m "feat: add per-project state directory support via TELEGRAM_PROJECT_ID"
```

---

### Task 2: Update the configure skill for --project and --global flags

**Files:**
- Modify: `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.1/skills/configure/SKILL.md`

- [ ] **Step 1: Add Bash(chmod *) to allowed-tools**

Update the frontmatter `allowed-tools` list:

```yaml
allowed-tools:
  - Read
  - Write
  - Bash(ls *)
  - Bash(mkdir *)
  - Bash(chmod *)
```

- [ ] **Step 2: Add per-project concepts to the dispatch section**

After the existing "Dispatch on arguments" heading, add a new section before "No args — status and guidance":

```markdown
## State directory resolution

Before any operation, determine which mode is active:

1. Read `.claude/settings.local.json` in the current project root (if it exists)
2. Check for `TELEGRAM_PROJECT_ID` in the `env` → `mcpServers` → `telegram` block
3. If found: state dir is `~/.claude/channels/telegram/projects/<id>/`
4. If not found: state dir is `~/.claude/channels/telegram/` (global)

Use this resolved state dir for ALL file operations below.

## Project ID validation

When `--project <name>` is used, validate the name:
- Allowed: `[a-zA-Z0-9_-]` only
- Max length: 64 characters
- Reject with a clear error if invalid
```

- [ ] **Step 3: Add --project dispatch block**

Add a new dispatch case:

```markdown
### `--project <name> <token>` — per-project setup

1. Validate `<name>` against project ID constraints. Reject if invalid.
2. Set state dir to `~/.claude/channels/telegram/projects/<name>/`.
3. `mkdir -p <state_dir>`
4. Read existing `<state_dir>/.env` if present; update/add `TELEGRAM_BOT_TOKEN=` line.
   Write back, no quotes around the value.
5. `chmod 600 <state_dir>/.env`
6. Read `.claude/settings.local.json` (create if missing). Set the MCP server env var for the telegram server.
   Write back with 2-space indent. The resulting JSON structure must be:
   ```json
   {
     "env": {
       "mcpServers": {
         "telegram": {
           "TELEGRAM_PROJECT_ID": "<name>"
         }
       }
     }
   }
   ```
   Merge into any existing keys — don't overwrite the whole file. Claude Code passes env vars
   from `env.mcpServers.<server-name>` to the corresponding MCP server process at startup.
7. If global `~/.claude/channels/telegram/access.json` exists and has `allowFrom` entries,
   AND `<state_dir>/access.json` does NOT exist:
   copy it as the initial per-project access.json.
8. Confirm: show project name, state dir, token status, inherited users count.
9. Remind: "Restart your Claude Code session (or run `/reload-plugins`) for the
   MCP server to pick up the new project configuration."

### `--project <name>` (no token) — project status

Show status for the named project: token set/not-set, access summary, state dir path.

### `--global <token>` — global setup

Same as the existing bare-token behavior. Saves to `~/.claude/channels/telegram/.env`.

### `--global` (no token) — global status

Show global status: token, access, state dir.
```

- [ ] **Step 4: Update the no-args status section**

Update the existing "No args — status and guidance" section to also show:
- Whether per-project mode is active (check `.claude/settings.local.json`)
- If active: which project, and a note about the per-project state dir
- If not active: current global behavior, with a note about `--project` option

- [ ] **Step 5: Update the `clear` command for per-project awareness**

The existing `clear` subcommand removes the token. Update it to be mode-aware:
- If per-project mode is active: clear the per-project `.env` token AND remove `TELEGRAM_PROJECT_ID` from `.claude/settings.local.json`
- If global mode: existing behavior (remove global `.env` token)

- [ ] **Step 6: Commit**

```bash
git add skills/configure/SKILL.md
git commit -m "feat: add --project and --global flags to configure skill"
```

---

### Task 3: Update the access skill for per-project state resolution

**Files:**
- Modify: `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.1/skills/access/SKILL.md`

- [ ] **Step 1: Add state directory resolution section**

After the "State shape" section and before "Dispatch on arguments", add:

```markdown
## State directory resolution

Before any operation, determine the active state directory:

1. Read `.claude/settings.local.json` in the current project root (if it exists)
2. Check for `TELEGRAM_PROJECT_ID` in the `env` → `mcpServers` → `telegram` block
3. If found: state dir is `~/.claude/channels/telegram/projects/<id>/`
4. If not found: state dir is `~/.claude/channels/telegram/` (global)

Use this resolved state dir for ALL file paths below:
- `access.json` → `<state_dir>/access.json`
- `approved/` → `<state_dir>/approved/`

When showing status, always display which mode is active and the resolved path.
```

- [ ] **Step 2: Update the pair command to use resolved approved/ path**

In the `pair <code>` section, update step 7 — both the `mkdir` and the file write use a hardcoded global path. Replace both with the resolved state dir:

```markdown
7. `mkdir -p <state_dir>/approved` then write
   `<state_dir>/approved/<senderId>` with `chatId` as the
   file contents. The channel server polls this dir and sends "you're in".
```

- [ ] **Step 3: Update status display**

In the "No args — status" section, add:
- Show active mode: "Per-project: cortex" or "Global"
- Show state dir path

- [ ] **Step 4: Commit**

```bash
git add skills/access/SKILL.md
git commit -m "feat: add per-project state resolution to access skill"
```

---

### Task 4: Update ACCESS.md documentation

**Files:**
- Modify: `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.1/ACCESS.md`

- [ ] **Step 1: Add per-project section after the "At a glance" table**

```markdown
## Per-project mode

By default, all Claude Code sessions share one bot and one access config. Per-project mode gives each project its own bot, access policy, and message inbox.

### Setup

```
/telegram:configure --project myproject 123456789:AAH...
```

This creates a project-scoped state directory and writes `TELEGRAM_PROJECT_ID` to the project's `.claude/settings.local.json`. The MCP server reads this at startup and uses the project-specific state.

### How it works

| | Global (default) | Per-project |
| --- | --- | --- |
| State dir | `~/.claude/channels/telegram/` | `~/.claude/channels/telegram/projects/<id>/` |
| Bot token | Shared across sessions | One per project |
| Access policy | Shared | Independent (bootstrapped from global on first run) |
| Inbox | Shared | Separate per project |

### Project ID rules

- Allowed characters: letters, digits, hyphens, underscores (`[a-zA-Z0-9_-]`)
- Maximum length: 64 characters
- Used as a directory name — no path separators allowed

### Access inheritance

When a per-project `access.json` is created for the first time, it inherits the `allowFrom` list from the global config. After that, the per-project config is independent.
```

- [ ] **Step 2: Commit**

```bash
git add ACCESS.md
git commit -m "docs: document per-project mode in ACCESS.md"
```

---

### Task 5: Update README.md with per-project setup guide

**Files:**
- Modify: `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.1/README.md`

- [ ] **Step 1: Add per-project section after "Access control"**

```markdown
## Per-project bots

Use separate Telegram bots for different projects. Each Claude Code session connects to its project's bot.

**1. Create a bot per project** with [@BotFather](https://t.me/BotFather) — give each a descriptive username (e.g. `@myproject_dev_bot`).

**2. Configure each project.** In the project's Claude Code session:

```
/telegram:configure --project myproject 123456789:AAH...
```

This saves the token to a project-specific directory and sets `TELEGRAM_PROJECT_ID` in the project's local settings.

**3. Restart** the Claude Code session (the MCP server reads the project ID at startup).

**4. Pair** by DMing the project's bot — your allowlist carries over from the global config on first setup.

**5. Run multiple sessions** — each project directory launches its own bot:

```sh
# Terminal 1
cd ~/projects/alpha && claude --channels plugin:telegram@claude-plugins-official

# Terminal 2
cd ~/projects/beta && claude --channels plugin:telegram@claude-plugins-official
```

DM `@alpha_dev_bot` to reach Terminal 1, `@beta_dev_bot` to reach Terminal 2.

See [ACCESS.md](./ACCESS.md) for details on per-project access control.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add per-project bot setup guide to README"
```

---

### Task 6: End-to-end manual verification

- [ ] **Step 1: Test backward compatibility — no project ID**

1. Remove any `TELEGRAM_PROJECT_ID` from `.claude/settings.local.json`
2. Start Claude Code with `--channels plugin:telegram@claude-plugins-official`
3. Verify bot connects and DMs work as before
4. Verify state is in `~/.claude/channels/telegram/` (global)

- [ ] **Step 2: Test per-project setup flow**

1. In a test project directory, run `/telegram:configure --project testproj <your-test-bot-token>`
2. Verify `~/.claude/channels/telegram/projects/testproj/.env` was created
3. Verify `.claude/settings.local.json` contains `{"env":{"mcpServers":{"telegram":{"TELEGRAM_PROJECT_ID":"testproj"}}}}`
4. Restart Claude Code session
5. Verify bot connects as the test bot
6. Verify access was bootstrapped from global (check `access.json`)

- [ ] **Step 3: Test two projects simultaneously**

1. Open Terminal 1: `cd ~/projects/Trinity/cortex && claude --channels plugin:telegram@claude-plugins-official`
2. Open Terminal 2: a different project with a different bot token configured
3. DM each bot and verify messages route to the correct session

- [ ] **Step 4: Test edge cases**

1. `/telegram:configure --project ../../bad` → should reject with validation error
2. `/telegram:configure --project` (no name) → should show usage help
3. `/telegram:configure --global` (no token) → should show global status
4. A project with no global access.json → should bootstrap with empty allowlist

- [ ] **Step 5: Final commit — version bump if appropriate**

```bash
git commit -m "test: verify per-project bot support end-to-end"
```
