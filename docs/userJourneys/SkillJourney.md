# Skills Distribution System — Manual Test Plan

## Prerequisites

- Cortex server running (`docker compose up -d` or local)
- Cortex MCP connected in Claude Code
- At least one project created in the UI
- Server URL: `http://localhost:8181`

---

## Journey 1: Server Startup Auto-Seeds Skills

**What it tests:** `SkillSeedingService` runs on startup and populates `cortex_skills` from bundled SKILL.md files.

1. Restart the server:
   ```bash
   docker compose restart cortex-server
   # or locally: kill and re-run uv run python -m src.server.main
   ```
2. Check server logs for the seeding line:
   ```bash
   docker compose logs cortex-server | grep "Skills seeded"
   ```
   **Expected:** `✅ Skills seeded: N created, 0 updated, 0 unchanged` (or similar counts)

3. Verify skills appear in the API:
   ```bash
   curl http://localhost:8181/api/skills | python3 -m json.tool
   ```
   **Expected:** JSON with a `skills` array containing at least `cortex-bootstrap`, `cortex-memory`, `cortex-skill-sync`

4. Restart again (idempotency check):
   ```bash
   docker compose restart cortex-server
   docker compose logs cortex-server | grep "Skills seeded"
   ```
   **Expected:** `0 created, 0 updated, N unchanged` — no duplicates created

---

## Journey 2: GET /api/skills?include_content=true

**What it tests:** The `include_content` query parameter returns full SKILL.md content.

1. Without param (content omitted):
   ```bash
   curl "http://localhost:8181/api/skills" | python3 -m json.tool
   ```
   **Expected:** Skills listed, no `content` field on each skill (or `content: null`)

2. With param (content included):
   ```bash
   curl "http://localhost:8181/api/skills?include_content=true" | python3 -m json.tool
   ```
   **Expected:** Each skill has a non-empty `content` field with the full SKILL.md markdown text

---

## Journey 3: MCP Bootstrap Action

**What it tests:** `manage_skills(action="bootstrap")` fetches skills + registers system.

**Setup:** Open Claude Code in any project with the Cortex MCP connected.

1. Ask Claude:
   > "Call manage_skills with action=bootstrap, system_fingerprint=test-machine-001, system_name=My Test Machine"

   **Expected response contains:**
   - `success: true`
   - `skills`: array of skills with `name`, `display_name`, `content` fields
   - `install_path`: suggested path (e.g. `~/.claude/skills/`)
   - `message` describing what to do

2. With project registration — also pass a valid `project_id` from your Cortex project:
   > "Call manage_skills with action=bootstrap, system_fingerprint=test-machine-001, system_name=My Test Machine, project_id=<your-project-id>"

   **Expected:** Same as above, plus the system appears in the Skills tab of that project

3. Verify system was registered:
   ```bash
   curl "http://localhost:8181/api/projects/<your-project-id>/systems" | python3 -m json.tool
   ```
   **Expected:** System `My Test Machine` with fingerprint `test-machine-001` appears in the list

---

## Journey 4: cortex-bootstrap SKILL (full machine bootstrap)

**What it tests:** The `cortex-bootstrap` SKILL.md end-to-end flow.

**Setup:** Claude Code with Cortex MCP connected.

1. Trigger the skill:
   > "Bootstrap cortex skills on this machine"

   Or: `/cortex-bootstrap` if installed

2. Walk through the 7 phases — Claude should:
   - Phase 0: Check MCP health (`GET /health`)
   - Phase 1: Generate a fingerprint using `sha256sum` (Linux) or `shasum -a 256` (macOS)
   - Phase 2: Confirm system name with you
   - Phase 3: Read `~/.claude/cortex-state.json` (may not exist yet — that's fine)
   - Phase 4: Call `manage_skills(action="bootstrap", ...)`
   - Phase 5: Write each skill's content to `~/.claude/skills/<name>.md`
   - Phase 6: Write/merge `~/.claude/cortex-state.json` (system_id, system_name, fingerprint)
   - Phase 7: Report summary

3. Verify files were written:
   ```bash
   ls ~/.claude/skills/
   cat ~/.claude/cortex-state.json
   ```
   **Expected:** SKILL.md files for each skill, and `cortex-state.json` with your system info

---

## Journey 5: Skills Tab — Remove a Skill

**What it tests:** The Remove button in `SystemSkillList` calls the remove endpoint.

**Setup:** In the Cortex UI, navigate to a project → Skills tab. A system must be registered with at least one installed skill.

1. Select a system from the left panel
2. In the skill list, find an **installed** skill (shown with a status badge)
3. Click the **Remove** button next to it
4. **Expected:** The skill disappears from the installed list (or its status changes to "not installed")
5. Refresh the page — verify the skill remains removed (server-side, not just optimistic)

---

## Journey 6: Skills Tab — Unlink a System

**What it tests:** The Unlink button in `SystemCard` calls `DELETE /api/projects/{id}/systems/{id}` and clears selection.

**Setup:** Skills tab with at least one registered system visible.

1. Note the system name in the left panel
2. Click **"Unlink from project"** below the system name
3. **Expected:**
   - System disappears from the left panel
   - Detail panel clears (no stale content shown)
4. Verify via API:
   ```bash
   curl "http://localhost:8181/api/projects/<project-id>/systems" | python3 -m json.tool
   ```
   **Expected:** The unlinked system no longer appears

---

## Journey 7: Edge Cases

| Scenario | Steps | Expected |
|---|---|---|
| Unlink non-existent system | `curl -X DELETE http://localhost:8181/api/projects/bad-id/systems/bad-id` | HTTP 404 |
| Bootstrap with no project_id | Call `manage_skills(action="bootstrap", system_fingerprint=x, system_name=y)` | Returns skills, no sync call, no 500 error |
| Skills content idempotency | Restart server twice, check seeding logs | `0 created` on 2nd restart (hash-based skip) |
| Biome/TS clean | `cd cortex-ui && npx tsc --noEmit && npm run biome` | No errors |

---

## Journey 8: Postman Collection — Using the API Test Suite

**What it tests:** The `postman/` directory contains a complete, executable Collections-as-Code test suite for all Cortex API endpoints, replacing ad-hoc curl commands with version-controlled, repeatable Postman requests.

### Prerequisites

- [Postman Desktop App](https://www.postman.com/downloads/) installed (v10+ recommended)
- OR the [Postman CLI](https://learning.postman.com/docs/postman-cli/postman-cli-installation/) for terminal-based execution
- Cortex server running locally on port 8181

### 8.1: Import the Collection into Postman

1. Open Postman Desktop
2. Enable **Collections as Code** in Settings > General (if not already enabled)
3. Connect your local repo folder to Postman:
   - Go to **File > Open Folder** (or drag-drop the repo root)
   - Postman auto-detects the `postman/` directory and loads the collection
4. **Expected:** The `Cortex` collection appears in the sidebar with 23 domain folders:

   | Folder | Endpoints | What It Covers |
   |--------|-----------|----------------|
   | Health | 2 | Root and API health checks |
   | Settings | 10 | Credentials CRUD, database metrics |
   | Knowledge | 19 | Sources, crawling, RAG, code search |
   | Pages | 3 | Page listing and retrieval |
   | Projects | 9 | Project CRUD, features, task counts |
   | Tasks | 7 | Task CRUD, project-scoped tasks |
   | Documents | 5 | Project document CRUD |
   | Versions | 4 | Version history and restore |
   | Extensions | 9 | Extension CRUD, validation |
   | Systems | 11 | System registration, project linking |
   | Sessions | 3 | Session memory management |
   | Progress | 2 | Operation tracking |
   | MCP | 5 | MCP server status and config |
   | Agent Chat | 4 | Chat session management |
   | Bug Reports | 2 | GitHub issue submission |
   | Providers | 1 | Provider status check |
   | Version | 3 | Version check and cache |
   | Migrations | 3 | Migration status and history |
   | Ollama | 4 | Ollama instance management |
   | OpenRouter | 1 | Model listing |
   | Materialization | 6 | Document materialization |
   | LeaveOff | 3 | Session leave-off points |
   | Internal | 3 | Internal/debug endpoints |

5. Select the `Cortex - Local` environment from the environment dropdown

### 8.2: Run a Single Request

1. Expand `Cortex` > `Health` > `Root Health`
2. Click **Send**
3. **Expected:**
   - Status: `200 OK`
   - Response body includes `status` and `version` fields
   - Test Results tab shows all tests passing (green checkmarks)

### 8.3: Run an Entire Folder

1. Right-click the `Projects` folder > **Run folder**
2. Postman executes requests in order (1000, 2000, 3000...)
3. **Expected flow:**
   - `List Projects` (GET) — passes
   - `Create Project` (POST) — creates project, captures `projectId` into collection variables
   - `Get Project` (GET) — uses captured `{{projectId}}`, passes
   - `Update Project` (PUT) — updates the captured project, passes
   - `Delete Project` (DELETE) — cleans up, passes
   - Remaining read-only requests pass independently

### 8.4: Run the Full Collection via CLI

Instead of manually curling each endpoint, run the entire suite:

```bash
# Run the full collection against local environment
postman collection run postman/collections/Cortex/ \
  --environment postman/environments/Cortex\ -\ Local.environment.yaml

# Run a specific folder only
postman collection run postman/collections/Cortex/Knowledge/ \
  --environment postman/environments/Cortex\ -\ Local.environment.yaml
```

**Expected:** All tests pass. Failed tests show clear diagnostics about which status code or response shape was wrong.

### 8.5: Request Chaining — CRUD Workflow

The collection uses `pm.collectionVariables.set()` in afterResponse scripts to chain requests:

1. `Create Project` captures `projectId`
2. `Create Task` uses `{{projectId}}` and captures `taskId`
3. `Create Project Doc` uses `{{projectId}}` and captures `docId`
4. Subsequent GET/PUT/DELETE requests use these captured IDs

This means running folders in order (Projects > Tasks > Documents) creates a complete end-to-end workflow without manually copying IDs.

### 8.6: Environment Management

Two environment files are provided:

| File | Use Case |
|------|----------|
| `Cortex - Local.environment.yaml` | Local dev: `baseUrl = http://localhost:8181` |
| `Cortex - CI.environment.yaml` | CI/CD: Docker service names as hosts |

To add a custom environment (e.g., staging):
1. Copy `Cortex - Local.environment.yaml` to `Cortex - Staging.environment.yaml`
2. Update the `baseUrl` value to your staging server
3. Commit — the new environment appears automatically in Postman

### 8.7: Replacing curl Commands

Instead of ad-hoc curl commands like:

```bash
# Old way — manual, not repeatable, no assertions
curl -X POST http://localhost:8181/api/projects \
  -H "Content-Type: application/json" \
  -d '{"title": "My Project"}' | python3 -m json.tool
```

Use the Postman collection:

```bash
# New way — repeatable, with assertions, version-controlled
postman collection run postman/collections/Cortex/Projects/ \
  --environment postman/environments/Cortex\ -\ Local.environment.yaml
```

Or open `postman/collections/Cortex/Projects/Create Project.request.yaml` in Postman and click Send. The test script automatically verifies the response status and shape.

### 8.8: Adding New Endpoints

When a new API endpoint is added to Cortex:

1. Create a `.request.yaml` file in the appropriate folder under `postman/collections/Cortex/`
2. Follow the existing format — see any existing request file for the template
3. Include an `afterResponse` test script
4. Update the environment YAML if new variables are needed
5. Commit the file — Postman auto-syncs it

**File format reference:**

```yaml
$kind: http-request
name: My New Endpoint
url: "{{baseUrl}}/api/my-endpoint"
method: POST
description: What this endpoint does

headers:
  Content-Type: application/json

body:
  type: text
  content: |
    {
      "field": "value"
    }

scripts:
  - type: afterResponse
    code: |-
      pm.test('Status is 200', function () {
          pm.response.to.have.status(200);
      });
    language: text/javascript

order: 1000
```

### 8.9: CI/CD Integration

Add to your GitHub Actions workflow:

```yaml
- name: Run Cortex API Tests
  uses: postmanlabs/postman-cli-action@v1
  with:
    command: >
      collection run postman/collections/Cortex/
      --environment postman/environments/Cortex\ -\ CI.environment.yaml
```

No Postman API key or account required — the CLI runs directly on the YAML files.

---

## Journey 9: Postman Collection — Directory Reference

Full directory tree for the Postman collection:

```
postman/
├── collections/
│   └── Cortex/
│       ├── .resources/definition.yaml          # Collection metadata + variables
│       ├── Health/                              # 2 requests
│       ├── Settings/                            # 10 requests
│       ├── Knowledge/                           # 19 requests
│       ├── Pages/                               # 3 requests
│       ├── Projects/                            # 9 requests
│       ├── Tasks/                               # 7 requests
│       ├── Documents/                           # 5 requests
│       ├── Versions/                            # 4 requests
│       ├── Extensions/                          # 9 requests
│       ├── Systems/                             # 11 requests
│       ├── Sessions/                            # 3 requests
│       ├── Progress/                            # 2 requests
│       ├── MCP/                                 # 5 requests
│       ├── Agent Chat/                          # 4 requests
│       ├── Bug Reports/                         # 2 requests
│       ├── Providers/                           # 1 request
│       ├── Version/                             # 3 requests
│       ├── Migrations/                          # 3 requests
│       ├── Ollama/                              # 4 requests
│       ├── OpenRouter/                          # 1 request
│       ├── Materialization/                     # 6 requests
│       ├── LeaveOff/                            # 3 requests
│       └── Internal/                            # 3 requests
├── environments/
│   ├── Cortex - Local.environment.yaml          # Local dev
│   └── Cortex - CI.environment.yaml             # CI/CD
└── globals/
    └── workspace.globals.yaml                   # Workspace constants
```

**Total: 119 request files across 23 folders, covering all Cortex API endpoints.**
