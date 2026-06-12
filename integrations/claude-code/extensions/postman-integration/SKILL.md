---
name: postman-integration
description: Use when suggesting API calls for testing, writing test plans, creating documentation that references API endpoints, or when the user mentions Postman. Maintains Postman collections in dual-mode — Cloud API sync via MCP tools or local Git YAML files — based on the configured POSTMAN_SYNC_MODE.
---

# Postman Integration — Dual-Mode

Maintain a Postman collection and environment per project. Supports two sync modes:

- **`api`** — Claude calls `manage_postman()` MCP tools → Cortex pushes to Postman Cloud
- **`git`** — Claude writes `.request.yaml` files directly to the repo (Collections as Code)

**Reference implementation (git mode):** `reference_repos/PostmanFastAPIDemo/postman/`

---

## Rule 0: Mode Check — ALWAYS DO THIS FIRST

On first Postman-related action per session, call `find_postman()` with no parameters. It returns:

```json
{ "sync_mode": "api" | "git" | "disabled", ... }
```

**Branch all subsequent behavior on `sync_mode`:**
- `api` → follow **API Mode Rules** (use MCP tools)
- `git` → follow **Git Mode Rules** (write YAML files)
- `disabled` → provide curl commands only, skip all Postman operations

**Cache the mode for the session.** Do not re-check on every request.

---

## Shared Rules (Both Modes)

### Rule 1: Always Add, Never Just Curl

When suggesting an API call for testing:

- **Add** the request to the Postman collection (via MCP tool or YAML file, per mode)
- **Include** test scripts that verify status and capture IDs (see Rule 3)
- **Tell the user** where it was added
- **Also provide** the curl equivalent inline for quick terminal testing

Never provide only a curl command without also adding to the collection.

### Rule 2: Folder Naming — Framework-Agnostic

Use the core resource name or domain grouping as the folder name. Derive from the controller/router file regardless of framework:

| Source File | Folder Name |
|-------------|-------------|
| `projects_api.py` | `Projects` |
| `users.controller.ts` | `Users` |
| `AuthRouter.java` | `Auth` |
| `handlers/orders.go` | `Orders` |
| Health check endpoints | `Health` |

### Rule 3: Test Script Patterns

Every request gets test scripts. Use the same patterns in both modes:

**Create (POST):**
```javascript
pm.test('Status is 201', function () {
    pm.response.to.have.status(201);
});

pm.test('Response has ID', function () {
    var json = pm.response.json();
    pm.expect(json.id).to.be.a('string');
    pm.collectionVariables.set('projectId', json.id);
});
```

**List (GET array):**
```javascript
pm.test('Status is 200', function () {
    pm.response.to.have.status(200);
});

pm.test('Returns array', function () {
    pm.expect(pm.response.json()).to.be.an('array');
});
```

**Read (GET single):**
```javascript
pm.test('Status is 200', function () {
    pm.response.to.have.status(200);
});

pm.test('Returns expected resource', function () {
    pm.expect(pm.response.json().id).to.eql(pm.collectionVariables.get('projectId'));
});
```

**Update (PUT/PATCH):**
```javascript
pm.test('Status is 200', function () {
    pm.response.to.have.status(200);
});
```

**Delete:**
```javascript
pm.test('Status is 200 or 204', function () {
    pm.expect(pm.response.code).to.be.oneOf([200, 204]);
});
```

**Error case (expected 404/400):**
```javascript
pm.test('Status is 404', function () {
    pm.response.to.have.status(404);
});
```

Captured variable names use camelCase: `projectId`, `taskId`, `sourceId`.

### Rule 4: Documentation References (Contextual)

**Test plans / user journeys** — per-step:

> Step 3: Create a new project via `POST /api/projects`
> *(Postman: `{Project}` → `Projects` → `Create Project`)*

**Architecture docs / general docs** — single summary section:

> ## API Testing
> All endpoints are available in the Postman collection for this project.

**Code comments** — no Postman references.

### Rule 5: Prevent Duplicates

- **API mode**: Call `find_postman(query="<Request Name>")` before adding. If it exists, update.
- **Git mode**: Check if a `.request.yaml` with the same name exists. If the URL + method matches an existing file, update it.

### Rule 6: Graceful Degradation

When `sync_mode` is `disabled`:
- Provide curl commands and documentation as normal
- Do not prompt the user to configure Postman unless they ask
- Do not create any Postman files or call any Postman MCP tools

---

## API Mode Rules

When `sync_mode` is `api`, use the Cortex MCP tools. Claude never possesses the API key — Cortex handles all Postman API communication server-side.

### Collection Initialization

If the project has no Postman collection yet:

```
manage_postman(action="init_collection", project_id="...", project_name="Cortex")
```

This creates the collection in Postman Cloud and stores the UID on the Cortex project.

### Adding Requests

```
manage_postman(
    action="add_request",
    project_id="...",
    folder_name="Projects",
    request={
        "name": "Create Project",
        "method": "POST",
        "url": "{{base_url}}/api/projects",
        "headers": {"Content-Type": "application/json"},
        "body": {"name": "My Project", "description": "..."},
        "description": "Creates a new Cortex project",
        "test_script": "pm.test('Status is 201', function() { pm.response.to.have.status(201); }); var json = pm.response.json(); pm.collectionVariables.set('projectId', json.id);"
    }
)
```

If no collection exists yet, `add_request` auto-calls `init_collection`.

### Environment Management

```
manage_postman(
    action="update_environment",
    project_id="...",
    system_name="WIN-DEV-01",
    variables={"base_url": "http://172.16.1.230:8181", "supabase_url": "http://172.16.1.230:8000"}
)
```

**Do not manually redact API keys or passwords** when passing them to `update_environment`. The Cortex backend automatically detects sensitive keys and marks them as secret in Postman.

### Collection Naming

- Primary: Cortex project name (e.g., `Cortex`)
- Fallback: Git repo name — just repo name, no owner prefix

### Environment Naming

Format: `{Project Name} - {System Name}` (e.g., `Cortex - WIN-DEV-01`)

---

## Git Mode Rules

When `sync_mode` is `git`, write Postman-compatible YAML files directly to the repository.

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

**Project name**: Use the Cortex project name if linked (from `.claude/cortex-state.json`), otherwise `basename $(git rev-parse --show-toplevel)`. Never include the owner prefix.

### Collection Initialization

When `postman/collections/` does not exist and you are about to suggest testing an API call:

1. Ask the user before creating (unless they've already mentioned Postman)
2. Create `postman/collections/{Project}/.resources/definition.yaml`:

```yaml
$kind: collection
description: >
  API collection for {Project Name}.
variables:
  baseUrl: "{{baseUrl}}"
```

3. Create `postman/environments/{Project} - Local.environment.yaml`:

```yaml
name: "{Project Name} - Local"
values:
  - key: baseUrl
    value: http://localhost:{port}
    enabled: true
color: null
```

4. Commit the scaffold.

### Request File Format

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

**Requirements:**
- `$kind: http-request` — required by Postman
- `url` with `{{baseUrl}}` prefix — never hardcode host/port
- `{{variableName}}` for all dynamic values — never hardcode IDs or tokens
- `headers` when the request has a body
- `order` for execution sequencing (increments of 1000)
- `description` summarizing what the request does

### Environment Files

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

When a request references variables not in the environment file, add them. Derive values from the project's `.env` when possible. Write empty strings for secrets — do not commit real credentials.

### Folder Ordering

Each folder gets `.resources/definition.yaml`:

```yaml
$kind: collection
order: 2000
```

Order: `Health` (1000) → domain folders alphabetically (2000, 3000...).

**Request ordering** within folders:

| Operation | Order |
|-----------|-------|
| List / Get All | 1000 |
| Search / Filter | 2000 |
| Create | 3000 |
| Get by ID | 4000 |
| Update | 5000 |
| Delete | 6000 |
| Error cases | 7000+ |

### Collection Variables

Add variables to `postman/collections/{Project}/.resources/definition.yaml` whenever `afterResponse` scripts use `pm.collectionVariables.set()`:

```yaml
variables:
  baseUrl: "{{baseUrl}}"
  projectId: ""
  taskId: ""
```

### Graceful Git Behavior

- If `postman/` doesn't exist and the user hasn't mentioned Postman, ask before scaffolding
- If `postman/` exists, always maintain it when suggesting API tests
- If the user asks for "just a curl command," provide only the curl

---

## Quick Reference

### YAML Schema (Git Mode)

| File Type | Path | Required Fields |
|-----------|------|-----------------|
| Collection definition | `{Collection}/.resources/definition.yaml` | `$kind` |
| Folder definition | `{Folder}/.resources/definition.yaml` | `$kind`, `order` |
| HTTP request | `{Folder}/{Name}.request.yaml` | `$kind`, `url`, `method`, `order` |
| Environment | `environments/{Name}.environment.yaml` | `name`, `values` |

### MCP Tools (API Mode)

| Tool | Purpose |
|------|---------|
| `find_postman()` | Get sync mode, collection info, search for duplicates |
| `manage_postman(action="init_collection")` | Create collection for project |
| `manage_postman(action="add_request")` | Add/update request in collection |
| `manage_postman(action="update_environment")` | Create/update environment |
| `manage_postman(action="remove_request")` | Remove a request |
| `manage_postman(action="sync_environment")` | Push .env to Postman environment |

### Cross-Mode Sync (MCP Tools)

| Tool | Purpose |
|------|---------|
| `manage_postman(action="import_from_git")` | Read local `postman/` YAML files → push to Postman Cloud |
| `manage_postman(action="export_to_git")` | Pull from Postman Cloud → write YAML files to `postman/` |

Use these when the user wants to replicate their collection to the other mode, or when switching modes with existing data.

### CLI Execution (Git Mode)

```bash
postman collection run postman/collections/{Project}/ \
  --environment postman/environments/{Project}\ -\ Local.environment.yaml
```
