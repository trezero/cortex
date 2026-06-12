# API Documentation Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a portable Claude Code skill that enforces FastAPI API documentation quality and generates Postman collection entries.

**Architecture:** Single SKILL.md behavioral file at `integrations/claude-code/extensions/api-docs/SKILL.md`. No backend, no Python scripts, no MCP tools. The skill instructs Claude Code how to behave when creating or auditing FastAPI endpoints. Supersedes the existing `fastapi-patterns` skill.

**Tech Stack:** Markdown (SKILL.md format), YAML frontmatter, Claude Code tools (Read, Write, Edit, Glob, Grep)

**Spec:** `docs/superpowers/specs/2026-03-20-api-docs-skill-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `integrations/claude-code/extensions/api-docs/SKILL.md` | The skill file |
| Delete | `.claude/skills/fastapi-patterns/SKILL.md` | Superseded skill |
| Delete | `.claude/skills/fastapi-patterns/` (directory) | Clean up empty directory |

This is a single-file deliverable. Each task below adds a section to the SKILL.md, building it up incrementally. The file is committed after major sections are complete.

---

### Task 1: Create SKILL.md with Frontmatter and Guard

**Files:**
- Create: `integrations/claude-code/extensions/api-docs/SKILL.md`

This task creates the file with the YAML frontmatter, skill title, and the guard section that detects whether the project uses FastAPI.

- [ ] **Step 1: Create the directory**

```bash
mkdir -p integrations/claude-code/extensions/api-docs
```

- [ ] **Step 2: Write initial SKILL.md with frontmatter and guard**

Create `integrations/claude-code/extensions/api-docs/SKILL.md` with this content:

```markdown
---
name: api-docs
description: Use when creating, modifying, or reviewing FastAPI API endpoints. Ensures endpoints have complete OpenAPI documentation including response models, field descriptions, status codes, and examples. Also generates Postman collection entries. Triggers on: "create endpoint", "add API route", "document API", "audit endpoints", "retrofit API docs", or when working in FastAPI route files.
---

# API Documentation Enforcement

Ensures every FastAPI endpoint has complete OpenAPI documentation and generates Postman collection entries. Works in any FastAPI project by discovering project structure at runtime.

## Phase 0: Guard — Detect FastAPI

Before doing anything, confirm this project uses FastAPI.

1. Use Grep to search for `APIRouter` or `FastAPI` in `*.py` files from the project root
   - Exclude: `venv/`, `.venv/`, `node_modules/`, `__pycache__/`, `.git/`, `site-packages/`
   - A single match is sufficient
2. **If found:** Proceed to Phase 1 (Project Discovery)
3. **If not found:** Output: *"Skipping API documentation — no FastAPI endpoints detected in this project."* and stop. Do not proceed further.
```

- [ ] **Step 3: Verify frontmatter is valid**

Read the file back and confirm:
- Frontmatter block starts with `---` on line 1
- Contains `name: api-docs`
- Contains `description:` with trigger phrases
- Frontmatter block closes with `---`
- Body content follows after the frontmatter

- [ ] **Step 4: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): create skill with frontmatter and FastAPI guard"
```

---

### Task 2: Add Project Discovery Section

**Files:**
- Modify: `integrations/claude-code/extensions/api-docs/SKILL.md`

Adds the section that instructs Claude how to discover the project layout before running either mode.

- [ ] **Step 1: Append project discovery section to the end of the file**

Add the following to the end of the SKILL.md file (after the Guard section):

```markdown
## Phase 1: Project Discovery

Run once per activation. Discover the project layout silently — no output to the user unless something unexpected is found (e.g., multiple FastAPI apps).

### Step 1: Find Python package root
Use Glob to find `pyproject.toml`, `setup.py`, or `requirements.txt`. The directory containing the first match is the Python package root.

### Step 2: Find all route files
Use Grep to find all `.py` files containing `APIRouter()`. These are the route files. Note the directory they live in — this is the route directory (e.g., `api_routes/`, `routes/`, `routers/`).

### Step 3: Infer service directory
Read several route files and look for import statements that reference service modules (e.g., `from ...services.project_service import ...`). The directory these imports resolve to is the service directory. If no service imports are found, note that the project does not use a service layer.

### Step 4: Determine model location
Check if route files define Pydantic models inline (classes inheriting `BaseModel` in the same file as route handlers) or import them from separate files (`schemas.py`, `models.py`). Follow whichever convention the project uses.

### Step 5: Detect Pydantic version
Check `pyproject.toml` or `requirements.txt` for the pydantic version:
- `pydantic>=2` or `pydantic==2.*` → **Pydantic v2** — use `model_config = ConfigDict(...)`, `json_schema_extra`
- `pydantic>=1` or `pydantic==1.*` → **Pydantic v1** — use `class Config`, `schema_extra`
- Cannot determine → default to **Pydantic v2**

### Step 6: Find app entry point
Use Grep to find the file containing `include_router(` — this is the app entry point (e.g., `main.py`). Needed for wiring new routers.

### Step 7: Check Postman integration
Check if the postman-integration skill is available (look for it in the current skill set or check for `postman-integration` in available skills). If available, Postman collection generation will be performed after endpoint work. If not, skip Postman steps silently.

### Multiple FastAPI apps
If Grep finds `FastAPI()` instantiated in more than one file, ask the user which app to target before proceeding.

### Discovery output
After discovery, you should know:
- Route directory path and list of route files
- Service directory path (or "none")
- Model convention (inline or separate files)
- Pydantic version (v1 or v2)
- App entry point path
- Postman integration availability (yes/no)

Proceed to Phase 2 (Mode Detection).
```

- [ ] **Step 2: Verify the section reads correctly**

Read the file and confirm Phase 1 follows Phase 0 and all 7 discovery steps are present.

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): add project discovery phase"
```

---

### Task 3: Add Mode Detection and Documentation Standards

**Files:**
- Modify: `integrations/claude-code/extensions/api-docs/SKILL.md`

Adds mode detection logic and the documentation standards that both modes enforce.

- [ ] **Step 1: Append mode detection section to the end of the file**

```markdown
## Phase 2: Mode Detection

Determine which mode to run based on context:

- **Intercept mode** — You are mid-task building a feature and need to create or modify endpoints. The skill was triggered by the frontmatter matching your current work context (creating route handlers, working in files with `APIRouter()`). Go to Phase 3.
- **Retrofit mode** — The user explicitly asked to document, audit, or review existing endpoints (e.g., "document all API endpoints", "audit the projects API", "generate API docs for this repo"). Go to Phase 4.
- **Ambiguous** — Ask the user: *"Should I apply documentation standards to the endpoints you're building (intercept), or audit and fix existing endpoints (retrofit)?"*
```

- [ ] **Step 2: Append documentation standards section to the end of the file**

```markdown
## Documentation Standards

Both modes enforce these standards. An endpoint is "fully documented" when ALL of the following are present.

### Route Decorator Requirements

Every route decorator (`@router.get`, `@router.post`, etc.) MUST have:

| Parameter | Rule | Example |
|-----------|------|---------|
| `response_model` | Pydantic model defining the response shape | `response_model=ProjectResponse` |
| `status_code` | Explicit HTTP status code | `status_code=201` for POST, `200` for GET, `204` for DELETE |
| `tags` | At least one tag for Swagger UI grouping | `tags=["projects"]` |
| `description` | One-line summary (alternative to docstring) | `description="Create a new project"` |
| `responses` | Error responses the endpoint can return | `responses={404: {"description": "Not found"}}` |

The endpoint function MUST have:
- A **docstring** OR the decorator must have a `description` parameter — one-line summary of what the endpoint does
- **Type hints** on all parameters
- **Return type annotation** matching the `response_model`

### Pydantic Model Requirements

Every request and response model MUST have:

**All fields** use `Field()` with a `description`:
```python
# Required field
title: str = Field(..., description="The project title")

# Optional field
description: str | None = Field(None, description="Optional project summary")
```

**Response models** include an example:

Pydantic v2:
```python
class ProjectResponse(BaseModel):
    id: str = Field(..., description="Unique project identifier")
    title: str = Field(..., description="The project title")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "proj_abc123",
                "title": "My Project"
            }
        }
    )
```

Pydantic v1:
```python
class ProjectResponse(BaseModel):
    id: str = Field(..., description="Unique project identifier")
    title: str = Field(..., description="The project title")

    class Config:
        schema_extra = {
            "example": {
                "id": "proj_abc123",
                "title": "My Project"
            }
        }
```

Use whichever version was detected during Project Discovery (Phase 1, Step 5).

### What This Skill Does NOT Enforce

- Docstring format or length beyond "exists and is non-empty"
- Specific tag naming conventions (use what the project already uses, or the feature name)
- Authentication/authorization patterns
- Service layer implementation details
- Test coverage
```

- [ ] **Step 3: Verify both sections read correctly**

Read the file and confirm Phase 2 follows Phase 1, and Documentation Standards follows Phase 2. Verify the code examples render properly.

- [ ] **Step 4: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): add mode detection and documentation standards"
```

---

### Task 4: Add Intercept Mode

**Files:**
- Modify: `integrations/claude-code/extensions/api-docs/SKILL.md`

Adds the intercept mode workflow — the mode that activates during feature development.

- [ ] **Step 1: Append intercept mode section to the end of the file**

```markdown
## Phase 3: Intercept Mode

Intercept mode is invisible. The developer asks for a feature, and the endpoints come out fully documented. This is a quality standard, not a workflow step.

### Workflow

#### Step 1: Apply documentation standards inline

As you write the endpoint, bake in all documentation standards from the start. Do not write a bare endpoint and fix it later — write it correctly the first time:

```python
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

router = APIRouter(prefix="/projects", tags=["projects"])

class CreateProjectRequest(BaseModel):
    title: str = Field(..., description="The project title")
    description: str | None = Field(None, description="Optional project summary")

class ProjectResponse(BaseModel):
    id: str = Field(..., description="Unique project identifier")
    title: str = Field(..., description="The project title")
    description: str | None = Field(None, description="Optional project summary")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "proj_abc123",
                "title": "My Project",
                "description": "A sample project",
                "created_at": "2026-01-15T10:30:00Z"
            }
        }
    )

@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
    responses={
        422: {"description": "Validation error in request body"},
    },
)
async def create_project(request: CreateProjectRequest) -> ProjectResponse:
    """Create a new project."""
    return await project_service.create(request)
```

Adapt this pattern to the project's conventions discovered in Phase 1 (Pydantic version, model location, import style).

#### Step 2: Full slice scaffolding (when applicable)

If creating a new endpoint and the supporting service method does not exist:

1. **Create service method stub** — In the service file discovered during Phase 1, add a stub method:
   ```python
   async def create(self, request: CreateProjectRequest) -> dict:
       """Create a new project."""
       raise NotImplementedError("TODO: implement")
   ```
2. **Create service file if needed** — If no service file exists for this feature, create one following the closest existing service file's pattern (imports, class structure, constructor).
3. **Wire router if needed** — If this is a brand new feature router, add `app.include_router(...)` to the app entry point found in Phase 1.

**Skip scaffolding entirely if:**
- The project does not have a service layer (no service files found in Phase 1)
- The endpoint is being added to an existing feature that already has services wired up

#### Step 3: Postman handoff

After the endpoint is written and committed, follow the Postman Integration instructions in Phase 5.

#### Step 4: Continue

Resume the developer's original task. Do not produce a report or prompt for review — the endpoint is already documented.
```

- [ ] **Step 2: Verify the section reads correctly**

Read the file and confirm Phase 3 follows the Documentation Standards section. Verify the code example is complete and the scaffolding rules are clear.

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): add intercept mode workflow"
```

---

### Task 5: Add Retrofit Mode

**Files:**
- Modify: `integrations/claude-code/extensions/api-docs/SKILL.md`

Adds the retrofit mode workflow — the on-demand audit and fix mode.

- [ ] **Step 1: Append retrofit mode section to the end of the file**

```markdown
## Phase 4: Retrofit Mode

Retrofit mode is a bulk operation for documenting existing endpoints. Run once to bring a codebase up to standard.

### Step 1: Determine scope

Based on the user's request:
- **Whole repo** — Use all route files found during Phase 1
- **Specific feature** — Match route files by feature name (e.g., "projects" → files containing "project" in the path or router prefix)

### Step 2: Scan for documentation gaps

For each endpoint in scope, check against the Documentation Standards. For each endpoint, check:

1. Does the route decorator have `response_model`?
2. Does it have an explicit `status_code`?
3. Does it have `tags`?
4. Does it have `responses` for error codes?
5. Does the function have a docstring?
6. Does the function have type hints on all parameters?
7. Does it have a return type annotation?
8. Do all Pydantic request/response model fields use `Field(description=...)`?
9. Do response models have examples (`json_schema_extra` or `schema_extra`)?

Tally:
- Total endpoints found
- Number with at least one gap
- Number of files affected
- Breakdown by gap type

### Step 3: Report to user

Present the findings:

*"Found {gap_count} documentation gaps across {file_count} files ({endpoint_count} endpoints). Want a dry-run report first, or should I fix them all?"*

**If the user asks for a dry-run report**, produce a table:

```
| File | Endpoint | Missing |
|------|----------|---------|
| projects_api.py | GET /api/projects | response_model, responses |
| projects_api.py | POST /api/projects | Field descriptions, json_schema_extra |
| knowledge_api.py | GET /api/knowledge/search | response_model, status_code |
```

After the dry run, ask: *"Fix all, or skip?"*

### Step 4: Fix in place

For each endpoint with gaps, edit the file to add what's missing:

1. **Missing `response_model`** — Read the endpoint's return statement to infer the response shape. Create a Pydantic response model with `Field(description=...)` on every field and an example. Add `response_model=ModelName` to the decorator.
2. **Missing `status_code`** — Add based on HTTP method: `201` for POST (create), `200` for GET/PUT/PATCH, `204` for DELETE.
3. **Missing `tags`** — Infer from the router prefix or file name. Add `tags=["feature_name"]`.
4. **Missing `responses`** — Check the function body for `HTTPException` raises. Add a `responses` dict documenting each error status code.
5. **Missing docstring** — Write a one-line summary based on the function name and HTTP method.
6. **Missing type hints** — Add type annotations based on usage.
7. **Missing return type** — Add annotation matching the `response_model`.
8. **Missing `Field(description=...)`** — Add descriptions to all Pydantic model fields. Infer descriptions from field names.
9. **Missing examples** — Add `json_schema_extra` (v2) or `schema_extra` (v1) with realistic sample data.

**Preserve existing documentation** — only fill gaps. Do not overwrite existing docstrings, descriptions, or field annotations.

**Report progress** on large operations: *"Fixed 8/23 endpoints (projects_api.py complete, starting tasks_api.py...)"*

### Step 5: Postman handoff

After all fixes are applied, follow the Postman Integration instructions in Phase 5 for all endpoints in scope.

### Step 6: Summary

*"Documented {endpoint_count} endpoints across {file_count} files. Postman collection entries generated for all endpoints."*
```

- [ ] **Step 2: Verify the section reads correctly**

Read the file and confirm Phase 4 follows Phase 3. Verify the scanning checklist has all 9 items and the fix instructions cover all gap types.

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): add retrofit mode workflow"
```

---

### Task 6: Add Postman Integration and Edge Cases

**Files:**
- Modify: `integrations/claude-code/extensions/api-docs/SKILL.md`

Adds the Postman handoff section and edge case handling.

- [ ] **Step 1: Append Postman integration section to the end of the file**

```markdown
## Phase 5: Postman Integration

This phase runs after endpoint work in either mode. It is a behavioral handoff — follow the postman-integration skill's own rules to create collection entries.

### Step 1: Check availability

Is the postman-integration skill available in the current session? If not, output:
*"Postman integration not available — skipping collection generation. Install the postman-integration skill to enable this."*
and skip to the end.

### Step 2: Gather endpoint data

For each new or modified endpoint, collect:
- HTTP method and full path (e.g., `GET /api/projects/{project_id}/stats`)
- Description (from the docstring)
- Request body schema (from the Pydantic request model fields and descriptions)
- Response body example (from `json_schema_extra` or `schema_extra`)
- Path parameters with descriptions (from function signature type hints)
- Query parameters with descriptions (from function signature defaults)
- Expected status codes — success (from `status_code`) and errors (from `responses`)

### Step 3: Follow postman-integration rules

With the endpoint data gathered, follow the postman-integration skill's workflow:

1. Call `find_postman()` to determine the sync mode (API mode, Git mode, or disabled)
2. **API mode:** Call `manage_postman(action="add_request")` with the endpoint data for each endpoint
3. **Git mode:** Write `.request.yaml` files to the `postman/` directory following the postman-integration skill's YAML schema and folder structure
4. **Disabled:** Skip silently

This skill does NOT own Postman collection structure, naming, or sync logic. Follow the postman-integration skill's rules exactly.
```

- [ ] **Step 2: Append edge cases section to the end of the file**

```markdown
## Edge Cases

### Complex response types
- `list[Item]` → Use `response_model=list[ItemResponse]`
- Raw `dict` return → Create a typed Pydantic response model to replace it
- Union types → Use Pydantic discriminated unions where possible

### Existing partial documentation
Retrofit mode preserves existing documentation. Only fill gaps — never overwrite existing docstrings, field descriptions, or model examples.

### No service layer
If the project has no service files (none found in Phase 1), skip all service scaffolding in Intercept mode. Only create the route handler and Pydantic models.

### Pydantic v1 vs v2
Detected in Phase 1, Step 5. Use the appropriate syntax throughout:
- **v2:** `model_config = ConfigDict(...)`, `json_schema_extra`, `Field(...)`
- **v1:** `class Config`, `schema_extra`, `Field(...)`
If version cannot be determined, default to Pydantic v2.

### Models inline vs separate files
Detected in Phase 1, Step 4. Follow whatever convention the project uses:
- If models are inline in route files → define new models in the same route file
- If models are in separate `schemas.py` or `models.py` files → create models there
```

- [ ] **Step 3: Verify both sections read correctly**

Read the file and confirm Phase 5 follows Phase 4, and Edge Cases follows Phase 5.

- [ ] **Step 4: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): add postman integration and edge cases"
```

---

### Task 7: Add Absorbed FastAPI Patterns

**Files:**
- Modify: `integrations/claude-code/extensions/api-docs/SKILL.md`

Adds the reference patterns absorbed from the `fastapi-patterns` skill that Claude should apply when writing endpoint code.

- [ ] **Step 1: Append absorbed patterns section to the end of the file**

```markdown
## Reference Patterns

These patterns are absorbed from the former `fastapi-patterns` skill. Apply them automatically when writing endpoint code — do not present them as a reference guide to the user.

### CRUD Endpoint Patterns

Standard HTTP method mapping:

| Operation | Method | Status Code | Example Path |
|-----------|--------|-------------|--------------|
| List | GET | 200 | `/api/projects` |
| Get one | GET | 200 | `/api/projects/{id}` |
| Create | POST | 201 | `/api/projects` |
| Update (full) | PUT | 200 | `/api/projects/{id}` |
| Update (partial) | PATCH | 200 | `/api/projects/{id}` |
| Delete | DELETE | 204 | `/api/projects/{id}` |

### Pydantic Schema Hierarchy

When a resource needs multiple representations, follow this hierarchy:

```python
class ProjectBase(BaseModel):
    """Shared fields."""
    title: str = Field(..., description="The project title")
    description: str | None = Field(None, description="Optional summary")

class ProjectCreate(ProjectBase):
    """Fields required for creation (no id, no timestamps)."""
    pass

class ProjectUpdate(BaseModel):
    """All fields optional for partial updates."""
    title: str | None = Field(None, description="New title")
    description: str | None = Field(None, description="New summary")

class ProjectResponse(ProjectBase):
    """Full representation with server-generated fields."""
    id: str = Field(..., description="Unique identifier")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
```

Only create the models that are actually needed. If an endpoint only reads data, only create the Response model. YAGNI.

### Exception Handling

Use `HTTPException` with specific status codes and descriptive messages:

```python
from fastapi import HTTPException, status

# 404 — resource not found
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Project {project_id} not found"
)

# 409 — conflict
raise HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail=f"Project with title '{title}' already exists"
)

# 422 — validation (usually handled by Pydantic automatically)
```

Document these in the route decorator's `responses` parameter:
```python
@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={
        404: {"description": "Project not found"},
    },
)
```

### Dependency Injection

When the project uses `Depends()` for service injection, follow the existing pattern:

```python
from fastapi import Depends

@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectResponse]:
    """List all projects."""
    return await service.list_all()
```

Only use `Depends()` if the project already uses this pattern. Do not introduce dependency injection into a project that doesn't use it.
```

- [ ] **Step 2: Verify the section reads correctly**

Read the full file from top to bottom. Verify all phases are in order (0→1→2→3→4→5), Documentation Standards is between Phase 2 and Phase 3, Edge Cases follows Phase 5, and Reference Patterns is the final section.

- [ ] **Step 3: Commit**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "feat(api-docs): add absorbed FastAPI reference patterns"
```

---

### Task 8: Remove Superseded fastapi-patterns Skill

**Files:**
- Delete: `.claude/skills/fastapi-patterns/SKILL.md`
- Delete: `.claude/skills/fastapi-patterns/` (directory)

- [ ] **Step 1: Verify fastapi-patterns exists at expected location**

```bash
ls -la .claude/skills/fastapi-patterns/
```

Expected: `SKILL.md` file present.

- [ ] **Step 2: Check for any other files in the directory**

```bash
ls -la .claude/skills/fastapi-patterns/
```

If there are files besides `SKILL.md` (references/, examples/), check whether they contain real content or are just placeholders referenced in the skill. Based on exploration, the `references/` and `examples/` directories referenced in the skill do not exist — the skill only references them as hypothetical locations.

- [ ] **Step 3: Check for references to fastapi-patterns elsewhere**

```bash
grep -r "fastapi-patterns" CLAUDE.md .claude/ integrations/ 2>/dev/null
```

Expected: No references outside of the skill itself. If references are found, update them to point to `api-docs` instead.

- [ ] **Step 4: Delete the skill using git rm**

```bash
git rm -r .claude/skills/fastapi-patterns/
```

This both deletes and stages the removal in one step.

- [ ] **Step 5: Verify deletion**

```bash
ls .claude/skills/fastapi-patterns/ 2>&1
```

Expected: "No such file or directory"

- [ ] **Step 6: Commit**

```bash
git commit -m "chore: remove fastapi-patterns skill (superseded by api-docs)"
```

---

### Task 9: Full Skill Verification

**Files:**
- Read: `integrations/claude-code/extensions/api-docs/SKILL.md` (final review)

Verify the complete skill file is correct and well-structured.

- [ ] **Step 1: Read the complete SKILL.md**

Read the entire file top to bottom. Verify:

1. **Frontmatter** — `name: api-docs` and `description:` with trigger phrases are present
2. **Section order:**
   - Phase 0: Guard
   - Phase 1: Project Discovery
   - Phase 2: Mode Detection
   - Documentation Standards
   - Phase 3: Intercept Mode
   - Phase 4: Retrofit Mode
   - Phase 5: Postman Integration
   - Edge Cases
   - Reference Patterns
3. **No broken references** — No links to files that don't exist
4. **Code examples** — All code examples are syntactically correct Python
5. **Consistency** — Documentation Standards referenced correctly in both modes
6. **Pydantic v1/v2** — Both versions covered in standards, examples, and edge cases

- [ ] **Step 2: Verify the skill would be picked up by seeding service**

The seeding service at `python/src/server/services/extensions/extension_seeding_service.py` scans `integrations/claude-code/extensions/*/SKILL.md` for files with `name:` and `description:` in YAML frontmatter. Confirm:
- File is at `integrations/claude-code/extensions/api-docs/SKILL.md` (correct path)
- Frontmatter has `name:` field (required by seeding service)
- Frontmatter has `description:` field (used for display)

- [ ] **Step 3: Verify fastapi-patterns is fully removed**

```bash
find . -path "*/fastapi-patterns/SKILL.md" 2>/dev/null
```

Expected: No output (file is gone).

- [ ] **Step 4: Final commit if any adjustments were made**

```bash
git add integrations/claude-code/extensions/api-docs/SKILL.md
git commit -m "chore(api-docs): final verification pass"
```

Only commit if changes were made during verification. Skip if file is unchanged.

---

### Task 10: Test Against Cortex Codebase (Retrofit Mode)

**Human verification — not for automated execution.** This task requires a human to start a new Claude Code session with the skill installed.

**Files:**
- Read: `python/src/server/api_routes/*.py` (scan targets)

- [ ] **Step 1: Invoke the skill**

Tell Claude: *"Use the api-docs skill to audit the projects API endpoints in this repo."*

- [ ] **Step 2: Verify guard passes**

The skill should detect FastAPI in `python/src/server/api_routes/` and proceed. It should NOT output the "Skipping" message.

- [ ] **Step 3: Verify discovery works**

The skill should silently discover:
- Route directory: `python/src/server/api_routes/`
- Service directory: `python/src/server/services/`
- Models: inline in route files
- Pydantic version: v2
- App entry point: `python/src/server/main.py`

- [ ] **Step 4: Verify gap report**

The skill should produce a gap count and offer dry-run or fix-all. Based on the codebase exploration, most endpoints are missing `response_model`, `Field(description=...)`, explicit `status_code`, and `responses`.

- [ ] **Step 5: Run dry-run report**

Choose dry-run. Verify the table format shows files, endpoints, and missing items correctly.

- [ ] **Step 6: Document results**

Note any issues with the skill's behavior for follow-up. Do not apply fixes during this verification — this is just testing that the skill's scanning and reporting work correctly.
