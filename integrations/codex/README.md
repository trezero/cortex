# Cortex Codex Integration

Cortex distributes reviewed skills to Codex without changing its existing
Claude Code extension flow.

## Model

- `cortex_extensions.content` is the agent-neutral source.
- `cortex_extension_targets` is the reviewed delivery contract for an agent.
- Each target records the exact source digest, `direct` or `adapted` mode,
  `repository` or `global` scope, payload snapshot, payload digest, reviewer,
  and review time.
- Compatibility is derived. A target is `pending`, `stale`, `invalid`, or
  `current`; these states are not manually assigned.
- Cortex is authoritative. External registries may be imported once but are not
  read during normal status or synchronization.

Codex locations:

| Scope | Path |
|---|---|
| Repository | `<repo>/.agents/skills/<name>/SKILL.md` |
| Global | `~/.agents/skills/<name>/SKILL.md` |

Repository is the default. A global target must be explicitly reviewed with
global scope.

## Bootstrap

Run this from the repository to associate with a Cortex project:

```bash
curl -fsS http://CORTEX_HOST:8051/cortex-codex-setup.sh -o /tmp/cortex-codex-setup.sh
bash /tmp/cortex-codex-setup.sh --project-id PROJECT_UUID
```

The bootstrap:

1. installs the dependency-free client at `~/.local/bin/cortex-codex`;
2. writes `.cortex/codex.json`;
3. registers the Cortex MCP endpoint with `codex mcp`;
4. merges a quiet, deterministic SessionStart status hook without replacing
   existing hooks.

Use `--no-hook` to skip the hook. The hook does not invoke a model and emits no
routine output.

## Commands

```bash
cortex-codex --project-root "$PWD" status
cortex-codex --project-root "$PWD" sync
cortex-codex --project-root "$PWD" review SKILL_NAME \
  --mode direct --scope repository
```

For adapted payloads:

```bash
cortex-codex review SKILL_NAME --mode adapted --scope repository \
  --payload /path/to/adapted/SKILL.md
```

`sync` refuses unmanaged name conflicts and duplicate global/repository names.
Managed replacements use a staged directory and archive the prior version
before activation. Failed activation restores the prior version. Scope changes
install the reviewed target first and then archive the old managed copy.

## One-Time Registry Import

The import command publishes shared sources to Cortex, links them to the
project, verifies every source digest, and creates reviewed Codex targets:

```bash
cortex-codex --project-root "$PWD" import-registry \
  --registry config/codex/shared-skill-registry.json \
  --shared-root SHARED_SKILLS \
  --adapted-root .codex/skills
```

After a successful import, retire the external registry as an active sync
authority. Future source edits make the Cortex target `stale` until a person or
agent explicitly reviews and republishes it.

## Rollback

Client rollback:

1. Stop using the SessionStart hook or remove only the hook entry whose command
   contains `cortex-codex`.
2. Restore a skill directory from `.cortex/backups/codex-skills/` for repository
   scope or `~/.local/state/cortex/backups/codex-skills/` for global scope.
3. Remove `.cortex/codex.json` and `~/.local/bin/cortex-codex` if fully
   disconnecting Codex.

Server rollback, after clients are disconnected:

```sql
DROP TABLE IF EXISTS cortex_extension_targets;
DROP INDEX IF EXISTS idx_cortex_systems_fingerprint_agent;
ALTER TABLE cortex_systems DROP COLUMN IF EXISTS agent;
ALTER TABLE cortex_systems ADD CONSTRAINT cortex_systems_fingerprint_key UNIQUE (fingerprint);
DELETE FROM cortex_migrations WHERE migration_name = '039_add_extension_agent_targets';
```

Do not use the server rollback if the same fingerprint has separate Claude and
Codex rows; reconcile those rows first or restoring the old uniqueness
constraint will fail.
