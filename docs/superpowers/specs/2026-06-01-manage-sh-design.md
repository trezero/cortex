# manage.sh — Interactive Docker CLI

## Purpose

A looping interactive shell script at the repo root that manages all Archon Docker services, with automatic Docker credential store remediation to prevent WSL2 credential helper failures.

## Problem Solved

Running `docker compose up --build` from WSL2 fails with `error getting credentials - err: exit status 1, out: A specified logon session does not exist` when `~/.docker/config.json` contains `"credsStore": "desktop.exe"`. This calls the Windows Credential Manager via `docker-credential-desktop.exe`, which fails when the Windows session is in a bad state. The fix is to remove that key so Docker uses the embedded `auths` block directly.

## Location

`manage.sh` — repo root, alongside `Makefile` and `docker-compose.yml`.

## Services Managed

All four core services as a group (no individual selection):

- `archon-server` (FastAPI backend, port 8181)
- `archon-mcp` (MCP server, port 8051)
- `archon-agents` (AI agents service, port 8052)
- `archon-frontend` (Vite/React UI, port 3737)

The optional `trinity-a2ui` service (profile: `trinity`) is out of scope.

## Credential Guard

Runs once at script startup, before the menu is shown:

1. Check if `~/.docker/config.json` exists and contains `"credsStore"`.
2. If found: remove the key using `jq` (preferred) with `sed` as fallback, print a one-line notice.
3. If already clean: silent, no output.

This ensures the credential error cannot occur from any operation this script performs.

## Menu

Uses bash's built-in `select` loop. Loops back to the menu after every operation.

```
Archon Manager
==============
1) Start
2) Stop
3) Restart
4) Rebuild & Restart
5) Status
6) Quit
```

### Operations

| Option | Command | Post-action |
|--------|---------|-------------|
| Start | `docker compose up -d` | Stream logs (Ctrl+C returns to menu) |
| Stop | `docker compose down` | Return to menu |
| Restart | `docker compose down` then `docker compose up -d` | Stream logs |
| Rebuild & Restart | `docker compose up -d --build` | Stream logs |
| Status | `docker compose ps` | Return to menu |
| Quit | `exit 0` | — |

Log streaming uses `docker compose logs -f`. Ctrl+C interrupts the log tail only — containers keep running.

## Structure & Behavior

- **Working directory**: script `cd`s to its own directory on startup so `docker-compose.yml` is always found regardless of where the user invokes it from.
- **Preflight check**: verifies `docker` and `docker compose` are available; exits with a clear message if not.
- **Timestamped headers**: each operation prints `[HH:MM:SS] <action>...` before executing.
- **Error handling**: non-zero Docker exit codes print the error and return to the menu; they do not crash the script.
- **No external dependencies** beyond `docker`, `docker compose`, and optionally `jq` (with `sed` fallback for credential fix).
- **Executable**: ships with `chmod +x manage.sh`.

## Out of Scope

- Individual service targeting
- Profile selection (trinity, backend, full)
- Log filtering or tailing specific services
- Environment variable management
