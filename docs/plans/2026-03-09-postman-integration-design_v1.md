**Date**: 2026-03-09

**Status**: Approved

**Feature**: Automatic Postman collection and environment management per Cortex project



## Overview



Automatically maintain a Postman collection and environment per Cortex project so that every API endpoint Claude suggests testing is captured as a reusable, executable Postman request — replacing ad-hoc curl commands with a living API test suite.



### How It Works End-to-End



1. User adds `POSTMAN_API_KEY` and `POSTMAN_WORKSPACE_ID` in Settings → API Keys section

2. User enables "Postman Integration" in Settings → Features section

3. When Claude is working in a project and suggests testing an API call, it:

   - Checks if a Postman collection exists for this Cortex project (or creates one)

   - Adds the request to the collection in a folder matching the resource domain (e.g., `Projects`, `Tasks`)

   - Includes test scripts that capture response IDs into environment variables

   - Creates/updates a system-specific environment with all needed variables

4. In documentation, Claude references the Postman collection contextually — per-step in test plans, summary section in architecture docs



### What Users Get



- A self-building Postman collection that grows alongside the project

- Per-system environments pushed from each developer's `.env` file

- Test scripts that chain naturally (create → captured ID → use in next request)

- Consistent references across all documentation



## Architecture: Cortex-Native MCP



### Approach



Port the Postman skill's core Python modules directly into the Cortex backend. The agent never possesses the Postman API key — it calls MCP tools, and Cortex handles all Postman API communication server-side.



**Key properties:**

- **Zero client installation** — agent connects to Cortex MCP, calls tools, done

- **Centralized keys** — `PostmanService` fetches `POSTMAN_API_KEY` from `cortex_settings` at call time

- **Programmatic config** — bypass `os.environ` reading, inject credentials directly into `PostmanConfig`



### Backend Services



#### Directory Structure



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



#### PostmanService



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



#### Collection Update Mechanism



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

| `postman_collection_uid` | VARCHAR(255) | Cached Postman collection UID |



**Migration:** `migration/0.1.0/020_add_postman_collection_uid.sql`



**Credentials in `cortex_settings` (existing table):**



| Key | Category | Encrypted | Purpose |

|-----|----------|-----------|---------|

| `POSTMAN_API_KEY` | `api_keys` | Yes | Postman API key (starts with `PMAK-`) |

| `POSTMAN_WORKSPACE_ID` | `api_keys` | No | Target workspace for collections/environments |

| `POSTMAN_INTEGRATION_ENABLED` | `features` | No | Feature toggle |



No new tables needed.



## MCP Tools



### find_postman()



Discovery and read operations.



| Parameter | Type | Purpose |

|-----------|------|---------|

| `project_id` | str (optional) | Get collection info for a specific project |

| `collection_uid` | str (optional) | Get full collection structure (folders + requests) |

| `query` | str (optional) | Search requests by name across the collection |



**Behaviors:**

- No params → returns integration status (configured? workspace? connected projects?)

- `project_id` → returns collection name, UID, folder list, request count, associated environments

- `collection_uid` → returns full folder/request tree

- `query` → searches request names for dedup checking



### manage_postman()



Write operations with an `action` parameter.



| Action | Key Parameters | Purpose |

|--------|---------------|---------|

| `init_collection` | `project_id`, `project_name` (optional) | Create collection, store UID on project, create default environment |

| `add_request` | `project_id`, `folder_name`, `request` (dict) | Upsert request into named folder |

| `update_environment` | `project_id`, `system_name`, `variables` (dict) | Create/update `{Project} - {System}` environment |

| `remove_request` | `project_id`, `folder_name`, `request_name` | Remove a specific request |

| `sync_environment` | `project_id`, `env_file_content` (str) | Parse `.env` content and push as system-specific environment |



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



**Error handling:**

- Not configured → `{"status": "skipped", "reason": "Postman integration not configured"}`

- Collection doesn't exist → `add_request` auto-calls `init_collection` first



## Session-Start Hook: Environment Sync



The session-start hook (`session_start_hook.py`) runs as a plain Python script before the LLM loop — it cannot call MCP tools. It uses the `CortexClient` HTTP client to hit REST endpoints.



**Flow:**

1. Read `.claude/cortex-state.json` → extract `system_name`, `cortex_project_id`, Cortex server URL

2. Check if Postman integration is enabled: `GET /api/credentials/POSTMAN_INTEGRATION_ENABLED`

3. If enabled, read the project's local `.env` file

4. Call `POST /api/postman/environments/sync` with `{project_id, system_name, env_file_content}`

5. Cortex backend parses `.env`, applies auto-secret detection, pushes to Postman API

6. Runs silently — no output unless error



The MCP tool `manage_postman("sync_environment")` also exists for mid-session refreshes (e.g., after Claude helps modify `.env`).



## Environment Naming



Postman environments are workspace-scoped, not collection-scoped. Association by naming convention:



- Format: `{Project Name} - {System Name}` (e.g., `Cortex - WIN-DEV-01`)

- All team members see all system environments in the shared workspace

- Auto-secret detection from `PostmanClient` handles sensitive variables



## Collection Naming



- Primary: Cortex project name (e.g., `Cortex`)

- Fallback: Git repo name (just repo name, no owner prefix — `Cortex` not `coleam00-Cortex`)

- Stored as `postman_collection_uid` on `cortex_projects` after creation



## Behavioral Extension (SKILL.md)



Location: `integrations/claude-code/extensions/postman-integration/SKILL.md`



Auto-seeded into extension registry on server start, distributed via `/cortex-setup`.



### Rule 1: Collection Initialization

When starting work on a project with Postman enabled but no `postman_collection_uid`, call `manage_postman("init_collection")` first.



### Rule 2: Always Add, Never Just Curl

When suggesting an API call for testing:

- Call `manage_postman("add_request")` with full request details

- Include test scripts that capture response IDs into environment variables

- Tell the user the request is available in Postman

- Never provide only a curl command without also adding to the collection



### Rule 3: Folder Naming — Framework-Agnostic

Use the core resource name or domain grouping as the folder name (e.g., `Users`, `Authentication`, `Products`). Derive from the controller/router file name regardless of framework:

- `users.controller.ts` → `Users`

- `projects_api.py` → `Projects`

- `AuthRouter.java` → `Auth`

- `handlers/orders.go` → `Orders`



### Rule 4: Test Script Patterns

Always include test scripts that:

- Verify the response status code

- Extract IDs from create/update responses: `pm.environment.set("created_{resource}_id", pm.response.json().id)`

- Use `{{variable}}` references in URLs and bodies for chaining



### Rule 5: Documentation References (Contextual)

- **Test plans / user journeys** → per-step references: `(Postman: {Collection} → {Folder} → {Request Name})`

- **Architecture docs / general docs** → single summary section listing available Postman requests

- **Code comments** → no Postman references



### Rule 6: Environment Variables

When adding a request that uses variables not yet in the environment, call `manage_postman("update_environment")` to add them. Use Postman variable syntax: `{{base_url}}`, `{{project_id}}`.



**Note:** Do not manually redact API keys or passwords when passing them to `update_environment`. The Cortex backend automatically detects sensitive keys and safely marks them as secret in Postman.



### Rule 7: Graceful Degradation

If Postman integration is not configured:

- Proceed normally with curl commands / documentation

- Don't prompt the user to set it up unless they ask about Postman

- Check once per session via `find_postman()` with no params



### Rule 8: Prevent Duplicates

Before calling `manage_postman("add_request")`, call `find_postman(query="<Request Name>")` or check the collection structure to ensure you aren't adding a duplicate. If a matching request exists, update it rather than creating a new one.



## Settings Integration



### API Keys Section



Two new credentials appear alongside existing keys (auto-displayed by `APIKeysSection.tsx` because they match the `_KEY` / `_ID` pattern):



| Key | Encrypted | Description |

|-----|-----------|-------------|

| `POSTMAN_API_KEY` | Yes | Postman API key (starts with `PMAK-`) |

| `POSTMAN_WORKSPACE_ID` | No | Target workspace ID |



No frontend component changes needed for this section.



### Features Section



One new toggle in the existing grid:



| Setting | Key | Default |

|---------|-----|---------|

| Postman Integration | `POSTMAN_INTEGRATION_ENABLED` | `false` |



- Shows validation warning if enabled but `POSTMAN_API_KEY` is not set

- When disabled, all MCP tools and hooks gracefully skip Postman operations



### Frontend Changes



- `FeaturesSection.tsx` — add toggle to grid (matches existing pattern)

- `SettingsContext.tsx` — add `postmanIntegrationEnabled` state + setter

- No new components



### Backend Changes



- Add `POSTMAN_INTEGRATION_ENABLED` to `OPTIONAL_SETTINGS_WITH_DEFAULTS` in `settings_api.py`



## Testing Strategy



### Backend Tests



**`tests/server/services/postman/test_postman_service.py`**

- Mock `PostmanClient` — never call real Postman API

- Test `get_or_create_collection`: creates when not found, returns existing when found

- Test `upsert_request`: folder creation, request append, request update, full GET→modify→PUT cycle

- Test `upsert_environment`: auto-secret detection passthrough, create vs update

- Test `list_collection_structure`: correct folder/request tree parsing

- Test graceful skip when `POSTMAN_INTEGRATION_ENABLED` is false



**`tests/server/api_routes/test_postman_api.py`**

- Test each endpoint with mocked `PostmanService`

- Test 400 responses when Postman not configured

- Test credential retrieval from `cortex_settings`



**`tests/mcp_server/features/postman/test_postman_tools.py`**

- Test `find_postman` with various parameter combinations

- Test `manage_postman` action routing and parameter validation

- Test graceful `{"status": "skipped"}` response when not configured

- Test dedup check flow



### Frontend Tests



- Feature toggle saves `POSTMAN_INTEGRATION_ENABLED` correctly

- Validation warning when toggle enabled but no API key



### Integration Testing (Manual)



- Configure keys in Settings → verify connection

- Init collection for a project → verify in Postman workspace

- Add requests to different folders → verify structure

- Push `.env` via session-start hook → verify environment with correct secrets

- Add duplicate request → verify update instead of duplicate

- Disable toggle → verify all operations skip gracefully



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

| `python/src/server/api_routes/postman_api.py` | REST endpoints |

| `python/src/mcp_server/features/postman/__init__.py` | MCP feature init |

| `python/src/mcp_server/features/postman/postman_tools.py` | MCP tools |

| `integrations/claude-code/extensions/postman-integration/SKILL.md` | Behavioral extension |

| `migration/0.1.0/020_add_postman_collection_uid.sql` | Add column to cortex_projects |

| `tests/server/services/postman/test_postman_service.py` | Service tests |

| `tests/server/api_routes/test_postman_api.py` | API route tests |

| `tests/mcp_server/features/postman/test_postman_tools.py` | MCP tool tests |



### Modified Files



| File | Change |

|------|--------|

| `python/src/server/main.py` | Register `postman_router` |

| `python/src/server/api_routes/settings_api.py` | Add `POSTMAN_INTEGRATION_ENABLED` to defaults |

| `python/src/mcp_server/mcp_server.py` | Register Postman MCP tools |

| `cortex-ui/src/components/settings/FeaturesSection.tsx` | Add Postman toggle |

| `cortex-ui/src/contexts/SettingsContext.tsx` | Add `postmanIntegrationEnabled` state |

| `integrations/claude-code/plugins/cortex-memory/hooks/session_start_hook.py` | Add `.env` sync step |



## Design Decisions Summary



1. **Cortex-native MCP** — ported client, centralized keys, zero client installation

2. **Collection per project** — named after Cortex project, fallback to repo name (no owner prefix)

3. **Folders mirror resource domains** — framework-agnostic derivation from controller/router names

4. **Test scripts capture variables** — chain requests naturally, no pre-request scripts

5. **Environments per system** — pushed from `.env` via session-start hook REST call to Postman API

6. **No `.env` in Cortex DB** — hook pushes directly to Postman, eliminating security concern

7. **Settings integration** — keys in existing API Keys section, toggle in existing Features grid

8. **Behavioral extension** — 8 rules governing when/how Claude uses the tools

9. **Graceful degradation** — skip silently when not configured, no user nagging