# Postman Integration — User Test Plan

## Overview

This test plan validates the Dual-Mode Postman Integration feature end-to-end. The feature maintains Postman collections per Cortex project in two modes:

- **API mode** — Claude calls MCP tools, Cortex backend proxies to Postman Cloud API
- **Git mode** — Claude writes `.request.yaml` files directly to the repo
- **Disabled** — No Postman integration (default)

Testing covers: database migration, settings UI, MCP tool registration, API mode operations, git mode behavior, session hook .env sync, cross-mode sync, graceful degradation, and behavioral extension compliance.

## Prerequisites

- Cortex stack running and accessible (default: `http://localhost:3737`)
- At least one project configured in Cortex
- Claude Code CLI installed and connected to Cortex MCP server
- The `cortex-memory` plugin installed (run `/cortex-setup` if not)
- Migration `020_add_postman_collection_uid.sql` applied to your database
- For API mode tests: A valid Postman API key (starts with `PMAK-`) and workspace ID
  - Get your API key from: https://web.postman.co/settings/me/api-keys
  - Get your workspace ID from: Workspace settings or URL (`https://app.getpostman.com/workspaces/{workspace_id}`)
- For Git mode tests: A project repo with write access

---

## Phase 1: Database Verification

### 1.1 Check migration applied

1. Open your Supabase dashboard SQL editor (or connect via `psql`)
2. Run:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'cortex_projects'
  AND column_name = 'postman_collection_uid'
ORDER BY ordinal_position;
```

**Expected:** One row returned: `postman_collection_uid | character varying`

### 1.2 Verify column is nullable

```sql
SELECT column_name, is_nullable
FROM information_schema.columns
WHERE table_name = 'cortex_projects'
  AND column_name = 'postman_collection_uid';
```

**Expected:** `is_nullable = YES` (existing projects should have NULL)

> **If the column doesn't exist:** Run the migration at `migration/0.1.0/020_add_postman_collection_uid.sql` in your Supabase SQL editor.

---

## Phase 2: Settings UI

### 2.1 Postman Sync Mode selector appears

1. Open Cortex UI at `http://localhost:3737/settings`
2. Scroll to the **Features** section

**Expected:** A card labeled "Postman Integration" (or similar) with a dropdown selector. Default value should be "Disabled".

### 2.2 Change mode to Git

1. In the Postman Integration card, select "Git (Collections as Code)" from the dropdown
2. Wait for the save confirmation toast

**Expected:**
- Toast message confirms the setting was saved
- No error messages
- Dropdown stays on "Git"

### 2.3 Change mode to API — validation warning

1. Select "API (Postman Cloud)" from the dropdown

**Expected:**
- Setting saves successfully
- A warning message appears indicating that `POSTMAN_API_KEY` and `POSTMAN_WORKSPACE_ID` must be configured in the API Keys section

### 2.4 Change mode back to Disabled

1. Select "Disabled" from the dropdown

**Expected:** Setting saves. No warning shown.

### 2.5 Verify persistence across page refresh

1. Set mode to "Git"
2. Refresh the page (F5)

**Expected:** The dropdown still shows "Git" after refresh.

### 2.6 Configure API credentials (for API mode tests)

1. Scroll to the **API Keys** section
2. Add `POSTMAN_API_KEY` with your Postman API key (starts with `PMAK-`)
3. Add `POSTMAN_WORKSPACE_ID` with your workspace ID

**Expected:** Both credentials save successfully. These are needed for Phase 5.

---

## Phase 3: Backend API Verification

### 3.1 Status endpoint — disabled mode

1. With mode set to "disabled", run:
```bash
curl -s http://localhost:8181/api/postman/status | jq
```

**Expected:**
```json
{
  "sync_mode": "disabled",
  "configured": false
}
```

### 3.2 Status endpoint — git mode

1. Set mode to "git" in Settings
2. Run:
```bash
curl -s http://localhost:8181/api/postman/status | jq
```

**Expected:**
```json
{
  "sync_mode": "git",
  "configured": false
}
```

### 3.3 Status endpoint — api mode (with credentials)

1. Set mode to "api" in Settings (ensure API key and workspace ID are configured)
2. Run:
```bash
curl -s http://localhost:8181/api/postman/status | jq
```

**Expected:**
```json
{
  "sync_mode": "api",
  "configured": true
}
```

### 3.4 API endpoints skip gracefully in non-api mode

1. Set mode to "git"
2. Run:
```bash
curl -s -X POST http://localhost:8181/api/postman/collections \
  -H "Content-Type: application/json" \
  -d '{"project_name": "Test"}' | jq
```

**Expected:**
```json
{
  "status": "skipped",
  "reason": "sync_mode is not api"
}
```

### 3.5 Environment sync endpoint parses .env correctly

1. Set mode to "api" (with valid credentials)
2. Run:
```bash
curl -s -X POST http://localhost:8181/api/postman/environments/sync \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test-proj",
    "system_name": "TEST-MACHINE",
    "env_file_content": "# Database\nSUPABASE_URL=http://localhost:8000\nSUPABASE_SERVICE_KEY=secret123\n\n# Empty line above\nAPI_PORT=8181"
  }' | jq
```

**Expected:**
```json
{
  "success": true,
  "environment": "test-proj - TEST-MACHINE",
  "variables_count": 3
}
```

Verify in your Postman workspace that the environment was created with 3 variables. `SUPABASE_SERVICE_KEY` should be marked as a secret.

---

## Phase 4: MCP Tool Registration

### 4.1 Check MCP server health

```bash
curl -s http://localhost:8051/health
```

**Expected:** Healthy status response.

### 4.2 Verify Postman tools are registered

```bash
docker compose logs cortex-mcp 2>&1 | grep -i "postman"
```

**Expected:**
```
✓ Postman integration module registered (HTTP-based)
```

### 4.3 Verify tools visible in Claude Code

1. Open Claude Code in a project connected to Cortex
2. Ask: "What Cortex MCP tools do you have access to?"

**Expected:** Claude lists `find_postman` and `manage_postman` among the available tools.

---

## Phase 5: API Mode — Full Lifecycle

> **Prerequisite:** Mode set to "api", valid `POSTMAN_API_KEY` and `POSTMAN_WORKSPACE_ID` configured.

### 5.1 find_postman — get status

1. In Claude Code, ask: "Check my Postman integration status"
2. Claude should call `find_postman()` with no parameters

**Expected:** Claude reports the sync mode is "api" and the integration is configured.

### 5.2 Collection initialization

1. Ask Claude: "Initialize a Postman collection for this project"
2. Claude should call `manage_postman(action="init_collection", project_name="<project name>")`

**Expected:**
- Claude confirms the collection was created
- In Postman, a new collection appears in your workspace named after the project
- The project's `postman_collection_uid` is now set in the database:
```sql
SELECT name, postman_collection_uid FROM cortex_projects WHERE name = '<project name>';
```

### 5.3 Add a request

1. Ask Claude: "Add a health check GET request to /api/health"
2. Claude should call `manage_postman(action="add_request", ...)` with a "Health" folder

**Expected:**
- Claude confirms the request was added to the collection
- In Postman, the collection now has a "Health" folder with a "Health Check" request
- The request has a test script verifying status 200

### 5.4 Add a CRUD endpoint set

1. Ask Claude: "I have a projects API at /api/projects with GET (list), POST (create), GET /:id, PUT /:id, DELETE /:id. Add all of these to Postman."

**Expected:**
- Claude adds 5 requests to a "Projects" folder
- Each request has appropriate test scripts:
  - GET list: checks status 200, returns array
  - POST create: checks status 201, captures `projectId`
  - GET by ID: uses `{{projectId}}` variable, checks status 200
  - PUT update: uses `{{projectId}}`, checks status 200
  - DELETE: uses `{{projectId}}`, checks status 200 or 204
- Variables like `{{base_url}}` are used for the host
- Collection variables include `projectId`

### 5.5 Prevent duplicate requests

1. Ask Claude again: "Add a health check GET request to /api/health"

**Expected:**
- Claude checks for duplicates (calls `find_postman(query="Health Check")` or checks structure)
- Claude either updates the existing request or tells you it already exists
- No duplicate "Health Check" request appears in Postman

### 5.6 Update an environment

1. Ask Claude: "Update my Postman environment with base_url=http://localhost:8181"

**Expected:**
- Claude calls `manage_postman(action="update_environment", ...)`
- In Postman, the environment for this project + system is created/updated
- The `base_url` variable is set to `http://localhost:8181`

### 5.7 Sync .env to Postman environment

1. Ask Claude: "Sync my .env file to Postman"
2. Claude should call `manage_postman(action="sync_environment", ...)` with the .env content

**Expected:**
- All .env variables appear in the Postman environment
- Sensitive variables (keys, passwords, tokens) are marked as secrets
- Comments and empty lines are ignored

---

## Phase 6: Git Mode — Collections as Code

> **Prerequisite:** Mode set to "git" in Settings.

### 6.1 find_postman returns git mode

1. In Claude Code, ask: "Check my Postman integration status"

**Expected:** Claude reports `sync_mode: "git"`.

### 6.2 MCP tools skip gracefully

1. Ask Claude to add a request that would use MCP tools

**Expected:** Claude writes `.request.yaml` files directly to the repo instead of calling MCP tools. It should NOT call `manage_postman()` for write operations (those return "skipped" in git mode).

### 6.3 Collection scaffold creation

1. If no `postman/` directory exists, ask Claude: "Set up Postman collections for this project"

**Expected:** Claude creates the directory structure:
```
postman/
├── collections/
│   └── {Project Name}/
│       └── .resources/
│           └── definition.yaml
└── environments/
    └── {Project Name} - Local.environment.yaml
```

### 6.4 Request YAML file creation

1. Ask Claude: "Add a GET request for /api/health to the Postman collection"

**Expected:** Claude creates `postman/collections/{Project}/Health/Health Check.request.yaml`:
```yaml
$kind: http-request
name: Health Check
url: "{{baseUrl}}/api/health"
method: GET
description: Check API health status

scripts:
  - type: afterResponse
    code: |-
      pm.test('Status is 200', function () {
          pm.response.to.have.status(200);
      });
    language: text/javascript

order: 1000
```

### 6.5 Folder ordering

1. Ask Claude to add requests for multiple resource domains (Health, Projects, Tasks)

**Expected:**
- Each folder has a `.resources/definition.yaml` with `order` field
- Health folder: order 1000
- Other folders: alphabetical, incrementing by 1000

### 6.6 Environment YAML file

1. Check `postman/environments/{Project} - Local.environment.yaml`

**Expected:**
```yaml
name: "{Project Name} - Local"
values:
  - key: baseUrl
    value: http://localhost:{port}
    enabled: true
color: null
```

### 6.7 Prevent duplicate YAML files

1. Ask Claude to add the same health check request again

**Expected:** Claude detects the existing file and updates it rather than creating a duplicate.

---

## Phase 7: Session-Start Hook (.env Sync)

> **Prerequisite:** Mode set to "api", valid credentials, a `.env` file in the project root.

### 7.1 Verify hook runs on session start

1. Start a new Claude Code session in a project with Cortex connected
2. Check the Cortex server logs:
```bash
docker compose logs cortex-server 2>&1 | grep -i "postman\|environment\|sync" | tail -5
```

**Expected:** If the project has a `.env` file and mode is "api", the log should show an environment sync request (or at least the endpoint being hit). The sync is best-effort — no errors should be visible to the user.

### 7.2 Verify environment created in Postman

1. Open your Postman workspace
2. Look for an environment named `{Project Name} - {System Name}`

**Expected:** The environment exists and contains variables from the project's `.env` file. Sensitive keys (API_KEY, PASSWORD, SECRET, TOKEN patterns) should be marked as secrets.

### 7.3 Verify hook is silent on failure

1. Set mode to "disabled" or remove API credentials
2. Start a new Claude Code session

**Expected:** No error output — the hook silently skips the sync.

### 7.4 Verify hook is silent in git mode

1. Set mode to "git"
2. Start a new Claude Code session

**Expected:** No Postman sync attempted. Hook completes without errors.

---

## Phase 8: Cross-Mode Sync

### 8.1 Import from Git to API

1. Set mode to "api"
2. Have existing `.request.yaml` files in `postman/` directory
3. Ask Claude: "Import my local Postman YAML files to the Postman Cloud collection"

**Expected:**
- Claude reads the local YAML files
- Claude calls `manage_postman(action="add_request", ...)` for each request
- All requests appear in the Postman Cloud collection
- Folder structure matches the local directory structure

### 8.2 Export from API to Git

1. Have a Postman Cloud collection with requests
2. Ask Claude: "Export my Postman collection to local YAML files"

**Expected:**
- Claude calls `find_postman(collection_uid="...")` to get the structure
- Claude writes `.request.yaml` files matching the collection structure
- Directory structure follows the git mode conventions

---

## Phase 9: Graceful Degradation

### 9.1 Disabled mode — no Postman behavior

1. Set mode to "disabled"
2. Ask Claude to help you test an API endpoint

**Expected:**
- Claude provides curl commands as normal
- No mention of Postman unless you ask about it
- No Postman files created
- No MCP tool calls related to Postman

### 9.2 API mode without credentials — clear error

1. Set mode to "api" but do NOT configure `POSTMAN_API_KEY`
2. Ask Claude to add a request to Postman

**Expected:**
- Claude receives a clear error message about missing API key
- Claude reports the issue to the user clearly
- No silent failures

### 9.3 API mode with invalid key — helpful error

1. Set `POSTMAN_API_KEY` to an invalid value (e.g., "PMAK-invalid-key")
2. Ask Claude to initialize a collection

**Expected:**
- The Postman API returns an authentication error
- Claude reports the error clearly with a suggestion to check the API key

### 9.4 Network failure handling

1. If possible, simulate a network issue (e.g., block `api.getpostman.com`)
2. Try adding a request via Claude

**Expected:**
- Claude receives a network error
- Claude reports it as a connectivity issue
- No crash or hang

---

## Phase 10: Behavioral Extension (SKILL.md) Compliance

### 10.1 Rule 0: Mode check per session

1. Start a fresh Claude Code session
2. Ask Claude to add a Postman request

**Expected:** Claude calls `find_postman()` first (with no params) to determine the mode, THEN performs the action appropriate for that mode.

### 10.2 Rule 1: Always add, never just curl

1. With Postman enabled (api or git mode), ask Claude to test an API endpoint

**Expected:** Claude adds the request to Postman AND provides the curl command. It should not provide ONLY a curl command.

### 10.3 Rule 2: Folder naming from resource domain

1. Ask Claude to add requests from a `users_api.py` controller

**Expected:** Requests go into a "Users" folder (not "users_api" or "UsersApi").

### 10.4 Rule 3: Test script patterns

1. Ask Claude to add a POST /create endpoint

**Expected:** The request includes test scripts that:
- Verify status code (201 for create)
- Capture the ID from the response into a collection/environment variable
- Use camelCase variable names (e.g., `userId`, not `user_id`)

### 10.5 Rule 4: Documentation references

1. Ask Claude to write a test plan for a user journey

**Expected:** Each step that involves an API call includes a Postman reference:
> *(Postman: `{Collection}` → `{Folder}` → `{Request Name}`)*

### 10.6 Rule 5: Prevent duplicates

1. Ask Claude to add the same request twice

**Expected:** Claude checks for existing requests before adding. Updates rather than creates duplicates.

### 10.7 Rule 6: Graceful when disabled

1. Set mode to "disabled"
2. Have a conversation about API design

**Expected:** Claude never prompts you to configure Postman. No Postman-related actions taken.

---

## Phase 11: Automated Test Verification

Verify all automated tests pass.

### 11.1 Service tests

```bash
cd python && uv run pytest tests/server/services/postman/test_postman_service.py -v
```

**Expected:** All 16 tests pass:
- `TestGetSyncMode` — api, disabled, invalid mode
- `TestGetClient` — raises when no API key
- `TestGetOrCreateCollection` — find existing, create new
- `TestUpsertRequest` — folder creation, update existing, test scripts
- `TestUpsertEnvironment` — create new, update existing
- `TestListCollectionStructure` — folder tree, URL-as-dict
- `TestBuildPostmanRequest` — GET, POST with body, default method

### 11.2 API route tests

```bash
cd python && uv run pytest tests/server/api_routes/test_postman_api.py -v
```

**Expected:** All 6 tests pass:
- Status endpoint returns sync mode
- Collection creation and skip behavior
- Request upsert success
- Environment sync parses .env correctly

### 11.3 MCP tool tests

```bash
cd python && uv run pytest tests/mcp_server/features/postman/test_postman_tools.py -v
```

**Expected:** All 18 tests pass (9 tests x asyncio + trio backends):
- find_postman returns sync mode
- manage_postman skips in non-api mode
- Parameter validation for all actions
- import/export not blocked by mode

### 11.4 Full test suite

```bash
cd python && uv run pytest tests/ -v --timeout=60
```

**Expected:** All existing tests + 40 new Postman tests pass. No regressions.

### 11.5 Frontend build

```bash
cd cortex-ui && npm run build
```

**Expected:** Build completes without TypeScript errors.

### 11.6 Lint checks

```bash
cd python && uv run ruff check src/server/services/postman/ src/server/api_routes/postman_api.py src/mcp_server/features/postman/
```

**Expected:** `All checks passed!`

---

## Phase 12: Edge Cases & Stress Tests

### 12.1 .env parsing edge cases

Test the `/api/postman/environments/sync` endpoint with these .env patterns:

```bash
curl -s -X POST http://localhost:8181/api/postman/environments/sync \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test",
    "system_name": "TEST",
    "env_file_content": "# Comment line\n\n  SPACED_KEY = spaced_value  \nQUOTED=\"double quoted\"\nSINGLE='\''single quoted'\''\nNO_VALUE=\nEMPTY=\"\"\nMULTI_EQUALS=key=value=extra\nUNDERSCORE_KEY_NAME=test"
  }' | jq
```

**Expected:**
- Comments and empty lines are ignored
- Leading/trailing whitespace on keys and values is trimmed
- Quotes (single and double) are stripped from values
- Keys with no value get empty string
- `=` signs within values are preserved (split on first `=` only)

### 12.2 Special characters in collection/folder names

1. Ask Claude to create a collection with special characters in the project name (e.g., "My Project (v2)")

**Expected:** Collection is created successfully. Name is preserved as-is.

### 12.3 Large number of requests

1. Ask Claude to add 20+ requests to a collection in rapid succession

**Expected:** All requests are added without errors. The GET→modify→PUT cycle handles large collections.

### 12.4 Concurrent mode switches

1. While Claude is working in API mode, switch to "git" mode in Settings
2. Claude tries to add another request

**Expected:** Claude's next `find_postman()` call (or mode check) detects the mode change and adjusts behavior accordingly. No crash or corruption.

---

## Test Results Summary

| Phase | Test | Status | Notes |
|-------|------|--------|-------|
| 1.1 | Migration column exists | | |
| 1.2 | Column is nullable | | |
| 2.1 | Mode selector appears | | |
| 2.2 | Set to Git | | |
| 2.3 | Set to API + warning | | |
| 2.4 | Set to Disabled | | |
| 2.5 | Persistence across refresh | | |
| 2.6 | API credentials configured | | |
| 3.1 | Status — disabled | | |
| 3.2 | Status — git | | |
| 3.3 | Status — api | | |
| 3.4 | Endpoints skip in non-api | | |
| 3.5 | .env sync parsing | | |
| 4.1 | MCP health check | | |
| 4.2 | Postman tools registered | | |
| 4.3 | Tools visible in Claude Code | | |
| 5.1 | find_postman status | | |
| 5.2 | Collection initialization | | |
| 5.3 | Add single request | | |
| 5.4 | Add CRUD endpoint set | | |
| 5.5 | Prevent duplicates | | |
| 5.6 | Update environment | | |
| 5.7 | Sync .env | | |
| 6.1 | Git mode status | | |
| 6.2 | MCP tools skip in git mode | | |
| 6.3 | Collection scaffold creation | | |
| 6.4 | Request YAML creation | | |
| 6.5 | Folder ordering | | |
| 6.6 | Environment YAML | | |
| 6.7 | Prevent duplicate YAML | | |
| 7.1 | Hook runs on session start | | |
| 7.2 | Environment created in Postman | | |
| 7.3 | Hook silent on failure | | |
| 7.4 | Hook silent in git mode | | |
| 8.1 | Import Git → API | | |
| 8.2 | Export API → Git | | |
| 9.1 | Disabled mode — no behavior | | |
| 9.2 | API mode — missing credentials | | |
| 9.3 | API mode — invalid key | | |
| 9.4 | Network failure handling | | |
| 10.1 | Rule 0: Mode check first | | |
| 10.2 | Rule 1: Always add + curl | | |
| 10.3 | Rule 2: Folder naming | | |
| 10.4 | Rule 3: Test script patterns | | |
| 10.5 | Rule 4: Doc references | | |
| 10.6 | Rule 5: Prevent duplicates | | |
| 10.7 | Rule 6: Graceful disabled | | |
| 11.1 | Service tests (16) | | |
| 11.2 | API route tests (6) | | |
| 11.3 | MCP tool tests (18) | | |
| 11.4 | Full test suite | | |
| 11.5 | Frontend build | | |
| 11.6 | Lint checks | | |
| 12.1 | .env edge cases | | |
| 12.2 | Special characters | | |
| 12.3 | Large request count | | |
| 12.4 | Concurrent mode switch | | |
