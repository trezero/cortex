# Postman Integration Design — Dual-Mode

**Date**: 2026-03-09
**Status**: Approved (v3 — dual-mode: API + Git YAML)
**Feature**: Automatic Postman collection and environment management per Cortex project

## Overview

Automatically maintain a Postman collection and environment per Cortex project so that every API endpoint Claude suggests testing is captured as a reusable, executable Postman request — replacing ad-hoc curl commands with a living API test suite.

**Two sync modes, one behavioral extension:**

| Mode | How It Works | Requires |
|------|-------------|----------|
| `api` | Claude calls MCP tools → Cortex backend pushes to Postman Cloud API | `POSTMAN_API_KEY`, `POSTMAN_WORKSPACE_ID` |
| `git` | Claude writes `.request.yaml` files directly to the repo | Nothing — works offline |
| `disabled` | No Postman integration (default) | Nothing |

Users select their mode in Settings → Features section via `POSTMAN_SYNC_MODE`.

### What Users Get

- A self-building Postman collection that grows alongside the project
- Test scripts that chain requests via captured variables
- Consistent Postman references across all documentation
- **API mode**: Cloud-synced collections visible to all team members, per-system environments
- **Git mode**: Version-controlled YAML files, clean PR diffs, CI/CD via `postman collection run`

---

## Architecture

### Mode Dispatch

The behavioral extension (SKILL.md) is the single entry point. On first use per session, Claude calls `find_postman()` with no params to get the current `sync_mode`. All subsequent behavior branches on that value:

```
find_postman() → { sync_mode: "api" | "git" | "disabled" }

if "api"      → use manage_postman() MCP tools (Cortex backend → Postman Cloud API)
if "git"      → write .request.yaml / .environment.yaml files directly to repo
if "disabled" → provide curl commands only, skip Postman entirely
```

### API Mode Architecture (Cortex-Native MCP)

Port the Postman skill's core Python modules into the Cortex backend. The agent never possesses the API key — it calls MCP tools, and Cortex handles all Postman API communication server-side.

**Key properties:**
- **Zero client installation** — agent calls MCP tools, done
- **Centralized keys** — `PostmanService` fetches `POSTMAN_API_KEY` from `cortex_settings`
- **Programmatic config** — bypass `os.environ`, inject credentials directly into `PostmanConfig`

### Git Mode Architecture (Collections as Code)

No backend needed. Claude writes Postman-compatible YAML files directly to the repository using the Write tool.

**Key properties:**
- **No API keys** — works fully offline
- **Git-native** — diffs, PRs, branches
- **CLI-runnable** — `postman collection run` in CI without accounts

**Reference implementation:** `reference_repos/PostmanFastAPIDemo/postman/`

---

## Backend Services (API Mode Only)

### Directory Structure

```
python/src/server/services/postman/
├── __init__.py
├── postman_service.py      # Orchestration layer
├── postman_client.py       # Ported from skill (HTTP client, retries, proxy handling)
├── config.py               # Ported from skill (modified for programmatic init)
├── exceptions.py           # Ported from skill (custom error classes)
├── formatters.py           # Ported from skill (output formatting)
└── retry_handler.py        # Ported from skill (exponential backoff)
```

### PostmanService

Thin orchestration layer that programmatically initializes `PostmanClient`:

```python
from .postman_client import PostmanClient
from .config import PostmanConfig

class PostmanService:
    def __init__(self, api_key: str, workspace_id: str):
        config = PostmanConfig()
        config.api_key = api_key
        config.workspace_id = workspace_id
        config.headers["X-Api-Key"] = api_key
        self.client = PostmanClient(config=config)
```

**Methods:**
- `get_or_create_collection(project_name)` — Find by name or create, return UID
- `upsert_request(collection_uid, folder_name, request_data)` — GET collection → find/create folder → append/update request → PUT collection
- `upsert_environment(env_name, variables)` — Create or update workspace environment, leveraging auto-secret detection
- `list_collection_structure(collection_uid)` — Return folder/request tree for dedup checking

### Collection Update Mechanism

Postman's API has no "append request" endpoint. The flow:

1. `client.get_collection(uid)` → full JSON
2. Find or create folder in `item[]` by name
3. Append or update the request in that folder
4. `client.update_collection(uid, modified_json)` → push entire object back

This preserves any manual edits users make directly in Postman.

### API Routes

`python/src/server/api_routes/postman_api.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/postman/collections` | POST | Create/find collection for a project |
| `POST /api/postman/collections/{uid}/requests` | POST | Upsert request into collection |
| `PUT /api/postman/environments/{name}` | PUT | Upsert environment with auto-secrets |
| `POST /api/postman/environments/sync` | POST | Sync `.env` from a system (called by session-start hook) |
| `GET /api/postman/status` | GET | Check if Postman is configured and reachable |

### Database Changes

**New column on `cortex_projects`:**

| Column | Type | Purpose |
|--------|------|---------|
| `postman_collection_uid` | VARCHAR(255) | Cached Postman collection UID (API mode) |

**Migration:** `migration/0.1.0/020_add_postman_collection_uid.sql`

**Credentials in `cortex_settings` (existing table):**

| Key | Category | Encrypted | Purpose |
|-----|----------|-----------|---------|
| `POSTMAN_API_KEY` | `api_keys` | Yes | Postman API key — required for `api` mode only |
| `POSTMAN_WORKSPACE_ID` | `api_keys` | No | Target workspace — required for `api` mode only |
| `POSTMAN_SYNC_MODE` | `features` | No | Mode selector: `api`, `git`, or `disabled` (default: `disabled`) |

---

## MCP Tools

### find_postman()

Discovery and read operations. **Also returns `sync_mode` so Claude knows which method to use.**

| Parameter | Type | Purpose |
|-----------|------|---------|
| `project_id` | str (optional) | Get collection info for a specific project |
| `collection_uid` | str (optional) | Get full collection structure (folders + requests) |
| `query` | str (optional) | Search requests by name across the collection |

**Behaviors:**
- No params → returns `{ sync_mode, configured, workspace_info }` — **Claude calls this first every session**
- `project_id` → returns collection name, UID, folder list, request count, associated environments (API mode only)
- `collection_uid` → returns full folder/request tree (API mode only)
- `query` → searches request names for dedup checking (API mode only)

**When `sync_mode` is `git` or `disabled`**, only the no-params call is meaningful. The response tells Claude the mode so it can branch behavior accordingly.

### manage_postman()

Write operations via Postman Cloud API. **Only functional in `api` mode.** Returns `{"status": "skipped", "reason": "sync_mode is not api"}` in other modes.

| Action | Key Parameters | Purpose |
|--------|---------------|---------|
| `init_collection` | `project_id`, `project_name` (optional) | Create collection, store UID on project, create default environment |
| `add_request` | `project_id`, `folder_name`, `request` (dict) | Upsert request into named folder |
| `update_environment` | `project_id`, `system_name`, `variables` (dict) | Create/update `{Project} - {System}` environment |
| `remove_request` | `project_id`, `folder_name`, `request_name` | Remove a specific request |
| `sync_environment` | `project_id`, `env_file_content` (str) | Parse `.env` content and push as system-specific environment |

| `import_from_git` | `project_id` | Read local `postman/` YAML files and push all requests/environments to Postman Cloud |
| `export_to_git` | `project_id`, `collection_uid` | Pull collection from Postman Cloud and write YAML files to `postman/` directory |

**Request dict structure for `add_request`:**
```python
{
    "name": "Create Project",
    "method": "POST",
    "url": "{{base_url}}/api/projects",
    "headers": {"Content-Type": "application/json"},
    "body": {"name": "My Project", "description": "..."},
    "description": "Creates a new Cortex project",
    "test_script": "pm.environment.set('project_id', pm.response.json().id);"
}
```

---

## Session-Start Hook: Environment Sync (API Mode Only)

The session-start hook runs as a plain Python script before the LLM loop — it calls REST endpoints, not MCP tools.

**Flow:**
1. Read `.claude/cortex-state.json` → extract `system_name`, `cortex_project_id`, Cortex server URL
2. Check sync mode: `GET /api/credentials/POSTMAN_SYNC_MODE`
3. If `api`, read the project's local `.env` file
4. Call `POST /api/postman/environments/sync` with `{project_id, system_name, env_file_content}`
5. Cortex backend parses `.env`, applies auto-secret detection, pushes to Postman API
6. Runs silently — no output unless error

In `git` mode, the hook skips Postman entirely — environment files are written by Claude during the session.

---

## Git Mode: Directory Structure & YAML Schemas

### Directory Structure

```
postman/
├── collections/
│   └── {Project Name}/
│       ├── .resources/
│       │   └── definition.yaml           # Collection metadata + variables
│       ├── {Resource Domain}/
│       │   ├── .resources/
│       │   │   └── definition.yaml       # Folder ordering
│       │   └── {Request Name}.request.yaml
│       └── {Request Name}.request.yaml   # Top-level requests (if any)
├── environments/
│   ├── {Project} - Local.environment.yaml
│   └── {Project} - CI.environment.yaml   # Optional
└── globals/
    └── workspace.globals.yaml            # Optional
```

### Collection Definition

```yaml
$kind: collection
description: >
  API collection for {Project Name}.
variables:
  baseUrl: "{{baseUrl}}"
  projectId: ""
  taskId: ""
```

### Folder Definition

```yaml
$kind: collection
order: 2000
```

### HTTP Request

```yaml
$kind: http-request
name: Create Project
url: "{{baseUrl}}/api/projects"
method: POST
description: Creates a new Cortex project

headers:
  Content-Type: application/json

body:
  type: text
  content: |
    {
      "name": "My Project",
      "description": "A new project"
    }

scripts:
  - type: afterResponse
    code: |-
      pm.test('Status is 201', function () {
          pm.response.to.have.status(201);
      });

      pm.test('Project has an ID', function () {
          var json = pm.response.json();
          pm.expect(json.id).to.be.a('string');
          pm.collectionVariables.set('projectId', json.id);
      });
    language: text/javascript

order: 1000
```

### Environment

```yaml
name: "{Project Name} - Local"
values:
  - key: baseUrl
    value: http://localhost:8181
    enabled: true
  - key: supabaseUrl
    value: http://localhost:8000
    enabled: true
  - key: supabaseKey
    value: ""
    enabled: true
color: null
```

---

## Behavioral Extension (SKILL.md)

Location: `integrations/claude-code/extensions/postman-integration/SKILL.md`

Auto-seeded into extension registry on server start, distributed via `/cortex-setup`.

The extension contains all rules for both modes. Claude checks the mode first via `find_postman()`, then follows the appropriate rules.

### Shared Rules (Both Modes)

- **Rule 1: Mode Check** — call `find_postman()` once per session to get `sync_mode`
- **Rule 2: Always Add, Never Just Curl** — every API test gets a Postman entry
- **Rule 3: Folder Naming** — framework-agnostic resource domain derivation
- **Rule 4: Test Script Patterns** — status checks, response validation, variable capture
- **Rule 5: Documentation References** — contextual per document type
- **Rule 6: Prevent Duplicates** — check before adding
- **Rule 7: Graceful Degradation** — skip silently when `disabled`

### API Mode Rules

- Use `manage_postman("init_collection")` to create collections
- Use `manage_postman("add_request")` to add requests
- Use `manage_postman("update_environment")` for environment variables
- Do not redact secrets — backend handles auto-secret detection
- Use `find_postman(query=...)` for dedup checking

### Git Mode Rules

- Write `.request.yaml` files using the Write tool
- Create `postman/collections/{Project}/` scaffold if missing
- Write `.environment.yaml` with empty strings for secrets
- Maintain `order` values in increments of 1000
- Add collection variables to `.resources/definition.yaml` when scripts use `pm.collectionVariables.set()`

---

## Settings Integration

### Mode Selector (Features Section)

Replaces a simple boolean toggle with a three-way selector:

| Setting | Key | Default | Values |
|---------|-----|---------|--------|
| Postman Sync Mode | `POSTMAN_SYNC_MODE` | `disabled` | `api`, `git`, `disabled` |

- When `api`: shows validation warning if `POSTMAN_API_KEY` is not set
- When `git`: no additional configuration needed
- When `disabled`: all Postman operations skip silently

### API Keys (API Mode Only)

| Key | Category | Encrypted | Description |
|-----|----------|-----------|-------------|
| `POSTMAN_API_KEY` | `api_keys` | Yes | Required for `api` mode only |
| `POSTMAN_WORKSPACE_ID` | `api_keys` | No | Required for `api` mode only |

### Frontend Changes

- `FeaturesSection.tsx` — add mode selector (dropdown or radio group instead of toggle)
- `SettingsContext.tsx` — add `postmanSyncMode` state + setter (string, not boolean)

### Backend Changes

- Add `POSTMAN_SYNC_MODE` to `OPTIONAL_SETTINGS_WITH_DEFAULTS` in `settings_api.py` (default: `"disabled"`)

---

## Collection & Environment Naming

### Collection Name

- **Primary**: Cortex project name (e.g., `Cortex`)
- **Fallback**: Git repo name — just repo name, no owner prefix
- **API mode**: stored as `postman_collection_uid` on `cortex_projects`
- **Git mode**: directory name under `postman/collections/`

### Environment Naming

- **API mode**: `{Project Name} - {System Name}` (e.g., `Cortex - WIN-DEV-01`) — workspace-scoped in Postman Cloud
- **Git mode**: `{Project Name} - Local.environment.yaml` — committed to repo, user populates secrets locally

---

## Testing Strategy

### Backend Tests (API Mode)

**`tests/server/services/postman/test_postman_service.py`**
- Mock `PostmanClient` — never call real Postman API
- Test `get_or_create_collection`: creates when not found, returns existing when found
- Test `upsert_request`: folder creation, request append, request update, full GET→modify→PUT cycle
- Test `upsert_environment`: auto-secret detection passthrough, create vs update
- Test `list_collection_structure`: correct folder/request tree parsing

**`tests/server/api_routes/test_postman_api.py`**
- Test each endpoint with mocked `PostmanService`
- Test 400 responses when Postman not configured
- Test credential retrieval from `cortex_settings`

**`tests/mcp_server/features/postman/test_postman_tools.py`**
- Test `find_postman` returns correct `sync_mode` for each mode
- Test `manage_postman` action routing and parameter validation
- Test `manage_postman` returns `{"status": "skipped"}` when mode is not `api`
- Test dedup check flow

### Frontend Tests

- Mode selector saves `POSTMAN_SYNC_MODE` correctly
- Validation warning when `api` selected but no API key
- No warning when `git` selected

### Integration Testing (Manual)

**API mode:**
- Configure keys + set mode to `api` → verify connection
- Init collection for a project → verify in Postman workspace
- Add requests to different folders → verify structure
- Push `.env` via session-start hook → verify environment with secrets
- Add duplicate request → verify update instead of duplicate

**Git mode:**
- Set mode to `git` → verify `find_postman()` returns `sync_mode: "git"`
- Ask Claude to test an API endpoint → verify YAML files created
- Verify generated YAML opens correctly in Postman
- Run `postman collection run` on generated collection

**Disabled mode:**
- Set mode to `disabled` → verify Claude provides curl only

---

## File Change Summary

### New Files

| File | Purpose |
|------|---------|
| `python/src/server/services/postman/__init__.py` | Package init |
| `python/src/server/services/postman/postman_service.py` | Orchestration layer |
| `python/src/server/services/postman/postman_client.py` | Ported from skill |
| `python/src/server/services/postman/config.py` | Ported, modified for programmatic init |
| `python/src/server/services/postman/exceptions.py` | Ported from skill |
| `python/src/server/services/postman/formatters.py` | Ported from skill |
| `python/src/server/services/postman/retry_handler.py` | Ported from skill |
| `python/src/server/api_routes/postman_api.py` | REST endpoints (API mode) |
| `python/src/mcp_server/features/postman/__init__.py` | MCP feature init |
| `python/src/mcp_server/features/postman/postman_tools.py` | MCP tools (find + manage) |
| `integrations/claude-code/extensions/postman-integration/SKILL.md` | Behavioral extension (dual-mode) |
| `migration/0.1.0/020_add_postman_collection_uid.sql` | Add column to cortex_projects |
| `tests/server/services/postman/test_postman_service.py` | Service tests |
| `tests/server/api_routes/test_postman_api.py` | API route tests |
| `tests/mcp_server/features/postman/test_postman_tools.py` | MCP tool tests |

### Modified Files

| File | Change |
|------|--------|
| `python/src/server/main.py` | Register `postman_router` |
| `python/src/server/api_routes/settings_api.py` | Add `POSTMAN_SYNC_MODE` to defaults |
| `python/src/mcp_server/mcp_server.py` | Register Postman MCP tools |
| `cortex-ui/src/components/settings/FeaturesSection.tsx` | Add mode selector |
| `cortex-ui/src/contexts/SettingsContext.tsx` | Add `postmanSyncMode` state |
| `integrations/claude-code/plugins/cortex-memory/hooks/session_start_hook.py` | Add `.env` sync (API mode only) |

---

## Design Decisions Summary

1. **Dual-mode** — `api` for cloud sync, `git` for local YAML, `disabled` as default
2. **Single behavioral extension** — one SKILL.md handles both modes via mode check
3. **Mode dispatch via `find_postman()`** — returns `sync_mode` so Claude branches correctly
4. **Cortex-native MCP for API mode** — ported client, centralized keys, zero client installation
5. **Collections as Code for Git mode** — human-readable YAML, no API keys, works offline
6. **Collection per project** — named after Cortex project, fallback to repo name (no owner prefix)
7. **Folders mirror resource domains** — framework-agnostic derivation from controller/router names
8. **Test scripts on every request** — verify status, validate shape, capture IDs
9. **Session-start hook for API mode only** — pushes `.env` to Postman Cloud environments
10. **Graceful degradation** — `disabled` mode skips silently, no user nagging
