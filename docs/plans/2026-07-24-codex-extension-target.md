# Codex Extension Target

Status: in progress

## Objective

Make Codex a first-class Cortex extension consumer without creating a second
registry or changing Claude Code's existing local-first installation behavior.

## Authority

- `cortex_extensions.content` remains the agent-neutral source.
- `cortex_extension_targets` stores one reviewed projection per extension and
  agent.
- A target records the reviewed source hash, direct/adapted mode,
  repository/global scope, immutable payload snapshot, payload hash, reviewer,
  and review time.
- Compatibility is derived: missing target is pending, a source-hash mismatch is
  stale, malformed target data is invalid, and an exact match is current.
- The operating-space Codex JSON registry is an import source only. Cortex
  becomes authoritative after import.

## Delivery

1. Add the target schema and migration.
2. Add backend target CRUD, project target listing, and deterministic sync
   reporting.
3. Add a model-free `cortex-codex` CLI for setup, review, status, sync, scope
   migration, conflict protection, rollback, and registry import.
4. Serve the Codex installer from Cortex.
5. Add target and agent state to the project extensions UI.
6. Test direct/adapted targets, global/repository scope, source drift,
   conflicts, migration, duplicate names, rollback, and failed writes.
7. Deploy the branch to the WSL Cortex checkout, apply the migration, import the
   operating-space registry, and validate from WSL and Blackwell.
