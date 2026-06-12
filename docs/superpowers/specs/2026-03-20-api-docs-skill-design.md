# API Documentation Enforcement Skill — Design Spec

## Overview

A portable Claude Code skill that enforces FastAPI API documentation quality and generates Postman collection entries. Works in any FastAPI project by discovering project structure at runtime. Distributed through the Cortex skill library.

Supersedes the existing `fastapi-patterns` skill (located at `.claude/skills/fastapi-patterns/SKILL.md`) by absorbing its useful patterns and adding documentation enforcement, retrofit auditing, and Postman integration.

## Problem

FastAPI auto-generates OpenAPI docs at `/docs` and `/redoc`, but quality depends on how thoroughly each endpoint is annotated. Without enforcement, endpoints ship with missing `response_model`, no field descriptions, implicit status codes, and no examples — making the auto-generated docs nearly useless.

## Skill Identity

- **Name:** `api-docs`
- **Invocation:** `/api-docs` (explicit), or auto-triggers during endpoint work
- **Type:** Behavioral skill (SKILL.md only, no backend component)
- **Portability:** Works in any FastAPI project. No hardcoded paths.

### SKILL.md Frontmatter

```yaml
---
name: api-docs
description: Use when creating, modifying, or reviewing FastAPI API endpoints. Ensures endpoints have complete OpenAPI documentation including response models, field descriptions, status codes, and examples. Also generates Postman collection entries. Triggers on: "create endpoint", "add API route", "document API", "audit endpoints", "retrofit API docs", or when working in FastAPI route files.
---
```

### File Location

`integrations/claude-code/extensions/api-docs/SKILL.md`

This location ensures the Cortex extension seeding service discovers and registers the skill for distribution via bootstrap and extension sync.

## Guard

On activation, the skill scans for FastAPI patterns in Python files starting from the git repository root (or current working directory if not in a git repo).

### Scan Behavior

- **Search targets:** Files containing `APIRouter`, `FastAPI`, `@router.get`, `@router.post`, `@app.get`, `@app.post` (or any HTTP method decorator)
- **Scope:** All `.py` files from the project root
- **Exclusions:** Skip `venv/`, `.venv/`, `node_modules/`, `__pycache__/`, `.git/`, `site-packages/`
- **Short-circuit:** A single match is sufficient to confirm FastAPI is present

### Outcomes

- **If found:** Proceed to discovery and mode selection.
- **If not found:** Output *"Skipping API documentation — no FastAPI endpoints detected in this project."* and exit. No error, no further action.

## Project Discovery

Runs once per activation, before either mode executes. Discovers project layout silently.

### Steps

1. **Find Python package root** — Locate `pyproject.toml`, `setup.py`, or `requirements.txt` to identify the project root.
2. **Find all route files** — Scan for files containing `APIRouter()` or `FastAPI()`. This maps where routes live.
3. **Infer directory conventions from the route files:**
   - Route directory (e.g., `api_routes/`, `routes/`, `routers/`)
   - Service directory (look for files imported by routes, typically a sibling `services/` folder)
   - Model location (inline in route files, or separate `schemas.py`/`models.py` files)
4. **Detect Pydantic version** — Check `pyproject.toml`, `requirements.txt`, or installed package metadata for the Pydantic major version (v1 vs v2). This determines which syntax to use for model configuration and examples (see Documentation Standards).
5. **Find app entry point** — The file that calls `app.include_router(...)`, needed for full slice scaffolding.
6. **Check postman-integration availability** — If available, Postman generation is enabled. If not, that step is skipped.

### Output

An internal understanding of:
- Where routes live
- Where services live
- Where/how Pydantic models are defined (inline vs separate files)
- Pydantic version (v1 or v2)
- Where the app entry point is
- Whether Postman integration is available

No output to the user unless something unexpected is found (e.g., multiple FastAPI apps in one repo).

## Mode Detection

After discovery, determine which mode to run:

- **Intercept mode** — Claude is mid-task building a feature and creates/modifies endpoints. Activation is driven by the skill's frontmatter `description` field — Claude Code matches it against the current task context (e.g., working in a file that contains `APIRouter()`, creating route handlers, or the user mentioning endpoint creation).
- **Retrofit mode** — User explicitly asks to document or audit endpoints (e.g., "document all API endpoints", "audit the projects API", "generate API docs for this repo").
- **Ambiguous** — Ask the user which mode they want.

## Documentation Standards

Both modes enforce these standards. An endpoint is "fully documented" when it meets all of the following.

### Route Decorator

| Attribute | Requirement |
|---|---|
| `response_model` | Pydantic model defining the response shape |
| `status_code` | Explicit HTTP status code (201 for POST/create, 200 for GET, 204 for DELETE) |
| `tags` | At least one tag for Swagger UI grouping (typically the feature name) |
| `description` or docstring | One-line summary of what the endpoint does (either decorator `description` parameter or function docstring) |
| `responses` | Error response documentation for non-2xx status codes the endpoint can return (e.g., 404, 422) |

### Pydantic Models (Request and Response)

| Attribute | Requirement |
|---|---|
| Field definitions | Every field uses `Field()` with a `description` parameter |
| Required fields | `Field(..., description="...")` |
| Optional fields | `Field(None, description="...")` |
| Response examples | **Pydantic v2:** `model_config` with `json_schema_extra` example on response models |
|                   | **Pydantic v1:** `class Config` with `schema_extra` example on response models |

The skill detects the Pydantic version during project discovery and uses the appropriate syntax.

### Function Signature

| Attribute | Requirement |
|---|---|
| Parameters | Type hints on all parameters |
| Return type | Annotation matching `response_model` |

### Not Enforced

- Docstring format/length beyond "exists and is non-empty"
- Specific tag naming conventions (uses whatever the project uses, or feature name as fallback)
- Authentication/authorization patterns
- Service layer implementation details

## Intercept Mode

Activates during feature development when Claude creates or modifies endpoints.

### Trigger

Activation is handled by Claude Code's skill matching system via the frontmatter `description` field. The skill activates when Claude is working in files containing FastAPI route decorators or when the task context involves endpoint creation/modification. No manual signal detection is needed — this is the same mechanism all Claude Code skills use.

### Workflow

1. **Detect endpoint work** — Claude recognizes it's about to write or has just written a route handler.
2. **Apply standards inline** — As the endpoint is written, bake in all documentation standards. This is not a separate pass — it's how the endpoint gets written:
   - Route decorator with `response_model`, `status_code`, `tags`, `responses`
   - Pydantic models with `Field(description=...)` and examples (v1/v2 aware)
   - Docstring on the function
   - Return type annotation
3. **Full slice scaffolding (when applicable)** — If creating a new endpoint and supporting code doesn't exist:
   - Create a service method stub in the appropriate service file (discovered during project discovery)
   - If the service file doesn't exist, create it following the closest existing service pattern in the project
   - Wire the router into the app entry point if it's a new feature router
   - **Skip scaffolding if:** the project does not follow a service layer pattern (no existing service files found during discovery), or the endpoint is being added to an existing feature that already has its service wired up
4. **Postman handoff** — After the endpoint is complete, follow the postman-integration skill's rules to generate collection entries (see Postman Integration section).
5. **Continue** — The skill does not interrupt the developer's flow. No reports, no prompts. The endpoint comes out documented.

### Key Principle

Intercept mode is invisible when it works. The developer asks for a feature, and the endpoints come out fully documented with Postman entries. The skill is a quality standard, not a workflow step.

## Retrofit Mode

On-demand mode for documenting existing endpoints in a codebase.

### Trigger

User explicitly asks to document endpoints — e.g., "document all API endpoints", "audit the projects API", "generate API docs for this repo."

### Workflow

1. **Determine scope** — Based on the user's request:
   - **Whole repo:** Scan all route files found during discovery.
   - **Specific feature:** Scan only route files matching the feature name.

2. **Scan and count gaps** — For each endpoint in scope, check against documentation standards. Tally:
   - Total endpoints found
   - Number with gaps
   - Number of files affected
   - Types of gaps (missing response_model, missing Field descriptions, etc.)

3. **Report to user** — Example: *"Found 47 documentation gaps across 12 files (23 endpoints). Want a dry-run report first, or should I fix them all?"*

   **Dry-run report format:**
   ```
   | File | Endpoint | Missing |
   |------|----------|---------|
   | projects_api.py | GET /api/projects | response_model, tags |
   | projects_api.py | POST /api/projects | Field descriptions, json_schema_extra |
   | knowledge_api.py | GET /api/knowledge/search | response_model, status_code, responses |
   ```
   After the dry run, ask again: fix all, or skip.

4. **Fix in place** — Edit each route file:
   - Add missing `response_model` — create the Pydantic response model if it doesn't exist
   - Add `Field(description=...)` to all model fields
   - Add `status_code` to route decorators
   - Add `responses` for error status codes
   - Add docstrings where missing
   - Add examples to response models (v1/v2 aware)
   - Report progress during large operations: *"Fixed 8/23 endpoints (projects_api.py complete, starting tasks_api.py...)"*

5. **Postman handoff** — After all fixes are applied, follow the postman-integration skill's rules to generate collection entries for all documented endpoints in scope.

6. **Summary** — Example: *"Documented 23 endpoints across 12 files. Postman collection entries generated for all endpoints."*

### Key Principle

Retrofit mode is a bulk operation. Run once (or occasionally) to bring a codebase up to standard, not as part of daily development.

## Postman Integration

### How It Works

Both skills (api-docs and postman-integration) are behavioral SKILL.md files — there is no programmatic function call between them. The handoff works as follows:

1. **This skill gathers endpoint data** for each new/modified endpoint:
   - HTTP method and full path (e.g., `GET /api/projects/{project_id}/stats`)
   - Description from docstring
   - Request body schema (from Pydantic request model, if applicable)
   - Response body example (from model examples)
   - Path/query parameters with descriptions
   - Expected status codes (success and error)

2. **This skill then follows the postman-integration skill's rules** to act on that data:
   - **API mode:** Call `manage_postman(action="add_request")` MCP tool with the gathered data
   - **Git mode:** Write `.request.yaml` files to the `postman/` directory structure
   - The postman-integration skill's own mode detection (Rule 0: call `find_postman()`) determines which path to take

3. **If postman-integration is not available** — Output: *"Postman integration not available — skipping collection generation. Install the postman-integration skill to enable this."* and continue.

### Separation of Concerns

This skill gathers endpoint data and follows the postman-integration skill's rules to create entries. It does NOT own Postman collection structure, naming, or sync logic — that belongs to the postman-integration skill.

## Absorbed FastAPI Patterns

This skill supersedes the existing `fastapi-patterns` skill (located at `.claude/skills/fastapi-patterns/SKILL.md`). The following patterns are absorbed and applied automatically when writing code (not presented as reference material):

### Absorbed

- **CRUD endpoint patterns** — Route decorator conventions, response_model usage
- **Pydantic schema patterns** — Base/Create/Update/Response model hierarchy
- **Exception handling patterns** — HTTPException with proper status codes
- **Dependency injection patterns** — Service dependencies via `Depends()`

### Dropped

- Project structure recommendations (the skill discovers structure, doesn't prescribe it)
- Application factory pattern (out of scope)
- API versioning patterns (project-specific decision)
- References to external files that exist only within the fastapi-patterns skill directory

### Disposition

Once this skill is deployed, the `fastapi-patterns` SKILL.md at `.claude/skills/fastapi-patterns/` should be removed. This skill fully replaces it.

## Skill File Structure

**Location:** `integrations/claude-code/extensions/api-docs/SKILL.md`

Single file with YAML frontmatter (see Skill Identity section). No backend component, no Python scripts, no MCP tools. The skill is behavioral instructions for Claude Code — it reads and edits files directly using standard tools (Read, Write, Edit, Glob, Grep).

## Edge Cases

### Multiple FastAPI Apps in One Repo

If discovery finds multiple `FastAPI()` instances, ask the user which app to target.

### Models in Separate Files vs Inline

Discovery determines the convention. If the project uses separate schema files, the skill creates models there. If models are inline in route files, the skill follows that convention.

### Endpoints with Complex Response Types

Some endpoints return unions, lists of models, or raw dicts. The skill creates appropriate response models:
- `list[Item]` → `response_model=list[ItemResponse]`
- Raw dict → Create a typed response model to replace it
- Union types → Use Pydantic discriminated unions

### Existing Partial Documentation

Retrofit mode preserves existing documentation and only fills gaps. It does not overwrite existing docstrings, descriptions, or field annotations — only adds missing ones.

### Service Layer Doesn't Exist

If creating a new endpoint for a feature that has no service file, the skill creates a minimal service file following the closest existing service pattern in the project. If the project has no service layer at all (no service files found during discovery), skip service scaffolding entirely — only create the route and models.

### Pydantic v1 vs v2

The skill detects the Pydantic version during project discovery and uses the appropriate syntax:
- **v2:** `model_config = ConfigDict(...)`, `json_schema_extra`, `Field(...)`
- **v1:** `class Config`, `schema_extra`, `Field(...)`

If version cannot be determined, default to Pydantic v2 syntax (current standard).
